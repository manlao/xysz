"""参数扫描 — 为 BL 标定观点信心水平 conf 与风险厌恶 λ。

背景：公开实证中，模型参数通常用网格遍历标定，且**权重的跨期稳定性**与绩效同等重要
——单点最优常常不可复现。标准置信度比例法下 Ω = τ(1−conf)/conf·PΣPᵀ 与 (τΣ)⁻¹ 同阶缩放，
后验期望对 τ 近似不敏感，真正决定后验的杠杆是 **conf**，故默认扫描 conf×λ；
`--scan tau` 用于 `--omega legacy` 口径（Ω 不含 τ，此时 τ 才有区分度）。

做法：资产收益矩阵只拉取一次，遍历网格对指定模型重跑回测，输出每个组合的绩效与
"相邻调仓期权重平均变动幅度"（换手/不稳定度代理），结果 CSV 带时间戳落盘。

用法：
    python param_scan.py --models bl --period 3y --views ../references/bl_views_example.json
    python param_scan.py --models bl --period 3y --confs 0.3,0.5,0.7,0.9 --lams 1,2,5
    python param_scan.py --models bl --period 3y --scan tau --omega legacy \
                         --taus 0.01,0.05,0.1,0.5 --views ../references/bl_views_example.json
    python param_scan.py --models bl,mv --period 3y --views ../references/bl_views_example.json
    python param_scan.py --models bl --period 3y --excess-cov --out ../output/asset_allocation
"""

import argparse
import itertools
import os
import sys
import time
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_provider import DataProvider
from backtest import build_asset_returns, run_backtest
from models import MODEL_LABELS, ASSET_NAMES

DEFAULT_TAUS = [0.01, 0.05, 0.1, 0.5]
DEFAULT_LAMS = [1.0, 2.0, 3.0, 5.0]


def weight_turnover(weights_long: pd.DataFrame) -> float:
    """相邻调仓期权重的平均 L1 变动（百分点/2，即单边换手代理）。"""
    if weights_long is None or len(weights_long) < 2:
        return float('nan')
    w = weights_long[[c for c in ASSET_NAMES if c in weights_long.columns]].values / 100.0
    return float(abs((w[1:] - w[:-1]).sum(axis=1)).mean() / 2.0 * 100.0)


def apply_conf(views, conf_value):
    """把一组观点的信心水平统一替换为 conf_value（标定时用）。"""
    out = []
    for v in views or []:
        nv = dict(v)
        nv['conf'] = conf_value
        out.append(nv)
    return out


def main():
    p = argparse.ArgumentParser(description='参数扫描（BL 标定 conf/λ，均值方差标定 λ）')
    p.add_argument('--models', default='bl', help='参与扫描的模型，逗号分隔（建议 bl 或 bl,mv）')
    p.add_argument('--period', default='3y', help='回测区间（与 search.py 口径一致）')
    p.add_argument('--begin', type=int, default=0)
    p.add_argument('--end', type=int, default=0)
    p.add_argument('--rebalance', default='m', choices=['y', 'm', 'w'])
    p.add_argument('--lookback', type=int, default=244)
    p.add_argument('--scan', default='conf', choices=['conf', 'tau'],
                   help="扫描维度：conf=扫描观点信心水平（默认，标准口径下真正决定后验的杠杆）；"
                        "tau=扫描 τ（仅在 --omega legacy 下有意义，标准口径下 τ 与 Ω 同步缩放、后验近似不变）")
    p.add_argument('--confs', default='0.3,0.5,0.7,0.9',
                   help='信心水平网格（--scan conf），扫描时会统一替换各观点的 conf')
    p.add_argument('--taus', default='0.01,0.05,0.1,0.5', help='τ 网格（--scan tau）')
    p.add_argument('--tau', type=float, default=0.05,
                   help='--scan conf 时使用的固定 τ（标准口径下 τ 只影响后验协方差膨胀项）')
    p.add_argument('--lams', default=','.join(str(x) for x in DEFAULT_LAMS), help='λ 网格，逗号分隔')
    p.add_argument('--views', default='', help='BL 观点 JSON（不给则 BL 退化为均衡，扫描意义有限）')
    p.add_argument('--bounds', default='0,0.6,0,0.6,0,0.6,0,0.6')
    p.add_argument('--cash-mode', dest='cash_mode', default='fixed', choices=['fixed', 'market'])
    p.add_argument('--cash-yield', dest='cash_yield', type=float, default=0.018)
    p.add_argument('--shrink', type=float, default=0.0)
    p.add_argument('--excess-cov', dest='excess_cov', action='store_true',
                   help='Σ 用相对基准的超额收益协方差（推荐与 BL 观点扫描同用）')
    p.add_argument('--omega', default='ratio', choices=['ratio', 'idzorek', 'legacy'],
                   help='BL 观点误差矩阵构造（ratio/idzorek 等价；legacy 为历史口径）')
    p.add_argument('--benchmark', default='000300.SH', help='超额协方差基准')
    p.add_argument('--out', default='', help='CSV 输出目录（默认 output/asset_allocation）')
    p.add_argument('--local-path', dest='local_path', default='D:/AmazingData_local_data/')
    args = p.parse_args()

    models = [m.strip() for m in args.models.split(',') if m.strip()]
    for m in models:
        if m not in MODEL_LABELS:
            raise SystemExit('未知模型 %r（可选 fixed/mv/rp/bl）' % m)
    lams = [float(x) for x in args.lams.split(',') if x.strip()]
    if args.scan == 'conf':
        firsts = [float(x) for x in args.confs.split(',') if x.strip()]
    else:
        firsts = [float(x) for x in args.taus.split(',') if x.strip()]
    if not firsts or not lams:
        raise SystemExit('扫描网格为空')

    t0 = time.time()
    from search import resolve_period_dp, load_views
    dp = DataProvider(args.local_path)
    begin, end = resolve_period_dp(dp, args.period, args.begin, args.end)
    views = load_views(args.views)
    if 'bl' in models and not views:
        print('[提示] 未提供 --views，BL 将退化为均衡组合，此时 conf 扫描无意义', flush=True)

    R = build_asset_returns(dp, begin, end, args.cash_mode, args.cash_yield, args.lookback)
    grid = list(itertools.product(firsts, lams))
    scan_name = 'conf' if args.scan == 'conf' else 'tau'
    print('\n═══ %s×λ 参数扫描（%d 组合 × %d 模型，区间 %d~%d）═══'
          % (scan_name, len(grid), len(models), begin, end), flush=True)

    rows = []
    for first, lam in grid:
        tau = first if args.scan == 'tau' else args.tau
        views_run = apply_conf(views, first) if args.scan == 'conf' else views
        res = run_backtest(begin, end, models, rebalance=args.rebalance,
                           lookback=args.lookback, lam=lam,
                           cash_mode=args.cash_mode, cash_yield=args.cash_yield,
                           bounds_str=('' if args.bounds == 'none' else args.bounds),
                           views=views_run, tau=tau, shrink=args.shrink,
                           dp=dp, R=R, excess_cov=args.excess_cov,
                           omega_mode=args.omega)
        wl = res['weights_long']
        for m in models:
            label = MODEL_LABELS[m]
            v = res['perf'][label]
            row = {'模型': label, scan_name: first, 'tau': tau, 'lambda': lam,
                   '累计收益率%': v['累计收益率%'], '年化收益率%': v['年化收益率%'],
                   '年化波动率%': v['年化波动率%'], '最大回撤%': v['最大回撤%'],
                   '夏普': v['夏普'], '卡玛': v['卡玛'],
                   '权重平均变动%': round(weight_turnover(wl[wl['模型'] == label]), 2)}
            row.update({a: round(res['latest_w'].loc[label, a] * 100, 1) for a in ASSET_NAMES})
            rows.append(row)
        print('  %s=%-6g λ=%-4g 完成（%.0fs）' % (scan_name, first, lam, time.time() - t0),
              flush=True)

    df = pd.DataFrame(rows)
    cols = ['模型', scan_name, 'tau', 'lambda', '年化收益率%', '年化波动率%', '最大回撤%',
            '夏普', '卡玛', '权重平均变动%'] + ASSET_NAMES
    print('\n%-10s %7s %6s %6s %8s %8s %8s %7s %7s %10s' %
          ('模型', scan_name, 'tau', 'lambda', '年化%', '波动%', '回撤%', '夏普', '卡玛', '权重变动%'),
          flush=True)
    for _, r in df.sort_values(['模型', '夏普'], ascending=[True, False]).iterrows():
        print('%-10s %7g %6g %6g %8.2f %8.2f %8.2f %7s %7s %10.2f' % (
            r['模型'], r[scan_name], r['tau'], r['lambda'], r['年化收益率%'], r['年化波动率%'],
            r['最大回撤%'], r['夏普'], r['卡玛'], r['权重平均变动%']), flush=True)
    print('\n最新权重（%）：')
    for m in models:
        sub = df[df['模型'] == MODEL_LABELS[m]]
        if len(sub):
            r = sub.sort_values('夏普', ascending=False).iloc[0]
            print('  %s（最优组合 %s=%g, λ=%g）: %s' % (
                MODEL_LABELS[m], scan_name, r[scan_name], r['lambda'],
                '  '.join('%s %.1f' % (a, r[a]) for a in ASSET_NAMES)), flush=True)
    print('\n选参提示：先看"权重平均变动%"小（稳定、可解释），再看夏普；'
          '单点最优不可复现时取邻近 plateau 的中心值。', flush=True)

    out_dir = args.out or os.path.join('output', 'asset_allocation')
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    path = os.path.join(out_dir, 'asset_allocation_param_scan_%s_%s_%s_%s.csv' % (
        '-'.join(models), args.scan, args.period, ts))
    df[cols].to_csv(path, index=False, encoding='utf-8-sig')
    print('\n扫描结果已保存: %s' % os.path.abspath(path), flush=True)
    print('完成 (%.0fs)' % (time.time() - t0), flush=True)


if __name__ == '__main__':
    main()
