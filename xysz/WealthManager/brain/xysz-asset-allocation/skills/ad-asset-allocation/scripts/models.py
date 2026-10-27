# -*- coding: utf-8 -*-
"""大类资产配置模型 — 四种配置方法。

资产顺序与中文名（模型输入的 μ/Σ、权重向量均按此顺序）：
    ['黄金', '国债', '宽基', '现金']

模型：
    fixed_weight   固定权重（默认等权，可指定）
    mean_variance  均值方差：max μᵀw − (λ/2)·wᵀΣw（SLSQP，Σw=1、多头、上下界）
    risk_parity    风险平价：各资产风险贡献相等
    black_litterman BL：标准 He-Litterman 后验 + MVO
        （观点输入 P/Q/conf，后验期望与后验协方差按 He-Litterman (1999) 标准公式）
年化口径：244 个交易日；μ = 窗口日均收益×244；Σ = 窗口日协方差×244。
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize

ASSET_NAMES = ['黄金', '国债', '宽基', '现金']
TRADING_DAYS = 244
CASH_NAME = '现金'


# ----------------------------------------------------------------------
# 工具
# ----------------------------------------------------------------------
def annualized_stats(window: pd.DataFrame, shrink: float = 0.0,
                     excess_bench: pd.Series = None):
    """窗口日收益 DataFrame → (μ ndarray, Σ ndarray)，年化口径。

    shrink: 协方差对角收缩系数 [0,1)，Σ' = (1-δ)Σ + δ·diag(Σ)，
    缓解样本协方差病态与 MV 输入敏感（0=不收缩）。

    excess_bench: 基准日收益 Series（与 window 索引对齐）。传入时启用
    **超额收益协方差口径**：μ 仍取原始收益均值，Σ 的风险资产部分改用
    相对基准的超额收益协方差（剔除系统性风险，避免"高市场风险资产反获高权重"）。
    现金是低风险代理资产，其方差与相关性**保留原始收益口径**（若用超额收益，
    现金波动将等于基准波动，低风险属性被破坏），故该 Σ 为"风险资产超额 + 现金原始"
    的混合口径，仅用于稳健性对照。
    """
    mu = window.mean().values * TRADING_DAYS
    window = window.fillna(0.0)   # 缺失日按 0 收益处理（与 build_asset_returns 的停牌口径一致）
    if excess_bench is None:
        cov = window.cov().values * TRADING_DAYS
    else:
        ex = window.subtract(excess_bench, axis=0)
        cov_df = ex.cov()
        raw_cov = window.cov()
        if CASH_NAME in window.columns:
            # 现金对角与现金-风险资产相关项用原始收益口径还原
            cov_df.loc[CASH_NAME, CASH_NAME] = raw_cov.loc[CASH_NAME, CASH_NAME]
            for a in window.columns:
                if a == CASH_NAME:
                    continue
                cov_df.loc[CASH_NAME, a] = raw_cov.loc[CASH_NAME, a]
                cov_df.loc[a, CASH_NAME] = raw_cov.loc[a, CASH_NAME]
        cov = cov_df.values * TRADING_DAYS
    cov = np.nan_to_num(np.asarray(cov, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    cov = (cov + cov.T) / 2.0            # 强制对称，避免数值不对称污染求逆/pinv
    if shrink and shrink > 0:
        d = np.diag(np.diag(cov))
        cov = (1.0 - shrink) * cov + shrink * d
    return mu, cov


def _inv_spd(mat: np.ndarray, label: str = '') -> np.ndarray:
    """求逆（优先逆矩阵；近奇异/含非有限值时退回伪逆并告警）。

    协方差/精度矩阵接近奇异时，直接求逆会把微小误差放大成极端权重，
    业界通行做法是改用伪逆（pinv）。
    """
    mat = np.asarray(mat, dtype=float)
    mat = np.nan_to_num(mat, nan=0.0, posinf=0.0, neginf=0.0)
    mat = (mat + mat.T) / 2.0
    try:
        cond = np.linalg.cond(mat)
    except Exception:
        cond = np.inf
    use_pinv = (not np.isfinite(cond)) or cond > 1e10
    if not use_pinv:
        try:
            inv = np.linalg.inv(mat)
            if np.all(np.isfinite(inv)):
                return inv
        except Exception:
            pass
    print('[模型][警告] %s 矩阵近奇异或求逆失败（条件数 %s），改用伪逆(pinv)'
          % (label, ('%.2e' % cond) if np.isfinite(cond) else '不可用'), flush=True)
    try:
        return np.linalg.pinv(mat, hermitian=True)
    except Exception:
        return np.linalg.pinv(mat)


def _clean_weights(w: np.ndarray, tol: float = 1e-6) -> np.ndarray:
    """数值清理：负值截 0、归一化。"""
    w = np.where(w < tol, 0.0, w)
    s = w.sum()
    return w / s if s > 0 else np.ones(len(w)) / len(w)


def check_weights(w: np.ndarray, bounds=None, label: str = '') -> np.ndarray:
    """权重合法性自检：和为 1、非负、上下界（容忍 1e-4）。

    用显式异常而非 assert：python -O 会禁用 assert，导致越界解被静默放行。
    """
    w = np.asarray(w, dtype=float)
    if abs(w.sum() - 1.0) >= 1e-4:
        raise RuntimeError('%s 权重和 %.6f != 1' % (label, w.sum()))
    if not (w >= -1e-4).all():
        raise RuntimeError('%s 出现负权重: %s' % (label, w))
    if bounds:
        for i, (lo, hi) in enumerate(bounds):
            if not (w[i] >= lo - 1e-4 and w[i] <= hi + 1e-4):
                raise RuntimeError('%s 第 %d 个资产权重 %.4f 越界 [%s, %s]'
                                   % (label, i, w[i], lo, hi))
    return w


def parse_bounds(bounds_str: str, n: int):
    """'0,1,0,1,...' 或 None → [(lo,hi), ...]。"""
    if not bounds_str:
        return None
    vals = [float(x) for x in bounds_str.split(',')]
    if len(vals) != 2 * n:
        raise ValueError('边界个数须为 2×资产数=%d，实际 %d 个' % (2 * n, len(vals)))
    return [(vals[2 * i], vals[2 * i + 1]) for i in range(n)]


# ----------------------------------------------------------------------
# 模型 1：固定权重
# ----------------------------------------------------------------------
def fixed_weight(mu, cov, weights=None, names=None) -> np.ndarray:
    """固定权重。weights: 各资产权重列表（和不必为1，内部归一化）；默认等权。"""
    if weights is None:
        w = np.ones(len(mu)) / len(mu)
    else:
        w = np.asarray(weights, dtype=float)
        if len(w) != len(mu):
            raise ValueError('固定权重个数须等于资产数（%d）' % len(mu))
        w = w / w.sum()
    return check_weights(w, label='固定权重')


# ----------------------------------------------------------------------
# 模型 2：均值方差
# ----------------------------------------------------------------------
def mean_variance(mu, cov, lam: float = 2.0, bounds=None, names=None) -> np.ndarray:
    """均值方差优化：max μᵀw − (λ/2)·wᵀΣw，s.t. Σw=1、多头、上下界。"""
    n = len(mu)
    bnds = bounds or [(0.0, 1.0)] * n

    def neg_util(w):
        return -(mu @ w - 0.5 * lam * w @ cov @ w)

    res = minimize(neg_util, np.ones(n) / n, method='SLSQP',
                   bounds=bnds, constraints=({'type': 'eq', 'fun': lambda w: w.sum() - 1.0},),
                   options={'maxiter': 500, 'ftol': 1e-12})
    if not np.isfinite(res.fun):
        raise RuntimeError('均值方差优化失败（目标值非有限）: %s' % res.message)
    if not res.success:
        print('[模型][警告] 均值方差 SLSQP 未收敛（%s），返回当前解，请核对权重是否异常'
              % res.message, flush=True)
    return check_weights(_clean_weights(res.x), bounds, label='均值方差')


# ----------------------------------------------------------------------
# 模型 3：风险平价
# ----------------------------------------------------------------------
def _risk_contribution(w: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """各资产风险贡献（绝对值口径，和=组合波动）。"""
    sigma = float(np.sqrt(w @ cov @ w))
    mrc = cov @ w
    return w * mrc / sigma


def risk_parity(mu, cov, lam=None, bounds=None, names=None) -> np.ndarray:
    """风险平价：各资产风险贡献相等。

    目标函数（等风险贡献预算）：
        J = Σ (RC_i − σ_p/N)²  最小化，s.t. Σw=1、多头。
    ⚠️ 现金（固定收益模拟）方差为 0 会使问题退化（100% 现金时 J=0 平凡解），
    故对协方差对角加 1e-6 下限（年化波动约 0.1% 的方差地板）。
    """
    n = len(mu)
    bnds = bounds or [(0.0, 1.0)] * n
    cov = np.asarray(cov, dtype=float)
    cov = cov + np.eye(n) * 1e-6

    def objective(w):
        sigma = float(np.sqrt(w @ cov @ w))
        rc = _risk_contribution(w, cov)
        target = sigma / n
        return float(np.sum((rc - target) ** 2))

    res = minimize(objective, np.ones(n) / n, method='SLSQP',
                   bounds=bnds, constraints=({'type': 'eq', 'fun': lambda w: w.sum() - 1.0},),
                   options={'maxiter': 1000, 'ftol': 1e-16})
    if not np.isfinite(res.fun):
        raise RuntimeError('风险平价优化失败（目标值非有限）: %s' % res.message)
    if not res.success:
        print('[模型][警告] 风险平价 SLSQP 未收敛（%s），返回当前解，请核对权重是否异常'
              % res.message, flush=True)
    return check_weights(_clean_weights(res.x), bounds, label='风险平价')


# ----------------------------------------------------------------------
# 模型 4：Black-Litterman
# ----------------------------------------------------------------------
def views_to_PQ(views: list, names: list):
    """观点列表 → (P ndarray K×N, Q ndarray K, conf ndarray K)。

    views: [{'p': {'宽基': 1.0}, 'q': 0.05, 'conf': 0.5},# 绝对观点：宽基年化 5%
         {'p': {'黄金': 1.0, '宽基': -1.0}, 'q': 0.03, 'conf': 0.6}]  # 相对观点：黄金跑赢宽基 3%
    资产名用中文（ASSET_NAMES）；p 缺省系数 1.0。

    纯相对观点（系数和为 0）自动归一化到 max|p| = 1：
    P 矩阵是原样进 BL 公式的，不做缩放，因此 q 的单位会跟着 p 的量纲走——
    写 {'黄金': 0.1, '宽基': -0.1} 配 q=0.03，数学含义是"黄金跑赢宽基 **30** 个百分点"
    （0.1×R_金 − 0.1×R_宽 = 0.03），而不是 3 个百分点，极端观点会把组合推向单一资产满仓。
    归一化后 q 恒等于"年化价差（百分点）"，符合直觉。绝对观点（系数和≠0）不归一化，
    保持"某资产年化收益 = q"的原义。
    """
    k, n = len(views), len(names)
    P = np.zeros((k, n))
    Q = np.zeros(k)
    conf = np.ones(k)
    for i, v in enumerate(views):
        p = v.get('p', {})
        for name, coef in p.items():
            if name not in names:
                raise ValueError('观点资产名 "%s" 不在资产池 %s' % (name, names))
            P[i, names.index(name)] = float(coef)
        if abs(P[i].sum()) < 1e-12 and np.abs(P[i]).max() > 0:
            P[i] /= np.abs(P[i]).max()          # 纯相对观点：q 即年化价差
        Q[i] = float(v['q'])
        conf[i] = float(v.get('conf', 0.5))
        if conf[i] <= 0:
            raise ValueError('第 %d 条观点的信心水平须为正' % (i + 1))
    return P, Q, conf


def omega_matrix(P: np.ndarray, cov: np.ndarray, conf: np.ndarray,
                 mode: str = 'ratio', tau: float = 0.05) -> np.ndarray:
    """观点误差矩阵 Ω（对角）。

    mode='ratio'（默认，He-Litterman 置信度比例法；与 Idzorek 2005 刻度因子法**完全等价**，
        刻度因子 τcf = c/(1−c)）：Ω = τ·(1−c)/c · diag(PΣPᵀ)
        含义直观：conf = 后验期望落在该观点上的比例（conf=0.6 → 约六成权重给观点）。
    mode='idzorek'：与 'ratio' 同一公式，保留该命名以对齐常见实现/业务表述。
    mode='legacy'：历史口径 Ω = diag(PΣPᵀ)/conf（**不含 τ**）。该式把观点影响
        严重压低（τ=0.05 时 conf=0.5 仅约 2.4%、conf=0.9 约 50% 权重给观点），
        仅用于复现历史结果，不推荐使用。
    """
    psp = np.diag(P @ cov @ P.T)
    if mode == 'legacy':
        return np.diag(psp / conf)
    if np.any(conf >= 1.0):
        raise ValueError('观点信心水平须在 (0, 1) 之间（1.0 会使 Ω 奇异）')
    ratio = np.maximum(1.0 - conf, 1e-6) / conf
    return np.diag(tau * psp * ratio)


def black_litterman(mu, cov, lam: float = 2.0, bounds=None, names=None,
                    w_eq=None, views: list = None, tau: float = 0.05,
                    omega_mode: str = 'ratio') -> np.ndarray:
    """BL 模型（标准 He-Litterman）+ 均值方差落地。

    步骤：
        1. 隐含均衡超额收益  Π = δ·Σ·w_eq（w_eq 默认等权，δ=λ 风险厌恶系数）
        2. 观点不确定性     Ω = τ(1−conf)/conf · diag(P·Σ·Pᵀ)（omega_mode='ratio'/'idzorek'，
                             conf 即后验落在观点上的权重；'legacy' 为不含 τ 的历史口径）
        3. 后验期望         E[R] = [(τΣ)⁻¹ + PᵀΩ⁻¹P]⁻¹ [(τΣ)⁻¹Π + PᵀΩ⁻¹Q]
        4. 后验协方差       Σ_bl = Σ + M，M = [(τΣ)⁻¹ + PᵀΩ⁻¹P]⁻¹
        5. MVO 落地：max E[R]ᵀw − (λ/2)·wᵀΣ_bl·w
    无观点时 E[R]=Π、Σ_bl=Σ，退化为隐含均衡 MVO。

    数值稳健性：所有矩阵求逆走 _inv_spd（近奇异自动改用伪逆并告警）。
    """
    n = len(names)
    cov = np.asarray(cov, dtype=float)
    # 方差地板 1e-6：现金（固定收益模拟）方差为 0 会使 τΣ 奇异、不可求逆
    cov = cov + np.diag(np.maximum(1e-6 - np.diag(cov), 0.0))
    w_eq = np.ones(n) / n if w_eq is None else np.asarray(w_eq, dtype=float)
    delta = lam if lam else 2.0
    pi = delta * cov @ w_eq

    if views:
        P, Q, conf = views_to_PQ(views, names)
        omega = omega_matrix(P, cov, conf, mode=omega_mode, tau=tau)
        tau_cov_inv = _inv_spd(tau * cov, 'τΣ')
        omega_inv = _inv_spd(omega, 'Ω')
        A = tau_cov_inv + P.T @ omega_inv @ P
        M = _inv_spd(A, 'A=(τΣ)⁻¹+PᵀΩ⁻¹P')
        exp_ret = M @ (tau_cov_inv @ pi + P.T @ omega_inv @ Q)
        cov_post = cov + M
    else:
        exp_ret = pi
        cov_post = cov

    w = mean_variance(np.asarray(exp_ret).ravel(), cov_post, lam=lam, bounds=bounds)
    return check_weights(w, bounds, label='BL')


# ----------------------------------------------------------------------
# 统一入口
# ----------------------------------------------------------------------
def solve(model: str, mu, cov, names=None, bounds=None, lam: float = 2.0,
          fixed_weights=None, views: list = None, tau: float = 0.05,
          omega_mode: str = 'ratio') -> np.ndarray:
    """按模型名求解权重。model ∈ fixed/mv/rp/bl。"""
    if model == 'fixed':
        return fixed_weight(mu, cov, weights=fixed_weights, names=names)
    if model == 'mv':
        return mean_variance(mu, cov, lam=lam, bounds=bounds, names=names)
    if model == 'rp':
        return risk_parity(mu, cov, bounds=bounds, names=names)
    if model == 'bl':
        return black_litterman(mu, cov, lam=lam, bounds=bounds, names=names,
                               views=views, tau=tau, omega_mode=omega_mode)
    raise ValueError('未知模型: %s（可选 fixed/mv/rp/bl）' % model)


MODEL_LABELS = {'fixed': '固定权重', 'mv': '均值方差', 'rp': '风险平价', 'bl': 'BL模型'}
