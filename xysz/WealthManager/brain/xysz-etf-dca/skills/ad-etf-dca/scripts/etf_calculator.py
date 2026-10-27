# -*- coding: utf-8 -*-
"""
ETF 定投核心计算引擎

纯数值计算模块，无外部依赖（除 numpy/scipy）。
包含：佣金建模、份额取整、正向测算、历史回测、目标反推、
IRR/XIRR、最大回撤、波动率、多情景对比。
"""

import math
import warnings
from typing import List, Dict, Optional
from datetime import datetime

import numpy as np
import pandas as pd
from scipy.optimize import newton

warnings.filterwarnings('ignore')


# ==============================================================================
# 基础工具函数
# ==============================================================================

def commission(amount: float, rate: float = 0.0003, min_comm: float = 5.0) -> float:
    """逐笔计算佣金（场内最低5元非线性建模）。

    Args:
        amount: 每期投入金额（元）
        rate: 佣金费率，默认万3
        min_comm: 最低佣金（元），默认5

    Returns:
        单笔佣金（元）
    """
    return max(amount * rate, min_comm)


def shares_buyable(net_amount: float, price: float, lot_size: int = 100) -> int:
    """计算可买入份额，向下取整到整手。

    Args:
        net_amount: 扣除佣金后的净投入金额
        price: 买入价格
        lot_size: 每手份数，默认100

    Returns:
        可买入份额数
    """
    raw_shares = net_amount / price
    return math.floor(raw_shares / lot_size) * lot_size


def _days_between(d1: datetime, d2: datetime) -> float:
    """计算两个日期间的天数。"""
    return (d2 - d1).total_seconds() / 86400.0


# ==============================================================================
# IRR / XIRR 数值求解
# ==============================================================================

def irr(cashflows: List[float], guess: float = 0.05) -> float:
    """内部收益率（适用于等间隔现金流）。

    使用 scipy.optimize.newton 求解，自动迭代多个初始值避免不收敛。

    Args:
        cashflows: 现金流列表 [-投入1, -投入2, ..., +总资产]
        guess: 默认初始猜测（会尝试多个初始值）

    Returns:
        年化 IRR（小数），如 0.092 表示 9.2%
    """
    cf = np.array(cashflows, dtype=float)
    n = len(cf) - 1

    def npv_safe(r):
        """安全的 NPV 计算，逐期递推避免 (1+r)^n 溢出。"""
        total = cf[0]
        disc = 1.0
        for i in range(1, n + 1):
            disc /= (1.0 + r)
            total += cf[i] * disc
        return total

    # 多初始值尝试
    guesses = [0.05, -0.05, 0.10, -0.10, 0.2, 0.01, 0.5]
    if guess not in guesses:
        guesses.insert(0, guess)

    for g in guesses:
        try:
            rate = newton(npv_safe, g, maxiter=100, tol=1e-8, disp=False)
            if abs(npv_safe(rate)) < 1e-4:
                return float(rate)
        except RuntimeError:
            continue
    return float('nan')


def xirr(
    cashflows: List[float],
    dates: List[datetime],
    guess: float = 0.05,
    max_iter: int = 100,
    tol: float = 1e-8,
) -> float:
    """扩展内部收益率（适用于不等间隔现金流）。

    Args:
        cashflows: 现金流列表 [-投入1, -投入2, ..., +总资产]
        dates: 对应的日期列表
        guess: 初始猜测
        max_iter: 最大迭代次数
        tol: 收敛容差

    Returns:
        年化 XIRR（小数）
    """
    cf = np.array(cashflows, dtype=float)
    d0 = dates[0]
    years = np.array([_days_between(d0, d) / 365.25 for d in dates])

    def npv(r):
        return np.sum(cf / (1 + r) ** years)

    def dnpv(r):
        return np.sum(-years * cf / (1 + r) ** (years + 1))

    try:
        r = newton(npv, guess, fprime=dnpv, maxiter=max_iter, tol=tol)
        return float(r)
    except RuntimeError:
        # 牛顿法不收敛，尝试二分法
        return _xirr_bisect(cf, years, tol)


def _xirr_bisect(cf: np.ndarray, years: np.ndarray, tol: float = 1e-8) -> float:
    """二分法求解 XIRR（牛顿法不收敛时的回退方案）。"""
    def npv(r):
        return np.sum(cf / (1 + r) ** years)

    lo, hi = -0.9999, 10.0
    flo, fhi = npv(lo), npv(hi)

    if flo * fhi > 0:
        return float('nan')

    for _ in range(100):
        mid = (lo + hi) / 2
        fmid = npv(mid)
        if abs(fmid) < tol:
            return mid
        if flo * fmid < 0:
            hi, fhi = mid, fmid
        else:
            lo, flo = mid, fmid
    return (lo + hi) / 2


# ==============================================================================
# 风险指标
# ==============================================================================

def annualized_volatility(daily_returns: np.ndarray, trading_days: int = 252) -> float:
    """计算年化波动率。

    Args:
        daily_returns: 日收益率序列
        trading_days: 年交易日数

    Returns:
        年化波动率（小数）
    """
    if len(daily_returns) < 2:
        return 0.0
    return float(np.std(daily_returns, ddof=1) * np.sqrt(trading_days))


def sharpe_ratio(
    annualized_return: float,
    annualized_vol: float,
    risk_free: float = 0.02,
) -> float:
    """计算夏普比率。"""
    if annualized_vol == 0:
        return 0.0
    return (annualized_return - risk_free) / annualized_vol


# ==============================================================================
# 正向测算
# ==============================================================================

def forward_projection(
    initial_price: float,
    amount_per_period: float,
    num_periods: int,
    periods_per_year: int,
    expected_annual_return: float,
    commission_rate: float = 0.0003,
    min_commission: float = 5.0,
) -> Dict:
    """正向测算：基于预期年化收益模拟定投。

    假设价格按几何布朗运动增长，每期以预期价格买入。

    Args:
        initial_price: 当前价格（前复权）
        amount_per_period: 每期投入金额
        num_periods: 总期数
        periods_per_year: 每年定投次数（12=月定投, 52=周定投）
        expected_annual_return: 预期年化收益率（%），如 8 表示 8%
        commission_rate: 佣金费率
        min_commission: 最低佣金

    Returns:
        {
            'total_asset': 期末总资产,
            'total_principal': 总投入本金,
            'total_return': 累计收益,
            'total_return_pct': 累计收益率(%),
            'total_commission': 总佣金,
            'irr': 年化IRR(小数),
            'irr_pct': 年化IRR(%),
            'period_details': [{期数, 日期, 投入, 佣金, 价格, 买入份额, 累计份额, 期末资产}, ...],
            'yearly_summary': [{年份, 当年投入, 当年佣金, 年末份额, 年末资产, 当年收益, irr_pct}, ...],
        }
    """
    period_return = (1 + expected_annual_return / 100) ** (1 / periods_per_year) - 1

    total_shares = 0
    total_principal = 0.0
    total_commission = 0.0
    price = initial_price
    period_details = []
    cashflows = []
    cashflow_dates = []

    for i in range(num_periods):
        comm = commission(amount_per_period, commission_rate, min_commission)
        net_amount = amount_per_period - comm
        shares = net_amount / price  # 正向测算不取整（不知道真实价格）

        total_shares += shares
        total_principal += amount_per_period
        total_commission += comm

        period_details.append({
            'period': i + 1,
            'amount': amount_per_period,
            'commission': round(comm, 2),
            'net_amount': round(net_amount, 2),
            'price': round(price, 4),
            'shares': shares,
            'cumulative_shares': total_shares,
        })

        cashflows.append(-amount_per_period)

        # 价格按期望收益增长
        price *= (1 + period_return)

    final_price = price
    total_asset = total_shares * final_price
    cashflows.append(total_asset)
    total_return = total_asset - total_principal
    total_return_pct = (total_return / total_principal) * 100 if total_principal > 0 else 0.0

    irr_period = irr(cashflows)
    irr_val = (1 + irr_period) ** periods_per_year - 1 if not math.isnan(irr_period) else float('nan')
    irr_pct = irr_val * 100 if not math.isnan(irr_val) else float('nan')

    # 逐年汇总
    yearly_summary = _build_yearly_summary(
        period_details, num_periods, periods_per_year, total_asset
    )

    return {
        'total_asset': round(total_asset, 2),
        'total_principal': round(total_principal, 2),
        'total_return': round(total_return, 2),
        'total_return_pct': round(total_return_pct, 2),
        'total_commission': round(total_commission, 2),
        'irr': irr_val,
        'irr_pct': round(irr_pct, 2),
        'period_details': period_details,
        'yearly_summary': yearly_summary,
        'final_price': round(final_price, 4),
    }


# ==============================================================================
# 历史回测
# ==============================================================================

def backtest_history(
    prices: pd.Series,
    amounts: List[float],
    dates: List[datetime],
    commission_rate: float = 0.0003,
    min_commission: float = 5.0,
) -> Dict:
    """历史回测：使用真实历史前复权价格模拟定投。

    Args:
        prices: 前复权收盘价 Series，index=日期
        amounts: 每期投入金额列表
        dates: 定投日期列表
        commission_rate: 佣金费率
        min_commission: 最低佣金

    Returns:
        {
            'total_asset': 期末总资产,
            'total_principal': 总本金,
            'total_return': 累计收益,
            'total_return_pct': 累计收益率(%),
            'total_commission': 总佣金,
            'xirr': 年化XIRR(小数),
            'xirr_pct': 年化XIRR(%),
            'irr': 年化IRR(小数),
            'irr_pct': 年化IRR(%),
            'max_drawdown': 最大回撤(小数),
            'max_drawdown_pct': 最大回撤(%),
            'annualized_volatility': 年化波动率(小数),
            'sharpe': 夏普比率,
            'daily_values': 每日市值序列,
            'period_details': [...],
            'yearly_summary': [...],
        }
    """
    total_shares = 0
    total_principal = 0.0
    total_commission = 0.0
    total_remaining_cash = 0.0
    period_details = []
    cashflows = []
    cashflow_dates = []

    # 构建日期到价格的映射
    price_map = {}
    for idx, val in prices.items():
        d = idx if isinstance(idx, datetime) else pd.Timestamp(idx).to_pydatetime()
        price_map[d.strftime('%Y-%m-%d')] = val

    for i, (date, amount) in enumerate(zip(dates, amounts)):
        date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date
        if date_str not in price_map:
            print(f"[回测] 日期 {date_str} 无价格数据，跳过本期")
            continue

        price = price_map[date_str]
        comm = commission(amount, commission_rate, min_commission)
        net_amount = amount - comm
        shares = shares_buyable(net_amount, price)
        actual_cost = shares * price
        remaining = net_amount - actual_cost  # 取整未投的现金

        total_shares += shares
        total_principal += amount
        total_commission += comm
        total_remaining_cash += remaining

        period_details.append({
            'period': i + 1,
            'date': date_str,
            'amount': amount,
            'commission': round(comm, 2),
            'net_amount': round(net_amount, 2),
            'price': round(price, 4),
            'shares': shares,
            'cumulative_shares': total_shares,
            'remaining_cash': round(remaining, 2),
            'total_remaining_cash': round(total_remaining_cash, 2),
        })

        cashflows.append(-amount)
        cashflow_dates.append(
            date if isinstance(date, datetime) else datetime.strptime(date_str, '%Y-%m-%d')
        )

    if not period_details:
        raise ValueError("没有有效的定投记录（所有定投日均无价格数据）")

    # 期末资产（以最后一天的价格计算+剩余现金）
    final_date_str = list(price_map.keys())[-1]
    final_price = price_map[final_date_str]
    total_asset = total_shares * final_price + total_remaining_cash

    cashflows.append(total_asset)
    cashflow_dates.append(datetime.strptime(final_date_str, '%Y-%m-%d'))

    total_return = total_asset - total_principal
    total_return_pct = (total_return / total_principal) * 100 if total_principal > 0 else 0.0

    # XIRR
    xirr_val = xirr(cashflows, cashflow_dates)
    xirr_pct = xirr_val * 100 if not math.isnan(xirr_val) else float('nan')

    # IRR（等间隔回退，从日期中位数估算年期数）
    if len(cashflow_dates) >= 2:
        gaps = [abs((cashflow_dates[i+1] - cashflow_dates[i]).days) for i in range(len(cashflow_dates)-1)]
        median_gap = np.median(gaps) if gaps else 30
        periods_per_year_est = 365.25 / median_gap if median_gap > 0 else 12
    else:
        periods_per_year_est = 12
    irr_period = irr(cashflows)
    irr_val = (1 + irr_period) ** periods_per_year_est - 1 if not math.isnan(irr_period) else float('nan')
    irr_pct = irr_val * 100 if not math.isnan(irr_val) else float('nan')

    # 每日市值序列 + 收益率曲线
    daily_values = _build_daily_value_series(period_details, price_map, total_shares)
    return_curve = _build_return_curve(daily_values, period_details, price_map)

    # 风险指标（基于基金收益率曲线计算）
    fund_cum_ret = np.array(return_curve['fund_cum_return'])
    mdd = max_drawdown_from_returns(fund_cum_ret)

    fund_daily_ret = np.diff(fund_cum_ret + 1) / (fund_cum_ret[:-1] + 1) if len(fund_cum_ret) > 1 else np.array([0])
    ann_vol = annualized_volatility(fund_daily_ret)
    sharpe = sharpe_ratio(xirr_val if not math.isnan(xirr_val) else 0, ann_vol)

    # 逐年汇总
    yearly_summary = _build_yearly_summary_from_dates(period_details, price_map)

    return {
        'total_asset': round(total_asset, 2),
        'total_principal': round(total_principal, 2),
        'total_return': round(total_return, 2),
        'total_return_pct': round(total_return_pct, 2),
        'total_commission': round(total_commission, 2),
        'xirr': xirr_val,
        'xirr_pct': round(xirr_pct, 2),
        'irr': irr_val,
        'irr_pct': round(irr_pct, 2),
        'max_drawdown': mdd,
        'max_drawdown_pct': round(mdd * 100, 2),
        'annualized_volatility': round(ann_vol, 4),
        'sharpe': round(sharpe, 2),
        'final_price': round(final_price, 4),
        'daily_values': daily_values.to_dict('records'),
        'return_curve': return_curve,
        'period_details': period_details,
        'yearly_summary': yearly_summary,
    }


def _build_daily_value_series(period_details, price_map, total_shares) -> pd.DataFrame:
    """构建每日市值序列。"""
    if not period_details:
        return pd.DataFrame(columns=['date', 'value'])

    first_date = period_details[0]['date']
    dates = sorted(price_map.keys())
    start_idx = 0
    for i, d in enumerate(dates):
        if d >= first_date:
            start_idx = i
            break

    records = []
    for d in dates[start_idx:]:
        shares_at_date = 0
        cash_at_date = 0
        for pd_item in period_details:
            if pd_item['date'] <= d:
                shares_at_date += pd_item['shares']
                cash_at_date += pd_item.get('remaining_cash', 0)
        records.append({
            'date': d,
            'value': round(shares_at_date * price_map[d] + cash_at_date, 2),
        })
    return pd.DataFrame(records)


def _build_return_curve(daily_values, period_details, price_map):
    """构建收益率曲线：基金定投累计收益 vs ETF 买入持有累计收益。

    Returns:
        {
            'dates': [日期],
            'fund_cum_return': [基金累计收益率],  # (日市值 - 累计投入) / 累计投入
            'benchmark_cum_return': [ETF买入持有累计收益率],  # (当日价 - 起始价) / 起始价
        }
    """
    if daily_values.empty or not period_details:
        return {'dates': [], 'fund_cum_return': [], 'benchmark_cum_return': []}

    # 累计投入序列（按日对齐）
    dates = sorted(price_map.keys())
    first_date = period_details[0]['date']

    # 找到起始日对应的价格
    start_idx = 0
    for i, d in enumerate(dates):
        if d >= first_date:
            start_idx = i
            break
    benchmark_start_price = price_map.get(dates[start_idx], period_details[0]['price'])

    # 基准: 买入持有累计收益率 = (当日价 - 起始价) / 起始价
    benchmark_cum = []
    fund_cum = []
    result_dates = []
    p_idx = 0
    invested_so_far = 0
    shares_so_far = 0
    remaining_cash_so_far = 0

    for d in dates[start_idx:]:
        # 累计投入和份额（包括当天的定投��
        while p_idx < len(period_details) and period_details[p_idx]['date'] <= d:
            invested_so_far += period_details[p_idx]['amount']
            shares_so_far += period_details[p_idx]['shares']
            remaining_cash_so_far += period_details[p_idx].get('remaining_cash', 0)
            p_idx += 1

        price = price_map.get(d, 0)
        if price == 0:
            continue

        result_dates.append(d)
        fund_value = shares_so_far * price + remaining_cash_so_far
        fund_cum.append((fund_value - invested_so_far) / invested_so_far if invested_so_far > 0 else 0)
        benchmark_cum.append((price - benchmark_start_price) / benchmark_start_price)

    return {
        'dates': result_dates,
        'fund_cum_return': [round(v, 6) for v in fund_cum],
        'benchmark_cum_return': [round(v, 6) for v in benchmark_cum],
    }


def max_drawdown_from_returns(cumulative_returns: np.ndarray) -> float:
    """从累计收益率序列计算最大回撤。

    cumulative_returns 是累计收益率（如 0.1 = 10%），1 + r 得到净值曲线。
    """
    if len(cumulative_returns) < 2:
        return 0.0
    net_values = 1 + cumulative_returns
    peak = np.maximum.accumulate(net_values)
    drawdown = (net_values - peak) / peak
    return float(np.min(drawdown))


def _build_yearly_summary(period_details, num_periods, periods_per_year, total_asset):
    """从正向测算的期明细构建逐年汇总。"""
    yearly = []
    for year in range(1, (num_periods // periods_per_year) + 2):
        year_start = (year - 1) * periods_per_year
        year_end = min(year * periods_per_year, len(period_details))
        year_items = period_details[year_start:year_end]
        if not year_items:
            break

        year_amount = sum(it['amount'] for it in year_items)
        year_commission = sum(it['commission'] for it in year_items)
        year_end_shares = year_items[-1]['cumulative_shares']
        year_end_asset = round(year_end_shares * year_items[-1]['price'], 2)

        yearly.append({
            'year': year,
            'amount': round(year_amount, 2),
            'commission': round(year_commission, 2),
            'end_shares': year_end_shares,
            'end_asset': year_end_asset,
            'return': round(year_end_asset - year_amount, 2),
        })
    return yearly


def _build_yearly_summary_from_dates(period_details, price_map):
    """从回测的期明细构建逐年汇总。

    Args:
        period_details: 每期明细列表
        price_map: {日期字符串 → 前复权收盘价}
    """
    if not period_details:
        return []

    yearly = {}
    for item in period_details:
        year = int(item['date'][:4])
        if year not in yearly:
            yearly[year] = {'year': year, 'amount': 0, 'commission': 0, 'end_shares': 0}
        yearly[year]['amount'] += item['amount']
        yearly[year]['commission'] += item['commission']
        yearly[year]['end_shares'] = item['cumulative_shares']

    # 找每年最后一个有价格的交易日
    years = sorted(yearly.keys())
    year_end_prices = {}
    for y in years:
        year_dates = sorted([d for d in price_map if d[:4] == str(y)])
        if year_dates:
            year_end_prices[y] = price_map[year_dates[-1]]
        elif y - 1 in year_end_prices:
            year_end_prices[y] = year_end_prices[y - 1]
        else:
            year_end_prices[y] = 0

    result = []
    prev_asset = 0
    prev_shares = 0
    for y in years:
        row = yearly[y]
        row['amount'] = round(row['amount'], 2)
        row['commission'] = round(row['commission'], 2)
        # 年末资产 = 年末份额 × 年末价格
        row['end_asset'] = round(row['end_shares'] * year_end_prices.get(y, 0), 2)
        # 当年收益 = (年末资产 - 上年末资产) - 当年投入
        row['year_return'] = round(row['end_asset'] - prev_asset - row['amount'], 2)
        prev_asset = row['end_asset']
        prev_shares = row['end_shares']
        result.append(row)

    return result


# ==============================================================================
# 目标反推
# ==============================================================================

def solve_for_amount(
    target_asset: float,
    duration_years: int,
    expected_annual_return: float,
    periods_per_year: int = 12,
    commission_rate: float = 0.0003,
    min_commission: float = 5.0,
) -> Dict:
    """目标反推-每期金额：已知目标资产、期限、预期年化，反推每期需要投入多少。

    使用年金终值公式 PMT 求解，再考虑佣金折损。

    Args:
        target_asset: 目标资产（元）
        duration_years: 期限（年）
        expected_annual_return: 预期年化（%）
        periods_per_year: 每年定投次数
        commission_rate: 佣金费率
        min_commission: 最低佣金

    Returns:
        {
            'amount_per_period': 每期需要投入金额,
            'effective_amount': 扣除佣金后每期净投入,
            'commission_per_period': 每期佣金,
            'total_principal': 总投入本金,
            'total_commission': 总佣金,
            'note': 说明文字,
        }
    """
    total_periods = duration_years * periods_per_year
    period_rate = (1 + expected_annual_return / 100) ** (1 / periods_per_year) - 1

    # PMT 公式: A = FV * r / ((1+r)^n - 1)
    if period_rate <= 0:
        raw_amount = target_asset / total_periods
    else:
        raw_amount = target_asset * period_rate / ((1 + period_rate) ** total_periods - 1)

    # 迭代修正佣金影响（佣金会减少实际投入，需要多投才能达成目标）
    amount = raw_amount
    for _ in range(20):
        comm = commission(amount, commission_rate, min_commission)
        net = amount - comm
        if net >= raw_amount:
            break
        # 缺口通过增加投入弥补
        amount = raw_amount + comm

    final_comm = commission(amount, commission_rate, min_commission)
    net_amount = amount - final_comm
    total_principal = amount * total_periods
    total_commission = final_comm * total_periods

    return {
        'amount_per_period': round(amount, 2),
        'effective_amount': round(net_amount, 2),
        'commission_per_period': round(final_comm, 2),
        'total_principal': round(total_principal, 2),
        'total_commission': round(total_commission, 2),
        'note': f'每月定投 ¥{amount:,.2f}，扣除佣金后净投入 ¥{net_amount:,.2f}',
    }


def solve_for_return(
    target_asset: float,
    amount_per_period: float,
    duration_years: int,
    periods_per_year: int = 12,
    commission_rate: float = 0.0003,
    min_commission: float = 5.0,
) -> Dict:
    """目标反推-所需年化：已知目标资产、每期金额、期限，反推需要多高的年化。

    使用牛顿迭代法求解 r，考虑佣金折损。

    Returns:
        {
            'required_return': 所需年化收益率(%),
            'note': 说明文字,
        }
    """
    total_periods = duration_years * periods_per_year
    comm = commission(amount_per_period, commission_rate, min_commission)
    net_amount = amount_per_period - comm

    def fv_diff(annual_rate):
        """年化 r 下的期末资产与目标的差值。"""
        period_rate = (1 + annual_rate) ** (1 / periods_per_year) - 1
        if period_rate <= 0:
            fv = net_amount * total_periods
        else:
            fv = net_amount * ((1 + period_rate) ** total_periods - 1) / period_rate
        return fv - target_asset

    # 区间搜索
    lo, hi = 0.001, 1.0  # 0.1% ~ 100%
    flo = fv_diff(lo)
    fhi = fv_diff(hi)

    if flo * fhi > 0:
        if flo > 0:
            return {
                'required_return': round(lo * 100, 2),
                'note': f'所需年化极低 (<0.1%)，当前条件远超目标',
            }
        else:
            return {
                'required_return': float('nan'),
                'note': f'所需年化超过100%，给定条件下无法达成目标',
            }

    try:
        rate = newton(fv_diff, 0.08, maxiter=100, tol=1e-8)
    except RuntimeError:
        # 二分法
        for _ in range(100):
            mid = (lo + hi) / 2
            fmid = fv_diff(mid)
            if abs(fmid) < 1.0:
                rate = mid
                break
            if flo * fmid < 0:
                hi, fhi = mid, fmid
            else:
                lo, flo = mid, fmid
        else:
            rate = (lo + hi) / 2

    return {
        'required_return': round(rate * 100, 2),
        'note': f'需要年化收益率 {rate*100:.2f}%，即每年 {((1+rate)**periods_per_year-1)*100:.2f}%',
    }


def solve_for_duration(
    target_asset: float,
    amount_per_period: float,
    expected_annual_return: float,
    periods_per_year: int = 12,
    commission_rate: float = 0.0003,
    min_commission: float = 5.0,
) -> Dict:
    """反推所需期数，先年金公式估算，再迭代 forward_projection 校准佣金/份额取整误差。"""
    comm = commission(amount_per_period, commission_rate, min_commission)
    net_amount = amount_per_period - comm
    period_rate = (1 + expected_annual_return / 100) ** (1 / periods_per_year) - 1

    if period_rate <= 0:
        est_periods = int(target_asset / net_amount)
    else:
        est_periods = int(math.ceil(
            math.log(target_asset * period_rate / net_amount + 1) / math.log(1 + period_rate)
        ))

    # 迭代校准（最多加 100 期）
    for offset in range(100):
        periods = est_periods + offset
        fwd = forward_projection(
            initial_price=1.0, amount_per_period=amount_per_period,
            num_periods=periods, periods_per_year=periods_per_year,
            expected_annual_return=expected_annual_return,
            commission_rate=commission_rate, min_commission=min_commission,
        )
        if fwd['total_asset'] >= target_asset:
            years = periods / periods_per_year
            return {
                'required_periods': periods,
                'required_months': round(years * 12, 1),
                'required_years': round(years, 1),
                'note': f'需要约 {years:.1f} 年（{periods} 期）达成 ¥{target_asset:,.0f} 目标',
            }

    years = est_periods / periods_per_year
    return {
        'required_periods': est_periods,
        'required_months': round(years * 12, 1),
        'required_years': round(years, 1),
        'note': f'需要约 {years:.1f} 年（{est_periods} 期）达成 ¥{target_asset:,.0f} 目标',
    }


# ==============================================================================
# 多情景对比
# ==============================================================================

def scenario_compare(
    initial_price: float,
    amount_per_period: float,
    num_periods: int,
    periods_per_year: int,
    return_scenarios: List[float],
    commission_rate: float = 0.0003,
    min_commission: float = 5.0,
) -> pd.DataFrame:
    """多情景对比：不同预期年化下的定投结果对比。

    Args:
        return_scenarios: 预期年化列表，如 [4, 6, 8, 10]

    Returns:
        DataFrame，列：预期年化 / 期末资产 / 总收益 / 收益倍数 / 标签
    """
    results = []
    base_return = return_scenarios[0] if return_scenarios else 8.0
    base_asset = None

    for er in return_scenarios:
        result = forward_projection(
            initial_price=initial_price,
            amount_per_period=amount_per_period,
            num_periods=num_periods,
            periods_per_year=periods_per_year,
            expected_annual_return=er,
            commission_rate=commission_rate,
            min_commission=min_commission,
        )
        if base_asset is None:
            base_asset = result['total_asset']

        label = '保守' if er <= 5 else ('中性' if er <= 8 else ('乐观' if er <= 12 else '激进'))
        results.append({
            'expected_return': er,
            'total_asset': result['total_asset'],
            'total_return': result['total_return'],
            'total_return_pct': result['total_return_pct'],
            'return_multiple': round(result['total_asset'] / base_asset, 2) if base_asset else 1.0,
            'label': label,
        })

    return pd.DataFrame(results)
