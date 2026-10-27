# -*- coding: utf-8 -*-
"""
信号层:外部指标面板加载与信号规则

本 skill 不自算指标。指标值由用户调用技术面/基本面指标 skill(如
ad_technical_analysis / ad_fundamental_analysis)获得,整理为
「指标值面板 CSV」后交给本模块。

指标值面板格式:CSV,第一列 date(YYYYMMDD 或 YYYY-MM-DD),
其余列为股票代码,值为指标值(行=日期, 列=股票)。

职责:
    1. 加载并校验指标面板(日期解析、数值化、按交易日对齐)
    2. 信号规则模板,把指标值转原始信号(-1 买入 / +1 卖出 / 0 无信号):
           pos           值 > 0 持有,< 0 空仓(用户已定方向时直接用)
           cross         上穿 0 买入,下穿 0 卖出(适合 DIF-DEA 价差类)
           band:低,高   低于低值买入,高于高值卖出(适合 RSI/CCI 等震荡指标)
    3. 排名合成所需的方向注册由 CLI --dirs 提供(+1 大优 / -1 小优 / 0 不参与)

所有信号矩阵统一为 DataFrame(index=日期, columns=股票代码)。
"""

import os

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------
# 指标面板加载
# ----------------------------------------------------------------------

def load_factor_panel(path: str) -> pd.DataFrame:
    """
    读取单个指标值面板。

    按扩展名分派:
        .h5/.hdf5  HDF5(推荐,大面板读写快),key 即因子名
        其他       CSV(首列 date,其余列为股票代码)

    日期兼容 YYYYMMDD 与 YYYY-MM-DD。
    """
    if path.lower().endswith(('.h5', '.hdf5')):
        df = pd.read_hdf(path, key=_h5_key(path))
    else:
        df = pd.read_csv(path, index_col=0)
    idx = pd.to_datetime(df.index.astype(str).str.replace('-', '', regex=False),
                         format='%Y%m%d')
    df.index = pd.DatetimeIndex(idx)
    df = df.apply(pd.to_numeric, errors='coerce').sort_index()
    df = df[~df.index.duplicated(keep='last')]
    df.columns = df.columns.astype(str)
    return df


def _h5_key(path: str, name: str = None) -> str:
    """
    推导 HDF5 key。

    约定:因子统一存于 '/factors/<因子名>'。若文件里只有一个 key
    (单因子文件),直接使用该 key,便于外部 skill 任意命名。
    """
    if name:
        return f'/factors/{name}'
    with pd.HDFStore(path, 'r') as store:
        keys = store.keys()
    if len(keys) == 1:
        return keys[0]
    raise ValueError(
        f'HDF5 文件含多个因子 {keys},请用 NAME:路径 规格指定因子名'
        '(将读取 /factors/NAME)')


def load_factor_h5(path: str, names=None) -> dict:
    """
    从 HDF5 批量读取因子面板。

    约定存储结构:每个因子一个 key '/factors/<因子名>',
    value 为 DataFrame(行=日期, 列=股票代码)。

    names 为 None 时读取文件内全部因子;否则按列表筛选。
    """
    out = {}
    with pd.HDFStore(path, 'r') as store:
        keys = store.keys()
        want = None if names is None else [f'/factors/{n}' for n in names]
        for k in keys:
            if want is not None and k not in want:
                continue
            panel = store[k]
            idx = pd.to_datetime(
                panel.index.astype(str).str.replace('-', '', regex=False),
                format='%Y%m%d')
            panel.index = pd.DatetimeIndex(idx)
            panel = panel.apply(pd.to_numeric, errors='coerce').sort_index()
            panel.columns = panel.columns.astype(str)
            out[k.split('/')[-1].upper()] = panel
    return out


def save_factors_h5(path: str, factors: dict):
    """
    批量写入因子面板到 HDF5(供指标 skill 输出侧对齐此格式)。

    factors: {因子名: DataFrame(行=日期, 列=股票代码)}
    """
    with pd.HDFStore(path, 'w') as store:
        for name, panel in factors.items():
            store.put(f'/factors/{name}', panel, format='fixed')


def parse_factor_spec(spec: str):
    """
    解析单个因子规格:NAME:path[:rule]

    rule 缺省 pos;band 规则形如 band:30,70
    注意:Windows 路径含盘符冒号(D:\\...),因此 rule 从字符串
    **尾部**识别(仅当末段为已知规则关键字时才视作规则)。
    返回 (name, path, rule)
    """
    parts = spec.strip().split(':', 1)
    if len(parts) == 1:
        raise ValueError(f'因子规格缺少路径: {spec}(应为 NAME:路径[:规则])')
    name, rest = parts[0].strip(), parts[1].strip()

    # 从尾部识别规则关键字(兼容 Windows 盘符冒号)
    rule = 'pos'
    tail = rest.rsplit(':', 1)
    if len(tail) == 2:
        candidate = tail[1].strip()
        if candidate == 'pos' or candidate == 'cross' or \
                candidate.startswith('band'):
            rest, rule = tail[0], candidate

    return name, rest.strip(), rule


def parse_dirs(dirs_spec: str) -> dict:
    """解析方向参数:NAME=1,NAME2=-1 → {NAME: int};缺省 0(不参与排名)"""
    out = {}
    if not dirs_spec:
        return out
    for item in dirs_spec.split(','):
        if '=' not in item:
            continue
        k, v = item.split('=', 1)
        out[k.strip().upper()] = int(v)
    return out


# ----------------------------------------------------------------------
# 信号规则模板
# ----------------------------------------------------------------------

def _sig_pos_gt_zero(x):
    """位置型:值 > 0 持有,< 0 空仓"""
    return np.where(x > 0, -1.0, np.where(x < 0, 1.0, 0.0))


def _sig_cross_zero(x):
    """穿越型:上穿 0 买入,下穿 0 卖出"""
    prev = x.shift(1)
    sig = pd.DataFrame(0.0, index=x.index, columns=x.columns)
    sig[(x > 0) & (prev <= 0)] = -1.0
    sig[(x < 0) & (prev >= 0)] = 1.0
    return sig


def _sig_band(x, lo, hi):
    """阈值型:x < lo 买入,x > hi 卖出(事件,经状态补全成持仓)"""
    sig = pd.DataFrame(0.0, index=x.index, columns=x.columns)
    sig[x < lo] = -1.0
    sig[x > hi] = 1.0
    return sig


def rule_to_signal(panel: pd.DataFrame, rule: str) -> pd.DataFrame:
    """
    指标值面板 → 原始信号矩阵。

    rule: pos / cross / band:低,高
    """
    rule = rule.strip()
    if rule == 'pos':
        sig = _sig_pos_gt_zero(panel)
        return pd.DataFrame(sig, index=panel.index, columns=panel.columns)
    if rule == 'cross':
        return _sig_cross_zero(panel)
    if rule.startswith('band'):
        try:
            lo, hi = [float(v) for v in rule.split(':', 1)[1].split(',')]
        except Exception:
            raise ValueError(f'band 规则格式错误: {rule}(应为 band:低,高)')
        return _sig_band(panel, lo, hi)
    raise ValueError(f'未知信号规则: {rule}(可用: pos / cross / band:低,高)')


def load_factors(spec_list, trade_index: pd.DatetimeIndex = None):
    """
    批量加载因子。

    spec_list: [(name, path, rule), ...]
    路径为 .h5/.hdf5 时按 HDF5 读(key=/factors/NAME);同文件多因子
    会自动合并读取以减少 IO。

    返回:
        values      {name: 指标值面板}
        raw_signals {name: 原始信号矩阵}
    """
    values, raw = {}, {}

    # 按 HDF5 文件分组,同文件一次读取
    h5_groups = {}
    for name, path, rule in spec_list:
        if path.lower().endswith(('.h5', '.hdf5')):
            h5_groups.setdefault(os.path.abspath(path), []).append((name, rule))

    h5_cache = {}
    for abspath, items in h5_groups.items():
        keys = _h5_keys(abspath)
        needed = [n for n, _ in items if f'/factors/{n}' in keys]
        loaded = load_factor_h5(abspath, names=needed) if needed else {}
        h5_cache.update(loaded)
        missing = [n for n, _ in items if n.upper() not in loaded]
        if missing:
            raise FileNotFoundError(
                f'HDF5 {abspath} 中未找到因子 {missing}(约定 key=/factors/因子名;'
                f'文件内现有: {keys})')

    for name, path, rule in spec_list:
        if path.lower().endswith(('.h5', '.hdf5')):
            panel = h5_cache.get(name, h5_cache.get(name.upper()))
        else:
            panel = load_factor_panel(path)
        if panel is None:
            raise FileNotFoundError(f'因子面板未加载: {name}')
        if trade_index is not None:
            panel = panel.reindex(trade_index)
        values[name] = panel
        raw[name] = rule_to_signal(panel, rule)
    return values, raw


def _h5_keys(path: str):
    with pd.HDFStore(path, 'r') as store:
        return store.keys()
