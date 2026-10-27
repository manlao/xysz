# 场景胶囊录入对照表（21 个）

> 用途：场景胶囊的真实 JSON schema 平台未导出（导出里 `scenes: []` 为空），`industry-config.json` 里的字段名是按表单推断的。**若导入后胶囊为空，按本表在平台表单逐个录入**。表单字段：英文名称*、图标（SVG≥48px，可空）、绑定专家、绑定技能（多选，用户不可见）、系统提示词（用户不可见）、提示词模板*（4-10 个，模板标题中文≤8字+英文≤30，提示词指令中英）。

## mode_0 财富规划（5 个）

### 1. 家庭风险测评 / Risk Assessment
- 绑定专家：稳舵（xysz-asset-allocation）
- 绑定技能：星耀数智金融数据、星耀数智资产配置
- 系统提示词：你是家庭财务风险测评顾问。先采集用户收入、负债、家庭责任与存量可投资产信息，风险承受力只按存量可投资产计算，回本时间超过24个月要降档。输出风险档位、可承受最大回撤与最大亏损金额。仅供研究参考，不构成投资建议。
- 模板：
  | 标题 | EN | 提示词指令 |
  |---|---|---|
  | 风险测评 | Risk check | 我的家庭收入、负债与资产情况如下，帮我评估风险承受档位 |
  | 回撤预算 | Drawdown budget | 根据我的存量资产和行为容忍度，计算我能承受的最大回撤与亏损金额 |
  | 应急储备 | Emergency fund | 帮我计算家庭应急储备金应该留多少 |
  | 回本时间 | Recovery time | 如果发生最大回撤，我的家庭需要多久能靠月结余回本 |

### 2. 大类资产配置 / Asset Allocation
- 绑定专家：稳舵　- 绑定技能：金融数据、资产配置
- 系统提示词：你是大类资产配置顾问。围绕黄金、国债、宽基、现金资产池给出配置方案，支持固定权重、均值方差、风险平价与BL模型，并用历史回测验证。展示结果时须说明这是历史数据环境的机械结果。仅供研究参考，不构成投资建议。
- 模板：配置方案/Allocation、模型对比/Model compare、历史回测/Backtest、BL观点/BL views（指令见 industry-config.json）

### 3. ETF定投测算 / ETF DCA Calculator
- 绑定专家：长流（xysz-etf-dca）　- 绑定技能：金融数据、ETF定投计算器
- 系统提示词：你是ETF定投测算顾问。支持正向测算、历史回测与目标金额、收益、期限反推，基于真实ETF行情并计入佣金与取整损耗。目标反推须先做通胀折算、扣除存量本金再对缺口测算。仅供研究参考，不构成投资建议。
- 模板：正向测算/Projection、历史回测/Backtest、目标反推/Goal solving、期限反推/Horizon solving

### 4. 定投计划书 / DCA Plan
- 绑定专家：长流　- 绑定技能：金融数据、ETF定投计算器
- 系统提示词：你是定投计划规划师。把测算结果整理成可执行的定投计划：标的、频率、金额、预期区间与风险提示，可输出可视化HTML报告。仅供研究参考，不构成投资建议。
- 模板：制定计划/Make plan、调整金额/Adjust amount、计划体检/Plan review、输出报告/Report

### 5. 自选股关注池 / Watchlist
- 绑定专家：稳舵　- 绑定技能：金融数据、自选股管理
- 系统提示词：你是自选股管理助手。帮用户维护自选股分组与标的，支持单只或批量增减、个股检索，并自动生成带行情与基本面数据的展示页。
- 模板：添加自选/Add stock、查看自选/View list、整理分组/Organize、批量导入/Batch add

## mode_1 深度分析（5 个）

### 1. 财务分析 / Fundamental Analysis → 财探（xysz-financial-detective）
- 技能：金融数据、基本面指标、公告搜索
- 模板：三表解读/Statements、利润质量/Earnings quality、现金流/Cash flow、同行对比/Peer compare

### 2. 技术分析 / Technical Analysis → 盘眼（xysz-chart-eye）
- 技能：金融数据、技术面指标
- 模板：趋势研判/Trend、指标体检/Indicators、支撑压力/Levels、背离识别/Divergence

### 3. 风险排查 / Risk Screening → 风探（xysz-risk-officer）
- 技能：金融数据、基本面指标、公告搜索
- 模板：风险扫描/Risk scan、减持解禁/Unlock plan、业绩风险/Earnings risk、空头清单/Bear case

### 4. 市场观点 / Market Intelligence → 风哨（xysz-market-intel-officer）
- 技能：公告搜索、研报摘要、智读新闻
- 模板：情报速览/Intel brief、机构预期/Consensus、舆情分析/Sentiment、预期差/Expectation gap

### 5. 个股全景体检 / Full Diagnosis → 财探（财探做组长视角）
- 技能：金融数据、基本面指标、技术面指标、公告搜索、智读新闻、研报摘要（全6个）
- 模板：全景体检/Full check、多头论证/Bull thesis、多空会诊/Committee、月度跟踪/Tracking

## mode_2 量化策略（6 个）

### 1. 单因子分析 / Single Factor → 宽客（xysz-factor-researcher）
- 技能：金融数据、基本面指标、技术面指标、因子分析
- 模板：构建因子/Build factor、有效性检验/IC test、拥挤度/Crowding、输出报告/Report

### 2. 多因子合成 / Factor Synthesis → 宽客
- 模板：共线性/Collinearity、正交化/Orthogonalize、加权合成/Weighting、打分排名/Scoring

### 3. 多因子筛选 / Factor Screening → 宽客
- 模板：构建股票池/Stock pool、条件叠加/Conditions、池内监控/Monitor、池回测/Validate

### 4. 形态捕手 / Pattern Hunter → 试金（xysz-indicator-backtest）
- 技能：金融数据、形态猎手
- 模板：形态雷达/Pattern radar、手绘匹配/Sketch match、单票诊断/Diagnosis、周期切换/Timeframe

### 5. 条件筛选 / Condition Screen → 试金
- 技能：金融数据、技术面指标、基本面指标
- 模板：技术选股/Technical、基本选股/Fundamental、组合条件/Combined、候选清单/Export

### 6. 多指标策略回测 / Multi-Indicator Backtest → 试金
- 技能：金融数据、多指标策略回测、策略业绩分析
- 模板：信号合成/Signal synth、组合回测/Backtest、业绩报告/Performance、参数寻优/Tuning

## mode_3 模拟交易（5 个）

### 1. 模拟买入 / Simulated Buy → 弈者（xysz-sim-trade）
- 技能：金融数据、模拟交易
- 模板：按量买入/Buy shares、按金额买入/Buy amount、限价挂单/Limit order、委托确认/Confirm

### 2. 模拟卖出 / Simulated Sell → 弈者
- 模板：卖出持仓/Sell position、部分卖出/Partial sell、止盈挂单/Take profit、清仓确认/Liquidate

### 3. 查模拟账户 / Account Query → 弈者
- 模板：查资金/Funds、查持仓/Positions、查委托/Orders、查成交/Fills

### 4. 撤单管理 / Order Management → 弈者
- 模板：全部撤单/Cancel all、撤指定单/Cancel one、委托体检/Order review、改价重挂/Re-price

### 5. 绩效复盘 / Performance Review → 弈者
- 技能：金融数据、模拟交易、策略业绩分析
- 模板：净值曲线/NAV curve、收益分析/Returns、交易复盘/Trade review、对比基准/vs benchmark

---

## 图标建议

表单"图标"项要求 SVG ≥48×48，可选配。建议按模式区分色相：财富规划（金）、深度分析（蓝）、量化策略（紫）、模拟交易（红）；同模式内胶囊用同色系不同线条图形（如风险测评=盾、配置=饼图、买入=↑、卖出=↓）。

## 示例代码说明

模板指令中的股票代码均为脱敏占位（600***.SH / 510***.SH），用户实际使用时替换为真实代码即可，无需改动。
