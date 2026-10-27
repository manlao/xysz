# -*- coding: utf-8 -*-
"""模拟交易 CLI 主入口（ad-sim-trade）

统一入口：python scripts/trade_cli.py <子命令>
12 个子命令覆盖 11 个柜台接口（buy/sell 共用 insert_order）。
仅支持限价委托、仅支持股票与 ETF。

示例：
  python scripts/trade_cli.py portfolio list
  python scripts/trade_cli.py buy --account-id 5 --code 600***.SH --volume 100
  python scripts/trade_cli.py buy --account-id 5 --code 600***.SH --volume 100 --price 9.70
  python scripts/trade_cli.py report --account-id 5
"""
import argparse
import json
import os
import sys

# 禁止在 skill 目录内生成 __pycache__（三级目录会导致 WorkBuddy 校验时报
# 「目录层级超限」）。必须在 import 本地模块之前设置。
sys.dont_write_bytecode = True

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import session
import trade_api
import portfolio_api as pf
import price_resolver
from common import TradeError, ConfigError, fmt_money

OK = common.OK_CODE


# ---------------------------------------------------------------- 输出

def out(data, as_json=False, table=None):
    """统一输出。table 为 (标题, DataFrame) 时以表格展示。"""
    if as_json:
        if table is not None:
            title, df = table
            if df is None:
                payload = {'title': title, 'rows': [], 'count': 0}
            else:
                payload = {
                    'title': title,
                    'count': int(len(df)),
                    'rows': json.loads(df.to_json(orient='records',
                                                 force_ascii=False)),
                }
        else:
            payload = data if isinstance(data, dict) else {'result': data}
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return
    if table is not None:
        title, df = table
        if df is None or len(df) == 0:
            print('%s：无数据' % title)
            return
        with pd_option():
            print('%s（%d 条）' % (title, len(df)))
            print(df.to_string(index=False))
        return
    if data is None:
        print('完成')
    elif isinstance(data, dict):
        for k, v in data.items():
            print('%-16s %s' % (k, v))
    else:
        print(data)


def pd_option():
    import pandas as pd
    return pd.option_context('display.max_columns', None,
                             'display.width', 200,
                             'display.unicode.east_asian_width', True)


def err(msg):
    print('✗ %s' % msg, file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- 子命令

def cmd_portfolio_list(a):
    session.login(need_market=False, need_trade=True)
    df = pf.get_list(status=a.status)
    out(None, a.json, ('组合列表', df))


def cmd_portfolio_create(a):
    session.login(need_market=False, need_trade=True)
    res = pf.create(a.name, a.desc or '')
    if not a.json:
        print('✓ 新建组合成功')
    out({
        '组合编号(account_id)': (res or {}).get('account_id'),
        '组合名称': (res or {}).get('portfolio_name'),
        '初始资金(元)': fmt_money((res or {}).get('begin_fund')),
        '组合描述': (res or {}).get('description') or '-',
        '创建时间': (res or {}).get('create_time'),
    }, a.json)


def cmd_portfolio_info(a):
    session.login(need_market=False, need_trade=True)
    df = pf.info(a.account_id, a.date)
    out(None, a.json, ('组合收益数据', df))


def cmd_portfolio_curve(a):
    session.login(need_market=False, need_trade=True)
    df = pf.curve(a.account_id, a.begin, a.end, a.len)
    out(None, a.json, ('历史收益率曲线', df))


def cmd_asset(a):
    session.login(need_market=False, need_trade=True)
    r = trade_api.query_asset(a.account_id)
    out({
        '资金账号id': (r or {}).get('account_id'),
        '总资产(元)': fmt_money((r or {}).get('total_asset')),
        '持仓市值(元)': fmt_money((r or {}).get('market_value')),
        '资金余额(元)': fmt_money((r or {}).get('leaves_value')),
        'T+1可用(元)': fmt_money((r or {}).get('available_t1')),
        '当前冻结(元)': fmt_money((r or {}).get('frozen_all')),
    }, a.json)


def cmd_position(a):
    session.login(need_market=False, need_trade=True)
    df = trade_api.query_position(a.account_id, a.code)
    out(None, a.json, ('持仓', df))


def cmd_order(a):
    session.login(need_market=False, need_trade=True)
    _warn_if_cleared(a.begin, a.end)
    df = trade_api.query_order(a.account_id, a.code, a.status, a.begin, a.end,
                           action_in=1 if a.cancellable else None)
    out(None, a.json, ('委托', df))


def cmd_trade(a):
    session.login(need_market=False, need_trade=True)
    _warn_if_cleared(a.begin, a.end)
    df = trade_api.query_trade(a.account_id, a.code, a.begin, a.end)
    if not a.all:
        df, dropped = _drop_unfilled(df)
        if dropped:
            print('提示：已剔除 %d 条未成交的撤单/废单占位记录（成交价为 0）。'
                  '如需查看全部记录请加 --all。\n' % dropped, file=sys.stderr)
    out(None, a.json, ('成交', df))


def _drop_unfilled(df):
    """剔除未成交的占位行（撤单/废单），只留确定成交的记录。"""
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


def _warn_if_cleared(begin, end):
    """17:00 盘后清算后不带日期查当日数据会为空，主动提示。"""
    if begin or end:
        return
    stage = common.current_stage()
    if stage in (common.STAGE_AFTER_CLEAR, common.STAGE_AFTER_DIV):
        print('提示：当前已过盘后清算时间（17:00），当日委托与成交已转为历史并清空。'
              '如需查看请用 --begin / --end 指定日期区间。\n', file=sys.stderr)


def cmd_max_qty(a):
    session.login(need_market=False, need_trade=True)
    price = a.price
    if price is None:
        raise TradeError('请通过 --price 指定委托价（查最大可买/卖需要价格）')
    side = 'Buy' if a.side.lower() == 'buy' else 'Sell'
    r = trade_api.query_max_qty(a.account_id, a.code, side, price)
    out({
        '可用资金(元)': fmt_money((r or {}).get('available')),
        '最大可%s数量(股)' % ('买' if side == 'Buy' else '卖'): (r or {}).get('max_qty'),
    }, a.json)


def cmd_cancel(a):
    session.login(need_market=False, need_trade=True)
    r = trade_api.cancel(a.order_id, a.account_id)
    print('✓ 撤单成功：委托编号 %s，状态 %s' % ((r or {}).get('order_id'),
                                          (r or {}).get('order_status')))


def _do_order(a, side):
    session.login(need_market=False, need_trade=True)
    try:
        res = trade_api.place_order(a.account_id, a.code, side, a.volume,
                                a.price, confirm=a.confirm)
    except price_resolver.NoQuoteError as e:
        err(str(e))
    plan = res['plan']
    fee = plan['fee']
    if res['needs_confirm']:
        print('⚠ 大额/异常委托需确认')
        print('  账户      : %s' % plan['account_id'])
        print('  方向      : %s' % ('买入' if side == 'Buy' else '卖出'))
        print('  代码      : %s%s' % (plan['code'],
              ' ' + plan['name'] if plan.get('name') else ''))
        print('  数量      : %d 股' % plan['volume'])
        print('  委托价    : %s（%s）' % (plan['price'], plan['price_source']))
        if plan.get('trade_time'):
            print('  行情时间  : %s' % plan['trade_time'])
        print('  预估金额  : %s 元' % fmt_money(plan['amount']))
        print('  预估费用  : 佣金 %s + 印花税 %s + 过户费 %s = %s 元'
              % (fee['commission'], fee['stamp_tax'], fee['transfer_fee'], fee['total']))
        print('  触发规则  :')
        for r_ in res['reasons']:
            print('     - %s' % r_)
        print('\n如确认执行，请追加参数 --confirm')
        return
    print('✓ 下单成功（限价委托）')
    print('  委托编号  : %s' % plan['order_id'])
    print('  账户      : %s' % plan['account_id'])
    print('  方向      : %s' % ('买入' if side == 'Buy' else '卖出'))
    print('  代码      : %s%s' % (plan['code'],
          ' ' + plan['name'] if plan.get('name') else ''))
    print('  数量      : %d 股' % plan['volume'])
    print('  委托价    : %s（%s）' % (plan['price'], plan['price_source']))
    print('  预估金额  : %s 元' % fmt_money(plan['amount']))
    print('  预估费用  : %s 元' % fee['total'])
    print('\n可用 order / trade 命令查看委托与成交进展。')


def cmd_buy(a):
    _do_order(a, 'Buy')


def cmd_sell(a):
    _do_order(a, 'Sell')


def cmd_report(a):
    import report_renderer
    session.login(need_market=False, need_trade=True)
    path = report_renderer.build(a.account_id, a.begin, a.end, a.out)
    print('✓ 报告已生成：%s' % path)


# ---------------------------------------------------------------- 解析器

def build_parser():
    p = argparse.ArgumentParser(
        description='星耀数智模拟交易 (ad-sim-trade)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''示例：
  portfolio list                                     查组合列表
  portfolio create --name 我的组合                      新建组合（初始资金固定100万）
  portfolio info --account-id 5                       组合收益数据
  buy --account-id 5 --code 600***.SH --volume 100    限价买入（自动取价）
  buy --account-id 5 --code 600***.SH --volume 100 --price 9.70   限价买入（指定价）
  sell --account-id 5 --code 600***.SH --volume 100   限价卖出
  cancel --account-id 5 --order-id 10005              撤单
  position --account-id 5                             查持仓
  order --account-id 5                                查当日委托
  trade --account-id 5                                查当日成交
  asset --account-id 5                                查资金
  max-qty --account-id 5 --code 600***.SH --side buy --price 9.70
  report --account-id 5                               生成可视化报告
''')
    p.add_argument('--json', action='store_true', help='以 JSON 输出')
    sub = p.add_subparsers(dest='cmd')

    # portfolio
    pp = sub.add_parser('portfolio', help='组合管理')
    psub = pp.add_subparsers(dest='sub')

    q = psub.add_parser('list', help='查组合列表')
    q.add_argument('--status', type=int, default=1, choices=[0, 1, 2, 3],
                   help='0-删除 1-正常(默认) 2-开户中 3-开户失败')
    q.set_defaults(func=cmd_portfolio_list)

    c = psub.add_parser('create', help='新建组合（初始资金固定100万）')
    c.add_argument('--name', required=False, help='组合名称（必填，1~50字符，不提供默认）')
    c.add_argument('--desc', help='组合描述（可选，≤200字符）')
    c.set_defaults(func=cmd_portfolio_create)

    i = psub.add_parser('info', help='组合收益数据')
    i.add_argument('--account-id', required=True, nargs='+', help='组合编号（可多个）')
    i.add_argument('--date', help='查询日期 YYYYMMDD（默认不限）')
    i.set_defaults(func=cmd_portfolio_info)

    cv = psub.add_parser('curve', help='历史收益率曲线')
    cv.add_argument('--account-id', required=True)
    cv.add_argument('--begin', help='起始日期 YYYYMMDD')
    cv.add_argument('--end', help='终止日期 YYYYMMDD')
    cv.add_argument('--len', type=int, dest='len', help='记录条数（与日期区间二选一）')
    cv.set_defaults(func=cmd_portfolio_curve)

    # 交易
    b = sub.add_parser('buy', help='限价买入')
    b.add_argument('--account-id', required=True)
    b.add_argument('--code', required=True, help='如 600***.SH')
    b.add_argument('--volume', type=int, required=True, help='数量（100整数倍）')
    b.add_argument('--price', type=float, help='委托价（省略则自动取价）')
    b.add_argument('--confirm', action='store_true', help='大额委托确认')
    b.set_defaults(func=cmd_buy)

    s = sub.add_parser('sell', help='限价卖出')
    s.add_argument('--account-id', required=True)
    s.add_argument('--code', required=True)
    s.add_argument('--volume', type=int, required=True)
    s.add_argument('--price', type=float)
    s.add_argument('--confirm', action='store_true')
    s.set_defaults(func=cmd_sell)

    cc = sub.add_parser('cancel', help='撤单')
    cc.add_argument('--account-id', required=True)
    cc.add_argument('--order-id', required=True, help='委托编号（counter_order_id）')
    cc.set_defaults(func=cmd_cancel)

    po = sub.add_parser('position', help='查持仓')
    po.add_argument('--account-id', required=True)
    po.add_argument('--code', help='代码（最多1只）')
    po.set_defaults(func=cmd_position)

    od = sub.add_parser('order', help='查委托')
    od.add_argument('--account-id', required=True)
    od.add_argument('--code', nargs='*', help='代码列表')
    od.add_argument('--status', nargs='*', help='状态列表，如 Filled New')
    od.add_argument('--begin', help='起始日期 YYYYMMDD（须与 --end 成对使用）')
    od.add_argument('--end', help='终止日期 YYYYMMDD（须与 --begin 成对使用）')
    od.add_argument('--cancellable', action='store_true',
                    help='只查可撤单委托')
    od.set_defaults(func=cmd_order)

    td = sub.add_parser('trade', help='查成交（默认仅显示确定成交的记录）')
    td.add_argument('--account-id', required=True)
    td.add_argument('--code', nargs='*')
    td.add_argument('--begin', help='起始日期 YYYYMMDD（须与 --end 成对使用）')
    td.add_argument('--end', help='终止日期 YYYYMMDD（须与 --begin 成对使用）')
    td.add_argument('--all', action='store_true',
                    help='显示全部记录（含未成交的撤单/废单占位行）')
    td.set_defaults(func=cmd_trade)

    as_ = sub.add_parser('asset', help='查资金')
    as_.add_argument('--account-id', required=True)
    as_.set_defaults(func=cmd_asset)

    mq = sub.add_parser('max-qty', help='查最大可买/卖')
    mq.add_argument('--account-id', required=True)
    mq.add_argument('--code', required=True)
    mq.add_argument('--side', required=True, choices=['buy', 'sell'])
    mq.add_argument('--price', type=float, required=True)
    mq.set_defaults(func=cmd_max_qty)

    rp = sub.add_parser('report', help='生成可视化 HTML 报告')
    rp.add_argument('--account-id', required=True)
    rp.add_argument('--begin')
    rp.add_argument('--end')
    rp.add_argument('--out', help='输出文件路径')
    rp.set_defaults(func=cmd_report)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, 'func', None):
        parser.print_help()
        sys.exit(0)
    try:
        args.func(args)
    except (ConfigError, session.LoginError, TradeError) as e:
        err(str(e))
    except KeyboardInterrupt:
        err('已取消')


if __name__ == '__main__':
    main()