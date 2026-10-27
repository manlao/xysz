# -*- coding: utf-8 -*-
"""大类资产配置 HTML 报告渲染（fresh-light 风格）。

模板占位符：
    __META_LINE__     顶部口径行
    __CARDS__         各模型核心指标卡片
    __NAV_OPT__       净值对比 ECharts option
    __WCHARTS__       各模型权重堆叠图容器
    __W_OPTS__        权重堆叠 ECharts options
    __PERF__          绩效对比表
    __PERF_NOTE__     绩效口径注
    __LATEST__        最新权重表
    __LATEST_DATE__   最新调仓日
    __TRADES__        最近调仓流水表
    __MODEL_NOTES__   模型与口径说明
"""

import os
import json
from datetime import datetime

import numpy as np

_ASSET_COLORS = {'黄金': '#c9a227', '国债': '#4a90d9', '宽基': '#e07a5f', '现金': '#7fb98a'}
_NAV_COLORS = ['#4a90d9', '#e07a5f', '#c9a227', '#7fb98a', '#9b7ede', '#8d99ae',
               '#b0c4b1', '#d8a48f', '#6d9dc5', '#caa8b0']
_ASSET_ORDER = ['黄金', '国债', '宽基', '现金']


def _ts() -> str:
    """时间戳（文件名用，避免同参数重复运行互相覆盖）。"""
    return datetime.now().strftime('%Y%m%d_%H%M%S')

_MODEL_NOTES = (
    '<b>固定权重</b>：按既定比例持有并定期再平衡，默认等权，可控性最强，收益取决于初始比例；'
    '<b>均值方差（MV）</b>：马科维茨框架，用近一年日收益估计预期收益与协方差，'
    '求解 max μᵀw−(λ/2)wᵀΣw，对输入敏感、常给出极端权重，实践需配合权重上下界；'
    '<b>风险平价（RP）</b>：让各资产对组合的风险贡献相等，不依赖收益预测，天然低配高波动资产、'
    '高配低波动资产（含现金资产时现金权重显著，可用边界约束控制）；'
    '<b>BL 模型</b>：以市场均衡（隐含收益 Π=δΣw_eq）为先验，融入主观观点（观点矩阵 P、'
    '目标收益 Q、信心水平 conf），按 He-Litterman 公式得到后验收益与协方差后再做均值方差优化；'
    '无观点时退化为均衡组合（等权先验下即等权）。'
)


def _cls(v):
    if v is None:
        return ''
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ''
    return 'pos' if v > 0 else ('neg' if v < 0 else '')


def build_report(res: dict, out_dir: str) -> str:
    from models import MODEL_LABELS
    os.makedirs(out_dir, exist_ok=True)
    tpl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'assets', 'report_template.html')
    with open(tpl_path, encoding='utf-8') as f:
        tpl = f.read()

    nav = res['nav']
    perf = res['perf']
    meta = res['meta']
    model_labels = [MODEL_LABELS[m] for m in meta['models']]
    # 净值曲线/导出只保留有效投资期（裁掉窗口估计期的平推段），绩效已按锚点口径计算
    nav = nav.loc[nav.index >= meta['eff_start']]

    # ── 顶部口径行 ──
    if meta['cash_mode'] == 'fixed':
        cash_desc = '固定年化 %.2f%% 模拟' % (meta['cash_yield'] * 100)
    else:
        cash_desc = '短融ETF 511360 实测收益'
    reb_name = {'y': '年', 'm': '月', 'w': '周'}[meta['rebalance']]
    meta_line = ('资产池 <b>黄金 518880｜国债 511010｜宽基 510300/510050/510500/512100/563300 等权｜'
                 '现金（%s）</b><br>区间 %d ~ %d｜调仓 %s度（共 %d 次）｜窗口 %d 交易日｜'
                 '风险厌恶 λ=%g｜边界 %s'
                 % (cash_desc, meta['begin'], meta['end'], reb_name,
                    meta['n_rebalance'], meta['lookback'], meta['lam'],
                    meta['bounds'] or '无（0~1）'))

    # ── 卡片：每模型 1 张（年化 + 回撤/夏普） ──
    cards = []
    for i, label in enumerate(model_labels):
        v = perf[label]
        cls = _cls(v['年化收益率%'])
        cards.append(
            '<div class="card"><div class="k">%s · 年化收益</div>'
            '<div class="v %s">%+.2f%%</div>'
            '<div class="s">回撤 %.2f%%｜夏普 %s</div></div>'
            % (label, cls, v['年化收益率%'], v['最大回撤%'],
               v['夏普'] if v['夏普'] is not None else '-'))
    v = perf['等权基准']
    cards.append('<div class="card"><div class="k">等权基准 · 年化收益</div>'
                 '<div class="v %s">%+.2f%%</div><div class="s">回撤 %.2f%%｜夏普 %s</div></div>'
                 % (_cls(v['年化收益率%']), v['年化收益率%'], v['最大回撤%'],
                    v['夏普'] if v['夏普'] is not None else '-'))

    # ── 净值对比图 ──
    x = [str(d) for d in nav.index]
    series = []
    for i, col in enumerate(nav.columns):
        series.append({'name': col, 'type': 'line', 'showSymbol': False,
                       'lineStyle': {'width': 2 if col in model_labels else 1.5,
                                     'type': 'solid' if col in model_labels else 'dashed'},
                       'color': _NAV_COLORS[i % len(_NAV_COLORS)],
                       'data': [[fmt_date(d), round(float(vv), 4)]
                                for d, vv in zip(x, nav[col])]})
    legend = list(nav.columns)
    nav_opt = ('mk("navChart", {tooltip:{trigger:"axis",valueFormatter:v=>v.toFixed(4)},'
               'legend:{data:%s,top:0,textStyle:{fontSize:11}},'
               'grid:{left:50,right:16,top:34,bottom:24},'
               'xAxis:{type:"category",data:%s,axisLabel:{fontSize:10}},'
               'yAxis:{type:"value",scale:true,axisLabel:{fontSize:10}},'
               'dataZoom:[{type:"inside"}],series:%s});'
               % (json.dumps(legend, ensure_ascii=False),
                  json.dumps([fmt_date(d) for d in x]),
                  json.dumps(series, ensure_ascii=False)))
    # ── 权重堆叠图（每模型一图） ──
    wh = res['weights_hist']
    w_divs, w_opts = [], []
    for j, label in enumerate(model_labels):
        df = wh[label]
        div_id = 'wchart_%d' % j
        w_divs.append('<div id="%s" class="wchart"></div>' % div_id)
        wdates = [fmt_date(str(d)) for d in df.index]
        sers = [{'name': a, 'type': 'line', 'stack': 'w', 'areaStyle': {'opacity': 0.85},
                 'lineStyle': {'width': 0}, 'symbol': 'none', 'color': _ASSET_COLORS[a],
                 'data': [round(float(vv) * 100, 2) for vv in df[a]]}
                for a in ['黄金', '国债', '宽基', '现金']]
        w_opts.append('mk("%s", {title:{text:"%s",left:"center",top:0,'
                      'textStyle:{fontSize:13,fontWeight:600,color:"#2c3e50"}},'
                      'tooltip:{trigger:"axis",valueFormatter:v=>v+"%%"},'
                      'legend:{data:["黄金","国债","宽基","现金"],top:22,textStyle:{fontSize:11}},'
                      'grid:{left:40,right:16,top:52,bottom:24},'
                      'xAxis:{type:"category",data:%s,axisLabel:{fontSize:10}},'
                      'yAxis:{type:"value",max:100,axisLabel:{formatter:"{value}%%",fontSize:10}},'
                      'series:%s});' % (div_id, label, json.dumps(wdates),
                                        json.dumps(sers, ensure_ascii=False)))

    # ── 绩效表 ──
    keys = ['累计收益率%', '年化收益率%', '年化波动率%', '最大回撤%', '夏普', '卡玛']
    perf_rows = ['<tr><th>组合</th>' + ''.join('<th>%s</th>' % k for k in keys) + '</tr>']
    ordered = model_labels + [c for c in nav.columns if c not in model_labels]
    for col in ordered:
        v = perf[col]
        hl = ' class="hl"' if col in model_labels else ''
        tds = ''.join('<td class="%s">%s</td>' % (_cls(v[k]), _fmt_val(v[k])) for k in keys)
        perf_rows.append('<tr%s><td>%s</td>%s</tr>' % (hl, col, tds))
    perf_note = ('年化按有效投资期计算（窗口估计期不计入年限，244 交易日/年）；'
                 '夏普=(年化−rf)/波动，rf=%g%%；卡玛=年化/最大回撤；'
                 '调仓日开盘重设权重、区间内权重随价格漂移。'
                 '注：rf 默认 0，而组合本身已含现金仓位收益（固定年化口径），'
                 '故夏普为"零无风险利率"口径、偏乐观，跨工具比较需注意口径差异。'
                 % (meta['rf'] * 100))

    # ── 最新权重 ──
    lw = res['latest_w']
    latest_date = str(int(lw.iloc[0]['date']))
    latest_rows = ['<tr><th>模型</th><th>调仓日</th>' +
                   ''.join('<th>%s</th>' % a for a in ['黄金', '国债', '宽基', '现金']) + '</tr>']
    for label, row in lw.iterrows():
        tds = ''.join('<td>%.1f%%</td>' % (row[a] * 100) for a in ['黄金', '国债', '宽基', '现金'])
        latest_rows.append('<tr><td>%s</td><td>%s</td>%s</tr>'
                           % (label, fmt_date(str(int(row['date']))), tds))

    # ── 调仓流水（最近 12 条有变化记录） ──
    td = res['trades']
    td = td[td['变化pp'] != ''].tail(12)
    trade_rows = ['<tr><th>日期</th><th>模型</th><th>资产</th><th>旧权重%</th>'
                  '<th>新权重%</th><th>变化pp</th></tr>']
    for _, r in td.iterrows():
        trade_rows.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
                          '<td class="%s">%s</td></tr>'
                          % (fmt_date(str(int(r['日期']))), r['模型'], r['资产'],
                             r['旧权重%'], r['新权重%'], _cls(r['变化pp']), r['变化pp']))

    html = (tpl
            .replace('__META_LINE__', meta_line)
            .replace('__CARDS__', '\n'.join(cards))
            .replace('__NAV_OPT__', nav_opt)
            .replace('__WCHARTS__', '\n'.join(w_divs))
            .replace('__W_OPTS__', '\n'.join(w_opts))
            .replace('__PERF__', '\n'.join(perf_rows))
            .replace('__PERF_NOTE__', perf_note)
            .replace('__LATEST__', '\n'.join(latest_rows))
            .replace('__LATEST_DATE__', latest_date)
            .replace('__TRADES__', '\n'.join(trade_rows))
            .replace('__MODEL_NOTES__', _MODEL_NOTES))

    # 文件名带参数指纹（调仓频率+模型组合）+ 时间戳，不同参数/不同次运行都不互相覆盖
    out = os.path.join(out_dir, 'asset_allocation_backtest_%d_%d_%s_%s_%s.html'
                       % (meta['begin'], meta['end'], meta['rebalance'],
                          '-'.join(meta['models']), _ts()))
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    return out


# ----------------------------------------------------------------------
# 当前配置（alloc 模式）报告
# ----------------------------------------------------------------------
def build_alloc_report(res: dict, out_dir: str) -> str:
    """当前配置 HTML 报告（纯表格 + CSS 堆叠条，不依赖 ECharts）。

    res: {mu, cov, weights:{模型标签: 权重数组}, models, window_begin, window_end,
          window_days, lam, tau, bounds_str, cash_mode, cash_yield, has_views}
    """
    from models import MODEL_LABELS
    os.makedirs(out_dir, exist_ok=True)
    tpl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'assets', 'alloc_template.html')
    with open(tpl_path, encoding='utf-8') as f:
        tpl = f.read()

    mu, cov = res['mu'], res['cov']
    weights = res['weights']

    cash_desc = ('固定年化 %.2f%% 模拟' % (res['cash_yield'] * 100)
                 if res['cash_mode'] == 'fixed' else '短融ETF 511360 实测收益')
    look_txt = '、'.join('%s %d 日' % (k, v)
                         for k, v in (res.get('lookbacks') or {}).items()) or '—'
    extra = []
    if res.get('excess_cov'):
        extra.append('Σ=相对沪深300的超额收益协方差（现金保留原始口径）')
    if res.get('omega_mode') == 'idzorek':
        extra.append('Ω=刻度因子法（conf 解释为后验落在观点上的比例）')
    meta_line = ('资产池 <b>黄金 518880｜国债 511010｜宽基 510300/510050/510500/512100/563300 等权｜'
                 '现金（%s）</b><br>估计窗口 %s ~ %s（%d 个交易日）｜风险厌恶 λ=%g｜边界 %s%s%s'
                 % (cash_desc, fmt_date(str(res['window_begin'])), fmt_date(str(res['window_end'])),
                    res['window_days'], res['lam'], res['bounds_str'] or '无（0~1）',
                    '｜τ=%g' % res['tau'] if 'bl' in res['models'] else '',
                    ('｜' + '；'.join(extra)) if extra else ''))
    meta_line += '<br>各模型估计窗口：%s' % look_txt

    cards = []
    for i, a in enumerate(_ASSET_ORDER):
        v = mu[i]
        cards.append('<div class="card"><div class="k">%s · 窗口年化收益</div>'
                     '<div class="v %s">%+.2f%%</div>'
                     '<div class="s">年化波动 %.2f%%</div></div>'
                     % (a, _cls(v), v * 100, (cov[i][i] ** 0.5) * 100))
    cash_note = ('现金口径：%s。511880 货币 ETF 价格序列不含收益（收益通过份额结转体现），'
                 '故不用其价格收益作现金收益源。' % cash_desc)

    bars = []
    for m in res['models']:
        label = MODEL_LABELS[m]
        w = weights[label]
        segs = ''.join('<div style="width:%.2f%%;background:%s" title="%s %.1f%%"></div>'
                       % (w[i] * 100, _ASSET_COLORS[a], a, w[i] * 100)
                       for i, a in enumerate(_ASSET_ORDER) if w[i] > 0)
        legend = '　'.join('<span style="color:%s">●</span> %s %.1f%%'
                           % (_ASSET_COLORS[a], a, w[i] * 100)
                           for i, a in enumerate(_ASSET_ORDER))
        bars.append('<div class="brow"><div class="blabel">%s</div>'
                    '<div class="bar">%s</div><div class="blabel">%s</div></div>'
                    % (label, segs, legend))

    head = '<tr><th>模型</th>' + ''.join('<th>%s</th>' % a for a in _ASSET_ORDER) + '</tr>'
    rows = [head]
    for m in res['models']:
        label = MODEL_LABELS[m]
        tds = ''.join('<td>%.1f%%</td>' % (weights[label][i] * 100) for i in range(len(_ASSET_ORDER)))
        rows.append('<tr class="hl"><td>%s</td>%s</tr>' % (label, tds))

    views_note = ('已融入主观观点（观点数 %d）。' % res['n_views']
                  if res.get('has_views') else
                  '未输入主观观点，BL 退化为均衡先验下的均值方差。')
    notes = (_MODEL_NOTES + '<br><br><b>本次口径</b>：' + views_note +
             '观点在一段回测/多次调仓中恒定使用，不做逐期更新或衰减，'
             '相当于假设该观点在整个样本期内持续有效。')

    disclaimer = ('本报告为历史统计与模型测算结果，纯研究教育用途，<b>不构成投资建议</b>，'
                  '不代表未来表现，亦不用于实盘下单。')

    html = (tpl
            .replace('__META_LINE__', meta_line)
            .replace('__CARDS__', '\n'.join(cards))
            .replace('__CASH_NOTE__', cash_note)
            .replace('__BARS__', '\n'.join(bars))
            .replace('__WEIGHT_TABLE__', '\n'.join(rows))
            .replace('__MODEL_NOTES__', notes)
            .replace('__DISCLAIMER__', disclaimer))

    out = os.path.join(out_dir, 'asset_allocation_alloc_%s.html' % _ts())
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    return out


def _fmt_val(v):
    if v is None:
        return '-'
    if isinstance(v, str):
        return v
    return '%.2f' % v


def fmt_date(d) -> str:
    s = str(d).split('.')[0].ljust(8, '0')[:8]
    return '%s-%s-%s' % (s[:4], s[4:6], s[6:8])
