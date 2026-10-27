# -*- coding: utf-8 -*-
"""
calc_pi.py — 打印 BL 模型的市场均衡先验 Pi（提问主观观点的参照系）

用途
----
`ad-asset-allocation/scripts/search.py --mode alloc` 会打印各资产的窗口年化收益 mu
与年化波动 sigma，但**不打印隐含均衡先验 Pi**。而 BL 观点采集必须以 Pi 为参照系
（问「相对市场均衡，你认为该偏离多少」），否则用户容易拍脑袋给绝对收益数字。

本脚本复用 search.py 完全相同的数据口径与估计函数，单独把 Pi 算出来并打印。

Pi 定义（He & Litterman 1999）
----------------------------
    Pi = lambda * Sigma @ w_eq

默认 lambda=2.0（风险厌恶系数，与 search.py --lam 默认一致），
w_eq 为等权 1/N（与 models.py black_litterman 默认一致）。

注意：Sigma 含非对角项，所以 Pi 通常不等于窗口年化收益 mu；
国债与现金的 Pi 接近 0（无风险资产不应有超额收益），这是正常的。

用法
----
    python calc_pi.py                 # 默认近一年窗口、244 交易日
    python calc_pi.py --lam 3         # 换风险厌恶系数
    python calc_pi.py --lookback 500  # 换估计窗口

环境依赖：需先配置 AD_USERNAME / AD_PASSWORD / AD_HOST / AD_PORT 并可登录 AmazingData。
运行异常时按 ad-asset-allocation skill 的说明注入环境变量
（SystemDrive / NUMBA_CACHE_DIR / PYTHONPATH 等）。
"""

import argparse
import sys
from pathlib import Path

import numpy as np

# 允许直接以脚本方式运行，同时兼容从任意 cwd 调用
_SCRIPTS = Path.home() / '.workbuddy' / 'skills' / 'ad_asset_allocation' / 'scripts'
if not _SCRIPTS.exists():
    sys.exit(f'找不到 ad_asset_allocation scripts 目录: {_SCRIPTS}')
sys.path.insert(0, str(_SCRIPTS))

from data_provider import DataProvider      # noqa: E402
from backtest import build_asset_returns     # noqa: E402
from models import ASSET_NAMES               # noqa: E402
from search import annualized_stats, resolve_period_dp  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description='打印 BL 市场均衡先验 Pi')
    ap.add_argument('--lam', type=float, default=2.0, help='风险厌恶系数 lambda，默认 2.0')
    ap.add_argument('--lookback', type=int, default=244, help='估计窗口（交易日），默认 244')
    ap.add_argument('--period', default='1y', help='拉取区间，默认 1y')
    ap.add_argument('--shrink', type=float, default=0.0, help='协方差收缩，默认 0（关）')
    args = ap.parse_args()

    dp = DataProvider()
    cal = dp.calendar()
    b, e = resolve_period_dp(dp, args.period, None, None)
    R = build_asset_returns(dp, b, e, dp.prev_trade_day(cal[-1]))
    win = R.tail(args.lookback)
    mu, cov = annualized_stats(win, shrink=args.shrink)

    n = len(ASSET_NAMES)
    w_eq = np.ones(n) / n
    pi = args.lam * cov @ w_eq

    print()
    print(f'=== BL 均衡先验 Pi（lambda={args.lam}，w_eq=等权，窗口 {args.lookback} 交易日）===')
    print(f'窗口区间: {win.index[0]} ~ {win.index[-1]}（{len(win)} 天）')
    print()
    print('%-8s %12s %12s %12s' % ('资产', '窗口年化收益', '年化波动', '隐含均衡Pi'))
    for i, nm in enumerate(ASSET_NAMES):
        print('%-8s %11.2f%% %11.2f%% %11.2f%%'
              % (nm, mu[i] * 100, cov[i][i] ** 0.5 * 100, pi[i] * 100))

    print()
    print('--- 提问用户主观观点用的参照系 ---')
    print(f'宽基 Pi 绝对值约 {pi[2] * 100:.1f}%  -> 问「宽基明年年化你看到几个点？市场均衡价是 {pi[2] * 100:.1f}%」')
    print(f'黄金相对宽基均衡价差约 {(pi[0] - pi[2]) * 100:.1f} 个百分点'
          f'  -> 问「黄金相对宽基能跑赢几个点？均衡是 {(pi[0] - pi[2]) * 100:.1f} 个点」')
    print()
    print('硬约束（来自 ad-asset-allocation skill）：')
    print('  1. 不要对国债/现金下绝对观点（Pi 约等于 0），要用债券/现金表达观点请改用相对观点')
    print('  2. 观点条数必须 <= 资产数（4 条），否则均衡先验被完全接管，BL 退化成纯主观配置')
    print('  3. 相对观点系数写成 1.0/-1.0（不是 0.1/-0.1）')
    print('  4. conf 含义是「后验落在该观点上的权重」（0.5 = 五五分），不是「我有多确定」')
    print()
    print(f'数据口径: 前复权、现金固定年化 1.80% 模拟、窗口 {win.index[0]} ~ {win.index[-1]}')
    print('来源: 星耀数智（AmazingData）｜纯研究教育用途，不构成投资建议')


if __name__ == '__main__':
    main()
