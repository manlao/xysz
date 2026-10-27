# -*- coding: utf-8 -*-
"""HTML 报告渲染（fresh-light 清新浅色风格 + 移动端适配）

模块：概览卡片 / 净值曲线 / 收益指标 / 持仓明细 / 委托明细 / 成交明细
"""
import os
import json
import datetime

import portfolio_api as pf
import trade_api

TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'assets', 'report_template.html')

STATUS_CN = {
    'New': '已申报', 'PartiallyFilled': '部分成交', 'Filled': '全部成交',
    'PartiallyFilledPartiallyCancelled': '部分成交部分撤销', 'Cancelled': '已撤销',
    'PartiallyCancelled': '部分撤销', 'Reject': '已拒绝',
    'WaitCancelled': '待撤销', 'PartiallyFilledWaitCancelled': '部成待撤',
    'Sended': '已发送', 'UnSend': '未发送', 'Undefined': '未知',
}


def _f(v, nd=2):
    if v is None:
        return None
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


def _hms(v):
    """柜台时间 HHMMSS 整数 → HH:MM:SS。"""
    if v is None:
        return None
    try:
        s = str(int(v)).zfill(6)
    except (TypeError, ValueError):
        return v
    return '%s:%s:%s' % (s[0:2], s[2:4], s[4:6])


def _filter_filled_trades(df):
    """只保留确定成交的记录。

    柜台的成交表会为**撤单、废单**也写入占位行（match_price=0 / trade_value=0 /
    fee=0，match_qty 却等于委托数量），若不剔除会在「成交明细」里显示成
    成交价 0.000、成交额 0.00 的空记录。

    判据：成交价 > 0（等价于成交额 > 0）。部分成交时成交价仍大于 0，同样保留。

    返回 (过滤后的 df, 被剔除的行数)。
    """
    if df is None or len(df) == 0:
        return df, 0
    if 'match_price' in df.columns:
        mask = df['match_price'].fillna(0) > 0
    elif 'trade_value' in df.columns:
        mask = df['trade_value'].fillna(0) > 0
    else:
        return df, 0
    dropped = int((~mask).sum())
    return df[mask], dropped


def _esc(v):
    if v is None:
        return '-'
    return str(v).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _records(df, cols):
    """DataFrame → list[dict]，只取指定列，空值转 None。"""
    if df is None or len(df) == 0:
        return []
    out = []
    for _, row in df.iterrows():
        d = {}
        for c in cols:
            d[c] = None if c not in df.columns else row.get(c)
        out.append(d)
    return out


def build(account_id, begin=None, end=None, out_path=None):
    """生成报告，返回输出路径。"""
    ast = trade_api.query_asset(account_id)
    ast = ast or {}
    info_df = pf.info([account_id])
    info = {}
    if info_df is not None and len(info_df):
        info = {k: info_df.iloc[0].get(k) for k in info_df.columns}

    curve_df = pf.curve(account_id, begin, end)
    pos_df = trade_api.query_position(account_id)
    order_df = trade_api.query_order(account_id, begin_date=begin, end_date=end)
    trade_df = trade_api.query_trade(account_id, begin_date=begin, end_date=end)
    trade_df, trade_filtered = _filter_filled_trades(trade_df)

    total_asset = _f(ast.get('total_asset'))
    market_value = _f(ast.get('market_value'))
    position_ratio = (market_value / total_asset) if (total_asset and market_value) else None

    data = {
        'account_id': account_id,
        'portfolio_name': None,
        'generated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'summary': {
            'total_asset': total_asset,
            'market_value': market_value,
            'leaves_value': _f(ast.get('leaves_value')),
            'available_t1': _f(ast.get('available_t1')),
            'frozen_all': _f(ast.get('frozen_all')),
            'position_ratio': _f(position_ratio, 4),
            'total_profit_rate': _f(info.get('total_profit_rate'), 6),
            'day_profit_rate': _f(info.get('day_profit_rate'), 6),
            'total_profit_num': _f(info.get('total_profit_num')),
            'max_retracement': _f(info.get('max_retracement'), 6),
            'current_net_value': _f(info.get('current_net_value'), 4),
            'win_win': info.get('win_win'),
            'win_loss': info.get('win_loss'),
            'win_draw': info.get('win_draw'),
        },
        'curve': _records(curve_df, ['date', 'profit_rate']),
        'positions': _records(pos_df, ['code', 'security_name', 'available_qty',
                                       'cost_price', 'last_price', 'market_value',
                                       'profit_loss']),
        'orders': _records(order_df, ['insert_time', 'code', 'security_name', 'side',
                                      'order_status', 'order_price', 'order_qty',
                                      'trade_qty', 'counter_order_id']),
        'trades': _records(trade_df, ['match_time', 'code', 'side',
                                      'match_price', 'match_qty', 'trade_value', 'fee']),
    }
    data['summary']['position_ratio_pct'] = (
        round(position_ratio * 100, 2) if position_ratio is not None else None)
    data['trade_dropped'] = trade_filtered

    # 时间字段格式化：柜台 HHMMSS 整数 → HH:MM:SS
    for r in data['orders']:
        r['insert_time'] = _hms(r.get('insert_time'))
    for r in data['trades']:
        r['match_time'] = _hms(r.get('match_time'))

    # 名称：try get from portfolio list
    try:
        lst = pf.get_list(status=1)
        if lst is not None and len(lst):
            m = lst[lst['account_id'].astype(str) == str(account_id)]
            if len(m):
                data['portfolio_name'] = m.iloc[0].get('portfolio_name')
    except Exception:
        pass

    with open(TEMPLATE, encoding='utf-8') as f:
        html = f.read()
    payload = json.dumps(data, ensure_ascii=False, default=str)
    html = html.replace('__REPORT_DATA__', payload)
    html = html.replace('__STATUS_CN__', json.dumps(STATUS_CN, ensure_ascii=False))

    if not out_path:
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        out_path = os.path.join(os.getcwd(),
                                'sim_trade_report_%s_%s.html' % (account_id, ts))
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return out_path