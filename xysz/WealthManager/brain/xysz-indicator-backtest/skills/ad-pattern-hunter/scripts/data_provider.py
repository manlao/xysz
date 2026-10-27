# -*- coding: utf-8 -*-
"""
形态猎手数据层 — 星耀数智(AmazingData)统一封装

数据链路：
    登录 → 交易日历(BaseData.get_calendar)
        → 股票池(InfoData.get_index_constituent 指数成分 / BaseData.get_code_list 全A)
        → 证券简称(BaseData.get_code_info)
        → 日线(MarketData.query_kline，分批拉取)
        → 前复权(BaseData.get_backward_factor 累计后复权因子归一化，
          不使用单次复权因子 get_adj_factor)
"""

import os
import sys
import time
import warnings

warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

# tgw 是 AmazingData 的强依赖，需先 pip install tgw（见 SKILL.md 前置条件）


def _norm_date(v):
    """任意日期表示(int YYYYMMDD / str / datetime) → int YYYYMMDD。"""
    s = str(v).strip()[:10].replace('-', '').replace('/', '')
    return int(s[:8])


def _set_date_index(df: pd.DataFrame, intraday: bool = False) -> pd.DataFrame:
    """query_kline 返回的 DataFrame → 以 int YYYYMMDD 为索引。

    实测（AmazingData 1.1.15）：index 为行号，日期在 kline_time 列
    （datetime64）；兼容日期直接在索引里的旧格式。
    intraday=True（分钟周期）：索引改为 'YYYYMMDD_HHMM' 字符串——同一交易日
    有多根 K 线，int 日期会冲突；前 8 位仍为所属交易日（复权对齐用）。
    """
    df = df.copy()
    if 'kline_time' in df.columns:
        ts = pd.to_datetime(df['kline_time'])
        if intraday:
            df.index = [t.strftime('%Y%m%d_%H%M') for t in ts]
        else:
            df.index = [int(t.strftime('%Y%m%d')) for t in ts]
    else:
        if intraday:
            df.index = [str(i).replace('-', '').replace(' ', '_').replace(':', '')[:13]
                        for i in df.index]
        else:
            df.index = [int(str(i)[:10].replace('-', '')) for i in df.index]
    return df


# 指数成分股池：universe 参数 → 指数代码
INDEX_POOLS = {
    'index300': ['000300.SH'],
    'index500': ['000905.SH'],
    'index1000': ['000852.SH'],
    'index_all': ['000300.SH', '000905.SH', '000852.SH'],
}


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
            # 单点登录限制：同账号另一连接占用时 login 可能失败，logout 后重试一次。
            # 实测（10-08）：tgw 登录失败时可能从 C 层直接 exit 进程（无 traceback），
            # 此时本重试不会执行——等待 1 分钟后重新运行即可恢复。
            try:
                ad.logout(os.environ['AD_USERNAME'])
                time.sleep(3)
                ok = ad.login(os.environ['AD_USERNAME'], os.environ['AD_PASSWORD'],
                              os.environ['AD_HOST'], port)
            except Exception:
                ok = False
            if not ok:
                raise ConnectionError('星耀数智登录失败（含重试），请检查账号与网络；'
                                      '若其他技能正在使用同一账号，请先关闭再试；'
                                      '若输出 login fail 后进程直接退出，多为单点登录'
                                      '冲突或登录频率限制，等待 1 分钟后重试')
        print('[DataProvider] 登录成功: %s:%d' % (os.environ['AD_HOST'], port), flush=True)
        # AD 内部对 local_path 做字符串拼接，必须保留尾部斜杠
        lp = local_path.replace('\\', '/')
        self._local_path = lp if lp.endswith('/') else lp + '/'
        self._base = ad.BaseData()
        self._info = ad.InfoData()
        self._calendar = None
        self._market = None
        self._stock_names = None

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

    def latest_trade_day(self) -> int:
        """最近一个交易日（含今天，若今天非交易日则前推）。"""
        return max(self.calendar())

    def calendar_between(self, begin: int, end: int) -> list:
        return [d for d in self.calendar() if begin <= d <= end]

    # ------------------------------------------------------------------
    # 股票池与名称
    # ------------------------------------------------------------------
    def index_constituents(self, index_codes: list) -> list:
        """指数在册成分股合集（OUTDATE 为空的当前成分，去重排序）。"""
        got = self._info.get_index_constituent(list(index_codes), is_local=False)
        codes = set()
        for _, df in (got or {}).items():
            if df is None or not len(df):
                continue
            col = 'CON_CODE' if 'CON_CODE' in df.columns else df.columns[1]
            out = 'OUTDATE' if 'OUTDATE' in df.columns else None
            for _, row in df.iterrows():
                if out is not None and out in df.columns:
                    o = row.get(out)
                    if o is not None and not (isinstance(o, float) and pd.isna(o)) and str(o) not in ('', 'nan', 'NaT'):
                        continue
                c = str(row.get(col, '')).strip()
                if c:
                    codes.add(c)
        return sorted(codes)

    def universe_codes(self, universe: str) -> list:
        """解析股票池参数 → 代码列表。

        index300 / index500 / index1000 / index_all：对应指数成分合集；
        allA：全市场沪深北 A 股（get_code_list）。
        """
        if universe == 'allA':
            codes = [str(c) for c in self._base.get_code_list(security_type='EXTRA_STOCK_A')]
            print('[DataProvider] 全A股票池: %d 只' % len(codes), flush=True)
            return codes
        if universe in INDEX_POOLS:
            codes = self.index_constituents(INDEX_POOLS[universe])
            print('[DataProvider] 股票池 %s: %d 只' % (universe, len(codes)), flush=True)
            return codes
        raise ValueError('不支持的股票池: %s（可选 index300/index500/index1000/index_all/allA）'
                         % universe)

    def stock_names(self, codes: list = None) -> dict:
        """证券简称 {code: 简称}（get_code_info，一次拉全表后缓存）。"""
        if self._stock_names is None:
            names = {}
            for attempt in (1, 2):  # get_code_info 服务端偶发返回 None，重试一次
                try:
                    ci = self._base.get_code_info(security_type='EXTRA_STOCK_A')
                    if ci is not None and 'symbol' in getattr(ci, 'columns', []):
                        names = {str(k): str(v) for k, v in zip(ci.index, ci['symbol'])}
                        names.update({k.split('.')[0]: v for k, v in names.items()})
                        break
                except Exception as exc:
                    print('[DataProvider] get_code_info 第%d次失败: %s'
                          % (attempt, str(exc)[:120]), flush=True)
                if attempt == 1:
                    time.sleep(2)
            self._stock_names = names
            if not names:
                print('[DataProvider] 简称表为空（服务端偶发异常），名称将显示为代码；'
                      '稍后重试可恢复', flush=True)
        if not codes:
            return self._stock_names
        out = {}
        for c in codes:
            c = str(c)
            out[c] = self._stock_names.get(c) or self._stock_names.get(c.split('.')[0]) or c
        return out

    # ------------------------------------------------------------------
    # K线与复权（支持 13 个周期：min1..min120 / day / week / month / season / year）
    # ------------------------------------------------------------------
    # 合法周期名（与 ad.constant.Period 成员一致）
    TIMEFRAMES = ('min1', 'min3', 'min5', 'min10', 'min15', 'min30', 'min60',
                  'min120', 'day', 'week', 'month', 'season', 'year')

    def stock_kline_batch(self, codes: list, begin: int, end: int,
                          batch: int = 100, progress: bool = True,
                          timeframe: str = 'day') -> dict:
        """股票 K 线（不复权），分批拉取。返回 {code: DataFrame(index, OHLCV+amount)}。

        timeframe: 周期名，见 TIMEFRAMES（默认 day）。
        日线索引为 int YYYYMMDD；分钟线索引为 'YYYYMMDD_HHMM' 字符串（同日多根）。
        全市场约 5000+ 只，单次传接口会失败，必须分批；失败批次跳过并告警。
        """
        if timeframe not in self.TIMEFRAMES:
            raise ValueError('未知周期 %r，可选: %s' % (timeframe, ','.join(self.TIMEFRAMES)))
        intraday = timeframe.startswith('min')
        period_val = getattr(self._ad.constant.Period, timeframe).value
        result = {}
        mkt = self.market()
        lst = [str(c) for c in codes]
        n_batches = (len(lst) + batch - 1) // batch
        for i in range(0, len(lst), batch):
            part = lst[i:i + batch]
            bno = i // batch + 1
            if progress:
                print('[DataProvider] K线(%s) 批次 %d/%d (%d 只)...'
                      % (timeframe, bno, n_batches, len(part)), flush=True)
            try:
                k = mkt.query_kline(part, begin_date=begin, end_date=end,
                                    period=period_val)
            except Exception as exc:
                print('[DataProvider] K线(%s) 批次 %d 失败，跳过: %s'
                      % (timeframe, bno, str(exc)[:120]), flush=True)
                continue
            for code, df in (k or {}).items():
                if df is None or not len(df):
                    continue
                df = _set_date_index(df, intraday=intraday).sort_index()
                df = df[(df['close'] > 0) | (df['volume'] > 0)]
                if len(df):
                    result[code] = df
        return result

    def backward_factor_batch(self, codes: list, batch: int = 100) -> pd.DataFrame:
        """整池后复权因子（累计口径）。返回 DataFrame(index=日期int, column=代码)。

        AD 的 get_backward_factor 返回自上市起累计的后复权因子（1990 年起点为 1.0），
        已包含分红与拆分/合并的影响；前复权因子 = bf(d) / bf(区间末日)。
        分批拉取（默认 100 只/批），失败批次跳过并告警。
        """
        lst = sorted(set(str(c) for c in codes))
        frames = []
        n_batches = (len(lst) + batch - 1) // batch
        for i in range(0, len(lst), batch):
            part = lst[i:i + batch]
            bno = i // batch + 1
            try:
                bf = self._base.get_backward_factor(part, local_path=self._local_path,
                                                    is_local=False)
            except Exception as exc:
                print('[DataProvider] 复权因子批次 %d/%d 失败，跳过: %s'
                      % (bno, n_batches, str(exc)[:120]), flush=True)
                continue
            if bf is None or not len(bf):
                continue
            df = bf if isinstance(bf, pd.DataFrame) else pd.DataFrame(bf)
            df.index = [_norm_date(idx) for idx in df.index]
            df = df.sort_index().apply(pd.to_numeric, errors='coerce')
            frames.append(df)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, axis=1)

    @staticmethod
    def forward_adjust_ohlc(df: pd.DataFrame, factor_col: pd.Series) -> pd.DataFrame:
        """对单只股票的 K 线 DataFrame 做 OHLC 前复权（日线与分钟线通用）。

        factor_col: 该股后复权因子（index=交易日 int YYYYMMDD，已排序）。
        F(d) = bf(d) / bf(区间内最新有效交易日)，最新 bar F=1，序列向前连续。
        日线索引即交易日；分钟线索引 'YYYYMMDD_HHMM'，按前 8 位所属交易日对齐因子。
        无因子的日期沿用前值（ffill），完全无因子时原样返回（不复权）。
        """
        df = df.copy()
        if pd.api.types.is_numeric_dtype(df.index):
            bar_dates = np.asarray(df.index, dtype=np.int64)
        else:  # 分钟线索引 'YYYYMMDD_HHMM' → 所属交易日
            bar_dates = np.asarray([int(str(ix)[:8]) for ix in df.index], dtype=np.int64)
        f = factor_col.reindex(pd.Index(bar_dates)).ffill()
        f.index = df.index
        f = f.dropna()
        if not len(f):
            return df
        ratio = (f / f.iloc[-1]).reindex(df.index).ffill()
        for col in ('open', 'high', 'low', 'close'):
            if col in df.columns:
                df[col] = df[col] * ratio
        return df
