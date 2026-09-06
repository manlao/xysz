# -*- coding: utf-8 -*-
"""
公告数据获取模块 - 按TAG筛选、下载PDF

支持上市公司(stock)、基金ETF(fund)、可转债(bond)三种公告类型。
TAG_ID 由 AI 查 references/announcement_categories.md 后传入。
"""

import os
import warnings
from typing import Dict, List, Optional

warnings.filterwarnings('ignore')

import pandas as pd

from data_provider import DataProvider

ANNOUNCEMENT_TYPES = {
    'stock': {
        'label': '上市公司公告',
        'list_method': 'get_announcement_stock_list',
        'download_method': 'get_announcement_stock',
    },
    'fund': {
        'label': 'ETF公告',
        'list_method': 'get_announcement_fund_list',
        'download_method': 'get_announcement_fund',
    },
    'bond': {
        'label': '可转债公告',
        'list_method': 'get_announcement_bond_list',
        'download_method': 'get_announcement_bond',
    },
}


class AnnouncementFetcher:
    """公告数据获取器。"""

    def __init__(
        self,
        announcement_type: str = 'stock',
        data_provider: Optional[DataProvider] = None,
        local_path: str = 'D:/AmazingData_local_data/',
    ):
        if announcement_type not in ANNOUNCEMENT_TYPES:
            raise ValueError(
                f"不支持的公告类型: {announcement_type}，可选: {list(ANNOUNCEMENT_TYPES.keys())}"
            )
        self.announcement_type = announcement_type
        self.type_config = ANNOUNCEMENT_TYPES[announcement_type]
        self.local_path = local_path
        if not self.local_path.endswith('/') and not self.local_path.endswith('\\'):
            self.local_path += '/'
        self.dp = data_provider or DataProvider()
        os.makedirs(self.local_path, exist_ok=True)

    def search(
        self,
        code_list: List[str],
        begin_date: int,
        end_date: int,
        tag_ids: Optional[List[str]] = None,
        is_local: bool = True,
    ) -> pd.DataFrame:
        """按 TAG_ID 搜索公告。

        Args:
            code_list: 代码列表
            begin_date: 起始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD
            tag_ids: TAG_ID 前缀列表，如 ['10301']，None=全部
            is_local: 是否使用本地缓存

        Returns:
            DataFrame，含 MARKET_CODE, SOURCE_ID, TITLE, TAG_ID, TAG_NAME, PUBLISH_TIME 等
        """
        label = self.type_config['label']
        print(f"\n{'='*60}", flush=True)
        print(f"[AnnouncementFetcher] {label} 搜索 (TAG: {tag_ids})", flush=True)
        print(f"{'='*60}", flush=True)

        # 调用 API
        list_method = getattr(self.dp.info_data, self.type_config['list_method'])

        if is_local:
            df = list_method(code_list=code_list, is_local=True, local_path=self.local_path)
        else:
            df = list_method(code_list=code_list, is_local=False, local_path=self.local_path,
                             begin_date=begin_date, end_date=end_date)

        if df is None or len(df) == 0:
            print(f"  ⚠ 未找到公告数据", flush=True)
            return pd.DataFrame()

        print(f"  原始命中: {len(df)} 条", flush=True)

        # TAG 筛选
        if tag_ids:
            tag_col = 'TAG_ID' if 'TAG_ID' in df.columns else None
            if tag_col:
                mask = pd.Series(False, index=df.index)
                tag_id_series = df[tag_col].astype(str)
                for tid in tag_ids:
                    mask |= tag_id_series.str.contains(r'(?:^|\|)' + str(tid))
                df = df[mask]
                print(f"  TAG 筛选: {len(df)} 条", flush=True)

        # 日期筛选
        if 'PUBLISH_TIME' in df.columns:
            df['_date'] = pd.to_numeric(
                df['PUBLISH_TIME'].str.replace('-', '').str[:8],
                errors='coerce',
            )
            df = df[(df['_date'] >= begin_date) & (df['_date'] <= end_date)]
            df = df.drop(columns=['_date'])
            print(f"  日期筛选: {len(df)} 条", flush=True)

        print(f"  ✅ 最终命中: {len(df)} 条", flush=True)
        return df.reset_index(drop=True)

    def download_pdfs(
        self,
        announcement_df: pd.DataFrame,
        begin_date: int = 19900101,
        end_date: int = 20980101,
    ) -> Dict[str, str]:
        """下载公告 PDF 原文（由 AD 管理存储路径，按 stock/fund/bond 分目录）。

        Returns:
            Dict[str, str]: {SOURCE_ID: PDF本地文件路径}
        """
        label = self.type_config['label']
        print(f"\n{'='*60}", flush=True)
        print(f"[AnnouncementFetcher] 下载 {label} PDF", flush=True)
        print(f"{'='*60}", flush=True)

        if announcement_df.empty:
            print("  ⚠ 无公告数据，跳过下载", flush=True)
            return {}

        download_method = getattr(self.dp.info_data, self.type_config['download_method'])

        try:
            pdf_paths, filtered_df = download_method(
                announcement_df,
                tag_id_list=None,
                begin_date=begin_date,
                end_date=end_date,
                local_path=self.local_path,
            )
        except Exception as e:
            print(f"  ❌ PDF下载失败: {e}", flush=True)
            return {}

        if pdf_paths is None:
            pdf_paths = {}

        valid = {}
        for source_id, path in pdf_paths.items():
            if os.path.exists(path):
                valid[source_id] = path
            else:
                print(f"  ⚠ 文件不存在: {source_id}", flush=True)

        print(f"  下载: {len(valid)} 篇", flush=True)
        return valid
