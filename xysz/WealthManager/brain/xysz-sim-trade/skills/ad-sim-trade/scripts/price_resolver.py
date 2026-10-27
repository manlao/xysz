# -*- coding: utf-8 -*-
"""取价引擎：三条取价路径 + 限价上下限校验

路径分流（见 SKILL.md 5.0）：
- 用户指定 price → 不取行情，直接用该价
- 未指定 · 连续竞价（09:15-11:30 / 13:00-15:30）→ 快照回退链取 last
- 未指定 · 午休（11:30-13:00）→ 午休专用链：end=11:31:00，begin 从 11:29 起三角数回退
- 未指定 · 非交易时段 → 最近已完成交易日收盘价

回退链增量序列（分钟）：1, 3, 6, 10, 15, 21, 28, 36, 45, 55, 66, 78, 91, 105, 120 ...
                     每次递增 1, 2, 3, 4, 5, 6 ...（三角数）
begin 回退到 09:15 之前仍无数据 → 抛 NoQuoteError，报「无行情，不能下单」。
"""
import datetime

import session
from common import (TradeError, current_stage, is_snapshot_stage, parse_code,
                    price_tick, board_of, STAGE_NOON, STAGE_NON_TRADING_DAY,
                    STAGE_PRE)

def _build_fallback(minutes=420, step_start=1):
    """构造三角数增量序列：1, 3, 6, 10, 15, 21, ...

    每次递增 1, 2, 3, 4 ...，直到超过 minutes。
    默认覆盖到 420 分钟（7 小时），确保 09:15 → 15:30（375 分钟）
    的整个交易时段都能回溯到开盘，不会在午后中途断掉。
    """
    seq, delta, step = [], 0, step_start
    while True:
        delta += step
        if delta > minutes:
            break
        seq.append(delta)
        step += 1
    return tuple(seq)


# 回退链的增量序列（分钟），三角数增量
FALLBACK_MINUTES = _build_fallback()

# 快照查询的结束时间（9 位 HHMMSS000）
END_TIME_AUCTION = 153100000   # 连续竞价：固定当日 15:31:00
END_TIME_NOON = 113100000      # 午休：固定 11:31:00

# 回退下界：09:15:00
_TS_0915 = 91500000


class NoQuoteError(TradeError):
    """无行情，无法取价"""


def _ts(dt):
    """datetime → 9 位时间戳 HHMMSS000。"""
    return dt.hour * 10000000 + dt.minute * 100000 + dt.second * 1000


def _is_kcb(code6):
    return board_of(code6) == 'star'


def _fetch_snapshot(code, begin_time, end_time, day):
    """查询当日快照，返回 DataFrame 或 None。

    注意两点（实测）：
    1. query_snapshot 返回结构是 {日期str: {代码: DataFrame}}，须按两层解析；
    2. begin_time/end_time 必须是 8/9 位（时分秒毫秒），传 6 位会静默返回 0 行。
    """
    md = session.market_data()
    day_i = int(day.strftime('%Y%m%d'))
    try:
        snap = md.query_snapshot([code], begin_date=day_i, end_date=day_i,
                                 begin_time=begin_time, end_time=end_time)
    except Exception as e:
        raise NoQuoteError('查询快照失败：%s: %s' % (type(e).__name__, e))
    if not snap:
        return None
    # 日期键后端可能是 str 也可能是 int，两种都试
    sub = snap.get(str(day_i))
    if sub is None:
        sub = snap.get(day_i)
    if sub is None and len(snap):
        # 兜底：取第一个日期分组
        sub = list(snap.values())[0]
    if not isinstance(sub, dict):
        return None
    df = sub.get(code)
    if df is None or len(df) == 0:
        return None
    return df


def _resolve_snapshot(code, day, base_dt, end_time, label):
    """回退链取价：从 base_dt 起按三角数向前回退 begin_time。

    返回 dict：price / source / trade_time / fallback_level
    """
    day_i = int(day.strftime('%Y%m%d'))
    # 当日快照最早只能从 09:15 起算（更早无数据）
    day_open = datetime.datetime(day.year, day.month, day.day, 9, 15, 0)
    if base_dt < day_open:
        base_dt = day_open

    for i, delta in enumerate(FALLBACK_MINUTES):
        bt_dt = base_dt - datetime.timedelta(minutes=delta)
        if bt_dt < day_open:
            break
        begin_time = _ts(bt_dt)
        if begin_time < _TS_0915:
            break
        df = _fetch_snapshot(code, begin_time, end_time, day)
        if df is not None:
            row = df.iloc[-1]
            price = row.get('last')
            if price is not None and float(price) > 0:
                return {
                    'price': float(price),
                    'source': label,
                    'trade_time': row.get('trade_time'),
                    'fallback_level': i + 1,
                    'fallback_minutes': delta,
                    'limit_up': _f(row, 'high_limited'),
                    'limit_down': _f(row, 'low_limited'),
                    'ask1': _f(row, 'ask_price1'),
                    'bid1': _f(row, 'bid_price1'),
                    'pre_close': _f(row, 'pre_close'),
                }
    raise NoQuoteError(
        '无行情，不能下单：%s 在 %s 未取到当日快照数据（已回退 %d 档，最早回溯至 09:15）。\n'
        '可能原因：证券代码不存在、尚未上市、当日无成交或行情服务异常。'
        % (code, day.strftime('%Y-%m-%d'), len(FALLBACK_MINUTES)))


def _f(row, key):
    v = row.get(key)
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _close_price_of(code, day_i):
    """取指定交易日的日线收盘价（不做复权——用于下单定价）。"""
    md = session.market_data()
    import AmazingData as ad
    try:
        kl = md.query_kline([code], begin_date=day_i, end_date=day_i,
                            period=ad.constant.Period.day.value)
    except Exception as e:
        raise NoQuoteError('查询日线失败：%s: %s' % (type(e).__name__, e))
    df = kl.get(code) if kl else None
    if df is None or len(df) == 0:
        return None
    v = df.iloc[-1].get('close')
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def resolve_price(code, now=None):
    """自动取价（用户未指定价格时调用）。

    返回 dict：price / source / trade_time 等，source 为中文说明。
    """
    now = now or datetime.datetime.now()
    parse_code(code)  # 先校验代码格式
    trading_day = session.is_trading_day(now.date())
    stage = current_stage(now=now, is_trading_day=trading_day)

    # 路径 A：连续竞价 / 午休 → 快照回退链
    if is_snapshot_stage(stage):
        day = now.date()
        if stage == STAGE_NOON:
            # 午休：end 固定 11:31:00，begin 从 11:29 起三角数回退
            base = datetime.datetime(day.year, day.month, day.day, 11, 29, 0)
            return _resolve_snapshot(code, day, base, END_TIME_NOON,
                                     '午间休市·上午收盘最新价')
        # 连续竞价：end 固定 15:31:00，begin 从 now-1min 起三角数回退
        return _resolve_snapshot(code, day, now, END_TIME_AUCTION, '当日快照最新价')

    # 路径 B：非交易时段 → 最近已完成交易日收盘价
    target = session.last_completed_trading_day()
    price = _close_price_of(code, target)
    if price is None:
        # 再往前找，最多 5 个交易日
        cal = [int(x) for x in session.calendar()]
        prev = [x for x in cal if x < target][-5:]
        for d in reversed(prev):
            price = _close_price_of(code, d)
            if price is not None:
                target = d
                break
    if price is None:
        raise NoQuoteError('无行情，不能下单：%s 未取到任何可用收盘价。' % code)
    src_map = {
        STAGE_NON_TRADING_DAY: '非交易日·最近交易日收盘价',
        STAGE_PRE: '盘前·最近交易日收盘价',
    }
    return {
        'price': round(price, 4),
        'source': src_map.get(stage, '盘后·最近交易日收盘价'),
        'trade_time': None,
        'trade_date': target,
        'limit_up': None,
        'limit_down': None,
    }


# ---------------------------------------------------------------- 限价校验

def price_bounds(code, snapshot_row=None, side='Buy'):
    """按文档 2.4 计算限价委托价格上下限。

    基准价取自盘口：
      买入基准价：卖一价 → 买一价 → 最新价 → 昨收
      卖出基准价：买一价 → 卖一价 → 最新价 → 昨收

    上下限：
      沪主板/深主板/创业板：上限 = max(买入基准价×102%, 买入基准价+10个价位)
                            下限 = min(卖出基准价×98%,  卖出基准价-10个价位)
      科创板：上限 = 买入基准价×102%；下限 = 卖出基准价×98%
    """
    tick = price_tick(code)
    code6 = parse_code(code)[0]
    if snapshot_row is None:
        return None
    if side == 'Buy':
        base = _first_pos(snapshot_row, 'ask_price1', 'bid_price1', 'last', 'pre_close')
    else:
        base = _first_pos(snapshot_row, 'bid_price1', 'ask_price1', 'last', 'pre_close')
    if base is None:
        return None
    if _is_kcb(code6):
        up = base * 1.02
        down = base * 0.98
    else:
        up = max(base * 1.02, base + 10 * tick)
        down = min(base * 0.98, base - 10 * tick)
    return {'base': round(base, 4), 'upper': round(up, 4),
            'lower': round(down, 4), 'tick': tick}


def _first_pos(row, *keys):
    for k in keys:
        v = _f(row, k)
        if v is not None and v > 0:
            return v
    return None


def validate_price(code, price, side, snapshot_row=None):
    """校验委托价：最小价位 + 限价上下限。返回警告信息（None 表示通过）。"""
    tick = price_tick(code)
    # 最小价位：ETF 0.001，股票 0.01
    if abs(round(price / tick) - price / tick) > 1e-6:
        return '委托价 %s 不符合最小价差要求（%s 的最小价位为 %s）' % (
            price, '场内基金' if tick == 0.001 else '股票', tick)
    b = price_bounds(code, snapshot_row, side)
    if b is None:
        return None  # 取不到盘口，交由柜台判断
    if side == 'Buy' and price > b['upper']:
        return '委托价 %.4f 超出买入上限 %.4f（基准价 %.4f）' % (price, b['upper'], b['base'])
    if side == 'Sell' and price < b['lower']:
        return '委托价 %.4f 低于卖出下限 %.4f（基准价 %.4f）' % (price, b['lower'], b['base'])
    return None


def validate_volume(code, volume, side, available_qty=None):
    """校验委托数量。

    交易单位：普通A股/ETF = 100 股整数倍；科创板 = >200 股整数。
    卖出零股：余额不足 100 股（科创板 200 股）的部分**可一次性申报卖出**，
    因此卖出时只要不超过 available_qty 即放行（含零股）。
    """
    if volume is None or int(volume) <= 0:
        return '委托数量必须为正整数'
    v = int(volume)
    b = board_of(code)
    lot = 200 if b == 'star' else 100
    if side == 'Sell':
        # 卖出：不超可用持仓即允许（零股可一次性清仓）
        if available_qty is not None and v <= int(available_qty):
            return None
        if b == 'star':
            if v <= 200:
                return '科创板卖出数量须大于 200 股'
        else:
            if v % 100 != 0:
                return '卖出数量 %d 不是 100 的整数倍' % v
    else:
        if b == 'star':
            if v <= 200:
                return '科创板买入数量须大于 200 股的整数'
        else:
            if v % 100 != 0:
                return '买入数量 %d 不是 100 的整数倍，请改为 100 / 200 / 300…' % v
    return None