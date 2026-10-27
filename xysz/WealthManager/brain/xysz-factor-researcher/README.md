# 宽客 · 星耀数智量化因子研究员（xysz-factor-researcher）

一条完整的股票量化策略流水线：**取数 → 因子构造 → 单因子检验 → 多因子合成与筛选 → 策略回测 → 业绩评估**。因子值由基本面（90 项）与技术面（56 项）指标 skill 联动供给，检验与合成由因子分析引擎承接，回测与业绩报告由回测、业绩分析 skill 完成。数据全部来自星耀数智 Skills，不使用任何外部行情/财经数据源。

## 类型

Agent 型（单个 AI 专家）

## 量化策略研究工作流（7 步串联）

> 每一步的产出物就是下一步的输入；用户只要求其中一段时，从对应步骤进入。

| 步骤 | 层级 | 使用的 Skill | 产出 |
|------|------|-------------|------|
| 1. 获取历史行情与因子数据 | 获取层 | `ad-api` | 价格面板、因子面板（HDF5）、基准与市值数据 |
| 2. 构造候选因子 | 因子层 | `ad-technical-analysis` + `ad-fundamental-analysis` | 技术类（动量/波动率/趋势/量价）+ 基本面类（价值/质量/成长/估值）候选因子 |
| 3. 单因子检验 | 检验层 | `ad-factor-analysis` | 因子有效性报告（IC/回归/分层/拥挤度）+ 中间结果 CSV |
| 4. 多因子合成 | 合成层 | `ad-factor-analysis` | 共线性检测 → 正交化 → 8 种加权 → 合成因子（复检） |
| 5. 多因子筛选 | 筛选层 | `ad-factor-analysis` | 有效因子子集 + 合成因子得分排序 |
| 6. 策略回测执行 | 回测层 | `ad-indicator-validation` | 含成本/不含成本双净值 + 完整交易日志 |
| 7. 业绩评估与报告 | 报告层 | `ad-strategy-performance` | 20+ 指标（胜率/CAGR/夏普/最大回撤）+ HTML 业绩报告 |

### 数据来源（铁律）

| 环节 | 使用的 Skill |
|---------|-------------|
| 原始数据（K 线/股票池/基准/市值/财报） | `ad-api` |
| 技术类因子构造（56 指标） | `ad-technical-analysis` |
| 基本面因子构造（90 指标） | `ad-fundamental-analysis` |
| 因子分析引擎（检验/合成/筛选/报告） | `ad-factor-analysis` |
| 策略回测引擎（信号/合成/撮合/双净值） | `ad-indicator-validation` |
| 策略业绩评估（20+ 指标/HTML 报告） | `ad-strategy-performance` |

## 使用示例

- 开发并验证一个多因子选股策略：用基本面与技术面因子构造候选池，完成单因子检验、IC_IR加权合成与筛选，对沪深300成分股回测，输出含夏普比率与最大回撤的完整业绩报告
- 检验动量因子在沪深300成分股上的有效性：IC分析、分组回测与拥挤度诊断，输出完整因子有效性报告
- 对比双均线交叉策略与多因子选股策略近三年的表现：含成本净值、胜率、CAGR、最大回撤与完整业绩报告

## 头像

头像已自动生成在 `avatars/` 目录下。如需替换为自定义头像，要求：
- 格式：PNG（推荐）或 JPG
- 尺寸：512×512 px
- 大小：单张不超过 500KB

## 内置技能

本专家包自带以下 Skill（位于 `skills/` 目录），安装后无需额外下载即可调用：

| Skill | 能力 |
|-------|------|
| `ad-api` | 星耀数智金融数据 API：三张报表、行情、股东、公告等原始数据 |
| `ad-factor-analysis` | 因子有效性分析（IC/回归/分层/拥挤度）与多因子合成 |
| `ad-fundamental-analysis` | 90 项 A 股基本面指标（盈利/成长/营运/盈余/安全/估值） |
| `ad-indicator-validation` | 指标有效性验证：单股信号 → 多指标合成 → 组合撮合 → 双净值 |
| `ad-strategy-performance` | 策略净值业绩评估（收益/风险/基准/调整后收益） |
| `ad-technical-analysis` | 56 项 A 股技术面指标计算 |


## 安装

将专家包目录放到专家目录下（相对 WorkBuddy 配置目录 `~/.workbuddy/`）：

```
plugins/my-experts/plugins/xysz-factor-researcher/
```

然后运行注册命令使其可见：

```bash
python3 scripts/register_expert.py <expert-dir>
```

## 打包分享

```bash
zip -r xysz-factor-researcher.zip xysz-factor-researcher/
```
