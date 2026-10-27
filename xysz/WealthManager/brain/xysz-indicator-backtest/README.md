# Xysz Multi Indicator Backtest

试金——把指标变成信号、把信号变成组合、把组合变成可检验净值的老教练，策略真伪一测便知。

## 类型

Agent 型（单个 AI 专家）

## 功能

- **三层回测链路**：单股层（每个指标独立生成买卖信号）→ 组合层（多指标合成或截面排名选股）→ 撮合层（逐日执行、计入全成本、产出双净值）
- **三种信号规则**：pos（值正持有）、cross（上穿 0 买入/下穿 0 卖出）、band（低于低值买入/高于高值卖出），事件信号沿时间轴补全为持仓状态
- **四种合成方式**：vote 投票（过半买入）、union 并集（一票否决最严格）、mean 均值；或 rank 调仓日截面排名选股（支持等权/波动率倒数/市值加权）
- **全成本撮合**：逐日卖出→重算持仓→买入三步，处理涨跌停、停牌、退市约束，计入佣金、印花税、过户费与滑点，输出含成本与不含成本双净值
- **完整业绩评估**：收益/风险/相对基准/风险调整/收益分布五类 20+ 指标（含最大回撤起止日期），对比沪深300基准，自动生成 fresh-light HTML 报告
- **单股信号诊断**：K 线主图（MA5/10/20/60 + 买卖标记）+ 各指标信号副图 + 投票/并集综合信号副图（ECharts 交互）
- 数据来源仅限星耀数智 Skills：ad-indicator-validation（回测引擎）、ad-technical-analysis（56 技术指标）、ad-fundamental-analysis（90 基本面指标）、ad-strategy-performance（业绩分析）、ad-pattern-hunter（34 类形态）、ad-api（原始数据）

## 使用示例

- 用 MACD 与 RSI 对沪深300成分股做多指标回测，对比投票与并集两种合成方式，输出含成本净值与夏普比率
- 回测一个月度调仓的动量+低波动选股策略（Top20 等权），给出年化收益、最大回撤与完整业绩报告
- 检查一只股票（600***.SH）MACD 金叉信号近两年的表现，生成单股信号可视化诊断图

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
| `ad-fundamental-analysis` | 90 项 A 股基本面指标（盈利/成长/营运/盈余/安全/估值） |
| `ad-indicator-validation` | 指标有效性验证：单股信号 → 多指标合成 → 组合撮合 → 双净值 |
| `ad-pattern-hunter` | K 线形态识别引擎（34 类形态 × 13 周期） |
| `ad-strategy-performance` | 策略净值业绩评估（收益/风险/基准/调整后收益） |
| `ad-technical-analysis` | 56 项 A 股技术面指标计算 |


## 安装

将专家包目录放到 WorkBuddy 的专家插件目录（plugins/marketplaces/my-experts/plugins/）下，保持目录名不变：

```
xysz-indicator-backtest/
```

然后运行注册命令使其可见：

```bash
python3 scripts/register_expert.py <expert-dir>
```
