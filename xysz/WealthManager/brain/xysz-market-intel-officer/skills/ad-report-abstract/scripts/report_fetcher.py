# -*- coding: utf-8 -*-
"""
研报摘要数据获取与机构观点统计模块

封装 AmazingData InfoData.get_report_abstract / save_report_abstract_md，
提供研报摘要拉取、列表输出、机构观点客观统计（评级分布/评级变动/目标价统计）。
仅做事实性转述与计数，不含任何倾向性判断。
"""

import re
import warnings
from typing import Dict, List, Optional

warnings.filterwarnings('ignore')

import pandas as pd


class ReportFetcher:
    """研报摘要获取器。

    通过 DataProvider 登录后，拉取指定股票的研报摘要数据，
    并生成机构观点的客观统计。
    """

    def __init__(self, dp, local_path: str = 'D:/AmazingData_local_data/'):
        """
        Args:
            dp: DataProvider 实例（已登录）
            local_path: AD 本地数据根目录
        """
        self._dp = dp
        self._local_path = local_path

    def fetch(
        self,
        code_list: List[str],
        begin_date: Optional[int] = None,
        end_date: Optional[int] = None,
        is_local: bool = False,
    ) -> Dict[str, pd.DataFrame]:
        """拉取研报摘要数据。

        Args:
            code_list: 股票代码列表，如 ['600***.SH']；传 ['0'] 取无标的研报
            begin_date: 研报发布起始日期 YYYYMMDD，None=不筛选
            end_date: 研报发布结束日期 YYYYMMDD，None=不筛选
            is_local: True=使用本地缓存，False=从服务器拉取

        Returns:
            dict: key 为股票代码，value 为研报摘要 DataFrame
        """
        kwargs = {}
        if begin_date:
            kwargs['begin_date'] = begin_date
        if end_date:
            kwargs['end_date'] = end_date
        report_abstract = self._dp.info_data.get_report_abstract(
            code_list,
            local_path=self._local_path,
            is_local=is_local,
            **kwargs,
        )
        return report_abstract

    def save_md(self, report_abstract: Dict[str, pd.DataFrame]) -> str:
        """将研报摘要逐条保存为 Markdown（增量，已存在自动跳过）。

        Args:
            report_abstract: fetch() 的返回值

        Returns:
            str: Markdown 文件的本地存储目录
        """
        return self._dp.info_data.save_report_abstract_md(
            report_abstract, local_path=self._local_path)

    @staticmethod
    def merge(report_abstract: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """合并多代码的研报摘要为一个 DataFrame，附加 stock 列。"""
        frames = []
        for code, df in report_abstract.items():
            if df is None or df.empty:
                continue
            d = df.copy()
            d['stock'] = code
            frames.append(d)
        if not frames:
            return pd.DataFrame()
        all_df = pd.concat(frames, ignore_index=True)
        # 按发布日期倒序
        if 'date' in all_df.columns:
            all_df = all_df.sort_values('date', ascending=False).reset_index(drop=True)
        return all_df

    @staticmethod
    def print_list(df: pd.DataFrame, limit: int = 0, des_len: int = 0):
        """打印研报列表。

        Args:
            des_len: >0 时每条附研报摘要正文（des）前 N 字符——摘要是最核心的
                内容，供 AI 不落盘直接精读；0=不输出（默认，保持列表简洁）。
        """
        n = len(df)
        display = df.head(limit) if limit > 0 else df
        print(f'\n共 {n} 条研报' + (f'（显示前 {min(limit, n)} 条）:' if limit > 0 else ':'), flush=True)
        print(flush=True)
        for _, row in display.iterrows():
            date = str(row.get('date', ''))[:10]
            title = str(row.get('title', ''))[:60]
            source = str(row.get('source', ''))[:12]
            author = str(row.get('author', ''))[:10]
            bcpj = ReportFetcher._label(row.get('bcpj'))
            pjbh = ReportFetcher._label(row.get('pjbh'))
            prmin = row.get('prmin')
            prmax = row.get('prmax')
            if pd.notna(prmin) and pd.notna(prmax) and prmin and prmax:
                try:
                    lo, hi = float(prmin), float(prmax)
                    price = f'{lo:.2f}' if lo == hi else f'{lo:.2f}-{hi:.2f}'
                except (TypeError, ValueError):
                    price = ReportFetcher._label(prmin) if str(prmin) == str(prmax) \
                        else f'{ReportFetcher._label(prmin)}-{ReportFetcher._label(prmax)}'
            else:
                price = '-'
            classify = str(row.get('classify', ''))[:8]
            stock = str(row.get('stock', ''))
            rid = str(row.get('id', ''))
            print(f'  [{date}] {title}', flush=True)
            print(f'      id:{rid} | {stock} | {source} | {author} | 评级:{bcpj} '
                  f'| 变动:{pjbh} | 目标价:{price} | {classify}', flush=True)
            if des_len > 0 and 'des' in df.columns:
                des = ReportFetcher._label(row.get('des'))
                if des != '-':
                    des = re.sub(r'\s+', ' ', des).strip()
                    if len(des) > des_len:
                        des = des[:des_len] + '…'
                    print(f'      摘要: {des}', flush=True)

    @staticmethod
    def _label(v) -> str:
        """NaN/None/空串统一显示 '-'。"""
        return '-' if (v is None or (isinstance(v, float) and pd.isna(v))
                       or str(v).strip() == '' or str(v) == 'nan') else str(v)

    @staticmethod
    def print_changes(df: pd.DataFrame):
        """打印评级变动与首次覆盖明细（纯转述，投资者关注"变化"）。

        pjbh 含"首次"的归入首次覆盖；上调/下调等归入评级变动；
        "维持"不属于变动，仅在统计概览的评级变动分布中计数，明细里提示篇数。
        """
        if df.empty or 'pjbh' not in df.columns:
            return
        pjbh = df['pjbh'].apply(ReportFetcher._label)
        valid = df[pjbh != '-'].copy()
        if valid.empty:
            print('\n区间内无评级变动/首次覆盖研报', flush=True)
            return

        is_first = valid['pjbh'].astype(str).str.contains('首次', na=False)
        is_keep = valid['pjbh'].astype(str).str.contains('维持', na=False)
        changes = valid[~is_first & ~is_keep]
        firsts = valid[is_first]
        kept_n = int(is_keep.sum())

        def _price(row):
            prmin, prmax = row.get('prmin'), row.get('prmax')
            if pd.notna(prmin) and pd.notna(prmax) and prmin and prmax:
                try:
                    lo, hi = float(prmin), float(prmax)
                    if lo == hi:
                        return f'{lo:.2f}'
                    return f'{lo:.2f}-{hi:.2f}'
                except (TypeError, ValueError):
                    return ReportFetcher._label(prmin) if str(prmin) == str(prmax) \
                        else f'{ReportFetcher._label(prmin)}-{ReportFetcher._label(prmax)}'
            return '-'

        def _line(row):
            return (f"  [{str(row.get('date', ''))[:10]}] {str(row.get('title', ''))[:45]}\n"
                    f"      {ReportFetcher._label(row.get('source'))} | "
                    f"评级:{ReportFetcher._label(row.get('bcpj'))} | "
                    f"变动:{ReportFetcher._label(row.get('pjbh'))} | 目标价:{_price(row)}")

        print(f'\n─── 评级变动明细（{len(changes)} 篇；另有 {kept_n} 篇"维持"，'
              f'已计入统计概览的评级变动分布）───', flush=True)
        if changes.empty:
            print('  无', flush=True)
        else:
            for _, row in changes.sort_values('date', ascending=False).iterrows():
                print(_line(row), flush=True)

        print(f'\n─── 首次覆盖（{len(firsts)} 篇）───', flush=True)
        if firsts.empty:
            print('  无', flush=True)
        else:
            for _, row in firsts.sort_values('date', ascending=False).iterrows():
                print(_line(row), flush=True)

    def print_price_vs_target(self, df: pd.DataFrame):
        """目标价中位数与最新收盘价的算术对比（纯计算事实，非投资建议）。

        现价来自 AD 日线最新收盘；比值 = 目标价中位数 / 现价。
        获取失败自动降级跳过，不影响主流程。
        """
        import AmazingData as ad
        from datetime import datetime, timedelta

        if df.empty or 'prmin' not in df.columns or 'prmax' not in df.columns:
            return
        codes = [str(c) for c in df['stock'].dropna().unique().tolist()
                 if str(c).strip() not in ('', '0')]
        if not codes:
            return

        # 每只股票的目标价上下限中点中位数
        per_stock = {}
        for code in codes:
            sub = df[df['stock'] == code]
            pr = sub[['prmin', 'prmax']].apply(pd.to_numeric, errors='coerce').dropna()
            if not pr.empty:
                per_stock[code] = float(((pr['prmin'] + pr['prmax']) / 2).median())
        if not per_stock:
            return

        try:
            cal = self._dp.base_data.get_calendar()
            market = ad.MarketData(cal)
            end = int(datetime.today().strftime('%Y%m%d'))
            begin = int((datetime.today() - timedelta(days=15)).strftime('%Y%m%d'))
            kline_dict = market.query_kline(
                code_list=list(per_stock.keys()),
                begin_date=begin, end_date=end,
                period=ad.constant.Period.day.value,
            )
        except Exception as e:
            print(f'\n[提示] 现价获取失败，跳过目标价对比: {e}', flush=True)
            return

        lines = []
        for code, target in per_stock.items():
            kdf = kline_dict.get(code) if kline_dict else None
            if kdf is None or getattr(kdf, 'empty', True) or 'close' not in kdf.columns:
                continue
            last = kdf.iloc[-1]
            close = float(last['close'])
            if not close:
                continue
            kdate = str(last.get('kline_time', ''))[:10]
            ratio = target / close
            lines.append(f'  {code}: 现价 {close:.2f}（{kdate}收盘），'
                         f'目标价中位数 {target:.2f}，比值 {ratio:.2f}')
        if not lines:
            return
        print('\n─── 目标价 vs 现价（算术对比，非投资建议）───', flush=True)
        for ln in lines:
            print(ln, flush=True)
        print('注: 比值 = 目标价中位数/最新收盘价，为机构观点与市场数据的计算对比', flush=True)

    @staticmethod
    def print_stats(df: pd.DataFrame):
        """打印机构观点客观统计（纯计数与转述，不含判断）。"""
        print(f'\n─── 机构观点统计 ───', flush=True)

        # 覆盖机构
        sources = df['source'].dropna().astype(str).str.strip()
        sources = sources[sources != '']
        print(f'覆盖机构: {sources.nunique()} 家', flush=True)

        # 评级分布
        if 'bcpj' in df.columns:
            bcpj = df['bcpj'].dropna().astype(str).str.strip()
            bcpj = bcpj[bcpj != '']
            if not bcpj.empty:
                dist = bcpj.value_counts()
                parts = '，'.join(f'{k} {v} 篇' for k, v in dist.items())
                print(f'评级分布: {parts}', flush=True)

        # 评级变动
        if 'pjbh' in df.columns:
            pjbh = df['pjbh'].dropna().astype(str).str.strip()
            pjbh = pjbh[pjbh != '']
            if not pjbh.empty:
                dist = pjbh.value_counts()
                parts = '，'.join(f'{k} {v} 篇' for k, v in dist.items())
                print(f'评级变动: {parts}', flush=True)

        # 目标价统计
        if 'prmin' in df.columns and 'prmax' in df.columns:
            pr = df[['prmin', 'prmax']].apply(pd.to_numeric, errors='coerce').dropna()
            if not pr.empty:
                mid = ((pr['prmin'] + pr['prmax']) / 2)
                print(f'目标价: 最低 {pr["prmin"].min():.2f}，最高 {pr["prmax"].max():.2f}，'
                      f'均值 {mid.mean():.2f}，中位数 {mid.median():.2f}（{len(pr)} 篇给出）',
                      flush=True)

        # 研报类型
        if 'classify' in df.columns:
            cls = df['classify'].dropna().astype(str).str.strip()
            cls = cls[cls != '']
            if not cls.empty:
                dist = cls.value_counts()
                parts = '，'.join(f'{k} {v} 篇' for k, v in dist.items())
                print(f'研报类型: {parts}', flush=True)

        # 观点共识度（纯计数：评级TOP1占比 + 目标价跨度，多股票时按股票分行）
        has_price_cols = 'prmin' in df.columns and 'prmax' in df.columns
        stock_keys = (df['stock'].dropna().unique().tolist()
                      if 'stock' in df.columns else [None])
        multi = len(stock_keys) > 1
        for stock in stock_keys:
            sub = df if stock is None else df[df['stock'] == stock]
            tag = f'{stock}: ' if multi else ''
            if 'bcpj' in sub.columns:
                bcpj = sub['bcpj'].apply(ReportFetcher._label)
                bcpj = bcpj[bcpj != '-']
                if not bcpj.empty:
                    vc = bcpj.value_counts()
                    top1_n = int(vc.iloc[0])
                    print(f'{tag}观点共识度: 评级TOP1「{vc.index[0]}」'
                          f'{top1_n}/{vc.sum()} 篇（{top1_n / vc.sum():.0%}）', flush=True)
            if has_price_cols:
                pr = sub[['prmin', 'prmax']].apply(pd.to_numeric, errors='coerce').dropna()
                if len(pr) >= 2:
                    lo, hi = float(pr['prmin'].min()), float(pr['prmax'].max())
                    if lo > 0 and hi > 0:
                        print(f'{tag}目标价分歧跨度: {lo:.2f}~{hi:.2f}'
                              f'（max/min={hi / lo:.2f}，{len(pr)} 篇给价）', flush=True)
