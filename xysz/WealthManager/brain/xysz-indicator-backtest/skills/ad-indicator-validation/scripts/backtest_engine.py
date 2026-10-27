# -*- coding: utf-8 -*-
"""
撮合回测引擎:信号 → 持仓 → 净值

撮合规则(逐日三步,日内向量化):
    ① 卖出:有持仓 & 空仓信号 & 非停牌 & 非跌停 → 卖出
    ② 重算持仓(卖出失败则延续持有,次日重试)
    ③ 买入:无持仓 & 持有信号 & 非停牌 & 非涨停 → 按优先级买入

收益计算:
    t 日信号(t 日收盘生成,以收盘价撮合)→ 当日建仓 → 次日起计收益
    (组合收益 = 上一日持仓权重 × 当日收益,等价于"当日买入不吃当日涨幅")
    (以收盘价序列计价,建仓与清仓均按收盘价撮合)

成本模型(按金额计):
    佣金     双向 0.025%,最低 5 元/笔
    印花税   卖出 0.05%
    过户费   双向 0.001%
    滑点     双向 0.05%(5 bps)

输出:
    net_value        含成本净值(主净值,可直接对接策略业绩分析)
    net_value_gross  不含成本净值(成本敏感性对照)
"""

import numpy as np
import pandas as pd

ANNUAL_DAYS = 244
RF_ANNUAL = 0.02

COMMISSION_RATE = 0.00025
COMMISSION_MIN = 5.0
STAMP_TAX = 0.0005        # 卖出印花税(现行)
TRANSFER_FEE = 0.00001    # 过户费(双向)
SLIPPAGE = 0.0005         # 单边滑点 5 bps


# ----------------------------------------------------------------------
# 信号预处理(纯 pandas,可离线测试)
# ----------------------------------------------------------------------

def fill_state(raw: pd.DataFrame) -> pd.DataFrame:
    """
    状态补全:沿时间轴前向填充,把事件信号转为持仓状态。

        原始: 只在信号发生日有 -1/+1,其余 0
        补全: -1 = 持有中, +1 = 空仓中(延续最近一次信号)
    """
    state = raw.replace(0.0, np.nan).ffill(axis=0)
    # 期初无信号视为空仓
    return state.fillna(1.0)


def composite_signal(raw_signals: dict, method: str = 'vote',
                     min_buy_ratio: float = 0.5, min_sell_ratio: float = 0.5):
    """
    多指标信号合成。

    vote: 投票制(与)。买入票占比 >= min_buy_ratio 时综合信号为买入;
          卖出票占比 >= min_sell_ratio 时为卖出;同时满足时按占比高的一方
          定方向,严格相等视为无信号。
    mean: 平均制。各指标信号均值 <-0.5 视为买入,>0.5 视为卖出。
    union: 全部满足制(一票否决)。各指标先转持仓状态(事件→状态补全),
           全部指标都处于持有才持有;任一指标空仓立即卖出。
           买入极严、退出极快,信号最少。

    返回: 原始综合信号矩阵(-1/+1/0,未做状态补全)
    """
    n = len(raw_signals)
    buy = sum((s == -1).astype(float) for s in raw_signals.values())
    sell = sum((s == 1).astype(float) for s in raw_signals.values())
    active = sum((s != 0).astype(float) for s in raw_signals.values()).replace(0, np.nan)

    if method == 'vote':
        buy_ratio = buy / active
        sell_ratio = sell / active
        combined = pd.DataFrame(0.0, index=buy.index, columns=buy.columns)
        # 双向达标时按比例高的一方定方向,严格相等视为无信号
        combined[(buy_ratio >= min_buy_ratio) & (buy >= 1)
                 & (buy_ratio > sell_ratio)] = -1.0
        combined[(sell_ratio >= min_sell_ratio) & (sell >= 1)
                 & (sell_ratio > buy_ratio)] = 1.0
        return combined
    elif method == 'union':
        # 基于各指标的持仓状态(而非当日事件票):
        # 全部持有 → 持有;任一空仓 → 卖出(一票否决)
        states = [fill_state(s) for s in raw_signals.values()]
        hold = (states[0] == -1)
        for s in states[1:]:
            hold = hold & (s == -1)
        combined = pd.DataFrame(1.0, index=hold.index, columns=hold.columns)
        combined[hold] = -1.0
        return combined
    elif method == 'mean':
        arr = sum(s.fillna(0.0) for s in raw_signals.values()) / n
        combined = pd.DataFrame(0.0, index=arr.index, columns=arr.columns)
        combined[arr < -0.5] = -1.0
        combined[arr > 0.5] = 1.0
        return combined
    else:
        raise ValueError(f'未知合成方法: {method}')


def simulate(state: pd.DataFrame, flags: dict, ret: pd.DataFrame,
             position_mode: str = 'topn', top_n: int = 20,
             weight_scheme: str = 'equal', panels: dict = None,
             total_capital: float = 1_000_000.0,
             total_shares: int = 2000, weight_table: pd.Series = None,
             cost_free: bool = False):
    """
    主回测循环。

    state : 状态补全后的信号矩阵(-1 持有 / +1 空仓),未做时移;
            t 日信号按 t 日收盘撮合,收益从次日开始(pos.shift(1))
    flags : tradable / limit_up / limit_down / valid
    ret   : 前复权日收益矩阵
    """
    index = state.index
    codes = state.columns
    T = len(index)

    tradable = flags['tradable'].reindex(index=index, columns=codes).fillna(False)
    can_buy = (tradable & ~flags['limit_up'].shift(1, fill_value=False)) \
        .reindex(index=index, columns=codes).fillna(False)
    can_sell = (tradable & ~flags['limit_down'].shift(1, fill_value=False)) \
        .reindex(index=index, columns=codes).fillna(False)

    holdings = np.zeros((T, len(codes)))
    codes_arr = list(codes)
    code_pos = {c: i for i, c in enumerate(codes_arr)}

    current = set()

    for t in range(T):
        s_today = state.iloc[t]
        want_hold = set(s_today[s_today == -1].index)
        want_sell = set(codes_arr) - want_hold

        # ① 卖出:有持仓 & 空仓信号 & 非停牌 & 非跌停
        for code in list(current & want_sell):
            if bool(can_sell.iloc[t][code]):
                current.discard(code)

        # ② 重算持仓(卖出失败自动延续,次日重试)—— current 即最新持仓

        # ③ 买入:无持仓 & 持有信号 & 非停牌 & 非涨停,受持仓数约束
        if position_mode == 'topn':
            capacity = top_n - len(current)
        else:
            capacity = total_shares - len(current)
        if capacity > 0:
            candidates = [c for c in want_hold - current
                          if bool(can_buy.iloc[t][c])]
            for code in candidates[:capacity]:
                current.add(code)

        if current:
            holdings[t, [code_pos[c] for c in current]] = 1.0

    holdings_df = pd.DataFrame(holdings, index=index, columns=codes)
    return holdings_df


def portfolio_return(holdings: pd.DataFrame, ret: pd.DataFrame,
                     position_mode: str = 'topn', top_n: int = 20,
                     total_capital: float = 1_000_000.0,
                     total_shares: int = 2000, cost_free: bool = False):
    """
    由持仓矩阵计算组合日收益与净值(含成本/不含成本)。

    等权假设:topn 口径下持仓内等权(1/N);shares 口径下每份等权(1/总份数)。
    收益口径:t 日持仓吃 t 日收益(即 t-1 收盘建仓,t+1 对齐由调用方处理 state.shift)。
    """
    if position_mode == 'topn':
        n_held = holdings.sum(axis=1).replace(0, np.nan)
        weight = holdings.div(n_held, axis=0).fillna(0.0)  # 每只 1/N
    else:
        weight = holdings / total_shares

    # T+1: t 日权重来自 t-1 日建仓 → 权重 shift(1) 后乘以当日收益
    pos = weight.shift(1).fillna(0.0)
    gross_ret = (pos * ret).sum(axis=1)

    if cost_free:
        nav = (1 + gross_ret).cumprod()
        return pd.DataFrame({'net_value': nav, 'net_value_gross': nav}), gross_ret

    # ---- 成本模型 ----
    turnover = (weight - weight.shift(1)).abs().sum(axis=1)  # 单边换手(占比)
    buy_amt = (weight - weight.shift(1)).clip(lower=0).sum(axis=1) * total_capital
    sell_amt = (weight.shift(1) - weight).clip(lower=0).sum(axis=1) * total_capital

    n_held_prev = holdings.shift(1).sum(axis=1).replace(0, np.nan)
    n_buy = (holdings - holdings.shift(1)).clip(lower=0).sum(axis=1)
    avg_buy_amt = (buy_amt / n_buy.replace(0, np.nan)).fillna(total_capital / max(top_n, 1))
    commission_buy = (avg_buy_amt * COMMISSION_RATE).clip(lower=COMMISSION_MIN) * n_buy
    n_sell = (holdings.shift(1) - holdings).clip(lower=0).sum(axis=1)
    avg_sell_amt = (sell_amt / n_sell.replace(0, np.nan)).fillna(total_capital / max(top_n, 1))
    commission_sell = (avg_sell_amt * COMMISSION_RATE).clip(lower=COMMISSION_MIN) * n_sell

    stamp = sell_amt * STAMP_TAX
    transfer = (buy_amt + sell_amt) * TRANSFER_FEE
    slip = (buy_amt + sell_amt) * SLIPPAGE

    cost = (commission_buy + commission_sell + stamp + transfer + slip) / total_capital

    net_ret = gross_ret - cost
    nav_gross = (1 + gross_ret).cumprod()
    nav_net = (1 + net_ret).cumprod()

    detail = pd.DataFrame({
        'gross_ret': gross_ret, 'cost': cost, 'turnover': turnover,
        'commission': (commission_buy + commission_sell) / total_capital,
        'stamp_tax': stamp / total_capital, 'transfer_fee': transfer / total_capital,
        'slippage': slip / total_capital,
    }, index=holdings.index)

    return pd.DataFrame({'net_value': nav_net, 'net_value_gross': nav_gross}), detail


def run_backtest(state: pd.DataFrame, flags: dict, ret: pd.DataFrame,
                 position_mode: str = 'topn', top_n: int = 20,
                 weight_scheme: str = 'equal', panels: dict = None,
                 total_capital: float = 1_000_000.0, total_shares: int = 2000,
                 cost_free: bool = False):
    """撮合 → 持仓 → 收益 → 净值,返回 (nav DataFrame, holdings, detail)"""
    holdings = simulate(
        state, flags, ret,
        position_mode=position_mode, top_n=top_n,
        weight_scheme=weight_scheme, panels=panels,
        total_capital=total_capital, total_shares=total_shares,
    )
    nav, detail = portfolio_return(
        holdings, ret,
        position_mode=position_mode, top_n=top_n,
        total_capital=total_capital, total_shares=total_shares,
        cost_free=cost_free,
    )
    return nav, holdings, detail


def summary_stats(nav: pd.Series, gross: pd.Series = None,
                  benchmark: pd.Series = None,
                  annual_days: int = ANNUAL_DAYS, rf: float = RF_ANNUAL):
    """终端简明摘要(完整绩效评估请用 策略业绩分析 skill)"""
    nav = nav.dropna()
    ret = nav.pct_change().dropna()
    years = len(ret) / annual_days
    total = nav.iloc[-1] / nav.iloc[0] - 1
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / years) - 1 if years > 0 else np.nan
    vol = ret.std() * np.sqrt(annual_days)
    sharpe = (cagr - rf) / vol if vol > 0 else np.nan

    peak = nav.cummax()
    dd = nav / peak - 1
    mdd = dd.min()
    mdd_end = dd.idxmin()
    mdd_start = nav.loc[:mdd_end].idxmax()

    out = {
        '总收益': round(total * 100, 2),
        '年化收益(%)': round(cagr * 100, 2),
        '年化波动(%)': round(vol * 100, 2),
        '夏普比率': round(sharpe, 2),
        '最大回撤(%)': round(mdd * 100, 2),
        '回撤起始': str(mdd_start.date()) if hasattr(mdd_start, 'date') else str(mdd_start),
        '回撤结束': str(mdd_end.date()) if hasattr(mdd_end, 'date') else str(mdd_end),
        '卡玛比率': round(cagr / abs(mdd), 2) if mdd < 0 else np.nan,
        '日胜率(%)': round((ret > 0).mean() * 100, 2),
    }
    if gross is not None:
        g = gross.dropna()
        g_total = g.iloc[-1] / g.iloc[0] - 1
        out['总收益(不含成本,%)'] = round(g_total * 100, 2)
    if benchmark is not None:
        b = benchmark.reindex(nav.index).dropna()
        if len(b) > 1:
            b_total = b.iloc[-1] / b.iloc[0] - 1
            out['基准收益(%)'] = round(b_total * 100, 2)
            out['超额收益(%)'] = round((total - b_total) * 100, 2)
    return out
