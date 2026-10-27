# -*- coding: utf-8 -*-
"""
ETF 定投计算器 - CLI 入口

支持五种模式：
  forward       正向测算（基于预期年化模拟）
  backtest      历史回测（真实 K 线数据）
  target_amount 目标反推·每期金额
  target_return 目标反推·所需年化
  target_duration 目标反推·所需期限

输出：亮色主题 HTML 报告 + 终端文字摘要
"""

import os
import sys
import math
import argparse
from datetime import datetime
from dateutil.relativedelta import relativedelta

# 将 scripts 目录加入 path，方便导入同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_provider import DataProvider
from etf_calculator import (
    forward_projection,
    backtest_history,
    solve_for_amount,
    solve_for_return,
    solve_for_duration,
    scenario_compare,
)
from report_renderer import build_context, render_report


FREQ_MAP = {
    'weekly': 52,
    'biweekly': 26,
    'monthly': 12,
    'quarterly': 4,
}

FREQ_LABEL = {
    'weekly': '周',
    'biweekly': '双周',
    'monthly': '月',
    'quarterly': '季',
}

TRADING_DAYS_PER_YEAR = 252


def _resolve_frequency(args):
    """根据频率参数计算 期数/年 和 显示标签。"""
    if args.frequency == 'day':
        if args.interval <= 0:
            print("错误: frequency=day 需要 --interval 参数 (>0)")
            sys.exit(1)
        return TRADING_DAYS_PER_YEAR // args.interval, f"每{args.interval}日"
    return FREQ_MAP[args.frequency], FREQ_LABEL[args.frequency]


def _get_etf_name(dp: DataProvider, symbol: str) -> str:
    """通过 AmazingData 获取 ETF 中文名称。"""
    return dp.get_etf_name(symbol)


def run_forward(args, dp: DataProvider):
    """正向测算模式。"""
    if not args.duration:
        print("错误: forward 模式需要 --duration 参数")
        sys.exit(1)
    start_dt = datetime.now()
    end_dt = start_dt + relativedelta(years=args.duration)
    start_date = start_dt.strftime('%Y-%m-%d')
    end_date_str = end_dt.strftime('%Y-%m-%d')

    # 获取当前价格作为起点
    begin_int = int(start_dt.strftime('%Y%m%d')) - 100  # 取最近100天
    end_int = int(start_dt.strftime('%Y%m%d'))
    price_series = dp.get_daily_close_series(args.symbol, begin_int, end_int)
    if price_series is None or price_series.empty:
        print(f"错误: 无法获取 {args.symbol} 的价格数据")
        sys.exit(1)
    initial_price = float(price_series.iloc[-1])

    periods_per_year, freq_display = _resolve_frequency(args)
    num_periods = args.duration * periods_per_year

    print(f"\n{'='*60}")
    print(f"  正向测算: {args.symbol} {freq_display}定投 {args.duration}年")
    print(f"  当前价格: ¥{initial_price:.4f}  每期投入: ¥{args.amount:,.0f}")
    print(f"  预期年化: {args.expected_return}%")
    print(f"{'='*60}\n")

    result = forward_projection(
        initial_price=initial_price,
        amount_per_period=args.amount,
        num_periods=num_periods,
        periods_per_year=periods_per_year,
        expected_annual_return=args.expected_return,
        commission_rate=args.commission_rate,
        min_commission=args.min_commission,
    )

    _print_summary(result, 'forward')

    # 多情景对比
    scenario_list = [float(x.strip()) for x in args.scenarios.split(',')]
    scenario_df = scenario_compare(
        initial_price=initial_price,
        amount_per_period=args.amount,
        num_periods=num_periods,
        periods_per_year=periods_per_year,
        return_scenarios=scenario_list,
        commission_rate=args.commission_rate,
        min_commission=args.min_commission,
    )

    # 生成报告
    context = build_context(
        mode='forward',
        symbol=args.symbol,
        symbol_name=_get_etf_name(dp, args.symbol),
        amount_per_period=args.amount,
        frequency=args.frequency,
        duration_years=args.duration,
        start_date=start_date,
        end_date=end_date_str,
        result=result,
        scenario_df=scenario_df,
        commission_rate=args.commission_rate,
        min_commission=args.min_commission,
    )
    # forward: 注入输入参数供报告显示
    result['expected_return'] = args.expected_return
    output_path = render_report(context, args.output)
    return output_path


def run_backtest(args, dp: DataProvider):
    """历史回测模式。"""
    begin_int = int(args.start)
    end_int = int(args.end) if args.end else int(datetime.now().strftime('%Y%m%d'))

    start_str = f"{str(args.start)[:4]}-{str(args.start)[4:6]}-{str(args.start)[6:8]}"
    end_str = f"{str(end_int)[:4]}-{str(end_int)[4:6]}-{str(end_int)[6:8]}"

    # 获取历史价格
    price_series = dp.get_daily_close_series(args.symbol, begin_int, end_int)
    if price_series is None or price_series.empty:
        print(f"错误: {args.symbol} 在 {args.start}-{end_int} 无价格数据")
        sys.exit(1)

    # 生成定投日期
    interval = args.interval if args.frequency == 'day' else 0
    dca_dates = dp.generate_dca_dates(start_str, end_str, args.frequency, interval_days=interval)

    if args.frequency == 'day':
        freq_display = f"每{args.interval}日"
    else:
        freq_display = FREQ_LABEL[args.frequency]

    print(f"\n{'='*60}")
    print(f"  历史回测: {args.symbol} {freq_display}定投")
    print(f"  时间: {args.start} ~ {end_int}")
    print(f"  每期投入: ¥{args.amount:,.0f}  共 {len(dca_dates)} 期")
    print(f"{'='*60}\n")

    if len(dca_dates) < 2:
        print("错误: 定投期数不足 (需要至少 2 期)")
        sys.exit(1)

    amounts = [args.amount] * len(dca_dates)
    dates_dt = [datetime.strptime(d, '%Y-%m-%d') for d in dca_dates]

    result = backtest_history(
        prices=price_series,
        amounts=amounts,
        dates=dates_dt,
        commission_rate=args.commission_rate,
        min_commission=args.min_commission,
    )

    _print_summary(result, 'backtest')

    # 生成报告
    context = build_context(
        mode='backtest',
        symbol=args.symbol,
        symbol_name=_get_etf_name(dp, args.symbol),
        amount_per_period=args.amount,
        frequency=args.frequency,
        duration_years=None,
        start_date=start_str,
        end_date=end_str,
        result=result,
        scenario_df=None,
        commission_rate=args.commission_rate,
        min_commission=args.min_commission,
    )
    output_path = render_report(context, args.output)
    return output_path


def run_target_amount(args, dp: DataProvider):
    """目标反推·每期金额。"""
    if not args.target or not args.duration:
        print("错误: target_amount 模式需要 --target 和 --duration")
        sys.exit(1)

    periods_per_year, freq_display = _resolve_frequency(args)

    print(f"\n{'='*60}")
    print(f"  目标反推·每期金额")
    print(f"  目标资产: ¥{args.target:,.0f}")
    print(f"  期限: {args.duration}年  预期年化: {args.expected_return}%")
    print(f"  定投频率: {FREQ_LABEL[args.frequency]}")
    print(f"{'='*60}\n")

    result = solve_for_amount(
        target_asset=args.target,
        duration_years=args.duration,
        expected_annual_return=args.expected_return,
        periods_per_year=periods_per_year,
        commission_rate=args.commission_rate,
        min_commission=args.min_commission,
    )

    print(f"  每期需要投入: ¥{result['amount_per_period']:,.2f}")
    print(f"  其中佣金: ¥{result['commission_per_period']:,.2f}")
    print(f"  净投入: ¥{result['effective_amount']:,.2f}")
    print(f"  总计投入本金: ¥{result['total_principal']:,.2f}")
    print(f"  总计佣金: ¥{result['total_commission']:,.2f}")

    # 获取当前价格，运行正向测算取期明细（用于画资产曲线）
    now_int = int(datetime.now().strftime('%Y%m%d'))
    price_series = dp.get_daily_close_series(args.symbol, now_int - 100, now_int)
    initial_price = float(price_series.iloc[-1]) if price_series is not None and not price_series.empty else 1.0
    num_periods = args.duration * periods_per_year
    fwd = forward_projection(
        initial_price=initial_price,
        amount_per_period=result['amount_per_period'],
        num_periods=num_periods,
        periods_per_year=periods_per_year,
        expected_annual_return=args.expected_return,
        commission_rate=args.commission_rate,
        min_commission=args.min_commission,
    )

    context = build_context(
        mode='target_amount',
        symbol=args.symbol,
        symbol_name=_get_etf_name(dp, args.symbol),
        amount_per_period=result['amount_per_period'],
        frequency=args.frequency,
        duration_years=args.duration,
        start_date=None,
        end_date=None,
        result={
            'total_asset': fwd['total_asset'],
            'total_principal': result['total_principal'],
            'total_return': fwd['total_asset'] - result['total_principal'],
            'total_return_pct': round((fwd['total_asset'] - result['total_principal']) / result['total_principal'] * 100, 2),
            'total_commission': result['total_commission'],
            'irr_pct': args.expected_return,
            'rate_type': '预期年化',
            'yearly_summary': [],
            'period_details': fwd.get('period_details', []),
            'target_answer': {
                'title': '每期金额',
                'value': f'¥{result["amount_per_period"]:,.0f} / 期',
                'desc': f'每月 ¥{result["amount_per_period"]:,.0f} 定投 {args.duration} 年，预期可达 ¥{fwd["total_asset"]:,.0f}'
            },
            'expected_return': args.expected_return,
            'target_asset': args.target,
        },
        commission_rate=args.commission_rate,
        min_commission=args.min_commission,
    )
    output_path = render_report(context, args.output)
    return output_path


def run_target_return(args, dp: DataProvider):
    """目标反推·所需年化。"""
    if not args.target or not args.duration:
        print("错误: target_return 模式需要 --target 和 --duration")
        sys.exit(1)

    periods_per_year, freq_display = _resolve_frequency(args)

    print(f"\n{'='*60}")
    print(f"  目标反推·所需年化")
    print(f"  目标资产: ¥{args.target:,.0f}")
    print(f"  每期投入: ¥{args.amount:,.0f}  期限: {args.duration}年")
    print(f"{'='*60}\n")

    result = solve_for_return(
        target_asset=args.target,
        amount_per_period=args.amount,
        duration_years=args.duration,
        periods_per_year=periods_per_year,
        commission_rate=args.commission_rate,
        min_commission=args.min_commission,
    )

    if math.isnan(result['required_return']):
        print(f"  {result['note']}")
        sys.exit(1)

    print(f"  所需年化收益率: {result['required_return']:.2f}%")
    print(f"  {result['note']}")

    # 获取当前价，跑正向测算取期明细
    now_int = int(datetime.now().strftime('%Y%m%d'))
    price_series = dp.get_daily_close_series(args.symbol, now_int - 100, now_int)
    initial_price = float(price_series.iloc[-1]) if price_series is not None and not price_series.empty else 1.0
    num_periods = args.duration * periods_per_year
    fwd = forward_projection(
        initial_price=initial_price,
        amount_per_period=args.amount,
        num_periods=num_periods,
        periods_per_year=periods_per_year,
        expected_annual_return=result['required_return'],
        commission_rate=args.commission_rate,
        min_commission=args.min_commission,
    )

    context = build_context(
        mode='target_return',
        symbol=args.symbol,
        symbol_name=_get_etf_name(dp, args.symbol),
        amount_per_period=args.amount,
        frequency=args.frequency,
        duration_years=args.duration,
        start_date=None,
        end_date=None,
        result={
            'total_asset': fwd['total_asset'],
            'total_principal': fwd['total_principal'],
            'total_return': fwd['total_asset'] - fwd['total_principal'],
            'total_return_pct': round((fwd['total_asset'] - fwd['total_principal']) / fwd['total_principal'] * 100, 2),
            'total_commission': 0,
            'irr_pct': result['required_return'],
            'rate_type': '所需年化',
            'yearly_summary': [],
            'period_details': fwd.get('period_details', []),
            'target_answer': {
                'title': '所需年化',
                'value': f'{result["required_return"]:.2f}%',
                'desc': f'每月 ¥{args.amount:,.0f} 定投 {args.duration} 年，需年化 {result["required_return"]:.2f}% 才能达到 ¥{args.target:,.0f}'
            },
            'expected_return': result['required_return'],
            'target_asset': args.target,
        },
        commission_rate=args.commission_rate,
        min_commission=args.min_commission,
    )
    output_path = render_report(context, args.output)
    return output_path


def run_target_duration(args, dp: DataProvider):
    """目标反推·期限。"""
    if not args.target:
        print("错误: target_duration 模式需要 --target")
        sys.exit(1)

    periods_per_year, freq_display = _resolve_frequency(args)

    print(f"\n{'='*60}")
    print(f"  目标反推·所需期限")
    print(f"  目标资产: ¥{args.target:,.0f}")
    print(f"  每期投入: ¥{args.amount:,.0f}  预期年化: {args.expected_return}%")
    print(f"{'='*60}\n")

    result = solve_for_duration(
        target_asset=args.target,
        amount_per_period=args.amount,
        expected_annual_return=args.expected_return,
        periods_per_year=periods_per_year,
        commission_rate=args.commission_rate,
        min_commission=args.min_commission,
    )

    total_periods = result['required_periods']

    # 获取当前价，用真实价格迭代校准（份额取整差异）
    now_int = int(datetime.now().strftime('%Y%m%d'))
    price_series = dp.get_daily_close_series(args.symbol, now_int - 100, now_int)
    initial_price = float(price_series.iloc[-1]) if price_series is not None and not price_series.empty else 1.0

    fwd = None
    for offset in range(50):
        prev_fwd = fwd
        fwd = forward_projection(
            initial_price=initial_price,
            amount_per_period=args.amount,
            num_periods=total_periods + offset,
            periods_per_year=periods_per_year,
            expected_annual_return=args.expected_return,
            commission_rate=args.commission_rate,
            min_commission=args.min_commission,
        )
        if fwd['total_asset'] >= args.target:
            total_periods += offset
            break

    print(f"  所需期数: {total_periods} 期（年金估算 {result['required_periods']} 期，经份额取整校准）")
    print(f"  约合: {total_periods / periods_per_year:.1f} 年")

    context = build_context(
        mode='target_duration',
        symbol=args.symbol,
        symbol_name=_get_etf_name(dp, args.symbol),
        amount_per_period=args.amount,
        frequency=args.frequency,
        duration_years=round(total_periods / periods_per_year, 2),
        start_date=None,
        end_date=None,
        result={
            'total_asset': fwd['total_asset'],
            'total_principal': fwd['total_principal'],
            'total_return': fwd['total_asset'] - fwd['total_principal'],
            'total_return_pct': round((fwd['total_asset'] - fwd['total_principal']) / fwd['total_principal'] * 100, 2),
            'total_commission': 0,
            'irr_pct': args.expected_return,
            'rate_type': '预期年化',
            'yearly_summary': [],
            'period_details': fwd.get('period_details', []),
            'target_answer': {
                'title': '所需期限',
                'value': f'{total_periods / periods_per_year:.2f} 年',
                'desc': f'每月 ¥{args.amount:,.0f} 定投、预期年化 {args.expected_return}%，约 {total_periods / periods_per_year:.2f} 年（{total_periods} 期）可达 ¥{args.target:,.0f}'
            },
            'expected_return': args.expected_return,
            'target_asset': args.target,
        },
        commission_rate=args.commission_rate,
        min_commission=args.min_commission,
    )
    output_path = render_report(context, args.output)
    return output_path


def _print_summary(result: dict, mode: str):
    """打印终端文字摘要。"""
    rate_label = 'XIRR' if mode == 'backtest' else 'IRR'
    rate_pct = result.get('xirr_pct' if mode == 'backtest' else 'irr_pct', 0)
    rate_pct = rate_pct if not (isinstance(rate_pct, float) and (math.isnan(rate_pct) or math.isinf(rate_pct))) else 0.0

    print(f"  ┌{'─'*50}┐")
    print(f"  │ {'期末总资产:':<16} ¥{result['total_asset']:>14,.2f}  │")
    print(f"  │ {'总投入本金:':<16} ¥{result['total_principal']:>14,.2f}  │")
    return_str = f"{'+' if result['total_return'] >= 0 else ''}{result['total_return']:,.2f}"
    print(f"  │ {'累计收益:':<16} ¥{return_str:>14}  │")
    print(f"  │ {'累计收益率:':<16} {result['total_return_pct']:>13.2f}%  │")
    print(f"  │ {f'真实年化({rate_label}):':<16} {rate_pct:>13.2f}%  │")
    print(f"  └{'─'*50}┘")

    if mode == 'backtest':
        mdd = result.get('max_drawdown_pct', 0)
        vol = result.get('annualized_volatility', 0)
        sharpe = result.get('sharpe', None)
        print(f"  最大回撤: {mdd:.2f}%")
        print(f"  年化波动率: {vol*100:.2f}%")
        if sharpe is not None:
            print(f"  夏普比率: {sharpe:.2f}")

    total_principal = result.get('total_principal', 1)
    print()


def main():
    parser = argparse.ArgumentParser(
        description='场内ETF定投计算器 - 中国银河证券星耀数智',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 正向测算
  python run_analysis.py --mode forward --symbol 510***.SH --amount 2000 --frequency monthly --duration 5

  # 历史回测
  python run_analysis.py --mode backtest --symbol 510***.SH --amount 2000 --frequency monthly --start 20200101

  # 目标反推
  python run_analysis.py --mode target_amount --symbol 510***.SH --target 1000000 --duration 10
        """
    )

    parser.add_argument('--mode', type=str, default='forward',
                        choices=['forward', 'backtest', 'target_amount', 'target_return', 'target_duration'],
                        help='运行模式 (default: forward)')
    parser.add_argument('--symbol', type=str, default='510***.SH',
                        help='ETF代码，如 510***.SH')
    parser.add_argument('--amount', type=float, default=2000,
                        help='每期定投金额/元 (default: 2000)')
    parser.add_argument('--frequency', type=str, default='monthly',
                        choices=['weekly', 'biweekly', 'monthly', 'quarterly', 'day'],
                        help='定投频率 (default: monthly)')
    parser.add_argument('--interval', type=int, default=0,
                        help='当 frequency=day 时，每隔多少日 (如 5=每5日)')
    parser.add_argument('--duration', type=int, default=None,
                        help='定投期限/年 (forward/target 模式必填)')
    parser.add_argument('--start', type=str, default=None,
                        help='回测起始日期 YYYYMMDD (backtest 模式)')
    parser.add_argument('--end', type=str, default=None,
                        help='回测结束日期 YYYYMMDD (默认今天)')
    parser.add_argument('--target', type=float, default=None,
                        help='目标资产/元 (target 模式必填)')
    parser.add_argument('--expected_return', type=float, default=8.0,
                        help='预期年化收益率%% (default: 8.0)')
    parser.add_argument('--commission_rate', type=float, default=0.0003,
                        help='佣金费率 (default: 0.0003 即万3)')
    parser.add_argument('--min_commission', type=float, default=5.0,
                        help='最低佣金/元 (default: 5)')
    parser.add_argument('--scenarios', type=str, default='4,6,8,10',
                        help='多情景对比年化值，逗号分隔 (default: 4,6,8,10)')
    parser.add_argument('--output', type=str,
                        default=os.path.join(os.getcwd(), 'data', 'etf_dca_report.html'),
                        help='报告输出路径 (default: data/etf_dca_report.html)')

    args = parser.parse_args()

    # 初始化数据层
    dp = DataProvider()
    dp._login()

    # 分发模式
    mode_handlers = {
        'forward': run_forward,
        'backtest': run_backtest,
        'target_amount': run_target_amount,
        'target_return': run_target_return,
        'target_duration': run_target_duration,
    }

    handler = mode_handlers.get(args.mode)
    if handler is None:
        print(f"不支持的模式: {args.mode}")
        sys.exit(1)

    output_path = handler(args, dp)
    print(f"\n报告已保存: {os.path.abspath(output_path)}")


if __name__ == '__main__':
    main()
