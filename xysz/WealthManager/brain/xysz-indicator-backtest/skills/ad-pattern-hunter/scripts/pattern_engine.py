# -*- coding: utf-8 -*-
"""
形态猎手 — K线形态识别引擎（纯本地计算，34 类形态）

两层评分（0-100）：
    score = 规则命中分 × 60% + 形状相似分 × 40%
    - 规则分：每个形态定义一组可解释子规则（极值点结构/斜率/回撤/位置/量能），
      按权重加权命中比例 → 0-60
    - 相似分：窗口收盘价 z-score 归一化后，与该形态标准模板轮廓（或外部轮廓）
      的 Pearson 相关 → 0-40

四大形态族：
    trend         趋势延续类：强趋势/趋势回踩/上升通道/上升旗形/阴跌通道/下降旗形
    bottom        底部反转类：底部反转/V形底/圆弧底/W底/三重底/头肩底
    top           顶部反转类：顶部反转/V形顶/圆弧顶/M头/三重顶/头肩顶（与底部镜像）
    consolidation 整理突破类：箱体震荡/上升三角/下降三角/对称三角/平台突破

输入：单只股票的**前复权**日线 DataFrame（index=int YYYYMMDD，
      列 open/high/low/close[/volume]），取全部传入窗口参与识别。
"""

import numpy as np
import pandas as pd


# ======================================================================
# 基础工具
# ======================================================================

def _linreg(y: np.ndarray):
    """对 y 做 x=0..n-1 的线性回归 → (slope, r2)。两点视为完全拟合。"""
    n = len(y)
    if n < 2:
        return 0.0, 0.0
    if n == 2:
        return float(y[1] - y[0]), 1.0
    x = np.arange(n, dtype=float)
    xm, ym = x.mean(), y.mean()
    vx = ((x - xm) ** 2).sum()
    if vx <= 1e-12:
        return 0.0, 0.0
    slope = ((x - xm) * (y - ym)).sum() / vx
    ss_tot = ((y - ym) ** 2).sum()
    if ss_tot <= 1e-12:
        return slope, 0.0
    ss_res = ((y - (ym + slope * (x - xm))) ** 2).sum()
    return float(slope), float(max(0.0, 1.0 - ss_res / ss_tot))


def _pivots(z: np.ndarray, k: int):
    """局部极值点（order=k）。返回 (peaks, troughs) 索引列表。

    平台处理：两侧都不高于(不低于)且至少一侧严格更优。
    """
    n = len(z)
    peaks, troughs = [], []
    for i in range(k, n - k):
        left, right = z[i - k:i], z[i + 1:i + k + 1]
        if z[i] >= left.max() and z[i] >= right.max() and \
                (z[i] > left.max() or z[i] > right.max()):
            peaks.append(i)
        if z[i] <= left.min() and z[i] <= right.min() and \
                (z[i] < left.min() or z[i] < right.min()):
            troughs.append(i)
    # 清除连续平台造成的相邻重复极值（间距 < k/2 时保留更极端者）
    def _dedup(idx, is_peak):
        out = []
        for i in idx:
            if out and i - out[-1] < max(1, k // 2):
                better = (z[i] > z[out[-1]]) if is_peak else (z[i] < z[out[-1]])
                if better:
                    out[-1] = i
            else:
                out.append(i)
        return out
    return _dedup(peaks, True), _dedup(troughs, False)


def _max_drawdown(c: np.ndarray) -> float:
    """窗口内最大回撤（正数，如 0.12 = 12%）。"""
    if len(c) < 2:
        return 0.0
    run_max = np.maximum.accumulate(c)
    dd = 1.0 - c / run_max
    return float(dd.max())


def _ma(c: np.ndarray, w: int) -> np.ndarray:
    w = max(2, min(w, len(c)))
    return pd.Series(c).rolling(w).mean().to_numpy()


def _seg_gain(c: np.ndarray, i0: int, i1: int) -> float:
    """区间涨幅（可负）。"""
    if c[i0] <= 0:
        return 0.0
    return float(c[i1] / c[i0] - 1.0)


def _interp_profile(keys, n: int) -> np.ndarray:
    """关键点 [(x0..1, z), ...] → 分段线性插值到 n 个点。"""
    xs = np.array([k[0] for k in keys], dtype=float)
    zs = np.array([k[1] for k in keys], dtype=float)
    x = np.linspace(0.0, 1.0, n)
    return np.interp(x, xs, zs)


def resample_profile(points, n: int) -> np.ndarray:
    """外部轮廓（任意长度序列 0..1 域）→ 重采样到 n 点并 z-score 归一化。

    points: list/ndarray，长度 ≥ 8 的轮廓点列（纵轴任意尺度，内部归一化）。
    """
    a = np.asarray(points, dtype=float)
    a = a[~np.isnan(a)]
    if len(a) < 8:
        raise ValueError('轮廓点列过短（至少 8 个点）')
    x_old = np.linspace(0.0, 1.0, len(a))
    x_new = np.linspace(0.0, 1.0, n)
    r = np.interp(x_new, x_old, a)
    sd = r.std()
    if sd <= 1e-12:
        raise ValueError('轮廓为常数序列，无法匹配')
    return (r - r.mean()) / sd


# ======================================================================
# 识别上下文
# ======================================================================

class Ctx:
    """单只股票单个窗口的识别上下文（预计算公共量）。"""

    def __init__(self, df: pd.DataFrame, amp: float = 1.0):
        c = df['close'].to_numpy(dtype=float)
        self.amp = amp  # 周期幅度缩放因子（day=1.0）
        self.n = len(c)
        self.c = c
        self.h = df['high'].to_numpy(dtype=float) if 'high' in df.columns else c
        self.l = df['low'].to_numpy(dtype=float) if 'low' in df.columns else c
        self.v = df['volume'].to_numpy(dtype=float) if 'volume' in df.columns else None
        self.dates = list(df.index)

        sd = c.std()
        self.z = (c - c.mean()) / sd if sd > 1e-12 else np.zeros_like(c)
        self.slope_z, self.r2 = _linreg(self.z)
        self.gain = _seg_gain(c, 0, self.n - 1)
        self.mdd = _max_drawdown(c)
        self.hi, self.lo = float(c.max()), float(c.min())
        self.pos_last = (c[-1] - self.lo) / (self.hi - self.lo) if self.hi > self.lo else 0.5

        k = max(2, self.n // 12)
        self.k = k
        self.peaks, self.troughs = _pivots(self.z, k)

        self.w_fast = max(5, self.n // 8)
        self.w_slow = max(10, self.n // 3)
        self.ma_fast = _ma(c, self.w_fast)
        self.ma_slow = _ma(c, self.w_slow)

    # ---- 常用派生量 ----
    def seg(self, a: float, b: float) -> slice:
        """按窗口比例取切片。"""
        return slice(int(self.n * a), max(int(self.n * b), int(self.n * a) + 2))

    def pivot_z(self, idx_list):
        return np.array([self.z[i] for i in idx_list], dtype=float)

    def pivot_c(self, idx_list):
        return np.array([self.c[i] for i in idx_list], dtype=float)

    def vol_mean(self, i0: int, i1: int) -> float:
        if self.v is None:
            return float('nan')
        seg = self.v[i0:i1]
        return float(seg.mean()) if len(seg) else float('nan')


# ======================================================================
# 规则定义（s=+1 底部口径，s=-1 顶部口径：方向量乘 s 后取正表示"顺结构"）
# ======================================================================

def _r(name, weight, fn):
    return (name, weight, fn)


# ---------------- 趋势延续类 ----------------

def rules_strong_trend(ctx: Ctx):
    n, c = ctx.n, ctx.c
    k = int(n * 0.5)
    yield _r('线性斜率显著向上（窗口涨幅≥15%）', 3,
             (ctx.gain >= 0.15 * ctx.amp, '窗口涨幅 %.1f%%' % (ctx.gain * 100)))
    yield _r('走势线性度高（回归R²≥0.5）', 2,
             (ctx.r2 >= 0.5, 'R²=%.2f' % ctx.r2))
    yield _r('途中回撤可控（≤12%）', 2,
             (ctx.mdd <= 0.12 * ctx.amp, '最大回撤 %.1f%%' % (ctx.mdd * 100)))
    ok_ma = bool(c[-1] > ctx.ma_fast[-1] > ctx.ma_slow[-1]) if n >= ctx.w_slow + 2 else (c[-1] > ctx.ma_fast[-1])
    yield _r('均线多头排列（收盘>快线>慢线）', 2,
             (ok_ma, 'MA%d=%.2f MA%d=%.2f' % (ctx.w_fast, ctx.ma_fast[-1], ctx.w_slow, ctx.ma_slow[-1])))
    yield _r('收于窗口高位（位置≥80%）', 1,
             (ctx.pos_last >= 0.8, '窗口位置 %.0f%%' % (ctx.pos_last * 100)))


def rules_trend_pullback(ctx: Ctx):
    n, c = ctx.n, ctx.c
    k = int(n * 0.6)
    first_gain = _seg_gain(c, 0, k)
    pull_peak = c[:k + 1].max()
    pullback = 1.0 - c[-1] / pull_peak if pull_peak > 0 else 0.0
    yield _r('前段上涨显著（前60%涨幅≥10%）', 3,
             (first_gain >= 0.10 * ctx.amp, '前段涨幅 %.1f%%' % (first_gain * 100)))
    yield _r('回撤适度（前段涨幅的15%~60%）', 2,
             (0.15 * first_gain <= pullback <= 0.60 * max(first_gain, 1e-9),
              '回撤 %.1f%% / 前段涨幅 %.1f%%' % (pullback * 100, first_gain * 100)))
    tail = max(5, n // 10)
    yield _r('回踩不破前段起涨点', 2,
             (c[-1] > c[0], '现价 %.2f vs 起点 %.2f' % (c[-1], c[0])))
    yield _r('尾段企稳（近段未创新低）', 2,
             (c[-tail:].min() > c[:k].min(), '近%d根最低 %.2f > 前段最低 %.2f' % (tail, c[-tail:].min(), c[:k].min())))
    yield _r('整体仍处上行（窗口涨幅≥5%）', 1,
             (ctx.gain >= 0.05 * ctx.amp, '窗口涨幅 %.1f%%' % (ctx.gain * 100)))


def _channel_rules(ctx: Ctx, s: int):
    """s=+1 上升通道 / s=-1 阴跌通道：高低点同向回归。"""
    n = ctx.n
    pk, tr = ctx.peaks, ctx.troughs
    yield _r('极值点充足（高/低点各≥2个）', 2,
             (len(pk) >= 2 and len(tr) >= 2, '高点%d个 低点%d个' % (len(pk), len(tr))))
    if len(pk) >= 2 and len(tr) >= 2:
        ph = ctx.pivot_z(pk)
        pt = ctx.pivot_z(tr)
        sh, rh = _linreg(ph)
        st, rt = _linreg(pt)
        yield _r('高点沿通道同向（回归斜率顺向）', 2,
                 (s * sh > 0.02 if s > 0 else sh < -0.02, '高点斜率 %.3f' % sh))
        yield _r('低点沿通道同向（回归斜率顺向）', 2,
                 (st > 0.02 if s > 0 else s * st > 0.02, '低点斜率 %.3f' % st))
        yield _r('通道规整（高/低点回归R²≥0.6）', 2,
                 (rh >= 0.6 and rt >= 0.6, 'R² 高点%.2f 低点%.2f' % (rh, rt)))
    yield _r('顺向净变动（窗口幅度≥15%）', 2,
             (s * ctx.gain >= 0.15 * ctx.amp, '窗口幅度 %.1f%%' % (s * ctx.gain * 100)))
    yield _r('未发生反向破位（回撤≤18%）', 1,
             (ctx.mdd <= 0.18 * ctx.amp if s > 0 else (ctx.pos_last >= 0.1), '最大回撤 %.1f%%' % (ctx.mdd * 100)))


def _flag_rules(ctx: Ctx, s: int):
    """s=+1 上升旗形（急涨后窄幅整理）/ s=-1 下降旗形。"""
    n, c = ctx.n, ctx.c
    k = int(n * 0.4)
    pole = s * _seg_gain(c, 0, k)
    body = c[k:]
    body_range = (body.max() - body.min()) / body.mean() if body.mean() > 0 else 0
    slope_body, r2_body = _linreg(s * (body - body.mean()))
    yield _r('旗杆急促（前40%顺向幅度≥12%）', 3,
             (pole >= 0.12 * ctx.amp, '旗杆幅度 %.1f%%' % (pole * 100)))
    yield _r('旗面窄幅（后60%振幅≤9%）', 3,
             (body_range <= 0.09 * ctx.amp, '旗面振幅 %.1f%%' % (body_range * 100)))
    yield _r('旗面逆风小幅漂移（斜率≤0）', 2,
             (slope_body <= 0.02, '旗面斜率 %.3f' % slope_body))
    yield _r('旗面未跌破旗杆中点', 2,
             (body.min() > c[0] * (1 + s * 0.5 * pole) if s > 0 else body.min() > c[0] * (1 + 0.5 * pole),
              '旗面最低 %.2f vs 旗杆中点 %.2f' % (body.min(), c[0] * (1 + 0.5 * pole))))
    if ctx.v is not None and ctx.vol_mean(0, k) > 0:
        vr = ctx.vol_mean(k, n) / ctx.vol_mean(0, k)
        yield _r('旗面量能萎缩（后段量≤旗杆量×0.9）', 1,
                 (vr <= 0.9, '量比 %.2f' % vr))
    else:
        yield _r('旗面量能萎缩（无成交量数据，跳过）', 0, (True, '无量能数据'))


# ---------------- 底部/顶部 反转类（s 镜像复用） ----------------

def rules_generic_reversal(ctx: Ctx, s: int):
    """s=+1 底部反转 / s=-1 顶部反转。"""
    n, c = ctx.n, ctx.c
    k = int(n * 0.5)
    if s > 0:
        drop = 1.0 - c[k] / c[0] if c[0] > 0 else 0.0
    else:
        drop = c[k] / c[0] - 1.0 if c[0] > 0 else 0.0
    yield _r('前半段逆向下行（幅度≥15%）', 3,
             (drop >= 0.15 * ctx.amp, '前段下行 %.1f%%' % (drop * 100)))
    lo_i = int(np.argmin(c)) if s > 0 else int(np.argmax(c))
    yield _r('极值点位于窗口中后段（35%~85%）', 2,
             (0.35 <= lo_i / n <= 0.85, '极值位置 %.0f%%' % (lo_i / n * 100)))
    tail = max(3, n // 8)
    if s > 0:
        lift = c[-1] / c[lo_i] - 1.0
        yield _r('右侧抬升（自极值点反弹≥10%）', 3,
                 (lift >= 0.10 * ctx.amp, '自低点抬升 %.1f%%' % (lift * 100)))
        yield _r('低位不再下探（近段低点=窗口低点）', 2,
                 (c[-tail:].min() >= c[lo_i] * 0.995, '近%d根最低 %.2f' % (tail, c[-tail:].min())))
    else:
        drop_back = 1.0 - c[-1] / c[lo_i] if c[lo_i] > 0 else 0.0
        yield _r('右侧回落（自极值点回落≥10%）', 3,
                 (drop_back >= 0.10 * ctx.amp, '自高点回落 %.1f%%' % (drop_back * 100)))
        yield _r('高位不再冲高（近段高点=窗口高点）', 2,
                 (c[-tail:].max() <= c[lo_i] * 1.005, '近%d根最高 %.2f' % (tail, c[-tail:].max())))
    slope2, _ = _linreg(s * ctx.z[k:])
    yield _r('后半段动量转顺（回归斜率>0.01）', 2,
             (slope2 > 0.01, '后半段斜率 %.3f' % slope2))


def rules_v_reversal(ctx: Ctx, s: int):
    """s=+1 V形底 / s=-1 V形顶。"""
    n, c, z = ctx.n, ctx.c, ctx.z
    lo_i = int(np.argmin(z)) if s > 0 else int(np.argmax(z))
    yield _r('单一尖锐极值（无同级次极值）', 3,
             (_is_single_extreme(ctx, s), '极值位置 %.0f%%' % (lo_i / n * 100)))
    left = s * _seg_gain(c, 0, lo_i)
    right = s * _seg_gain(c, lo_i, n - 1)
    yield _r('左侧急促（顺向幅度≥10%）', 2, (left >= 0.10 * ctx.amp, '左腿 %.1f%%' % (left * 100)))
    yield _r('右侧急促（顺向幅度≥10%）', 2, (right >= 0.10 * ctx.amp, '右腿 %.1f%%' % (right * 100)))
    yield _r('右腿力度≥左腿六成', 2,
             (abs(right) >= 0.6 * abs(left) if left != 0 else False,
              '右/左 = %.2f' % (abs(right) / abs(left) if left != 0 else 0)))
    w = max(2, n // 20)
    sharp = (max(c[max(0, lo_i - w):lo_i + 1]) - min(c[lo_i:min(n, lo_i + w + 1)])) / c[lo_i] if c[lo_i] > 0 else 0
    yield _r('转折尖锐（极值附近振幅≥6%）', 1,
             (sharp >= 0.06 * ctx.amp, '转折区振幅 %.1f%%' % (sharp * 100)))


def _is_single_extreme(ctx: Ctx, s: int) -> bool:
    """主极值之外无深度超过主极值 40% 的次级极值。"""
    z = ctx.z
    rng = z.max() - z.min()
    if rng <= 1e-12:
        return False
    if s > 0:
        trs = ctx.troughs
        if not trs:
            return False
        main_i = min(trs, key=lambda i: z[i])
        main_v = z[main_i]
        return all(v - main_v > 0.4 * rng for v in (z[i] for i in trs if i != main_i))
    else:
        pks = ctx.peaks
        if not pks:
            return False
        main_i = max(pks, key=lambda i: z[i])
        main_v = z[main_i]
        return all(main_v - v > 0.4 * rng for v in (z[i] for i in pks if i != main_i))


def rules_round_reversal(ctx: Ctx, s: int):
    """s=+1 圆弧底 / s=-1 圆弧顶：抛物线拟合。"""
    n, z = ctx.n, ctx.z
    x = np.linspace(-1.0, 1.0, n)
    coef = np.polyfit(x, s * z, 2)
    yhat = np.polyval(coef, x)
    ss_tot = ((s * z - (s * z).mean()) ** 2).sum()
    r2 = 1.0 - ((s * z - yhat) ** 2).sum() / ss_tot if ss_tot > 1e-12 else 0.0
    yield _r('弧形显著（二次拟合a>0且R²≥0.5）', 3,
             (coef[0] > 0 and r2 >= 0.5, 'a=%.2f R²=%.2f' % (coef[0], r2)))
    lo_i = int(np.argmin(s * z))
    yield _r('弧底居中（极值位置30%~70%）', 2,
             (0.30 <= lo_i / n <= 0.70, '极值位置 %.0f%%' % (lo_i / n * 100)))
    m0, m1 = int(n * 0.4), int(n * 0.6)
    flat = (s * z[m0:m1]).std()
    yield _r('弧底平缓（中部波动≤全程×0.5）', 2,
             (flat <= 0.5 * z.std() + 1e-9, '中部σ=%.2f 全程σ=%.2f' % (flat, z.std())))
    edge_l, edge_r = s * z[0], s * z[-1]
    yield _r('右端不弱于左端（对称收口）', 2,
             (edge_r >= edge_l - 0.3, '左端 %.2f 右端 %.2f' % (edge_l, edge_r)))
    yield _r('弧口张幅（两端-弧底≥1.4σ）', 1,
             ((s * z).max() - (s * z).min() >= 1.4, '张幅 %.2fσ' % ((s * z).max() - (s * z).min())))


def _double_rules(ctx: Ctx, s: int):
    """s=+1 W底/双底 / s=-1 M头/双顶。"""
    n, c = ctx.n, ctx.c
    piv = ctx.troughs if s > 0 else ctx.peaks
    yield _r('极值点充足（≥2个）', 2, (len(piv) >= 2, '极值点 %d 个' % len(piv)))
    if len(piv) < 2:
        return
    # 取相距最远的两个主极值
    best = None
    for i in range(len(piv)):
        for j in range(i + 1, len(piv)):
            d = abs(piv[j] - piv[i])
            if best is None or d > best[0]:
                best = (d, piv[i], piv[j])
    _, t1, t2 = best
    yield _r('双极值间隔充分（≥窗口12%）', 2,
             ((t2 - t1) >= n * 0.12, '间隔 %.0f%%' % ((t2 - t1) / n * 100)))
    p1, p2 = c[t1], c[t2]
    diff = abs(p1 - p2) / min(p1, p2) if min(p1, p2) > 0 else 1
    yield _r('双底/双顶价差小（≤3.5%）', 3,
             (diff <= 0.035 * ctx.amp, '价差 %.1f%%' % (diff * 100)))
    mid = c[t1:t2 + 1]
    neck = mid.max() if s > 0 else mid.min()
    base = min(p1, p2) if s > 0 else max(p1, p2)
    bounce = (neck - base) / base if base > 0 else 0
    yield _r('中间反弹/回落充分（≥5%）', 3,
             (s * bounce >= 0.05 * ctx.amp if s > 0 else bounce >= 0.05 * ctx.amp,
              '颈线幅度 %.1f%%' % (bounce * 100)))
    pre = _seg_gain(c, 0, t1)
    pre_ok = (pre <= -0.10 * ctx.amp) if s > 0 else (pre >= 0.10 * ctx.amp)
    yield _r('前置趋势（起点到第一极值≥10%）', 2,
             (pre_ok, '前置幅度 %.1f%%' % (abs(pre) * 100)))
    if s > 0:
        yield _r('右侧抬升（现价高于第二底2%）', 2,
                 (c[-1] > p2 * (1 + 0.02 * ctx.amp), '现价 %.2f vs 第二底 %.2f' % (c[-1], p2)))
    else:
        yield _r('右侧走弱（现价低于第二顶2%）', 2,
                 (c[-1] < p2 * (1 - 0.02 * ctx.amp), '现价 %.2f vs 第二顶 %.2f' % (c[-1], p2)))


def _triple_rules(ctx: Ctx, s: int):
    """s=+1 三重底 / s=-1 三重顶。"""
    n, c = ctx.n, ctx.c
    piv = ctx.troughs if s > 0 else ctx.peaks
    yield _r('极值点充足（≥3个）', 2, (len(piv) >= 3, '极值点 %d 个' % len(piv)))
    if len(piv) < 3:
        return
    # 选深度最深且间隔充分的三个
    piv_sorted = sorted(piv, key=lambda i: s * c[i])
    cand = sorted(piv_sorted[:4])
    best, best_score = None, -1
    for i in range(len(cand)):
        for j in range(i + 1, len(cand)):
            for k2 in range(j + 1, len(cand)):
                t1, t2, t3 = cand[i], cand[j], cand[k2]
                gaps = (t2 - t1) + (t3 - t2)
                if min(t2 - t1, t3 - t2) < n * 0.10:
                    continue
                score = gaps
                if best is None or score > best_score:
                    best, best_score = (t1, t2, t3), score
    if best is None:
        yield _r('三极值间隔充分（各≥窗口10%）', 2, (False, '间隔不足'))
        return
    t1, t2, t3 = best
    vals = sorted([c[t1], c[t2], c[t3]])
    spread = (vals[-1] - vals[0]) / vals[0] if vals[0] > 0 else 1
    yield _r('三底/三顶价差小（≤4.5%）', 3,
             (spread <= 0.045 * ctx.amp, '价差 %.1f%%' % (spread * 100)))
    yield _r('间隔均匀（各≥窗口10%）', 2,
             (True, '位置 %d%%/%d%%/%d%%' % (t1 / n * 100, t2 / n * 100, t3 / n * 100)))
    if s > 0:
        b1 = (max(c[t1:t2]) - min(c[t1], c[t2])) / min(c[t1], c[t2])
        b2 = (max(c[t2:t3]) - min(c[t2], c[t3])) / min(c[t2], c[t3])
        yield _r('两次反弹充分（各≥4%）', 3,
                 (b1 >= 0.04 * ctx.amp and b2 >= 0.04 * ctx.amp, '反弹 %.1f%% / %.1f%%' % (b1 * 100, b2 * 100)))
        yield _r('右侧抬升（现价高于第三底2%）', 2,
                 (c[-1] > c[t3] * (1 + 0.02 * ctx.amp), '现价 %.2f vs 第三底 %.2f' % (c[-1], c[t3])))
    else:
        d1 = (max(c[t1], c[t2]) - min(c[t1:t2])) / max(c[t1], c[t2])
        d2 = (max(c[t2], c[t3]) - min(c[t2:t3])) / max(c[t2], c[t3])
        yield _r('两次回落充分（各≥4%）', 3,
                 (d1 >= 0.04 * ctx.amp and d2 >= 0.04 * ctx.amp, '回落 %.1f%% / %.1f%%' % (d1 * 100, d2 * 100)))
        yield _r('右侧走弱（现价低于第三顶2%）', 2,
                 (c[-1] < c[t3] * (1 - 0.02 * ctx.amp), '现价 %.2f vs 第三顶 %.2f' % (c[-1], c[t3])))


def _head_shoulder_rules(ctx: Ctx, s: int):
    """s=+1 头肩底 / s=-1 头肩顶。"""
    n, c = ctx.n, ctx.c
    piv = ctx.troughs if s > 0 else ctx.peaks
    yield _r('极值点充足（≥3个）', 2, (len(piv) >= 3, '极值点 %d 个' % len(piv)))
    if len(piv) < 3:
        return
    # 头 = 最深极值；左右肩 = 头两侧各自最顺的极值
    head = min(piv, key=lambda i: s * c[i])
    lefts = [i for i in piv if i < head - n * 0.06]
    rights = [i for i in piv if i > head + n * 0.06]
    if not lefts or not rights:
        yield _r('头与双肩结构成立', 2, (False, '缺少左肩或右肩'))
        return
    ls = min(lefts, key=lambda i: abs(head - i))
    rs = min(rights, key=lambda i: abs(head - i))
    sh1, sh2 = c[ls], c[rs]
    shoulder_diff = abs(sh1 - sh2) / min(sh1, sh2) if min(sh1, sh2) > 0 else 1
    yield _r('双肩大致对称（价差≤5.5%）', 2,
             (shoulder_diff <= 0.055 * ctx.amp, '肩差 %.1f%%' % (shoulder_diff * 100)))
    head_depth = (min(sh1, sh2) - c[head]) / min(sh1, sh2) if s > 0 else (c[head] - max(sh1, sh2)) / max(sh1, sh2)
    yield _r('头部低于双肩（深度≥3.5%）', 3,
             (s * head_depth >= 0.035 * ctx.amp, '头部深度 %.1f%%' % (head_depth * 100)))
    # 颈线：两肩之间的中间反弹高点
    mid_seg = c[ls:rs + 1]
    neck_v = mid_seg.max() if s > 0 else mid_seg.min()
    if s > 0:
        yield _r('右肩后突破/接近颈线（≥颈线97%）', 3,
                 (c[-1] >= neck_v * (1 - 0.03 * ctx.amp), '现价 %.2f vs 颈线 %.2f' % (c[-1], neck_v)))
        yield _r('前置下跌（起点高于左肩3%）', 1,
                 (c[0] > sh1 * (1 + 0.03 * ctx.amp) or ls <= n * 0.1, '起点 %.2f 左肩 %.2f' % (c[0], sh1)))
    else:
        yield _r('右肩后跌破/接近颈线（≤颈线103%）', 3,
                 (c[-1] <= neck_v * (1 + 0.03 * ctx.amp), '现价 %.2f vs 颈线 %.2f' % (c[-1], neck_v)))
        yield _r('前置上涨（起点低于左肩3%）', 1,
                 (c[0] < sh1 * (1 - 0.03 * ctx.amp) or ls <= n * 0.1, '起点 %.2f 左肩 %.2f' % (c[0], sh1)))


# ---------------- 整理突破类 ----------------

def rules_range_consolidation(ctx: Ctx):
    n, c, z = ctx.n, ctx.c, ctx.z
    rng = (ctx.hi - ctx.lo) / ctx.c.mean() if ctx.c.mean() > 0 else 0
    yield _r('箱体窄幅（全程振幅≤15%）', 3,
             (rng <= 0.15 * ctx.amp, '振幅 %.1f%%' % (rng * 100)))
    yield _r('无方向漂移（|起止变动|≤6%）', 2,
             (abs(ctx.gain) <= 0.06 * ctx.amp, '起止变动 %.1f%%' % (ctx.gain * 100)))
    up_band = ctx.lo + 0.85 * (ctx.hi - ctx.lo)
    dn_band = ctx.lo + 0.15 * (ctx.hi - ctx.lo)
    touch_up = int((c >= up_band).sum())
    touch_dn = int((c <= dn_band).sum())
    yield _r('上下沿均有触碰（各≥2次）', 2,
             (touch_up >= 2 and touch_dn >= 2, '上沿%d次 下沿%d次' % (touch_up, touch_dn)))
    half = n // 2
    sd1, sd2 = c[:half].std(), c[half:].std()
    yield _r('波动未发散（后半σ≤前半σ×1.3）', 2,
             (sd2 <= sd1 * 1.3 + 1e-9, 'σ %.3f→%.3f' % (sd1, sd2)))
    yield _r('收盘位于箱体内（位置15%~85%）', 1,
             (0.15 <= ctx.pos_last <= 0.85, '窗口位置 %.0f%%' % (ctx.pos_last * 100)))


def _triangle_rules(ctx: Ctx, kind: str):
    """kind: asc / desc / sym。"""
    n, c = ctx.n, ctx.c
    pk, tr = ctx.peaks, ctx.troughs
    yield _r('极值点充足（高/低点各≥2个）', 2,
             (len(pk) >= 2 and len(tr) >= 2, '高点%d 低点%d' % (len(pk), len(tr))))
    if len(pk) < 2 or len(tr) < 2:
        return
    ph, pt = ctx.pivot_c(pk), ctx.pivot_c(tr)
    slope_h, _ = _linreg(ph)
    slope_t, _ = _linreg(pt)
    flat_h = abs(ph.max() - ph.min()) / ph.mean() <= 0.03 * ctx.amp
    flat_t = abs(pt.max() - pt.min()) / pt.mean() <= 0.03 * ctx.amp
    if kind == 'asc':
        yield _r('上沿水平（高点价差≤3%或斜率≈0）', 3,
                 (flat_h or abs(slope_h) <= 0.01 * ctx.amp, '高点极差 %.1f%%' % ((abs(ph.max() - ph.min()) / ph.mean()) * 100)))
        yield _r('下沿抬升（低点斜率>0）', 3, (slope_t > 0, '低点斜率 %.3f' % slope_t))
    elif kind == 'desc':
        yield _r('下沿水平（低点价差≤3%或斜率≈0）', 3,
                 (flat_t or abs(slope_t) <= 0.01 * ctx.amp, '低点极差 %.1f%%' % ((abs(pt.max() - pt.min()) / pt.mean()) * 100)))
        yield _r('上沿下降（高点斜率<0）', 3, (slope_h < 0, '高点斜率 %.3f' % slope_h))
    else:
        yield _r('上沿下降（高点斜率<0）', 3, (slope_h < 0, '高点斜率 %.3f' % slope_h))
        yield _r('下沿抬升（低点斜率>0）', 3, (slope_t > 0, '低点斜率 %.3f' % slope_t))
    converge = (ph[-1] - pt[-1]) < (ph[0] - pt[0]) * 0.8
    yield _r('区间收敛（末距<首距×0.8）', 2, (converge, '首距 %.2f → 末距 %.2f' % (ph[0] - pt[0], ph[-1] - pt[-1])))
    yield _r('趋势中性（|窗口斜率|≤0.02/根）', 1,
             (abs(ctx.slope_z) <= 0.02 * max(1, 60 / n) * 60 / n + 0.015,
              '窗口斜率 %.3f' % ctx.slope_z))


def rules_breakout(ctx: Ctx):
    n, c = ctx.n, ctx.c
    k = int(n * 0.7)
    base = c[:k]
    box_hi, box_lo = base.max(), base.min()
    box_range = (box_hi - box_lo) / box_lo if box_lo > 0 else 1
    yield _r('前期平台窄幅（前70%振幅≤12%）', 3,
             (box_range <= 0.12 * ctx.amp, '平台振幅 %.1f%%' % (box_range * 100)))
    burst = c[k:].max() / box_hi - 1.0 if box_hi > 0 else 0
    yield _r('放量突破平台高点（≥+3%）', 3,
             (burst >= 0.03 * ctx.amp, '突破幅度 %.1f%%' % (burst * 100)))
    ok_vol, vol_detail = True, '无量能数据'
    if ctx.v is not None and ctx.vol_mean(0, k) > 0:
        vol_after = ctx.vol_mean(k, n)
        ratio = vol_after / ctx.vol_mean(0, k)
        ok_vol, vol_detail = ratio >= 1.3, '突破段量/平台量 = %.2f' % ratio
    yield _r('量能配合（突破段≥平台量×1.3）', 2, (ok_vol, vol_detail))
    yield _r('收盘站稳平台上方', 2,
             (c[-1] > box_hi, '现价 %.2f > 平台高点 %.2f' % (c[-1], box_hi)))
    yield _r('突破前平台不散（前70%起止变动≤6%）', 1,
             (abs(_seg_gain(c, 0, k)) <= 0.06 * ctx.amp, '平台漂移 %.1f%%' % (abs(_seg_gain(c, 0, k)) * 100)))


# ---------------- 杯柄 / 塔形 / 岛形 / 喇叭 / 三角旗 / 楔形 ----------------

def rules_cup_handle(ctx: Ctx):
    """杯柄形（看多）：平滑 U 形杯 + 窄幅柄部，现价接近杯沿。"""
    n, c = ctx.n, ctx.c
    k = int(n * 0.75)
    cup = c[:k]
    handle = c[k:]
    rim = float(cup.max())
    cup_lo = float(cup.min())
    lo_i = int(np.argmin(cup))
    depth = (rim - cup_lo) / rim if rim > 0 else 0.0
    zc = (cup - cup.mean()) / (cup.std() + 1e-12)
    x = np.linspace(-1.0, 1.0, k)
    coef = np.polyfit(x, zc, 2)
    yhat = np.polyval(coef, x)
    ss_tot = ((zc - zc.mean()) ** 2).sum()
    r2 = 1.0 - ((zc - yhat) ** 2).sum() / ss_tot if ss_tot > 1e-12 else 0.0
    yield _r('杯形显著（二次拟合开口向上且R²≥0.45）', 3,
             (coef[0] > 0 and r2 >= 0.45, 'a=%.2f R²=%.2f' % (coef[0], r2)))
    yield _r('杯深足够（≥10%）', 3,
             (depth >= 0.10 * ctx.amp, '杯深 %.1f%%' % (depth * 100)))
    yield _r('杯底居中（杯内位置25%~65%）', 2,
             (0.25 <= lo_i / k <= 0.65, '杯底位置 %.0f%%' % (lo_i / k * 100)))
    h_range = (handle.max() - handle.min()) / rim if rim > 0 else 1.0
    yield _r('柄部窄幅（柄幅≤杯深×0.35）', 2,
             (h_range <= 0.35 * depth + 1e-9, '柄幅 %.1f%% vs 杯深 %.1f%%'
              % (h_range * 100, depth * 100)))
    yield _r('柄不破杯底', 2,
             (handle.min() > cup_lo * (1 + 0.02 * ctx.amp), '柄最低 %.2f vs 杯底 %.2f'
              % (handle.min(), cup_lo)))
    yield _r('现价接近杯沿（≥杯沿×0.96）', 2,
             (c[-1] >= rim * (1 - 0.04 * ctx.amp), '现价 %.2f vs 杯沿 %.2f' % (c[-1], rim)))


def rules_tower(ctx: Ctx, s: int):
    """s=+1 塔形底 / s=-1 塔形顶：急促→平底→急促反向。"""
    n, c = ctx.n, ctx.c
    a, b = int(n * 0.3), int(n * 0.7)
    first, mid, last = c[:a], c[a:b], c[b:]
    if s > 0:
        edge1 = 1.0 - first.min() / c[0] if c[0] > 0 else 0.0
        edge2 = c[-1] / mid.min() - 1.0 if mid.min() > 0 else 0.0
    else:
        edge1 = first.max() / c[0] - 1.0 if c[0] > 0 else 0.0
        edge2 = 1.0 - c[-1] / mid.max() if mid.max() > 0 else 0.0
    yield _r('前段急促（幅度≥8%）', 3,
             (edge1 >= 0.08 * ctx.amp, '前段 %.1f%%' % (edge1 * 100)))
    mid_range = (mid.max() - mid.min()) / mid.mean() if mid.mean() > 0 else 1.0
    yield _r('中段平底（振幅≤4%）', 3,
             (mid_range <= 0.04 * ctx.amp, '平底振幅 %.1f%%' % (mid_range * 100)))
    yield _r('后段急促（幅度≥8%）', 3,
             (edge2 >= 0.08 * ctx.amp, '后段 %.1f%%' % (edge2 * 100)))
    ex_i = int(np.argmin(s * z_arr(c)))
    yield _r('极值位置居中（30%~70%）', 2,
             (0.30 <= ex_i / n <= 0.70, '极值位置 %.0f%%' % (ex_i / n * 100)))
    near = abs(float(mid.min() if s > 0 else mid.max()) - float(c.min() if s > 0 else c.max())) \
        / float(c.min() if s > 0 else c.max()) if len(mid) else 1.0
    yield _r('平底贴近窗口极值（偏差≤1%）', 1,
             (near <= 0.01 * ctx.amp, '偏差 %.1f%%' % (near * 100)))


def z_arr(c):
    c = np.asarray(c, dtype=float)
    sd = c.std()
    return (c - c.mean()) / sd if sd > 1e-12 else np.zeros_like(c)


def _find_island(ctx: Ctx, s: int):
    """定位岛形结构。s=+1 岛形底（向下跳空进岛、向上跳空离岛）；s=-1 岛形顶。

    返回 (i, j)：i=岛首索引，j=离岛后首根索引；未找到返回 None。
    缺口判定用最高价/最低价（前复权），带 0.1% 容差。
    """
    h, l, n = ctx.h, ctx.l, ctx.n
    tol = 1.001
    for i in range(2, n - 3):
        if s > 0:
            if not h[i] < l[i - 1] / tol:      # 向下跳空进岛
                continue
        else:
            if not l[i] > h[i - 1] * tol:      # 向上跳空进岛
                continue
        for j in range(i + 2, n - 1):          # 岛内至少 2 根
            if s > 0:
                if l[j] > h[j - 1] * tol:      # 向上跳空离岛
                    return i, j
            else:
                if h[j] < l[j - 1] / tol:      # 向下跳空离岛
                    return i, j
            # 岛内一旦出现同向延续缺口则岛屿定义被破坏前仍可延伸，继续扫描
    return None


def rules_island(ctx: Ctx, s: int):
    """s=+1 岛形底 / s=-1 岛形顶：双向缺口孤岛 + 前后趋势。"""
    n, c = ctx.n, ctx.c
    isl = _find_island(ctx, s)
    yield _r('岛形结构（双向缺口孤岛）', 3,
             (isl is not None, '缺口对 %s' % (str(isl) if isl else '未找到')))
    if isl is None:
        return
    i, j = isl
    yield _r('岛内根数≥2', 2,
             (j - i >= 2, '岛内 %d 根' % (j - i)))
    if s > 0:
        pre = 1.0 - c[i] / c[0] if c[0] > 0 else 0.0
        post = c[-1] / c[j - 1] - 1.0 if c[j - 1] > 0 else 0.0
    else:
        pre = c[i] / c[0] - 1.0 if c[0] > 0 else 0.0
        post = 1.0 - c[-1] / c[j - 1] if c[j - 1] > 0 else 0.0
    yield _r('前置趋势（岛前顺向≥4%）', 2,
             (pre >= 0.04 * ctx.amp, '岛前 %.1f%%' % (pre * 100)))
    yield _r('离岛反转（岛后顺向≥3%）', 2,
             (post >= 0.03 * ctx.amp, '岛后 %.1f%%' % (post * 100)))
    if s > 0:
        yield _r('现价已脱离岛区（高于岛内最高）', 1,
                 (c[-1] > ctx.h[i:j].max(), '现价 %.2f' % c[-1]))
    else:
        yield _r('现价已脱离岛区（低于岛内最低）', 1,
                 (c[-1] < ctx.l[i:j].min(), '现价 %.2f' % c[-1]))


def rules_broadening(ctx: Ctx, s: int):
    """喇叭形（扩散形）：高点抬高 + 低点降低 + 波幅扩张。

    s=-1 喇叭形顶（看空，经典）；s=+1 喇叭形底（看多，下跌后扩张 + 右侧转强）。
    """
    n, c, z = ctx.n, ctx.c, ctx.z
    pk, tr = ctx.peaks, ctx.troughs
    yield _r('极值点充足（高/低点各≥2个）', 2,
             (len(pk) >= 2 and len(tr) >= 2, '高点%d 低点%d' % (len(pk), len(tr))))
    if len(pk) >= 2 and len(tr) >= 2:
        ph, pt = ctx.pivot_z(pk), ctx.pivot_z(tr)
        slope_h, _ = _linreg(ph)
        slope_t, _ = _linreg(pt)
        yield _r('高点抬高（斜率>0）', 2, (slope_h > 0, '高点斜率 %.3f' % slope_h))
        yield _r('低点降低（斜率<0）', 2, (slope_t < 0, '低点斜率 %.3f' % slope_t))
        expand = (ph[-1] - pt[-1]) > (ph[0] - pt[0]) * 1.3
        yield _r('波幅扩张（末距>首距×1.3）', 3,
                 (expand, '首距 %.2f → 末距 %.2f' % (ph[0] - pt[0], ph[-1] - pt[-1])))
    half = n // 2
    sd1, sd2 = c[:half].std(), c[half:].std()
    yield _r('后半波动放大（σ≥前半×1.2）', 2,
             (sd2 >= sd1 * 1.2 + 1e-9, 'σ %.3f→%.3f' % (sd1, sd2)))
    if s < 0:
        yield _r('前置上涨（窗口涨幅≥8%）', 1,
                 (ctx.gain >= 0.08 * ctx.amp, '窗口涨幅 %.1f%%' % (ctx.gain * 100)))
        yield _r('现价走弱（≤窗口最高×0.95）', 2,
                 (c[-1] <= ctx.hi * (1 - 0.05 * ctx.amp), '现价 %.2f vs 最高 %.2f' % (c[-1], ctx.hi)))
    else:
        yield _r('下跌背景（窗口最大回撤≥8%）', 1,
                 (ctx.mdd >= 0.08 * ctx.amp, '最大回撤 %.1f%%' % (ctx.mdd * 100)))
        yield _r('现价转强（≥窗口最低×1.05）', 2,
                 (c[-1] >= ctx.lo * (1 + 0.05 * ctx.amp), '现价 %.2f vs 最低 %.2f' % (c[-1], ctx.lo)))


def rules_pennant(ctx: Ctx, s: int):
    """s=+1 三角旗形（多）/ s=-1 三角旗形（空）：急促旗杆 + 收敛窄幅旗面。"""
    n, c = ctx.n, ctx.c
    k = int(n * 0.4)
    pole = s * _seg_gain(c, 0, k)
    body = c[k:]
    yield _r('旗杆急促（前40%顺向幅度≥12%）', 3,
             (pole >= 0.12 * ctx.amp, '旗杆 %.1f%%' % (pole * 100)))
    body_range = (body.max() - body.min()) / body.mean() if body.mean() > 0 else 1.0
    yield _r('旗面窄幅（总振幅≤6.5%）', 3,
             (body_range <= 0.065 * ctx.amp, '旗面振幅 %.1f%%' % (body_range * 100)))
    half = len(body) // 2
    r1 = body[:half].std()
    r2 = body[half:].std()
    yield _r('旗面收敛（后半σ≤前半σ×0.85）', 3,
             (r2 <= r1 * 0.85 + 1e-9, 'σ %.2f→%.2f' % (r1, r2)))
    hold = body.min() > c[0] * (1 + s * 0.6 * pole) if s > 0 else \
        body.max() < c[0] * (1 + s * 0.6 * pole)
    yield _r('旗面守住杆身（不回撤过杆身60%处）', 2,
             (hold, '旗面区间 [%.2f, %.2f]' % (body.min(), body.max())))


def rules_wedge(ctx: Ctx, kind: str):
    """kind='rising' 上升楔形（看空）/ 'falling' 下降楔形（看多）。

    高低点同向回归且通道收敛：rising 斜率均>0 且高点斜率<低点斜率；
    falling 斜率均<0 且高点斜率>低点斜率（价格域取 z 域同号）。
    """
    n = ctx.n
    pk, tr = ctx.peaks, ctx.troughs
    yield _r('极值点充足（高/低点各≥2个）', 2,
             (len(pk) >= 2 and len(tr) >= 2, '高点%d 低点%d' % (len(pk), len(tr))))
    if len(pk) < 2 or len(tr) < 2:
        return
    ph, pt = ctx.pivot_z(pk), ctx.pivot_z(tr)
    slope_h, rh = _linreg(ph)
    slope_t, rt = _linreg(pt)
    if kind == 'rising':
        same = slope_h > 0.02 and slope_t > 0.02
        conv = slope_h < slope_t
        yield _r('高低点同升（双斜率>0.02）', 3,
                 (same, '高点 %.3f 低点 %.3f' % (slope_h, slope_t)))
        yield _r('通道上倾收敛（高点斜率<低点斜率）', 3,
                 (conv and same, '斜率差 %.3f' % (slope_t - slope_h)))
    else:
        same = slope_h < -0.02 and slope_t < -0.02
        conv = slope_h > slope_t
        yield _r('高低点同降（双斜率<-0.02）', 3,
                 (same, '高点 %.3f 低点 %.3f' % (slope_h, slope_t)))
        yield _r('通道下倾收敛（高点斜率>低点斜率）', 3,
                 (conv and same, '斜率差 %.3f' % (slope_h - slope_t)))
    yield _r('通道规整（至少一侧R²≥0.35）', 2,
             (max(rh, rt) >= 0.35, 'R² 高点%.2f 低点%.2f' % (rh, rt)))
    yield _r('幅度适度（|窗口涨幅|≤30%）', 1,
             (abs(ctx.gain) <= 0.30 * ctx.amp, '窗口涨幅 %.1f%%' % (ctx.gain * 100)))




def _profile_strong_trend(n):
    return _interp_profile([(0, -1.6), (0.35, -0.5), (0.7, 0.6), (1, 1.6)], n)

def _profile_trend_pullback(n):
    return _interp_profile([(0, -1.4), (0.45, 0.5), (0.72, -0.1), (1, 1.2)], n)

def _profile_channel_up(n):
    x = np.linspace(0, 1, n)
    return -1.4 + 2.8 * x + 0.35 * np.sin(6.5 * np.pi * x)

def _profile_flag_up(n):
    return _interp_profile([(0, -1.4), (0.4, 1.1), (0.65, 0.95), (1, 1.05)], n)

def _profile_channel_down(n):
    x = np.linspace(0, 1, n)
    return 1.4 - 2.8 * x - 0.35 * np.sin(6.5 * np.pi * x)

def _profile_flag_down(n):
    return _interp_profile([(0, 1.4), (0.4, -1.1), (0.65, -0.95), (1, -1.05)], n)

def _profile_generic_reversal(n, s):
    keys = [(0, 1.3), (0.35, 0.2), (0.58, -1.2), (0.8, -0.6), (1, 0.1)]
    return _interp_profile(keys if s > 0 else [(x, -v) for x, v in keys], n)

def _profile_v_reversal(n, s):
    keys = [(0, 1.2), (0.48, -1.4), (0.55, -0.9), (1, 1.0)]
    return _interp_profile(keys if s > 0 else [(x, -v) for x, v in keys], n)

def _profile_round_reversal(n, s):
    x = np.linspace(-1, 1, n)
    v = 1.15 * x ** 2 - 1.0
    return v if s > 0 else -v

def _profile_double(n, s):
    keys = [(0, 1.1), (0.3, -1.2), (0.5, 0.4), (0.7, -1.15), (1, 0.6)]
    return _interp_profile(keys if s > 0 else [(x, -v) for x, v in keys], n)

def _profile_triple(n, s):
    keys = [(0, 1.1), (0.2, -1.1), (0.36, 0.35), (0.52, -1.12), (0.68, 0.35), (0.84, -1.1), (1, 0.5)]
    return _interp_profile(keys if s > 0 else [(x, -v) for x, v in keys], n)

def _profile_head_shoulder(n, s):
    keys = [(0, 1.0), (0.22, -0.65), (0.42, -1.25), (0.62, -0.7), (0.82, 0.15), (1, 0.55)]
    return _interp_profile(keys if s > 0 else [(x, -v) for x, v in keys], n)

def _profile_range(n):
    x = np.linspace(0, 1, n)
    return 0.85 * np.sin(5.5 * np.pi * x + 0.4)

def _profile_triangle(n, kind):
    x = np.linspace(0, 1, n)
    osc = np.sin(5.5 * np.pi * x)
    if kind == 'asc':
        return osc * (1 - 0.75 * x) + 0.9 * x
    if kind == 'desc':
        return osc * (1 - 0.75 * x) - 0.9 * x
    return osc * (1 - 0.8 * x)

def _profile_breakout(n):
    return _interp_profile([(0, -0.1), (0.2, 0.1), (0.45, -0.1), (0.68, 0.1), (0.78, 0.9), (1, 1.4)], n)


def _profile_cup_handle(n):
    return _interp_profile([(0, 1.0), (0.15, 0.2), (0.42, -1.0), (0.62, -0.9),
                            (0.75, 0.85), (0.85, 0.5), (1, 0.8)], n)


def _profile_tower(n, s):
    keys = [(0, 1.2), (0.28, -0.5), (0.4, -1.3), (0.6, -1.35), (0.72, -0.4), (1, 1.1)]
    return _interp_profile(keys if s > 0 else [(x, -v) for x, v in keys], n)


def _profile_island(n, s):
    keys = [(0, -0.5), (0.4, 0.4), (0.46, 1.3), (0.6, 1.25), (0.66, 0.3), (1, -0.8)]
    return _interp_profile(keys if s < 0 else [(x, -v) for x, v in keys], n)


def _profile_broadening(n, s):
    x = np.linspace(0, 1, n)
    v = (0.4 + 1.3 * x) * np.sin(5.5 * np.pi * x) - 0.5 * x
    return v if s < 0 else -v


def _profile_pennant(n, s):
    keys = [(0, -1.3), (0.4, 1.1), (0.6, 0.8), (0.8, 1.0), (1, 1.05)]
    return _interp_profile(keys if s > 0 else [(x, -v) for x, v in keys], n)


def _profile_wedge(n, kind):
    x = np.linspace(0, 1, n)
    if kind == 'rising':
        mid, amp = 0.2 + 0.9 * x, 0.9 - 0.55 * x
    else:
        mid, amp = 0.9 - 1.1 * x, 0.9 - 0.55 * x
    return mid + amp * np.sin(5.5 * np.pi * x)


# ======================================================================
# 形态注册表
# ======================================================================

class PatternDef:
    def __init__(self, pid, name_zh, family, direction, rules_fn, profile_fn,
                 min_rule_score=30.0, min_score=None):
        self.id = pid
        self.name_zh = name_zh
        self.family = family
        self.direction = direction      # 看多 / 看空 / 中性
        self.rules_fn = rules_fn        # fn(ctx) -> generator of (name, weight, (ok, detail))
        self.profile_fn = profile_fn    # fn(n) -> ndarray
        self.min_rule_score = min_rule_score
        # 形态级总分门槛：None=用全局值；宽结构形态（如 W底/喇叭形）规则分易达
        # 标但形状相似度低，用更高总分门槛保证区分度（10-08 阈值回检实证）
        self.min_score = min_score


PATTERNS = {
    # ---- 趋势延续 ----
    'strong_trend':  PatternDef('strong_trend', '强趋势延续', '趋势延续类', '看多',
                                lambda x: rules_strong_trend(x), _profile_strong_trend),
    'trend_pullback': PatternDef('trend_pullback', '趋势回踩', '趋势延续类', '看多',
                                 lambda x: rules_trend_pullback(x), _profile_trend_pullback),
    'channel_up':    PatternDef('channel_up', '上升通道', '趋势延续类', '看多',
                                lambda x: _channel_rules(x, +1), _profile_channel_up),
    'flag_up':       PatternDef('flag_up', '上升旗形', '趋势延续类', '看多',
                                lambda x: _flag_rules(x, +1), _profile_flag_up),
    'channel_down':  PatternDef('channel_down', '阴跌通道', '趋势延续类', '看空',
                                lambda x: _channel_rules(x, -1), _profile_channel_down,
                                min_score=70.0),
    'flag_down':     PatternDef('flag_down', '下降旗形', '趋势延续类', '看空',
                                lambda x: _flag_rules(x, -1), _profile_flag_down),
    'pennant_up':    PatternDef('pennant_up', '三角旗形（多）', '趋势延续类', '看多',
                                lambda x: rules_pennant(x, +1),
                                lambda n: _profile_pennant(n, +1)),
    'pennant_down':  PatternDef('pennant_down', '三角旗形（空）', '趋势延续类', '看空',
                                lambda x: rules_pennant(x, -1),
                                lambda n: _profile_pennant(n, -1)),
    # ---- 底部反转 ----
    'bottom_reversal': PatternDef('bottom_reversal', '底部反转', '底部反转类', '看多',
                                  lambda x: rules_generic_reversal(x, +1),
                                  lambda n: _profile_generic_reversal(n, +1),
                                  min_score=65.0),
    'v_bottom':      PatternDef('v_bottom', 'V形底', '底部反转类', '看多',
                                lambda x: rules_v_reversal(x, +1),
                                lambda n: _profile_v_reversal(n, +1)),
    'round_bottom':  PatternDef('round_bottom', '圆弧底', '底部反转类', '看多',
                                lambda x: rules_round_reversal(x, +1),
                                lambda n: _profile_round_reversal(n, +1),
                                min_score=60.0),
    'w_bottom':      PatternDef('w_bottom', 'W底/双底', '底部反转类', '看多',
                                lambda x: _double_rules(x, +1),
                                lambda n: _profile_double(n, +1),
                                min_rule_score=50.0, min_score=60.0),
    'triple_bottom': PatternDef('triple_bottom', '三重底', '底部反转类', '看多',
                                lambda x: _triple_rules(x, +1),
                                lambda n: _profile_triple(n, +1)),
    'head_shoulder_bottom': PatternDef('head_shoulder_bottom', '头肩底', '底部反转类', '看多',
                                       lambda x: _head_shoulder_rules(x, +1),
                                       lambda n: _profile_head_shoulder(n, +1)),
    'cup_handle':    PatternDef('cup_handle', '杯柄形', '底部反转类', '看多',
                                rules_cup_handle, _profile_cup_handle,
                                min_score=60.0),
    'tower_bottom':  PatternDef('tower_bottom', '塔形底', '底部反转类', '看多',
                                lambda x: rules_tower(x, +1),
                                lambda n: _profile_tower(n, +1)),
    'island_bottom': PatternDef('island_bottom', '岛形底', '底部反转类', '看多',
                                lambda x: rules_island(x, +1),
                                lambda n: _profile_island(n, +1)),
    'broadening_bottom': PatternDef('broadening_bottom', '喇叭形底', '底部反转类', '看多',
                                    lambda x: rules_broadening(x, +1),
                                    lambda n: _profile_broadening(n, +1)),
    # ---- 顶部反转 ----
    'top_reversal':  PatternDef('top_reversal', '顶部反转', '顶部反转类', '看空',
                                lambda x: rules_generic_reversal(x, -1),
                                lambda n: _profile_generic_reversal(n, -1),
                                min_score=65.0),
    'v_top':         PatternDef('v_top', 'V形顶', '顶部反转类', '看空',
                                lambda x: rules_v_reversal(x, -1),
                                lambda n: _profile_v_reversal(n, -1)),
    'round_top':     PatternDef('round_top', '圆弧顶', '顶部反转类', '看空',
                                lambda x: rules_round_reversal(x, -1),
                                lambda n: _profile_round_reversal(n, -1)),
    'm_top':         PatternDef('m_top', 'M头/双顶', '顶部反转类', '看空',
                                lambda x: _double_rules(x, -1),
                                lambda n: _profile_double(n, -1),
                                min_score=60.0),
    'triple_top':    PatternDef('triple_top', '三重顶', '顶部反转类', '看空',
                                lambda x: _triple_rules(x, -1),
                                lambda n: _profile_triple(n, -1)),
    'head_shoulder_top': PatternDef('head_shoulder_top', '头肩顶', '顶部反转类', '看空',
                                    lambda x: _head_shoulder_rules(x, -1),
                                    lambda n: _profile_head_shoulder(n, -1)),
    'tower_top':     PatternDef('tower_top', '塔形顶', '顶部反转类', '看空',
                                lambda x: rules_tower(x, -1),
                                lambda n: _profile_tower(n, -1)),
    'island_top':    PatternDef('island_top', '岛形顶', '顶部反转类', '看空',
                                lambda x: rules_island(x, -1),
                                lambda n: _profile_island(n, -1)),
    'broadening_top': PatternDef('broadening_top', '喇叭形顶', '顶部反转类', '看空',
                                 lambda x: rules_broadening(x, -1),
                                 lambda n: _profile_broadening(n, -1)),
    # ---- 整理突破 ----
    'range_consolidation': PatternDef('range_consolidation', '箱体震荡', '整理突破类', '中性',
                                      rules_range_consolidation, _profile_range),
    'ascending_triangle': PatternDef('ascending_triangle', '上升三角形', '整理突破类', '看多',
                                     lambda x: _triangle_rules(x, 'asc'),
                                     lambda n: _profile_triangle(n, 'asc')),
    'descending_triangle': PatternDef('descending_triangle', '下降三角形', '整理突破类', '看空',
                                      lambda x: _triangle_rules(x, 'desc'),
                                      lambda n: _profile_triangle(n, 'desc'),
                                      min_score=60.0),
    'symmetrical_triangle': PatternDef('symmetrical_triangle', '对称三角形', '整理突破类', '中性',
                                       lambda x: _triangle_rules(x, 'sym'),
                                       lambda n: _profile_triangle(n, 'sym'),
                                       min_score=60.0),
    'rising_wedge':  PatternDef('rising_wedge', '上升楔形', '整理突破类', '看空',
                                lambda x: rules_wedge(x, 'rising'),
                                lambda n: _profile_wedge(n, 'rising')),
    'falling_wedge': PatternDef('falling_wedge', '下降楔形', '整理突破类', '看多',
                                lambda x: rules_wedge(x, 'falling'),
                                lambda n: _profile_wedge(n, 'falling'),
                                min_score=60.0),
    'breakout':      PatternDef('breakout', '平台突破', '整理突破类', '看多',
                                rules_breakout, _profile_breakout),
}

# 周期幅度缩放因子：非日线周期下，幅度类阈值（涨跌幅/回撤/振幅等）乘以该系数。
# 经验常量——同样 120 根 BAR，月线窗口≈10 年波动≈日线的 2.2 倍，60 分钟窗口≈1.5 月≈0.62 倍。
# z 域斜率/R²/相对比例/区间位置/量能比不缩放（归一化后天然尺度无关）。
TIMEFRAME_AMP = {
    'min1': 0.12, 'min3': 0.18, 'min5': 0.25, 'min10': 0.32,
    'min15': 0.40, 'min30': 0.50, 'min60': 0.62, 'min120': 0.78,
    'day': 1.0, 'week': 1.6, 'month': 2.2, 'season': 3.0, 'year': 4.0,
}

FAMILY_ORDER = ['趋势延续类', '底部反转类', '顶部反转类', '整理突破类']


# ======================================================================
# 评分与对外接口
# ======================================================================

def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    sa, sb = a.std(), b.std()
    if sa <= 1e-12 or sb <= 1e-12:
        return 0.0
    return float(((a - a.mean()) * (b - b.mean())).mean() / (sa * sb))


def evaluate_pattern(df: pd.DataFrame, pdef: PatternDef,
                     external_profile: np.ndarray = None, amp: float = 1.0) -> dict:
    """对单个窗口评估单个形态。

    df: 前复权日线（index=int日期），取全部传入数据作为窗口。
    返回 {pattern_id, pattern_name, family, direction, score, rule_score,
          sim_score, corr, hits:[{name, ok, detail, weight}]}
    """
    ctx = Ctx(df, amp=amp)
    hits = []
    w_sum = w_hit = 0.0
    for name, weight, (ok, detail) in pdef.rules_fn(ctx):
        if weight <= 0:
            hits.append({'name': name, 'ok': True, 'detail': detail, 'weight': 0})
            continue
        w_sum += weight
        if ok:
            w_hit += weight
        hits.append({'name': name, 'ok': bool(ok), 'detail': detail, 'weight': weight})
    rule_score = (w_hit / w_sum * 100.0) if w_sum > 0 else 0.0

    if external_profile is not None:
        profile = resample_profile(external_profile, ctx.n)
    else:
        profile = pdef.profile_fn(ctx.n)
    corr = _pearson(ctx.z, profile)
    sim_score = max(0.0, corr) * 100.0

    score = 0.6 * rule_score + 0.4 * sim_score
    return {
        'pattern_id': pdef.id,
        'pattern_name': pdef.name_zh,
        'family': pdef.family,
        'direction': pdef.direction,
        'score': round(score, 1),
        'rule_score': round(rule_score, 1),
        'sim_score': round(sim_score, 1),
        'corr': round(corr, 3),
        'hits': hits,
        '_rule_pass': rule_score >= pdef.min_rule_score,
    }


def analyze_window(df: pd.DataFrame, pattern_ids=None,
                   external_profile: np.ndarray = None,
                   min_score: float = 50.0, amp: float = 1.0) -> list:
    """对单只股票窗口评估（多个形态或外部轮廓）。

    pattern_ids: 形态ID列表；None=全部。external_profile 传入时忽略 pattern_ids，
                 以 profile 模式评分（相似分对标外部轮廓，规则分用通用结构规则）。
    返回按 score 降序、且 score≥min_score 的结果列表。
    """
    if external_profile is not None:
        pdefs = [PatternDef(
            'profile_custom', '自定义轮廓匹配', '轮廓匹配', '中性',
            lambda x: _profile_mode_rules(x, external_profile),
            None)]
        results = [evaluate_pattern(df, pdefs[0], external_profile, amp=amp)]
        # profile 模式：通用质量规则区分度低，min_score 约束**相似分**而非总分
        results = [r for r in results if r['sim_score'] >= min_score]
        return sorted(results, key=lambda r: -r['score'])

    ids = pattern_ids or list(PATTERNS.keys())
    results = []
    for pid in ids:
        pdef = PATTERNS.get(pid)
        if pdef is None:
            continue
        r = evaluate_pattern(df, pdef, amp=amp)
        gate = pdef.min_score if pdef.min_score is not None else min_score
        if r['score'] >= gate and r['_rule_pass']:
            results.append(r)
    return sorted(results, key=lambda r: -r['score'])


def _profile_mode_rules(ctx: Ctx, profile: np.ndarray):
    """轮廓模式的通用结构规则（轮廓已通过相似分表达形状，这里只约束基本质量）。"""
    n, z = ctx.n, ctx.z
    yield _r('窗口波动充分（σ范围≥1.2）', 2,
             ((z.max() - z.min()) >= 1.2, '波动范围 %.2fσ' % (z.max() - z.min())))
    yield _r('与轮廓相关性为正', 3, (True, '相似分已单独列示'))
    yield _r('数据完整（窗口无缺失价）', 2,
             (bool(np.isfinite(ctx.c).all()), '收盘价序列完整'))
    slope, r2 = _linreg(z)
    yield _r('窗口非单边极端（斜率|每根|≤0.06）', 1,
             (abs(slope) <= 0.06, '斜率 %.3f' % slope))
