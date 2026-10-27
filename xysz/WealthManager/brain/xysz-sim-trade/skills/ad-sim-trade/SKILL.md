---
name: ad-sim-trade
display_name: 星耀数智模拟交易
display_name_en: Xingyao Simulated Trading
version: 1.1.0
author: 中国银河证券
description: "中国银河证券星耀数智模拟交易技能。提供组合管理（新建/查询/收益数据/净值曲线）与交易（下单/撤单/查持仓/委托/成交/资金/最大可买），支持生成可视化HTML报告（净值曲线/持仓/委托/成交明细）。仅供模拟交易，不构成投资建议。"
description_zh: "中国银河证券星耀数智模拟交易技能。提供组合管理（新建/查询/收益数据/净值曲线）与交易（下单/撤单/查持仓/委托/成交/资金/最大可买），未指定价格时自动取价（连续竞价取当日快照最新价、午休取上午收盘价、非交易时段取最近交易日收盘价，含1/3/6/10/15…三角数回退链），下单前做两级风控（代码格式/交易单位/最小价位/限价上下限/资金持仓硬拦截，大额与清仓需确认），支持生成可视化HTML报告（净值曲线/持仓/委托/成交明细）。仅限价委托，仅股票与ETF。仅供模拟交易，不构成投资建议。"
description_en: "China Galaxy Securities Xingyao simulated trading skill. Portfolio management (create/list/returns/net-value curve) and trading (buy/sell/cancel/positions/orders/trades/asset/max-qty). When no price is given, it resolves one automatically: latest snapshot tick during continuous auction, morning close during lunch break, or the latest completed trading day's close outside trading hours, using a 1/3/6/10/15... triangular fallback chain. Two-tier pre-trade risk control (hard blocks on code format, lot size, tick size, price bounds, funds/positions; large orders and full liquidation need confirmation). Generates a visual HTML report (net value curve, positions, orders, trades). Simulation only, not investment advice."

---

# 模拟交易 Skill（ad-sim-trade）

对接星耀数智模拟交易柜台，把「建组合 → 下单 → 撤单 → 查持仓/委托/成交 → 看收益」做成可复用的技能能力。

**边界**：仅模拟交易环境，不接实盘；**仅限价委托**；**仅股票与 ETF**。

---

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

`AD_PORT` 必须是 **int**（底层 uint16），从环境变量读出后需 `int()` 转换，传字符串会报错。本技能已处理。

账号密码从环境变量读取，**代码中不硬编码、不落盘、不打日志明文**。同一套账号同时覆盖行情与柜台；若柜台使用独立账号，可选设置 `AD_TRADE_USERNAME` / `AD_TRADE_PASSWORD` / `AD_TRADE_HOST` / `AD_TRADE_PORT`，未设时回落到 `AD_*`。

## 调用方式

```bash
python scripts/trade_cli.py <子命令> [参数]
```

示例：

```bash
python scripts/trade_cli.py portfolio list
python scripts/trade_cli.py buy --account-id 5 --code 600***.SH --volume 100
python scripts/trade_cli.py buy --account-id 5 --code 600***.SH --volume 100 --price 9.70
python scripts/trade_cli.py report --account-id 5
```

---

## 能力覆盖

### 组合类

| 子命令 | 说明 |
|---|---|
| `portfolio list [--status 1]` | 查组合列表，`status`：0-删除 / 1-正常(默认) / 2-开户中 / 3-开户失败 |
| `portfolio create --name X [--desc "..."]` | 新建组合。**初始资金固定 100 万**；**名称必填无默认**，1~50 字符 |
| `portfolio info --account-id N [N...] [--date]` | 组合收益数据（25 列） |
| `portfolio curve --account-id N [--begin --end] [--len]` | 历史收益率曲线 |

### 交易类

| 子命令 | 说明 |
|---|---|
| `buy --account-id N --code 600***.SH --volume 100 [--price X] [--confirm]` | 限价买入。给 `--price` 直接按该价下单；省略则自动取价 |
| `sell --account-id N --code 600***.SH --volume 100 [--price X] [--confirm]` | 限价卖出。同上 |
| `cancel --account-id N --order-id X` | 撤单 |
| `position --account-id N [--code]` | 查持仓（`--code` 最多 1 只） |
| `order --account-id N [--code ...] [--status ...] [--begin --end] [--cancellable]` | 查委托。不传日期即查当日；日期须成对；`--cancellable` 只查可撤单委托 |
| `trade --account-id N [--code ...] [--begin --end] [--all]` | 查成交。**默认只显示确定成交的记录**（成交价 > 0），`--all` 可查看含撤单/废单占位行的全部记录；日期须成对 |
| `asset --account-id N` | 查资金 |
| `max-qty --account-id N --code X --side buy --price P` | 查最大可买/卖 |

### 报告类

| 子命令 | 说明 |
|---|---|
| `report --account-id N [--begin --end] [--out 路径]` | 生成可视化 HTML 报告 |

所有子命令支持 `--json` 输出。

---

## 关键行为规则

### 登录

- 账号密码一律取环境变量。
- **用户指定价格下单**：只初始化柜台（`only_trade`），不登录行情，完全不取行情。
- **自动取价下单**：完整登录（行情）+ 初始化柜台，两者同进程并存。
- 登录失败内部会静默退出，本技能已内置重试与强制踢会话（`force_logout`），失败时给出中文原因而非无输出。

### 取价

未指定价格时按时段自动取价（**撮合时段是 9:30–11:30 / 13:00–15:00**）：

| 时段 | 取价来源 |
|---|---|
| 上午竞价 09:30–11:30 / 下午竞价 13:00–15:00 | 当日快照最新价（`end=15:31:00`，begin 按三角数序列 1/3/6/10/15/21/28… 分钟向前回退） |
| 午间休市 11:30–13:00 | 上午收盘最新价（`end=11:31:00`，begin 从 11:29 起同序列回退） |
| 盘前（<09:15）/ 盘后（≥15:00）/ 非交易日 | 最近已完成交易日收盘价（最多向前回退 5 个交易日） |

**回退链**：`1, 3, 6, 10, 15, 21, 28, 36, 45, 55…` 分钟，每次递增 1、2、3、4…（共 28 档，可回溯约 6.8 小时，覆盖 09:15→15:00 全时段）；begin 回退到 09:15 之前仍无数据 → **报「无行情，不能下单」**，绝不用 0 或前收盘价顶替。

> **09:15 是取价参数下界**（快照数据从此时起才有），不是交易时段起点——交易时段起点是 **9:30**。

输出会注明**价格来源与行情时间戳**，便于判断价格新鲜度。

### 下单风控（两级）

**一级 · 硬拦截**（直接拒绝并给中文原因，不打到柜台）：

- **代码校验采用 AmazingData 官方规则**：`security_type_config.base_type` 正则做 fullmatch（与柜台 `trade._split_code` 同一口径），后缀仅 `SH`/`SZ`/`BJ` 且须与代码匹配——不自行按首位数字推断交易所
- **品种校验**：下单前用官方 `is_security_type` 判定，仅**股票与 ETF** 可下单（可转债、国债、指数等其他品种一律拒收），与柜台 `trade._check_order_type` 一致
- 交易单位：买入时普通 A 股/ETF 须为 100 股整数倍、**科创板须为大于 200 股的整数**；**卖出时不超可用持仓即放行**（余额不足 100 股的零股可一次性清仓）
- 最小价位：**A 股 0.01、ETF 0.001**
- 限价上下限：按盘口基准价计算（见 [references/lifecycle.md](references/lifecycle.md)）
- 资金充足（`query_max_qty`）与持仓充足（`available_qty`，T+1 锁定与卖出冻结分别提示）

**二级 · 需 `--confirm`**（参数合法但异常）：单笔 ≥ 账户总资产 50%、单笔 ≥ 50 万、数量 ≥ 100000 股、卖出全部**可用**持仓（`volume >= available_qty`）。**不加 `--confirm` 只打印计划，不下单。**


### 查询日期必须成对

`--begin` 与 `--end` **必须成对使用**（要么都传、要么都不传），只传一个会被拒绝。传日期区间时，只要区间结束日不早于当日，返回结果**一定包含当日委托**——当日尚未完成盘后清算也能查到，无需等待。

### 参数校验陷阱

查询类接口的 `code` / `order_status` **必须传 list**（单只也要写成列表），传字符串会**静默返回空表**。本技能已在封装层处理。

### 返回值与错误码

所有接口返回 `(res, error_code)`，**不抛异常**。`error_code` 是**字符串**：

- `'00000'` 成功
- `None` 入参未通过校验、**请求未发出**（代码格式、list 参数、日期格式等）
- 其他为具体错误码，**可能带负号**（如 `'-1021'` 卖出查无持仓）

**必须用 `== '00000'` 判成功**，不可用真值判断。全部错误码的中文对照见 [references/api.md](references/api.md)。

**盘后下单会被拒绝**：若用户收盘后要求下单，柜台返回 `-1031`。此时应直接告知「当前非交易时段无法下单，请于下一个交易时段提交」，不要反复重试。

### 成交明细的判定

柜台的**成交表会为撤单、废单也写入占位行**（成交价 0、成交额 0、费用 0，但成交量等于委托数量）。判断真成交的判据是 **`match_price > 0`**（等价于 `trade_value > 0`）。本技能的 `trade` 子命令与 HTML 报告默认按此过滤，避免展示空记录。

### 交易规则要点

- **交易时段**：股票与 ETF 的撮合时段为 **9:30–11:30 / 13:00–15:00**。
- **午间休市（11:30–13:00）可挂单、可撤单**，但都不立即生效——挂单等 13:00 开盘后撮合，**撤单也要等 13:00 开盘后才处理**。因此午休撤单后、开盘前委托状态仍可能显示 `New`，属正常现象，不要误判撤单失败。
- **撮合**：限价单满足条件即**全部成交**，没有量的限制。买入价 ≥ 卖一价即按**最新价**全成；卖出价 ≤ 买一价同样全成。
- **交割**：沪深京 A 股、ETF、科创板、创业板均 **T+1**，当日买入当日不可卖。卖出校验看持仓表的 `available_qty`（可用数量），T+1 锁定时该字段为 0，本技能会提示「T+1 锁定，最早可卖日为下一交易日」而非笼统的「持仓不足」。
- **涨跌幅**：科创板/创业板 20%，其他 10%。
- **上市初期**：科创板/创业板上市前 5 天、非科创板非创业板 A 股上市首日不接受委托。
- **盘后不能下单**：15:00 收盘后至次日 9:30 期间提交委托，**柜台直接返回 `-1031 非交易时段不能下单`**，不受理为隔夜委托。⚠️ 规则文档中「盘后到次日 9:30 可提交委托、次日开盘撮合」的描述与实测不符，**以实测为准**——不要向用户承诺盘后可挂单或隔夜委托。
- **盘后**：16:30 盘后结算（可用划转，未成交委托自动撤单释放资金）→ 17:00 盘后清算（**当日委托与成交转为历史后清空**）→ 17:30 盘后分红。**17:00 后不带日期查当日委托/成交会返回空**，本技能会主动提示改用 `--begin/--end`。

详见 [references/lifecycle.md](references/lifecycle.md)。

### 费率

| 品种 | 佣金 | 印花税 | 过户费 | 单笔最低佣金 |
|---|---|---|---|---|
| 沪深A股 | 0.0003 | 0.0005 | 0.00001 | 5 元 |
| 北交所 | 0.0015 | 0.0005 | 0.00001 | 5 元 |
| 场内基金 | 0.0003 | — | — | 5 元 |

印花税仅股票收取。下单计划与报告中会给出费用预估。

---

## 参考文档

- [接口与错误码](references/api.md) —— 12 个接口签名、枚举取值、费率、约 120 个错误码中文对照
- [取价与交易规则](references/lifecycle.md) —— 时段划分、快照回退链、限价上下限计算、撮合规则、盘后生命周期
- [数据字段](references/fields.md) —— 各返回表的列数与字段中文含义

## 注意事项

- 模拟交易结果不代表真实交易表现，真实市场存在流动性、撮合与价格风险。
- 模拟交易仅用于策略演练与教学演示，不构成投资建议。
- **每个用户最多只能建 1 个组合**（后台限制），已建则无法再建；如需操作请直接使用已有组合。
- 组合初始资金固定 100 万，不可自定义。