# -*- coding: utf-8 -*-
"""
rebalance_calc.py — 从目标权重算出调仓买卖清单

用途
----
Step 5 要给用户「调仓规则」，但只有权重百分比是不够的——用户真正要执行的是
"现在每个品种该买多少、该卖多少"。本脚本把「目标权重 + 当前持仓市值」转成
一张可直接照着下单的清单。

它同时回答了资产配置里最容易被忽略的两个问题：
  1. 哪些该先卖（换手最小化：先卖超出目标最多的品种）
  2. 买多少要向下取整到 100 份/手，且估算最低佣金对实际投入的侵蚀

用法
----
    python rebalance_calc.py --total 500000 \
        --target 黄金:0.15,国债:0.25,宽基:0.40,窄基:0.05,现金:0.15 \
        --current 黄金:120000,国债:80000,宽基:150000,窄基:50000,现金:100000

价格从哪来
----------
**价格一律从星耀数智（AmazingData）实时取最新收盘价，不使用任何硬编码价格。**
价格会变，写死会导致手数取整和佣金估算全错（例如黄金实际 6.5 元时，
按 5.92 元算出的手数会少买 1~2 手）。

五类资产对应的实操标的（宽基为 5 只等权合成，取 510300 为代表计算手数）：

| 资产 | 标的代码 |
|------|---------|
| 黄金 | 518880.SH |
| 国债 | 511010.SH |
| 宽基 | 510300.SH（等权合成的代表，取整时按它算，实际按各成分分别下单） |
| 窄基 | 用户指定（如 159915.SZ），不指定则该品种跳过取整 |
| 现金 | 511880.SH（货币 ETF，面值 1 元） |

不传 `--price` 时自动拉取；`--price` 仅在用户明确指定了其他标的时覆盖。

其他可选参数：
    --price 黄金:6.52,国债:112.30
        手动指定价格覆盖自动取价（仅在用非默认标的时需要）

    --amount-only
        不取价、不做手数取整，只输出金额（离线或取价失败时用）

    --threshold 5
        偏离阈值（百分点）。目标与现状偏差 <该值 的标的不动，避免为凑数反复调仓。

    --sell-first
        只买不卖模式（用新增资金补足目标，存量超配部分不动）——适合工资上涨后
        逐步挪仓、或用户明确表示不想卖出现有持仓的场景。

输出为中文 Markdown 表格，可直接贴进报告。
"""

import argparse
import sys

from pathlib import Path

# 五类资产 → 星耀数智 ETF 代码。宽基为 5 只等权合成（510300/510050/510500/
# 512100/563300），取 510300 作为手数取整的代表；窄基因标的由用户自选，不设默认。
DEFAULT_SYMBOLS = {
    '黄金': '518880.SH',
    '国债': '511010.SH',
    '宽基': '510300.SH',
    '现金': '511880.SH',
}
LOT = 100             # 场内最小交易单位：1 手 = 100 份
MIN_COMMISSION = 5.0  # 最低佣金（元）
COMMISSION_RATE = 0.0003  # 万三


def parse_kv(s):
    """把 '黄金:0.15,国债:0.25' 解析成 dict。"""
    out = {}
    for part in s.split(','):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition(':')
        if not k or not v:
            sys.exit(f"格式错误: '{part}'，应形如 黄金:0.15")
        out[k.strip()] = float(v)
    return out


def fetch_prices(names, user_price=None):
    """从星耀数智（ad-etf-dca 的 DataProvider）取各标的最新收盘价。

    用**不复权**收盘价而非前复权价：前复权是把历史价格按分红/份额折算过的口径，
    用于收益计算是对的，但拿去算"买几手"会与实盘成交价不符。

    Returns
    -------
    (prices, note)
        prices: {资产名: 最新收盘价}，取不到的不在字典里
        note:   展示用的取价口径说明
    """
    prices = {}
    if user_price:
        prices.update(user_price)

    need = [n for n in names if n not in prices]
    if not need:
        return prices, '价格来源：用户通过 --price 指定'

    missing_symbol = [n for n in need if n not in DEFAULT_SYMBOLS]
    auto = [n for n in need if n in DEFAULT_SYMBOLS]
    if not auto:
        return prices, '价格来源：用户通过 --price 指定'

    scripts = Path.home() / '.workbuddy' / 'skills' / 'ad_asset_allocation' / 'scripts'
    if not scripts.exists():
        return prices, '价格来源：未取到（找不到 ad-asset-allocation 目录），仅输出金额'
    sys.path.insert(0, str(scripts))

    from data_provider import DataProvider  # noqa: E402  (需先补 sys.path)

    dp = DataProvider()
    # 用交易日历定位最新交易日（该 DataProvider 的 calendar 在回测中已验证可用）
    cal = dp.calendar()
    end = cal[-1]
    begin = cal[-max(10, min(30, len(cal) - 1))]

    for name in auto:
        code = DEFAULT_SYMBOLS[name]
        try:
            df = dp.etf_kline(code, begin, end)
        except Exception as e:  # 单个标的失败不影响其余
            print(f'⚠️  {name}({code}) 取价失败: {e}')
            continue
        if df is None or len(df) == 0:
            print(f'⚠️  {name}({code}) 无K线数据')
            continue
        # 取 close_raw（不复权）——调仓下单要按实际成交价算手数，
        # 前复权价是历史收益计算口径，与实盘对不上
        col = 'close_raw' if 'close_raw' in df.columns else 'close'
        row = df.iloc[-1]
        prices[name] = float(row[col])
        print(f'  {name}({code}) 最新收盘 {row[col]} 元  截至 {df.index[-1]}')

    got = sorted(set(auto) & set(prices))
    if got:
        note = f'价格来源：星耀数智（AmazingData）{end} 收盘价（不复权）'
    else:
        note = '价格来源：未取到，仅输出金额（可加 --price 手动指定）'
    if missing_symbol:
        note += f'；{"、".join(missing_symbol)} 需用 --price 指定标的'
    return prices, note


def fmt(n):
    """金额加千分位。"""
    return f'{n:,.0f}'


def main():
    ap = argparse.ArgumentParser(description='从目标权重算调仓买卖清单')
    ap.add_argument('--total', type=float, required=True, help='可投资产总市值（元）')
    ap.add_argument('--target', required=True, help='目标权重，如 黄金:0.15,国债:0.25,宽基:0.40,窄基:0.05,现金:0.15')
    ap.add_argument('--current', required=True, help='当前持仓市值，如 黄金:120000,国债:80000')
    ap.add_argument('--price', default='',
                    help='手动指定价格覆盖自动取价（仅非默认标的时需要），如 窄基:1.85')
    ap.add_argument('--cash', default='现金', help='现金仓对应的资产名，默认 现金')
    ap.add_argument('--threshold', type=float, default=5.0,
                    help='偏离阈值（百分点），默认 5。目标与现状偏差小于该值则不动')
    ap.add_argument('--sell-first', action='store_true', help='只买不卖模式')
    ap.add_argument('--amount-only', action='store_true',
                    help='只算金额，不取价也不按手数取整（离线或取价失败时用）')
    args = ap.parse_args()

    target = parse_kv(args.target)
    current = parse_kv(args.current)
    user_price = parse_kv(args.price) if args.price else None

    tsum = sum(target.values())
    if abs(tsum - 1.0) > 0.01:
        sys.exit(f'❌ 目标权重合计 {tsum:.2%} != 100%，请检查（允许 ±1% 舍入误差）')

    # 取价：默认从星耀数智拉最新收盘价；--amount-only 时完全跳过
    price, price_note = ({}, '价格来源：未取价（--amount-only），仅输出金额')
    if not args.amount_only:
        print('\n正在从星耀数智获取最新收盘价...')
        price, price_note = fetch_prices(list(target.keys()), user_price)
        if not price:
            print('⚠️  未能取到任何价格，无法按手数取整。可改用 --amount-only 仅看金额。')

    total = args.total
    cur_sum = sum(current.values())
    if cur_sum > 0 and abs(cur_sum - total) > total * 0.02:
        print(f'⚠️  当前持仓合计 {fmt(cur_sum)} 元 与 --total {fmt(total)} 元 偏差 '
              f'{(cur_sum - total) / total:+.1%}，以持仓合计为准重算')
        total = cur_sum

    # 每行：名称、目标市值、现市值、差额
    rows = []
    for name, tw in target.items():
        cur = current.get(name, 0.0)
        tgt_val = total * tw
        diff = tgt_val - cur
        cur_w = cur / total if total else 0.0
        drift = (tw - cur_w) * 100  # 百分点
        action = '买入' if diff > 0 else ('卖出' if diff < 0 else '不动')
        if args.sell_first and diff < 0:
            # 只买不卖模式：超配部分保留原状，不产生卖出动作
            action = '保留超配'
        if abs(drift) < args.threshold:
            action = '不动'
        rows.append({
            'name': name, 'target_w': tw, 'cur_w': cur_w, 'drift': drift,
            'tgt_val': tgt_val, 'cur_val': cur, 'diff': diff, 'action': action,
        })

    # 换手最小化：卖出按偏离从大到小排序
    sells = sorted([r for r in rows if r['diff'] < 0 and r['action'] == '卖出'],
                   key=lambda r: r['drift'])
    buys = [r for r in rows if r['diff'] > 0 and r['action'] == '买入']

    print()
    print('=' * 72)
    print(f'调仓清单｜可投资产 {fmt(total)} 元｜偏离阈值 {args.threshold:.0f} 个百分点'
          f'｜模式 {"只买不卖" if args.sell_first else "买卖双向"}')
    print('=' * 72)
    print()
    print('| 资产 | 目标权重 | 当前权重 | 偏离(pct) | 目标市值(元) | 当前市值(元) | 差额(元) | 操作 |')
    print('|------|---------|---------|----------|-------------|-------------|---------|------|')
    for r in sorted(rows, key=lambda x: -abs(x['drift'])):
        print(f"| {r['name']} | {r['target_w']:.0%} | {r['cur_w']:.0%} | {r['drift']:+.1f} | "
              f"{fmt(r['tgt_val'])} | {fmt(r['cur_val'])} | {r['diff']:+,.0f} | {r['action']} |")

    # 实际执行金额（取整到 100 份 + 佣金）
    if not args.amount_only:
        # 现金仓是资金来源，同时又要被调整到目标比例，因此不参与买卖平衡：
        # 若把「减现金」也算作卖出，又用其资金去买入，必然出现假缺口。
        cash_name = args.cash
        buys = [r for r in buys if r['name'] != cash_name]

        print()
        print('--- 可执行清单（按 100 份/手取整，已估最低佣金 5 元/笔）---')
        print(f'注：现金仓「{cash_name}」不参与买卖平衡——它既是资金来源，又是被调整的目标，'
              f'计入会产生假缺口。')
        print(f'{price_note}')
        print()
        print('| 资产 | 操作 | 手数 | 成交金额(元) | 佣金(元) | 实际投入/回收(元) |')
        print('|------|------|------|-----------|--------|------------------|')
        cash_needed = 0.0
        cash_gained = 0.0
        for r in sells + buys:
            p = price.get(r['name'])
            if not p or p <= 0:
                hint = '需用 --price 指定' if r['name'] not in DEFAULT_SYMBOLS else '未取到价'
                print(f"| {r['name']} | {r['action']} | — | {abs(r['diff']):,.0f} | {hint} | 跳过取整 |")
                continue
            lots = int(abs(r['diff']) / p / LOT)
            if lots <= 0:
                print(f"| {r['name']} | {r['action']} | 0 | 0 | 0 | 金额不足 1 手，不动 |")
                continue
            amount = lots * LOT * p
            comm = max(amount * COMMISSION_RATE, MIN_COMMISSION)
            net = amount + comm if r['action'] == '买入' else amount - comm
            if r['action'] == '买入':
                cash_needed += net
            else:
                cash_gained += net
            print(f"| {r['name']} | {r['action']} | {lots} | {fmt(amount)} | {comm:.0f} | {fmt(net)} |")

        print()
        print(f'卖出回收合计：{fmt(cash_gained)} 元')
        print(f'买入需要合计：{fmt(cash_needed)} 元')
        gap = cash_needed - cash_gained
        cash_row = next((r for r in rows if r['name'] == cash_name), None)
        cash_now = cash_row['cur_val'] if cash_row else 0.0
        if gap > 0:
            # 现金仓需减到目标比例，可动用的只有超出目标的那部分
            cash_excess = max(cash_now - (total * target.get(cash_name, 0.0)), 0.0)
            print(f'⚠️  资金缺口 {fmt(gap)} 元')
            print(f'   现金仓现有 {fmt(cash_now)} 元，目标 {fmt(total * target.get(cash_name, 0.0))} 元，'
                  f'可超额动用 {fmt(cash_excess)} 元')
            if gap <= cash_excess:
                print(f'✅ 从现金仓划出 {fmt(gap)} 元即可，划出后现金仓仍有 '
                      f'{fmt(cash_now - gap)} 元，符合目标比例')
            else:
                rest = gap - cash_excess
                print(f'❌ 现金超额部分不够，仍缺 {fmt(rest)} 元')
                print()
                print('   ⇩ 建议改为「分期调仓」（二选一）：')
                # 方案 A：按比例下调买入金额
                print(f'   方案 A｜按比例下调买入：把上面买入金额各乘 '
                      f'{(cash_needed and (cash_gained + cash_excess) / cash_needed):.0%}'
                      f'，各标的买入量等比缩减，本轮先调到接近目标')
                # 方案 B：只买偏离最大的
                top = max(buys, key=lambda r: abs(r['drift'])) if buys else None
                if top:
                    print(f'   方案 B｜本轮只动偏离最大的「{top['name']}」（偏离 {top["drift"]:+.1f} pct），'
                          f'其余等下期或等资金到位再调')
                print('   理由：偏离 <阈值的品种不动是刻意的——频繁小额调仓会被佣金和'
                      '买卖价差反复侵蚀，收益远小于纠偏价值。')
        elif gap < 0:
            print(f'✅ 卖出回收多于买入需求，剩余 {fmt(-gap)} 元留在现金仓（现金仓将高于目标，'
                  f'属正常的调仓中间态）')
        else:
            print('✅ 买卖金额平衡，无需额外划转')

    # 换手成本提示
    if args.sell_first:
        buy_total = sum(r['diff'] for r in rows if r['action'] == '买入')
        if buy_total > total * 0.5:
            print()
            print(f'⚠️  只买不卖模式下买入合计 {fmt(buy_total)} 元，占总资产 '
                  f'{buy_total / total:.0%}——这会耗尽现金储备并让组合严重超配，'
                  f'**不建议一次性执行**')
            print(f'   建议：把买入量分摊到 {max(1, round(buy_total / max(total * 0.3, 1)))} '
                  f'期执行，或改用双向模式卖出超配部分')
        elif buy_total > 0:
            print()
            print(f'只买不卖模式：买入合计 {fmt(buy_total)} 元（占总资产 {buy_total / total:.0%}），'
                  f'超配部分保留原状，请注意组合将持续偏离目标')

    if sells:
        sell_total = sum(abs(r['diff']) for r in sells)
        print()
        print(f'换手率（卖出额/总市值）：{sell_total / total:.1%}'
              + ('　—— 偏高，频繁调仓会被佣金和波动双重侵蚀，建议只在触发阈值时执行'
                 if sell_total / total > 0.3 else '　—— 属正常范围'))

    print()
    print(f'提示：偏离 <{args.threshold:.0f} 个百分点的品种本轮不动（避免为凑数反复调仓）。')
    if not args.sell_first:
        print('卖出顺序：按偏离幅度从大到小，先卖超配最多的品种，可减少交易次数。')
    print('分红处理：国债、宽基、窄基有分红，收到分红后按目标权重重新再平衡（同样用本脚本重算）。')
    if not args.amount_only:
        print('价格时效：手数按取价当日收盘价估算，盘中价格已变时请以最新市价重新核对手数。')
    print()
    print('本清单为依据目标权重的算术结果，不构成投资建议；实际下单以最新市价为准，'
          '前复权价 ≠ 交易价。')


if __name__ == '__main__':
    main()
