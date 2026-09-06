# -*- coding: utf-8 -*-
"""
数据提供层 - 封装 AmazingData 数据获取与本地缓存

提供:
    - 交易日历
    - 股票代码列表（含历史代码表）
    - K线数据（日线/分钟线，含复权）
    - 行业分类数据
    - 流通市值数据
    - 指数行情（基准）
    - 行业哑变量矩阵（预生成缓存，加速中性化和回归分析）

缓存策略:
    - 支持 AmazingData 的 local_path + is_local 机制
    - 首次从服务端拉取，后续直接从本地 HDF5 读取
    - 行业哑变量预生成并缓存，避免重复计算
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Union, Tuple

import numpy as np
import pandas as pd
import AmazingData as ad
from AmazingData.utils.constant import Period


# ============================================================
# 工具函数
# ============================================================

def date_to_int(d: Union[str, datetime, pd.Timestamp]) -> int:
    """将日期转换为 int 格式 (YYYYMMDD)"""
    if isinstance(d, int):
        return d
    if isinstance(d, pd.Timestamp):
        return int(d.strftime('%Y%m%d'))
    if isinstance(d, datetime):
        return int(d.strftime('%Y%m%d'))
    if isinstance(d, str):
        return int(d.replace('-', '').replace('/', '')[:8])
    raise ValueError(f"无法转换日期: {d}")


def int_to_datetime(d: int) -> pd.Timestamp:
    """将 int (YYYYMMDD) 转换为 pd.Timestamp"""
    s = str(d)
    return pd.Timestamp(f"{s[:4]}-{s[4:6]}-{s[6:8]}")


_logged_in = False

def _ensure_login():
    """确保 AmazingData 已登录（模块级只登录一次）"""
    global _logged_in
    if _logged_in:
        return

    username = os.environ.get('AD_USERNAME')
    password = os.environ.get('AD_PASSWORD')
    host = os.environ.get('AD_HOST')
    port = os.environ.get('AD_PORT')

    if not all([username, password, host, port]):
        missing = []
        if not username: missing.append('AD_USERNAME')
        if not password: missing.append('AD_PASSWORD')
        if not host: missing.append('AD_HOST')
        if not port: missing.append('AD_PORT')
        print(json.dumps({
            "error": f"缺少环境变量: {', '.join(missing)}。请先设置: "
                     f"set AD_USERNAME=xxx & set AD_PASSWORD=xxx & set AD_HOST=xxx & set AD_PORT=xxx"
        }, ensure_ascii=False))
        return
    print(f"正在登录AmazingData...", file=sys.stderr)
    ad.login(username=username, password=password, host=host, port=int(port))
    _logged_in = True


# ============================================================
# DataProvider 主类
# ============================================================

class DataProvider:
    """
    AmazingData 数据获取与缓存封装。

    使用示例:
        dp = DataProvider(local_path='D:/AmazingData_local_data/')
        calendar = dp.get_calendar()
        kline = dp.get_kline(['000***.SZ', '600***.SH'], begin_date=20200101, end_date=20241231)
        industry = dp.get_industry_class()
    """

    def __init__(self, local_path: Optional[str] = None):
        """
        :param local_path: 本地缓存路径，如 'D:/AmazingData_local_data/'。
                           为 None 则不使用本地缓存。
        """
        _ensure_login()
        self.local_path = local_path
        self._base_data = ad.BaseData()
        self._info_data = ad.InfoData()

        # 延迟初始化（用到时才创建）
        self._market_data: Optional[ad.MarketData] = None
        self._calendar: Optional[List[int]] = None

        # 缓存容器
        self._industry_dummies_cache: Optional[pd.DataFrame] = None  # 行业哑变量矩阵
        self._industry_map_cache: Optional[Dict[str, str]] = None     # 股票代码 → 行业代码
        self._stock_basic_cache: Optional[pd.DataFrame] = None       # 股票基础信息

    # ----------------------------------------------------------
    # 交易日历
    # ----------------------------------------------------------

    @property
    def market_data(self) -> ad.MarketData:
        """懒加载 MarketData 实例"""
        if self._market_data is None:
            # MarketData 内部用 int 比较 calendar，需传 int 列表
            self._market_data = ad.MarketData(self.get_calendar(data_type='int'))
        return self._market_data

    def get_calendar(self, market: str = 'SH', data_type: str = 'datetime') -> List:
        """
        获取交易日历。

        :param market: 市场，'SH'/'SZ'/'BJ' 等
        :param data_type: 'int' 返回 YYYYMMDD 整数列表，'datetime' 返回 pd.Timestamp 列表
        :return: 交易日历列表
        """
        if self._calendar is None:
            # get_calendar 返回 str 列表 (YYYYMMDD)
            cal = self._base_data.get_calendar(data_type='str', market=market)
            self._calendar = sorted([int(d) for d in cal])

        if data_type == 'datetime':
            return [int_to_datetime(d) for d in self._calendar]
        elif data_type == 'int':
            return self._calendar
        else:
            return [str(d) for d in self._calendar]

    # ----------------------------------------------------------
    # 股票代码
    # ----------------------------------------------------------

    def get_stock_list(self, security_type: str = 'EXTRA_STOCK_A_SH_SZ') -> List[str]:
        """获取当前全量股票代码列表"""
        return self._base_data.get_code_list(security_type=security_type)

    def get_hist_stock_list(
        self,
        start_date: Union[int, str, datetime],
        end_date: Union[int, str, datetime],
        security_type: str = 'EXTRA_STOCK_A_SH_SZ'
    ) -> List[str]:
        """
        获取历史代码表（指定区间内曾上市的股票）。

        :param start_date: 起始日期
        :param end_date: 结束日期
        :param security_type: 品种类型
        :return: 股票代码列表
        """
        return self._base_data.get_hist_code_list(
            security_type=security_type,
            start_date=date_to_int(start_date),
            end_date=date_to_int(end_date),
        )

    # ----------------------------------------------------------
    # K线数据
    # ----------------------------------------------------------

    def get_kline(
        self,
        code_list: List[str],
        begin_date: Union[int, str, datetime],
        end_date: Union[int, str, datetime],
        period: Period = Period.day,
        fields: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        获取K线数据，返回 DataFrame（index=日期, columns=股票代码, values=价格）。

        :param code_list: 股票代码列表
        :param begin_date: 起始日期
        :param end_date: 结束日期
        :param period: K线周期，默认日线
        :param fields: 需要的字段列表，如 ['close', 'open', 'volume']，None 返回全部
        :return: Multi-level DataFrame 或单字段 DataFrame
        """
        result = self.market_data.query_kline(
            code_list=code_list,
            begin_date=date_to_int(begin_date),
            end_date=date_to_int(end_date),
            period=period.value,
        )
        # result 格式: {code: DataFrame(columns=[code, kline_time, open, high, low, close, volume, amount])}
        # DataFrame index 是默认整数，kline_time 列才是日期

        if not result:
            return pd.DataFrame()

        if fields is None:
            fields = ['open', 'high', 'low', 'close', 'volume', 'amount']

        field_dfs = {}
        for field in fields:
            series_dict = {}
            for code, df in result.items():
                if df is None or df.empty or field not in df.columns:
                    continue
                # 用 kline_time 列作为 index
                s = df.set_index('kline_time')[field]
                s.index = pd.DatetimeIndex(s.index)
                series_dict[code] = s
            if series_dict:
                field_df = pd.DataFrame(series_dict)
                field_dfs[field] = field_df

        if not field_dfs:
            return pd.DataFrame()

        if len(field_dfs) == 1:
            return list(field_dfs.values())[0]

        # 多字段: 构建 MultiIndex columns
        return pd.concat(field_dfs, axis=1, names=['field', 'code'])

    def get_close_price(
        self,
        code_list: List[str],
        begin_date: Union[int, str, datetime],
        end_date: Union[int, str, datetime],
    ) -> pd.DataFrame:
        """
        快捷方法：获取收盘价矩阵 (日期 × 股票代码)。

        :return: DataFrame, index=日期, columns=股票代码
        """
        return self.get_kline(code_list, begin_date, end_date, fields=['close'])

    # ----------------------------------------------------------
    # 行业分类
    # ----------------------------------------------------------

    def get_industry_class(self) -> pd.DataFrame:
        """
        获取所有股票的行业分类数据。

        使用行业分类（通过 AmazingData 行业指数成分股反推）。

        :return: DataFrame, index=股票代码, columns=['industry_code', 'industry_name']
        """
        # 获取行业基本信息（不传 local_path 和 is_local，直接从服务端获取）
        industry_info = self._info_data.get_industry_base_info()
        # 列名是大写的 INDEX_CODE
        code_col = 'INDEX_CODE' if 'INDEX_CODE' in industry_info.columns else 'index_code'
        name_col = 'LEVEL1_NAME' if 'LEVEL1_NAME' in industry_info.columns else 'index_name'

        # 只取一级行业 (LEVEL_TYPE == 1) 共 31 个一级行业
        if 'LEVEL_TYPE' in industry_info.columns:
            industry_info = industry_info[industry_info['LEVEL_TYPE'] == 1]

        industry_codes = industry_info[code_col].tolist()

        # 获取每个行业的成分股
        industry_constituent = self._info_data.get_industry_constituent(
            code_list=industry_codes,
        )

        # 构建股票→行业的映射
        records = []
        if industry_constituent:
            for industry_code, df in industry_constituent.items():
                if df is None or df.empty:
                    continue
                matched = industry_info[industry_info[code_col] == industry_code]
                name = matched[name_col].values[0] if len(matched) > 0 else industry_code
                for stock_code in df.index:
                    records.append({
                        'stock_code': stock_code,
                        'industry_code': industry_code,
                        'industry_name': name,
                    })

        if not records:
            # 降级方案：用 get_stock_basic 获取行业信息
            stock_list = self.get_stock_list()
            basic = self._info_data.get_stock_basic(stock_list[:100])
            # 查找可能的行业列
            for col in ['industry', 'industry_code', 'sw_industry', 'sector']:
                if col in basic.columns:
                    for stock_code, row in basic.iterrows():
                        records.append({
                            'stock_code': stock_code,
                            'industry_code': str(row[col]),
                            'industry_name': str(row[col]),
                        })
                    break

        result = pd.DataFrame(records).set_index('stock_code') if records else pd.DataFrame()
        return result

    def get_industry_dummies(self, stock_list: List[str]) -> pd.DataFrame:
        """
        生成行业哑变量矩阵（预计算并缓存，用于中性化和回归分析加速）。

        :param stock_list: 目标股票列表
        :return: DataFrame, index=股票代码, columns=行业代码(one-hot), values=0/1
        """
        if self._industry_dummies_cache is not None:
            return self._industry_dummies_cache.reindex(stock_list, fill_value=0)

        industry_df = self.get_industry_class()
        dummies = pd.get_dummies(industry_df['industry_code'])
        dummies.index = industry_df.index
        dummies = dummies.reindex(stock_list, fill_value=0)
        self._industry_dummies_cache = dummies
        return dummies

    def get_stock_industry_map(self, stock_list: List[str]) -> Dict[str, str]:
        """
        获取股票→行业代码的映射字典。

        :return: {股票代码: 行业代码}
        """
        if self._industry_map_cache is not None:
            return {
                s: self._industry_map_cache.get(s, 'unknown')
                for s in stock_list
            }

        industry_df = self.get_industry_class()
        self._industry_map_cache = industry_df['industry_code'].to_dict()
        return {
            s: self._industry_map_cache.get(s, 'unknown')
            for s in stock_list
        }

    # ----------------------------------------------------------
    # 流通市值
    # ----------------------------------------------------------

    def get_float_market_value(
        self,
        stock_list: List[str],
        begin_date: Union[int, str, datetime],
        end_date: Union[int, str, datetime],
    ) -> pd.DataFrame:
        """
        获取流通市值数据。

        通过收盘价 × 流通A股 × 10000 计算（流通A股从 get_equity_structure 获取，单位万股）。

        :return: DataFrame, index=日期, columns=股票代码, values=流通市值
        """
        close_df = self.get_close_price(stock_list, begin_date, end_date)

        # 获取股本结构（DataFrame，含 TOT_SHARE 总股本、FLOAT_A_SHARE 流通A股，单位万股）
        equity = self._info_data.get_equity_structure(stock_list, is_local=False)
        if equity is None or equity.empty:
            return pd.DataFrame()

        # 每股取最新一期股本数据
        if 'FLOAT_A_SHARE' in equity.columns:
            latest = equity.groupby('MARKET_CODE')['FLOAT_A_SHARE'].last()
        elif 'TOT_SHARE' in equity.columns:
            latest = equity.groupby('MARKET_CODE')['TOT_SHARE'].last()
        else:
            return pd.DataFrame()

        shares_series = latest.reindex(close_df.columns).fillna(0)

        # 流通市值 = 收盘价 × 流通A股(万股) × 10000
        return close_df.mul(shares_series, axis=1) * 10000

    def get_total_market_value(
        self,
        stock_list: List[str],
        begin_date: Union[int, str, datetime],
        end_date: Union[int, str, datetime],
    ) -> pd.DataFrame:
        """获取总市值 = 收盘价 × 总股本(万股) × 10000"""
        close_df = self.get_close_price(stock_list, begin_date, end_date)

        equity = self._info_data.get_equity_structure(stock_list, is_local=False)
        if equity is None or equity.empty or 'TOT_SHARE' not in equity.columns:
            return pd.DataFrame()

        latest = equity.groupby('MARKET_CODE')['TOT_SHARE'].last()
        shares_series = latest.reindex(close_df.columns).fillna(0)
        return close_df.mul(shares_series, axis=1) * 10000

    # ----------------------------------------------------------
    # 基准指数
    # ----------------------------------------------------------

    def get_benchmark(
        self,
        benchmark_code: str = '000300.SH',
        begin_date: Optional[Union[int, str, datetime]] = None,
        end_date: Optional[Union[int, str, datetime]] = None,
    ) -> pd.DataFrame:
        """
        获取基准指数行情。

        :param benchmark_code: 指数代码，默认沪深300
        :param begin_date: 起始日期
        :param end_date: 结束日期
        :return: DataFrame, index=日期, columns=['close']
        """
        if begin_date is None:
            begin_date = self.get_calendar(data_type='int')[0]
        if end_date is None:
            end_date = self.get_calendar(data_type='int')[-1]

        result = self.market_data.query_kline(
            code_list=[benchmark_code],
            begin_date=date_to_int(begin_date),
            end_date=date_to_int(end_date),
            period=Period.day.value,
        )
        if benchmark_code not in result:
            return pd.DataFrame()

        df = result[benchmark_code]
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.set_index('kline_time')[['close']].copy()
        df.index = pd.DatetimeIndex(df.index)
        df.index.name = 'date'
        return df

    # ----------------------------------------------------------
    # 股票基础信息
    # ----------------------------------------------------------

    def get_stock_basic(self, stock_list: List[str]) -> pd.DataFrame:
        """
        获取股票基础信息（上市日期、退市日期、流通股本等）。

        :return: DataFrame
        """
        return self._info_data.get_stock_basic(stock_list)


# ============================================================
# 单例模式（可选）
# ============================================================

_default_provider: Optional[DataProvider] = None


def get_default_provider(local_path: Optional[str] = None) -> DataProvider:
    """获取默认 DataProvider 单例"""
    global _default_provider
    if _default_provider is None:
        _default_provider = DataProvider(local_path=local_path)
    return _default_provider


# ============================================================
# 测试
# ============================================================

if __name__ == '__main__':
    print("=== DataProvider 测试 ===\n")

    dp = DataProvider()

    # 1. 交易日历
    calendar = dp.get_calendar()
    print(f"交易日历: {len(calendar)} 个交易日, 范围 {calendar[0]} ~ {calendar[-1]}")

    # 2. 股票列表
    stock_list = dp.get_stock_list()
    print(f"当前全量股票: {len(stock_list)} 只")

    # 3. K线数据
    test_stocks = stock_list[:5]
    print(f"测试股票: {test_stocks}")
    kline = dp.get_close_price(test_stocks, 20240101, 20240531)
    print(f"K线数据 shape: {kline.shape}")

    # 4. 行业分类
    try:
        industry = dp.get_industry_class()
        print(f"行业分类: {industry.shape[0]} 只股票, {industry['industry_code'].nunique()} 个行业")
    except Exception as e:
        print(f"行业分类获取失败: {e}")

    # 5. 基准指数
    try:
        benchmark = dp.get_benchmark('000300.SH', 20240101, 20240531)
        print(f"基准指数: {len(benchmark)} 行")
    except Exception as e:
        print(f"基准指数获取失败: {e}")

    print("\n测试完成!")
