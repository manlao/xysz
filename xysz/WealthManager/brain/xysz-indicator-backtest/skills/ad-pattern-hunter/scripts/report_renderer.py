# -*- coding: utf-8 -*-
"""
形态猎手 — HTML 报告渲染器（fresh-light 风格，__PLACEHOLDER__ 替换式）
"""

import json
import os
from datetime import datetime

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.abspath(os.path.join(SCRIPT_DIR, '..', 'assets', 'report_template.html'))
OUTPUT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', 'output', 'pattern_hunter'))

FAMILY_COLORS = {
    '趋势延续类': '#5b8ff9',
    '底部反转类': '#2e9e6b',
    '顶部反转类': '#e5484d',
    '整理突破类': '#f0855c',
    '轮廓匹配': '#8a6fe8',
}
DIR_CLASS = {'看多': 'bull', '看空': 'bear', '中性': 'neutral'}
DIR_COLOR = {'看多': '#e5484d', '看空': '#2e9e6b', '中性': '#d98324'}
RANK_COLORS = ['#e5484d', '#f0855c', '#f0b05c', '#5b8ff9', '#8a6fe8',
               '#26b8a8', '#2e9e6b', '#5c6c80']


def _fmt_date(d) -> str:
    s = str(d)
    return '%s-%s-%s' % (s[:4], s[4:6], s[6:8])


def _direction_of(r) -> str:
    return r.get('direction', '中性')


def _profile_price(pdef_id, n, mean, std, external=None):
    """模板/外部轮廓 → 价格域叠加序列。"""
    from pattern_engine import PATTERNS, resample_profile
    if external is not None:
        z = resample_profile(external, n)
    elif pdef_id in PATTERNS:
        z = PATTERNS[pdef_id].profile_fn(n)
        sd = z.std()
        z = (z - z.mean()) / sd if sd > 1e-12 else z
    else:
        return [None] * n
    return [round(float(mean + v * std), 4) for v in z]


def _build_charts(top_overall, klines, names, window, max_candidates=8):
    """重点候选图表数据（按代码去重，保留最高分形态）。"""
    seen = set()
    candidates = []
    for code, r in top_overall:
        if code in seen:
            continue
        seen.add(code)
        df = klines.get(code)
        if df is None or len(df) < 10:
            continue
        win = df.tail(window)
        c = win['close'].to_numpy(dtype=float)
        mean, std = float(c.mean()), float(c.std())
        ohlc = []
        vol_color = []
        for _, row in win.iterrows():
            o, hi, lo, cl = row['open'], row['high'], row['low'], row['close']
            ohlc.append([round(float(o), 4), round(float(cl), 4),
                         round(float(lo), 4), round(float(hi), 4)])
            up = cl >= o
            vol_color.append({'value': round(float(row.get('volume', 0) or 0), 0),
                              'itemStyle': {'color': '#e5484d' if up else '#2e9e6b'}})
        overlay = _profile_price(r['pattern_id'], len(win), mean, std,
                                 external=None if r['pattern_id'] != 'profile_custom'
                                 else None)
        # profile_custom 模式的外部轮廓由调用方经 profile 参数传入（见 render_report）
        candidates.append({
            'code': code, 'name': names.get(code, code),
            'pattern': r['pattern_name'], 'direction': _direction_of(r),
            'score': r['score'], 'rule_score': r['rule_score'],
            'sim_score': r['sim_score'], 'corr': r['corr'],
            'dates': [_fmt_date(d) for d in win.index],
            'ohlc': ohlc, 'vol_color': vol_color, 'profile': overlay,
            'hits': [{'name': h['name'], 'ok': bool(h['ok']), 'detail': h['detail']}
                     for h in r['hits']],
            '_begin': _fmt_date(win.index[0]), '_end': _fmt_date(win.index[-1]),
        })
        if len(candidates) >= max_candidates:
            break
    return candidates


def _jsonable(obj):
    """递归转换 numpy 类型 → JSON 可序列化的 Python 原生类型。"""
    if isinstance(obj, np.ndarray):
        return [_jsonable(v) for v in obj.tolist()]
    if isinstance(obj, np.generic):
        return _jsonable(obj.item())
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (bool, int, float, str)) or obj is None:
        return obj
    return str(obj)


def render_report(mode, args, begin, end, data_date, window, universe, elapsed,
                  total_scanned, insufficient, min_score, by_pattern, top_overall,
                  klines, names, profile=None, profile_note='', pattern_ids=None,
                  external_profile=None, timeframe='day'):
    """渲染 HTML 报告并落盘，返回报告路径。"""
    mode_cn = '轮廓匹配' if mode == 'profile' else '模板雷达扫描'
    title = '形态猎手 · %s报告' % mode_cn
    if timeframe and timeframe != 'day':
        title += '（%s）' % timeframe

    # ---- meta chips ----
    if mode == 'scan':
        ptext = '全部 %d 类' % len(pattern_ids or []) if args.get('pattern') == 'all' \
            else str(args.get('pattern'))
    else:
        ptext = os.path.basename(args.get('profile', '外部轮廓'))
        if profile_note:
            ptext += '（%s）' % profile_note[:20]
    chips = [
        ('模式', mode_cn), ('形态', ptext), ('周期', timeframe or 'day'),
        ('股票池', universe), ('窗口', '%d BAR' % window),
        ('区间', '%d ~ %d' % (begin, end)), ('数据日', str(data_date)),
        ('分数线', '≥%.0f' % min_score), ('耗时', '%.0f 秒' % elapsed),
    ]
    meta = ''.join('<span class="chip">%s <b>%s</b></span>' % (k, v) for k, v in chips)

    n_hits = sum(len(v) for v in by_pattern.values())
    n_patterns = len(by_pattern)
    n_candidates = min(len({c for c, _ in top_overall}), 8)
    kpis = [
        ('参与扫描', '%d' % total_scanned, '只', '#5b8ff9'),
        ('命中条数', '%d' % n_hits, '条', '#e5484d'),
        ('命中形态', '%d' % n_patterns, '类', '#f0855c'),
        ('重点候选', '%d' % n_candidates, '只', '#8a6fe8'),
        ('数据不足跳过', '%d' % insufficient, '只', '#93a1b3'),
    ]
    kpi_html = ''.join(
        '<div class="kpi-card"><div class="kpi-label">'
        '<span class="kpi-dot" style="background:%s;"></span>%s</div>'
        '<div class="kpi-value">%s</div><div class="kpi-sub">%s</div></div>'
        % (color, label, value, unit)
        for label, value, unit, color in kpis)

    # ---- 重点候选卡片 ----
    candidates = _build_charts(top_overall, klines, names, window)
    if mode == 'profile' and external_profile is not None:
        for cd in candidates:
            df = klines.get(cd['code'])
            if df is not None:
                win = df.tail(window)
                c = win['close'].to_numpy(dtype=float)
                cd['profile'] = _profile_price('profile_custom', len(win),
                                               float(c.mean()), float(c.std()),
                                               external=external_profile)
    cand_html = []
    for i, cd in enumerate(candidates):
        d = _direction_of(cd)
        rc = RANK_COLORS[i % len(RANK_COLORS)]
        rules = ''.join(
            '<span class="rule-tag %s">%s %s</span>'
            % ('ok' if h['ok'] else 'no', '✓' if h['ok'] else '✗', h['name'])
            for h in cd['hits'])
        cand_html.append(
            '<div class="cand">'
            '<div class="cand-head">'
            '<div class="rank-badge" style="background:%s;">%d</div>'
            '<h3>%s</h3><span class="code">%s · 匹配区间 %s ~ %s</span>'
            '<span class="dir-chip" style="background:%s;">%s · %s</span>'
            '<div class="score-chips">'
            '<span class="score-chip">总分 <b>%.1f</b></span>'
            '<span class="score-chip">规则 <b>%.0f</b></span>'
            '<span class="score-chip">相似 <b>%.0f</b></span>'
            '<span class="score-chip">相关 <b>%.2f</b></span>'
            '</div></div>'
            '<div id="chart_%d" class="chart"></div>'
            '<div class="rules">%s</div>'
            '</div>'
            % (rc, i + 1, cd['name'], cd['code'], cd['_begin'], cd['_end'],
               DIR_COLOR.get(d, '#93a1b3'), d, cd['pattern'],
               cd['score'], cd['rule_score'], cd['sim_score'], cd['corr'],
               i, rules))
    if not cand_html:
        cand_html.append('<div class="empty">没有达到分数线（≥%.0f）的候选，'
                         '可降低 --min-score 或更换形态/股票池再试。</div>' % min_score)
    candidates_html = ''.join(cand_html)

    # ---- 命中明细表 ----
    rows = []
    fams = []
    if mode == 'scan':
        from pattern_engine import FAMILY_ORDER, PATTERNS
        fam_of = {pid: PATTERNS[pid].family for pid in by_pattern}
        for fam in FAMILY_ORDER:
            if any(fam_of.get(p) == fam for p in by_pattern):
                fams.append((fam, [p for p in by_pattern if fam_of.get(p) == fam]))
    else:
        fams.append(('轮廓匹配', list(by_pattern.keys())))

    for fam, pids in fams:
        color = FAMILY_COLORS.get(fam, '#5b8ff9')
        rows.append('<tr class="group-row"><td colspan="8">'
                    '<span class="g-tag" style="background:%s;">%s</span></td></tr>'
                    % (color, fam))
        # 组内按形态聚合，形态间按最高分排序，形态内按分数降序
        pattern_blocks = []
        for pid in pids:
            lst = by_pattern[pid]
            pname = lst[0]['pattern_name'] if lst else pid
            pattern_blocks.append((max(r['score'] for r in lst), pid, pname, lst))
        pattern_blocks.sort(key=lambda b: -b[0])
        for _, pid, pname, lst in pattern_blocks:
            rows.append('<tr class="group-row" style="background:#fcfdff;"><td colspan="8">'
                        '<span style="color:#4c5c70;font-weight:600;">▸ %s</span>'
                        '<span style="color:#93a1b3;font-size:11px;margin-left:8px;">%d 只</span>'
                        '</td></tr>' % (pname, len(lst)))
            for j, r in enumerate(lst, 1):
                d = _direction_of(r)
                rows.append(
                    '<tr><td>%d</td><td>%s</td><td>%s</td>'
                    '<td><span class="dir-chip" style="background:%s;">%s</span></td>'
                    '<td><b>%.1f</b></td><td>%.1f</td><td>%.1f</td><td>%.2f</td></tr>'
                    % (j, r['code'], r['name'], DIR_COLOR.get(d, '#93a1b3'), d,
                       r['score'], r['rule_score'], r['sim_score'], r['corr']))
    header = ('<table class="metric-table"><thead><tr>'
              '<th>排名</th><th>代码</th><th>名称</th><th>方向</th>'
              '<th>总分</th><th>规则分</th><th>相似分</th><th>相关性</th>'
              '</tr></thead><tbody>%s</tbody></table>' % ''.join(rows)) if rows \
        else '<div class="empty">无命中</div>'
    hits_note = ''
    if n_hits:
        hits_note = ('<div class="note">共 <b>%d</b> 条命中 / <b>%d</b> 类形态。'
                     '方向为该形态的常规含义（看多/看空/中性），不构成买卖建议。</div>'
                     % (n_hits, n_patterns))

    footer_line1 = ('星耀数智形态猎手 · 数据来源：星耀数智（AmazingData，前复权日线） · '
                    '生成于 %s' % datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    charts_json = 'var charts = %s;' % json.dumps(
        _jsonable({'candidates': candidates}), ensure_ascii=False)

    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        html = f.read()
    replacements = {
        '__TITLE__': title,
        '__META_CHIPS__': meta,
        '__KPIS__': kpi_html,
        '__CANDIDATES__': candidates_html,
        '__HITS_TABLE__': header,
        '__HITS_NOTE__': hits_note,
        '__MIN_SCORE__': '%.0f' % min_score,
        '__FOOTER_LINE1__': footer_line1,
        '__CHARTS_JSON__': charts_json,
    }
    for k, v in replacements.items():
        html = html.replace(k, v)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out = os.path.join(OUTPUT_DIR, '%s_%s.html' % (mode, ts))
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    return out
