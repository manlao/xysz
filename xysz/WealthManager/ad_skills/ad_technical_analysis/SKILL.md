---
name: ad-technical-analysis
description: 中国银河证券星耀数智A股技术面指标计算工具。当用户需要计算A股股票的技术指标时使用此技能。支持56个技术指标的计算，涵盖超买超卖、趋势、能量、成交量、均线、路径、其他共7大类。包括MACD、KDJ、RSI、布林线、均线系统、DMI、TRIX、SAR等。本技能仅提供技术指标的数值计算结果，不包含任何买卖信号或投资建议。即使用户没有明确提到"技术指标"，只要涉及A股技术指标计算、KDJ、RSI、MACD、布林带等技术分析场景，都应该使用此技能。
---

# A股技术指标计算

## 概述

56个技术指标，涵盖7大分类。本工具仅提供技术指标的数值计算结果，不包含任何买卖信号、多空判断或投资建议。

- **超买超卖型（14个）**：KDJ、RSI、WR、CCI、ROC、MTM、BIAS、SKDJ、MFI、OSC、UDL、ACCER、RCCD、MARSI
- **趋势型（14个）**：MACD、DMI、DMA、TRIX、ARBR、EMV、DPO、VHF、CHO、DBCD、DDI、JS、QACD、UOS
- **能量型（5个）**：CR、PSY、MASS、PCNT、WAD
- **成交量型（9个）**：OBV、VR、VOLMA、WVAD、VOSC、VRSI、VSTD、AMO、TAPI
- **均线型（4个）**：MA、EXPMA、BBI、AMV
- **路径型（6个）**：BOLL、ENE、MIKE、PBX、XS、BBIBOLL
- **其他型（4个）**：ASI、ATR、SAR、CDP

数据来源：AmazingData API（中国银河证券金融数据接口）

## 重要声明

**本工具仅提供技术指标的客观计算结果，不构成任何投资建议。所有技术指标的计算结果仅供研究参考，用户应自行判断并承担投资风险。**

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

## 使用方法

通过 Bash 工具调用 `scripts/run_technical_analysis.py` 脚本：

```bash
# 综合分析（所有指标）
D:/ProgramData/anaconda313/python.exe D:/WealthManager/WealthManager/ad_skills/ad_technical_analysis/scripts/run_technical_analysis.py 600***.SH

# 指定日期范围
D:/ProgramData/anaconda313/python.exe D:/WealthManager/WealthManager/ad_skills/ad_technical_analysis/scripts/run_technical_analysis.py 600***.SH --begin 20240101 --end 20260321

# 单指标分析
D:/ProgramData/anaconda313/python.exe D:/WealthManager/WealthManager/ad_skills/ad_technical_analysis/scripts/run_technical_analysis.py 600***.SH --indicator MACD

# 指定指标类别
D:/ProgramData/anaconda313/python.exe D:/WealthManager/WealthManager/ad_skills/ad_technical_analysis/scripts/run_technical_analysis.py 600***.SH --category overbought_oversold
```

### 可用的 category 参数

| category | 中文名 | 指标数 |
|----------|--------|--------|
| overbought_oversold | 超买超卖型 | 14 |
| trend | 趋势型 | 14 |
| energy | 能量型 | 5 |
| volume | 成交量型 | 10 |
| ma | 均线型 | 4 |
| path | 路径型 | 6 |
| other | 其他型 | 4 |

### 可用的 indicator 参数

所有指标名称均支持大小写：KDJ, RSI, WR, CCI, ROC, MTM, BIAS, SKDJ, MFI, OSC, UDL, ACCER, RCCD, MARSI, MACD, DMI, DMA, TRIX, ARBR, EMV, DPO, VHF, CHO, DBCD, DDI, JS, QACD, UOS, CR, PSY, MASS, PCNT, WAD, OBV, VR, VOLMA, WVAD, VOSC, VRSI, VSTD, AMO, TAPI, MA, EXPMA, BBI, AMV, BOLL, ENE, MIKE, PBX, XS, BBIBOLL, ASI, ATR, SAR, CDP

## 输出格式

### 全部指标模式

```json
{
  "code": "60****.SH",
  "date": "2026-03-21",
  "data_count": 500,
  "price": {"open": 0, "high": 0, "low": 0, "close": 0, "volume": 0, "amount": 0},
  "categories": {
    "overbought_oversold": {
      "name": "一、超买超卖型",
      "indicators": [
        {"name": "KDJ", "values": {"K": 0, "D": 0, "J": 0}},
        {"name": "RSI", "values": {"RSI6": 0, "RSI12": 0}},
        ...
      ]
    },
    ...
  }
}
```

### 单指标模式

```json
{
  "code": "60****.SH",
  "date": "2026-03-21",
  "price": {"open": 0, "high": 0, "low": 0, "close": 0, "volume": 0, "amount": 0},
  "indicator": {
    "name": "MACD",
    "values": {"DIF": 0, "DEA": 0, "MACD": 0}
  },
  "category": "二、趋势型"
}
```

## 技术指标列表（57个）

本技能支持计算以下7大类共57个技术指标：

### 一、超买超卖型（14个）
KDJ、RSI、WR、CCI、ROC、MTM、BIAS、SKDJ、MFI、OSC、UDL、ACCER、RCCD、MARSI

### 二、趋势型（14个）
MACD、DMI、DMA、TRIX、ARBR、EMV、DPO、VHF、CHO、DBCD、DDI、JS、QACD、UOS

### 三、能量型（5个）
CR、PSY、MASS、PCNT、WAD

### 四、成交量型（10个）
OBV、VR、VOLMA、WVAD、VOSC、VRSI、VSTD、AMO、TAPI

### 五、均线型（4个）
MA、EXPMA、BBI、AMV

### 六、路径型（6个）
BOLL、ENE、MIKE、PBX、XS、BBIBOLL

### 七、其他型（4个）
ASI、ATR、SAR、CDP

详细的技术指标公式和实现细节请参考脚本源码。

## 核心辅助函数说明

| 函数 | 功能 | 说明 |
|------|------|------|
| `is_stock(code)` | 判断是否为A股股票 | SH市场首位6，SZ市场首位0或3，代码6位数字 |
| `forward_adjust(df, backward_factor, code)` | 前复权处理 | price_adj = price_raw * backward_factor / latest_factor，仅调整OHLC |

## 数据依赖

### 必需的 AmazingData API 调用

| 数据 | API函数 | 用途 |
|------|---------|------|
| 交易日历 | `base_data.get_calendar()` | MarketData 初始化 |
| K线行情 | `market_data.query_kline(code_list, begin_date, end_date, period=day)` | OHLCV 数据 |
| 后复权因子 | `base_data.get_backward_factor(code_list, is_local=False)` | 前复权计算（仅股票） |

### K线数据字段

| 字段 | 含义 | 用途 |
|------|------|------|
| `close` | 收盘价 | 所有指标 |
| `open` | 开盘价 | ARBR, WVAD, ASI |
| `high` | 最高价 | KDJ, WR, CCI, SKDJ, MFI, DMI, EMV, CHO, DDI, MASS, WAD, MIKE, XS, ATR, SAR, CDP 等 |
| `low` | 最低价 | 同上 |
| `volume` | 成交量 | MFI, EMV, CHO, OBV, VR, VOLMA, WVAD, VOSC, VRSI, VSTD, AMV |
| `amount` | 成交额 | AMO, TAPI, AMV |
| `kline_time` | K线日期 | 日期展示、前复权对齐 |
### 算子函数库依赖

脚本依赖 AmazingData 内置算子函数库：

| 模块 | 函数 | 说明 |
|------|------|------|
| `MathFunction` | MAX, MIN, ABS, IF, SIGN | 基础数学运算，支持 Series 间逐元素操作 |
| `StatisticsFunction` | STD, AVEDEV | 滚动标准差、平均绝对偏差 |
| `TimeSeriesFunction` | MA, EMA, SMA, REF, HHV, LLV, SUM, COUNT, CUMSUM, TR, SAR | 时间序列函数：移动平均、指数平均、历史引用、滚动最高/最低、累计求和等 |

## 前复权处理

对于股票代码（SH市场首位6，SZ市场首位0或3），自动进行前复权处理：
- 获取后复权因子（`get_backward_factor`）
- 按 `kline_time` 对齐复权因子（`reindex` + `ffill`）
- 前复权价格 = 原始价格 x 复权因子 / 最新复权因子
- 仅调整 open, high, low, close 四个价格字段
- 指数和基金代码不做前复权处理

## 模块结构

```
ad_technical_analysis/
├── SKILL.md                              # 本技能说明文档
├── references/
│   └── 技术指标说明.md                   # 57个技术指标的详细公式与说明
└── scripts/
    └── run_technical_analysis.py         # 分析脚本（完全自包含）
```

**`scripts/run_technical_analysis.py`** 包含：
- `TechnicalIndicators` 类：57个静态方法，输入 pandas Series (OHLCV)，输出 dict of Series
- `is_stock(code)` / `forward_adjust(df, backward_factor, code)`：股票判断与前复权
- `run_analysis(code, begin_date, end_date, indicator, category)`：主分析逻辑，计算技术指标
- `main()`：CLI 入口，支持 `--begin`, `--end`, `--indicator`, `--category` 参数


## 注意事项

1. 所有数据接口调用前必须先通过环境变量配置认证信息，然后调用`ad.login()`登录
2. 必须设置以下4个环境变量：`AD_USERNAME`、`AD_PASSWORD`、`AD_HOST`、`AD_PORT`
3. 账号、密码、IP和端口需联系开户营业部申请
4. `MarketData`实例化时必须传入交易日历：`ad.MarketData(base_data.get_calendar())`
5. 支持本地数据缓存（local_path + is_local）和指定日期范围（begin_date + end_date）两种模式，二选一
6. 股票数据最早可追溯至2013年，期货数据至2010年，期权数据至2015年
7. AmazingData限制单点登录，所以同一时间只能有一个AmazingData的登录链接
8. 本工具仅提供技术指标计算结果，不构成任何投资建议

## Python环境要求

- Python版本: 3.8-3.14
- 操作系统: Linux/Windows
- 依赖包: tgw>=1.0.8.5, AmazingData>=1.0.24