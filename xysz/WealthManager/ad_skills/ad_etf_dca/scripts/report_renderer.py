# -*- coding: utf-8 -*-
"""
报告渲染模块 - 数据注入 + Jinja2 模板渲染

读取 assets/templates/report_template.html 模板，
将计算结果注入模板变量，输出最终 HTML 文件。
"""

import os
import math
from typing import Dict, Optional, Any
from datetime import datetime

from jinja2 import Environment, FileSystemLoader


_TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    'assets', 'templates'
)


def get_template_env() -> Environment:
    """获取 Jinja2 模板环境。"""
    return Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=False,
    )


def _build_commission_warning(
    amount_per_period: float,
    commission_rate: float,
    min_commission: float,
) -> Optional[Dict[str, str]]:
    """构建最低佣金警示信息。

    当单笔投入达不到阈值时触发（场内每笔最低5元佣金）。
    """
    if amount_per_period <= 0 or commission_rate <= 0:
        return None

    threshold = min_commission / commission_rate  # 突破最低佣金的阈值
    actual_pct = (min_commission / amount_per_period) * 100

    if amount_per_period < threshold:
        return {
            'title': (
                f'每期投入 ¥{amount_per_period:,.0f} 触发最低佣金 {min_commission} 元。'
                f'默认佣金费率 {commission_rate*100:.2f}%，单笔最低 ¥{min_commission}。'
            ),
            'detail': '',
            'suggestion': '',
        }
    return None


def _build_asset_curve(result: dict, is_backtest: bool) -> dict:
    """构建资产曲线：市值 / 本金 / 盈亏（所有模式通用）。"""
    if is_backtest and 'daily_values' in result:
        dvs = result['daily_values']
        dates = [d['date'] for d in dvs]
        vals = [d['value'] for d in dvs]
        pd_list = result.get('period_details', [])
        invested = 0; pi = 0
        principals = []; profits = []
        for i, d in enumerate(dates):
            while pi < len(pd_list) and pd_list[pi].get('date', pd_list[pi].get('period', '')) <= d:
                invested += pd_list[pi]['amount']; pi += 1
            principals.append(invested)
            profits.append(vals[i] - invested)
        return {'dates': dates, 'vals': vals, 'principals': principals, 'profits': profits}

    pd_list = result.get('period_details', [])
    if not pd_list:
        ta = result.get('total_asset', 0); tp = result.get('total_principal', 0)
        if ta > 0:
            return {'dates': ['开始', '结束'], 'vals': [0, ta], 'principals': [0, tp], 'profits': [0, ta - tp]}
        return {'dates': [], 'vals': [], 'principals': [], 'profits': []}

    dates = [p.get('date', p.get('period', str(i))) for i, p in enumerate(pd_list)]
    invested = 0; vals = []; principals = []; profits = []
    for p in pd_list:
        invested += p['amount']
        asset = p['cumulative_shares'] * p['price'] + p.get('total_remaining_cash', 0)
        vals.append(asset); principals.append(invested)
        profits.append(asset - invested)
    return {'dates': dates, 'vals': vals, 'principals': principals, 'profits': profits}


def build_context(
    mode: str,
    symbol: str,
    symbol_name: str,
    amount_per_period: float,
    frequency: str,
    duration_years: Optional[int],
    start_date: Optional[str],
    end_date: Optional[str],
    result: Dict[str, Any],
    scenario_df: Any = None,
    commission_rate: float = 0.0003,
    min_commission: float = 5.0,
) -> Dict[str, Any]:
    """从计算结果构建模板上下文。

    Args:
        mode: forward / backtest / target_amount / target_return / target_duration
        symbol: ETF 代码
        symbol_name: ETF 名称
        amount_per_period: 每期金额
        frequency: 定投频率
        duration_years: 定投年限
        start_date: 起始日期
        end_date: 结束日期
        result: 计算引擎返回的 dict
        scenario_df: 多情景对比 DataFrame
        commission_rate: 佣金费率
        min_commission: 最低佣金

    Returns:
        Jinja2 模板变量 dict
    """
    freq_label = {
        'weekly': '每周', 'biweekly': '双周',
        'monthly': '每月', 'quarterly': '每季',
        'day': '每日',
    }.get(frequency, frequency)

    mode_label = {
        'forward': '正向测算',
        'backtest': '历史回测',
        'target_amount': '目标反推 · 每期金额',
        'target_return': '目标反推 · 所需年化',
        'target_duration': '目标反推 · 所需期限',
    }.get(mode, mode)

    # 日期范围
    if start_date and end_date:
        date_range = f"{start_date} ~ {end_date}"
    elif duration_years:
        date_range = f"从现在起 {duration_years} 年（{freq_label}定投）"
    else:
        date_range = "—"

    # 指标卡
    is_backtest = mode == 'backtest'
    rate_type = result.get('rate_type', 'XIRR' if is_backtest else 'IRR')
    rate_pct = result.get('xirr_pct' if is_backtest else 'irr_pct', 0)
    if isinstance(rate_pct, float) and (math.isnan(rate_pct) or math.isinf(rate_pct)):
        rate_pct = 0.0

    total_principal = result.get('total_principal', 0)
    total_asset = result.get('total_asset', 0)
    period_count = len(result.get('period_details', []))
    total_commission = result.get('total_commission', 0)
    commission_pct = (total_commission / total_principal * 100) if total_principal > 0 else 0

    indicator_cards = {
        'total_asset': result.get('total_asset', 0),
        'total_principal': total_principal,
        'total_return': result.get('total_return', 0),
        'total_return_pct': result.get('total_return_pct', 0),
        'rate_type': rate_type,
        'rate_pct': rate_pct,
    }

    # 图表数据：收益率曲线（基金定投 vs ETF买入持有）
    chart_data = None
    if is_backtest and 'return_curve' in result:
        rc = result['return_curve']
        chart_data = {
            'dates': rc['dates'],
            'fund_cum_return': [round(v * 100, 2) for v in rc['fund_cum_return']],
            'benchmark_cum_return': [round(v * 100, 2) for v in rc['benchmark_cum_return']],
        }

    # 逐年汇总
    yearly_summary = result.get('yearly_summary', [])
    # 多情景对比
    scenario_data = None
    if scenario_df is not None and not scenario_df.empty:
        scenario_data = {
            'scenarios': [f"{r['expected_return']}" for _, r in scenario_df.iterrows()],
            'assets': [r['total_asset'] for _, r in scenario_df.iterrows()],
            'returns': [r['total_return'] for _, r in scenario_df.iterrows()],
        }

    # 风险指标（仅回测模式）
    risk_data = None
    if is_backtest:
        risk_data = {
            'max_drawdown_pct': result.get('max_drawdown_pct', 0),
            'annualized_volatility': result.get('annualized_volatility', 0),
            'sharpe': result.get('sharpe', None),
        }

    # 资产曲线（所有模式）：市值 / 本金 / 盈亏
    asset_curve = _build_asset_curve(result, is_backtest)

    # 佣金警示
    commission_warning = _build_commission_warning(
        amount_per_period, commission_rate, min_commission
    )

    # 报告标题（按模式区分）
    title_map = {
        'forward': f'{symbol_name} 定投测算 — {mode_label}',
        'backtest': f'{symbol_name} 定投回测 — {mode_label}',
        'target_amount': f'目标反推·每期金额 — {symbol_name}',
        'target_return': f'目标反推·所需年化 — {symbol_name}',
        'target_duration': f'目标反推·所需期限 — {symbol_name}',
    }
    report_title = title_map.get(mode, f'{symbol_name} 定投分析 — {mode_label}')

    # 输入参数条件（按模式去重：不显示待求解的变量）
    params = {'标的': f'{symbol_name}（{symbol}）'}
    if mode not in ('target_amount',):
        params['每期金额'] = f'¥{amount_per_period:,.0f}'
    params['定投频率'] = freq_label

    if mode == 'backtest':
        params['时间'] = f'{start_date} ~ {end_date}'
    elif mode != 'target_duration' and duration_years:
        params['期限'] = f'{duration_years} 年'
    if mode != 'target_return' and result.get('expected_return') is not None:
        params['预期年化'] = f'{result["expected_return"]}%'
    if result.get('target_asset') is not None:
        params['目标资产'] = f'¥{result["target_asset"]:,.0f}'

    return {
        'title': report_title,
        'mode': mode,
        'params': params,
        'symbol': symbol,
        'symbol_name': symbol_name,
        'mode_label': mode_label,
        'amount_per_period': amount_per_period,
        'total_principal': total_principal,
        'total_asset': total_asset,
        'period_count': period_count,
        'frequency_label': freq_label,
        'date_range': date_range,
        'indicator_cards': indicator_cards,
        'chart_data': chart_data,
        'asset_curve': asset_curve,
        'scenario_data': scenario_data,
        'yearly_summary': yearly_summary,
        'risk_data': risk_data,
        'target_answer': result.get('target_answer'),
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }


def render_report(context: Dict[str, Any], output_path: str) -> str:
    """渲染报告并写出到文件。

    Args:
        context: build_context 返回的模板变量
        output_path: 输出 HTML 文件路径

    Returns:
        输出文件的绝对路径
    """
    env = get_template_env()
    template = env.get_template('report_template.html')
    html = template.render(**context)

    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"[ReportRenderer] 报告生成完成: {output_path}")
    return output_path
