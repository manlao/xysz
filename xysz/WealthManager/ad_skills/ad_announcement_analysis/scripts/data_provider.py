# -*- coding: utf-8 -*-
"""
数据提供封装模块 - 统一登录与数据访问入口

统一管理 AmazingData 登录认证、交易日历获取、股票代码列表获取，
为公告搜索模块提供数据基础。支持环境变量配置和本地缓存两种模式。
"""

import os
import warnings
from typing import List, Optional

warnings.filterwarnings('ignore')

import AmazingData as ad
import pandas as pd


class DataProvider:
    """统一数据提供器，封装 AmazingData 登录与基础数据查询。

    使用前需设置环境变量：
        AD_USERNAME, AD_PASSWORD, AD_HOST, AD_PORT

    或传入 login_kwargs 直接指定。
    """

    def __init__(self, login_kwargs: Optional[dict] = None):
        """初始化数据提供器并登录。

        Args:
            login_kwargs: 直接传入登录参数，优先级高于环境变量。
                格式: {'username': 'xxx', 'password': 'xxx', 'host': 'xxx', 'port': xxx}
        """
        self._base_data = None
        self._info_data = None
        self._calendar = None
        self._code_cache = {}
        self._login(login_kwargs)

    def _login(self, login_kwargs: Optional[dict] = None):
        """登录 AmazingData。优先使用传入参数，其次环境变量。"""
        if login_kwargs:
            username = login_kwargs.get('username', '')
            password = login_kwargs.get('password', '')
            host = login_kwargs.get('host', '')
            port = login_kwargs.get('port', 0)
        else:
            username = os.environ.get('AD_USERNAME', '')
            password = os.environ.get('AD_PASSWORD', '')
            host = os.environ.get('AD_HOST', '')
            port = int(os.environ.get('AD_PORT', '0'))

        missing = []
        if not username:
            missing.append('AD_USERNAME')
        if not password:
            missing.append('AD_PASSWORD')
        if not host:
            missing.append('AD_HOST')
        if not port:
            missing.append('AD_PORT')
        if missing:
            raise EnvironmentError(
                f"缺少环境变量: {', '.join(missing)}。"
                f"请设置后重试，或传入 login_kwargs 参数。"
            )

        try:
            ad.login(username=username, password=password, host=host, port=port)
        except SystemExit:
            raise ConnectionError(
                "无法登录星耀数智，请检查账号密码和网络连接。\n"
                f"  账号: {username}\n"
                f"  主机: {host}:{port}\n"
                "  环境变量: AD_USERNAME / AD_PASSWORD / AD_HOST / AD_PORT"
            )
        print(f"[DataProvider] 登录成功: {host}:{port}")

    @property
    def base_data(self) -> ad.BaseData:
        """获取 BaseData 实例（延迟初始化）"""
        if self._base_data is None:
            self._base_data = ad.BaseData()
        return self._base_data

    @property
    def info_data(self) -> ad.InfoData:
        """获取 InfoData 实例（延迟初始化）"""
        if self._info_data is None:
            self._info_data = ad.InfoData()
        return self._info_data

    def get_calendar(self, market: str = 'SH') -> pd.DataFrame:
        """获取交易日历。

        Args:
            market: 市场代码，默认 SH（上海）

        Returns:
            DataFrame，含 trade_date 列。
        """
        if self._calendar is None:
            self._calendar = self.base_data.get_calendar(market=market)
            print(f"[DataProvider] 交易日历加载完成: {len(self._calendar)} 个交易日")
        return self._calendar

    def get_stock_list(self) -> List[str]:
        """获取最新A股代码列表。"""
        return self.get_code_list('EXTRA_STOCK_A_SH_SZ')

    def get_fund_list(self) -> List[str]:
        """获取最新ETF代码列表。"""
        return self.get_code_list('EXTRA_ETF')

    def get_bond_list(self) -> List[str]:
        """获取最新可转债代码列表。"""
        return self.get_code_list('EXTRA_KZZ')

    def get_code_list(
        self,
        security_type: str,
    ) -> List[str]:
        """获取最新代码列表（通用方法）。

        Args:
            security_type: AD 枚举值 (EXTRA_STOCK_A_SH_SZ / EXTRA_ETF / EXTRA_KZZ)
        """
        if security_type not in self._code_cache:
            code_list = self.base_data.get_code_list(security_type=security_type)
            print(f"[DataProvider] {security_type} 代码获取完成: {len(code_list)} 只")
            self._code_cache[security_type] = code_list
        return self._code_cache[security_type]

    def get_hist_code_list(
        self,
        security_type: str,
        start_date: int = 20130101,
        end_date: Optional[int] = None,
    ) -> List[str]:
        """获取历史代码列表（按日期范围的成分股）。

        慢，仅在需要历史某一日的成分股时使用。
        """
        if end_date is None:
            import datetime
            end_date = int(datetime.date.today().strftime('%Y%m%d'))

        code_list = self.base_data.get_hist_code_list(
            security_type=security_type,
            start_date=start_date,
            end_date=end_date,
        )
        print(f"[DataProvider] {security_type} 历史代码获取完成: {len(code_list)} 只")
        return code_list
