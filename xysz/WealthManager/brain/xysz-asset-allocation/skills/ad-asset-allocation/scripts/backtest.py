# -*- coding: utf-8 -*-
"""大类资产配置回测引擎。

资产池（4 大类）：
    黄金  518880.SH
    国债  511010.SH
    宽基  510300.SH / 510050.SH / 510500.SH / 512100.SH / 563300.SH（逐日可得成分等权合成）
    现金  固定年化（默认 1.8%，--cash-yield 可调）
          或 --cash-mode market 用短融ETF 511360.SH 实测收益（市场化替代）

口径：
    全部前复权（累计复权因子归一化，见 data_provider.etf_kline_adj）
    调仓频率 年/月/周（默认月度，每月第一个交易日），调仓日重设权重、期间持有
    模型窗口：调仓日前 lookback 个交易日的日收益估计 μ、Σ（年化 244）
    NAV0 = 1；基准 = 等权组合（月度再平衡）+ 各单资产
"""

import os
import bisect

import numpy as np
import pandas as pd

from data_provider import DataProvider
from models import ASSET_NAMES, MODEL_LABELS, annualized_stats, solve, parse_bounds

ETF = {
    'gold': '518880.SH',
    'bond': '511010.SH',
    'broad': ['510300.SH', '510050.SH', '510500.SH', '512100.SH', '563300.SH'],
    'cash_sim': '511880.SH',    # 实操对应标的（展示用）
    'cash_mkt': '511360.SH',    # 市场化现金替代（短融ETF）
}


# ----------------------------------------------------------------------
# 资产收益矩阵
# ----------------------------------------------------------------------
def build_asset_returns(dp: DataProvider, begin: int, end: int,
                        cash_mode: str = 'fixed', cash_yield: float = 0.018,
                        lookback: int = 244) -> pd.DataFrame:
    """4 大类资产日收益矩阵（index=交易日，columns=ASSET_NAMES）。

    起点自动前伸 lookback 个交易日供首个调仓日的窗口估计。
    """
    cal = dp.calendar()
    # 前伸窗口起点（begin 不是交易日时取其后第一个交易日）
    i = bisect.bisect_left(cal, begin)
    if i >= len(cal):
        raise ValueError('起始日 %d 晚于交易日历' % begin)
    i0 = max(0, i - lookback - 10)
    b0 = cal[i0]
    print('[回测] 拉取资产前复权行情 %d-%d（含 %d 日窗口前伸）...' % (b0, end, lookback), flush=True)

    gold = dp.asset_returns([ETF['gold']], b0, end)[ETF['gold']]
    bond = dp.asset_returns([ETF['bond']], b0, end)[ETF['bond']]

    # 宽基：逐日可得成分等权合成（563300 于 2023-09 上市，之前自动用前 4 只）
    broad_all = dp.asset_returns(ETF['broad'], b0, end)
    broad = broad_all.mean(axis=1, skipna=True)
    n_avail = broad_all.notna().sum(axis=1)
    broad[n_avail == 0] = np.nan

    if cash_mode == 'market':
        cash = dp.asset_returns([ETF['cash_mkt']], b0, end)[ETF['cash_mkt']]
        cash_note = '短融ETF %s 实测收益（市场化口径）' % ETF['cash_mkt']
    else:
        daily = (1.0 + cash_yield) ** (1.0 / 244) - 1.0
        cash = None  # 之后按对齐后的交易日填充
        cash_note = '固定年化 %.2f%% 模拟（实操对应标的 %s）' % (cash_yield * 100, ETF['cash_sim'])

    R = pd.DataFrame({'黄金': gold, '国债': bond, '宽基': broad})
    R = R.dropna(how='all').sort_index()
    # 黄金/国债缺日（停牌）按 0 处理，宽基逐日可得
    R = R.fillna({'黄金': 0.0, '国债': 0.0})
    if cash is None:
        R['现金'] = daily
    else:
        R['现金'] = cash.reindex(R.index).fillna(0.0)
    R = R[ASSET_NAMES]
    print('[回测] 资产日收益矩阵 %d 天（%d ~ %d）｜现金口径: %s'
          % (len(R), R.index.min(), R.index.max(), cash_note), flush=True)
    return R


# ----------------------------------------------------------------------
# 调仓日序列
# ----------------------------------------------------------------------
def rebalance_dates(dates: list, freq: str) -> list:
    """freq ∈ y/m/w：每期第一个交易日。"""
    seen, out = set(), []
    for d in dates:
        ts = pd.Timestamp(str(d))
        if freq == 'y':
            key = str(d)[:4]
        elif freq == 'm':
            key = str(d)[:6]
        else:
            iso = ts.isocalendar()
            key = '%d-W%02d' % (iso[0], iso[1])
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


# ----------------------------------------------------------------------
# 绩效指标
# ----------------------------------------------------------------------
def metrics(nav: pd.Series, rf: float = 0.0) -> dict:
    nav = nav.dropna()
    ret = float(nav.iloc[-1] / nav.iloc[0] - 1.0)
    daily = nav.pct_change().dropna()
    years = max(len(nav) / 244.0, 1e-9)
    ann = (1.0 + ret) ** (1.0 / years) - 1.0
    vol = float(daily.std() * np.sqrt(244))
    dd = float((nav / nav.cummax() - 1.0).min())
    sharpe = float((ann - rf) / vol) if vol > 1e-9 else None
    calmar = float(ann / abs(dd)) if abs(dd) > 1e-9 else None
    return {'累计收益率%': round(ret * 100, 2), '年化收益率%': round(ann * 100, 2),
            '年化波动率%': round(vol * 100, 2), '最大回撤%': round(dd * 100, 2),
            '夏普': round(sharpe, 2) if sharpe is not None else None,
            '卡玛': round(calmar, 2) if calmar is not None else None}


# ----------------------------------------------------------------------
# 回测主流程
# ----------------------------------------------------------------------
def run_backtest(begin: int, end: int, models: list, rebalance: str = 'm',
                 lookback: int = 244, lam: float = 2.0, rf: float = 0.0,
                 cash_mode: str = 'fixed', cash_yield: float = 0.018,
                 bounds_str: str = '', fixed_weights=None, views: list = None,
                 tau: float = 0.05, shrink: float = 0.0,
                 dp: DataProvider = None,
                 local_path: str = 'D:/AmazingData_local_data/',
                 R: pd.DataFrame = None,
                 excess_cov: bool = False,
                 omega_mode: str = 'ratio',
                 lookback_mv: int = None,
                 lookback_bl: int = None,
                 benchmark_close: pd.Series = None) -> dict:
    """回测主流程。

    R: 预先构建好的资产日收益矩阵（参数扫描时复用，避免重复拉行情）
    benchmark_close: 基准收盘 Series（excess_cov 时用；缺省按需取 000300.SH）
    excess_cov: Σ 用相对基准的超额收益估计（风险资产部分，现金保留原始口径）
    omega_mode: 'ratio'（默认）| 'idzorek'（同公式）| 'legacy'（历史口径）
    lookback_mv / lookback_bl: 均值方差 / BL 的独立估计窗口（缺省时沿用 lookback；
        均值方差默认 122=半年，对输入更敏感、宜配合 --shrink 收缩）
    """
    dp = dp or DataProvider(local_path=local_path)
    if R is None:
        R = build_asset_returns(dp, begin, end, cash_mode, cash_yield, lookback)
    all_dates = list(R.index)

    # 各模型估计窗口（均值方差默认半年，BL 对窗口不敏感故沿用 lookback）
    win_map = {m: lookback for m in models}
    if 'mv' in models:
        win_map['mv'] = lookback_mv if lookback_mv else min(122, lookback)
    if 'bl' in models:
        win_map['bl'] = lookback_bl if lookback_bl else lookback
    win_min = min(win_map.values())

    # 有效起点：最短估计窗口的第 N 个交易日起
    if len(all_dates) <= max(win_map.values()):
        raise ValueError('估计窗口(%d 日)超过数据长度 %d，请扩大区间或调小 lookback'
                         % (max(win_map.values()), len(all_dates)))
    eff_start = all_dates[win_min]
    rb_all = rebalance_dates(all_dates, rebalance)
    rb_dates = [d for d in rb_all if d >= eff_start and d <= end]
    if not rb_dates:
        raise ValueError('无有效调仓日')
    # 消除死区：eff_start 不在期首时立即建仓（否则建仓前 NAV 平推浪费窗口后时间）
    if rb_dates[0] > eff_start:
        rb_dates.insert(0, eff_start)
    win_txt = '、'.join('%s=%d' % (MODEL_LABELS.get(m, m), win_map[m]) for m in models)
    print('[回测] 有效区间 %d~%d，调仓 %d 次（%s），估计窗口 %s'
          % (eff_start, end, len(rb_dates), {'y': '年', 'm': '月', 'w': '周'}[rebalance],
             win_txt), flush=True)

    bounds = parse_bounds(bounds_str, len(ASSET_NAMES))

    # 基准日收益（--excess-cov 用；未传入则按需从 000300.SH 取）
    bm_ret = None
    if excess_cov:
        bm = benchmark_close
        if bm is None:
            try:
                bm = dp.benchmark_close('000300.SH', begin, end)
            except Exception as exc:
                print('[回测][警告] 获取基准失败（%s），退回原始收益协方差' % str(exc)[:80],
                      flush=True)
                bm = None
        if bm is not None:
            bm_ret = pd.Series(bm).pct_change().reindex(R.index).fillna(0.0)
            print('[回测] Σ 采用超额收益协方差口径（基准 000300.SH，现金保留原始口径）', flush=True)

    # 逐调仓日求解各模型权重
    weights_hist = {m: [] for m in models}   # {model: DataFrame(date × 资产)}
    for t in rb_dates:
        loc = all_dates.index(t)
        stats_cache = {}
        for m in models:
            win = win_map[m]
            key = win
            if key not in stats_cache:
                window = R.iloc[loc - win:loc]
                stats_cache[key] = annualized_stats(window, shrink=shrink,
                                                    excess_bench=bm_ret)
            mu, cov = stats_cache[key]
            w = solve(m, mu, cov, names=ASSET_NAMES, bounds=bounds, lam=lam,
                      fixed_weights=fixed_weights, views=views, tau=tau,
                      omega_mode=omega_mode)
            weights_hist[m].append([t] + list(w))

    # 日收益合成：调仓日重设权重（t 开盘调仓、t 日收益按新权重），
    # 调仓区间内权重随价格漂移（真实月度再平衡口径，非每日再平衡）
    def drifted_returns(weights_df: pd.DataFrame) -> pd.Series:
        rb_set = set(weights_df.index)
        out = pd.Series(np.nan, index=all_dates)
        cur = None
        for d in all_dates:
            if d in rb_set:
                cur = weights_df.loc[d].values.astype(float).copy()
                out.loc[d] = float(cur @ R.loc[d].values)
                continue
            if cur is None:
                continue
            r = R.loc[d].values
            r_p = float(cur @ r)
            out.loc[d] = r_p
            tot = 1.0 + r_p
            if tot > 0:
                cur = cur * (1.0 + r) / tot   # 组合权重随价格漂移
        return out.fillna(0.0)

    navs = {}
    for m in models:
        wh = pd.DataFrame(weights_hist[m], columns=['date'] + ASSET_NAMES).set_index('date')
        navs[MODEL_LABELS[m]] = (1.0 + drifted_returns(wh)).cumprod()

    # 基准：等权组合（与模型同一调仓节奏、月内漂移）+ 各单资产买入持有
    eq_w = pd.Series(1.0 / len(ASSET_NAMES), index=ASSET_NAMES)
    eq_wh = pd.DataFrame([eq_w.values] * len(rb_dates), index=rb_dates, columns=ASSET_NAMES)
    navs['等权基准'] = (1.0 + drifted_returns(eq_wh)).cumprod()
    eff_mask = pd.Series(all_dates, index=all_dates) >= eff_start
    for a in ASSET_NAMES:
        ra = pd.Series(0.0, index=all_dates).add(R[a][eff_mask.values], fill_value=0.0)
        navs['仅%s' % a] = (1.0 + ra).cumprod()

    nav = pd.DataFrame(navs)
    nav.index.name = 'date'

    # 绩效：裁掉窗口平推段，锚点=eff_start 前一交易日 NAV=1.0
    # （否则 years=len(nav)/244 把窗口期算进投资年限，年化/夏普被系统性低估）
    anchor_d = all_dates[win_min - 1]
    perf = {}
    for c in nav.columns:
        seg = pd.concat([pd.Series([1.0], index=[anchor_d]),
                         nav.loc[nav.index >= eff_start, c]])
        perf[c] = metrics(seg, rf)

    # 最新权重
    latest = {}
    for m in models:
        wh = pd.DataFrame(weights_hist[m], columns=['date'] + ASSET_NAMES).set_index('date')
        latest[MODEL_LABELS[m]] = wh.iloc[-1]
        latest[MODEL_LABELS[m]]['date'] = int(wh.index[-1])
    latest_w = pd.DataFrame(latest).T

    # 调仓流水（每次调仓的权重变化，各模型合并长表）
    trades = []
    for m in models:
        wh = pd.DataFrame(weights_hist[m], columns=['date'] + ASSET_NAMES).set_index('date')
        prev = None
        for d, row in wh.iterrows():
            for a in ASSET_NAMES:
                trades.append({'日期': d, '模型': MODEL_LABELS[m], '资产': a,
                               '新权重%': round(row[a] * 100, 2),
                               '旧权重%': round(prev[a] * 100, 2) if prev is not None else '',
                               '变化pp': round((row[a] - prev[a]) * 100, 2) if prev is not None else ''})
            prev = row
    trades = pd.DataFrame(trades)

    # 权重明细长表（各模型各调仓日权重，百分比）
    wrows = []
    for m in models:
        wh = pd.DataFrame(weights_hist[m], columns=['date'] + ASSET_NAMES).set_index('date')
        for d, row in wh.iterrows():
            wrows.append({'日期': d, '模型': MODEL_LABELS[m],
                          **{a: round(row[a] * 100, 2) for a in ASSET_NAMES}})
    weights_long = pd.DataFrame(wrows)

    meta = {'begin': begin, 'end': end, 'eff_start': eff_start, 'models': models,
            'rebalance': rebalance, 'lookback': lookback, 'lam': lam, 'rf': rf,
            'cash_mode': cash_mode, 'cash_yield': cash_yield, 'bounds': bounds_str,
            'n_rebalance': len(rb_dates), 'tau': tau, 'shrink': shrink,
            'lookbacks': win_map, 'excess_cov': excess_cov, 'omega_mode': omega_mode,
            'asset_names': list(ASSET_NAMES),
            'etf': dict(ETF),
            'note': '全部前复权（累计复权因子归一化）；宽基=5只ETF逐日可得成分等权合成；'
                    '现金=固定年化模拟（实操对应标的 %s）或短融ETF %s 实测收益；'
                    '调仓日开盘重设权重、区间内权重随价格漂移（真实再平衡口径）；'
                    '估计窗口（交易日，年化 244）：%s；'
                    '%s'
                    '绩效按有效投资期计算（窗口估计期不计入年限）；'
                    '纯研究教育用途，不构成投资建议'
                    % (ETF['cash_sim'], ETF['cash_mkt'], win_txt,
                       'Σ=相对基准的超额收益协方差（现金保留原始口径）；' if excess_cov
                       else 'Σ=原始日收益协方差；')}

    return {'nav': nav, 'perf': perf, 'latest_w': latest_w, 'trades': trades,
            'weights_long': weights_long,
            'weights_hist': {MODEL_LABELS[m]: pd.DataFrame(
                weights_hist[m], columns=['date'] + ASSET_NAMES).set_index('date')
                for m in models},
            'meta': meta}
