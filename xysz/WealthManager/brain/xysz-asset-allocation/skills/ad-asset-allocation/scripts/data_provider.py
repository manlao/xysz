# -*- coding: utf-8 -*-
"""
大类资产配置数据层 — 星耀数智(AmazingData)统一封装

核心能力：
    etf_kline_adj(code, begin, end) → 前复权日线（不复权收盘 × 前复权因子）
    asset_returns(codes, begin, end) → 多资产前复权日收益率对齐矩阵

数据链路（2026-09-24 实测验证）：
    登录 → 交易日历(BaseData.get_calendar)
        → ETF 日线(MarketData.query_kline) + 累计复权因子(BaseData.get_backward_factor)
"""

import os
import warnings

warnings.filterwarnings('ignore')

import pandas as pd


def _set_date_index(df: pd.DataFrame) -> pd.DataFrame:
    """query_kline 返回的 DataFrame → 以 int YYYYMMDD 为索引。

    实测（AmazingData 1.1.14）：index 为行号，日期在 kline_time 列
    （datetime64）；兼容日期直接在索引里的旧格式。
    """
    df = df.copy()
    if 'kline_time' in df.columns:
        df.index = [int(str(t)[:10].replace('-', '')) for t in pd.to_datetime(df['kline_time'])]
    else:
        df.index = [int(str(i)[:10].replace('-', '')) for i in df.index]
    return df


class DataProvider:
    """星耀数智数据提供器（登录一次，全流程复用）。"""

    def __init__(self, local_path: str = 'D:/AmazingData_local_data/'):
        import AmazingData as ad
        self._ad = ad
        port = int(os.environ.get('AD_PORT', '0'))
        for key in ('AD_USERNAME', 'AD_PASSWORD', 'AD_HOST'):
            if not os.environ.get(key) or not port:
                raise EnvironmentError(
                    '缺少环境变量 AD_USERNAME / AD_PASSWORD / AD_HOST / AD_PORT')
        if not ad.login(os.environ['AD_USERNAME'], os.environ['AD_PASSWORD'],
                        os.environ['AD_HOST'], port):
            # 单点登录限制：同账号另一连接占用时 login 可能失败，logout 后重试一次
            import time as _time
            try:
                ad.logout()
                _time.sleep(3)
                ok = ad.login(os.environ['AD_USERNAME'], os.environ['AD_PASSWORD'],
                              os.environ['AD_HOST'], port)
            except Exception:
                ok = False
            if not ok:
                raise ConnectionError('星耀数智登录失败（含重试），请检查账号与网络；'
                                      '若其他技能正在使用同一账号，请先关闭再试')
        print('[DataProvider] 登录成功: %s:%d' % (os.environ['AD_HOST'], port), flush=True)
        # AD 内部对 local_path 做字符串拼接，必须保留尾部斜杠
        lp = local_path.replace('\\', '/')
        self._local_path = lp if lp.endswith('/') else lp + '/'
        self._base = ad.BaseData()
        self._calendar = None
        self._market = None

    # ------------------------------------------------------------------
    # 基础
    # ------------------------------------------------------------------
    def calendar(self) -> list:
        """交易日历（int YYYYMMDD 升序，全历史）。"""
        if self._calendar is None:
            self._calendar = [int(d) for d in self._base.get_calendar()]
        return self._calendar

    def market(self):
        if self._market is None:
            self._market = self._ad.MarketData(self.calendar())
        return self._market

    def calendar_between(self, begin: int, end: int) -> list:
        return [d for d in self.calendar() if begin <= d <= end]

    def prev_trade_day(self, date: int) -> int:
        """date 前一个交易日（不含 date）。"""
        cal = self.calendar()
        for d in reversed(cal):
            if d < date:
                return d
        raise ValueError('交易日历中找不到 %s 之前的日子' % date)

    def next_trade_day(self, date: int) -> int:
        """date 后一个交易日（不含 date）。"""
        for d in self.calendar():
            if d > date:
                return d
        raise ValueError('交易日历中找不到 %s 之后的日子' % date)

    # ------------------------------------------------------------------
    # ETF 行情与复权
    # ------------------------------------------------------------------
    def etf_kline(self, code: str, begin: int, end: int) -> pd.DataFrame:
        """ETF 日线（不复权）。index=日期，含 open/high/low/close/volume。"""
        k = self.market().query_kline([code], begin_date=begin, end_date=end,
                                      period=self._ad.constant.Period.day.value)
        df = (k or {}).get(code)
        if df is None or not len(df):
            raise ValueError('ETF %s 在 %d-%d 无行情数据' % (code, begin, end))
        df = _set_date_index(df)
        return df.sort_index()

    def backward_factor(self, code: str) -> pd.Series:
        """累计后复权因子（index=日期 int）。全历史、无缺失，起点为 1.0。"""
        bf = self._base.get_backward_factor([code], local_path=self._local_path, is_local=False)
        if bf is None or not len(bf):
            return pd.Series(dtype=float)
        if isinstance(bf, pd.DataFrame):
            s = bf[code] if code in bf.columns else bf.iloc[:, 0]
        else:
            s = bf
        s = s.dropna().astype(float)
        if not len(s):
            return pd.Series(dtype=float)
        s.index = [int(str(i)[:10].replace('-', '')) for i in s.index]
        return s.sort_index()

    def forward_factor(self, code: str, begin: int, end: int) -> pd.Series:
        """前复权因子 = 累计后复权因子 / 区间内最后一个因子值。

        归一化到最新交易日 = 1.0，区间起点之前亦为 1.0（与"最新价即真实价"的前复权口径一致）。
        """
        bf = self.backward_factor(code)
        if bf.empty:
            return pd.Series(dtype=float)
        last = bf[bf.index <= end]
        if last.empty:
            return pd.Series(dtype=float)
        return bf / float(last.iloc[-1])

    def etf_kline_adj(self, code: str, begin: int, end: int) -> pd.DataFrame:
        """ETF 前复权日线（连续口径）。

        直接取累计复权因子并归一化：ff(d) = bf(d) / bf(end)，adj(d) = raw(d) × ff(d)。
        事件日（如分红、份额合并）bf 与 raw 反向跳变、相乘后相互抵消，序列连续，无需手工累乘。

        复权因子缺失时降级为不复权收盘并打印警告。
        返回 DataFrame：index=int 日期，含 close（前复权）/close_raw。
        """
        df = self.etf_kline(code, begin, end)
        ff = self.forward_factor(code, begin, end)
        df['close_raw'] = df['close']
        if ff.empty:
            print('[DataProvider][警告] %s 无复权因子，按不复权处理' % code, flush=True)
            return df
        df['close'] = df['close_raw'] * ff.reindex(df.index).ffill().fillna(1.0)
        return df

    def benchmark_close(self, code: str = '000300.SH', begin: int = None, end: int = None) -> pd.Series:
        """基准指数收盘价 Series（index=int 日期）。指数无需复权。"""
        k = self.market().query_kline([code], begin_date=begin, end_date=end,
                                      period=self._ad.constant.Period.day.value)
        df = (k or {}).get(code)
        if df is None or not len(df):
            raise ValueError('基准 %s 在 %s-%s 无行情数据' % (code, begin, end))
        df = _set_date_index(df)
        return df.sort_index()['close']

    def asset_returns(self, codes: list, begin: int, end: int) -> pd.DataFrame:
        """多资产前复权日收益率矩阵（index=int 日期，columns=代码）。

        各资产按自身交易日取前复权收盘 → pct_change → 按交易日并集外连接对齐，
        缺失日（如新上市较晚的 563300）不前向填充收益率，保留 NaN 供上层裁剪。
        """
        closes = {}
        for c in codes:
            df = self.etf_kline_adj(c, begin, end)
            closes[c] = df['close']
        px = pd.DataFrame(closes).sort_index()
        ret = px.pct_change()
        ret.iloc[0] = 0.0  # 首日收益记 0（净值口径 NAV0=1）
        return ret
