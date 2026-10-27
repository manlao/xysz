# -*- coding: utf-8 -*-
"""
数据提供封装模块 - ETF定投数据层

统一管理 AmazingData 登录认证、ETF行情数据获取、交易日历管理。
为 ETF 定投计算器提供数据基础。

所有接口行为严格参照 ad_api skill 文档。
"""

import os
import warnings
from typing import Optional
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')

import AmazingData as ad
import pandas as pd


class DataProvider:
    """统一数据提供器，封装 AmazingData 登录与 ETF 数据查询。

    使用前需设置环境变量：
        AD_USERNAME, AD_PASSWORD, AD_HOST, AD_PORT
    """

    def __init__(self):
        self._base_data = None
        self._market_data = None
        self._calendar = None

    def _login(self):
        """登录 AmazingData，失败抛异常。"""
        username = os.environ.get('AD_USERNAME')
        password = os.environ.get('AD_PASSWORD')
        host = os.environ.get('AD_HOST')
        port = os.environ.get('AD_PORT')

        missing = [k for k, v in [('AD_USERNAME', username), ('AD_PASSWORD', password),
                                   ('AD_HOST', host), ('AD_PORT', port)] if not v]
        if missing:
            raise RuntimeError(
                f"缺少环境变量: {', '.join(missing)}。\n"
                f"请先设置: set AD_USERNAME=xxx & set AD_PASSWORD=xxx & set AD_HOST=xxx & set AD_PORT=xxx"
            )

        ad.login(username=username, password=password, host=host, port=int(port))
        print("[DataProvider] AmazingData 登录成功")

    @property
    def base_data(self) -> ad.BaseData:
        if self._base_data is None:
            self._base_data = ad.BaseData()
        return self._base_data

    @property
    def market_data(self) -> ad.MarketData:
        """MarketData 实例化必须传入交易日历。"""
        if self._market_data is None:
            self._market_data = ad.MarketData(self.get_calendar())
        return self._market_data

    def get_calendar(self, market: str = 'SH'):
        """获取交易日历，返回 List[int]。"""
        if self._calendar is None:
            self._calendar = self.base_data.get_calendar(market=market)
            print(f"[DataProvider] 交易日历加载完成: {len(self._calendar)} 个交易日")
        return self._calendar

    def get_etf_name(self, symbol: str) -> str:
        """通过 AmazingData get_code_info(EXTRA_ETF) 获取 ETF 中文名称。
        首次调用拉取全量 ETF 列表并缓存，后续 O(1) 查表。
        """
        if not hasattr(self, '_etf_name_cache'):
            try:
                df = self.base_data.get_code_info(security_type='EXTRA_ETF')
                self._etf_name_cache = dict(zip(df.index, df['symbol']))
            except Exception as e:
                print(f"[DataProvider] 获取 ETF 名称列表失败: {e}")
                self._etf_name_cache = {}
        return self._etf_name_cache.get(symbol, symbol)

    def get_etf_kline(
        self,
        code: str,
        begin_date: int,
        end_date: int,
        period: str = 'day',
    ) -> Optional[pd.DataFrame]:
        """获取 ETF 日线 K 线数据（原始不复权）。

        Args:
            code: ETF 代码，如 '510***.SH'
            begin_date: 起始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD
            period: 周期，默认 'day'

        Returns:
            DataFrame，含 open/high/low/close/volume/amount 等列，
            index 为日期，或 None（无数据时）
        """
        # query_kline 必须指定 period=日线，否则默认返回分钟线
        result = self.market_data.query_kline(
            [code],
            begin_date=begin_date,
            end_date=end_date,
            period=ad.constant.Period.day.value,
        )

        if code not in result or result[code].empty:
            print(f"[DataProvider] {code} 在 {begin_date}-{end_date} 无K线数据")
            return None

        df = result[code].copy()
        # 官方字段 kline_time 为日期 (datetime 类型)
        df.set_index('kline_time', inplace=True)
        df.sort_index(inplace=True)
        print(f"[DataProvider] {code} 原始K线获取完成: {len(df)} 条")
        return df

    def get_etf_backward_factor(
        self,
        code: str,
        local_path: str = os.path.join(os.path.expanduser('~'), 'AmazingData_local_data'),
        is_local: bool = True,
    ) -> Optional[pd.Series]:
        """获取 ETF 后复权因子（来自 BaseData.get_backward_factor）。

        前复权价格公式：
            前复权收盘价 = 原始收盘价 × (当日后复权因子 / 最新后复权因子)

        Args:
            code: ETF 代码，如 '510***.SH'
            local_path: 本地数据存储路径，默认 'D://AmazingData_local_data//'
            is_local: 是否优先使用本地缓存，默认 True。False 时从服务器拉取最新并更新本地

        Returns:
            Series，index=日期，values=后复权因子，或 None
        """
        try:
            factor_data = self.base_data.get_backward_factor(
                [code],
                local_path=local_path,
                is_local=is_local,
            )
        except Exception as e:
            print(f"[DataProvider] 获取后复权因子失败: {e}")
            return None

        if code not in factor_data:
            print(f"[DataProvider] {code} 无后复权因子数据，可用: {list(factor_data.keys())[:3]}")
            return None

        raw = factor_data[code]
        if not isinstance(raw, pd.Series):
            print(f"[DataProvider] {code} 后复权因子类型异常: {type(raw)}")
            return None
        if raw.empty:
            print(f"[DataProvider] {code} 后复权因子为空")
            return None

        factor_series = raw.copy()
        if not isinstance(factor_series.index, pd.DatetimeIndex):
            factor_series.index = pd.to_datetime(factor_series.index.astype(str), format='%Y%m%d')
        factor_series.sort_index(inplace=True)
        factor_series.name = 'backward_factor'
        print(f"[DataProvider] {code} 后复权因子获取完成: {len(factor_series)} 条")
        print(f"  因子范围: {factor_series.min():.4f} ~ {factor_series.max():.4f}")
        return factor_series

    def get_daily_close_series(
        self,
        code: str,
        begin_date: int,
        end_date: int,
        local_path: str = os.path.join(os.path.expanduser('~'), 'AmazingData_local_data'),
        is_local: bool = True,
    ) -> Optional[pd.Series]:
        """获取前复权收盘价序列（定投计算主入口）。

        Args:
            code: ETF 代码，如 '510***.SH'
            begin_date: 起始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD
            local_path: 复权因子本地存储路径
            is_local: 复权因子是否优先使用本地缓存

        取原始K线收盘价 + 后复权因子 (BaseData.get_backward_factor)，合成前复权价：
            前复权收盘价 = 原始收盘价 × (当日后复权因子 / 最新后复权因子)

        Returns:
            Series，index=日期，values=前复权收盘价
        """
        # 1. 取原始K线
        kline = self.get_etf_kline(code, begin_date, end_date)
        if kline is None:
            return None

        # 2. 取后复权因子
        factor_series = self.get_etf_backward_factor(code, local_path=local_path, is_local=is_local)
        if factor_series is None:
            print("[DataProvider] 警告: 无法获取后复权因子，使用原始收盘价")
            return kline['close']

        # 3. 合成前复权收盘价
        latest_factor = float(factor_series.iloc[-1])
        if latest_factor == 0:
            print("[DataProvider] 警告: 最新复权因子为0，使用原始收盘价")
            return kline['close']

        # 合并K线和复权因子（按日期对齐，inner join）
        combined = pd.DataFrame({
            'close_raw': kline['close'],
            'factor': factor_series,
        }).dropna()

        combined['close_adj'] = combined['close_raw'] * (combined['factor'] / latest_factor)

        print(f"[DataProvider] {code} 前复权收盘价合成完成: {len(combined)} 条")
        print(f"  后复权因子范围: {combined['factor'].min():.4f} ~ {combined['factor'].max():.4f}")
        print(f"  前复权价范围: {combined['close_adj'].min():.4f} ~ {combined['close_adj'].max():.4f}")

        return combined['close_adj']

    def get_nearest_trading_days(
        self,
        dates: list[str],
    ) -> list[str]:
        """将给定日期列表对齐到最近交易日（顺延）。

        Args:
            dates: 日期字符串列表 ['YYYY-MM-DD', ...]

        Returns:
            最近交易日列表
        """
        calendar = self.get_calendar()
        trading_dates = set()
        if isinstance(calendar, pd.DataFrame):
            for _, row in calendar.iterrows():
                td = str(row.get('trade_date', row.get('date', '')))
                if td:
                    trading_dates.add(td[:4] + '-' + td[4:6] + '-' + td[6:8])
        else:
            # calendar 可能是 int 列表
            for td in calendar:
                td_str = str(td)
                if len(td_str) >= 8:
                    trading_dates.add(td_str[:4] + '-' + td_str[4:6] + '-' + td_str[6:8])

        result = []
        for d in dates:
            dt = datetime.strptime(d, '%Y-%m-%d')
            for offset in range(10):
                check = (dt + timedelta(days=offset)).strftime('%Y-%m-%d')
                if check in trading_dates:
                    result.append(check)
                    break
            else:
                result.append(d)  # fallback
        return result

    def generate_dca_dates(
        self,
        start_date: str,
        end_date: str,
        frequency: str = 'monthly',
        interval_days: int = 0,
    ) -> list[str]:
        """生成定投日期序列并对齐到交易日。

        Args:
            start_date: 起始日期 'YYYY-MM-DD'
            end_date: 结束日期 'YYYY-MM-DD'
            frequency: weekly / biweekly / monthly / quarterly / day
            interval_days: 当 frequency='day' 时，每隔多少天，如 5=每5日
        """
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')

        dates = []
        current = start
        if frequency == 'day':
            if interval_days <= 0:
                raise ValueError("frequency=day 时必须指定 interval_days > 0")
            while current <= end:
                dates.append(current.strftime('%Y-%m-%d'))
                current += timedelta(days=interval_days)
        else:
            from dateutil.relativedelta import relativedelta
            step_map = {
                'weekly': relativedelta(weeks=1),
                'biweekly': relativedelta(weeks=2),
                'monthly': relativedelta(months=1),
                'quarterly': relativedelta(months=3),
            }
            if frequency not in step_map:
                raise ValueError(f"不支持的频率: {frequency}")
            step = step_map[frequency]
            while current <= end:
                dates.append(current.strftime('%Y-%m-%d'))
                current += step

        return self.get_nearest_trading_days(dates)
