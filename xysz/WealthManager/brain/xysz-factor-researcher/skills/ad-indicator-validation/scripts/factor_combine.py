# -*- coding: utf-8 -*-
"""
合成层:多指标截面排名与加权合成(排名选股模式)

提供三种多指标合成方式,统一输出"买入优先级 score 面板":
    rank    截面排名:每个指标截面排名后等权求和
    zscore  截面标准化:每个指标 CSZSCORE 后按权重求和
    pctrank 截面百分位:每个指标 CSPCTRANK 后按权重求和

score 越小越优先买入(1 = 截面最优)。

截面运算使用 AmazingData 截面算子(CrossSectionFunction),
输入输出均为 DataFrame(行=日期, 列=股票),全面板向量化。
"""

import numpy as np
import pandas as pd

from AmazingData.operator.cross_section_function import (
    CrossSectionFunction as CS)  # 顶层导入:SDK 在 import 时完成鉴权(权限管控点)


# ----------------------------------------------------------------------
# 截面预处理
# ----------------------------------------------------------------------

def winsorize(panel: pd.DataFrame, n_mad: float = 3.0) -> pd.DataFrame:
    """MAD 缩尾:超出 中位数 ± n_mad×MAD 的值截断到边界(逐日截面)"""
    med = panel.median(axis=1)
    mad = (panel.sub(med, axis=0)).abs().median(axis=1)
    upper = med + n_mad * 1.4826 * mad
    lower = med - n_mad * 1.4826 * mad
    return panel.clip(lower=lower, upper=upper, axis=0)


def standardize(panel: pd.DataFrame, method: str = 'zscore') -> pd.DataFrame:
    """截面标准化;zscore / pctrank / normalize 分别对应 CS 算子"""
    valid = panel.notna()
    if method == 'zscore':
        out = CS.CSZSCORE(panel)
    elif method == 'pctrank':
        out = CS.CSPCTRANK(panel)
    elif method == 'normalize':
        out = CS.CSNORMALIZE(panel)
    elif method == 'rank':
        out = CS.CSRANK(panel, ascending=True)
    else:
        raise ValueError(f'未知标准化方法: {method}')
    return out.where(valid)


# ----------------------------------------------------------------------
# 多指标合成
# ----------------------------------------------------------------------

def combine(values: dict, names, dirs: dict, method: str = 'zscore',
            weights: dict = None, winsor: bool = True) -> pd.DataFrame:
    """
    多指标加权合成 → 截面排名 → score(1 = 最优先买入)。

    参数
    ----
    values  : {因子名: 值面板} 来自 signal_engine.load_factors(外部指标 CSV)
    names   : 参与合成的因子名列表
    dirs    : {因子名: 方向} 来自 CLI --dirs(+1 大优 / -1 小优 / 0 不参与)
    method  : zscore / pctrank / rank
    weights : {因子名: 权重},默认等权

    返回
    ----
    score DataFrame(行=日期, 列=股票),值 = 截面排名,1 = 最优
    """
    weights = weights or {}
    total = None
    used = []
    for name in names:
        name_u = name.upper()
        panel = values.get(name, values.get(name_u))
        if panel is None or panel.empty:
            continue
        factor_dir = int(dirs.get(name_u, 0)) if dirs else 0
        if factor_dir == 0:
            # 未给方向(或方向 0)的因子不参与排名合成
            continue
        if winsor:
            panel = winsorize(panel)
        std = standardize(panel * factor_dir if factor_dir < 0 else panel, method)

        w = float(weights.get(name, 1.0))
        total = std * w if total is None else total.add(std * w, fill_value=np.nan)
        used.append(name)

    if total is None:
        raise RuntimeError('没有任何可参与合成的指标(检查指标方向注册)')

    score = CS.CSRANK(total, ascending=True)
    return score


def score_to_signal(score: pd.DataFrame, rebalance_index, top_n: int = 20):
    """
    排名选股 → 信号矩阵(调仓日重排,周期内持有不变)。

    调仓日:取截面 score 最小的 top_n 只 → -1(持有),其余 +1(空仓)。
    非调仓日:0(延续上一状态,由状态补全处理)。

    rebalance_index: 调仓日列表(DatetimeIndex 或 list)
    """
    sig = pd.DataFrame(0.0, index=score.index, columns=score.columns)
    members = {}
    for d in rebalance_index:
        if d not in score.index:
            continue
        row = score.loc[d]
        top = row.dropna().nsmallest(top_n).index
        sig.loc[d, top] = -1.0
        other = row.dropna().index.difference(top)
        sig.loc[d, other] = 1.0
        members[d] = list(top)
    return sig, members


def rebalance_dates(index: pd.DatetimeIndex, freq: str = 'monthly'):
    """
    生成调仓日序列(取每个周期最后一个交易日)。

    freq: daily / weekly / monthly / quarterly
    """
    idx = pd.DatetimeIndex(index)
    if freq == 'daily':
        return idx
    if freq == 'weekly':
        key = idx.isocalendar().year.astype(str) + '-' + idx.isocalendar().week.astype(str)
    elif freq == 'monthly':
        key = idx.to_period('M').astype(str)
    elif freq == 'quarterly':
        key = idx.to_period('Q').astype(str)
    else:
        raise ValueError(f'未知调仓频率: {freq}')
    s = pd.Series(idx, index=key)
    return pd.DatetimeIndex(s.groupby(level=0).last().sort_values())
