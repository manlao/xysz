# -*- coding: utf-8 -*-
"""
可视化报告渲染器 — 科技感暗色主题

纯 HTML/CSS/JS 渲染层，不依赖 AmazingData 业务逻辑。
将因子分析数据渲染为单页面交互式 HTML 报告。

图表使用 ECharts CDN + 暗色主题，表格使用原生 HTML。

报告模块:
    1. 因子定义
    2. 共线性检测
    3. 因子加权
    4. IC 分析
    5. 回归法分析
    6. 分层法分析
    7. 因子拥挤度
"""

import json
import webbrowser
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


# ECharts 暗色主题 JSON (vintage-inspired dark)
ECHARTS_DARK_THEME = {
    "color": ["#00d4ff", "#7b68ee", "#ff6b9d", "#00e676", "#ffab40",
              "#40c4ff", "#b388ff", "#ff80ab", "#69f0ae", "#ffd740"],
    "backgroundColor": "transparent",
    "textStyle": {"color": "#b0bec5"},
    "title": {"textStyle": {"color": "#eceff1"}},
    "line": {"symbol": "none"},
    "tooltip": {"backgroundColor": "rgba(20,25,40,0.95)", "borderColor": "#333"},
    "legend": {"textStyle": {"color": "#90a4ae"}},
    "categoryAxis": {
        "axisLine": {"lineStyle": {"color": "#37474f"}},
        "axisTick": {"lineStyle": {"color": "#37474f"}},
        "axisLabel": {"color": "#78909c"},
        "splitLine": {"lineStyle": {"color": ["#263238"]}},
    },
    "valueAxis": {
        "axisLine": {"lineStyle": {"color": "#37474f"}},
        "axisTick": {"lineStyle": {"color": "#37474f"}},
        "axisLabel": {"color": "#78909c"},
        "splitLine": {"lineStyle": {"color": ["#263238"]}},
    },
    "dataZoom": {
        "textStyle": {"color": "#78909c"},
        "dataBackground": {"lineStyle": {"color": "#00d4ff", "opacity": 0.15},
                           "areaStyle": {"color": "#00d4ff", "opacity": 0.05}},
        "handleStyle": {"color": "#00d4ff"},
        "selectedDataBackground": {"lineStyle": {"color": "#00d4ff"},
                                   "areaStyle": {"color": "#00d4ff", "opacity": 0.15}},
    },
}


class FactorAnalysisReport:
    def __init__(self, factor_name: str, title: str = None, is_multi_factor: bool = False, display_title: str = None):
        self.factor_name = factor_name
        self.title = title or f'因子分析报告 - {factor_name}'
        self.display_title = display_title or self.title
        self.sections: List[str] = []
        self._chart_id = 0
        self.is_multi_factor = is_multi_factor

    # ----------------------------------------------------------
    # 因子定义
    # ----------------------------------------------------------
    def add_definition_section(self, html_content: str):
        self.sections.insert(0, f'''
        <section id="factor-definition">
            <h2><span class="icon">&#9881;</span> 因子定义</h2>
            <div class="card">{html_content}</div>
        </section>
        ''')

    # ----------------------------------------------------------
    # IC 分析
    # ----------------------------------------------------------
    def add_ic_section(
        self, ic_df: pd.DataFrame, ic_result: pd.DataFrame,
        p_value_df: Optional[pd.DataFrame] = None,
    ):
        section_idx = len(self.sections)

        delay_cols = list(ic_result.columns)
        short_cols = delay_cols[:10]
        has_more = len(delay_cols) > 10

        def _rename_cols(df):
            if df is None:
                return None
            r = df.copy()
            r.columns = [c.replace('delay_', '滞后') + '期' for c in r.columns]
            return r

        def _filter_rename(df, cols):
            if df is None:
                return None
            available = [c for c in cols if c in df.columns]
            return _rename_cols(df[available])

        def _make_elements(ic_result_sub, ic_df_sub, pv_df_sub, suffix=''):
            table = self._df_to_table(_rename_cols(ic_result_sub).round(4),
                                       caption='IC 评价指标', index_name='指标')
            decay = pd.DataFrame({
                'IC 均值': ic_result_sub.loc['IC 均值'],
                'IC IR': ic_result_sub.loc['IC IR'],
            })
            decay.index = [f'D{i+1}' for i in range(len(decay))]
            bar_chart = self._echarts_bar(decay, f'IC 衰减概览{suffix}', '值')
            ic_renamed = _rename_cols(ic_df_sub)
            ic_chart = self._echarts_line(ic_renamed, f'IC 衰减时序图{suffix}', 'IC 值',
                                           list(ic_renamed.columns))
            pv_chart = ''
            if pv_df_sub is not None:
                pv_renamed = _rename_cols(pv_df_sub)
                pv_chart = self._echarts_line(pv_renamed, f'P 值时序图{suffix}', 'P 值',
                                               list(pv_renamed.columns))
            return table, bar_chart, ic_chart, pv_chart

        # 1-10 期（默认显示）
        ic_result_short = ic_result[short_cols]
        ic_df_short = _filter_rename(ic_df, short_cols)
        pv_df_short = _filter_rename(p_value_df, short_cols)
        tbl_s, bar_s, ic_s, pv_s = _make_elements(ic_result_short, ic_df_short, pv_df_short)

        # 全部期（默认隐藏）
        tbl_f, bar_f, ic_f, pv_f = _make_elements(ic_result, ic_df, p_value_df,
                                                    suffix=' (1-20期)')

        toggle_html = ''
        if has_more:
            toggle_html = f'''
        <div class="ic-toggle-bar">
            <button class="ic-toggle-btn active" onclick="icToggle('ic-section-{section_idx}','short',this)">1-10 期</button>
            <button class="ic-toggle-btn" onclick="icToggle('ic-section-{section_idx}','full',this)">全部 {len(delay_cols)} 期</button>
        </div>'''

        self.sections.append(f'''
        <section id="ic-analysis">
            <h2><span class="icon">&#9733;</span> IC 分析</h2>
            {toggle_html}
            <div class="ic-short" id="ic-section-{section_idx}-short">
                <div class="card">{tbl_s}</div>
                <div class="card">{bar_s}</div>
                <div class="card">{ic_s}</div>
                <div class="card">{pv_s}</div>
            </div>
            <div class="ic-full" id="ic-section-{section_idx}-full" style="display:none">
                <div class="card">{tbl_f}</div>
                <div class="card">{bar_f}</div>
                <div class="card">{ic_f}</div>
                <div class="card">{pv_f}</div>
            </div>
        </section>
        ''')

    # ----------------------------------------------------------
    # 回归法分析
    # ----------------------------------------------------------
    def add_regression_section(
        self, factor_return: pd.DataFrame, t_value: pd.Series,
        net_analysis: Dict, acf_result: Optional[Dict] = None,
    ):
        nav_data = pd.DataFrame({
            '单利净值': factor_return.get('cumsum', pd.Series()),
            '复利净值': factor_return.get('cumprod', pd.Series()),
        })
        nav_chart = self._echarts_line(nav_data, '因子收益率净值曲线', '净值', list(nav_data.columns))

        t_data = pd.DataFrame({'T 值': t_value})
        t_chart = self._echarts_line(t_data, '因子 T 值序列', 'T 值', ['T 值'], mark_line=2.0)

        # 收益/风险表
        metrics_rows = []
        for key, m in net_analysis.items():
            if not m: continue
            key_label = {'cumsum': '单利净值', 'cumprod': '复利净值'}.get(key, key)
            metrics_rows.append(f'''
            <div class="metric-group">
                <h4>{key_label}</h4>
                <div class="metric-grid">
                    <div class="metric"><span class="label">年化收益</span><span class="value">{m.get('annual_return',0):.4f}</span></div>
                    <div class="metric"><span class="label">年化波动</span><span class="value">{m.get('annual_volatility',0):.4f}</span></div>
                    <div class="metric"><span class="label">夏普比率</span><span class="value">{m.get('sharpe_ratio',0):.4f}</span></div>
                    <div class="metric"><span class="label">最大回撤</span><span class="value">{m.get('max_drawdown',0):.2f}%</span></div>
                    <div class="metric"><span class="label">Calmar</span><span class="value">{m.get('calmar_ratio',0):.4f}</span></div>
                    <div class="metric"><span class="label">Alpha</span><span class="value">{m.get('alpha',0):.4f}</span></div>
                    <div class="metric"><span class="label">胜率</span><span class="value">{m.get('win_rate',0):.2%}</span></div>
                    <div class="metric"><span class="label">索提诺</span><span class="value">{m.get('sortino_ratio',0):.4f}</span></div>
                    <div class="metric"><span class="label">下行风险</span><span class="value">{m.get('downside_risk',0):.4f}</span></div>
                    <div class="metric"><span class="label">超额收益</span><span class="value">{m.get('excess_annual_return',0):.4f}</span></div>
                    <div class="metric"><span class="label">特雷诺</span><span class="value">{m.get('treynor_ratio',0):.4f}</span></div>
                    <div class="metric"><span class="label">跟踪误差</span><span class="value">{m.get('tracking_error',0):.4f}</span></div>
                </div>
            </div>''')

        # 回撤图
        dd_chart = ''
        for key in ['cumsum', 'cumprod']:
            if key in factor_return.columns:
                nv = factor_return[key].dropna()
                if len(nv) > 0:
                    dd = (nv - nv.cummax()) / nv.cummax() * 100
                    label = '回撤曲线(单利)' if key == 'cumsum' else '回撤曲线(复利)'
                    dd_chart += self._echarts_area(pd.DataFrame({'回撤(%)': dd}), label, '%')

        self.sections.append(f'''
        <section id="regression-analysis">
            <h2><span class="icon">&#9883;</span> 回归法分析</h2>
            <div class="card">{nav_chart}</div>
            <div class="grid-2">
                <div class="card">{t_chart}</div>
                <div class="card"><h4 style="color:#90a4ae;margin-bottom:12px">绩效指标</h4>{''.join(metrics_rows)}</div>
            </div>
            <div class="card">{dd_chart}</div>
        </section>
        ''')

    # ----------------------------------------------------------
    # 分层法分析
    # ----------------------------------------------------------
    def add_stratification_section(
        self, group_navs: pd.DataFrame, group_metrics: Dict[str, Dict],
        turnover: Optional[pd.DataFrame] = None,
        signal_decay: Optional[pd.Series] = None,
        signal_reversal: Optional[pd.Series] = None,
        long_short_nav: Optional[pd.Series] = None,
    ):
        nav_chart = self._echarts_line(group_navs, '分组净值曲线', '净值', list(group_navs.columns))

        # 分组指标表
        rows = []
        for gk, m in group_metrics.items():
            rows.append([
                gk,
                f"{m.get('annual_return',0):.4f}",
                f"{m.get('sharpe_ratio',0):.4f}",
                f"{m.get('max_drawdown',0):.2f}%",
                f"{m.get('calmar_ratio',0):.4f}",
                f"{m.get('win_rate',0):.2%}",
            ])
        cols = ['分组', '年化收益', '夏普比率', '最大回撤', 'Calmar', '胜率']
        metrics_html = f'<table><caption>分组绩效指标</caption><thead><tr>'
        for c in cols:
            metrics_html += f'<th>{c}</th>'
        metrics_html += '</tr></thead><tbody>'
        for r in rows:
            metrics_html += '<tr>'
            for v in r:
                metrics_html += f'<td>{v}</td>'
            metrics_html += '</tr>'
        metrics_html += '</tbody></table>'

        # 分组年化收益柱状图（单调性可视化）
        bar_data = pd.DataFrame({gk: [m.get('annual_return',0)] for gk, m in group_metrics.items()}).T
        bar_data.columns = ['年化收益']
        bar_chart = self._echarts_bar(bar_data, '各组年化收益对比', '年化收益')

        turnover_chart = ''
        if turnover is not None:
            turnover_chart = self._echarts_line(turnover, '换手率分析', '换手率(%)', list(turnover.columns))

        signal_chart = ''
        if signal_decay is not None:
            sig_data = pd.DataFrame({
                '买入衰减': signal_decay,
                '买入反转': signal_reversal if signal_reversal is not None else pd.Series(),
            })
            signal_chart = self._echarts_line(sig_data, '买入信号衰减与反转', '比例', list(sig_data.columns))

        ls_chart = ''
        if long_short_nav is not None and len(long_short_nav) > 1:
            ls_chart = self._echarts_line(
                pd.DataFrame({'多空组合': long_short_nav}), '多空组合净值', '净值', ['多空组合'])

        self.sections.append(f'''
        <section id="stratification-analysis">
            <h2><span class="icon">&#9776;</span> 分层法分析</h2>
            <div class="card">{nav_chart}</div>
            <div class="grid-2">
                <div class="card">{bar_chart}</div>
                <div class="card">{ls_chart}</div>
            </div>
            <div class="card">{metrics_html}</div>
            <div class="card">{turnover_chart}</div>
            <div class="card">{signal_chart}</div>
        </section>
        ''')

    # ----------------------------------------------------------
    # 因子拥挤度
    # ----------------------------------------------------------
    def add_crowding_section(self, crowding_summary: pd.DataFrame, crowding_series: Dict[str, pd.Series] = None):
        if crowding_summary.empty:
            return

        table_html = self._df_to_table(crowding_summary.round(4), caption='拥挤度指标汇总', index_name='指标')

        charts = ''
        if crowding_series:
            for name, sr in crowding_series.items():
                if sr is not None and len(sr.dropna()) > 1:
                    df = pd.DataFrame({name: sr})
                    charts += self._echarts_line(df, name, '', [name])

        # 拥挤度水平标签
        level = 'normal'
        if '复合拥挤度' in crowding_summary.index:
            pct = crowding_summary.loc['复合拥挤度', '历史分位']
            if pct >= 0.8: level = 'high'
            elif pct >= 0.6: level = 'warn'
        level_label = {'high': '拥挤', 'warn': '关注', 'normal': '正常'}.get(level, '正常')
        level_color = {'high': '#ff5252', 'warn': '#ffab40', 'normal': '#00e676'}.get(level, '#00e676')

        self.sections.append(f'''
        <section id="crowding-analysis">
            <h2><span class="icon">&#9889;</span> 因子拥挤度</h2>
            <div class="card" style="text-align:center;padding:24px">
                <div class="crowding-badge" style="background:{level_color}20;border:2px solid {level_color};color:{level_color}">
                    当前拥挤度: {level_label}
                </div>
            </div>
            <div class="card">{table_html}</div>
            <div class="card">{charts}</div>
        </section>
        ''')

    # ----------------------------------------------------------
    # 多因子合成 — 共线性检测
    # ----------------------------------------------------------
    def add_collinearity_section(
        self, corr_matrix: pd.DataFrame, vif_df: pd.DataFrame,
        condition_number: float,
    ):
        """
        共线性检测。

        :param corr_matrix: 因子间相关系数矩阵
        :param vif_df: VIF DataFrame (可能是时序或单行)
        :param condition_number: 条件数标量
        """
        # 共线性状态
        is_high = condition_number > 30
        level_label = '严重共线性' if is_high else ('轻微共线性' if condition_number > 15 else '正常')
        level_color = '#ff5252' if is_high else ('#ffab40' if condition_number > 15 else '#00e676')

        # 相关系数矩阵热力图（使用共用 _echarts_heatmap）
        heatmap_chart = ''
        if not corr_matrix.empty and corr_matrix.shape[0] > 1:
            heatmap_chart = self._echarts_heatmap(corr_matrix, '因子间相关系数矩阵')

        # VIF 均值摘要表（每个因子一行）
        vif_table = ''
        if not vif_df.empty:
            # 尝试按因子名求均值（处理时序 VIF）；单行数据直接使用
            vif_col = vif_df.columns[0] if len(vif_df.columns) > 0 else 'VIF'
            if len(vif_df) > 1 and vif_col in vif_df.columns:
                vif_mean = vif_df.mean().to_frame('VIF 均值')
            else:
                vif_mean = vif_df.copy()
                if vif_mean.shape[1] == 1:
                    vif_mean.columns = ['VIF 均值']
            vif_mean.index.name = '因子'
            vif_table = self._df_to_table(vif_mean.round(2), caption='VIF 方差膨胀因子 — 均值摘要', index_name='')
            vif_table = vif_table.replace('<td>inf</td>', '<td style="color:#ff5252">∞</td>')

        # VIF 时序折线图（仅当有多期数据时）
        vif_chart = ''
        if not vif_df.empty and len(vif_df) > 1:
            vif_chart = self._echarts_line(vif_df, 'VIF 时序', 'VIF', list(vif_df.columns))

        self.sections.append(f'''
        <section id="collinearity-analysis">
            <h2><span class="icon">&#9883;</span> 共线性检测</h2>
            <div class="card" style="text-align:center;padding:24px">
                <div class="crowding-badge" style="background:{level_color}20;border:2px solid {level_color};color:{level_color}">
                    条件数: {condition_number:.2f} — {level_label}
                </div>
            </div>
            <div class="grid-2">
                <div class="card">{heatmap_chart}</div>
                <div class="card">{vif_table}</div>
            </div>
            <div class="card">{vif_chart}</div>
        </section>
        ''')

    # ----------------------------------------------------------
    # 多因子合成 — 因子加权
    # ----------------------------------------------------------
    def add_weighting_section(self, weights_df: pd.DataFrame, method_name: str):
        method_labels = {
            'equal_weight': '等权平均',
            'ic_mean': 'IC 均值加权',
            'ic_ir': 'IC IR 加权',
            'max_ic': '最大 IC 加权',
            'max_ic_ir': '最优 IC IR 加权',
            'return_mean': '收益率均值加权',
            'return_half_life': '收益率半衰加权',
            'return_ir': '收益率 IR 加权',
        }
        method_label = method_labels.get(method_name, method_name)

        # 权重饼图
        self._chart_id += 1
        pie_cid = f'chart_{self._chart_id}'
        pie_data = []
        for idx, row in weights_df.iterrows():
            val_col = '权重' if '权重' in weights_df.columns else weights_df.columns[0]
            pie_data.append({'name': str(idx), 'value': round(float(row[val_col]), 4)})
        pie_opt = {
            'tooltip': {'trigger': 'item', 'formatter': '{b}: {c} ({d}%)'},
            'legend': {'orient': 'vertical', 'right': 10, 'top': 'center', 'textStyle': {'color': '#90a4ae', 'fontSize': 11}},
            'series': [{
                'type': 'pie', 'radius': ['35%', '65%'], 'center': ['40%', '50%'],
                'data': pie_data,
                'label': {'color': '#90a4ae', 'fontSize': 11, 'formatter': '{b}\\n{d}%'},
                'emphasis': {'itemStyle': {'shadowBlur': 10, 'shadowColor': 'rgba(0,0,0,0.5)'}},
            }],
        }
        pie_chart = self._render_chart(pie_cid, pie_opt, f'权重分布 ({method_label})')

        # 权重柱状图
        self._chart_id += 1
        bar_cid = f'chart_{self._chart_id}'
        bar_x = list(weights_df.index)
        val_col = '权重' if '权重' in weights_df.columns else weights_df.columns[0]
        bar_vals = [round(float(weights_df.loc[idx, val_col]), 4) for idx in bar_x]
        bar_opt = {
            'tooltip': {'trigger': 'axis', 'axisPointer': {'type': 'shadow'}},
            'grid': {'left': 60, 'right': 30, 'top': 10, 'bottom': 50},
            'xAxis': {'type': 'category', 'data': bar_x, 'axisLabel': {'fontSize': 10, 'rotate': 30}},
            'yAxis': {'type': 'value', 'name': '权重',
                      'axisLabel': {'fontSize': 10, 'formatter': '___BAR_YFMT___'}},
            'series': [{
                'type': 'bar', 'data': bar_vals, 'barMaxWidth': 50,
                'itemStyle': {'borderRadius': [6, 6, 0, 0],
                              'color': '___BAR_COLOR___'}
            }],
        }
        bar_chart = self._render_chart(bar_cid, bar_opt, '因子权重对比')

        # 权重表
        weight_table = self._df_to_table(weights_df.round(4), caption='因子权重明细', index_name='因子')
        # 转换为百分比显示（精确匹配：因子名+权重值，避免同权重冲突）
        for idx in weights_df.index:
            v = weights_df.loc[idx, val_col]
            weight_table = weight_table.replace(
                f'<td>{idx}</td><td>{v:.4f}</td>',
                f'<td>{idx}</td><td>{v*100:.2f}%</td>',
                1
            )

        self.sections.append(f'''
        <section id="weighting-analysis">
            <h2><span class="icon">&#9878;</span> 因子加权 ({method_label})</h2>
            <div class="grid-2">
                <div class="card">{pie_chart}</div>
                <div class="card">{bar_chart}</div>
            </div>
            <div class="card">{weight_table}</div>
        </section>
        ''')

    # ----------------------------------------------------------
    # 生成 HTML
    # ----------------------------------------------------------
    def _nav_collinearity_and_weighting(self) -> str:
        """仅多因子合成模式显示共线性检测和因子加权导航链接"""
        if self.is_multi_factor:
            return (
                '    <a href="#collinearity-analysis">共线性</a>\n'
                '    <a href="#weighting-analysis">因子加权</a>\n'
            )
        return ''

    def generate(self, output_path: str = None, open_browser: bool = True):
        if output_path is None:
            output_path = f'{self.factor_name}_report.html'
        html = self._build_html()
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"报告已生成: {output_path}")
        if open_browser:
            webbrowser.open(output_path)
        return output_path

    def _build_html(self) -> str:
        return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{self.title}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
:root {{
    --bg: #0a0e17;
    --bg-card: #111827;
    --bg-card-hover: #1a2332;
    --border: #1e2d3d;
    --text: #b0bec5;
    --text-bright: #e0e6ed;
    --text-dim: #607d8b;
    --accent: #00d4ff;
    --accent2: #7b68ee;
    --accent3: #ff6b9d;
    --green: #00e676;
    --orange: #ffab40;
    --red: #ff5252;
    --radius: 10px;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    min-height: 100vh;
}}
.header {{
    background: linear-gradient(135deg, #0a1628 0%, #0d1f3c 40%, #0a1628 100%);
    border-bottom: 1px solid var(--border);
    padding: 32px 40px;
    position: relative;
    overflow: hidden;
}}
.header::before {{
    content: '';
    position: absolute;
    top: -50%; right: -10%;
    width: 400px; height: 400px;
    background: radial-gradient(circle, rgba(0,212,255,0.08) 0%, transparent 70%);
    pointer-events: none;
}}
.header h1 {{
    font-size: 26px; font-weight: 700; color: var(--text-bright);
    letter-spacing: -0.5px; text-align: center;
}}
.header h1 span {{ color: var(--accent); }}
.header .meta {{
    margin-top: 8px; font-size: 13px; color: var(--text-dim);
    display: flex; gap: 24px; justify-content: center;
}}
.header .meta .badge {{
    display: inline-block; padding: 2px 10px; border-radius: 12px;
    font-size: 11px; font-weight: 600;
    background: rgba(0,212,255,0.12); color: var(--accent);
}}
.nav {{
    max-width: 1300px; margin: 0 auto;
    background: rgba(17,24,39,0.95);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border);
    display: flex; gap: 0; padding: 0 40px;
    position: sticky; top: 0; z-index: 100;
    overflow-x: auto;
}}
.nav a {{
    display: inline-block; padding: 14px 22px; color: var(--text-dim);
    text-decoration: none; font-size: 13px; font-weight: 500;
    border-bottom: 2px solid transparent; white-space: nowrap;
    transition: all .25s; letter-spacing: 0.3px;
}}
.nav a:hover {{ color: var(--text-bright); background: rgba(255,255,255,0.02); }}
.nav a.active {{ color: var(--accent); border-bottom-color: var(--accent); }}
.content {{ max-width: 1300px; margin: 0 auto; padding: 32px 40px; }}
section {{ margin-bottom: 48px; }}
section h2 {{
    font-size: 18px; font-weight: 700; color: var(--text-bright);
    margin-bottom: 20px; display: flex; align-items: center; gap: 10px;
    letter-spacing: 0.5px;
}}
section h2 .icon {{ color: var(--accent); font-size: 20px; }}
.card {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 24px; margin-bottom: 16px;
    transition: border-color .3s;
}}
.card:hover {{ border-color: #2a3a50; }}
.grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }}
.grid-2 .card {{ margin-bottom: 0; }}
.chart {{ width: 100%; height: 420px; }}
h4 {{ font-size: 14px; color: var(--text-dim); font-weight: 500; margin-bottom: 8px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
caption {{
    font-weight: 600; font-size: 14px; margin-bottom: 12px;
    text-align: left; color: var(--text-bright);
    padding-left: 25px;
}}
th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--border); }}
th:first-child, td:first-child {{ padding-left: 40px; }}
th {{ background: rgba(0,212,255,0.06); color: var(--accent); font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }}
td {{ color: var(--text); }}
tr:hover td {{ background: rgba(0,212,255,0.03); }}
.metric-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
.metric-group h4 {{ margin-bottom: 12px; color: var(--accent2); }}
.metric {{
    background: rgba(255,255,255,0.02);
    border: 1px solid var(--border);
    border-radius: 8px; padding: 12px; text-align: center;
}}
.metric .label {{ display: block; font-size: 11px; color: var(--text-dim); margin-bottom: 4px; }}
.metric .value {{ display: block; font-size: 18px; font-weight: 700; color: var(--text-bright); }}
.crowding-badge {{
    display: inline-block; padding: 10px 32px; border-radius: 20px;
    font-size: 16px; font-weight: 700; letter-spacing: 1px;
}}
.ic-toggle-bar {{
    display: flex; gap: 8px; margin-bottom: 16px;
}}
.ic-toggle-btn {{
    padding: 6px 18px; border: 1px solid var(--border); border-radius: 6px;
    background: transparent; color: var(--text-dim); cursor: pointer;
    font-size: 12px; font-family: inherit; transition: all .2s;
}}
.ic-toggle-btn:hover {{
    border-color: var(--accent); color: var(--text-bright);
}}
.ic-toggle-btn.active {{
    background: rgba(0,212,255,0.12); border-color: var(--accent); color: var(--accent);
    font-weight: 600;
}}
.footer {{
    text-align: center; padding: 32px; color: var(--text-dim); font-size: 12px;
    border-top: 1px solid var(--border); margin-top: 48px;
}}
@media (max-width: 900px) {{
    .grid-2 {{ grid-template-columns: 1fr; }}
    .metric-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .header {{ padding: 24px 20px; }}
    .header h1 {{ font-size: 20px; }}
    .header .meta {{ flex-direction: column; gap: 4px; }}
    .content {{ padding: 16px; }}
    .nav {{ padding: 0 12px; }}
    .nav a {{ padding: 12px 14px; font-size: 12px; }}
    .card {{ padding: 16px; }}
    .chart {{ height: 300px !important; }}
    table {{ font-size: 11px; }}
    th, td {{ padding: 6px 8px; }}
}}
@media (max-width: 480px) {{
    .header h1 {{ font-size: 17px; }}
    .header .meta {{ font-size: 11px; }}
    .nav a {{ padding: 10px 10px; font-size: 11px; }}
    .metric-grid {{ grid-template-columns: repeat(2, 1fr); gap: 8px; }}
    .metric .value {{ font-size: 15px; }}
    .chart {{ height: 250px !important; }}
    .crowding-badge {{ font-size: 14px; padding: 8px 20px; }}
}}
</style>
</head>
<body>
<div class="header">
    <h1><span>&#9670;</span> {self.display_title}</h1>
    <div class="meta">
        <span>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span>
    </div>
</div>
<nav class="nav">
    <a href="#factor-definition" class="active">因子定义</a>
{self._nav_collinearity_and_weighting()}
    <a href="#ic-analysis">IC 分析</a>
    <a href="#regression-analysis">回归法</a>
    <a href="#stratification-analysis">分层法</a>
    <a href="#crowding-analysis">因子拥挤度</a>
</nav>
<div class="content">
    {''.join(self.sections)}
</div>
<div class="footer">
    Factor Analysis Framework v1.0 &copy; {datetime.now().year} &mdash; Powered by AmazingData
</div>
<script>
echarts.registerTheme('dark', {json.dumps(ECHARTS_DARK_THEME, ensure_ascii=False)});
document.querySelectorAll('.nav a').forEach(a => {{
    a.addEventListener('click', function() {{
        document.querySelectorAll('.nav a').forEach(x => x.classList.remove('active'));
        this.classList.add('active');
    }});
}});
function icToggle(sectionId, mode, btn) {{
    var bar = btn.parentElement;
    bar.querySelectorAll('.ic-toggle-btn').forEach(function(b) {{ b.classList.remove('active'); }});
    btn.classList.add('active');
    var shortDiv = document.getElementById(sectionId + '-short');
    var fullDiv = document.getElementById(sectionId + '-full');
    if (!shortDiv || !fullDiv) return;
    if (mode === 'short') {{
        shortDiv.style.display = 'block';
        fullDiv.style.display = 'none';
    }} else {{
        shortDiv.style.display = 'none';
        fullDiv.style.display = 'block';
    }}
    setTimeout(function() {{
        var visible = mode === 'short' ? shortDiv : fullDiv;
        visible.querySelectorAll('.chart').forEach(function(el) {{
            var c = echarts.getInstanceByDom(el);
            if (c) c.resize();
        }});
    }}, 80);
}}
(function initAllCharts() {{
    if (!window.echarts) {{ setTimeout(initAllCharts, 200); return; }}
    for (var key in window) {{
        if (key.startsWith('_initChart_')) window[key]();
    }}
}})();
window.addEventListener('resize', () => {{
    document.querySelectorAll('.chart').forEach(el => {{
        const c = echarts.getInstanceByDom(el);
        if (c) c.resize();
    }});
}});
</script>
</body>
</html>'''

    # ----------------------------------------------------------
    # ECharts 图表生成
    # ----------------------------------------------------------
    def _echarts_line(self, data, title, y_name, legend, mark_line=None):
        self._chart_id += 1
        cid = f'chart_{self._chart_id}'
        dates = [str(d)[:10] for d in data.index]
        series = []
        for col in data.columns:
            vals = [float(v) if not pd.isna(v) else None for v in data[col].values]
            s = {'name': str(col), 'type': 'line', 'data': vals, 'smooth': True, 'symbol': 'none',
                 'lineStyle': {'width': 1.5}}
            if mark_line is not None:
                s['markLine'] = {'data': [{'yAxis': mark_line, 'label': {'formatter': f'{mark_line}'}}],
                                 'silent': True, 'lineStyle': {'type': 'dashed', 'color': '#607d8b'}}
            series.append(s)
        opt = {'tooltip': {'trigger': 'axis', 'valueFormatter': self._get_formatter(y_name)},
               'legend': {'data': legend or list(data.columns), 'top': 0},
               'grid': {'left': 55, 'right': 25, 'top': 40, 'bottom': 70},
               'xAxis': {'type': 'category', 'data': dates,
                         'axisLabel': {'rotate': 45, 'fontSize': 10, 'margin': 8,
                                       'interval': max(0, len(dates) // 8)}},
               'yAxis': {'type': 'value', 'name': y_name, 'nameTextStyle': {'fontSize': 11},
                         'scale': True, 'axisLabel': {'formatter': self._get_yaxis_formatter(y_name)}},
               'series': series,
               'dataZoom': [{'type': 'inside'}, {'type': 'slider', 'bottom': 22, 'height': 18}]}
        return self._render_chart(cid, opt, title)

    def _echarts_area(self, data, title, y_name):
        self._chart_id += 1
        cid = f'chart_{self._chart_id}'
        dates = [str(d)[:10] for d in data.index]
        series = []
        for col in data.columns:
            vals = [float(v) if not pd.isna(v) else None for v in data[col].values]
            series.append({'name': str(col), 'type': 'line', 'data': vals,
                           'areaStyle': {'opacity': 0.25}, 'symbol': 'none', 'smooth': True,
                           'lineStyle': {'width': 1.5}})
        opt = {'tooltip': {'trigger': 'axis', 'valueFormatter': self._get_formatter(y_name)},
               'legend': {'data': list(data.columns), 'top': 0},
               'grid': {'left': 55, 'right': 25, 'top': 40, 'bottom': 70},
               'xAxis': {'type': 'category', 'data': dates,
                         'axisLabel': {'fontSize': 10, 'rotate': 45, 'margin': 8,
                                       'interval': max(0, len(dates) // 8)}},
               'yAxis': {'type': 'value', 'name': y_name, 'scale': True,
                         'axisLabel': {'formatter': self._get_yaxis_formatter(y_name)}},
               'series': series,
               'dataZoom': [{'type': 'inside'}, {'type': 'slider', 'bottom': 22, 'height': 18}]}
        return self._render_chart(cid, opt, title)

    def _echarts_bar(self, data, title, y_name):
        self._chart_id += 1
        cid = f'chart_{self._chart_id}'
        x_data = [str(i) for i in data.index]
        series = []
        for col in data.columns:
            vals = [float(v) if not pd.isna(v) else None for v in data[col].values]
            series.append({'name': str(col), 'type': 'bar', 'data': vals,
                           'barMaxWidth': 40, 'itemStyle': {'borderRadius': [4, 4, 0, 0]}})
        opt = {'tooltip': {'trigger': 'axis', 'valueFormatter': self._get_formatter(y_name)},
               'legend': {'data': list(data.columns), 'top': 0},
               'grid': {'left': 55, 'right': 25, 'top': 40, 'bottom': 70},
               'xAxis': {'type': 'category', 'data': x_data, 'axisLabel': {'fontSize': 10}},
               'yAxis': {'type': 'value', 'name': y_name},
               'series': series}
        return self._render_chart(cid, opt, title)

    def _echarts_heatmap(self, data, title):
        """相关系数矩阵热力图"""
        self._chart_id += 1
        cid = f'chart_{self._chart_id}'
        labels = [str(c) for c in data.columns]
        heat_data = []
        for i, ri in enumerate(data.index):
            for j, cj in enumerate(data.columns):
                heat_data.append([j, i, round(float(data.loc[ri, cj]), 4)])
        opt = {
            'tooltip': {
                'position': 'top',
                'backgroundColor': 'rgba(20,25,40,0.95)',
                'borderColor': '#37474f',
                'textStyle': {'fontSize': 13},
            },
            'grid': {'left': 110, 'right': 60, 'top': 60, 'bottom': 90},
            'xAxis': {'type': 'category', 'data': labels, 'position': 'top',
                      'axisLabel': {'rotate': 45, 'fontSize': 11, 'color': '#b0bec5',
                                    'fontWeight': 'bold'}},
            'yAxis': {'type': 'category', 'data': [str(r) for r in data.index],
                      'axisLabel': {'fontSize': 11, 'color': '#b0bec5', 'fontWeight': 'bold'}},
            'visualMap': {
                'min': -1, 'max': 1, 'calculable': True,
                'orient': 'horizontal', 'left': 'center', 'bottom': 6,
                'textStyle': {'color': '#b0bec5', 'fontSize': 11},
                'inRange': {'color': ['#1565C0', '#64B5F6', '#FFE082', '#EF5350', '#C62828']},
            },
            'series': [{
                'type': 'heatmap', 'data': heat_data,
                'label': {'show': True, 'fontSize': 12, 'fontWeight': 'bold',
                          'formatter': '___HM_TOOLTIP___'},
                'itemStyle': {'borderColor': '#1a2332', 'borderWidth': 2,
                              'borderRadius': 2},
                'emphasis': {'itemStyle': {'shadowBlur': 10, 'shadowColor': 'rgba(0,0,0,0.5)',
                                           'borderWidth': 2}},
            }],
        }
        return self._render_chart(cid, opt, title)

    def _render_chart(self, cid, option, title):
        opt_json = json.dumps(option, ensure_ascii=False)
        # 替换占位符为真实 JS 函数
        opt_json = opt_json.replace('"___FMT_PCT___"', '(function(v){{ return v != null ? v.toFixed(2) + "%" : "-"; }})')
        opt_json = opt_json.replace('"___FMT_NUM___"', '(function(v){{ return v != null ? v.toFixed(4) : "-"; }})')
        opt_json = opt_json.replace('"___YFMT_PCT___"', '(function(v){{ return v.toFixed(0) + "%"; }})')
        opt_json = opt_json.replace('"___YFMT_NUM___"', '(function(v){{ return (Math.abs(v) < 0.01 && v !== 0) ? v.toExponential(2) : v.toFixed(4); }})')
        opt_json = opt_json.replace('"___HM_TOOLTIP___"', '(function(p){{ return p.data[2] != null ? p.data[2].toFixed(4) : "-"; }})')
        opt_json = opt_json.replace('"___BAR_COLOR___"', 'function(p){{ var colors = ["#00d4ff","#7b68ee","#ff6b9d","#00e676","#ffab40","#40c4ff"]; return colors[p.dataIndex % colors.length]; }}')
        opt_json = opt_json.replace('"___BAR_YFMT___"', 'function(v){{ return (v*100).toFixed(1)+"%"; }}')
        return f'''
        <h4>{title}</h4>
        <div id="{cid}" class="chart"></div>
        <script>
        _initChart_{cid} = function() {{
            var el = document.getElementById('{cid}');
            if (!el || !window.echarts) return;
            var chart = echarts.init(el, 'dark');
            chart.setOption({opt_json});
        }};
        if (window.echarts) {{ _initChart_{cid}(); }} else {{ window.addEventListener('DOMContentLoaded', _initChart_{cid}); }}
        </script>'''

    @staticmethod
    def _get_formatter(y_name: str) -> str:
        """返回 tooltip valueFormatter 的 JS 函数字符串（占位符，后续替换）"""
        if '%' in y_name:
            return "___FMT_PCT___"
        return "___FMT_NUM___"

    @staticmethod
    def _get_yaxis_formatter(y_name: str) -> str:
        """返回 axisLabel formatter 的 JS 函数字符串（占位符，后续替换）"""
        if '%' in y_name:
            return "___YFMT_PCT___"
        return "___YFMT_NUM___"

    @staticmethod
    def _df_to_table(df, caption='', index_name=''):
        html = f'<table><caption>{caption}</caption><thead><tr>'
        if index_name:
            html += f'<th>{index_name}</th>'
        for col in df.columns:
            html += f'<th>{col}</th>'
        html += '</tr></thead><tbody>'
        for idx, row in df.iterrows():
            html += '<tr>'
            html += f'<td>{idx}</td>'
            for val in row:
                if isinstance(val, float):
                    html += f'<td>{val:.4f}</td>'
                elif isinstance(val, (int, np.integer)):
                    html += f'<td>{val}</td>'
                else:
                    html += f'<td>{val}</td>'
            html += '</tr>'
        html += '</tbody></table>'
        return html
