"""
因子分析 — 编排入口

调用 AmazingData.factor_analysis 算法 + report_renderer 生成 HTML 报告。

用法:
    python run_analysis.py --factor_name ma5 --stock_count 200 --begin 20250101 --end 20260530

或在 Python 中:
    from scripts.run_analysis import run_factor_analysis
    run_factor_analysis(factor_raw, factor_name, stock_list, close, benchmark_df, mc, output_path)
"""

import sys
import os
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

# 确保可以 import 当前脚本目录
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r'D:\AmazingData')

from AmazingData.factor_analysis import (
    FactorPreProcessing, IcAnalysis, RegressionAnalysis,
    StratificationAnalysis, FactorCrowdingAnalysis,
    ExtremeMethod, ScaleMethod, FillNanMethod,
)
from report_renderer import FactorAnalysisReport

# 尝试导入多因子合成类（API 可能因版本而异）
try:
    from AmazingData.factor_analysis import (
        CollinearityAnalysis, FactorOrthogonalization,
        FactorWeighting, StockScorer,
    )
    _has_multi_factor_api = True
except ImportError:
    CollinearityAnalysis = None
    FactorOrthogonalization = None
    FactorWeighting = None
    StockScorer = None
    _has_multi_factor_api = False

# 拥挤度指标英文 key → 中文名映射
CROWDING_KEY_MAP = {
    'valuation_spread': '估值价差',
    'pairwise_corr': '配对相关性',
    'return_reversal': '长期收益反转',
    'factor_volatility': '因子波动率',
    'composite_crowding': '复合拥挤度',
}

def _rename_group_data(group_navs, group_metrics, turnover, group_keys):
    """将英文分组名统一映射为中文：group_0→分组1, group_0_count→分组1-个数法, ..."""
    name_map = {f'group_{i}': f'分组{i+1}' for i in range(len(group_keys))}

    renamed_navs = group_navs.rename(columns=name_map)
    renamed_metrics = {name_map.get(k, k): v for k, v in group_metrics.items()}

    turnover_map = {}
    for old_key, new_key in name_map.items():
        turnover_map[f'{old_key}_count'] = f'{new_key}-个数法'
        turnover_map[f'{old_key}_weight'] = f'{new_key}-权重法'
    renamed_turnover = turnover.rename(columns=turnover_map) if turnover is not None else None

    return renamed_navs, renamed_metrics, renamed_turnover, name_map


def run_factor_analysis(
    factor_raw: pd.DataFrame,
    factor_name: str,
    close_price: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    market_cap: pd.DataFrame = None,
    output_path: str = None,
    group_num: int = 5,
    ic_decay: int = 20,
    factor_desc: str = None,
) -> str:
    """
    一键执行完整因子分析并生成 HTML 报告。

    :param factor_raw: 原始因子值 DataFrame (index=日期, columns=股票代码)
    :param factor_name: 因子名称
    :param close_price: 收盘价 DataFrame
    :param benchmark_df: 基准收盘价 DataFrame (columns=['close'])
    :param market_cap: 流通市值 DataFrame (可选，用于拥挤度)
    :param output_path: 报告输出路径
    :param group_num: 分层数量
    :param ic_decay: IC 衰减周期
    :param factor_desc: 因子计算方法描述（用于因子定义区）
    :return: 报告文件路径
    """
    if output_path is None:
        output_path = f'{factor_name}_report.html'

    # ============================================================
    # 1. 预处理
    # ============================================================
    fpp = FactorPreProcessing(factor_raw)
    fpp.extreme_processing({ExtremeMethod.MAD.value: {'median_multiple': 5}})
    fpp.scale_processing(ScaleMethod.Z_SCORE.value)
    fpp.fill_nan_processing(FillNanMethod.MEDIAN.value)
    factor = fpp.processed_data

    # ============================================================
    # 2. IC 分析
    # ============================================================
    ia = IcAnalysis(factor, factor_name, close_price, ic_decay)
    ia.cal_ic_df(method='spearmanr')
    ia.cal_ic_indicator()

    # ============================================================
    # 3. 回归法分析
    # ============================================================
    ra = RegressionAnalysis(factor, factor_name, close_price, benchmark_df)
    ra.cal_factor_return()
    ra.cal_t_value_statistics()
    ra.cal_net_analysis()
    ra.cal_acf(nlags=10)

    # ============================================================
    # 4. 分层法分析
    # ============================================================
    bm_series = benchmark_df['close'] / benchmark_df['close'].iloc[0] if not benchmark_df.empty else None
    sa = StratificationAnalysis(factor, close_price, group_num, False, bm_series)
    sa.run()
    sa._backtest.calc_signal_decay_reversal(10)

    # ============================================================
    # 5. 因子拥挤度
    # ============================================================
    crowding_series = {}
    crowding_summary = pd.DataFrame()
    if market_cap is not None:
        fca = FactorCrowdingAnalysis(factor, close_price, market_cap, group_num, False)
        cr = fca.calc_all(60)
        crowding_summary = fca.crowding_summary()
        crowding_series = {
            CROWDING_KEY_MAP.get(k, k): v
            for k, v in cr.items()
            if v is not None and len(v.dropna()) > 1
        }

    # ============================================================
    # 6. 生成报告
    # ============================================================
    title = f'{factor_name} 因子分析报告'
    report = FactorAnalysisReport(factor_name, title)

    # 因子定义
    calc_row = f'<tr><td>计算方法</td><td>{factor_desc}</td></tr>' if factor_desc else ''
    desc = f'''<h3 style="color:#e0e6ed;margin-bottom:16px">{factor_name}</h3>
<table>
<tr><th style="width:120px">项目</th><th>内容</th></tr>
<tr><td>因子名称</td><td>{factor_name}</td></tr>
{calc_row}
<tr><td>股票数量</td><td>{len(factor.columns)} 只</td></tr>
<tr><td>测试区间</td><td>{factor.index[0].strftime('%Y-%m-%d')} ~ {factor.index[-1].strftime('%Y-%m-%d')}</td></tr>
<tr><td>预处理</td><td>MAD(5倍) → Z-Score → 中位数补空值</td></tr>
<tr><td>IC 方法</td><td>Spearman 秩相关系数</td></tr>
<tr><td>分层数</td><td>{group_num}组 (降序)</td></tr>
</table>'''
    report.add_definition_section(desc)
    report.add_ic_section(ia.ic_df, ia.ic_result, ia.p_value_df)
    report.add_regression_section(ra.factor_return, ra.factor_t_value, ra.net_analysis_result)
    renamed_navs, renamed_metrics, renamed_turnover, name_map = _rename_group_data(
        sa.group_navs, sa.group_metrics, sa.turnover, sa.group_keys,
    )
    report.add_stratification_section(
        renamed_navs, renamed_metrics, renamed_turnover,
        sa.signal_decay, sa.signal_reversal, sa.long_short_nav,
    )
    if not crowding_summary.empty:
        report.add_crowding_section(crowding_summary, crowding_series)

    path = report.generate(output_path, open_browser=True)
    print(f"报告已生成: {path}")

    # 打印关键摘要
    print("\n" + "=" * 50)
    print("关键指标摘要")
    print("=" * 50)
    print(f"IC 均值 (delay_1): {ia.ic_result.loc['IC 均值', 'delay_1']:.4f}")
    print(f"IC IR (delay_1):   {ia.ic_result.loc['IC IR', 'delay_1']:.4f}")
    nv = ra.net_analysis_result.get('cumprod', {})
    print(f"年化因子收益率: {nv.get('annual_return', 0):.4f}")
    print(f"夏普比率:       {nv.get('sharpe_ratio', 0):.4f}")
    print(f"最大回撤:       {nv.get('max_drawdown', 0):.2f}%")
    for gk in sa.group_keys:
        m = sa.group_metrics.get(gk, {})
        print(f"{name_map[gk]}: 年化={m.get('annual_return', 0):.4f}, 夏普={m.get('sharpe_ratio', 0):.4f}")

    return path


# ============================================================
# 多因子合成辅助函数
# ============================================================

def _preprocess_single_factor(factor_raw: pd.DataFrame) -> pd.DataFrame:
    """预处理单个因子：MAD去极值 + Z-Score标准化 + 中位数补空值"""
    fpp = FactorPreProcessing(factor_raw)
    fpp.extreme_processing({ExtremeMethod.MAD.value: {'median_multiple': 5}})
    fpp.scale_processing(ScaleMethod.Z_SCORE.value)
    fpp.fill_nan_processing(FillNanMethod.MEDIAN.value)
    return fpp.processed_data


def _ensure_common_index(*dfs: pd.DataFrame) -> List[pd.DataFrame]:
    """对齐多个 DataFrame 的 index 和 columns（取交集）"""
    common_idx = dfs[0].index
    for df in dfs[1:]:
        common_idx = common_idx.intersection(df.index)
    common_cols = dfs[0].columns
    for df in dfs[1:]:
        common_cols = common_cols.intersection(df.columns)
    return [df.loc[common_idx, common_cols] for df in dfs]


def _detect_collinearity(factors: Dict[str, pd.DataFrame]) -> Tuple[pd.DataFrame, pd.DataFrame, float]:
    """
    共线性检测。
    
    优先使用 AmazingData 的 CollinearityAnalysis，失败则使用自实现兜底。
    
    :return: (相关系数矩阵, VIF DataFrame, 条件数)
    """
    # 取最新一期截面做检测
    factor_names = list(factors.keys())
    cross_section = {}
    for name, f in factors.items():
        last_valid = f.dropna(how='all').index[-1]
        cross_section[name] = f.loc[last_valid].dropna()

    # 对齐股票
    common_stocks = cross_section[factor_names[0]].index
    for name in factor_names[1:]:
        common_stocks = common_stocks.intersection(cross_section[name].index)
    cross_data = pd.DataFrame({name: cross_section[name].loc[common_stocks].values
                                for name in factor_names})

    # Try AmazingData API first
    if _has_multi_factor_api:
        try:
            ca = CollinearityAnalysis(factors)
            ca.cal_collinearity()
            corr_matrix = ca.relation if ca.relation is not None else cross_data.corr()
            vif_df = ca.vif if ca.vif is not None else pd.DataFrame()
            cond_num = ca.condition_num.mean() if ca.condition_num is not None else float(np.linalg.cond(cross_data.values))
            return corr_matrix, vif_df, cond_num
        except Exception:
            pass

    # Fallback: 自实现
    # 相关系数矩阵
    corr_matrix = cross_data.corr()

    # VIF: 对每个因子做回归，VIF = 1 / (1 - R²)
    vif_values = {}
    for i, name in enumerate(factor_names):
        y = cross_data.iloc[:, i].values
        X = cross_data.drop(columns=[name]).values
        if X.shape[1] == 0:
            vif_values[name] = 1.0
            continue
        # 加截距项
        X_design = np.column_stack([np.ones(len(y)), X])
        try:
            beta = np.linalg.lstsq(X_design, y, rcond=None)[0]
            y_pred = X_design @ beta
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 1e-12 else 0
            vif_values[name] = 1 / (1 - r2) if r2 < 1 - 1e-12 else float('inf')
        except Exception:
            vif_values[name] = 1.0

    vif_df = pd.DataFrame({'因子': list(vif_values.keys()), 'VIF': list(vif_values.values())}).set_index('因子')

    # 条件数
    cond_num = float(np.linalg.cond(cross_data.values))

    return corr_matrix, vif_df, cond_num


def _orthogonalize_factors(
    factors: Dict[str, pd.DataFrame],
    method: str = 'symmetric',
) -> Dict[str, pd.DataFrame]:
    """
    因子正交化。
    
    优先使用 AmazingData，失败则使用 Gram-Schmidt 自实现。
    """
    if _has_multi_factor_api:
        try:
            fo = FactorOrthogonalization(factors)
            fo.cal_orthogonalization(method=method)
            if fo.orthogonalized_data:
                return fo.orthogonalized_data
        except Exception:
            pass

    # Fallback: Gram-Schmidt 正交化（逐期截面处理）
    factor_names = list(factors.keys())
    aligned = _ensure_common_index(*factors.values())
    aligned_factors = dict(zip(factor_names, aligned))

    common_idx = aligned[0].index
    common_cols = aligned[0].columns

    orthogonalized = {}
    for name in factor_names:
        orthogonalized[name] = pd.DataFrame(np.nan, index=common_idx, columns=common_cols)

    for t in common_idx:
        X = np.column_stack([aligned_factors[name].loc[t].values for name in factor_names])
        Q = np.zeros_like(X)
        for i in range(X.shape[1]):
            v = X[:, i].copy().astype(float)
            for j in range(i):
                v -= np.dot(Q[:, j], X[:, i]) * Q[:, j]
            norm = np.linalg.norm(v)
            if norm > 1e-12:
                Q[:, i] = v / norm

        for i, name in enumerate(factor_names):
            orthogonalized[name].loc[t] = Q[:, i]

    return orthogonalized


# ============================================================
# 多因子合成主函数
# ============================================================

def run_multi_factor_analysis(
    factors: Dict[str, pd.DataFrame],
    factor_names: List[str],
    close_price: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    market_cap: pd.DataFrame = None,
    output_path: str = None,
    group_num: int = 5,
    ic_decay: int = 20,
    weight_method: str = 'equal_weight',
    orthogonal_method: str = 'symmetric',
    use_orthogonal: bool = True,
    factor_descs: Dict[str, str] = None,
) -> str:
    """
    多因子合成 + 综合因子分析 + HTML 报告生成。

    流程: 预处理 → 共线性检测 → 正交化(可选) → 加权 → 打分 → 合成因子分析

    :param factors: {因子名: 原始因子值 DataFrame (T×N)}
    :param factor_names: 因子名列表（决定排序和命名）
    :param close_price: 收盘价 DataFrame
    :param benchmark_df: 基准收盘价 DataFrame (columns=['close'])
    :param market_cap: 流通市值 DataFrame (可选)
    :param output_path: 报告输出路径
    :param group_num: 分层数量
    :param ic_decay: IC 衰减周期
    :param weight_method: 加权方法 (equal_weight/ic_mean/ic_ir/max_ic/max_ic_ir/return_mean/return_half_life/return_ir)
    :param orthogonal_method: 正交化方法 (symmetric/schmidt/canonical)
    :param use_orthogonal: 是否进行正交化
    :param factor_descs: {因子名: 计算方法描述}，用于报告因子定义区
    :return: 报告文件路径
    """
    if output_path is None:
        output_path = 'multi_factor_report.html'

    print("=" * 60)
    print(f"多因子合成分析")
    print(f"因子列表: {factor_names}")
    print(f"加权方法: {weight_method} | 正交化: {use_orthogonal}")
    print("=" * 60)

    # ============================================================
    # 1. 逐因子预处理
    # ============================================================
    print("\n[1/6] 逐因子预处理...")
    processed_factors = {}
    for name in factor_names:
        if name not in factors:
            raise KeyError(f"因子 '{name}' 不在 factors 字典中")
        print(f"  处理 '{name}' ...")
        processed_factors[name] = _preprocess_single_factor(factors[name])

    # ============================================================
    # 2. 共线性检测
    # ============================================================
    print("\n[2/6] 共线性检测...")
    corr_matrix, vif_df, cond_num = _detect_collinearity(processed_factors)
    print(f"  条件数: {cond_num:.2f}")
    if not vif_df.empty:
        for idx, row in vif_df.iterrows():
            vif_val = row['VIF'] if 'VIF' in vif_df.columns else row.iloc[0]
            status = "[!] 严重共线性" if vif_val > 10 else "[OK] 正常"
            print(f"  {idx}: VIF={vif_val:.2f} {status}")

    # ============================================================
    # 3. 因子正交化
    # ============================================================
    need_orthogonal = use_orthogonal and (cond_num > 30 or (not vif_df.empty and
        any((vif_df['VIF'] if 'VIF' in vif_df.columns else vif_df.iloc[:, 0]) > 10)))
    working_factors = processed_factors

    if need_orthogonal:
        print(f"\n[3/6] 因子正交化 (method={orthogonal_method})...")
        working_factors = _orthogonalize_factors(processed_factors, method=orthogonal_method)
        print("  正交化完成")
    else:
        print(f"\n[3/6] 跳过正交化 (条件数={cond_num:.2f})")

    # ============================================================
    # 4. 计算因子 IC（供 FactorWeighting 使用）
    # ============================================================
    print(f"\n[4/6] 计算因子 IC ...")
    factor_ic = {}
    for name in factor_names:
        aligned_f, aligned_close = _ensure_common_index(working_factors[name], close_price)
        ia_tmp = IcAnalysis(aligned_f, name, aligned_close, ic_decay=ic_decay)
        ia_tmp.cal_ic_df(method='spearmanr')
        factor_ic[name] = ia_tmp.ic_df

    # ============================================================
    # 5. FactorWeighting 加权 + 合成
    # ============================================================
    # CLI 名称到 FactorWeighting 内部方法名的映射（仅 CLI 特殊命名需映射）
    _WM_MAP = {'equal_weight': 'equal'}
    fw_method = _WM_MAP.get(weight_method, weight_method)
    print(f"\n[5/6] FactorWeighting (method={fw_method})...")
    fw = FactorWeighting(working_factors)
    composite_factor = fw.weighting(fw_method, factor_ic=factor_ic, window=ic_decay)
    print(f"  合成因子 shape: {composite_factor.shape}")

    # 提取权重用于展示
    weights = {name: 1.0 / len(factor_names) for name in factor_names}
    if fw_method != 'equal':
        try:
            if fw_method in ('max_ic_ir', 'max_ic'):
                w_func = fw._weighting_max_ic_ir if fw_method == 'max_ic_ir' else fw._weighting_max_ic
                na_w_df = w_func(factor_ic, ic_decay)
            else:
                na_w_df = fw._weighting_simple(fw_method, None, factor_ic, ic_decay, ic_decay)
            last_row = na_w_df.dropna(how='all')
            if not last_row.empty:
                last_row = last_row.iloc[-1]
                total = last_row.abs().sum()
                if total > 1e-12:
                    weights = {name: abs(last_row.get(name, 0)) / total for name in factor_names}
        except Exception:
            pass
    for name, w in weights.items():
        print(f"  {name}: {w:.4f}")

    # ============================================================
    # 6. 合成因子验证分析
    # ============================================================
    composite_name = f"MultiFactor_{weight_method}"
    print(f"\n[6/6] 合成因子分析 ({composite_name})...")

    # 预处理合成因子
    fpp = FactorPreProcessing(composite_factor)
    fpp.extreme_processing({ExtremeMethod.MAD.value: {'median_multiple': 5}})
    fpp.scale_processing(ScaleMethod.Z_SCORE.value)
    fpp.fill_nan_processing(FillNanMethod.MEDIAN.value)
    composite_processed = fpp.processed_data

    # IC 分析
    ia = IcAnalysis(composite_processed, composite_name, close_price, ic_decay)
    ia.cal_ic_df(method='spearmanr')
    ia.cal_ic_indicator()

    # 回归法分析
    ra = RegressionAnalysis(composite_processed, composite_name, close_price, benchmark_df)
    ra.cal_factor_return()
    ra.cal_t_value_statistics()
    ra.cal_net_analysis()
    ra.cal_acf(nlags=10)

    # 分层法分析
    bm_series = benchmark_df['close'] / benchmark_df['close'].iloc[0] if not benchmark_df.empty else None
    sa = StratificationAnalysis(composite_processed, close_price, group_num, False, bm_series)
    sa.run()
    sa._backtest.calc_signal_decay_reversal(10)

    # 因子拥挤度
    crowding_series = {}
    crowding_summary = pd.DataFrame()
    if market_cap is not None:
        fca = FactorCrowdingAnalysis(composite_processed, close_price, market_cap, group_num, False)
        cr = fca.calc_all(60)
        crowding_summary = fca.crowding_summary()
        crowding_series = {
            CROWDING_KEY_MAP.get(k, k): v
            for k, v in cr.items()
            if v is not None and len(v.dropna()) > 1
        }

    # ============================================================
    # 7. 生成报告
    # ============================================================
    print("\n生成多因子合成报告...")
    title = f'多因子合成分析报告'
    display_title = f'多因子合成分析报告<br><span style="font-size:14px;font-weight:400;color:#90a4ae;">{weight_method}</span>'
    report = FactorAnalysisReport(f"{composite_name}_{weight_method}", title, is_multi_factor=True, display_title=display_title)

    # --- 多因子定义 ---
    test_range = f"{composite_processed.index[0].strftime('%Y-%m-%d')} ~ {composite_processed.index[-1].strftime('%Y-%m-%d')}"
    factor_descs = factor_descs or {}
    factor_list_html = ''.join(
        f'<tr><td>{name}</td><td>{factor_descs.get(name, "-")}</td>'
        f'<td>{factors[name].shape[0]} × {factors[name].shape[1]}</td></tr>'
        for name in factor_names
    )
    desc = f'''<h3 style="color:#e0e6ed;margin-bottom:16px">多因子合成<br><span style="font-size:13px;font-weight:400;color:#90a4ae;">{weight_method}</span></h3>
<table>
<tr><th style="width:140px">项目</th><th>内容</th></tr>
<tr><td>因子名称</td><td>{', '.join(factor_names)}</td></tr>
<tr><td>合成因子数</td><td>{len(factor_names)} 个</td></tr>
<tr><td>测试区间</td><td>{test_range}</td></tr>
<tr><td>正交化</td><td>{orthogonal_method if need_orthogonal else '未进行'} (条件数={cond_num:.2f})</td></tr>
<tr><td>加权方法</td><td>{weight_method}</td></tr>
<tr><td>IC 方法</td><td>Spearman 秩相关系数</td></tr>
<tr><td>分层数</td><td>{group_num}组 (降序)</td></tr>
</table>
<h4 style="margin-top:20px;color:#90a4ae;">因子列表</h4>
<table>
<tr><th>因子名</th><th>算法</th><th>数据规模</th></tr>
{factor_list_html}
</table>'''
    report.add_definition_section(desc)

    # --- 共线性分析 ---
    report.add_collinearity_section(corr_matrix, vif_df, cond_num)

    # --- 权重分析 ---
    weight_df = pd.DataFrame({
        '因子': list(weights.keys()),
        '权重': list(weights.values()),
    }).set_index('因子')
    report.add_weighting_section(weight_df, weight_method)

    # --- 单因子分析 ---
    report.add_ic_section(ia.ic_df, ia.ic_result, ia.p_value_df)
    report.add_regression_section(ra.factor_return, ra.factor_t_value, ra.net_analysis_result)
    renamed_navs2, renamed_metrics2, renamed_turnover2, _ = _rename_group_data(
        sa.group_navs, sa.group_metrics, sa.turnover, sa.group_keys,
    )
    report.add_stratification_section(
        renamed_navs2, renamed_metrics2, renamed_turnover2,
        sa.signal_decay, sa.signal_reversal, sa.long_short_nav,
    )
    if not crowding_summary.empty:
        report.add_crowding_section(crowding_summary, crowding_series)

    path = report.generate(output_path, open_browser=True)
    print(f"报告已生成: {path}")

    # 打印关键摘要
    print("\n" + "=" * 60)
    print("多因子合成关键摘要")
    print("=" * 60)
    print(f"条件数: {cond_num:.2f}")
    for name, w in weights.items():
        print(f"{name}: 权重={w:.4f}")
    print(f"\n--- 合成因子 ({weight_method}) ---")
    print(f"IC 均值 (delay_1): {ia.ic_result.loc['IC 均值', ia.ic_result.columns[0]]:.4f}")
    print(f"IC IR (delay_1):   {ia.ic_result.loc['IC IR', ia.ic_result.columns[0]]:.4f}")
    nv = ra.net_analysis_result.get('cumprod', {})
    print(f"年化因子收益率: {nv.get('annual_return', 0):.4f}")
    print(f"夏普比率:       {nv.get('sharpe_ratio', 0):.4f}")
    print(f"最大回撤:       {nv.get('max_drawdown', 0):.2f}%")

    return path


# ============================================================
# CLI 入口
# ============================================================
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='因子分析报告生成器')
    parser.add_argument('--factor_name', default='test_factor', help='因子名称（单因子模式）')
    parser.add_argument('--stock_count', type=int, default=200, help='股票数量')
    parser.add_argument('--begin', type=int, default=20250101, help='起始日期')
    parser.add_argument('--end', type=int, default=20260530, help='结束日期')
    parser.add_argument('--output', default=None, help='输出路径')
    parser.add_argument('--groups', type=int, default=5, help='分层数量')
    parser.add_argument('--multi', action='store_true', help='启用多因子合成模式')
    parser.add_argument('--weight_method', default='equal_weight',
                        choices=['equal_weight', 'ic_mean', 'ic_ir', 'max_ic', 'max_ic_ir',
                                 'return_mean', 'return_half_life', 'return_ir'],
                        help='多因子加权方法')
    parser.add_argument('--no_orthogonal', action='store_true', help='禁用因子正交化')
    args = parser.parse_args()

    # 获取数据
    from data_provider import DataProvider
    dp = DataProvider()
    stock_list = dp.get_stock_list()[:args.stock_count]
    close = dp.get_close_price(stock_list, args.begin, args.end)
    benchmark_df = dp.get_benchmark('000300.SH', args.begin, args.end)

    # 获取真实流通市值
    mc = dp.get_float_market_value(stock_list, args.begin, args.end)
    if mc.empty:
        print("警告: 无法获取流通市值，拥挤度分析将跳过")
        mc = None

    if args.multi:
        # ============================================================
        # 多因子合成模式
        # ============================================================
        # 计算多个因子
        ma5 = close.rolling(5).mean()
        ma20 = close.rolling(20).mean()
        ma60 = close.rolling(60).mean()

        # 成交量因子
        volume_field = dp.get_kline(stock_list, args.begin, args.end, fields=['close', 'volume'])
        if isinstance(volume_field.columns, pd.MultiIndex):
            close_clean = volume_field['close']
        else:
            close_clean = close

        factor_ma5 = (close_clean - ma5) / ma5
        factor_ma20 = (close_clean - ma20) / ma20
        factor_ma60 = (close_clean - ma60) / ma60

        factors = {
            'ma5': factor_ma5,
            'ma20': factor_ma20,
            'ma60': factor_ma60,
        }
        factor_names = ['ma5', 'ma20', 'ma60']

        run_multi_factor_analysis(
            factors=factors,
            factor_names=factor_names,
            close_price=close_clean,
            benchmark_df=benchmark_df,
            market_cap=mc,
            output_path=args.output,
            group_num=args.groups,
            weight_method=args.weight_method,
            use_orthogonal=not args.no_orthogonal,
        )
    else:
        # ============================================================
        # 单因子模式
        # ============================================================
        ma5 = close.rolling(5).mean()
        factor_raw = (close - ma5) / ma5

        run_factor_analysis(
            factor_raw=factor_raw,
            factor_name=args.factor_name,
            close_price=close,
            benchmark_df=benchmark_df,
            market_cap=mc,
            output_path=args.output,
            group_num=args.groups,
        )
