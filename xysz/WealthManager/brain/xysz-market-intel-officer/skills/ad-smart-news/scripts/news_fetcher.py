# -*- coding: utf-8 -*-
"""
新闻数据获取、去重归并与客观统计模块

封装 AmazingData 新闻接口（两步式，手册 §3.5.18）：
    get_news_list 拉新闻列表（news_id/stock_code/create_date/data_status）
    -> get_news_detail_html 下载新闻详情并保存为 html 文件（title/摘要/来源/
       作者/发布时间/新闻范围等元信息与正文合并嵌入 html，增量跳过已存在）
    -> 解析本次新闻的 html 元信息合并出明细 DataFrame 提供去重、统计。

纯事实层：只整理"谁、何时、何事"，不做任何倾向性判断。
"""

import os
import re
import time
import warnings
from typing import Dict, List, Optional, Tuple

warnings.filterwarnings('ignore')

import pandas as pd

# ranges 字段含义（据开发手册，0-无/1-按全市场/2-按行业/3-按个股）
RANGES_LABEL = {0: '无', 1: '全市场', 2: '行业', 3: '个股'}
# html 元信息"新闻范围"文字 -> 数值（get_news_detail_html 生成）
RANGES_TEXT = {'无': 0, '按全市场': 1, '按行业': 2, '按个股': 3}

# 事实性主题关键词规则（打不准标"其他"，留给AI精分）
# 高管变动按动作词匹配（辞职/聘任等），不用"董事长"等人物词，避免"董事长出席活动"误命中
TOPIC_RULES = [
    ('业绩披露', ['业绩预告', '业绩快报', '季报', '年报', '半年报', '三季报', '中报',
               '中报点评', '半年报点评', '预增', '预亏', '预盈', '减亏', '盈利', '营收',
               '净利润', '财报', '业绩']),
    ('并购重组', ['收购', '并购', '重组', '借壳', '分拆', '增资', '入股',
               '挂牌转让', '股权收购', '取得控制权', '吸收合并']),
    ('监管处罚', ['处罚', '立案', '警示', '监管函', '问询函', '违规', '罚款',
               '谴责', '整改', '调查', '退市']),
    ('高管变动', ['辞职', '辞任', '聘任', '任命', '离任', '辞去', '出任',
               '履新', '卸任', '新董事长', '当选', '换帅']),
    ('回购分红', ['回购', '分红', '派息', '送转', '股权激励', '员工持股', '中期分红']),
    ('增减持', ['增持', '减持']),
    ('业务动态', ['签约', '中标', '合作', '订单', '投产', '发布', '上线', '开工',
               '项目', '量产', '交付', '战略合作', '复牌', '停牌', '入驻', '开户']),
    ('行业政策', ['政策', '规划', '指导意见', '实施方案', '行业规范', '新规',
               '征求意见稿']),
    ('宏观', ['央行', 'GDP', '通胀', 'CPI', '利率', '降准', '降息', '加息', '宏观',
            '经济数据', '财政部', '证监会', '美联储', '汇率', '人民币']),
]

_TITLE_STOP = re.compile(r'[^\w\u4e00-\u9fff]+')


def normalize_title(title: str) -> str:
    """标题归一化：去空白与标点，仅保留中英文数字与下划线。"""
    if not isinstance(title, str):
        return ''
    return _TITLE_STOP.sub('', title).lower()


def classify_topic(title: str) -> str:
    """按关键词规则给新闻打事实性主题标签。"""
    text = title or ''
    for topic, keywords in TOPIC_RULES:
        if any(kw in text for kw in keywords):
            return topic
    return '其他'


class NewsFetcher:
    """新闻获取器。

    通过 DataProvider 登录后，按两步式拉取新闻：
    列表 -> 详情+html（接口自动增量下载），再从本地详情 h5 合并明细数据，
    提供多源去重归并与客观统计。
    """

    def __init__(self, dp, local_path: str = 'D:/AmazingData_local_data/'):
        """
        Args:
            dp: DataProvider 实例（已登录）
            local_path: AD 本地数据根目录（需保留尾部斜杠）
        """
        self._dp = dp
        self._local_path = local_path

    BATCH_SIZE = 500  # 单次 get_news_list 代码数上限（超限接口可能失败，自动分批）

    def fetch(
        self,
        code_list: List[str],
        begin_date: Optional[int] = None,
        end_date: Optional[int] = None,
        is_local: bool = False,
        batch_size: int = BATCH_SIZE,
    ) -> Tuple[pd.DataFrame, str]:
        """拉取新闻列表与详情。

        Args:
            code_list: 股票代码列表，如 ['600***.SH']；全市场模式传全部A股代码
            begin_date: 新闻创建起始日期 YYYYMMDD，None=按接口增量机制自动确定
            end_date: 新闻创建结束日期 YYYYMMDD，None=至当天
            is_local: True=优先读本地缓存并增量续传，False=从服务器拉取
            batch_size: 代码分批大小（接口单次传入代码过多会失败）

        Returns:
            (detail_df, news_html_dir):
                detail_df: 从 html 解析合并的新闻明细 DataFrame（含 stock 列，
                           字段 news_id/title/summary/source/author/
                           publish_time/ranges/stock）
                news_html_dir: 新闻原文 html 本地目录
        """
        info = self._dp.info_data

        kwargs = {}
        if begin_date:
            kwargs['begin_date'] = begin_date
        if end_date:
            kwargs['end_date'] = end_date

        # 分批拉取列表并合并（全市场约 5000+ 只代码，单次传接口会失败）
        merged = {}
        batches = [code_list[i:i + batch_size]
                   for i in range(0, len(code_list), batch_size)] or [[]]
        if len(batches) > 1:
            print(f'代码 {len(code_list)} 只，分 {len(batches)} 批拉取新闻列表（每批 {batch_size} 只）...',
                  flush=True)
        for bi, part in enumerate(batches, 1):
            try:
                r = info.get_news_list(
                    part,
                    local_path=self._local_path,
                    is_local=is_local,
                    **kwargs,
                ) or {}
            except Exception as exc:
                print(f'[警告] 第 {bi}/{len(batches)} 批新闻列表失败，跳过: {str(exc)[:100]}',
                      flush=True)
                continue
            if isinstance(r, dict):
                for k, v in r.items():
                    if v is not None and len(v):
                        merged.setdefault(str(k), v)
            if len(batches) > 1:
                print(f'  批次 {bi}/{len(batches)} 完成，累计 {len(merged)} 只股票有新闻',
                      flush=True)
                if bi < len(batches):
                    time.sleep(1)

        if not merged:
            return pd.DataFrame(), ''

        # 两步式：列表 -> 详情html（1.1.12）
        news_html_dir = info.get_news_detail_html(
            merged, local_path=self._local_path)

        detail_df = self.load_details(merged, str(news_html_dir))
        return detail_df, str(news_html_dir)

    def count_unique_news(
        self,
        code_list: List[str],
        begin_date: Optional[int] = None,
        end_date: Optional[int] = None,
        is_local: bool = False,
        batch_size: int = BATCH_SIZE,
    ) -> int:
        """统计区间内去重 news_id 条数（只拉列表，不下载详情，用于热度环比）。"""
        kwargs = {}
        if begin_date:
            kwargs['begin_date'] = begin_date
        if end_date:
            kwargs['end_date'] = end_date
        ids = set()
        batches = [code_list[i:i + batch_size]
                   for i in range(0, len(code_list), batch_size)] or [[]]
        for part in batches:
            try:
                news_list = self._dp.info_data.get_news_list(
                    part,
                    local_path=self._local_path,
                    is_local=is_local,
                    **kwargs,
                ) or {}
            except Exception:
                continue
            if isinstance(news_list, dict):
                for code, df in news_list.items():
                    if df is None or df.empty or 'news_id' not in df.columns:
                        continue
                    ids.update(df['news_id'].astype(str))
        return len(ids)

    def load_details(
        self,
        news_list: Dict[str, pd.DataFrame],
        news_html_dir: str,
    ) -> pd.DataFrame:
        """解析本次新闻的 html 元信息，合并为明细 DataFrame。

        get_news_detail_html 生成的 html（以 news_id 命名）内嵌元信息：
        <h1>标题</h1> 与 <ul class="meta-list"> 中的 摘要/来源/作者/发布时间/
        新闻范围。详情不再单独落盘，明细数据从 html 提取。
        """
        html_dir = str(news_html_dir).replace('//', '/').rstrip('/\\')
        items = []
        for code, df in news_list.items():
            if df is None or df.empty:
                continue
            for nid in df['news_id'].astype(str):
                fp = os.path.join(html_dir, f'{nid}.html')
                if not os.path.isfile(fp):
                    continue
                try:
                    with open(fp, 'r', encoding='utf-8', errors='replace') as f:
                        html = f.read()
                except Exception:
                    continue
                row = self.parse_html(html)
                row['news_id'] = nid
                row['stock'] = code
                items.append(row)

        if not items:
            return pd.DataFrame()
        all_df = pd.DataFrame(items)
        sort_col = 'publish_time' if 'publish_time' in all_df.columns else 'create_date'
        if sort_col in all_df.columns:
            all_df = all_df.sort_values(sort_col, ascending=False, na_position='last')
        return all_df.reset_index(drop=True)

    @staticmethod
    def parse_html(html: str) -> dict:
        """从 get_news_detail_html 生成的 html 中提取元信息字段。"""
        def grab(pattern, text, default=''):
            m = re.search(pattern, text, re.DOTALL)
            return m.group(1).strip() if m else default

        row = {}
        row['title'] = grab(r'<h1>(.*?)</h1>', html,
                            grab(r'<title>(.*?)</title>', html))
        row['summary'] = grab(r'<b>摘要：</b>(.*?)</li>', html)
        row['source'] = grab(r'<b>来源：</b>(.*?)</li>', html)
        row['author'] = grab(r'<b>作者：</b>(.*?)</li>', html)
        row['publish_time'] = grab(r'<b>发布时间：</b>(.*?)</li>', html)
        ranges_text = grab(r'<b>新闻范围：</b>(.*?)</li>', html)
        row['ranges'] = RANGES_TEXT.get(ranges_text, 0)
        return row

    @staticmethod
    def dedup(df: pd.DataFrame) -> pd.DataFrame:
        """多源去重：归一化标题相同的新闻归并，保留最早一条，统计报道数。

        报道数按组内**去重 news_id** 计数——同一条新闻挂多只股票时
        news_id 相同，只算 1 条报道，避免把"标的关联数"误当成转载媒体数。

        Returns:
            DataFrame，新增 republish_count（报道总数，含首发）与
            first_source（最早来源）列。
        """
        if df.empty:
            return df
        d = df.copy()
        d['_norm_title'] = d['title'].map(normalize_title)
        d = d[d['_norm_title'] != '']

        # 排序键：优先 publish_time，缺失回退 create_date
        sort_col = 'publish_time' if 'publish_time' in d.columns else 'create_date'
        # 空串视为缺失（na_position='last'），避免空日期被误当作"最早"保留为代表条目
        if sort_col in d.columns:
            d[sort_col] = d[sort_col].replace('', pd.NA)
        d = d.sort_values(sort_col, ascending=True, na_position='last')

        groups = []
        for _, g in d.groupby('_norm_title'):
            # 组内先按 news_id 去重：同一新闻挂多只股票只保留一条
            if 'news_id' in g.columns:
                g = g.drop_duplicates(subset='news_id', keep='first')
            first = g.iloc[0].copy()
            first['republish_count'] = len(g)
            first['first_source'] = first.get('source', '')
            groups.append(first)
        out = pd.DataFrame(groups)
        out = out.drop(columns=['_norm_title'])
        out = out.sort_values(sort_col, ascending=False, na_position='last').reset_index(drop=True)
        return out

    @staticmethod
    def filter_topic(df: pd.DataFrame, topics: List[str]) -> pd.DataFrame:
        """按主题标签过滤（topic 列须已附加）。"""
        if df.empty or not topics:
            return df
        tset = {str(t).strip() for t in topics if str(t).strip()}
        if not tset:
            return df
        return df[df['topic'].isin(tset)].reset_index(drop=True)

    @staticmethod
    def add_topic(df: pd.DataFrame) -> pd.DataFrame:
        """附加事实性主题标签列 topic。"""
        if df.empty:
            return df
        d = df.copy()
        d['topic'] = d['title'].map(classify_topic)
        return d

    @staticmethod
    def print_list(df: pd.DataFrame, limit: int = 0):
        """打印去重后的新闻列表（含主题标签与转载数）。"""
        n = len(df)
        display = df.head(limit) if limit > 0 else df
        print(f'\n去重后 {n} 条新闻' + (f'（显示前 {min(limit, n)} 条）:' if limit > 0 else ':'),
              flush=True)
        print(flush=True)
        for _, row in display.iterrows():
            date = str(row.get('publish_time', '') or row.get('create_date', ''))[:10]
            title = str(row.get('title', ''))[:70]
            source = str(row.get('source', ''))[:12]
            ranges = row.get('ranges')
            ranges_lab = RANGES_LABEL.get(ranges, str(ranges)) if pd.notna(ranges) else '-'
            topic = str(row.get('topic', ''))
            nid = str(row.get('news_id', ''))
            rep = row.get('republish_count')
            rep_lab = f' | {int(rep)}条报道' if pd.notna(rep) and rep and rep > 1 else ''
            print(f'  [{date}] {title}', flush=True)
            print(f'      id:{nid} | {source} | {ranges_lab} | {topic}{rep_lab}', flush=True)

    @staticmethod
    def print_stats(raw_df: pd.DataFrame, dedup_df: pd.DataFrame):
        """打印统计概览（纯计数）。"""
        print(f'\n─── 统计概览 ───', flush=True)
        print(f'原始新闻: {len(raw_df)} 条 → 去重归并后: {len(dedup_df)} 条事件',
              flush=True)

        # 按日分布（去重后事件数；天数超过8天只展示事件数TOP5，避免刷屏）
        date_src = dedup_df['publish_time'] if 'publish_time' in dedup_df.columns else dedup_df.get('create_date')
        if date_src is not None:
            by_day = date_src.dropna().astype(str).str[:10].value_counts().sort_index()
            if not by_day.empty:
                peak_day = by_day.idxmax()
                if len(by_day) > 8:
                    top = by_day.sort_values(ascending=False).head(5)
                    parts = '，'.join(f'{k}: {v} 条' for k, v in top.items())
                    print(f'按日分布: 共 {len(by_day)} 天，事件数TOP5 → {parts}', flush=True)
                else:
                    parts = '，'.join(f'{k}: {v} 条' for k, v in by_day.items())
                    print(f'按日分布: {parts}', flush=True)
                print(f'事件峰值: {peak_day}（{by_day.max()} 条）', flush=True)

        # 媒体来源 TOP
        if 'source' in dedup_df.columns:
            src = dedup_df['source'].dropna().astype(str).str.strip()
            src = src[src != '']
            if not src.empty:
                top = src.value_counts().head(5)
                parts = '，'.join(f'{k} {v} 条' for k, v in top.items())
                print(f'来源TOP5: {parts}', flush=True)

        # ranges 分层计数
        if 'ranges' in dedup_df.columns:
            rg = dedup_df['ranges'].dropna()
            if not rg.empty:
                dist = rg.map(lambda x: RANGES_LABEL.get(int(x), str(x))).value_counts()
                parts = '，'.join(f'{k} {v} 条' for k, v in dist.items())
                print(f'范围分层: {parts}', flush=True)

        # 主题分布
        if 'topic' in dedup_df.columns:
            tp = dedup_df['topic'].dropna()
            if not tp.empty:
                dist = tp.value_counts()
                parts = '，'.join(f'{k} {v} 条' for k, v in dist.items())
                print(f'主题分布: {parts}', flush=True)

        # 热度TOP（报道数≥2 的事件，按报道数降序，最多3条）
        if 'republish_count' in dedup_df.columns:
            rep = pd.to_numeric(dedup_df['republish_count'], errors='coerce')
            hot = dedup_df[rep > 1].copy()
            if not hot.empty:
                hot['_rep'] = pd.to_numeric(hot['republish_count'], errors='coerce')
                hot = hot.sort_values('_rep', ascending=False).head(3)
                print(f'热度TOP{len(hot)}（按报道数）:', flush=True)
                for _, row in hot.iterrows():
                    date = str(row.get('publish_time', '') or row.get('create_date', ''))[:10]
                    title = str(row.get('title', ''))[:40]
                    print(f'  [{date}] {title}（{int(row["_rep"])}条报道）', flush=True)
