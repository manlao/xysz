# 多因子分析算法参考手册



## 目录

1. [多因子模型理论框架](#1-多因子模型理论框架)
2. [因子数据预处理](#2-因子数据预处理)
3. [IC 分析 — 信息系数](#3-ic-分析--信息系数)
4. [回归法分析](#4-回归法分析)
5. [分层法分析](#5-分层法分析)
6. [净值绩效分析](#6-净值绩效分析)
7. [因子拥挤度分析](#7-因子拥挤度分析)
8. [因子共线性检测](#8-因子共线性检测)
9. [因子正交化](#9-因子正交化)
10. [因子加权合成](#10-因子加权合成)
11. [个股评分与选股](#11-个股评分与选股)
12. [附录：枚举常量表](#12-附录枚举常量表)

---

## 1. 多因子模型理论框架

### 1.1 理论演进

```
MPT (Markowitz, 1952)
  → 均值-方差优化，有效前沿
    → CAPM (Sharpe, 1964)
      → 单因子 β 定价模型
        → APT (Ross, 1976)
          → 多因子线性定价框架
            → Fama-French 三因子/五因子 (1993/2015)
              → Barra 结构化风险模型
                → 多因子选股体系
```

### 1.2 多因子模型的基本形式

设股票池有 N 只股票、K 个定价因子，则收益率的线性分解为：

$$R = X \cdot f + u$$

其中：
- $R$：$N \times 1$ 股票收益率向量
- $X$：$N \times K$ 因子载荷矩阵（暴露度）
- $f$：$K \times 1$ 因子收益率向量
- $u$：$N \times 1$ 特质收益率向量

**核心假设**：
1. $E[u] = 0$，特质收益均值为零
2. $\mathrm{Cov}(Xf, u) = 0$，因子收益与特质收益不相关
3. $\mathrm{Cov}(u_i, u_j) = 0 \ (i \neq j)$，不同股票特质收益不相关

### 1.3 风险结构

组合 $P$ 的风险可分解为：

$$\sigma_P^2 = w^T (X F X^T + \Delta) w$$

- $F$：$K \times K$ 因子收益率协方差矩阵
- $\Delta$：$N \times N$ 对角矩阵（特质风险）
- $w$：组合权重向量

---

## 2. 因子数据预处理

预处理流水线：**数据筛选 → 去极值 → 中性化 → 标准化 → 补空值**。

### 2.1 数据筛选 (`data_filter`)

按时间区间（`start` / `end`）和股票池（`stock_list`）过滤因子数据。

### 2.2 去极值 (`extreme_processing`)

消除因子值中的异常值干扰，实现于内部类 `_Extreme`。

#### 方法一：三倍标准差法 (STD)

对每个截面日独立计算：

$$\text{上限} = \mu + n \cdot \sigma, \quad \text{下限} = \mu - n \cdot \sigma$$

默认 $n = 3$。将超出区间的值截断到边界。适用于近似正态分布的因子，对偏态分布敏感。

**实现**：
```python
upper = mean + sigma_multiple * std
lower = mean - sigma_multiple * std
return data.clip(lower, upper, axis=0)
```

#### 方法二：MAD 法 (Median Absolute Deviation)

$$\text{上限} = \text{median} + n \cdot \text{MAD}, \quad \text{下限} = \text{median} - n \cdot \text{MAD}$$

$$\text{MAD} = \text{median}(|X_i - \text{median}(X)|)$$

默认 $n = 5$。MAD 是稳健的离差度量，对异常值不敏感，正态或低偏态分布均适用。

#### 方法三：分位数法 (Quantile)

$$X_i = \begin{cases} Q_{\alpha_{\min}}, & X_i < Q_{\alpha_{\min}} \\ X_i, & Q_{\alpha_{\min}} \le X_i \le Q_{\alpha_{\max}} \\ Q_{\alpha_{\max}}, & X_i > Q_{\alpha_{\max}} \end{cases}$$

默认 $\alpha_{\min} = 0.025$、$\alpha_{\max} = 0.975$。

#### 方法四：Boxplot 法（含 medcouple 偏度调整）

标准 Boxplot（Tukey, 1977）：

$$[Q_1 - 1.5 \cdot \mathrm{IQR}, \ Q_3 + 1.5 \cdot \mathrm{IQR}], \quad \mathrm{IQR} = Q_3 - Q_1$$

**偏度调整**（Hubert & Vandervieren, 2007）：引入 medcouple (MC) 偏度统计量（Brys et al., 2004）：

$$\mathrm{MC} = \underset{x_i \le m \le x_j}{\mathrm{median}} \frac{(x_j - m) - (m - x_i)}{x_j - x_i}$$

其中 $m$ 为样本中位数。调整后的上下界：

$$\begin{aligned}
\text{下限} &= Q_1 - 1.5 \cdot e^{a_{\min} \cdot \mathrm{MC}} \cdot \mathrm{IQR} \\
\text{上限} &= Q_3 + 1.5 \cdot e^{a_{\max} \cdot \mathrm{MC}} \cdot \mathrm{IQR}
\end{aligned}$$

| MC 正负 | $a_{\min}$ | $a_{\max}$ |
|---------|------------|------------|
| MC < 0  | -4.0 | 3.5 |
| MC ≥ 0  | -3.5 | 4.0 |

右偏时上限自适应抬高，左偏时下限自适应降低。

### 2.3 中性化 (`neutralize_processing`)

对每个交易日截面做 OLS 回归，以因子值为被解释变量，行业哑变量和/或流通市值为解释变量，**取残差**作为中性化后的因子值。

$$\tilde{X}_i = X_i - \hat{X}_i$$

内部类 `_Neutralize` 逐截面迭代执行 `sm.OLS(y, X)` → `fit.resid`。

### 2.4 标准化 (`scale_processing`)

| 方法 | 公式 | 输出分布 |
|------|------|---------|
| Min-Max | $X_i' = \frac{X_i - X_{\min}}{X_{\max} - X_{\min}}$ | $[0, 1]$ |
| Z-score | $X_i' = \frac{X_i - \mu}{\sigma}$ | $\mathcal{N}(0, 1)$ |
| Rank 百分位 | $X_i' = \frac{\mathrm{rank}(X_i)}{N_{\text{valid}}}$ | $\mathcal{U}[0, 1]$ |

Rank 方法最为稳健，不受极端值影响。

### 2.5 补空值 (`fill_nan_processing`)

| 方法 | 说明 |
|------|------|
| 截面均值 | 用当日所有股票因子值的均值填充 NaN |
| 截面中位数 | 用当日所有股票因子值的中位数填充 NaN |
| 行业均值 | 用当日同行业股票因子值的均值填充 NaN |

**注意**：空值占比较高的因子不适合用统计方法补值，建议从数据源头解决。

---

## 3. IC 分析 — 信息系数

### 3.1 定义

IC（Information Coefficient）衡量因子暴露度与未来收益之间的相关性：

$$\mathrm{IC}_T^{(N)} = \mathrm{corr}\big(Factor_T, \ Return_{T+N}\big)$$

- $T$：观测期
- $N$：滞后周期（默认计算 delay_1 到 delay_20）

### 3.2 计算方法

#### Spearman 秩相关系数 (RankIC) — **推荐**

$$r_s = 1 - \frac{6\sum d_i^2}{n(n^2 - 1)}$$

其中 $d_i$ 为两变量排序后的秩差，对异常值稳健。

#### Pearson 相关系数 (NormalIC)

$$r_p = \frac{\sum (x_i - \bar{x})(y_i - \bar{y})}{\sqrt{\sum (x_i - \bar{x})^2 \sum (y_i - \bar{y})^2}}$$

### 3.3 IC 衰减 (IC Decay)

计算因子在 T 期与 T+1、T+2、...、T+N 期收益的相关系数序列，观察随滞后增大 IC 的衰减速率。衰减越慢，因子持续性越好。

**实现优化**：预计算所有 delay 周期的收益率矩阵（`stock_return_dict`），避免重复 `pct_change().shift()`。

### 3.4 IC 评价指标体系（12 项）

| 序号 | 指标 | 公式/说明 |
|------|------|----------|
| 1 | IC 均值 | $\overline{\mathrm{IC}} = \frac{1}{n}\sum_t \mathrm{IC}_t$ |
| 2 | IC 标准差 | $\sigma_{\mathrm{IC}}$ |
| 3 | IC IR | $\mathrm{IR} = \overline{\mathrm{IC}} / \sigma_{\mathrm{IC}}$（信息比率，关键指标） |
| 4 | IC > 0 占比 | 正向预测比例 |
| 5 | \|IC\| > 0.02 占比 | 显著预测比例 |
| 6 | IC 偏度 | IC 分布对称性 |
| 7 | IC 峰度 | IC 分布尾部特征 |
| 8 | 正相关显著比例 | p-value < 0.05 的比例 |
| 9 | 负相关显著比例 | 1 - 正相关显著比例 |
| 10 | 方向切换比例 | $\mathrm{sign}(\mathrm{IC}_t) \neq \mathrm{sign}(\mathrm{IC}_{t-1})$ 的频率 |
| 11 | 同向比例 | 1 - 方向切换比例 |

---

## 4. 回归法分析

### 4.1 WLS 回归模型

对每个交易日截面，建立 WLS 回归：

$$r_{i,T+1} = \alpha + \beta_f \cdot X_{i,T} + \sum_{k} \beta_k \cdot D_{ik} + \beta_{mv} \cdot MV_i + \varepsilon_i$$

其中 $r_{i,T+1}$ 为 T+1 期收益率，$X_{i,T}$ 为 T 期因子暴露度，$D_{ik}$ 为行业哑变量，$MV_i$ 为流通市值。

$\beta_f$ 即**因子收益率**（核心输出）。

### 4.2 权重设定（消除异方差）

$$w_i = \frac{1}{MV_i} \quad \text{或} \quad w_i = \sqrt{MV_i}$$

使用 `statsmodels` 的 `sm.WLS(y, X, weights=weights)`。

### 4.3 因子收益率净值

**累加净值 (cumsum)**：$\mathrm{NAV}_t = 1 + \sum_{s=1}^{t} \hat{f}_s$  
**累乘净值 (cumprod)**：$\mathrm{NAV}_t = \prod_{s=1}^{t} (1 + \hat{f}_s)$

### 4.4 T 值统计

| 指标 | 标准 |
|------|------|
| T 值均值 | — |
| \|T\| > 2 占比 | 理想 > 40% |

|T| > 2 表示 95% 置信水平下因子对收益的影响显著。

### 4.5 自相关分析 (ACF/PACF)

检验因子日收益率的自相关性：

$$\rho_k = \frac{\mathrm{Cov}(\hat{f}_t, \hat{f}_{t-k})}{\mathrm{Var}(\hat{f}_t)}$$

### 4.6 因子自稳定性系数 (FSC)

$$\mathrm{FSC} = 1 - \frac{\operatorname{Var}(r)}{\operatorname{Var}(\lvert r \rvert)} \in [0, 1]$$

FSC 越接近 1，因子收益越稳定。

---

## 5. 分层法分析

### 5.1 基本流程

每个截面日按因子值排序等分为 G 组（默认 5 组），构建各组等权组合。

| 分组 (ascending=False) | 含义 |
|------------------------|------|
| group_0 (G0) | 因子值最大（多头） |
| group_1-3 | 中间组 |
| group_4 (G4) | 因子值最小（空头） |

### 5.2 向量化回测引擎

传统方法逐日循环 O(T×N×G)，本引擎矩阵运算 O(T×N)：

**Step 1**：构建权重矩阵 $W_g$ (T×N)，$w_{t,i}^{(g)} = 1/N_g^{(t)}$ 当 i 在组 g，否则 0。

**Step 2**：收益率矩阵 $R_{t,i} = P_{t+1,i}/P_{t,i} - 1$。

**Step 3**：向量化组收益率 $r_t^{(g)} = \sum_i w_{t,i}^{(g)} \cdot R_{t,i}$

**Step 4**：净值 $\mathrm{NAV}_t^{(g)} = \prod_{s=1}^{t} (1 + r_s^{(g)})$

### 5.3 换手率分析

**个数法**：$\frac{\#\{\text{股票变化}\}}{\#\{\text{组内股票}\}} \times 100\%$  
**权重法**：$\frac{1}{2} \sum_i |w_{t,i} - w_{t-1,i}| \times 100\%$

### 5.4 买入信号衰减与反转

**衰减**：G0 组股票在后续仍留在 G0 的比例，衰减越慢 → 持续性越好  
**反转**：G0 组股票变为 GN 组的比例，反转越小越好

### 5.5 多空组合

$\mathrm{NAV}_t^{\text{LS}} = \prod_{s=1}^{t} (1 + r_s^{\text{G0}} - r_s^{\text{GN}})$

多空净值持续向上说明因子区分度高。

### 5.6 单调性检验

检验 G0 → GN 各组年化收益是否单调。计算秩相关系数 `rank_corr`，越接近 ±1 说明因子单调性越好。

---

## 6. 净值绩效分析

对净值序列计算全面绩效指标。

### 6.1 核心指标

| 指标 | 公式 |
|------|------|
| 年化收益率 | $(\mathrm{NAV}_T / \mathrm{NAV}_1)^{252/n} - 1$ |
| 年化波动率 | $\sigma_{\text{daily}} \times \sqrt{252}$ |
| 夏普比率 | $(R_{\text{annual}} - r_f) / \sigma_{\text{annual}},\ r_f = 2\%$ |
| 最大回撤 | $\min_t (\mathrm{NAV}_t - \max_{s\le t} \mathrm{NAV}_s) / \max_{s\le t} \mathrm{NAV}_s$ |
| Calmar 比率 | $R_{\text{annual}} / |\text{MDD}|$ |
| 索提诺比率 | 仅计入下行波动的风险调整收益 |
| 日/月胜率 | 正收益天数/月数占比 |
| 偏度/峰度 | 日收益率的偏度和峰度 |
| FSC（因子自稳定性系数） | $1 - \operatorname{Var}(r) \,/\, \operatorname{Var}(\lvert r \rvert)$ |

### 6.2 与基准比较（可选）

| 指标 | 说明 |
|------|------|
| 超额年化收益 | $R_{\text{annual}} - R_{\text{benchmark}}$ |
| 跟踪误差 | $\sigma(r - r_{\text{bm}}) \times \sqrt{252}$ |
| 信息比率 | $\bar{r}_{\text{excess}} \cdot \sqrt{252} / \sigma_{\text{excess}}$ |
| Beta | $\mathrm{Cov}(r, r_{\text{bm}}) / \mathrm{Var}(r_{\text{bm}})$ |
| Alpha (詹森指数) | $R_{\text{annual}} - [r_f + \beta (R_{\text{bm}} - r_f)]$ |
| 特雷诺比率 | $(R_{\text{annual}} - r_f) / \beta$ |

### 6.3 日收益率分布

12 档：-10%以下、-10%~-5%、-5%~-3%、-3%~-2%、-2%~-1%、-1%~0%、0%~1%、1%~2%、2%~3%、3%~5%、5%~10%、10%以上。

---

## 7. 因子拥挤度分析

### 7.1 五项拥挤度指标

| 指标 | 计算方法 | 拥挤信号 |
|------|---------|---------|
| 估值价差 | 空头-多头市值分位数差 | 价差扩大→拥挤 |
| 配对相关性 | 多头组内股票收益率两两相关系数均值 | 相关性升高→拥挤 |
| 长期收益反转 | 多头长期收益(120日) - 近期收益(20日) | 正值(回落)→拥挤 |
| 因子波动率 | 多空收益差的滚动标准差 | 波动放大→拥挤 |
| 复合拥挤度 | 四指标 Z-score 等权平均 | 综合判断 |

### 7.2 拥挤度水平判断

基于复合拥挤度的历史分位数：

| 分位 | 水平 | 含义 |
|------|------|------|
| ≥ 80% | `high` | 高度拥挤 |
| ≥ 60% | `warn` | 值得警惕 |
| < 60% | `normal` | 正常 |

---

## 8. 因子共线性检测

### 8.1 相关系数矩阵

因子间截面相关系数的时间维度均值 $\bar{\rho}_{ij} = \frac{1}{T} \sum_t \rho_{ij}^{(t)}$。

### 8.2 方差膨胀因子 (VIF)

$$\mathrm{VIF}_j = \frac{1}{1 - R_j^2}, \quad R_j^2 \text{ 来自 } X_j = \alpha + \sum_{k \neq j} \beta_k X_k + \varepsilon$$

**判断标准**：VIF < 5 可接受 | 5~10 中等共线 | >10 严重共线

### 8.3 条件数 (Condition Number)

$$\kappa(A) = \frac{\sigma_{\max}(A)}{\sigma_{\min}(A)}$$

**判断标准**：κ < 30 可接受 | 30~100 中等共线 | ≥ 100 严重共线

---

## 9. 因子正交化

### 9.1 数学框架

目标：找到变换矩阵 $T_{K \times K}$，使 $X_{\text{orth}} = T \cdot X$（各行互不相关）。

### 9.2 对称正交 (Symmetric) — **推荐**

正交后因子与原始因子最相似，不依赖因子输入顺序。

1. 协方差矩阵：$M = (N-1) \cdot \mathrm{Cov}(X)$
2. 特征分解：$M = V \Lambda V^T$
3. 过渡矩阵：$T = V \Lambda^{-1/2} V^T$
4. $X_{\text{orth}} = T \cdot X$

验证：$M_{\text{orth}} = T M T^T = I$。

### 9.3 施密特正交 (Gram-Schmidt)

结果依赖因子输入顺序。对行向量做经典 Gram-Schmidt 过程，最后保持原始标准差缩放。

### 9.4 规范正交 (Canonical)

$T = V \Lambda^{-1/2}$（不含右侧 $V^T$），正交后与原因子相似性不如对称正交。

---

## 10. 因子加权合成

合成因子：$X_{\text{composite}} = \sum_{k=1}^{K} w_k \cdot X_k$，合成后 Min-Max 归一化至 $[0,1]$。

### 10.1 八种加权方法

#### (1) 等权法 (Equal)
$$w_k = 1/K$$

#### (2) 历史收益率均值法 (Return Mean)
$$w_k^{(t)} \propto \bar{f}_k^{(t)} = \frac{1}{\text{window}} \sum_{s} f_{k,s}$$

#### (3) 历史收益率半衰法 (Return Half-Life)
$$w_k^{(t)} \propto \sum_{s} \lambda^{t-s} \cdot f_{k,s}, \quad \lambda = (0.5)^{1/H}$$

#### (4) 历史收益率 IR 法 (Return IR)
$$w_k^{(t)} \propto \frac{\bar{f}_k^{(t)}}{\sigma_{f,k}^{(t)}}$$

#### (5) 历史 IC 均值法 (IC Mean)
$$w_k^{(t)} \propto \overline{\mathrm{IC}}_k^{(t)}$$

#### (6) 历史 IC 半衰法 (IC Half-Life)
$$w_k^{(t)} \propto \sum_{s} \lambda^{t-s} \cdot \mathrm{IC}_{k,s}$$

#### (7) 最大化 IC_IR 法 (Max IC_IR) — **推荐**

优化目标：
$$\max_w \frac{w^T \mu}{\sqrt{w^T \Sigma w}}$$

**解析解**：$w^* \propto \Sigma^{-1} \cdot \mu$

其中 $\mu$ 为 IC 均值向量，$\Sigma$ 为 IC 协方差矩阵。

```python
mu = window_data.mean().values
cov = window_data.cov().values
w = np.linalg.inv(cov) @ mu
w = w / np.sum(np.abs(w))
```

#### (8) 最大化 IC 法 (Max IC)

优化目标：
$$\max_w w^T \mu, \quad \text{s.t. } w^T V w = 1$$

**解析解**：$w^* \propto V^{-1} \cdot \mu$

**关键区别**：$V$ 是**截面因子值**的相关系数矩阵（非 IC 协方差），并采用 **Ledoit-Wolf 压缩估计**：

$$V_{\text{shrink}} = (1 - \delta) \cdot V + \delta \cdot I, \quad \delta = 0.2$$

向单位矩阵收缩以减少估计误差。

### 10.2 方法选择建议

| 场景 | 推荐方法 |
|------|---------|
| 缺乏历史数据 | 等权法 |
| 因子表现稳定 | IC 均值法 |
| IC 近期趋势重要 | IC 半衰法 |
| 最优统计性质 | Max IC_IR（推荐） |
| 同时考虑截面相关性 | Max IC |
| 以因子收益率驱动 | Return IR 法 |

---

## 11. 个股评分与选股

### 综合得分

$$S_i^{(t)} = \sum_{k=1}^{K} w_k \cdot X_{k,i}^{(t)}$$

每期按得分降序选取前 N 只。

### 完整多因子选股流程

```
因子数据 → [预处理] → [IC分析初筛] → [共线性检测] → [正交化（如需）] → [因子加权] → [个股评分] → [Top-N选股]
```

---

## 12. 附录：枚举常量表

### 去极值方法 (ExtremeMethod)

| 枚举值 | 说明 | 默认参数 |
|--------|------|---------|
| `std` | 标准差法 | `sigma_multiple=3` |
| `mad` | MAD 法 | `median_multiple=5` |
| `quantile` | 分位数截断 | `quantile_min=0.025, max=0.975` |
| `box_plot` | Boxplot + medcouple | `quantile_min=0.25, max=0.75` |

### 标准化方法 (ScaleMethod)

| 枚举值 | 输出分布 |
|--------|---------|
| `min_max` | $[0, 1]$ |
| `z_score` | $\mathcal{N}(0, 1)$ |
| `rank` | $\mathcal{U}[0, 1]$ |

### 补空值方法 (FillNanMethod)

| 枚举值 | 说明 |
|--------|------|
| `mean` | 截面均值 |
| `median` | 截面中位数 |
| `industry_mean` | 行业均值 |

### 中性化方法 (NeutralizeMethod)

| 枚举值 | 说明 |
|--------|------|
| `industry` | 行业哑变量 OLS 取残差 |
| `market_value` | 流通市值 + 行业 OLS 取残差 |

### 加权方法 (WeightMethod)

| 枚举值 | 依赖数据 | 说明 |
|--------|---------|------|
| `equal` | 无 | 等权 |
| `return_mean` | 因子收益率 | 滚动均值 |
| `return_half_life` | 因子收益率 | 半衰加权 |
| `return_ir` | 因子收益率 | 收益/标准差 |
| `ic_mean` | IC 序列 | IC 均值 |
| `ic_half_life` | IC 序列 | IC 半衰 |
| `max_ic_ir` | IC 序列 | 最大化 IC_IR 解析解 |
| `max_ic` | IC + 截面因子 | 最大化 IC + 压缩估计 |

### 正交化方法 (OrthogonalMethod)

| 枚举值 | 特点 |
|--------|------|
| `symmetric` | **推荐**，正交后与原因子最相似 |
| `gram_schmidt` | 依赖因子顺序 |
| `canonical` | 规范正交 |

### 分组方向 (GroupMethod)

| 枚举值 | 说明 |
|--------|------|
| `ascending` | 因子值从小到大 |
| `descending` | 因子值从大到小 |

