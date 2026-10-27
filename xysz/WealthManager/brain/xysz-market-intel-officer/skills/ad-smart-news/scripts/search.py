# -*- coding: utf-8 -*-
"""
个股新闻查询、去重归并、客观统计 — 通用工具

功能: 拉新闻 → 多源去重 → 主题初分类 → 统计概览 → 喂AI做事实性整理

用法:
    python scripts/search.py --codes 601***.SH                        # 近7天新闻
    python scripts/search.py --codes 601***.SH --begin 20260901
    python scripts/search.py --codes 601***.SH,600***.SH --limit 50
"""

import os
import sys
import time
import warnings
from datetime import datetime, timedelta
from typing import List

warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_provider import DataProvider
from news_fetcher import NewsFetcher


def search(
    codes: List[str],
    begin_date: int = 0,
    end_date: int = 0,
    limit: int = 0,
    topics: List[str] = None,
    prev_compare: bool = False,
    is_local: bool = False,
    local_path: str = 'D:/AmazingData_local_data/',
):
    """拉取个股新闻并输出去重列表与统计概览。

    Args:
        codes: 股票代码列表
        begin_date: 起始日期 YYYYMMDD，默认近7天
        end_date: 结束日期 YYYYMMDD，默认今天
        limit: 最多显示条数，0=全部
        topics: 主题过滤列表（如 ['增减持','监管处罚']），空=不过滤
        prev_compare: 是否输出舆情热度环比（本期 vs 上一等长区间，纯计数）
        is_local: 是否使用本地缓存（默认False，从服务器拉取最新数据）
        local_path: AD 本地数据根目录

    Returns:
        去重后的新闻 DataFrame；登录失败或无结果时返回 None
    """
    if not end_date:
        end_date = int(datetime.today().strftime('%Y%m%d'))
    if not begin_date:
        begin_date = int((datetime.today() - timedelta(days=7)).strftime('%Y%m%d'))

    # 注意：AD 内部对 local_path 做字符串直接拼接，必须保留尾部斜杠
    local_path = local_path.replace('\\', '/')
    if not local_path.endswith('/'):
        local_path += '/'
    t0 = time.time()

    # ── 登录 ──
    try:
        dp = DataProvider()
    except (ConnectionError, EnvironmentError) as e:
        print(f'❌ {e}', flush=True)
        return None

    # ── 全市场模式：先取全部A股代码，再分批拉新闻 ──
    if any(c.strip().lower() in ('all', '全市场') for c in codes):
        codes = dp.get_stock_list()
        print(f'全市场模式: 获取A股代码 {len(codes)} 只', flush=True)

    print(f'新闻查询: {codes if len(codes) <= 5 else f"{len(codes)} 只代码"}，区间 {begin_date}-{end_date}', flush=True)

    # ── 拉取（两步式：列表 -> 详情+html，接口自动增量下载） ──
    try:
        fetcher = NewsFetcher(dp, local_path=local_path)
        raw_df, news_html_dir = fetcher.fetch(
            codes,
            begin_date=begin_date,
            end_date=end_date,
            is_local=is_local,
        )
    except SystemExit:
        print('❌ 登录会话失效，请稍后重试', flush=True)
        return None
    except Exception as e:
        print(f'❌ 拉取新闻失败: {e}', flush=True)
        return None

    if raw_df is None or raw_df.empty:
        print('指定区间内无新闻', flush=True)
        return None

    # ── 去重 + 主题 ──
    dedup_df = NewsFetcher.dedup(raw_df)
    dedup_df = NewsFetcher.add_topic(dedup_df)

    # ── 统计概览（用全量去重结果，先于主题过滤，保证口径完整） ──
    NewsFetcher.print_stats(raw_df, dedup_df)

    # ── 主题过滤（只影响列表展示，不改统计口径） ──
    if topics:
        before = len(dedup_df)
        dedup_df = NewsFetcher.filter_topic(dedup_df, topics)
        print(f'\n主题过滤 {topics}: {before} 条 → {len(dedup_df)} 条（以下列表仅显示匹配项，'
              f'统计概览仍为全量口径）', flush=True)
        if dedup_df.empty:
            print('过滤后无匹配新闻（可用主题见统计概览的主题分布）', flush=True)
            return None

    # 全市场/大批量时列表默认只显示前 50 条，避免刷屏
    if limit <= 0 and len(codes) > 100:
        limit = 50
        print('全市场模式列表较长，默认显示前 50 条（可用 --limit 调整，统计概览为全量）',
              flush=True)

    NewsFetcher.print_list(dedup_df, limit=limit)

    # ── 舆情热度环比（可选：对比上一等长区间报道量，纯计数，只拉列表不下载详情） ──
    if prev_compare:
        try:
            begin_dt = datetime.strptime(str(begin_date), '%Y%m%d')
            end_dt = datetime.strptime(str(end_date), '%Y%m%d')
            span = (end_dt - begin_dt).days + 1
            prev_end = begin_dt - timedelta(days=1)
            prev_begin = prev_end - timedelta(days=span - 1)
            cur_cnt = int(raw_df['news_id'].astype(str).nunique()) \
                if 'news_id' in raw_df.columns else len(raw_df)
            prev_cnt = fetcher.count_unique_news(
                codes,
                begin_date=int(prev_begin.strftime('%Y%m%d')),
                end_date=int(prev_end.strftime('%Y%m%d')),
                is_local=is_local,
            )
            diff = cur_cnt - prev_cnt
            pct = f'（{diff / prev_cnt:+.0%}）' if prev_cnt else ''
            print('\n─── 舆情热度环比（纯计数，按去重新闻id） ───', flush=True)
            print(f'本期 {begin_date}-{end_date}: {cur_cnt} 条', flush=True)
            print(f'上期 {prev_begin:%Y%m%d}-{prev_end:%Y%m%d}: {prev_cnt} 条', flush=True)
            print(f'环比: {diff:+d} 条{pct}', flush=True)
        except Exception as e:
            print(f'[提示] 热度环比计算失败: {e}', flush=True)

    # ── 原文目录 ──
    if news_html_dir:
        print(f'\n新闻原文 html 目录: {news_html_dir}', flush=True)
        print(f'AI 需要原文细节时可直接读取该目录下的 html 文件（以新闻id命名）', flush=True)

    elapsed = time.time() - t0
    print(f'\n完成 ({elapsed:.0f}s)', flush=True)

    return dedup_df


if __name__ == '__main__':
    import argparse

    p = argparse.ArgumentParser(description='个股新闻查询、去重归并、客观统计')
    p.add_argument('--codes', required=True,
                   help='股票代码，逗号分隔，如 601***.SH,600***.SH；传 all/全市场 取全部A股（先取代码再分批拉取）')
    p.add_argument('--begin', type=int, default=0, help='起始日期 YYYYMMDD，默认近7天')
    p.add_argument('--end', type=int, default=0, help='结束日期 YYYYMMDD，默认今天')
    p.add_argument('--limit', type=int, default=0, help='最多显示条数，0=全部')
    p.add_argument('--topic', default='',
                   help='按主题过滤，逗号分隔，如: 增减持,监管处罚（可选主题见主题分布）')
    p.add_argument('--prev', action='store_true',
                   help='输出舆情热度环比：对比上一等长区间的报道量（纯计数）')
    p.add_argument('--local', action='store_true', help='使用本地缓存数据（默认从服务器拉取最新）')
    p.add_argument('--local-path', default='D:/AmazingData_local_data/',
                   help='AD 本地数据根目录（默认: D:/AmazingData_local_data/）')

    args = p.parse_args()

    codes = [c.strip() for c in args.codes.split(',') if c.strip()]

    search(
        codes=codes,
        begin_date=args.begin,
        end_date=args.end,
        limit=args.limit,
        topics=[t.strip() for t in args.topic.split(',') if t.strip()] if args.topic else None,
        prev_compare=args.prev,
        is_local=args.local,
        local_path=args.local_path,
    )
