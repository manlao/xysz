---
name: ad-indicator-validation
display_name: 星耀数智指标验证
display_name_en: Xingyao Indicator Validation
version: 0.3.0
author: 中国银河证券
agent_created: true
description: "中国银河证券星耀数智指标验证技能。用历史回测验证指标的真实有效性——从单股信号到组合模型的完整验证链路。单股层——每个指标独立生成买卖信号,支持位置型(值正持有)、穿越型(上穿零轴买入)、阈值型(超买超卖区间触发)三种规则,事件信号沿时间轴补全为持仓状态;组合层——多指标信号经投票(过半)、并集(全部持有才持有,任一空仓立即卖出)或均值合成,也可在调仓日做截面排名选股,按目标持仓数或份数口径、等权/波动率倒数/市值加权构建组合;撮合层——逐日执行卖出、重算持仓、买入三步,处理涨跌停、停牌、退市约束,计入佣金、印花税、过户费与滑点,输出含成本与不含成本双净值,直接判断单个指标或多指标组合能否带来超额收益。指标值由技术面/基本面指标 skill 联动提供(HDF5 或 CSV 指标面板),双净值可对接策略业绩分析生成完整绩效报告。涉及指标有效性验证、单股信号回测、多指标合成、组合回测、排名选股、交易成本测算等场景时使用。"
description_zh: "中国银河证券星耀数智指标验证技能。用历史回测验证指标的真实有效性——从单股信号到组合模型的完整验证链路。单股层——每个指标独立生成买卖信号,支持位置型(值正持有)、穿越型(上穿零轴买入)、阈值型(超买超卖区间触发)三种规则,事件信号沿时间轴补全为持仓状态;组合层——多指标信号经投票(过半)、并集(全部持有才持有,任一空仓立即卖出)或均值合成,也可在调仓日做截面排名选股,按目标持仓数或份数口径、等权/波动率倒数/市值加权构建组合;撮合层——逐日执行卖出、重算持仓、买入三步,处理涨跌停、停牌、退市约束,计入佣金、印花税、过户费与滑点,输出含成本与不含成本双净值,直接判断单个指标或多指标组合能否带来超额收益。指标值由技术面/基本面指标 skill 联动提供(HDF5 或 CSV 指标面板),双净值可对接策略业绩分析生成完整绩效报告。涉及指标有效性验证、单股信号回测、多指标合成、组合回测、排名选股、交易成本测算等场景时使用。"
description_en: "China Galaxy Securities Xingyao indicator validation skill. Validates real indicator effectiveness through historical backtesting, from per-stock signals to portfolio modeling. Stock level: each indicator independently generates buy/sell signals via three rule templates (position, cross, band) with state completion. Portfolio level: multi-indicator signals are synthesized by voting, union (all-hold with one-vote veto) or averaging, or cross-sectional ranking at rebalance dates; portfolios are built under top-n or share-count schemes with equal, inverse-vol or market-cap weights. Matching level: daily sell-recalc-buy execution with price-limit, suspension and delisting constraints, plus a full cost model (commission, tax, transfer fee, slippage), outputting net values with and without costs. Indicator values come from technical or fundamental skills (HDF5 or CSV panels); net values feed the strategy performance skill."

---

# 指标验证 Skill(ad-indicator-validation)

中国银河证券星耀数智的指标验证技能。

核心定位:**从单股信号到组合模型的完整回测引擎,不自算指标**。设计分三层——**单股层**把每个指标的指标值转为该股的买卖信号(三种规则模板 + 状态补全);**组合层**把多股多指标信号合成统一持仓(三种合成方式或截面排名选股 + 持仓口径与权重方案);**撮合层**逐日执行卖出/重算/买入,处理涨跌停与停牌约束并计入交易成本,产出双净值。指标值不自算,由技术面/基本面指标 skill 联动提供(HDF5 优先,CSV 兼容);完整绩效评估与 HTML 报告由「策略业绩分析」skill 承接。

## 联动工作流

```
① 调用指标 skill(ad_technical_analysis / ad_fundamental_analysis)
        获得指标值 → 整理为指标面板(HDF5 或 CSV)
② 本 skill --indicators 加载指标 → 信号规则 → 合成 → 撮合 → 净值
③ 净值 CSV → 策略业绩分析 skill → 完整绩效报告
```

### 指标面板格式

**HDF5(推荐,单文件可装全部指标)**:每个指标一个 key `/factors/<指标名>`,value 为 DataFrame(行=日期, 列=股票代码)。可用 `signal_engine.save_factors_h5(path, {指标名: 面板})` 写入。

**CSV(兼容)**:首列 date(YYYYMMDD 或 YYYY-MM-DD),其余列为股票代码,一个文件一个指标。

## 前置条件 - 安装库,设置 AmazingData 账号环境变量
使用本技能前，安装python运行环境(推荐python3.8/3.9/3.10/3.11/3.12/3.13/3.14环境)，并安装AmazingData依赖包。
从 https://gitee.com/cgs2026/xysz/releases 下载 tgw 和 AmazingData 的 wheel 文件并安装。
```bash
pip install tgw>=1.0.8.7
pip install AmazingData>=1.1.15
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

## 使用方法

### 组合回测(信号模式)

```bash
D:/ProgramData/anaconda313/python.exe scripts/run_backtest.py --mode backtest \
    --begin 20240101 --end 20260930 \
    --indicators "MACD价差:D:/data/macd.h5:cross" "RSI6:D:/data/rsi.h5:band:30,70" \
    --position-mode topn --top-n 20
```

### 组合回测(排名选股模式)

```bash
D:/ProgramData/anaconda313/python.exe scripts/run_backtest.py --mode backtest \
    --indicators "动量:D:/data/mom20.h5" "波动:D:/data/vol20.h5" \
    --selection rank --rebalance monthly --dirs "动量=1,波动=-1" --top-n 20
```

### 单股信号检查(ECharts 可视化)

```bash
D:/ProgramData/anaconda313/python.exe scripts/run_backtest.py --mode signal \
    --code 600000.SH --indicators "MACD价差:D:/data/macd.h5:cross" "RSI6:D:/data/rsi.h5:band:30,70"
```

### 指标规格与信号规则

`--indicators` 每项格式:`指标名:路径[:规则]`

| 规则 | 语义 |
|---|---|
| `pos`(默认) | 值 > 0 持有,< 0 空仓(用户已定方向的值) |
| `cross` | 上穿 0 买入,下穿 0 卖出(价差类指标) |
| `band:低,高` | 低于低值买入,高于高值卖出(震荡类指标) |

`--dirs` 排名方向(rank 模式):`指标名=1`(越大越优)或 `指标名=-1`(越小越优),逗号分隔;未指定的指标不参与排名合成。

### 合成方式(--combine-method)

| 方式 | 语义 |
|---|---|
| `vote`(默认) | 投票制:买入票占比 ≥ 50% 才买 |
| `union` | 并集:全部指标都持有才持有,任一转空仓立即卖出(一票否决,最严格) |
| `mean` | 均值:信号均值 < -0.5 买,> 0.5 卖 |

### 主要参数

| 参数 | 说明 |
|---|---|
| `--mode` | `signal` 单股信号检查 / `backtest` 组合回测 |
| `--indicators` | 指标规格列表(HDF5 优先,CSV 兼容) |
| `--selection` | `signal` 信号驱动 / `rank` 调仓日截面排名选股 |
| `--rebalance` | 调仓频率(rank 模式): daily / weekly / monthly / quarterly |
| `--position-mode` | `topn` 目标持仓数(默认) / `shares` 份数模式 |
| `--top-n` | 目标持仓数,默认 20 |
| `--capital` | 期初资金,默认 100 万元(影响最低佣金测算) |
| `--cost-free` | 关闭交易成本(对照用) |
| `--max-stocks` | 股票池上限(快速试跑) |

## 输出

- **终端摘要**:总收益 / 年化 / 波动 / 夏普 / 最大回撤(起止日期) / 卡玛 / 日胜率 / 年化换手 / 累计成本 / 基准对比
- **`backtest_nav_*.csv`**:date + net_value(含成本) + net_value_gross(不含成本),直接对接策略业绩分析 skill:

```bash
D:/ProgramData/anaconda313/python.exe ../ad_strategy_performance/scripts/performance_analysis.py \
    --input output/backtest_nav_*.csv --benchmark-code 000300.SH --open
```

- **`backtest_holdings_*.csv`**:逐日持仓明细
- **`signal_*.html`**(单股模式):K 线主图(含 MA5/10/20/60 + 买卖动作标记)+ 各指标信号副图 + 综合信号(投票)副图 + 并集信号(一票否决)副图,ECharts 交互

## 算法文档

- `references/backtest_methodology.md` — 回测算法逻辑说明(**先读本文档再改代码**)
- `references/indicator_universe.md` — 指标联动说明、信号规则与推荐池

## 模块结构

| 文件 | 职责 |
|---|---|
| `scripts/data_provider.py` | 登录、股票池、K线面板、前复权、停牌/涨跌停/ST 矩阵 |
| `scripts/signal_engine.py` | 指标面板加载(HDF5/CSV)、信号规则模板 |
| `scripts/factor_combine.py` | 截面预处理(MAD缩尾/标准化)、排名合成 |
| `scripts/portfolio_builder.py` | 两种持仓口径与权重方案、板块限制 |
| `scripts/backtest_engine.py` | 逐日撮合三步、信号合成、收益与成本、净值与摘要 |
| `scripts/signal_report.py` | 单股信号 ECharts 可视化(模板在 assets/) |
| `scripts/run_backtest.py` | CLI 入口 |

## 注意事项

1. 所有数据接口调用前必须先通过环境变量配置认证信息，然后调用`ad.login()`登录
2. `MarketData`实例化时必须传入交易日历：`ad.MarketData(base_data.get_calendar())`
3. AmazingData限制单点登录，所以同一时间只能有一个AmazingData的登录链接
4. 股票数据最早可追溯至2013年
5. 股票池为区间内曾上市的全部沪深A股(含退市),首次运行需下载本地数据,耗时较长
6. 全市场回测内存占用较大,建议先用 `--max-stocks 300` 试跑
7. 本工具输出为历史统计结果，不构成任何投资建议
