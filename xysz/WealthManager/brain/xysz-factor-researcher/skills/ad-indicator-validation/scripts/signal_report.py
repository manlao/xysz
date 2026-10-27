# -*- coding: utf-8 -*-
"""
单股信号可视化报告:ECharts 交互图

布局:
    主图   K线(蜡烛) + MA5/10/20/60 + 买卖动作标记(▲买 ▼卖)
    副图   每个参与指标的持仓状态(0=空仓 1=持有,阶梯填充)
    副图   综合信号(投票合成)+ 并集信号(全部指标同时触发)

风格:fresh-light 清新浅色,涨红跌绿,移动端自适应。
HTML 骨架来自 assets/signal_report_template.html,本模块只负责组装
ECharts option 并做 {{占位符}} 替换。不依赖 AmazingData。
"""

import json
import os

C_UP = '#e24b4a'        # 上涨/买入(红)
C_DOWN = '#0f6e56'      # 下跌/卖出(绿)
C_MA = ['#378add', '#7f77dd', '#ba7517', '#888780']
C_HOLD_FILL = 'rgba(216, 90, 48, 0.14)'
C_HOLD_LINE = '#d85a30'
C_TEXT = '#2c2c2a'
C_TEXT_SUB = '#6b6a66'

# 可读性:统一字号与白描边(浅色背景 + 图形叠加场景)
FS_AXIS = 11          # 坐标轴标签
FS_LEGEND = 12        # 图例
FS_MARK = 12          # 买卖标记
AXIS_LABEL = {'color': C_TEXT_SUB, 'fontSize': FS_AXIS,
              'textBorderColor': '#ffffff', 'textBorderWidth': 2}

_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets',
    'signal_report_template.html')


def render_signal_report(code, stock_name, begin, end, style, indicator_names,
                         dates, kline, ma, actions, signals, combined_state,
                         out_path, union_state=None):
    """
    生成单股信号 HTML 报告。

    参数
    ----
    dates           : ['YYYY-MM-DD', ...]
    kline           : [[open, close, low, high], ...] (ECharts 蜡烛顺序)
    ma              : {'MA5': [...], 'MA10': [...], 'MA20': [...], 'MA60': [...]}
    actions         : {'buy': [[idx, price], ...], 'sell': [[idx, price], ...]}
    signals         : [{'name': 'MACD', 'state': [0/1, ...]}, ...]
    combined_state  : [0/1, ...] 综合信号(投票合成)持仓状态
    union_state     : [0/1, ...] 并集信号(全部指标同时触发)持仓状态,多指标时输出
    """
    n_ind = len(signals)
    main_h = 340
    sub_h = 72
    gap = 32
    top0 = 70
    grids, xaxes, yaxes, series = [], [], [], []

    def _add_grid(top, height, is_main):
        idx = len(grids)
        grids.append({'left': 60, 'right': 72, 'top': top,
                      'height': height if is_main else height - 20})
        xaxes.append({
            'type': 'category', 'gridIndex': idx, 'data': dates,
            'boundaryGap': True,
            'axisLine': {'lineStyle': {'color': '#d3d1c7'}},
            'axisLabel': dict(AXIS_LABEL, show=idx == 0 or idx == len(grids) - 1,
                              interval='auto'),
            'axisTick': {'show': False},
            'splitLine': {'show': False},
        })
        if is_main:
            yaxes.append({
                'gridIndex': idx, 'scale': True,
                'axisLabel': dict(AXIS_LABEL),
                'splitLine': {'lineStyle': {'color': '#f1efe8'}},
            })
        else:
            yaxes.append({
                'gridIndex': idx, 'min': -0.3, 'max': 1.3, 'interval': 1,
                'axisLabel': dict(AXIS_LABEL,
                                  formatter='function(v){return v===1?"持有":(v===0?"空仓":"");}'),
                'splitLine': {'lineStyle': {'color': '#f1efe8'}},
            })
        return idx

    # ---- 主图 ----
    gi = _add_grid(top0, main_h, True)
    series.append({
        'name': 'K线', 'type': 'candlestick', 'xAxisIndex': gi, 'yAxisIndex': gi,
        'data': kline, 'itemStyle': {'color': C_UP, 'color0': C_DOWN,
                                     'borderColor': C_UP, 'borderColor0': C_DOWN},
    })
    for i, (maname, maval) in enumerate(ma.items()):
        series.append({
            'name': maname, 'type': 'line', 'xAxisIndex': gi, 'yAxisIndex': gi,
            'data': maval, 'symbol': 'none',
            'lineStyle': {'width': 1.3, 'color': C_MA[i % 4]},
        })
    if actions['buy']:
        series.append({
            'name': '买入', 'type': 'scatter', 'xAxisIndex': gi, 'yAxisIndex': gi,
            'data': actions['buy'], 'symbol': 'triangle', 'symbolSize': 12,
            'itemStyle': {'color': C_UP, 'borderColor': '#ffffff',
                          'borderWidth': 1},
            'label': {'show': True, 'position': 'bottom', 'fontSize': FS_MARK,
                      'fontWeight': 600, 'color': C_UP,
                      'textBorderColor': '#ffffff', 'textBorderWidth': 2,
                      'formatter': '买'},
        })
    if actions['sell']:
        series.append({
            'name': '卖出', 'type': 'scatter', 'xAxisIndex': gi, 'yAxisIndex': gi,
            'data': actions['sell'],
            'symbol': 'path://M4,0 L12,0 L8,8 Z',
            'symbolSize': 12,
            'itemStyle': {'color': C_DOWN, 'borderColor': '#ffffff',
                          'borderWidth': 1},
            'label': {'show': True, 'position': 'top', 'fontSize': FS_MARK,
                      'fontWeight': 600, 'color': C_DOWN,
                      'textBorderColor': '#ffffff', 'textBorderWidth': 2,
                      'formatter': '卖'},
        })

    # ---- 副图:各指标 ----
    top = top0 + main_h + gap
    for s in signals:
        gi = _add_grid(top, sub_h, False)
        series.append({
            'name': s['name'], 'type': 'line', 'xAxisIndex': gi, 'yAxisIndex': gi,
            'data': s['state'], 'step': 'end', 'symbol': 'none',
            'lineStyle': {'width': 1.5, 'color': C_HOLD_LINE},
            'areaStyle': {'color': C_HOLD_FILL, 'origin': 'start'},
        })
        top += sub_h + gap

    # ---- 副图:综合(投票) ----
    gi = _add_grid(top, sub_h, False)
    series.append({
        'name': '综合信号(投票)', 'type': 'line', 'xAxisIndex': gi, 'yAxisIndex': gi,
        'data': combined_state, 'step': 'end', 'symbol': 'none',
        'lineStyle': {'width': 1.9, 'color': '#534ab7'},
        'areaStyle': {'color': 'rgba(83, 74, 183, 0.12)', 'origin': 'start'},
    })
    top += sub_h + gap

    # ---- 副图:并集(任一触发) ----
    if union_state is not None:
        gi = _add_grid(top, sub_h, False)
        series.append({
            'name': '并集信号(全部持有)', 'type': 'line', 'xAxisIndex': gi, 'yAxisIndex': gi,
            'data': union_state, 'step': 'end', 'symbol': 'none',
            'lineStyle': {'width': 1.9, 'color': '#1d9e75'},
            'areaStyle': {'color': 'rgba(29, 158, 117, 0.12)', 'origin': 'start'},
        })
        top += sub_h + gap

    chart_height = int(top + sub_h + 76)

    chart_opt = {
        'animation': False,
        'backgroundColor': '#ffffff',
        'title': {'show': False},
        'textStyle': {'fontFamily': '-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif'},
        'tooltip': {
            'trigger': 'axis',
            'axisPointer': {'type': 'cross',
                            'label': {'backgroundColor': '#5f5e5a',
                                      'fontSize': 11}},
            'backgroundColor': 'rgba(255,255,255,0.97)',
            'borderColor': '#d3d1c7',
            'textStyle': {'color': C_TEXT, 'fontSize': 12},
        },
        'axisPointer': {'link': [{'xAxisIndex': 'all'}]},
        'legend': {
            'data': ['K线'] + list(ma.keys()) + ['买入', '卖出'],
            'top': 8, 'left': 60, 'itemWidth': 14, 'itemHeight': 9,
            'textStyle': {'color': C_TEXT, 'fontSize': FS_LEGEND},
        },
        'grid': grids,
        'xAxis': xaxes,
        'yAxis': yaxes,
        'series': series,
        'dataZoom': [
            {'type': 'inside', 'xAxisIndex': list(range(len(grids))),
             'start': max(0, 100 - int(24000 / max(len(dates), 1))), 'end': 100},
            {'type': 'slider', 'xAxisIndex': list(range(len(grids))),
             'bottom': 8, 'height': 22,
             'start': max(0, 100 - int(24000 / max(len(dates), 1))), 'end': 100,
             'borderColor': '#d3d1c7',
             'fillerColor': 'rgba(55, 138, 221, 0.15)',
             'handleStyle': {'color': '#378add'},
             'textStyle': {'color': C_TEXT_SUB, 'fontSize': 11}},
        ],
    }

    # ---- 模板替换 ----
    with open(_TEMPLATE_PATH, encoding='utf-8') as f:
        html = f.read()
    replacements = {
        '{{STOCK_NAME}}': str(stock_name),
        '{{STOCK_CODE}}': str(code),
        '{{DATE_RANGE}}': f'{begin} ~ {end}',
        '{{STYLE_NAME}}': ('位置型' if style == 'position'
                           else ('穿越型' if style == 'cross' else str(style))),
        '{{INDICATOR_BADGES}}': ''.join(
            f'<span class="badge">{n}</span>' for n in indicator_names),
        '{{CHART_HEIGHT}}': str(chart_height),
        '{{OPTION_JSON}}': json.dumps(chart_opt, ensure_ascii=False),
    }
    for k, v in replacements.items():
        html = html.replace(k, v)

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return out_path
