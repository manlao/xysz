# -*- coding: utf-8 -*-
"""
上市公司公告搜索、下载、转MD — 通用工具

功能: 搜公告 → 下PDF → 转MD → 喂AI分析

用法:
    python scripts/search.py --tag 10301                       # 业绩预告
    python scripts/search.py --tag 10301 --pdf                 # +下载PDF转MD
    python scripts/search.py --tag 10301 --limit 50            # 只显示前50条
    python scripts/search.py --type bond --tag 10408           # 可转债回购
    python scripts/search.py --codes 600***.SH,601***.SH --tag 10301 --pdf
"""

import os
import sys
import time
import warnings
from datetime import datetime
from typing import List, Optional

warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_provider import DataProvider
from announcement_fetcher import AnnouncementFetcher

# 标的类型 → AD 枚举
ASSET_TYPES = {
    'stock': {'label': '股票', 'enum': 'EXTRA_STOCK_A_SH_SZ'},
    'fund':  {'label': 'ETF',  'enum': 'EXTRA_ETF'},
    'bond':  {'label': '可转债', 'enum': 'EXTRA_KZZ'},
}

def search(
    tag: str,
    asset_type: str = 'stock',
    codes: Optional[List[str]] = None,
    begin_date: int = 0,
    end_date: int = 0,
    download_pdf: bool = False,
    limit: int = 0,
    is_local: bool = False,
    local_path: str = 'D:/AmazingData_local_data/',
):
    """搜索公告并下载PDF转MD。

    Args:
        tag: TAG_ID，如 '10301'=业绩预告, '10408'=回购
        asset_type: stock/fund/bond
        codes: 指定代码列表，None=全市场
        begin_date: 起始日期 YYYYMMDD，默认今年元旦
        end_date: 结束日期 YYYYMMDD，默认今天
        download_pdf: 是否下载PDF并转MD
        limit: 最多显示条数，0=全部
        is_local: 是否使用本地缓存（默认False，从服务器拉取最新数据）
        local_path: AD 本地数据根目录，PDF/MD 自动存到其 infodata/announcement 子目录

    Returns:
        DataFrame，含公告列表；登录失败或无结果时返回 None
    """
    if not end_date:
        end_date = int(datetime.today().strftime('%Y%m%d'))
    if not begin_date:
        begin_date = int(f'{datetime.today().year}0101')

    # 子目录不可配置：PDF 由 AD 管理，MD 按类型分目录
    local_path = local_path.rstrip('/').rstrip('\\')
    md_dir = os.path.join(local_path, 'infodata', 'announcement', 'md', asset_type)

    t0 = time.time()
    cfg = ASSET_TYPES[asset_type]

    # ── 登录 + 获取代码列表 ──
    try:
        dp = DataProvider()
    except (ConnectionError, EnvironmentError) as e:
        print(f'❌ {e}', flush=True)
        return None

    if codes:
        code_list = codes
    else:
        print('正在获取全市场代码列表...', flush=True)
        code_list = dp.get_code_list(cfg['enum'])
    print(f'{cfg["label"]}代码: {len(code_list)} 只', flush=True)

    # ── 搜索 ──
    fetcher = AnnouncementFetcher(asset_type, dp, local_path=local_path)
    df = fetcher.search(code_list, begin_date, end_date, tag_ids=[tag], is_local=is_local)

    if df.empty:
        print(f'未找到匹配的{cfg["label"]}公告 (TAG {tag})', flush=True)
        return None

    tc = 'TITLE' if 'TITLE' in df.columns else 'title'

    # ── 保存搜索结果 ──
    pickle_name = f'results_{asset_type}_{tag}_{begin_date}_{end_date}.pkl'
    pickle_path = os.path.join(local_path, 'infodata', 'announcement', pickle_name)
    os.makedirs(os.path.dirname(pickle_path), exist_ok=True)
    df.to_pickle(pickle_path)
    print(f'搜索结果已保存: {pickle_path}', flush=True)

    # ── 列表 ──
    display_count = min(limit, len(df)) if limit > 0 else len(df)
    print(f'\n命中 {len(df)} 条' + (f'（显示前 {display_count} 条）:' if limit > 0 else ':'), flush=True)
    print(flush=True)
    for _, row in df.head(display_count).iterrows():
        print(f'  [{row.get("MARKET_CODE", "")}] {row.get(tc, "")[:90]}', flush=True)

    # ── PDF下载 + MD转换 ──
    if download_pdf:
        print(f'\n下载 PDF 并转 MD...', flush=True)
        pdfs = fetcher.download_pdfs(df, begin_date=begin_date, end_date=end_date)
        print(f'PDF: {len(pdfs)} 篇（由 AD 管理路径）', flush=True)

        if pdfs:
            from pdf_converter import PdfConverter
            conv = PdfConverter(
                output_dir=md_dir,
                error_log=os.path.join(md_dir, 'convert_errors.log'),
            )
            mds = conv.convert_batch(pdfs, skip_existing=True, max_workers=4)
            print(f'MD:  {len(mds)} 篇 → {md_dir}', flush=True)
            print(f'\nAI 可直接读取 MD 文件进行分析:\n', flush=True)
            for sid, path in mds.items():
                print(f'  {path}', flush=True)

    elapsed = time.time() - t0
    print(f'\n完成 ({elapsed:.0f}s)', flush=True)

    return df


if __name__ == '__main__':
    import argparse

    p = argparse.ArgumentParser(description='上市公司公告搜索、下载、转MD')
    p.add_argument('--tag', required=True, help='TAG_ID（必传），查 references/announcement_categories.md')
    p.add_argument('--type', choices=['stock', 'fund', 'bond'], default='stock',
                   help='标的类型 (默认: stock)')
    p.add_argument('--codes', help='指定代码，逗号分隔，不传=全市场')
    p.add_argument('--begin', type=int, default=0, help='起始日期 YYYYMMDD，默认今年元旦')
    p.add_argument('--end', type=int, default=0, help='结束日期 YYYYMMDD，默认今天')
    p.add_argument('--pdf', action='store_true', help='下载 PDF 并转 MD')
    p.add_argument('--limit', type=int, default=0, help='最多显示条数，0=全部')
    p.add_argument('--local', action='store_true', help='使用本地缓存数据（默认从服务器拉取最新）')
    p.add_argument('--local-path', default='D:/AmazingData_local_data/',
                   help='AD 本地数据根目录（默认: D:/AmazingData_local_data/）')

    args = p.parse_args()

    codes = None
    if args.codes:
        codes = [c.strip() for c in args.codes.split(',') if c.strip()]

    search(
        tag=args.tag,
        asset_type=args.type,
        codes=codes,
        begin_date=args.begin,
        end_date=args.end,
        download_pdf=args.pdf,
        limit=args.limit,
        is_local=args.local,
        local_path=args.local_path,
    )
