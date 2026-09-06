---
name: ad-etf-dca
description: 中国银河证券星耀数智场内ETF定投计算器。支持正向测算、历史回测、目标反推（自定义每期投入金额、年化收益、投资期限）等多类 ETF 定投测算场景。
---

# ETF定投计算器 Skill

中国银河证券星耀数智的场内ETF定投计算工具。输入ETF代码与定投参数，自动获取历史行情数据，计算收益并生成可视化HTML报告。

## 核心特性

- **价格口径**：前复权收盘价（红利再投资全收益口径），与行情软件一致
- **费用建模**：佣金逐笔计算 `max(金额 × 费率, 最低5元)`，不可平均
- **份额规则**：向下取整到100份（1手），场内最小交易单位
- **真实年化**：IRR（定期）/ XIRR（不定期），资金加权计算
- **报告输出**：Jinja2模板 + ECharts亮色主题HTML报告

## 前置条件 - 安装库，设置 AmazingData 账号环境变量

使用本技能前，安装python运行环境(推荐python3.8/3.9/3.10/3.11/3.12/3.13环境)，并安装AmazingData依赖包。
从https://gitee.com/cgs2026/xysz clone整个项目，再用xysz_tools下的wheel文件安装tgw和AmazingData。
```bash
pip install tgw>=1.0.8.7
pip install AmazingData>=1.1.4
pip install jinja2
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

## 使用方法

在技能根目录下执行脚本，会自动：
1. 通过 AmazingData 获取 ETF 历史行情和复权因子
2. 执行定投计算
3. 生成 HTML 可视化报告并保存到工作空间 `data/` 目录
4. **计算完成后，必须将生成的 HTML 报告展示给用户**

```bash
# 正向测算：预估定投收益
python scripts/run_analysis.py --mode forward --symbol 510***.SH \
    --amount 2000 --frequency monthly --duration 5 --expected_return 8

# 历史回测：真实K线数据回测
python scripts/run_analysis.py --mode backtest --symbol 510***.SH \
    --amount 2000 --frequency monthly --start 20200101 --end 20241231

# 目标反推-每期金额：达成目标需要每月投多少
python scripts/run_analysis.py --mode target_amount --symbol 510***.SH \
    --target 1000000 --duration 10 --expected_return 8 --frequency monthly

# 目标反推-所需年化：需要多高的年化才能达成
python scripts/run_analysis.py --mode target_return --symbol 510***.SH \
    --target 1000000 --amount 3000 --duration 10 --frequency monthly

# 目标反推-期限：需要多久才能达成
python scripts/run_analysis.py --mode target_duration --symbol 510***.SH \
    --target 1000000 --amount 3000 --expected_return 8 --frequency monthly
```

## 运行模式

| 模式 | 输入 | 输出 | 场景                           |
|------|------|------|------------------------------|
| `forward` | 当前价格 + 每期金额 + 年限 + **预期年化** | 预估期末资产 + IRR | "如果年化8%，投5年后值多少？"            |
| `backtest` | ETF代码 + 每期金额 + **起止日期** | 实际资产 + XIRR + 最大回撤 + 年化波动率 | "2020年到2024年每月投2000，真实赚了多少？" |
| `target_amount` | 目标资产 + 年限 + 预期年化 | **每期需要投多少** (PMT求解) | "想5年攒100万，每月该投多少？"           |
| `target_return` | 目标资产 + 每期金额 + 年限 | **需要多高的年化** (牛顿迭代求解) | "我每月只能投3000，10年到100万要多少收益？"  |
| `target_duration` | 目标资产 + 每期金额 + 预期年化 | **需要多久** (对数求解) | "每月3000、预期8%，多久能到100万？"      |

`forward` 和 `backtest` 是正算（已知投入→求产出），三个 `target_*` 是反推（已知目标→求条件）。

## 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--mode` | forward / backtest / target_amount / target_return / target_duration | forward |
| `--symbol` | ETF代码（AmazingData格式，如510***.SH） | 510***.SH |
| `--amount` | 每期定投金额（元） | 2000 |
| `--frequency` | 定投频率：weekly / biweekly / monthly / quarterly / day | monthly |
| `--interval` | 每隔多少日，配合 `--frequency day` 使用（如5=每5日） | - |
| `--duration` | 定投期限（年），forward模式必填 | - |
| `--start` | 起始日期 YYYYMMDD（backtest模式） | - |
| `--end` | 结束日期 YYYYMMDD（backtest模式） | 今天 |
| `--target` | 目标资产（元），target模式必填 | - |
| `--expected_return` | 预期年化收益率（%），forward/target模式 | 8.0 |
| `--commission_rate` | 佣金费率 | 0.0003（万3） |
| `--min_commission` | 最低佣金（元） | 5 |
| `--scenarios` | 多情景对比年化值，逗号分隔 | 4,6,8,10 |
| `--output` | 报告输出路径 | data/etf_dca_report.html（当前工作空间 data/ 目录） |

## 输出报告内容

HTML报告包含以下板块：

1. **核心指标卡** — 期末总资产 / 总投入本金 / 累计收益(+率) / IRR/XIRR / 总佣金 / 有效费率
2. **资产曲线图** — ECharts 双线：资产走势 vs 本金投入
3. **逐年明细表** — 每年投入 / 佣金 / 份额 / 资产 / 收益 / IRR
4. **多情景对比图** — 不同预期年化下的期末资产与总收益
5. **风险指标** — 最大回撤 / 年化波动率
6. **佣金警示** — 触发最低5元时提示有效费率与优化建议

## 注意事项

1. 所有数据接口调用前必须先通过环境变量配置认证信息，然后调用`ad.login()`登录
2. 必须设置以下4个环境变量：`AD_USERNAME`、`AD_PASSWORD`、`AD_HOST`、`AD_PORT`
3. 账号、密码、IP和端口需联系开户营业部申请
4. AmazingData限制单点登录，同一时间只能有一个登录链接
5. 计算结果仅供参考，不构成投资建议。过往业绩不代表未来收益
6. 前复权价格不等于实际交易价格，实盘下单需以最新市价为准
7. 定投日如遇非交易日，自动顺延至下一个交易日

## Python环境要求

- Python版本: 3.8-3.14
- 操作系统: Linux/Windows
- 依赖包: tgw>=1.0.8.5, AmazingData>=1.1.4, jinja2, pandas, numpy, scipy
