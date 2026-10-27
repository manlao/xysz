# -*- coding: utf-8 -*-
"""交易接口封装（7 个）：下单 / 撤单 / 查资金 / 查持仓 / 查委托 / 查成交 / 查最大可买

仅支持限价委托（price_type 恒为 Limit），仅支持股票与 ETF。
下单前做两级风控（方案 C：常规单直接执行，危险单需 --confirm）。
"""
import session
from common import TradeError, check, parse_code, estimate_fee, is_tradable
import price_resolver

# 二级风控阈值
LARGE_RATIO = 0.50          # 单笔占账户总资产比例（50%）
LARGE_AMOUNT = 500000.0     # 单笔绝对金额（元）
LARGE_VOLUME = 100000       # 数量阈值（股）


def _snapshot_row(code):
    """取当前快照最后一行（用于涨跌停与限价上下限校验），取不到返回 None。

    注意 query_snapshot 返回结构是 {日期键: {代码: DataFrame}}，
    日期键后端可能是 str 也可能是 int，须两种都试。
    """
    try:
        import datetime
        md = session.market_data()
        today = datetime.date.today()
        td = int(today.strftime('%Y%m%d'))
        snap = md.query_snapshot([code], begin_date=td, end_date=td)
        if not snap:
            return None
        sub = None
        for k in (str(td), td):
            if k in snap:
                sub = snap[k]
                break
        if sub is None:
            sub = list(snap.values())[0] if len(snap) else None
        if not isinstance(sub, dict):
            return None
        df = sub.get(code)
        if df is None or len(df) == 0:
            return None
        return df.iloc[-1]
    except Exception:
        return None


def query_asset(account_id):
    """查资金。"""
    tr = session.trade_module()
    res, code = tr.query_asset(account_id)
    check(code, '查询资金')
    return res


def query_position(account_id, code=None):
    """查持仓。code 必须传 list（单只也写 ['600***.SH']），本接口最多 1 只。"""
    tr = session.trade_module()
    codes = None
    if code:
        codes = [code] if isinstance(code, str) else list(code)
        if len(codes) > 1:
            raise TradeError('query_position 最多传 1 只代码，请改用 order 或 trade 查询多标的。')
    df, code_ = tr.query_position(account_id, code=codes)
    check(code_, '查询持仓')
    return df


def query_order(account_id, code=None, status=None, begin_date=None, end_date=None,
                action_in=None):
    """查委托。

    不传日期即查当日。status 必须传 list。
    begin_date/end_date **必须成对使用**（要么都传、要么都不传）。
    action_in  0 查当日委托（默认）/ 1 查可撤单委托（此时不与日期区间合并）。

    注意：传日期区间时，只要区间结束日不早于当日，返回结果**一定包含当日委托**，
    即使当日尚未完成盘后清算也能查到。
    """
    _check_date_pair(begin_date, end_date)
    tr = session.trade_module()
    kw = {}
    if code:
        kw['code'] = [code] if isinstance(code, str) else list(code)
    if status:
        kw['order_status'] = [status] if isinstance(status, str) else list(status)
    if begin_date is not None:
        kw['begin_date'] = int(begin_date)
    if end_date is not None:
        kw['end_date'] = int(end_date)
    if action_in is not None:
        kw['action_in'] = int(action_in)
    df, code_ = tr.query_order(account_id, **kw)
    check(code_, '查询委托')
    return df


def _check_date_pair(begin_date, end_date):
    """begin_date 与 end_date 必须成对使用。"""
    if (begin_date is None) != (end_date is None):
        raise TradeError(
            '查询日期区间必须成对使用：--begin 与 --end 要么都传、要么都不传。\n'
            '（只查当日请两个都不传；查历史区间请同时指定起止日期）')
    if begin_date is not None and int(begin_date) > int(end_date):
        raise TradeError('起始日期 %s 不能晚于终止日期 %s。' % (begin_date, end_date))


def query_trade(account_id, code=None, begin_date=None, end_date=None):
    """查成交。不传日期即查当日。code 必须传 list。日期须成对使用。"""
    _check_date_pair(begin_date, end_date)
    tr = session.trade_module()
    kw = {}
    if code:
        kw['code'] = [code] if isinstance(code, str) else list(code)
    if begin_date is not None:
        kw['begin_date'] = int(begin_date)
    if end_date is not None:
        kw['end_date'] = int(end_date)
    df, code_ = tr.query_trade(account_id, **kw)
    check(code_, '查询成交')
    return df


def query_max_qty(account_id, code, side, price):
    """查最大可买/卖数量。"""
    tr = session.trade_module()
    parse_code(code)
    if side not in ('Buy', 'Sell'):
        raise TradeError('方向仅支持 Buy 或 Sell，当前：%s' % side)
    res, code_ = tr.query_max_qty(account_id, code, tr.SideType[side], float(price))
    check(code_, '查询最大可交易数量')
    return res


def cancel(order_id, account_id):
    """撤单。order_id 取自委托查询的 counter_order_id 列。"""
    tr = session.trade_module()
    res, code = tr.cancel_order(order_id, account_id)
    check(code, '撤单')
    return res


# ---------------------------------------------------------------- 下单

def _big_order_reasons(account_id, side, price, volume, total_asset=None,
                       avail=None):
    """二级风控：返回触发的规则说明列表（空表示常规单）。

    total_asset / avail 由调用方传入，避免重复查询柜台。
    """
    reasons = []
    amount = price * volume
    if total_asset:
        if amount >= total_asset * LARGE_RATIO:
            reasons.append('单笔金额 %.2f 元，占账户总资产 %.2f 元的 %.1f%%（阈值 %.0f%%）'
                           % (amount, total_asset,
                              amount / total_asset * 100, LARGE_RATIO * 100))
    if amount >= LARGE_AMOUNT:
        reasons.append('单笔金额 %.2f 元达到绝对阈值 %.0f 元' % (amount, LARGE_AMOUNT))
    if volume >= LARGE_VOLUME:
        reasons.append('委托数量 %d 股达到数量阈值 %d 股' % (volume, LARGE_VOLUME))
    if side == 'Sell' and avail:
        if volume >= avail:
            reasons.append('卖出数量 %d 股覆盖全部可用持仓 %d 股，清仓后不可撤销'
                           % (volume, avail))
    return reasons


def place_order(account_id, code, side, volume, price=None, confirm=False):
    """限价下单。

    price 为 None 时自动取价；否则直接用该价（不取行情）。
    返回 dict：plan（计划） / order_id / needs_confirm。
    """
    code6, _ = parse_code(code)
    if side not in ('Buy', 'Sell'):
        raise TradeError('方向仅支持 Buy 或 Sell，当前：%s' % side)
    # 可下单品种校验（官方 is_security_type 口径，与柜台 _check_order_type 一致）
    if not is_tradable(code):
        raise TradeError(
            '仅支持股票与 ETF，%s 不在可下单范围内（可转债、国债、指数、基金等'
            '品种均不支持）。' % code)
    volume = int(volume)
    if volume <= 0:
        raise TradeError('委托数量必须为正整数')

    auto_price = price is None
    if auto_price:
        # 需要行情 → 完整登录 + 初始化柜台
        session.login(need_market=True, need_trade=True)
        info_q = price_resolver.resolve_price(code)
        final_price = float(info_q['price'])
        price_source = info_q['source']
        trade_time = info_q.get('trade_time')
    else:
        # 用户指定价格 → 只初始化柜台，不取行情
        session.login(need_market=False, need_trade=True)
        final_price = float(price)
        price_source = '用户指定'
        trade_time = None

    amount = final_price * volume
    fee = estimate_fee(code6, amount)

    # ---------- 一级硬拦截 ----------
    # 资金 / 持仓充足性（查询结果复用到二级风控，避免重复请求柜台）
    total_asset = None
    avail_qty = None
    if side == 'Buy':
        v_err = price_resolver.validate_volume(code, volume, side)
        if v_err:
            raise TradeError(v_err)
    else:
        # 卖出需先查持仓，才能判断零股清仓与可用数量
        pos = query_position(account_id, code)
        if pos is None or len(pos) == 0:
            raise TradeError('卖出查无持仓（该账户当前无 %s 持仓）。' % code)
        row = pos.iloc[0]
        avail = int(row.get('available_qty') or 0)
        total = int(row.get('leaves_qty') or 0)
        frozen = int(row.get('stock_sale') or 0)
        avail_qty = avail
        v_err = price_resolver.validate_volume(code, volume, side,
                                               available_qty=avail)
        if v_err:
            raise TradeError(v_err)

    p_err = price_resolver.validate_price(code, final_price, side,
                                          snapshot_row=None if auto_price else _snapshot_row(code))
    if p_err:
        raise TradeError(p_err)

    if side == 'Buy':
        mq = query_max_qty(account_id, code, side, final_price)
        max_qty = int((mq or {}).get('max_qty') or 0)
        if max_qty and volume > max_qty:
            raise TradeError('可用资金不足，最多可买 %d 股，本次申请 %d 股。' % (max_qty, volume))
        ast = query_asset(account_id)
        total_asset = float((ast or {}).get('total_asset') or 0)
    else:
        if volume > avail_qty:
            if avail_qty == 0 and total > 0:
                # 可用为 0 但有持股：区分 T+1 锁定与卖出冻结
                if frozen > 0:
                    raise TradeError(
                        '卖出持仓不足：%s 持股 %d 股全部处于卖出冻结状态，可用 0 股，'
                        '请先撤销在途的卖出委托。' % (code, total))
                raise TradeError(
                    '%s 持仓 %d 股全部处于 T+1 锁定状态（当日买入当日不可卖出），'
                    '最早可卖日为下一交易日。' % (code, total))
            raise TradeError(
                '卖出持仓不足，可用 %d 股（总持股 %d 股，其中 %d 股卖出冻结），本次申请 %d 股。'
                % (avail_qty, total, frozen, volume))
        ast = query_asset(account_id)
        total_asset = float((ast or {}).get('total_asset') or 0)

    plan = {
        'account_id': account_id,
        'code': code,
        'name': _sec_name(code),
        'side': side,
        'volume': volume,
        'price': round(final_price, 4),
        'price_source': price_source,
        'trade_time': str(trade_time) if trade_time is not None else None,
        'amount': round(amount, 2),
        'fee': fee,
    }

    # ---------- 二级风控 ----------
    reasons = _big_order_reasons(account_id, side, final_price, volume,
                                 total_asset=total_asset, avail=avail_qty)
    if reasons and not confirm:
        return {'plan': plan, 'order_id': None, 'needs_confirm': True,
                'reasons': reasons}
    if reasons:
        plan['confirmed_reasons'] = reasons

    tr = session.trade_module()
    order_id, code_ = tr.insert_order(account_id, code, float(final_price),
                                      volume, tr.SideType[side], tr.PriceType.Limit)
    check(code_, '下单')
    plan['order_id'] = order_id
    # 委托成功后从委托表回读证券简称
    name = _sec_name_from_orders(tr, account_id, code)
    if name:
        plan['name'] = name
    return {'plan': plan, 'order_id': order_id, 'needs_confirm': False}


def _sec_name_from_orders(tr, account_id, code):
    """从当日委托记录中读取证券简称。"""
    try:
        df, _ = tr.query_order(account_id, code=[code])
        if df is not None and len(df) and 'security_name' in df.columns:
            return df.iloc[-1].get('security_name')
    except Exception:
        pass
    return None


def _sec_name(code):
    """证券简称占位：快照无名称字段，由 _sec_name_from_orders 在委托成功后回填。"""
    return None