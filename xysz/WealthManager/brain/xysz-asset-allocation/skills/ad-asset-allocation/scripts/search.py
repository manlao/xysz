# -*- coding: utf-8 -*-
"""大类资产配置 skill 命令行入口。

模式：
    backtest  历史回测（默认近 3 年、月度调仓、四模型对比）→ 控制台 + HTML 报告 + CSV
    alloc     当前配置（用最近 lookback 窗口估计，输出各模型权重对比表）
    explain   策略知识：模型原理讲解

参数输入：
    纯命令行参数驱动；AI 对话使用时，AI 应先向用户确认参数（见 SKILL.md「运行前参数确认」）。

示例：
    python search.py --mode backtest                          # 近 3 年四模型全默认
    python search.py --mode backtest --period 5y --rebalance w
    python search.py --mode backtest --views bl_views.json    # 带观点的 BL
    python search.py --mode backtest --views ../references/bl_views_example.json
    python search.py --mode backtest --cash-mode market --shrink 0.2 --tau 0.1
    python search.py --mode alloc
    python search.py --mode explain --topic 风险平价
"""

import argparse
import json
import os
import time
from datetime import datetime

import pandas as pd

from models import ASSET_NAMES, MODEL_LABELS, solve, annualized_stats, parse_bounds
from backtest import run_backtest, build_asset_returns

DEFAULT_BOUNDS = '0,0.6,0,0.6,0,0.6,0,0.6'   # 单资产上限 60%，'none' 关闭


def _ts() -> str:
    """时间戳（输出文件名用，避免同参数重复运行互相覆盖）。"""
    return datetime.now().strftime('%Y%m%d_%H%M%S')


def _check_models(models: list) -> list:
    """模型名校验（显式异常，不用 assert：python -O 会禁用 assert）。"""
    for m in models:
        if m not in MODEL_LABELS:
            raise SystemExit('未知模型 %r（可选 fixed/mv/rp/bl）' % m)
    return models


# ----------------------------------------------------------------------
# 区间解析
# ----------------------------------------------------------------------
def resolve_period_dp(dp, period: str, begin: int, end: int):
    """'3y'(默认)/'5y'/'1y'/'6m'/'ytd'/'2024' → (begin, end)；begin/end 显式给出时优先。"""
    if begin and end:
        return begin, end
    cal = dp.calendar()
    end_eff = cal[-1]
    if period.isdigit() and len(period) == 4:      # 自然年度
        return int(period + '0101'), min(int(period + '1231'), end_eff)
    p = period.lower()
    if p == 'ytd':
        return int(str(end_eff)[:4] + '0101'), end_eff
    if len(p) < 2 or not p[:-1].isdigit() or p[-1] not in ('y', 'm', 'w'):
        raise SystemExit('无法解析 --period %r，请用 3y/5y/1y/6m/ytd/2024 等形式' % period)
    mult, unit = (int(p[:-1]), p[-1])
    days = {'y': 244, 'm': 20, 'w': 5}[unit]
    begin_eff = cal[max(0, len(cal) - 1 - mult * days)]
    return begin_eff, end_eff


def load_views(path: str):
    """读 BL 观点文件（不存在给中文报错）。"""
    if not path:
        return None
    p = os.path.expanduser(path)
    if not os.path.isfile(p):
        raise FileNotFoundError('BL 观点文件不存在: %s（可参考 references/bl_views_example.json）' % path)
    with open(p, encoding='utf-8') as f:
        views = json.load(f).get('views', [])
    print('[BL] 观点 %d 条来自 %s' % (len(views), path), flush=True)
    return views


KNOWLEDGE_MD = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'references', 'knowledge.md')


def load_knowledge(path: str = None) -> dict:
    """解析 references/knowledge.md，返回 {二级标题: 正文}。

    知识库正文是文档（便于 AI 直接阅读与维护），这里按 '## ' 标题切分供 explain 模式检索。
    """
    p = os.path.normpath(path or KNOWLEDGE_MD)
    if not os.path.isfile(p):
        raise FileNotFoundError('知识库文件不存在: %s' % p)
    with open(p, encoding='utf-8') as f:
        lines = f.read().splitlines()
    topics, cur, buf = {}, None, []
    for ln in lines:
        if ln.startswith('## '):
            if cur:
                topics[cur] = '\n'.join(buf).strip()
            cur, buf = ln[3:].strip(), []
        elif cur is not None:
            buf.append(ln)
    if cur:
        topics[cur] = '\n'.join(buf).strip()
    return topics


# ----------------------------------------------------------------------
# backtest 模式
# ----------------------------------------------------------------------
def run_backtest_mode(args):
    from data_provider import DataProvider
    from report import build_report
    t0 = time.time()
    dp0 = DataProvider(args.local_path)
    begin, end = resolve_period_dp(dp0, args.period, args.begin, args.end)
    views = load_views(args.views)

    models = _check_models([m.strip() for m in args.models.split(',') if m.strip()])
    fixed_w = [float(x) for x in args.fixed_weights.split(',')] if args.fixed_weights else None

    res = run_backtest(begin, end, models, rebalance=args.rebalance,
                       lookback=args.lookback, lam=args.lam, rf=args.rf,
                       cash_mode=args.cash_mode, cash_yield=args.cash_yield,
                       bounds_str=('' if args.bounds == 'none' else args.bounds),
                       fixed_weights=fixed_w, views=views,
                       tau=args.tau, shrink=args.shrink,
                       dp=dp0, local_path=args.local_path,
                       excess_cov=args.excess_cov, omega_mode=args.omega,
                       lookback_mv=(args.lookback_mv or None),
                       lookback_bl=(args.lookback_bl or None))

    m, meta = res['perf'], res['meta']
    print('\n═══ 大类资产配置回测（%d~%d，%s度调仓 %d 次，窗口 %d 日，λ=%g%s%s）═══' % (
        meta['begin'], meta['end'],
        {'y': '年', 'm': '月', 'w': '周'}[meta['rebalance']],
        meta['n_rebalance'], meta['lookback'], meta['lam'],
        '，τ=%g' % meta['tau'] if 'bl' in meta['models'] else '',
        '，收缩=%g' % meta['shrink'] if meta['shrink'] else ''), flush=True)
    print('%-10s %9s %9s %9s %8s %8s %8s' % ('组合', '累计%', '年化%', '波动%', '回撤%', '夏普', '卡玛'), flush=True)
    for k, v in m.items():
        print('%-10s %+9.2f %+9.2f %9.2f %+8.2f %8s %8s' % (
            k, v['累计收益率%'], v['年化收益率%'], v['年化波动率%'],
            v['最大回撤%'], v['夏普'], v['卡玛']), flush=True)

    lw = res['latest_w']
    print('\n── 最新权重（%s） ──' % int(lw.iloc[0]['date']), flush=True)
    print('%-10s %8s %8s %8s %8s' % ('模型', '黄金', '国债', '宽基', '现金'), flush=True)
    for label, row in lw.iterrows():
        print('%-10s %7.1f%% %7.1f%% %7.1f%% %7.1f%%' % (
            label, row['黄金'] * 100, row['国债'] * 100,
            row['宽基'] * 100, row['现金'] * 100), flush=True)

    out_dir = args.out or os.path.join('output', 'asset_allocation')
    html = build_report(res, out_dir)
    print('\n可视化报告: %s' % os.path.abspath(html), flush=True)
    # CSV 与报告同目录同批次（文件名带时间戳，避免多次运行互相覆盖）
    csv_dir = os.path.dirname(os.path.abspath(html))
    ts = _ts()
    nav_eff = res['nav'].loc[res['nav'].index >= res['meta']['eff_start']]  # 有效投资期
    nav_eff.to_csv(os.path.join(csv_dir, 'asset_allocation_nav_%s.csv' % ts), encoding='utf-8-sig')
    res['trades'].to_csv(os.path.join(csv_dir, 'asset_allocation_trades_%s.csv' % ts),
                         index=False, encoding='utf-8-sig')
    res['weights_long'].to_csv(os.path.join(csv_dir, 'asset_allocation_weights_%s.csv' % ts),
                               index=False, encoding='utf-8-sig')
    print('中间结果已保存（有效投资期 %d ~ %d）:'
          % (res['meta']['eff_start'], res['meta']['end']), flush=True)
    for f in ('nav', 'trades', 'weights'):
        print('  %s' % os.path.join(csv_dir, 'asset_allocation_%s_%s.csv' % (f, ts)), flush=True)
    print('完成 (%.0fs)' % (time.time() - t0), flush=True)
    return res


# ----------------------------------------------------------------------
# alloc 模式
# ----------------------------------------------------------------------
def run_alloc_mode(args):
    from data_provider import DataProvider
    from report import build_alloc_report
    t0 = time.time()
    dp = DataProvider(args.local_path)
    cal = dp.calendar()
    # 只取「窗口+缓冲」的数据量（--begin 缺省时不拉全历史）
    b = args.begin or cal[max(0, len(cal) - 1 - args.lookback - 10)]
    R = build_asset_returns(dp, b, args.end or cal[-1],
                            cash_mode=args.cash_mode, cash_yield=args.cash_yield,
                            lookback=args.lookback)
    window = R.iloc[-args.lookback:]
    mu, cov = annualized_stats(window, shrink=args.shrink)
    d0, d1 = str(window.index[0]), str(window.index[-1])
    print('\n═══ 当前配置（窗口 %s ~ %s，%d 交易日，λ=%g%s）═══'
          % (d0[:8], d1[:8], len(window), args.lam,
             '，τ=%g' % args.tau if 'bl' in args.models else ''), flush=True)
    print('\n窗口年化收益: ' + '  '.join('%s %+0.1f%%' % (a, mu[i] * 100)
                                        for i, a in enumerate(ASSET_NAMES)), flush=True)
    print('窗口年化波动: ' + '  '.join('%s %.1f%%' % (a, cov[i][i] ** 0.5 * 100)
                                      for i, a in enumerate(ASSET_NAMES)), flush=True)
    views = load_views(args.views)
    models = _check_models([m.strip() for m in args.models.split(',') if m.strip()])
    bounds = parse_bounds('' if args.bounds == 'none' else args.bounds, len(ASSET_NAMES))
    fixed_w = [float(x) for x in args.fixed_weights.split(',')] if args.fixed_weights else None

    # 基准日收益（--excess-cov 用）
    bm_ret = None
    if args.excess_cov:
        try:
            bm_close = dp.benchmark_close('000300.SH', b, args.end or cal[-1])
            bm_ret = bm_close.pct_change().reindex(R.index).fillna(0.0)
            print('[配置] Σ 采用超额收益协方差口径（基准 000300.SH，现金保留原始口径）', flush=True)
        except Exception as exc:
            print('[配置][警告] 获取基准失败（%s），退回原始收益协方差' % str(exc)[:80], flush=True)
            bm_ret = None

    # 分模型估计窗口（均值方差默认半年，BL 沿用 --lookback）
    win_map = {m: args.lookback for m in models}
    if 'mv' in models:
        win_map['mv'] = args.lookback_mv or min(122, args.lookback)
    if 'bl' in models:
        win_map['bl'] = args.lookback_bl or args.lookback
    print('估计窗口: ' + '、'.join('%s=%d' % (MODEL_LABELS[m], win_map[m]) for m in models), flush=True)

    print('\n%-10s %8s %8s %8s %8s' % ('模型', '黄金', '国债', '宽基', '现金'), flush=True)
    weights = {}
    stats_cache = {}
    for m in models:
        win = win_map[m]
        if win not in stats_cache:
            stats_cache[win] = annualized_stats(window.iloc[-win:], shrink=args.shrink,
                                                excess_bench=bm_ret)
        mu_m, cov_m = stats_cache[win]
        w = solve(m, mu_m, cov_m, names=ASSET_NAMES, bounds=bounds,
                  lam=args.lam, fixed_weights=fixed_w, views=views, tau=args.tau,
                  omega_mode=args.omega)
        weights[MODEL_LABELS[m]] = w
        print('%-10s %7.1f%% %7.1f%% %7.1f%% %7.1f%%' % (
            MODEL_LABELS[m], w[0] * 100, w[1] * 100, w[2] * 100, w[3] * 100), flush=True)
    print('\n实操对应标的: 黄金 518880｜国债 511010｜宽基 510300/510050/510500/512100/563300 等权｜'
          '现金 511880', flush=True)
    print('口径: 前复权、现金 %s；纯研究教育用途，不构成投资建议'
          % ('固定年化 %.2f%%' % (args.cash_yield * 100) if args.cash_mode == 'fixed'
             else '短融ETF 511360 实测'), flush=True)

    # 落盘：HTML 报告 + 权重 CSV（与回测同目录，便于策略交流场景直接转发）
    out_dir = args.out or os.path.join('output', 'asset_allocation')
    html = build_alloc_report({
        'mu': mu, 'cov': cov, 'weights': weights, 'models': models,
        'window_begin': window.index[0], 'window_end': window.index[-1],
        'window_days': len(window), 'lam': args.lam, 'tau': args.tau,
        'bounds_str': '' if args.bounds == 'none' else args.bounds,
        'cash_mode': args.cash_mode, 'cash_yield': args.cash_yield,
        'has_views': bool(views), 'n_views': len(views or []),
        'lookbacks': {MODEL_LABELS[m]: win_map[m] for m in models},
        'excess_cov': bool(bm_ret is not None), 'omega_mode': args.omega,
    }, out_dir)
    print('\n可视化报告: %s' % os.path.abspath(html), flush=True)
    wdf = pd.DataFrame({label: w for label, w in weights.items()},
                       index=ASSET_NAMES).T * 100
    csv_path = os.path.join(out_dir, 'asset_allocation_alloc_weights_%s.csv' % _ts())
    wdf.to_csv(csv_path, encoding='utf-8-sig')
    print('权重表已保存: %s' % os.path.abspath(csv_path), flush=True)
    print('完成 (%.0fs)' % (time.time() - t0), flush=True)
    return wdf


# ----------------------------------------------------------------------
# explain 模式
# ----------------------------------------------------------------------
def run_explain_mode(args):
    """讲解知识库主题。知识库正文在 references/knowledge.md，本函数只做检索与打印。"""
    topics = load_knowledge()
    topic = args.topic
    if topic not in topics:
        print('可用主题: %s' % '、'.join(topics), flush=True)
        return
    print('\n【%s】\n\n%s\n' % (topic, topics[topic].strip()), flush=True)


# ----------------------------------------------------------------------
# 参数
# ----------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(description='星耀数智大类资产配置（黄金/国债/宽基/现金 × 四模型）')
    p.add_argument('--mode', required=True, choices=['backtest', 'alloc', 'explain'])
    p.add_argument('--period', default='3y', help='快捷区间：3y(默认)/5y/1y/6m/ytd/2024 等')
    p.add_argument('--begin', type=int, default=0, help='起始 YYYYMMDD（与 --end 同时给出时优先）')
    p.add_argument('--end', type=int, default=0, help='结束 YYYYMMDD')
    p.add_argument('--models', default='fixed,mv,rp,bl', help='模型组合，逗号分隔 fixed/mv/rp/bl')
    p.add_argument('--rebalance', default='m', choices=['y', 'm', 'w'], help='调仓频率，默认月度')
    p.add_argument('--lookback', type=int, default=244, help='估计窗口（交易日），默认 244')
    p.add_argument('--lookback-mv', dest='lookback_mv', type=int, default=0,
                   help='均值方差独立估计窗口（交易日），0=自动取 122（半年）；'
                        'MV 对输入更敏感，建议同时开 --shrink 0.2')
    p.add_argument('--lookback-bl', dest='lookback_bl', type=int, default=0,
                   help='BL 独立估计窗口（交易日），0=沿用 --lookback（BL 对窗口不敏感）')
    p.add_argument('--omega', default='ratio', choices=['ratio', 'idzorek', 'legacy'],
                   help='BL 观点误差矩阵构造：ratio=置信度比例法 Ω=τ(1−conf)/conf·PΣPᵀ（默认，'
                        'conf 即后验落在观点上的权重，与 idzorek 刻度因子法等价）；'
                        'legacy=不含 τ 的历史口径（观点影响被压低，仅用于复现旧结果）')
    p.add_argument('--excess-cov', dest='excess_cov', action='store_true',
                   help='Σ 改用相对沪深300的超额收益估计（风险资产部分，现金保留原始口径），'
                        '剔除系统性风险、缓解"高市场风险资产反获高权重"')
    p.add_argument('--lam', type=float, default=2.0, help='风险厌恶系数 λ，默认 2')
    p.add_argument('--tau', type=float, default=0.05, help='BL 先验不确定性 τ，默认 0.05')
    p.add_argument('--shrink', type=float, default=0.0,
                   help='协方差对角收缩系数（0~0.5），缓解 MV 输入敏感，0=关')
    p.add_argument('--rf', type=float, default=0.0, help='无风险利率（年化，夏普用）')
    p.add_argument('--cash-mode', dest='cash_mode', default='fixed', choices=['fixed', 'market'],
                   help='现金口径：fixed=固定年化(默认)｜market=短融ETF 511360 实测')
    p.add_argument('--cash-yield', dest='cash_yield', type=float, default=0.018,
                   help='固定年化现金收益率，默认 0.018')
    p.add_argument('--bounds', default=DEFAULT_BOUNDS,
                   help="各资产权重上下界，8 个数字（黄金lo,hi,国债lo,hi,...）；'none' 关界")
    p.add_argument('--fixed-weights', dest='fixed_weights', default='',
                   help='固定权重模型的权重，如 0.2,0.3,0.4,0.1（默认等权）')
    p.add_argument('--views', default='', help='BL 观点 JSON 文件路径')
    p.add_argument('--topic', default='资产配置', help='explain 模式主题')
    p.add_argument('--out', default='', help='报告输出目录')
    p.add_argument('--local-path', dest='local_path', default='D:/AmazingData_local_data/')
    return p


def main():
    args = build_parser().parse_args()
    if args.mode == 'backtest':
        run_backtest_mode(args)
    elif args.mode == 'alloc':
        run_alloc_mode(args)
    else:
        run_explain_mode(args)


if __name__ == '__main__':
    main()
