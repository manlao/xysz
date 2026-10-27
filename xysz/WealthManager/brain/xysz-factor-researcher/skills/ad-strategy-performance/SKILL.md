---
name: ad-strategy-performance
display_name: 星耀数智策略业绩分析
display_name_en: Xingyao Strategy Performance Analysis
version: 1.1.1
author: 中国银河证券
description: 中国银河证券星耀数智的策略业绩分析技能。对策略净值序列做完整业绩评估（收益/风险/相对基准/风险调整/收益分布五类共20余项指标，含最大回撤起止日期），支持对比基准指数（默认沪深300，经星耀数智AmazingData在线拉取），自动生成可视化HTML报告（净值曲线/最大回撤分析/月度收益热力图/日收益分布）。涉及策略业绩分析、绩效分析、净值分析、策略评估、回测评估、夏普比率、最大回撤、年化收益、信息比率、卡玛比率、索提诺比率、日胜率等场景时使用。
description_zh: 中国银河证券星耀数智的策略业绩分析技能。对策略净值序列做完整业绩评估（收益/风险/相对基准/风险调整/收益分布五类共20余项指标，含最大回撤起止日期），支持对比基准指数（默认沪深300，经星耀数智AmazingData在线拉取），自动生成可视化HTML报告（净值曲线/最大回撤分析/月度收益热力图/日收益分布）。涉及策略业绩分析、绩效分析、净值分析、策略评估、回测评估、夏普比率、最大回撤、年化收益、信息比率、卡玛比率、索提诺比率、日胜率等场景时使用。
description_en: China Galaxy Securities Xingyao strategy performance analysis skill. Evaluates strategy nav series with 20+ metrics across return, risk, benchmark-relative, risk-adjusted and distribution categories (max drawdown with peak/valley dates), supports benchmark comparison (default CSI 300, fetched online via AmazingData), and generates a fresh-light visual HTML report with nav curve, max drawdown analysis, monthly return heatmap and daily return distribution.

---

# 策略业绩分析 Skill（ad-strategy-performance）

中国银河证券星耀数智的策略业绩分析技能。

对策略净值序列做完整业绩评估，支持对比基准指数（默认沪深300），输出终端摘要表 + fresh-light 风格可视化 HTML 报告。

## 前置条件

- 安装python运行环境(推荐python3.8/3.9/3.10/3.11/3.12/3.13/3.14环境)，并安装AmazingData依赖包。
从 https://gitee.com/cgs2026/xysz/releases 下载 tgw 和 AmazingData 的 wheel 文件并安装。
```bash
pip install tgw>=1.0.8.7
pip install AmazingData>=1.1.15
```
- 联系开户营业部申请账号、密码、服务器IP。
- 设置环境变量：
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

本技能的基准指数行情（默认沪深300）经 AmazingData 在线拉取；若环境变量未配置或拉取失败，脚本会跳过基准对比并给出提示，仅输出策略单边指标。
> `import AmazingData` 依赖 tgw，两者需安装在同一 Python 环境中。

## 使用流程

### 1. 准备净值数据（CSV）

支持两种格式，列名自动识别（也可用参数显式指定）：

| 格式 | 必需列 | 说明 |
|---|---|---|
| 净值 | `date`（或 time_tag/日期）+ `net_value`（或 净值） | 直接使用 |
| 资产 | 日期列 + `total_balance`（或 总资产） | 自动换算为净值（首日=1） |

### 2. 一键分析（CLI）

```bash
cd <skill目录>/scripts

# 基准经星耀数智在线拉取（默认沪深300）
python performance_analysis.py --input net_value.csv \
    --output output/performance_report.html

# 区间预设（以净值末日至终点倒推）：all全部/半年/1年/3年/5年/ytd今年以来
python performance_analysis.py --input net_value.csv --period 5年 \
    --output output/performance_report.html

# 指定起止日期（YYYYMMDD）

# 不对比基准 / 指定参数
python performance_analysis.py --input net_value.csv \
    --benchmark-code "" --annual-days 244 --rf 2.0 --open
```

运行后输出：终端指标摘要表（策略 vs 基准）+ 单文件 HTML 报告。

### 3. Python API

```python
import pandas as pd
from performance_analysis import PerformanceAnalyzer, load_nav_csv, fetch_benchmark_from_api

nav = load_nav_csv('net_value.csv')                      # 归一化净值序列
bench = fetch_benchmark_from_api('000300.SH', 20250101, 20251231)

analyzer = PerformanceAnalyzer(nav, bench, annual_days=244, rf=0.02)
result = analyzer.run()
analyzer.print_summary()

from report_renderer import PerformanceReport
PerformanceReport(title='我的策略业绩报告').generate(result, 'output/report.html', benchmark_name='沪深300')
```

## 指标清单

| 类别 | 指标 |
|---|---|
| 收益 | 累计收益率、年化收益率、日均收益率、月度收益表（YYYY-MM）、**年度收益表**、月均收益、月胜率、日胜率、**盈亏比**、**最大连涨/连跌天数** |
| 风险 | 年化/日/月波动率、最大回撤（含高点→低点→修复日期）、**当前回撤**、**距上次创新高交易日数**、**最长回撤持续交易日数**、**分年度最大回撤**、下行风险、偏度、峰度 |
| 相对基准 | Beta、Alpha、跟踪误差、信息比率、特雷诺比率、超额累计/年化收益、日收益相关系数 |
| 风险调整 | 夏普比率、索提诺比率、卡玛比率 |
| 分布 | 日收益率分布（12档，-10%以下 至 10%以上） |
| 数据质量 | **数据断档检测**：以基准指数（默认沪深300）交易日历为参照，比对净值序列缺失/多余的交易日 |

## 参数与口径

| 参数 | 默认 | 说明 |
|---|---|---|
| `--annual-days` | 244 | 年化天数，所有年化指标统一使用 |
| `--rf` | 2.0 (%) | 无风险年利率，参与夏普/索提诺/卡玛/Alpha/特雷诺 |
| `--benchmark-code` | 000300.SH | 基准指数代码；传空字符串则不对比基准 |
| `--start` / `--end` | 净值首末日 | YYYYMMDD，区间裁剪 |
| `--period` | all（全部） | 区间预设：all/半年/1年/3年/5年/ytd，以净值末日为终点倒推；与 `--start` 二选一 |

关键计算口径：
- 年化收益 = (期末净值/期初净值)^(244/日收益个数) − 1（复利口径）
- 年化波动率 = 日收益样本标准差(ddof=1) × √244
- Beta = 协方差(ddof=1) / 基准日收益样本方差(ddof=1)
- Alpha = 年化收益 − (rf + Beta × (基准年化收益 − rf))
- 下行风险 = 低于 rf/244 的日收益（其余记0）样本标准差 × √244

## HTML 报告内容

1. KPI 概览卡（累计收益/年化/最大回撤/当前回撤/夏普/卡玛/日胜率，红涨绿跌）
2. 业绩指标明细表（策略 vs 基准，按收益/风险/风险调整/相对基准四类分组，含最大回撤起止日期与当前回撤状态注释）
3. **年度收益与年度最大回撤**（策略 vs 基准柱状图 + 逐年明细表）
4. 净值曲线（叠加基准，支持缩放）
5. 最大回撤分析（回撤曲线 + 历史最低点标注）
6. 月度收益率热力图（年 × 月，红涨绿跌）
7. 日收益率分布（12档柱状图）
8. **指标口径说明**（折叠区，列出各指标计算口径与当前参数）

fresh-light 清新浅色主题，移动端自适应，单文件输出。

## 注意事项

1. 策略净值 CSV 为必需输入；本 skill 只做净值层面的业绩分析，不含持仓/交易分析
2. 在线拉取基准需配置 AD_USERNAME/AD_PASSWORD/AD_HOST/AD_PORT 环境变量，且 AmazingData 限制单点登录（同一时间只能有一个登录链接）
3. 净值数据不允许存在非正值；同一交易日多条记录取最后一条
4. 策略与基准按共同交易日对齐，被丢弃的非共同交易日会在终端提示
5. 指标口径与默认参数详见上表；年化天数与无风险利率均可通过参数调整
6. 数据断档检测依赖基准交易日历，未对比基准（`--benchmark-code ""`）时不做该项检查
7. 月度/年度收益的首月（首年）按净值首日到期末计算，其余按自然月末（年末）净值点计算
8. 本工具仅提供业绩统计结果，不构成任何投资建议

## Python环境要求

- Python版本: 3.8-3.14
- 操作系统: Linux/Windows
- 依赖包: tgw>=1.0.8.7, AmazingData>=1.1.15
