# -*- coding: utf-8 -*-
"""
策略业绩分析 HTML 报告渲染器 — fresh-light 清新浅色主题

纯 HTML/CSS/JS 渲染层，不依赖 AmazingData 业务逻辑。
模板: assets/strategy_performance_report_template.html（__大写占位符__ 约定）
图表使用 ECharts CDN，单文件 HTML 输出，移动端自适应。
配色遵循 A 股惯例：红涨绿跌。
"""

import os
from typing import Dict

import pandas as pd

TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'assets', 'strategy_performance_report_template.html',
)

# A 股配色惯例: 红涨绿跌
COLOR_UP = "#e5484d"
COLOR_DOWN = "#2e9e6b"

# KPI 卡配色（清新系列）
KPI_COLORS = ['#e5484d', '#f2707a', '#2e9e6b', '#5b8ff9', '#8a6fe8', '#26b8a8', '#f0855c']

# 指标分组: (组名, 组色, [(指标, 取值路径, 小数位, 后缀)])
# 取值路径: 'strategy.xxx' / 'benchmark.xxx' / 顶层键如 'calmar'/'beta'
METRIC_GROUPS = [
    ('收益指标', '#5b8ff9', [
        ('累计收益率 (%)', 'strategy.cum_return', 2, '%'),
        ('年化收益率 (%)', 'strategy.annual_return', 2, '%'),
        ('日均收益率 (%)', 'strategy.daily_return_avg', 4, '%'),
        ('月均收益率 (%)', 'strategy.monthly_return_avg', 2, '%'),
        ('月胜率 (%)', 'strategy.month_win_ratio', 1, '%'),
        ('日胜率 (%)', 'strategy.day_win_ratio', 1, '%'),
        ('盈亏比（平均盈利/平均亏损）', 'strategy.profit_loss_ratio', 2, ''),
        ('最大连涨 (交易日)', 'strategy.max_consecutive_up', 0, ''),
        ('最大连跌 (交易日)', 'strategy.max_consecutive_down', 0, ''),
    ]),
    ('风险指标', '#f0855c', [
        ('年化波动率 (%)', 'strategy.annual_volatility', 2, '%'),
        ('日波动率 (%)', 'strategy.daily_volatility', 2, '%'),
        ('月波动率 (%)', 'strategy.monthly_volatility', 2, '%'),
        ('最大回撤 (%)', 'strategy.max_drawdown', 2, '%'),
        ('当前回撤 (%)', 'strategy.current_drawdown', 2, '%'),
        ('距上次创新高 (交易日)', 'strategy.days_since_high', 0, ''),
        ('最长回撤持续 (交易日)', 'strategy.longest_drawdown_days', 0, ''),
        ('下行风险 (%)', 'strategy.downside_risk', 2, '%'),
        ('偏度', 'strategy.skewness', 2, ''),
        ('峰度', 'strategy.kurtosis', 2, ''),
    ]),
    ('风险调整指标', '#8a6fe8', [
        ('夏普比率', 'strategy.sharpe', 2, ''),
        ('索提诺比率', 'strategy.sortino', 2, ''),
        ('卡玛比率', 'calmar', 2, ''),
    ]),
    ('相对基准指标', '#26b8a8', [
        ('Beta', 'beta', 4, ''),
        ('Alpha (%)', 'alpha', 2, '%'),
        ('跟踪误差 (%)', 'tracking_error', 2, '%'),
        ('信息比率', 'information_ratio', 2, ''),
        ('特雷诺比率', 'treynor', 2, ''),
        ('超额累计收益 (%)', 'excess_cum_return', 2, '%'),
        ('超额年化收益 (%)', 'excess_annual_return', 2, '%'),
        ('日收益相关系数', 'correlation', 4, ''),
    ]),
]


def _fmt(v, digits=2, suffix='') -> str:
    if v is None:
        return '—'
    return f"{v:.{digits}f}{suffix}"


def _fmt_date(v) -> str:
    if v is None:
        return '未修复'
    if isinstance(v, pd.Timestamp):
        return v.strftime('%Y-%m-%d')
    return str(v)


def _num_class(v) -> str:
    """红涨绿跌样式类"""
    if v is None:
        return ''
    return 'up' if v >= 0 else 'down'


def _resolve(result: Dict, path: str):
    """按 'strategy.xxx' / 'calmar' 路径取值"""
    cur = result
    for part in path.split('.'):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


class PerformanceReport:
    """策略业绩分析报告（fresh-light 主题，模板驱动）"""

    def __init__(self, title: str = '策略业绩分析报告'):
        self.title = title
        if not os.path.exists(TEMPLATE_PATH):
            raise FileNotFoundError(f'报告模板不存在: {TEMPLATE_PATH}')

    # ----------------------------------------------------------
    # HTML 片段构建
    # ----------------------------------------------------------

    @staticmethod
    def _meta_chips(result: Dict, benchmark_name: str) -> str:
        has_b = result.get('benchmark') is not None
        chips = [
            f'区间 <b>{result["start_date"]:%Y-%m-%d} ~ {result["end_date"]:%Y-%m-%d}</b>',
            f'<b>{result["n_days"]}</b> 个交易日',
            f'年化天数 <b>{result["annual_days"]}</b>',
            f'无风险利率 <b>{result["rf"]*100:.1f}%</b>',
        ]
        if has_b:
            chips.insert(2, f'基准 <b>{benchmark_name}</b>')
        gaps = result.get('data_gaps') or {}
        if gaps.get('checked') and gaps.get('missing_days'):
            chips.append(f'⚠ 缺失交易日 <b>{len(gaps["missing_days"])}</b>')
        return ''.join(f'<span class="chip">{c}</span>' for c in chips)

    @staticmethod
    def _kpi_cards(result: Dict) -> str:
        s = result['strategy']
        items = [
            ('累计收益率', s['cum_return'], f"{_fmt(s['cum_return'], 2, '%')}", True),
            ('年化收益率', s['annual_return'], f"{_fmt(s['annual_return'], 2, '%')}", True),
            ('最大回撤', s['max_drawdown'], _fmt(s['max_drawdown'], 2, '%'), False),
            ('当前回撤', s['current_drawdown'], _fmt(s['current_drawdown'], 2, '%'), False),
            ('夏普比率', s['sharpe'], _fmt(s['sharpe']), False),
            ('卡玛比率', result.get('calmar'), _fmt(result.get('calmar')), False),
            ('日胜率', s['day_win_ratio'], _fmt(s['day_win_ratio'], 1, '%'), False),
        ]
        if result.get('benchmark') is not None:
            items.append(('超额年化收益', result.get('excess_annual_return'),
                          _fmt(result.get('excess_annual_return'), 2, '%'), True))

        html, colors = [], KPI_COLORS
        for i, (label, value, text, colored) in enumerate(items):
            dot = colors[i % len(colors)]
            val_cls = f' {_num_class(value)}' if colored and value is not None else ''
            # 回撤类恒为负值, 固定用绿色
            if label in ('最大回撤', '当前回撤'):
                val_cls = ' down' if value is not None and value < 0 else ''
            html.append(
                f'<div class="kpi-card">'
                f'<div class="kpi-label"><span class="kpi-dot" style="background:{dot}"></span>{label}</div>'
                f'<div class="kpi-value{val_cls}">{text}</div></div>'
            )
        return '\n'.join(html)

    @staticmethod
    def _metrics_table(result: Dict) -> str:
        has_b = result.get('benchmark') is not None
        thead = ('<thead><tr><th>指标</th><th>策略</th>'
                 + ('<th>基准</th>' if has_b else '') + '</tr></thead>')
        rows = []
        for group_name, group_color, metrics in METRIC_GROUPS:
            if group_name == '相对基准指标' and not has_b:
                continue
            tag = f'<span class="g-tag" style="background:{group_color}">{group_name}</span>'
            rows.append(f'<tr class="group-row"><td colspan="{3 if has_b else 2}">{tag}</td></tr>')
            for label, path, digits, suffix in metrics:
                sval = _resolve(result, path)
                row = (f'<td>{label}</td>'
                       f'<td class="{_num_class(sval)}">{_fmt(sval, digits, suffix)}</td>')
                if has_b:
                    bpath = path.replace('strategy.', 'benchmark.', 1) \
                        if path.startswith('strategy.') else None
                    bval = _resolve(result, bpath) if bpath else None
                    # 卡玛等仅策略侧计算的指标, 基准列显示 —
                    row += f'<td class="{_num_class(bval)}">{_fmt(bval, digits, suffix)}</td>'
                rows.append(f'<tr>{row}</tr>')
        return f'<table class="metric-table">{thead}<tbody>{"".join(rows)}</tbody></table>'

    @staticmethod
    def _annual_table(result: Dict) -> str:
        s = result['strategy']
        b = result.get('benchmark')
        has_b = b is not None
        annual = s['annual_returns']
        s_mdd = s['annual_max_drawdown']
        b_annual = b['annual_returns'] if has_b else {}
        b_mdd = b['annual_max_drawdown'] if has_b else {}
        head = ('<thead><tr><th>年份</th><th>策略收益</th>'
                + ('<th>基准收益</th><th>超额</th>' if has_b else '')
                + '<th>策略年度最大回撤</th>'
                + ('<th>基准年度最大回撤</th>' if has_b else '') + '</tr></thead>')
        rows = []
        for year, val in annual.items():
            cells = (f'<td>{year}</td>'
                     f'<td class="{_num_class(val)}">{_fmt(val, 2, "%")}</td>')
            if has_b:
                bv = b_annual.get(year)
                ev = (val - bv) if (val is not None and bv is not None) else None
                cells += (f'<td class="{_num_class(bv)}">{_fmt(bv, 2, "%")}</td>'
                          f'<td class="{_num_class(ev)}">{_fmt(ev, 2, "%")}</td>')
            cells += f'<td class="down">{_fmt(s_mdd.get(year), 2, "%")}</td>'
            if has_b:
                cells += f'<td class="down">{_fmt(b_mdd.get(year), 2, "%")}</td>'
            rows.append(f'<tr>{cells}</tr>')
        return f'<table class="annual-table">{head}<tbody>{"".join(rows)}</tbody></table>'

    @staticmethod
    def _spec_items(result: Dict) -> str:
        s = result['strategy']
        items = [
            ('年化收益率', f'（期末净值 / 期初净值）^(244 / 日收益个数) − 1，复利口径，年化天数 {result["annual_days"]}'),
            ('年化波动率', f'日收益率样本标准差（ddof=1）× √{result["annual_days"]}'),
            ('最大回撤', '净值 / 历史最高净值 − 1 的最小值；报告标注高点、低点与修复日'),
            ('当前回撤', '期末净值相对历史最高净值的回落幅度；「距上次创新高」为距最近一次历史新高的交易日数'),
            ('回撤持续天数', '自峰值（回撤前一交易日）到修复日（或期末）的交易日数'),
            ('夏普比率', f'（年化收益 − 无风险利率 {result["rf"]*100:.1f}%） / 年化波动率'),
            ('索提诺比率', f'（年化收益 − 无风险利率 {result["rf"]*100:.1f}%） / 下行风险，仅将低于无风险日收益的部分计入'),
            ('卡玛比率', '（年化收益 − 无风险利率）/ |最大回撤|'),
            ('盈亏比', '平均盈利日收益 / |平均亏损日收益|；连涨连跌以日收益正负计数'),
            ('Beta', '策略与基准日收益的样本协方差 / 基准日收益样本方差（ddof=1）'),
            ('Alpha', f'年化收益 − [无风险利率 + Beta × (基准年化收益 − 无风险利率)]，{result["rf"]*100:.1f}%'),
            ('跟踪误差', '策略与基准日收益之差的样本标准差 × √244（年化）'),
            ('信息比率', '（策略年化收益 − 基准年化收益）/ 跟踪误差'),
            ('特雷诺比率', f'（年化收益 − 无风险利率 {result["rf"]*100:.1f}%）/ Beta'),
            ('月度/年度收益', '按自然月/自然年最后一个净值点计算；首月/首年按净值首日到期末计算'),
            ('数据断档检测', '以基准指数（默认沪深300）交易日历为参照，比对净值序列缺失的交易日；'
                             '净值序列不完整会失真波动率、超额等指标'),
        ]
        if s['day_win_ratio'] is not None:
            items.insert(12, ('日胜率', '日收益率 ≥ 0 的交易日占比（不含首日）'))
        return '\n'.join(f'<li><b>{k}</b>：{v}</li>' for k, v in items)

    @staticmethod
    def _mdd_note(result: Dict) -> str:
        s = result['strategy']
        b = result.get('benchmark')
        note = (f'策略最大回撤 <b>{_fmt(s["max_drawdown"], 2, "%")}</b>'
                f'（高点 {_fmt_date(s["mdd_peak_date"])} → 低点 {_fmt_date(s["mdd_valley_date"])}，'
                f'修复于 <b>{_fmt_date(s["mdd_recover_date"])}</b>）')
        if b is not None:
            note += (f'；基准最大回撤 <b>{_fmt(b["max_drawdown"], 2, "%")}</b>'
                     f'（高点 {_fmt_date(b["mdd_peak_date"])} → 低点 {_fmt_date(b["mdd_valley_date"])}）')
        note += (f'<br>↳ 当前回撤 <b class="down">{_fmt(s["current_drawdown"], 2, "%")}</b>'
                 f'，距上次创新高 <b>{s["days_since_high"]}</b> 个交易日，'
                 f'历史最长回撤持续 <b>{s["longest_drawdown_days"]}</b> 个交易日')
        gaps = result.get('data_gaps') or {}
        if gaps.get('checked') and (gaps.get('missing_days') or gaps.get('extra_days')):
            note += (f'<br>↳ <span class="warn">⚠ 相对基准交易日历缺失 {len(gaps["missing_days"])} 个交易日'
                     f'（净值序列不完整，可能影响波动率等指标）</span>')
        return f'<p class="note">{note}</p>'

    @staticmethod
    def _dd_hint(result: Dict) -> str:
        s = result['strategy']
        b = result.get('benchmark')
        hint = f'历史最大回撤：<b class="down">{_fmt(s["max_drawdown"], 2, "%")}</b>'
        if b is not None:
            hint += f' · 基准 <b class="down">{_fmt(b["max_drawdown"], 2, "%")}</b>'
        hint += ' · 图中标注为区间最低点'
        return f'<span class="hint">{hint}</span>'

    @staticmethod
    def _heat_hint(result: Dict) -> str:
        s = result['strategy']
        return (f'<span class="hint">月均 <b class="{_num_class(s["monthly_return_avg"])}">'
                f'{_fmt(s["monthly_return_avg"], 2, "%")}</b> · 月胜率 '
                f'{_fmt(s["month_win_ratio"], 1, "%")} · 共 {len(s["monthly_returns"])} 个月</span>')

    @staticmethod
    def _footer_line(result: Dict, benchmark_name: str) -> str:
        has_b = result.get('benchmark') is not None
        bench_src = (f'基准行情来自星耀数智 AmazingData（{benchmark_name}）'
                     if has_b else '未对比基准')
        return (f'数据来源: 策略净值由用户提供，{bench_src} · '
                f'年化天数 {result["annual_days"]} · 无风险利率 {result["rf"]*100:.1f}%')

    # ----------------------------------------------------------
    # 图表数据
    # ----------------------------------------------------------

    @staticmethod
    def _prepare_charts(result: Dict, benchmark_name: str) -> Dict:
        nav = result['nav_series']
        charts = {
            'bench_name': benchmark_name,
            'dates': [ts.strftime('%Y-%m-%d') for ts in nav.index],
            'nav': [round(float(v), 4) for v in nav.values],
        }
        bench_nav = result.get('benchmark_nav_series')
        if bench_nav is not None:
            charts['bench_nav'] = [round(float(v), 4) for v in bench_nav.values]

        dd = result['strategy']['drawdown_series']
        charts['dd'] = [round(float(v), 4) for v in dd.values]
        charts['dd_min'] = round(float(dd.min()), 4)
        if result.get('benchmark') is not None:
            bdd = result['benchmark']['drawdown_series']
            charts['bench_dd'] = [round(float(v), 4) for v in bdd.values]
            charts['bench_dd_min'] = round(float(bdd.min()), 4)

        charts['dist_labels'] = list(result['strategy']['day_return_distribution'].keys())
        charts['dist_strategy'] = [round(v, 2) for v in
                                   result['strategy']['day_return_distribution'].values()]
        if result.get('benchmark') is not None:
            charts['dist_bench'] = [round(v, 2) for v in
                                    result['benchmark']['day_return_distribution'].values()]

        # 月度收益热力图
        monthly = result['strategy']['monthly_returns']
        heat, years = {}, set()
        for ym, v in monthly.items():
            y, m = int(ym[:4]), int(ym[5:7])
            years.add(y)
            heat[(y, m)] = round(v, 2)
        charts['heat_years'] = sorted(years)
        charts['heat_data'] = [{'year': y, 'month': m, 'value': v} for (y, m), v in heat.items()]

        # 年度收益
        annual = result['strategy']['annual_returns']
        charts['annual_years'] = [str(y) for y in annual.keys()]
        charts['annual_strategy'] = list(annual.values())
        if result.get('benchmark') is not None:
            b_annual = result['benchmark']['annual_returns']
            charts['annual_bench'] = [b_annual.get(y) for y in annual.keys()]
        return charts

    # ----------------------------------------------------------
    # 生成报告
    # ----------------------------------------------------------

    def generate(self, result: Dict, output_path: str,
                 benchmark_name: str = '基准', open_browser: bool = False) -> str:
        """渲染并保存 HTML 报告, 返回输出路径。"""
        import json as _json

        charts = self._prepare_charts(result, benchmark_name)
        charts_json = 'var charts = ' + _json.dumps(charts, ensure_ascii=False) + ';'

        with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
            html = f.read()

        replacements = {
            '__TITLE__': self.title,
            '__META_CHIPS__': self._meta_chips(result, benchmark_name),
            '__KPIS__': self._kpi_cards(result),
            '__METRICS_TABLE__': self._metrics_table(result),
            '__ANNUAL_TABLE__': self._annual_table(result),
            '__SPEC_ITEMS__': self._spec_items(result),
            '__MDD_NOTE__': self._mdd_note(result),
            '__DD_HINT__': self._dd_hint(result),
            '__HEAT_HINT__': self._heat_hint(result),
            '__FOOTER_LINE1__': self._footer_line(result, benchmark_name),
            '__CHARTS_JSON__': charts_json,
        }
        for key, val in replacements.items():
            html = html.replace(key, val)

        out_dir = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(out_dir, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"[报告] 已生成: {os.path.abspath(output_path)}")
        if open_browser:
            import webbrowser
            webbrowser.open('file://' + os.path.abspath(output_path))
        return os.path.abspath(output_path)


if __name__ == '__main__':
    print("本模块为渲染器, 请通过 performance_analysis.py CLI 调用")
