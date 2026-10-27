# -*- coding: utf-8 -*-
"""
组合层:目标持仓权重构建

两种持仓口径:
    topn    目标持仓数(默认):持有信号覆盖的股票按等权/加权分配资金
    shares  份数模式:总资金划分为固定份数,每只股票占用一份(可自定义权重表)

权重方案(equal/invvol/mktcap)仅在 topn 口径下生效。
板块限制对两种口径均生效:限制板块内持仓市值不超过板块上限。
"""

import numpy as np
import pandas as pd


def equal_weight(names) -> pd.Series:
    n = len(names)
    if n == 0:
        return pd.Series(dtype=float)
    return pd.Series(1.0 / n, index=names)


def inverse_vol_weight(close: pd.DataFrame, names, lookback: int = 60) -> pd.Series:
    """波动率倒数加权(近 lookback 日收益波动)"""
    ret = close[names].pct_change().iloc[-lookback:]
    vol = ret.std()
    inv = 1.0 / vol.replace(0, np.nan)
    w = inv / inv.sum()
    return w.dropna()


def market_cap_weight(mv: pd.DataFrame, names, date) -> pd.Series:
    """流通市值加权(按指定日期截面)"""
    if date in mv.index:
        row = mv.loc[date, names]
    else:
        row = mv[names].iloc[-1]
    w = row / row.sum()
    return w.dropna()


def build_target_weights(signal_state: pd.DataFrame, date,
                         position_mode: str = 'topn', top_n: int = 20,
                         weight_scheme: str = 'equal',
                         panels: dict = None, total_shares: int = 2000,
                         weight_table: pd.Series = None):
    """
    计算指定日期的目标权重向量(资金占比,和 <= 1)。

    signal_state: 状态补全后的信号矩阵(-1 持有 / +1 空仓)
    """
    if date not in signal_state.index:
        return pd.Series(dtype=float)
    row = signal_state.loc[date]
    held = row[row == -1].index.tolist()
    if not held:
        return pd.Series(dtype=float)

    if position_mode == 'topn':
        held = held[:top_n]
        if weight_scheme == 'invvol' and panels is not None:
            w = inverse_vol_weight(panels['close'], held)
        elif weight_scheme == 'mktcap' and panels is not None and 'mv' in panels:
            w = market_cap_weight(panels['mv'], held, date)
        else:
            w = equal_weight(held)
        return w
    elif position_mode == 'shares':
        # 份数模式:每只股票固定份数,单份权重 = 份数 / 总份数
        if weight_table is not None:
            wt = weight_table.reindex(held).fillna(0)
            total = wt.sum()
            if total <= 0:
                return pd.Series(dtype=float)
            return wt / total
        per = 1.0 / total_shares
        n = min(len(held), total_shares)
        w = pd.Series(per, index=held[:n])
        return w / w.sum()
    else:
        raise ValueError(f'未知持仓口径: {position_mode}')


def apply_sector_cap(weights: pd.Series, sector_map: dict, sector_caps: dict,
                     current_usage: dict = None):
    """
    板块限制:限制板块内权重总和不超过上限。

    超限的股票按优先顺序截断,返回 (调整后权重, 更新后的板块占用)。
    sector_map: {股票: 板块名};sector_caps: {板块名: 上限(资金占比)}
    """
    usage = dict(current_usage or {})
    out = {}
    for code, w in weights.items():
        sector = sector_map.get(code)
        if sector is None or sector not in sector_caps:
            out[code] = w
            continue
        cap = sector_caps[sector]
        used = usage.get(sector, 0.0)
        allowed = max(cap - used, 0.0)
        take = min(w, allowed)
        if take > 0:
            out[code] = take
            usage[sector] = used + take
    return pd.Series(out), usage
