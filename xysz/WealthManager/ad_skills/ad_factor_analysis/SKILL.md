---
name: ad-factor-analysis
description: 中国银河证券星耀数智的因子分析框架。支持单因子分析（预处理+IC/回归/分层三大方法+拥挤度）和多因子合成（共线性检测+正交化+8种加权+打分），自动生成可视化HTML报告。涉及因子检验、因子有效性、因子合成、因子加权、因子正交化、因子打分、IC分析、分层回测、因子拥挤度、多因子选股、因子组合、因子共线性、因子降维等场景时使用。
---

# 因子分析 Skill

中国银河证券星耀数智的因子分析框架。

## 前置条件 - 安装库,设置 AmazingData 账号环境变量
使用本技能前，安装python运行环境(推荐python3.8/3.9/3.10/3.11/3.12/3.13环境)，并安装AmazingData依赖包。
从https://gitee.com/cgs2026/xysz clone整个项目，再用xysz_tools下的wheel文件安装tgw和AmazingData。
```bash
pip install tgw>=1.0.8.7
pip install AmazingData>=1.1.4
```
使用本技能前，用户必须先设置以下环境变量（AmazingData 登录信息）：

```bash
# Windows CMD
set AD_USERNAME=your_username
set AD_PASSWORD=your_password
set AD_HOST=server_ip
set AD_PORT=port

# Windows PowerShell
$env:AD_USERNAME="your_username"
$env:AD_PASSWORD="your_password"
$env:AD_HOST="server_ip"
$env:AD_PORT="port"
```

如果用户未设置环境变量，脚本会报错提示缺少哪些变量。请引导用户先完成环境变量配置。


## 使用流程

### 1. 获取数据

```python
from scripts.data_provider import DataProvider

dp = DataProvider()
stock_list = dp.get_stock_list()[:200]  # 取前200只
close = dp.get_close_price(stock_list, begin_date, end_date)
benchmark_df = dp.get_benchmark('000300.SH', begin_date, end_date)
```

### 2. 计算因子值

用户自定义因子计算，返回 `pd.DataFrame`（index=日期，columns=股票代码）。例如 MA5 偏离度：
```python
ma5 = close.rolling(5).mean()
factor_raw = (close - ma5) / ma5
```

### 3. 因子预处理

```python
from AmazingData.factor_analysis import FactorPreProcessing, ExtremeMethod, ScaleMethod, FillNanMethod

fpp = FactorPreProcessing(factor_raw)
fpp.extreme_processing({ExtremeMethod.MAD.value: {'median_multiple': 5}})
fpp.scale_processing(ScaleMethod.Z_SCORE.value)
fpp.fill_nan_processing(FillNanMethod.MEDIAN.value)
factor = fpp.processed_data
```


### 4. 执行分析

```python
from AmazingData.factor_analysis import (
    IcAnalysis, RegressionAnalysis, StratificationAnalysis, FactorCrowdingAnalysis
)

# IC 分析
ia = IcAnalysis(factor, factor_name, close, ic_decay=20)
ia.cal_ic_df(method='spearmanr')
ia.cal_ic_indicator()

# 回归法分析
ra = RegressionAnalysis(factor, factor_name, close, benchmark_df)
ra.cal_factor_return()
ra.cal_t_value_statistics()
ra.cal_net_analysis()
ra.cal_acf(nlags=10)

# 分层法分析
bm_series = benchmark_df['close'] / benchmark_df['close'].iloc[0]
sa = StratificationAnalysis(factor, close, group_num=5, ascending=False, benchmark=bm_series)
sa.run()
sa._backtest.calc_signal_decay_reversal(10)

# 因子拥挤度
mc = pd.DataFrame(...)  # 流通市值
fca = FactorCrowdingAnalysis(factor, close, mc, group_num=5, ascending=False)
fca.calc_all(window=60)
```

### 5. 生成报告

调用 `scripts/run_analysis.py` 或直接使用 `report_renderer.py`：

```python
from scripts.report_renderer import FactorAnalysisReport

report = FactorAnalysisReport(factor_name, title)
report.add_definition_section(html_desc)      # 因子定义
report.add_ic_section(ia.ic_df, ia.ic_result, ia.p_value_df)
report.add_regression_section(ra.factor_return, ra.factor_t_value, ra.net_analysis_result)
report.add_stratification_section(sa.group_navs, sa.group_metrics, sa.turnover,
                                   sa.signal_decay, sa.signal_reversal, sa.long_short_nav)
report.add_crowding_section(fca.crowding_summary(), crowding_series)
report.generate(output_path)
```

### 6. 多因子合成

当用户有多个因子（如动量、波动率、价值等），需要将这些因子合成为一个综合因子时使用。多因子合成包括共线性检测、正交化、加权、个股打分四个步骤，最终输出合成因子并对其做完整的有效性分析。

#### 6.1 准备多个因子

```python
# 假设有 3 个因子：ma5 偏离度、ma20 偏离度、换手率因子
ma5 = close.rolling(5).mean()
ma20 = close.rolling(20).mean()
factor_ma5 = (close - ma5) / ma5
factor_ma20 = (close - ma20) / ma20
factor_turnover = dp.get_kline(stock_list, begin_date, end_date, fields=['volume'])
factor_turnover = factor_turnover.droplevel(0, axis=1)  # 去掉 MultiIndex 层级

# 组装为字典
factors = {
    'ma5_deviation': factor_ma5,
    'ma20_deviation': factor_ma20,
    'volume': factor_turnover,
}
```

#### 6.2 一键多因子合成（推荐）

使用 `run_multi_factor_analysis()` 一键完成所有步骤：

```python
from scripts.run_analysis import run_multi_factor_analysis

run_multi_factor_analysis(
    factors=factors,                              # {因子名: 因子值 DataFrame}
    factor_names=['ma5', 'ma20', 'volume'],       # 因子名列表（决定合成顺序）
    close_price=close,
    benchmark_df=benchmark_df,
    market_cap=mc,
    output_path='multi_factor_report.html',
    group_num=5,
    ic_decay=20,
    weight_method='ic_mean',                      # 加权方法（见下方说明）
    use_orthogonal=True,                          # 是否进行正交化
)
```

#### 6.3 分步执行（高级用法）

如需对中间步骤进行精细控制，可手动编排流程：

```python
from AmazingData.factor_analysis import (
    FactorPreProcessing, ExtremeMethod, ScaleMethod, FillNanMethod,
    CollinearityAnalysis, FactorOrthogonalization, FactorWeighting,
    StockScorer,
)

# Step 1: 逐因子预处理
processed_factors = {}
for name, factor_raw in factors.items():
    fpp = FactorPreProcessing(factor_raw)
    fpp.extreme_processing({ExtremeMethod.MAD.value: {'median_multiple': 5}})
    fpp.scale_processing(ScaleMethod.Z_SCORE.value)
    fpp.fill_nan_processing(FillNanMethod.MEDIAN.value)
    processed_factors[name] = fpp.processed_data

# Step 2: 共线性检测
ca = CollinearityAnalysis(processed_factors)
ca.cal_correlation()          # 因子间相关系数矩阵
ca.cal_vif()                  # 方差膨胀因子 VIF
ca.cal_condition_number()     # 条件数
print(f"VIF: {ca.vif_df}")
print(f"条件数: {ca.condition_number}")

# Step 3: 因子正交化（消除共线性）
orthogonalized = processed_factors  # 默认使用原始因子
if ca.condition_number > 30 or any(ca.vif_df['VIF'] > 10):
    fa = FactorOrthogonalization(processed_factors)
    fa.orthogonalize(method='symmetric')  # symmetric(推荐)/schmidt/canonical
    orthogonalized = fa.orthogonalized_factors

# Step 4: 因子加权
fw = FactorWeighting()
fw.cal_weight(orthogonalized, method='ic_mean')  # 8 种方法可选
weights = fw.weights  # Dict[str, float]

# Step 5: 个股打分 → 合成因子
ss = StockScorer(orthogonalized, weights)
ss.calculate()
composite_factor = ss.composite_score  # pd.DataFrame (index=日期, columns=股票代码)

# Step 6: 对合成因子做单因子分析
from scripts.run_analysis import run_factor_analysis

run_factor_analysis(
    factor_raw=composite_factor,
    factor_name='multi_factor_composite',
    close_price=close,
    benchmark_df=benchmark_df,
    market_cap=mc,
    output_path='composite_report.html',
)
```

#### 6.4 加权方法说明

| 方法参数 | 说明 | 适用场景 |
|----------|------|----------|
| `equal_weight` | 等权平均，各因子权重 = 1/N | 因子信息量相近时 |
| `ic_mean` | 按各因子 IC 均值绝对值加权 | IC 稳定性较高时 |
| `ic_ir` | 按各因子 IC IR 加权，综合 IC 水平与稳定性 | 推荐，通用性强 |
| `max_ic` | 按各因子最佳 IC 值加权 | 期望因子周期性有效时 |
| `max_ic_ir` | 选 IC_IR 最高的因子赋权，其余清零 | 偏好单一最优因子 |
| `return_mean` | 按各因子年化收益率加权 | 因子的收益导向 |
| `return_half_life` | 按收益率半衰期加权 | 因子的持续导向 |
| `return_ir` | 按因子收益 IR 加权 | 收益与风险平衡 |

---

## 计算方法说明

> **详细算法公式、推导与判断标准见**: `references/factor_analysis_algorithms.md`  
> 该文件包含 12 章完整内容：理论框架 / 预处理 / IC分析 / 回归法 / 分层法 / 净值绩效 / 拥挤度 / 共线性 / 正交化 / 因子加权 / 个股评分 / 枚举常量表

### 快速参考 — 关键诊断阈值

| 检测项 | 阈值 | 含义 |
|--------|------|------|
| VIF | > 10 | 严重共线性 |
| 条件数 | > 30 | 矩阵接近奇异 |
| |T| > 2 占比 | 理想 > 40%，衡量因子显著性 |
| |IC| > 0.02 占比 | IC 显著预测比例 |
| 拥挤度分位 | ≥ 80% | 高度拥挤 |
| FSC | 接近 1 | 因子稳定 |

### 快速参考 — 预处理流水线

去极值(4种: STD/MAD/分位数/Boxplot) → 中性化(行业+市值OLS取残差) → 标准化(Min-Max/Z-Score/Rank) → 补空值(均值/中位数/行业均值)

### 快速参考 — 因子加权方法速查

| 方法 | 依赖 | 核心逻辑 |
|------|------|---------|
| `equal` | 无 | 等权 $1/K$ |
| `ic_mean` | IC | $\propto \overline{\mathrm{IC}}$ |
| `ic_half_life` | IC | 半衰加权 |
| `max_ic_ir` | IC | $\propto \Sigma^{-1} \mu$（推荐） |
| `max_ic` | IC+截面 | $\propto V_{\text{shrink}}^{-1} \mu$ |
| `return_mean` | 收益率 | $\propto \bar{f}$ |
| `return_ir` | 收益率 | $\propto \bar{f} / \sigma_f$ |

### 快速参考 — grep 定位

```bash
# 在 references/factor_analysis_algorithms.md 中搜索关键字：
grep -n "VIF\|条件数\|medcouple\|Ledoit\|FSC\|WLS\|IC_IR\|单调性" references/factor_analysis_algorithms.md
```

---

## 注意事项

1. 所有数据接口调用前必须先通过环境变量配置认证信息，然后调用`ad.login()`登录
2. 必须设置以下4个环境变量：`AD_USERNAME`、`AD_PASSWORD`、`AD_HOST`、`AD_PORT`
3. 账号、密码、IP和端口需联系开户营业部申请
4. `MarketData`实例化时必须传入交易日历：`ad.MarketData(base_data.get_calendar())`
5. 支持本地数据缓存（local_path + is_local）和指定日期范围（begin_date + end_date）两种模式，二选一
6. 股票数据最早可追溯至2013年，期货数据至2010年，期权数据至2015年
7. AmazingData限制单点登录，所以同一时间只能有一个AmazingData的登录链接
8. 本工具仅提供技术指标计算结果，不构成任何投资建议