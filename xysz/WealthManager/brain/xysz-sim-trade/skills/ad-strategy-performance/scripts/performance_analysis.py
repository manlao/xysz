# -*- coding: utf-8 -*-
"""
策略业绩分析核心模块

    - 收益类: 累计/年化/日均收益 / 月度与年度收益表 / 月均收益 / 月胜率 / 日胜率
               / 盈亏比 / 最大连涨连跌天数
    - 风险类: 年化/日/月波动率 / 最大回撤(含起止与修复日) / 当前回撤 / 距上次创新高
               与最长回撤持续交易日 / 下行风险 / 偏度 / 峰度
    - 相对基准: Beta / Alpha / 跟踪误差 / 信息比率 / 特雷诺 / 超额收益
    - 风险调整: 夏普 / 索提诺 / 卡玛
    - 分布类: 日收益率分布(12档)
    - 数据质量: 以基准交易日历为参照的数据断档检测

"""

import os
import sys
from datetime import datetime
from typing import Dict, Optional

import numpy as np
import pandas as pd


# ============================================================
# 数据加载
# ============================================================

def load_nav_csv(
    path: str,
    date_col: Optional[str] = None,
    value_col: Optional[str] = None,
) -> pd.Series:
    """
    加载策略净值 CSV, 返回净值序列 (index=日期, 归一化到首日=1)。

    自动识别:
        - 日期列: date / time_tag / datetime / 日期 / 净值日期 / index列
        - 数值列: net_value / total_balance(自动换算净值) / 净值 / 总资产

    :param path: CSV 路径
    :param date_col: 指定日期列名, None 自动识别
    :param value_col: 指定数值列名, None 自动识别
    """
    df = pd.read_csv(path)
    if df.empty:
        raise ValueError(f"CSV 文件为空: {path}")

    # ---- 日期列 ----
    if date_col is None:
        candidates = ['date', 'time_tag', 'datetime', 'trade_date', '日期', '净值日期']
        date_col = next((c for c in candidates if c in df.columns), df.columns[0])
    if date_col not in df.columns:
        raise ValueError(f"日期列不存在: {date_col}, 现有列: {list(df.columns)}")

    # ---- 数值列 ----
    if value_col is None:
        if 'net_value' in df.columns:
            value_col = 'net_value'
        elif 'total_balance' in df.columns:
            value_col = 'total_balance'
        elif '净值' in df.columns:
            value_col = '净值'
        elif '总资产' in df.columns:
            value_col = '总资产'
        else:
            raise ValueError(
                f"无法识别净值列, 现有列: {list(df.columns)}。"
                f"请通过 --value-col 指定 (支持 net_value 或 total_balance)"
            )
    if value_col not in df.columns:
        raise ValueError(f"数值列不存在: {value_col}, 现有列: {list(df.columns)}")

    # ---- 构建净值序列 ----
    s = pd.Series(
        df[value_col].astype(float).values,
        index=pd.DatetimeIndex(pd.to_datetime(df[date_col])),
        name='nav',
    ).sort_index()
    # 同一交易日多条记录取最后一条
    s = s[~s.index.duplicated(keep='last')]

    if (s <= 0).any():
        bad = s[s <= 0]
        raise ValueError(f"净值数据存在非正值, 共 {len(bad)} 条, 示例: {bad.index[0]}={bad.iloc[0]}")

    return s / s.iloc[0]


def fetch_benchmark_from_api(
    code: str = '000300.SH',
    begin_date: int = 20250101,
    end_date: int = 20251231,
) -> Optional[pd.Series]:
    """
    经星耀数智 AmazingData 拉取基准指数日线收盘价。

    需环境变量: AD_USERNAME / AD_PASSWORD / AD_HOST / AD_PORT。
    失败返回 None (不中断主流程, 本次分析不对比基准)。
    """
    try:
        import AmazingData as ad
        from AmazingData.utils.constant import Period
    except ImportError as e:
        print(f"[警告] 导入 AmazingData 失败: {e}", file=sys.stderr)
        print("[警告] 无法在线拉取基准, 本次分析不对比基准", file=sys.stderr)
        return None

    missing = [v for v in ['AD_USERNAME', 'AD_PASSWORD', 'AD_HOST', 'AD_PORT']
               if not os.environ.get(v)]
    if missing:
        print(f"[警告] 缺少环境变量 {', '.join(missing)}, 无法在线拉取基准, 本次分析不对比基准",
              file=sys.stderr)
        return None

    try:
        ad.login(
            username=os.environ['AD_USERNAME'],
            password=os.environ['AD_PASSWORD'],
            host=os.environ['AD_HOST'],
            port=int(os.environ['AD_PORT']),
        )
        result = ad.MarketData(ad.BaseData().get_calendar(data_type='int')).query_kline(
            code_list=[code],
            begin_date=begin_date,
            end_date=end_date,
            period=Period.day.value,
        )
        if code not in result or result[code] is None or result[code].empty:
            print(f"[警告] 未拉取到基准 {code} 行情", file=sys.stderr)
            return None
        df = result[code].set_index('kline_time')['close'].astype(float)
        df.index = pd.DatetimeIndex(df.index)
        return df.sort_index()
    except Exception as e:
        print(f"[警告] 在线拉取基准失败: {e}", file=sys.stderr)
        return None


# ============================================================
# 策略业绩分析主类
# ============================================================

class PerformanceAnalyzer:
    """
    策略业绩分析器。

    :param nav: 策略净值序列 (index=日期, 建议归一化到首日=1)
    :param benchmark_close: 基准收盘价序列, None 则不做相对基准分析
    :param annual_days: 年化天数, 默认 244
    :param rf: 无风险年利率, 默认 0.02 (2%)
    """

    def __init__(self, nav: pd.Series, benchmark_close: Optional[pd.Series] = None,
                 annual_days: int = 244, rf: float = 0.02):
        self.annual_days = annual_days
        self.rf = rf
        self.has_benchmark = benchmark_close is not None and len(benchmark_close) > 0

        if self.has_benchmark:
            # 对齐: 取双方共同交易日
            common = nav.index.intersection(benchmark_close.index)
            if len(common) < 2:
                raise ValueError("策略净值与基准的共同交易日不足 2 天, 请检查日期区间")
            dropped = len(nav) - len(common)
            if dropped > 0:
                print(f"[提示] 对齐基准后丢弃 {dropped} 个非共同交易日", file=sys.stderr)
            self.nav = nav.loc[common]
            self.benchmark_close = benchmark_close.loc[common]
            # 保留未对齐的原始序列, 供数据断档检测使用（对齐会抹掉缺失日的证据）
            self.raw_nav = nav
            self.raw_benchmark_close = benchmark_close
        else:
            self.nav = nav.sort_index()
            self.benchmark_close = None
            self.raw_nav = self.nav
            self.raw_benchmark_close = None

        self.result: Dict = {}

    # ---------- 基础序列 ----------

    @property
    def nav_ret(self) -> pd.Series:
        return self.nav.pct_change().dropna() * 100  # 百分比

    @property
    def benchmark_nav(self) -> Optional[pd.Series]:
        if self.benchmark_close is None:
            return None
        return self.benchmark_close / self.benchmark_close.iloc[0]

    @property
    def bench_ret(self) -> Optional[pd.Series]:
        if self.benchmark_close is None:
            return None
        return self.benchmark_close.pct_change().dropna() * 100

    # ---------- 单序列指标 (返回百分比口径) ----------

    def cum_return(self, nav: pd.Series) -> float:
        return (nav.iloc[-1] / nav.iloc[0] - 1) * 100

    def annual_return(self, nav: pd.Series) -> float:
        n = len(nav) - 1
        if n <= 0:
            return 0.0
        return ((nav.iloc[-1] / nav.iloc[0]) ** (self.annual_days / n) - 1) * 100

    def annual_volatility(self, ret: pd.Series) -> float:
        return ret.std(ddof=1) * np.sqrt(self.annual_days) if len(ret) > 1 else 0.0

    def max_drawdown(self, nav: pd.Series) -> Dict:
        cummax = nav.expanding().max()
        dd = nav / cummax - 1
        valley_date = dd.idxmin()
        mdd = dd.min() * 100
        peak_date = nav.loc[:valley_date].idxmax()
        peak_val = nav.loc[peak_date]
        after = nav.loc[valley_date:]
        recovered = after[after >= peak_val]
        recover_date = recovered.index[0] if len(recovered) > 0 else None
        return {
            'max_drawdown': mdd,                       # 负值 %
            'drawdown_series': dd * 100,
            'peak_date': peak_date,
            'valley_date': valley_date,
            'recover_date': recover_date,
        }

    def downside_risk(self, ret: pd.Series) -> float:
        threshold = self.rf * 100 / self.annual_days
        downside = ret.where(ret < threshold, 0.0)
        return downside.std(ddof=1) * np.sqrt(self.annual_days) if len(ret) > 1 else 0.0

    def day_win_ratio(self, ret: pd.Series) -> float:
        return (ret >= 0).sum() / len(ret) * 100 if len(ret) else 0.0

    def day_return_distribution(self, ret: pd.Series) -> Dict[str, float]:
        """日收益率分布 (12 档, 返回占比 %)。"""
        bins = [
            ('-10%以下', lambda r: r < -10),
            ('-10%~-5%', lambda r: (r >= -10) & (r < -5)),
            ('-5%~-3%', lambda r: (r >= -5) & (r < -3)),
            ('-3%~-2%', lambda r: (r >= -3) & (r < -2)),
            ('-2%~-1%', lambda r: (r >= -2) & (r < -1)),
            ('-1%~0%', lambda r: (r >= -1) & (r < 0)),
            ('0%~1%', lambda r: (r >= 0) & (r < 1)),
            ('1%~2%', lambda r: (r >= 1) & (r < 2)),
            ('2%~3%', lambda r: (r >= 2) & (r < 3)),
            ('3%~5%', lambda r: (r >= 3) & (r < 5)),
            ('5%~10%', lambda r: (r >= 5) & (r < 10)),
            ('10%以上', lambda r: r >= 10),
        ]
        n = len(ret)
        return {label: (cond(ret).sum() / n * 100) if n else 0.0 for label, cond in bins}

    def monthly_returns(self, nav: pd.Series) -> Dict[str, float]:
        """月度收益率, key 为 'YYYY-MM' (%)。"""
        month_last = nav.resample('ME').last()
        month_ret = month_last.pct_change() * 100
        month_ret.iloc[0] = (month_last.iloc[0] / nav.iloc[0] - 1) * 100
        return {ts.strftime('%Y-%m'): round(v, 4) for ts, v in month_ret.items()}

    def annual_returns(self, nav: pd.Series) -> Dict[int, float]:
        """年度收益率, key 为年份 (%)。首年按净值首日到年末计算。"""
        year_last = nav.resample('YE').last()
        year_ret = year_last.pct_change() * 100
        year_ret.iloc[0] = (year_last.iloc[0] / nav.iloc[0] - 1) * 100
        return {ts.year: round(float(v), 4) for ts, v in year_ret.items()}

    def annual_max_drawdown(self, nav: pd.Series) -> Dict[int, float]:
        """分年度最大回撤 (%)。"""
        return {int(year): round(self.max_drawdown(seg)['max_drawdown'], 4)
                for year, seg in nav.groupby(nav.index.year)}

    def drawdown_state(self, nav: pd.Series) -> Dict:
        """当前回撤状态: 当前回撤/距上次新高交易日数/当前回撤已持续天数/最长回撤持续天数。"""
        cummax = nav.expanding().max()
        dd = nav / cummax - 1
        current_dd = float(dd.iloc[-1]) * 100
        high_date = cummax.idxmax()
        high_pos = nav.index.get_loc(high_date)
        since_high = len(nav) - 1 - high_pos
        in_dd = (dd < -1e-12).values
        durations, start = [], None
        for i, flag in enumerate(in_dd):
            if flag and start is None:
                start = max(i - 1, 0)          # 峰值位置为回撤开始前一交易日
            elif not flag and start is not None:
                durations.append(i - start)
                start = None
        if start is not None:                   # 未修复的回撤计到期末
            durations.append(len(nav) - start)
        return {
            'current_drawdown': current_dd,
            'days_since_high': int(since_high),
            'current_drawdown_days': int(since_high),
            'longest_drawdown_days': int(max(durations)) if durations else 0,
        }

    def profit_loss_stats(self, ret: pd.Series) -> Dict:
        """盈亏结构: 平均盈利日/平均亏损日/盈亏比/最大连涨连跌天数。"""
        wins, losses = ret[ret > 0], ret[ret < 0]
        avg_win = float(wins.mean()) if len(wins) else 0.0
        avg_loss = float(losses.mean()) if len(losses) else 0.0

        def max_consecutive(mask) -> int:
            best = cur = 0
            for flag in mask:
                cur = cur + 1 if flag else 0
                best = max(best, cur)
            return best

        return {
            'avg_win_day': avg_win,
            'avg_loss_day': avg_loss,
            'profit_loss_ratio': abs(avg_win / avg_loss) if avg_loss != 0 else None,
            'max_consecutive_up': max_consecutive((ret > 0).values),
            'max_consecutive_down': max_consecutive((ret < 0).values),
        }

    def detect_data_gaps(self, nav: pd.Series, calendar: Optional[pd.Series] = None) -> Dict:
        """
        数据断档检测: 以基准指数(默认沪深300)交易日历为参照, 比对净值序列缺失的交易日。

        :param nav: 策略净值序列
        :param calendar: 基准交易日序列; None 时不检测
        :return: {'missing_days': [Timestamp...], 'extra_days': [Timestamp...], 'checked': bool}
        """
        if calendar is None or len(calendar) == 0:
            return {'missing_days': [], 'extra_days': [], 'checked': False}
        cal_idx = calendar.index
        cal = cal_idx[(cal_idx >= nav.index[0]) & (cal_idx <= nav.index[-1])]
        missing = cal.difference(nav.index)
        extra = nav.index.difference(cal)
        return {
            'missing_days': list(missing),
            'extra_days': list(extra),
            'checked': True,
        }

    # ---------- 单边全量指标 ----------

    def _single_side(self, nav: pd.Series, ret: pd.Series) -> Dict:
        mdd_info = self.max_drawdown(nav)
        monthly = self.monthly_returns(nav)
        month_vals = [v for v in monthly.values()]
        skew = ret.skew() if len(ret) > 2 else 0.0
        kurt = ret.kurt() if len(ret) > 3 else 0.0
        ann_ret = self.annual_return(nav)
        ann_vol = self.annual_volatility(ret)
        dsr = self.downside_risk(ret)
        pl_stats = self.profit_loss_stats(ret)
        dd_state = self.drawdown_state(nav)
        return {
            'cum_return': self.cum_return(nav),
            'annual_return': ann_ret,
            'daily_return_avg': ret.mean(),
            'daily_volatility': ret.std(ddof=1) if len(ret) > 1 else 0.0,
            'annual_volatility': ann_vol,
            'monthly_volatility': float(np.std(month_vals, ddof=1)) if len(month_vals) > 1 else 0.0,
            'max_drawdown': mdd_info['max_drawdown'],
            'drawdown_series': mdd_info['drawdown_series'],
            'mdd_peak_date': mdd_info['peak_date'],
            'mdd_valley_date': mdd_info['valley_date'],
            'mdd_recover_date': mdd_info['recover_date'],
            'current_drawdown': dd_state['current_drawdown'],
            'days_since_high': dd_state['days_since_high'],
            'longest_drawdown_days': dd_state['longest_drawdown_days'],
            'downside_risk': dsr,
            'skewness': float(skew),
            'kurtosis': float(kurt),
            'day_win_ratio': self.day_win_ratio(ret),
            'day_return_distribution': self.day_return_distribution(ret),
            'monthly_returns': monthly,
            'annual_returns': self.annual_returns(nav),
            'annual_max_drawdown': self.annual_max_drawdown(nav),
            **pl_stats,
            'monthly_return_avg': float(np.mean(month_vals)) if month_vals else 0.0,
            'month_win_ratio': (sum(1 for v in month_vals if v > 0) / len(month_vals) * 100)
                               if month_vals else 0.0,
            'sharpe': (ann_ret - self.rf * 100) / ann_vol if ann_vol != 0 else None,
            'sortino': (ann_ret - self.rf * 100) / dsr if dsr != 0 else None,
        }

    # ---------- 主入口 ----------

    def run(self) -> Dict:
        nav_ret, bench_ret = self.nav_ret, self.bench_ret
        res: Dict = {
            'strategy': self._single_side(self.nav, nav_ret),
            'annual_days': self.annual_days,
            'rf': self.rf,
            'start_date': self.nav.index[0],
            'end_date': self.nav.index[-1],
            'n_days': len(self.nav),
        }
        res['calmar'] = (res['strategy']['annual_return'] - self.rf * 100) \
            / abs(res['strategy']['max_drawdown']) \
            if res['strategy']['max_drawdown'] != 0 else None
        # 图表用序列
        res['nav_series'] = self.nav
        res['benchmark_nav_series'] = self.benchmark_nav
        # 数据断档检测 (以基准指数交易日历为参照, 用未对齐的原始净值序列比对)
        res['data_gaps'] = self.detect_data_gaps(
            self.raw_nav, self.raw_benchmark_close if self.has_benchmark else None)

        if self.has_benchmark:
            res['benchmark'] = self._single_side(self.benchmark_nav, bench_ret)
            # Beta: 样本协方差 / 样本方差 (ddof=1)
            cov = np.cov(nav_ret.values, bench_ret.values, ddof=1)[0, 1]
            var = np.var(bench_ret.values, ddof=1)
            beta = cov / var if var != 0 else None
            res['beta'] = beta
            ann_ret = res['strategy']['annual_return']
            bench_ann = res['benchmark']['annual_return']
            res['alpha'] = (ann_ret - (self.rf * 100 + beta * (bench_ann - self.rf * 100)))
            # 跟踪误差: 超额日收益年化
            excess = nav_ret.values - bench_ret.values
            res['tracking_error'] = float(np.std(excess, ddof=1) * np.sqrt(self.annual_days))
            res['information_ratio'] = (ann_ret - bench_ann) / res['tracking_error'] \
                if res['tracking_error'] != 0 else None
            res['treynor'] = (ann_ret - self.rf * 100) / beta if beta else None
            res['excess_cum_return'] = res['strategy']['cum_return'] - res['benchmark']['cum_return']
            res['excess_annual_return'] = ann_ret - bench_ann
            res['correlation'] = float(np.corrcoef(nav_ret.values, bench_ret.values)[0, 1])
        self.result = res
        return res

    # ---------- 终端摘要 ----------

    def print_summary(self) -> None:
        res = self.result
        if not res:
            self.run()
            res = self.result
        s, b = res['strategy'], res.get('benchmark') or {}
        # (标签, 策略值, 基准值, 超额是否有意义, 是否按整数显示)
        rows = [
            ('累计收益率 (%)', s['cum_return'], b.get('cum_return'), True, False),
            ('年化收益率 (%)', s['annual_return'], b.get('annual_return'), True, False),
            ('年化波动率 (%)', s['annual_volatility'], b.get('annual_volatility'), True, False),
            ('最大回撤 (%)', s['max_drawdown'], b.get('max_drawdown'), True, False),
            ('当前回撤 (%)', s['current_drawdown'], b.get('current_drawdown'), False, False),
            ('距上次新高 (交易日)', s['days_since_high'], None, False, True),
            ('最长回撤持续 (交易日)', s['longest_drawdown_days'], None, False, True),
            ('下行风险 (%)', s['downside_risk'], b.get('downside_risk'), True, False),
            ('夏普比率', s['sharpe'], b.get('sharpe'), True, False),
            ('索提诺比率', s['sortino'], b.get('sortino'), True, False),
            ('卡玛比率', res.get('calmar'), None, False, False),
            ('日胜率 (%)', s['day_win_ratio'], b.get('day_win_ratio'), True, False),
            ('盈亏比', s['profit_loss_ratio'], b.get('profit_loss_ratio'), False, False),
            ('最大连涨 (日)', s['max_consecutive_up'], None, False, True),
            ('最大连跌 (日)', s['max_consecutive_down'], None, False, True),
            ('月均收益 (%)', s['monthly_return_avg'], b.get('monthly_return_avg'), True, False),
            ('月胜率 (%)', s['month_win_ratio'], b.get('month_win_ratio'), True, False),
            ('偏度', s['skewness'], b.get('skewness'), True, False),
            ('峰度', s['kurtosis'], b.get('kurtosis'), True, False),
        ]
        lines = [f"策略业绩分析摘要  {res['start_date']:%Y-%m-%d} ~ {res['end_date']:%Y-%m-%d}"
                 f"  ({res['n_days']} 个交易日, 年化天数={res['annual_days']}, 无风险利率={res['rf']*100:.1f}%)"]

        if self.has_benchmark:
            header = f"{'指标':<22}{'策略':>12}{'基准':>12}{'超额':>12}"
            lines.append(header)
            lines.append('-' * len(header))
            for label, sval, bval, show_excess, as_int in rows:
                exc = (sval - bval) if (show_excess and sval is not None and bval is not None) else None
                lines.append(f"{label:<22}{self._fmt(sval, as_int):>12}"
                             f"{self._fmt(bval, as_int):>12}{self._fmt(exc, as_int):>12}")
            lines.append('-' * len(header))
            lines.append(f"{'相对基准指标':<22}{'值':>12}")
            for label, val in [('Beta', res.get('beta')), ('Alpha (%)', res.get('alpha')),
                               ('跟踪误差 (%)', res.get('tracking_error')),
                               ('信息比率', res.get('information_ratio')),
                               ('特雷诺比率', res.get('treynor')),
                               ('日收益相关系数', res.get('correlation')),
                               ('超额累计收益 (%)', res.get('excess_cum_return')),
                               ('超额年化收益 (%)', res.get('excess_annual_return'))]:
                lines.append(f"{label:<22}{self._fmt(val):>12}")
        else:
            header = f"{'指标':<22}{'策略':>12}"
            lines.append(header)
            lines.append('-' * len(header))
            for label, sval, _, _, as_int in rows:
                lines.append(f"{label:<22}{self._fmt(sval, as_int):>12}")

        # 年度收益
        ann = s['annual_returns']
        if ann:
            lines.append('')
            b_ann = b.get('annual_returns') or {}
            if self.has_benchmark:
                lines.append(f"{'年度':<8}{'策略':>10}{'基准':>10}{'超额':>10}")
                lines.append('-' * 38)
            else:
                lines.append(f"{'年度':<8}{'策略':>10}")
                lines.append('-' * 18)
            for year, val in ann.items():
                line = f"{year:<8}{self._fmt(val):>10}"
                if self.has_benchmark:
                    bv = b_ann.get(year)
                    ev = (val - bv) if (val is not None and bv is not None) else None
                    line += f"{self._fmt(bv):>10}{self._fmt(ev):>10}"
                lines.append(line)

        # 数据断档提示 (以基准交易日历为参照)
        gap_info = res.get('data_gaps') or {}
        if gap_info.get('checked'):
            missing, extra = gap_info['missing_days'], gap_info['extra_days']
            if missing or extra:
                lines.append('')
                if missing:
                    lines.append(f"[数据断档] 相对基准交易日历缺失 {len(missing)} 个交易日"
                                 f"（净值序列不完整，会影响波动率等指标）：")
                    for d in missing[:10]:
                        lines.append(f"  缺失 {d:%Y-%m-%d}")
                    if len(missing) > 10:
                        lines.append(f"  ...（其余 {len(missing) - 10} 个已省略）")
                if extra:
                    lines.append(f"[数据异常] 净值序列中有 {len(extra)} 个日期不在基准交易日历内："
                                 + ', '.join(f"{d:%Y-%m-%d}" for d in extra[:5])
                                 + ('...' if len(extra) > 5 else ''))
        print('\n'.join(lines))

    @staticmethod
    def _fmt(v, as_int: bool = False) -> str:
        if v is None:
            return '—'
        if as_int:
            return f"{int(round(v))}"
        return f"{v:.4f}" if abs(v) < 1 else f"{v:.2f}"


# ============================================================
# CLI
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description='策略业绩分析 (星耀数智策略业绩分析 Skill)')
    parser.add_argument('--input', required=True, help='策略净值 CSV 路径')
    parser.add_argument('--date-col', default=None, help='日期列名 (默认自动识别)')
    parser.add_argument('--value-col', default=None, help='净值列名 (默认自动识别 net_value/total_balance)')
    parser.add_argument('--benchmark-code', default='000300.SH',
                        help='基准指数代码, 默认 000300.SH (沪深300); 传空字符串则不对比基准')
    parser.add_argument('--period', default=None,
                        choices=['all', '半年', '1年', '3年', '5年', 'ytd'],
                        help='区间预设: all全部(默认)/半年/1年/3年/5年/ytd今年以来, 以净值末日为终点; 与--start二选一')
    parser.add_argument('--start', default=None, help='起始日期 YYYYMMDD')
    parser.add_argument('--end', default=None, help='结束日期 YYYYMMDD')
    parser.add_argument('--annual-days', type=int, default=244, help='年化天数, 默认 244')
    parser.add_argument('--rf', type=float, default=2.0, help='无风险年利率（%%），默认 2.0')
    parser.add_argument('--title', default='策略业绩分析报告', help='报告标题')
    parser.add_argument('--output', default=None,
                        help='输出 HTML 路径; 缺省输出到运行时 cwd 的 '
                             'output/strategy_performance_report_<YYYYMMDD_HHMMSS>.html')
    parser.add_argument('--open', action='store_true', help='生成后用浏览器打开报告')
    args = parser.parse_args()

    nav = load_nav_csv(args.input, date_col=args.date_col, value_col=args.value_col)

    end = pd.Timestamp(args.end) if args.end else nav.index[-1]
    if args.start:
        start = pd.Timestamp(args.start)
    elif args.period and args.period not in ('all',):
        if args.period == 'ytd':
            start = pd.Timestamp(year=end.year, month=1, day=1)
        elif args.period == '半年':
            start = end - pd.DateOffset(months=6)
        else:
            start = end - pd.DateOffset(years=int(args.period[0]))
    else:
        start = nav.index[0]
    nav = nav.loc[start:end]
    if len(nav) < 2:
        raise ValueError('区间内净值数据不足 2 条')

    # 基准: 仅支持经星耀数智 AmazingData 在线拉取
    benchmark_close = None
    if args.benchmark_code:
        benchmark_close = fetch_benchmark_from_api(
            code=args.benchmark_code,
            begin_date=int(start.strftime('%Y%m%d')),
            end_date=int(end.strftime('%Y%m%d')),
        )
    if benchmark_close is not None:
        benchmark_close = benchmark_close.loc[start:end]
        if len(benchmark_close) < 2:
            print('[警告] 基准在区间内数据不足, 忽略基准对比', file=sys.stderr)
            benchmark_close = None

    analyzer = PerformanceAnalyzer(
        nav, benchmark_close,
        annual_days=args.annual_days, rf=args.rf / 100,
    )
    analyzer.run()
    analyzer.print_summary()

    # HTML 报告
    from report_renderer import PerformanceReport
    common_names = {'000300.SH': '沪深300', '000905.SH': '中证500', '000852.SH': '中证1000',
                    '000001.SH': '上证指数', '399006.SZ': '创业板指', '399330.SZ': '深证300'}
    if benchmark_close is None:
        bench_name = ''
    else:
        bench_name = common_names.get(args.benchmark_code, args.benchmark_code)
    report = PerformanceReport(title=args.title)
    output_path = args.output or os.path.join(
        'output',
        f'strategy_performance_report_{datetime.now():%Y%m%d_%H%M%S}.html',
    )
    report.generate(analyzer.result, output_path, benchmark_name=bench_name)
    if args.open:
        import webbrowser
        webbrowser.open('file://' + os.path.abspath(output_path))


if __name__ == '__main__':
    main()
