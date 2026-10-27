# -*- coding: utf-8 -*-
"""
研报摘要查询、机构观点统计、MD保存 — 通用工具

功能: 拉研报摘要 → 列表/统计输出 → 可选逐条存MD → 喂AI精读分析

用法:
    python scripts/search.py --codes 601***.SH                        # 近30天研报摘要
    python scripts/search.py --codes 601***.SH --md                   # +逐条存Markdown
    python scripts/search.py --codes 601***.SH,600***.SH --begin 20260901
    python scripts/search.py --codes 0 --md                           # 无标的研报(宏观/策略等)
"""

import os
import sys
import time
import warnings
from datetime import datetime, timedelta
from typing import List, Optional

warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_provider import DataProvider
from report_fetcher import ReportFetcher


def search(
    codes: List[str],
    begin_date: int = 0,
    end_date: int = 0,
    save_md: bool = False,
    limit: int = 0,
    show_changes: bool = False,
    des_len: int = 0,
    is_local: bool = False,
    local_path: str = 'D:/AmazingData_local_data/',
):
    """拉取研报摘要并输出列表与机构观点统计。

    Args:
        codes: 股票代码列表；['0'] 表示无标的研报
        begin_date: 起始日期 YYYYMMDD，默认近30天
        end_date: 结束日期 YYYYMMDD，默认今天
        save_md: 是否逐条保存为 Markdown（增量，已存在自动跳过）
        limit: 最多显示条数，0=全部
        show_changes: 是否输出评级变动/首次覆盖明细与目标价vs现价对比
        des_len: >0 时列表每条附研报摘要正文前 N 字符（0=不输出）
        is_local: 是否使用本地缓存（默认False，从服务器拉取最新数据）
        local_path: AD 本地数据根目录

    Returns:
        合并后的研报摘要 DataFrame；登录失败或无结果时返回 None
    """
    if not end_date:
        end_date = int(datetime.today().strftime('%Y%m%d'))
    if not begin_date:
        begin_date = int((datetime.today() - timedelta(days=30)).strftime('%Y%m%d'))

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

    print(f'研报摘要: {codes}，区间 {begin_date}-{end_date}', flush=True)

    # ── 拉取 ──
    try:
        fetcher = ReportFetcher(dp, local_path=local_path)
        report_abstract = fetcher.fetch(
            codes,
            begin_date=begin_date,
            end_date=end_date,
            is_local=is_local,
        )
    except SystemExit:
        print('❌ 登录会话失效，请稍后重试', flush=True)
        return None
    except Exception as e:
        print(f'❌ 拉取研报摘要失败: {e}', flush=True)
        return None

    if not report_abstract:
        print('未获取到研报摘要数据', flush=True)
        return None

    all_df = ReportFetcher.merge(report_abstract)
    if all_df.empty:
        print('指定区间内无研报摘要', flush=True)
        return None

    # ── 列表 + 统计 ──
    ReportFetcher.print_list(all_df, limit=limit, des_len=des_len)
    ReportFetcher.print_stats(all_df)

    # ── 变化明细 + 目标价vs现价（投资者视角：关注"变化"与"空间口径"） ──
    if show_changes:
        ReportFetcher.print_changes(all_df)
        try:
            fetcher.print_price_vs_target(all_df)
        except Exception as e:
            print(f'[提示] 目标价对比跳过: {e}', flush=True)

    # ── 保存 Markdown ──
    if save_md:
        print(f'\n保存研报摘要为 Markdown...', flush=True)
        md_dir = fetcher.save_md(report_abstract)
        print(f'MD 目录: {md_dir}', flush=True)
        print(f'AI 可直接读取 MD 文件做精读分析（文件以研报摘要id命名，增量保存）',
              flush=True)

    elapsed = time.time() - t0
    print(f'\n完成 ({elapsed:.0f}s)', flush=True)

    return all_df


if __name__ == '__main__':
    import argparse

    p = argparse.ArgumentParser(description='研报摘要查询、机构观点统计、MD保存')
    p.add_argument('--codes', required=True,
                   help='股票代码，逗号分隔，如 601***.SH,600***.SH；传 0 取无标的研报')
    p.add_argument('--begin', type=int, default=0, help='起始日期 YYYYMMDD，默认近30天')
    p.add_argument('--end', type=int, default=0, help='结束日期 YYYYMMDD，默认今天')
    p.add_argument('--md', action='store_true', help='逐条保存为 Markdown（增量，已存在跳过）')
    p.add_argument('--limit', type=int, default=0, help='最多显示条数，0=全部')
    p.add_argument('--changes', action='store_true',
                   help='输出评级变动/首次覆盖明细与目标价vs现价对比')
    p.add_argument('--des', type=int, nargs='?', const=200, default=0,
                   help='列表每条附研报摘要正文前 N 字符（默认200，如 --des 或 --des 400）')
    p.add_argument('--local', action='store_true', help='使用本地缓存数据（默认从服务器拉取最新）')
    p.add_argument('--local-path', default='D:/AmazingData_local_data/',
                   help='AD 本地数据根目录（默认: D:/AmazingData_local_data/）')

    args = p.parse_args()

    codes = [c.strip() for c in args.codes.split(',') if c.strip()]

    search(
        codes=codes,
        begin_date=args.begin,
        end_date=args.end,
        save_md=args.md,
        limit=args.limit,
        show_changes=args.changes,
        des_len=args.des,
        is_local=args.local,
        local_path=args.local_path,
    )
