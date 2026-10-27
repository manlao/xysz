# -*- coding: utf-8 -*-
"""
数据层:指标验证的数据面板构建

职责:
    1. 登录 AmazingData,初始化 BaseData / InfoData / MarketData
    2. 获取交易日历与历史股票池(含已退市股票,消除生存偏差)
    3. 拉取 K 线并构建 (日期 × 股票) 面板:open/high/low/close/volume/amount
    4. 前复权处理(基于累计后复权因子归一化)
    5. 构建交易可行性矩阵:上市/退市/停牌/涨停/跌停/ST

所有面板统一为 DataFrame(index=日期, columns=股票代码)。
"""

import os
import sys
import time

import numpy as np
import pandas as pd

import AmazingData as ad  # 顶层导入:SDK 在 import 时完成鉴权(权限管控点)

DEFAULT_LOCAL_PATH = 'D://AmazingData_local_data//'

# 涨跌停幅度(按板块): 创业板(30)/科创板(68) 20%, 其余主板 10%
_LIMIT_20_PREFIX = ('300', '301', '688', '689')
# 涨跌停判定容差(收盘价涨幅与理论涨停价的舍入差异)
_LIMIT_TOLERANCE = 0.002


def check_env():
    """检查 AmazingData 登录环境变量,缺失时抛出明确错误"""
    missing = [k for k in ('AD_USERNAME', 'AD_PASSWORD', 'AD_HOST', 'AD_PORT')
               if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(
            '缺少环境变量: ' + ', '.join(missing)
            + '。请先设置 AD_USERNAME / AD_PASSWORD / AD_HOST / AD_PORT'
        )


class DataProvider:
    """回测数据提供器:一次性登录,构建全部面板"""

    def __init__(self, local_path: str = DEFAULT_LOCAL_PATH):
        check_env()
        port = int(os.environ['AD_PORT'])  # 端口必须为 int

        # 单点登录:同一时刻仅允许一个连接,被占用时等待重试
        logged = False
        for attempt in range(3):
            ret = ad.login(
                username=os.environ['AD_USERNAME'],
                password=os.environ['AD_PASSWORD'],
                host=os.environ['AD_HOST'],
                port=port,
            )
            ok = (ret is None) or (ret is True) or \
                 (isinstance(ret, dict) and ret.get('success')) or \
                 (isinstance(ret, (int, float)) and ret == 0)
            if ok:
                logged = True
                break
            print(f'登录失败(第{attempt + 1}次),单点登录可能被占用,30秒后重试...',
                  file=sys.stderr)
            time.sleep(30)
        if not logged:
            raise RuntimeError(
                'AmazingData 登录失败:单点登录被其他连接占用,请关闭其他'
                '正在使用该账号的会话后重试')
        self.local_path = local_path
        self.base_data = ad.BaseData()
        self.info_data = ad.InfoData()
        # 日历用默认格式(int yyyymmdd)初始化 MarketData——query_kline 传入 int 日期,
        # datetime 格式日历会在服务端比较时报类型错误
        calendar_raw = self.base_data.get_calendar()
        self.market_data = ad.MarketData(calendar_raw)
        # 面板行索引另用 DatetimeIndex
        self.calendar = pd.to_datetime(
            pd.Series(calendar_raw).astype(str), format='%Y%m%d')

    # ------------------------------------------------------------------
    # 股票池
    # ------------------------------------------------------------------

    def get_universe(self, begin_date, end_date, exclude_st: bool = False,
                     max_stocks: int = None):
        """
        获取回测区间的历史股票池(区间内曾上市,含期间退市股票)。

        返回: (code_list, stock_basic DataFrame)
            stock_basic 含 MARKET_CODE / SECURITY_NAME / LISTDATE /
            DELISTDATE / IS_LISTED / LISTPLATE_NAME 等字段
        """
        codes = self.base_data.get_hist_code_list(
            security_type='EXTRA_STOCK_A_SH_SZ',
            start_date=int(begin_date),
            end_date=int(end_date),
            local_path=self.local_path,
        )
        codes = sorted(codes)
        if not codes:
            raise RuntimeError('历史股票池为空,请检查本地数据路径与服务端连接')

        basic = self.info_data.get_stock_basic(codes)
        if basic is None or basic.empty:
            raise RuntimeError('get_stock_basic 返回为空')

        # 过滤:确认曾经上市成功(IS_LISTED 1=上市交易 3=终止上市,均保留)
        if 'IS_LISTED' in basic.columns:
            basic = basic[basic['IS_LISTED'].isin([1, 3])]
        if exclude_st and 'SECURITY_NAME' in basic.columns:
            basic = basic[~basic['SECURITY_NAME'].astype(str).str.contains('ST', na=False)]
        basic = basic.reset_index(drop=True)

        code_list = basic['MARKET_CODE'].astype(str).tolist()
        if max_stocks:
            code_list = code_list[:max_stocks]
            basic = basic[basic['MARKET_CODE'].astype(str).isin(code_list)]
        return code_list, basic.reset_index(drop=True)

    # ------------------------------------------------------------------
    # K 线面板
    # ------------------------------------------------------------------

    def get_kline_panels(self, code_list, begin_date, end_date,
                         fields=('open', 'high', 'low', 'close', 'volume', 'amount')):
        """
        拉取 K 线并转成面板 dict {field: DataFrame(index=日期, columns=代码)}。

        注意: query_kline 返回 dict{code: DataFrame},日期取自 kline_time 列。
        """
        kline_dict = self.market_data.query_kline(
            code_list=list(code_list),
            begin_date=int(begin_date),
            end_date=int(end_date),
            period=ad.constant.Period.day.value,
        )
        if not kline_dict:
            raise RuntimeError('query_kline 返回为空')

        panels = {f: {} for f in fields}
        for code, df in kline_dict.items():
            if df is None or df.empty:
                continue
            if 'kline_time' in df.columns:
                s = df.set_index('kline_time')
                s.index = pd.DatetimeIndex(s.index)
            else:
                s = df
                s.index = pd.DatetimeIndex(s.index)
            s = s[~s.index.duplicated(keep='last')].sort_index()
            for f in fields:
                if f in s.columns:
                    panels[f][code] = s[f]

        out = {}
        trade_index = self.calendar[
            (self.calendar >= pd.Timestamp(str(begin_date)))
            & (self.calendar <= pd.Timestamp(str(end_date)))
        ]
        for f in fields:
            if panels[f]:
                out[f] = pd.DataFrame(panels[f]).reindex(trade_index).sort_index()
            else:
                out[f] = pd.DataFrame(index=trade_index)
        return out

    # ------------------------------------------------------------------
    # 复权
    # ------------------------------------------------------------------

    def get_backward_factor(self, code_list) -> pd.DataFrame:
        """累计后复权因子面板(index=日期, columns=代码)"""
        bf = self.base_data.get_backward_factor(
            code_list=list(code_list),
            local_path=self.local_path,
            is_local=False,
        )
        if bf is None or bf.empty:
            raise RuntimeError('get_backward_factor 返回为空')
        bf.index = pd.DatetimeIndex(bf.index)
        return bf.sort_index()

    @staticmethod
    def forward_adjust(raw: pd.DataFrame, backward_factor: pd.DataFrame) -> pd.DataFrame:
        """
        前复权 = 原始价 × bf(d) / bf(区间最后一个交易日)。

        锚定区间末日真实价格,序列连续,不引入前视(因子只用当日及以前的值)。
        """
        bf = backward_factor.reindex(raw.index, columns=raw.columns).ffill()
        bf = bf.bfill()  # 上市初期因子可能缺失,向前补一次(不影响末日锚定)
        last = bf.ffill().iloc[-1]
        return raw * bf / last

    # ------------------------------------------------------------------
    # 交易可行性矩阵
    # ------------------------------------------------------------------

    @staticmethod
    def build_tradable(panels: dict, raw_close: pd.DataFrame, basic: pd.DataFrame):
        """
        构建有效性矩阵:
            valid      已上市且未退市(且有行情)
            tradable   可正常交易(非停牌)
            buy_open   次日可买入(非一字涨停/停牌)
            sell_open  次日可卖出(非一字跌停/停牌)
            is_st      ST 股标记
        """
        close_adj = panels['close']
        valid = close_adj.notna() & (close_adj > 0)

        # 用不复权收盘价计算日涨幅,判定涨跌停(复权价在除权日会失真)
        ret_raw = raw_close.pct_change()

        st_names = basic.set_index('MARKET_CODE')['SECURITY_NAME'].astype(str)
        is_st = pd.DataFrame(
            {c: ('ST' in st_names.get(c, '')) for c in raw_close.columns},
            index=raw_close.index,
        )

        def _limit_pct(col):
            prefix = col[:3]
            if prefix in _LIMIT_20_PREFIX:
                return 0.20
            return 0.05 if ('ST' in st_names.get(col, '')) else 0.10

        up_lim = pd.DataFrame({c: _limit_pct(c) - _LIMIT_TOLERANCE for c in raw_close.columns},
                              index=raw_close.index)
        down_lim = -up_lim

        limit_up = valid & (ret_raw >= up_lim)
        limit_down = valid & (ret_raw <= down_lim)

        # 停牌: 有效但无成交(成交量缺失或为 0),价格用前收盘填充
        vol = panels['volume']
        suspended = valid & (vol.isna() | (vol <= 0))
        # 未上市/退市
        tradable = valid & ~suspended

        buy_open = tradable & ~limit_up.shift(1, fill_value=False)    # 昨日涨停,今日大概率高开难买
        sell_open = tradable & ~limit_down.shift(1, fill_value=False)

        return dict(
            valid=valid, tradable=tradable, is_st=is_st,
            limit_up=limit_up, limit_down=limit_down,
            buy_open=buy_open, sell_open=sell_open,
        )

    # ------------------------------------------------------------------
    # 一站式构建
    # ------------------------------------------------------------------

    def build(self, begin_date, end_date, exclude_st: bool = False,
              max_stocks: int = None):
        """
        构建 P0 回测所需全部数据,返回 dict:
            panels   {field: adj DataFrame}  前复权面板
            raw      {field: raw DataFrame}  不复权面板(涨跌停判定/成交额用)
            flags    {valid/tradable/buy_open/sell_open/is_st}
            basic    证券基础信息
            universe 股票池列表
        """
        code_list, basic = self.get_universe(begin_date, end_date,
                                             exclude_st=exclude_st,
                                             max_stocks=max_stocks)
        raw = self.get_kline_panels(code_list, begin_date, end_date)

        bf = self.get_backward_factor(code_list)
        panels = {}
        for f in ('open', 'high', 'low', 'close'):
            panels[f] = self.forward_adjust(raw[f], bf) if not raw[f].empty else raw[f]
        for f in ('volume', 'amount'):
            panels[f] = raw[f]

        # 停牌日价格用前收盘填充(保证 close 无 0/NaN 断点,收益不跳空)
        for f in ('open', 'high', 'low', 'close'):
            panels[f] = panels[f].ffill()

        flags = self.build_tradable(panels, raw['close'], basic)
        flags['valid'] = flags['valid'] & panels['close'].notna()

        return dict(panels=panels, raw=raw, flags=flags, basic=basic,
                    universe=code_list)
