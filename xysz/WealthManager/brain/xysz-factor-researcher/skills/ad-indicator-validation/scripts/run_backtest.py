# -*- coding: utf-8 -*-
"""
CLI 入口:指标验证

联动工作流(本 skill 不自算指标):
    ① 用户调用技术面/基本面指标 skill(如 ad_technical_analysis、
       ad_fundamental_analysis)获得指标值,整理为「指标值面板 CSV」
       (第一列 date,其余列为股票代码)
    ② 本 skill 加载指标面板 → 信号规则 → 多指标合成 → 组合撮合 → 净值

模式:
    signal   单股信号检查:指标信号 + ECharts 可视化(K线主图 + 信号副图)
    backtest 组合回测:多指标信号 → 合成 → 撮合 → 净值 CSV + 终端摘要

净值输出为 CSV(date + net_value 含成本 + net_value_gross 不含成本),
可直接用「策略业绩分析」skill 做完整绩效评估与 HTML 报告。
"""

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# AmazingData 相关模块延迟加载(在 mode 函数内部 import):
# 避免仅查看帮助/校验参数时触发 SDK 初始化


def _fmt(v):
    if isinstance(v, float):
        return f'{v:.4f}'
    return str(v)


def _parse_factors(args):
    """解析 --factors 规格列表 → [(name, path, rule), ...]"""
    from signal_engine import parse_factor_spec
    specs = [parse_factor_spec(s) for s in args.indicators]
    names = [n for n, _, _ in specs]
    dup = {n for n in names if names.count(n) > 1}
    if dup:
        raise ValueError(f'指标名重复: {dup}')
    return specs


# ----------------------------------------------------------------------
# 模式一:单股信号检查
# ----------------------------------------------------------------------

def mode_signal(args):
    from data_provider import DataProvider
    from signal_engine import load_factors
    from backtest_engine import fill_state, composite_signal
    from signal_report import render_signal_report

    specs = _parse_factors(args)
    names = [n for n, _, _ in specs]

    dp = DataProvider()
    panels = dp.get_kline_panels([args.code], args.begin, args.end)
    panels_ff = {k: v.ffill() for k, v in panels.items()
                 if k in ('open', 'high', 'low', 'close', 'volume', 'amount')}

    # ---- 加载外部指标并生成信号 ----
    close = panels_ff['close']
    values, raw_sigs = load_factors(specs, trade_index=close.index)

    state_map, rows = {}, []
    for name in names:
        state = fill_state(raw_sigs[name])
        state_map[name] = state
        rows.append({
            '指标': name,
            '规则': dict(specs)[name],
            '持仓状态': '持有' if state.iloc[-1].get(args.code, 1) == -1 else '空仓',
        })

    # ---- 综合信号(多指标投票,单指标即其本身) ----
    combined_raw = (composite_signal(raw_sigs, method=args.combine_method,
                                     min_buy_ratio=args.min_buy_ratio,
                                     min_sell_ratio=args.min_sell_ratio)
                    if len(names) > 1 else raw_sigs[names[0]])
    combined_state = fill_state(combined_raw)

    # ---- 并集信号(全部持有才持有,任一空仓即卖出) ----
    union_state = None
    if len(names) > 1:
        union_state = fill_state(composite_signal(raw_sigs, method='union'))

    # ---- JSON 摘要(终端) ----
    print(json.dumps({
        'code': args.code,
        '区间': f'{args.begin} ~ {args.end}',
        '综合持仓状态': '持有' if combined_state.iloc[-1].get(args.code, 1) == -1 else '空仓',
        '指标信号': rows,
    }, ensure_ascii=False, indent=2))

    # ---- ECharts 可视化报告 ----
    close_c = close[args.code]
    open_ = panels_ff['open'][args.code]
    high = panels_ff['high'][args.code]
    low = panels_ff['low'][args.code]

    valid_idx = close_c.dropna().index
    dates = [d.strftime('%Y-%m-%d') for d in valid_idx]
    kline = [[round(float(open_[d]), 2), round(float(close_c[d]), 2),
              round(float(low[d]), 2), round(float(high[d]), 2)] for d in valid_idx]

    ma = {}
    for n in (5, 10, 20, 60):
        ma[f'MA{n}'] = [None if pd.isna(v) else round(float(v), 2)
                        for v in close_c.rolling(n).mean().reindex(valid_idx)]

    state_col = combined_state[args.code].reindex(valid_idx).fillna(1.0)
    prev = state_col.shift(1).fillna(1.0)
    buy_idx = state_col[(state_col == -1) & (prev != -1)].index
    sell_idx = state_col[(state_col == 1) & (prev != 1)].index
    pos_of = {d: i for i, d in enumerate(valid_idx)}
    actions = {
        'buy': [[pos_of[d], round(float(low[d]) * 0.985, 2)] for d in buy_idx],
        'sell': [[pos_of[d], round(float(high[d]) * 1.015, 2)] for d in sell_idx],
    }

    def _state01(series):
        return [0 if v == 1 else 1 for v in
                series[args.code].reindex(valid_idx).fillna(1.0)]

    signals_out = [{'name': n, 'state': _state01(state_map[n])} for n in names]
    combined_out = [0 if v == 1 else 1 for v in state_col]
    union_out = (None if union_state is None else _state01(union_state))

    stock_name = args.code
    try:
        basic = dp.info_data.get_stock_basic([args.code])
        if basic is not None and len(basic):
            stock_name = str(basic.iloc[0].get('SECURITY_NAME', args.code))
    except Exception:
        pass

    out_dir = args.output or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        'output')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(
        out_dir, f"signal_{args.code.replace('.', '_')}_"
                 f"{'-'.join(names)[:30]}_{args.begin}.html")
    render_signal_report(args.code, stock_name, str(args.begin), str(args.end),
                         'external', names,
                         dates, kline, ma, actions, signals_out,
                         combined_out, os.path.abspath(out_path),
                         union_state=union_out)

    print(json.dumps({
        '信号报告HTML': os.path.abspath(out_path),
        '买卖动作次数': {'买入': len(actions['buy']), '卖出': len(actions['sell'])},
        '说明': '浏览器打开查看 K线主图 + 各指标信号副图',
    }, ensure_ascii=False, indent=2))


# ----------------------------------------------------------------------
# 模式二:组合回测
# ----------------------------------------------------------------------

def mode_backtest(args):
    from data_provider import DataProvider, ad
    from signal_engine import load_factors, parse_dirs
    from factor_combine import combine, score_to_signal, rebalance_dates
    from backtest_engine import (run_backtest, summary_stats,
                                 fill_state, composite_signal)

    print('== 登录并构建数据面板 ==', file=sys.stderr)
    dp = DataProvider()
    data = dp.build(args.begin, args.end, exclude_st=not args.keep_st,
                    max_stocks=args.max_stocks)
    panels, flags = data['panels'], data['flags']
    universe = data['universe']
    print(f'   股票池: {len(universe)} 只', file=sys.stderr)

    close = panels['close']
    ret = close / close.shift(1) - 1
    ret = ret.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    specs = _parse_factors(args)
    names = [n for n, _, _ in specs]

    print('== 加载外部指标面板与信号 ==', file=sys.stderr)
    values, raw_sigs = load_factors(specs, trade_index=close.index)

    # ---- 信号合成 → 状态补全 ----
    print('== 多指标合成 ==', file=sys.stderr)
    combined = composite_signal(raw_sigs, method=args.combine_method,
                                min_buy_ratio=args.min_buy_ratio,
                                min_sell_ratio=args.min_sell_ratio)
    state = fill_state(combined)
    # 只保留股票池内且可交易的股票列
    state = state.reindex(index=close.index, columns=close.columns).fillna(1.0)

    # ---- 排名选股模式:以调仓日截面排名覆盖信号 ----
    members = None
    rb_dates = None
    score = None
    if args.selection == 'rank':
        dirs = parse_dirs(args.dirs)
        score = combine(values, names, dirs, method=args.score_method)
        score = score.reindex(index=close.index, columns=close.columns)
        rb_dates = rebalance_dates(close.index, args.rebalance)
        rank_sig, members = score_to_signal(score, rb_dates, top_n=args.top_n)
        state = fill_state(rank_sig)
        state = state.reindex(index=close.index, columns=close.columns).fillna(1.0)

    # ---- 撮合回测 ----
    print('== 撮合回测 ==', file=sys.stderr)
    nav, holdings, detail = run_backtest(
        state, flags, ret,
        position_mode=args.position_mode, top_n=args.top_n,
        weight_scheme=args.weight_scheme, panels=panels,
        total_capital=args.capital, total_shares=args.total_shares,
        cost_free=args.cost_free,
    )

    # ---- 基准 ----
    benchmark = None
    try:
        bm = dp.market_data.query_kline(
            code_list=[args.benchmark], begin_date=int(args.begin),
            end_date=int(args.end),
            period=ad.constant.Period.day.value)
        if bm and args.benchmark in bm:
            b = bm[args.benchmark]
            if 'kline_time' in b.columns:
                b = b.set_index('kline_time')
            b.index = pd.DatetimeIndex(b.index)
            bclose = b['close'].sort_index()
            benchmark = bclose / bclose.iloc[0]
    except Exception as e:
        print(f'   基准拉取失败({e}),摘要跳过基准对比', file=sys.stderr)

    # ---- 摘要 ----
    stats = summary_stats(nav['net_value'], nav.get('net_value_gross'), benchmark)
    if detail is not None:
        stats['年化换手(单边,倍)'] = round(float(detail['turnover'].sum() / 2), 2) if len(detail) else 0
        stats['累计成本(占期初资金,%)'] = round(float(detail['cost'].sum()) * 100, 3)

    print(json.dumps({'回测摘要': stats}, ensure_ascii=False, indent=2))

    # ---- 输出 CSV ----
    out_dir = args.output or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        'output')
    os.makedirs(out_dir, exist_ok=True)
    tag = f"{args.begin}_{args.end}_{'-'.join(names)[:40]}"
    nav_path = os.path.join(out_dir, f'backtest_nav_{tag}.csv')
    nav_out = nav.copy()
    nav_out.insert(0, 'date', [d.strftime('%Y-%m-%d') for d in nav_out.index])
    nav_out.to_csv(nav_path, index=False, encoding='utf-8-sig')

    hold_path = os.path.join(out_dir, f'backtest_holdings_{tag}.csv')
    holdings.replace(0, np.nan).dropna(how='all', axis=1).to_csv(
        hold_path, encoding='utf-8-sig')

    print(json.dumps({
        '净值CSV': os.path.abspath(nav_path),
        '持仓CSV': os.path.abspath(hold_path),
        '说明': '净值 CSV 可直接用策略业绩分析 skill 生成完整绩效报告与 HTML',
    }, ensure_ascii=False, indent=2))

    if members is not None and rb_dates is not None and len(rb_dates):
        last_d = rb_dates[-1]
        if last_d in score.index:
            top = score.loc[last_d].dropna().nsmallest(args.top_n)
            print(json.dumps({
                '最近调仓日': str(last_d.date()),
                '最新目标持仓': list(top.index),
            }, ensure_ascii=False, indent=2))


# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='中国银河证券星耀数智指标验证(指标值由外部指标 skill 联动提供)')
    parser.add_argument('--mode', default='backtest', choices=['signal', 'backtest'],
                        help='运行模式: signal=单股信号检查 / backtest=组合回测')
    parser.add_argument('--code', default=None, help='单股模式下的股票代码')
    parser.add_argument('--begin', type=int, default=20230101, help='开始日期(如 20230101)')
    parser.add_argument('--end', type=int, default=None, help='结束日期,默认今天')
    parser.add_argument('--indicators', '--factors', dest='indicators', nargs='+', required=True,
                        help='指标规格列表 NAME:路径[:规则],规则 pos / cross / band:低,高;'
                             'CSV 为指标值面板(首列 date,其余列=股票代码)')
    parser.add_argument('--dirs', default=None,
                        help='排名合成方向: NAME=1 或 NAME=-1(逗号分隔),缺省 0 不参与排名')
    parser.add_argument('--combine-method', default='vote',
                        choices=['vote', 'mean', 'union'],
                        help='信号合成方式: vote=投票(过半) / mean=均值 / union=并集(全部持有才持有,任一空仓即卖出)')
    parser.add_argument('--min-buy-ratio', type=float, default=0.5,
                        help='投票买入比例阈值')
    parser.add_argument('--min-sell-ratio', type=float, default=0.5,
                        help='投票卖出比例阈值')
    parser.add_argument('--selection', default='signal', choices=['signal', 'rank'],
                        help='选股方式: signal=信号驱动 / rank=调仓日截面排名')
    parser.add_argument('--score-method', default='zscore',
                        choices=['zscore', 'pctrank', 'rank'], help='排名合成的标准化方式')
    parser.add_argument('--rebalance', default='monthly',
                        choices=['daily', 'weekly', 'monthly', 'quarterly'],
                        help='调仓频率(rank 模式)')
    parser.add_argument('--position-mode', default='topn', choices=['topn', 'shares'],
                        help='持仓口径: topn=目标持仓数 / shares=份数模式')
    parser.add_argument('--top-n', type=int, default=20, help='目标持仓数(topn 口径)')
    parser.add_argument('--total-shares', type=int, default=2000, help='总份数(shares 口径)')
    parser.add_argument('--weight-scheme', default='equal',
                        choices=['equal', 'invvol', 'mktcap'], help='权重方案(topn 口径)')
    parser.add_argument('--capital', type=float, default=1_000_000.0, help='期初资金(元)')
    parser.add_argument('--benchmark', default='000300.SH', help='基准指数代码')
    parser.add_argument('--cost-free', action='store_true', help='关闭交易成本(对照)')
    parser.add_argument('--keep-st', action='store_true', help='保留 ST 股(默认剔除)')
    parser.add_argument('--max-stocks', type=int, default=None, help='股票池上限(快速试跑)')
    parser.add_argument('--output', default=None, help='输出目录,默认 生态根 output/')
    args = parser.parse_args()

    if args.end is None:
        args.end = int(pd.Timestamp.now().strftime('%Y%m%d'))

    if args.mode == 'signal':
        if not args.code:
            raise SystemExit('单股信号检查需要 --code 参数')
        mode_signal(args)
    else:
        mode_backtest(args)


if __name__ == '__main__':
    main()
