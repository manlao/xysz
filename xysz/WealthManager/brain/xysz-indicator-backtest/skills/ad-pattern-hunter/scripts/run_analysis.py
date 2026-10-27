# -*- coding: utf-8 -*-
"""
形态猎手 — 编排入口（三模式 CLI）

用法:
  # 模板雷达扫描
  python run_analysis.py scan --pattern w_bottom --universe index_all --window 120 --top-n 10
  python run_analysis.py scan --pattern all --universe index300

  # 外部轮廓匹配（手绘图提取点列 / AI 生成轮廓，120 点归一化 JSON）
  python run_analysis.py profile --profile points.json --universe index_all --window 120

  # 单票诊断（该股命中哪些形态+评分明细）
  python run_analysis.py check --code 600519.SH --window 120

环境变量: AD_USERNAME / AD_PASSWORD / AD_HOST / AD_PORT
输出: output/pattern_hunter/ 下 HTML 报告 + JSON 结果
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd  # noqa: E402

from pattern_engine import (  # noqa: E402
    PATTERNS, FAMILY_ORDER, TIMEFRAME_AMP, analyze_window, evaluate_pattern,
    resample_profile,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', 'output', 'pattern_hunter'))

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass


# 各周期回溯自然日表：保证拉满窗口 BAR 且分钟周期数据量可控
# （= 120 根 × 每根自然日跨度 × 1.2 + 余量；day 用 1.7×N+40 老公式）
LOOKBACK_DAYS = {
    'min1': 3, 'min3': 5, 'min5': 8, 'min10': 15, 'min15': 22, 'min30': 44,
    'min60': 86, 'min120': 170, 'day': None, 'week': 940, 'month': 3760,
    'season': 5000, 'year': 5000,
}


def _resolve_range(dp, args):
    """确定扫描区间：默认截至最近交易日，回溯长度按周期取表。"""
    end = args.end or dp.latest_trade_day()
    if args.begin:
        begin = args.begin
    else:
        import datetime as _dt
        tf = getattr(args, 'timeframe', 'day') or 'day'
        days = LOOKBACK_DAYS.get(tf)
        if days is None:  # day：回溯约 1.7 倍窗口的自然日
            days = int(args.window * 1.7) + 40
        d = _dt.datetime.strptime(str(end), '%Y%m%d') - _dt.timedelta(days=days)
        begin = int(d.strftime('%Y%m%d'))
    return begin, end


def _fetch_pool(dp, args, begin, end):
    """拉取股票池 K 线 + 前复权。返回 {code: 前复权df}、被跳过数。"""
    tf = getattr(args, 'timeframe', 'day') or 'day'
    codes = args.codes if getattr(args, 'codes', None) else dp.universe_codes(args.universe)
    print('[数据] 拉取 %d 只股票 %s K线 %d~%d ...' % (len(codes), tf, begin, end), flush=True)
    raw = dp.stock_kline_batch(codes, begin, end, timeframe=tf)
    if not raw:
        raise RuntimeError('股票池内未拉到任何 K 线数据')
    print('[数据] 拉到 %d/%d 只，计算前复权因子...' % (len(raw), len(codes)), flush=True)
    bf = dp.backward_factor_batch(list(raw.keys()))
    adjusted = {}
    for code, df in raw.items():
        f = bf[code] if (bf is not None and not bf.empty and code in bf.columns) else None
        adjusted[code] = dp.forward_adjust_ohlc(df, f) if f is not None else df
    return adjusted, len(codes) - len(raw)


def _load_profile(path):
    """读取轮廓 JSON：{"points": [...]} 或裸数组。"""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    points = data.get('points') if isinstance(data, dict) else data
    if points is None:
        raise ValueError('轮廓文件缺少 points 字段')
    return resample_profile(points, 128), (data.get('note', '') if isinstance(data, dict) else '')


# ----------------------------------------------------------------------
# 模式：scan / profile
# ----------------------------------------------------------------------

def run_scan(args, mode='scan'):
    t0 = time.time()
    from data_provider import DataProvider
    dp = DataProvider()
    begin, end = _resolve_range(dp, args)
    klines, skipped = _fetch_pool(dp, args, begin, end)

    profile = note = None
    if mode == 'profile':
        profile, note = _load_profile(args.profile)
        pattern_ids = None
        min_score = args.min_score
    else:
        pattern_ids = list(PATTERNS.keys()) if args.pattern == 'all' else args.pattern.split(',')
        for pid in pattern_ids:
            if pid not in PATTERNS:
                raise ValueError('未知形态: %s（可选: %s 或 all）' % (pid, ','.join(PATTERNS.keys())))
        min_score = args.min_score

    names = dp.stock_names()
    amp = TIMEFRAME_AMP.get(getattr(args, 'timeframe', 'day') or 'day', 1.0)
    min_bars = max(30, int(args.window * 0.8))
    hits_all = []          # (code, result)
    insufficient = 0
    total = len(klines)
    print('[扫描] 开始形态识别（窗口 %d BAR，共 %d 只）...' % (args.window, total), flush=True)
    for i, (code, df) in enumerate(klines.items(), 1):
        if i % 200 == 0 or i == total:
            print('  [进度] %d/%d' % (i, total), flush=True)
        if len(df) < min_bars:
            insufficient += 1
            continue
        win = df.tail(args.window)
        res = analyze_window(win, pattern_ids=pattern_ids,
                             external_profile=profile, min_score=min_score, amp=amp)
        for r in res:
            r['code'] = code
            r['name'] = names.get(code, code)
            hits_all.append((code, r))
    elapsed = time.time() - t0

    # 组装结果
    by_pattern = {}
    if mode == 'scan':
        for code, r in hits_all:
            by_pattern.setdefault(r['pattern_id'], []).append(r)
        for pid, lst in by_pattern.items():
            lst.sort(key=lambda r: -r['score'])
        top_overall = sorted(hits_all, key=lambda cr: -cr[1]['score'])[:args.top_n]
    else:
        lst = [r for _, r in hits_all]
        lst.sort(key=lambda r: -r['score'])
        by_pattern['profile_custom'] = lst
        top_overall = [(r['code'], r) for r in lst[:args.top_n]]

    # 控制台摘要
    mode_cn = '轮廓匹配' if mode == 'profile' else '模板雷达扫描'
    print()
    print('=' * 64)
    print('  形态猎手 · %s' % mode_cn)
    if mode == 'scan':
        ptext = '全部 %d 类' % len(pattern_ids) if args.pattern == 'all' else args.pattern
        print('  周期: %s   形态: %s   股票池: %s   窗口: %d BAR'
              % (getattr(args, 'timeframe', 'day'), ptext, args.universe, args.window))
    else:
        print('  周期: %s   外部轮廓: %s   股票池: %s   窗口: %d BAR'
              % (getattr(args, 'timeframe', 'day'), os.path.basename(args.profile),
                 args.universe, args.window))
    print('  区间: %d ~ %d   数据截止: %d' % (begin, end, dp.latest_trade_day()))
    print('=' * 64)

    print('命中汇总（score≥%.0f）: 共 %d 条命中 / %d 只参与 / %d 只数据不足跳过 / 耗时 %.0f 秒'
          % (min_score, len(hits_all), total - insufficient, insufficient, elapsed))
    if mode == 'scan':
        print('-' * 64)
        fam_of = {pid: PATTERNS[pid].family for pid in by_pattern}
        for fam in FAMILY_ORDER:
            pids = [p for p in by_pattern if fam_of[p] == fam]
            if not pids:
                continue
            for pid in sorted(pids, key=lambda p: -len(by_pattern[p])):
                lst = by_pattern[pid]
                top1 = lst[0]
                print('  [%s] %-12s %-8d只  Top1: %s %s %.1f分'
                      % (fam, PATTERNS[pid].name_zh, len(lst),
                         top1['name'], top1['code'], top1['score']))
    print('-' * 64)
    print('重点候选 Top%d:' % len(top_overall))
    for i, (code, r) in enumerate(top_overall, 1):
        print('  %2d. %.1f分 [%s·%s] %s %s (规则%.0f 相似%.0f)'
              % (i, r['score'], r['pattern_name'], r['direction'],
                 r['name'], code, r['rule_score'], r['sim_score']))

    # 报告与 JSON
    report = None
    try:
        from report_renderer import render_report
        report = render_report(
            mode=mode, args=vars(args), begin=begin, end=end,
            data_date=dp.latest_trade_day(), window=args.window,
            universe=args.universe, elapsed=elapsed, timeframe=getattr(args, 'timeframe', 'day'),
            total_scanned=total - insufficient, insufficient=insufficient,
            min_score=min_score, by_pattern=by_pattern, top_overall=top_overall,
            klines=klines, names=names, profile=profile, profile_note=note,
            pattern_ids=pattern_ids, external_profile=profile)
    except Exception as exc:
        print('[警告] HTML 报告生成失败: %s' % exc, flush=True)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')

    # 全量命中与统计（供阈值回检与后续分析；profile 模式挂在 profile_custom 下）
    all_hits = {pid: [
        {'code': r['code'], 'name': r['name'], 'score': r['score'],
         'rule_score': r['rule_score'], 'sim_score': r['sim_score'], 'corr': r['corr']}
        for r in lst]
        for pid, lst in by_pattern.items()}
    pattern_stats = {}
    for pid, lst in by_pattern.items():
        scores = sorted(r['score'] for r in lst)

        def _pct(p):
            if not scores:
                return None
            k = (len(scores) - 1) * p
            f, c = int(k), min(int(k) + 1, len(scores) - 1)
            return round(scores[f] + (scores[c] - scores[f]) * (k - f), 1)
        pattern_stats[pid] = {
            'count': len(scores),
            'top1': scores[-1] if scores else None,
            'median': _pct(0.5), 'p25': _pct(0.25), 'p75': _pct(0.75),
        }

    json_path = os.path.join(OUTPUT_DIR, '%s_%s.json' % (mode, ts))
    payload = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'mode': mode, 'timeframe': getattr(args, 'timeframe', 'day'),
        'begin': begin, 'end': end, 'window': args.window,
        'universe': args.universe, 'min_score': min_score,
        'total_scanned': total - insufficient, 'insufficient': insufficient,
        'elapsed_sec': round(elapsed, 1),
        'pattern_stats': pattern_stats,
        'top_overall': [
            {'rank': i, 'code': c, 'name': r['name'], 'pattern_id': r['pattern_id'],
             'pattern_name': r['pattern_name'], 'direction': r['direction'],
             'score': r['score'], 'rule_score': r['rule_score'],
             'sim_score': r['sim_score'], 'corr': r['corr'],
             'hits': [{'name': h['name'], 'ok': h['ok'], 'detail': h['detail']}
                      for h in r['hits']]}
            for i, (c, r) in enumerate(top_overall, 1)],
        'all_hits': all_hits,
    }
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print('报告: %s' % (report or '(未生成)'))
    print('JSON: %s' % json_path)
    print('结果仅供形态相似度研究，不构成投资建议。')
    return 0


# ----------------------------------------------------------------------
# 模式：check
# ----------------------------------------------------------------------

def run_check(args):
    t0 = time.time()
    from data_provider import DataProvider
    dp = DataProvider()
    begin, end = _resolve_range(dp, args)
    klines, _ = _fetch_pool(dp, argparse.Namespace(codes=[args.code], universe=None,
                                                   begin=begin, end=end,
                                                   timeframe=getattr(args, 'timeframe', 'day')),
                            begin, end)
    df = klines.get(args.code)
    if df is None or len(df) < max(30, int(args.window * 0.8)):
        print('该股在区间内 K 线不足（%d 根），无法诊断' % (0 if df is None else len(df)))
        return 1
    win = df.tail(args.window)
    names = dp.stock_names()
    name = names.get(args.code, args.code)

    print()
    print('=' * 64)
    print('  形态猎手 · 单票诊断: %s %s' % (name, args.code))
    print('  周期: %s   窗口: 最近 %d 根K线（%s ~ %s），前复权'
          % (getattr(args, 'timeframe', 'day'), len(win),
             win.index[0], win.index[-1]))
    print('=' * 64)

    # 单票诊断：直调 evaluate_pattern，全量展示（不做规则门槛过滤）
    amp = TIMEFRAME_AMP.get(getattr(args, 'timeframe', 'day') or 'day', 1.0)
    res_all = [evaluate_pattern(win, pdef, amp=amp) for pdef in PATTERNS.values()]
    res_all.sort(key=lambda r: -r['score'])
    # 去掉规则门槛的展示限制：直接全量展示，按分数排序
    print('%-14s %-8s %-6s %6s %6s %6s %6s' %
          ('形态', '族', '方向', '总分', '规则', '相似', '相关'))
    for r in res_all:
        print('%-14s %-8s %-6s %6.1f %6.1f %6.1f %6.2f' %
              (r['pattern_name'], r['family'], r['direction'],
               r['score'], r['rule_score'], r['sim_score'], r['corr']))
    if res_all:
        best = res_all[0]
        print('-' * 64)
        print('最匹配: %s（%.1f 分）规则明细:' % (best['pattern_name'], best['score']))
        for h in best['hits']:
            print('  %s %s | %s' % ('✓' if h['ok'] else '✗', h['name'], h['detail']))
    print('耗时 %.1f 秒。结果仅供形态相似度研究，不构成投资建议。' % (time.time() - t0))
    return 0


# ----------------------------------------------------------------------
# argparse
# ----------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog='run_analysis.py', description='星耀数智形态猎手（K线形态识别选股）')
    sub = parser.add_subparsers(dest='command', required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--universe', default='index_all',
                        choices=['index300', 'index500', 'index1000', 'index_all', 'allA'],
                        help='股票池：index300/index500/index1000/index_all=成分股合集/allA=全市场')
    common.add_argument('--window', type=int, default=120, choices=[30, 60, 120],
                        help='匹配窗口（BAR 数），默认 120')
    common.add_argument('--timeframe', default='day',
                        choices=['min1', 'min3', 'min5', 'min10', 'min15', 'min30',
                                 'min60', 'min120', 'day', 'week', 'month', 'season', 'year'],
                        help='K线周期，默认 day；幅度阈值按周期经验缩放')
    common.add_argument('--top-n', type=int, default=10, help='重点候选数量，默认 10')
    common.add_argument('--min-score', type=float, default=50.0,
                        help='命中分数线（0-100），默认 50')
    common.add_argument('--begin', type=int, default=None, help='起始日期 YYYYMMDD，默认近一年')
    common.add_argument('--end', type=int, default=None, help='截止日期 YYYYMMDD，默认最近交易日')

    p_scan = sub.add_parser('scan', parents=[common], help='模板雷达扫描')
    p_scan.add_argument('--pattern', default='all',
                        help='形态ID（逗号分隔多个）或 all，如 w_bottom / all / '
                             'w_bottom,m_top,strong_trend')

    p_profile = sub.add_parser('profile', parents=[common], help='外部轮廓匹配')
    p_profile.add_argument('--profile', required=True,
                           help='轮廓 JSON 路径（{"points":[...]} 或裸数组，≥8 个点）')

    p_check = sub.add_parser('check', parents=[common], help='单票诊断')
    p_check.add_argument('--code', required=True, help='股票代码，如 600519.SH')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == 'scan':
        return run_scan(args, mode='scan')
    if args.command == 'profile':
        return run_scan(args, mode='profile')
    if args.command == 'check':
        return run_check(args)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
