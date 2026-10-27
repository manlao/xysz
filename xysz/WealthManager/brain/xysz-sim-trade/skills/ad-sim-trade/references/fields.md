# 数据字段

各返回表的列数与字段中文含义。取自柜台真实返回验证（AmazingData 1.1.17 环境实测）。

---

## 持仓 query_position —— 固定 12 列

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | str | 代码+市场，如 `600***.SH` |
| `security_name` | str | 证券简称 |
| `market_value` | float | 市值 |
| `init_qty` | int | 日初持仓数量 |
| `stock_buy` | int | 股份买入冻结 |
| `stock_sale` | int | 股份卖出冻结 |
| `available_qty` | int | 可用数量（可用于卖出校验） |
| `cost_price` | float | 成本价 |
| `last_price` | float | 最新价 |
| `profit_loss` | float | 浮动盈亏 |

> **卖出必须看 `available_qty`（可用数量），不是 `leaves_qty`（总持股）**。
>
> | 字段 | 含义 |
> |---|---|
> | `available_qty` | **可用数量**，可卖。T+1 锁定时为 0 |
> | `leaves_qty` | 持股总数（含锁定与冻结） |
> | `stock_sale` | 卖出冻结数量 |
> | `stock_buy` | 买入冻结数量 |
> | `init_qty` | 日初持仓，跨日后才有意义；当日新买为 None |
>
> **T+1 实测**：当日买入 100 股后 `available_qty=0`、`leaves_qty=100`、`stock_sale=100`，此时下单卖出会被 T+1 规则拦住，最早可卖日为下一交易日。本技能会识别该状态并给出明确提示，而非笼统的「持仓不足」。

---

## 委托 query_order —— 实测 25 列

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | str | 代码+市场 |
| `security_name` | str | 证券简称 |
| `side` | str | 委托方向（Buy/Sell） |
| `price_type` | str | 委托类型（Limit 等） |
| `order_status` | str | 委托状态，见 [api.md](api.md) 枚举 |
| `order_price` | float | 委托价格 |
| `order_qty` | int | 委托数量 |
| `trade_qty` | int | 已成交数量 |
| `cancel_qty` | int | 已撤数量 |
| `leaves_qty` | int | 剩余未成交数量 |
| `last_match_qty` | float | 最后一笔成交量 |
| `total_trade_value` | float | 累计成交金额 |
| `total_trade_fee` | float | 累计手续费 |
| `frozen_fee` | float | 冻结手续费 |
| `frozen_trade_value` | float | 冻结成交金额 |
| `error_code` | str | 柜台错误码 |
| `error_msg` | str | 错误信息 |
| `insert_time` | int | 委托时间（HHMMSS 整数，如 `125258`） |
| `confirm_time` | int | 确认时间 |
| `update_time` | int | 更新时间 |
| `cancel_time` | int | 撤单时间 |
| `orderDate` | int | 委托日期（8 位整数） |
| `trdDate` | int | 交易日期（8 位整数，未成交为 None） |
| `counter_order_id` | str | **柜台委托编号——撤单要用这个** |
| `account_id` | str | 资金账户id |

> ⚠️ **撤单必须用 `counter_order_id`**，不是 `insert_order` 返回的 order_id 以外的字段。

---

## 成交 query_trade —— 实测 13 列

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | str | 代码+市场 |
| `side` | str | 买卖方向 |
| `order_price` | float | 委托价格 |
| `match_price` | float | 成交价格 |
| `match_qty` | int | 成交量 |
| `match_time` | int | 成交时间（HHMMSS 整数） |
| `trade_value` | float | 成交金额 |
| `fee` | float | 手续费 |
| `exec_id` | str | 成交编号 |
| `counter_order_id` | str | 对应的委托编号 |
| `orderDate` | int | 委托日期 |
| `trdDate` | int | 交易日期 |
| `account_id` | str | 资金账户id |

> **成交表不含 `security_name`**，展示证券简称需自行关联委托表或代码表。
>
> ⚠️ **成交表会为撤单、废单写入占位行**：`match_price=0` / `trade_value=0` / `fee=0`，但 `match_qty` 仍等于委托数量。判断是否真成交的判据是 **`match_price > 0`**（等价于 `trade_value > 0`）；部分成交时成交价仍大于 0，同样应保留。本技能的 `trade` 子命令默认按此过滤（`--all` 可看全部），HTML 报告的「成交明细」也只展示确定成交的记录。

---

## 资金 query_asset —— dict

| 字段 | 类型 | 说明 |
|---|---|---|
| `account_id` | str | 资金账户id |
| `total_asset` | float | 总资产 |
| `market_value` | float | 当前所有持仓市值 |
| `leaves_value` | float | 资金余额 |
| `init_leaves_value` | float | 日初资金金额 |
| `available_t1` | float | T+1 可用资金 |
| `frozen_all` | float | 当前所有冻结（删组合前置校验用） |

---

## 最大可买 query_max_qty —— dict

| 字段 | 类型 | 说明 |
|---|---|---|
| `available` | float | 可用资金 |
| `max_qty` | int | 最大可买卖数量 |

---

## 组合列表 get_portfolio_list —— 固定 9 列

| 字段 | 类型 | 说明 |
|---|---|---|
| `account_id` | int | **资金账户id——所有组合接口的入参用它** |
| `portfolio_name` | str | 组合名称 |
| `begin_fund` | float | 初始资金 |
| `description` | str | 组合描述 |
| `channel` | int | 渠道 |
| `status` | int | 0-删除 / 1-正常 / 2-开户中 / 3-开户失败 |
| `delete_time` | str | 删除时间（`status=0` 时有值，其余为 None） |
| `create_time` | str | 创建时间 |
| `update_time` | str | 更新时间 |

---

## 组合收益 get_portfolio_benefits_info —— 固定 25 列

| 字段 | 类型 | 说明 |
|---|---|---|
| `account_id` | int | 资金账户id |
| `user_i_buss_id` | int | 账户类型（0 组合/模拟社区，1+ 为模拟大赛 ID） |
| `update_time` | int | 更新时间 |
| `total_value` | float | 总资产 |
| `total_mkt_value` | float | 总市值 |
| `aval_value` | float | 可用资金 |
| `day_profit_rate` | float | 日收益率 |
| `week_profit_rate` | float | 周收益率 |
| `month_profit_rate` | float | 月收益率 |
| `season_profit_rate` | float | 季收益率 |
| `total_profit_rate` | float | 总收益率 |
| `current_net_value` | float | 当前净值 |
| `holdpos` | float | 仓位 |
| `today_profit_value` | float | 当日盈亏 |
| `total_profit_num` | float | 总利润金额 |
| `max_retracement` | float | 最大回撤 |
| `win_win` | int | 盈利笔数 |
| `win_loss` | int | 亏损笔数 |
| `win_draw` | int | 平盘笔数 |
| `win_totalwin` | int | 累计盈利笔数 |
| `win_totalloss` | int | 累计亏损笔数 |
| `win_totaldraw` | int | 累计平盘笔数 |
| `win_win_rate` | float | 盈利比例 |
| `win_loss_rate` | float | 亏损比例 |
| `win_draw_rate` | float | 平盘比例 |

> 收益率类字段是小数（0.0523 表示 5.23%），展示时须乘 100。

---

## 收益率曲线 get_portfolio_benefits_rate —— 固定 2 列

| 字段 | 类型 | 说明 |
|---|---|---|
| `date` | str | 日期 |
| `profit_rate` | float | 收益率（小数） |

---

## 组合创建 create_portfolio —— dict

| 字段 | 说明 |
|---|---|
| `portfolio_name` | 组合名称 |
| `account_id` | 资金账户id |
| `begin_fund` | 初始资金 |
| `description` | 组合描述 |
| `channel` | 渠道 |
| `status` | 组合状态 |
| `create_time` | 创建时间 |
| `update_time` | 更新时间 |


---

## 代码与品种校验口径

本技能的代码校验**直接采用 AmazingData 官方实现**，不自行推断：

| 环节 | 官方来源 | 作用 |
|---|---|---|
| 格式校验 | `security_type_config.base_type` 正则 + `fullmatch` | 校验「代码.市场」格式及后缀与代码是否匹配 |
| 品种校验 | `utils.security_type.is_security_type` | 判定是否属于股票（`EXTRA_STOCK_A`）或 ETF（`EXTRA_ETF`） |
| 可下单判定 | 二者结合（与柜台 `trade._check_order_type` 同口径） | 仅股票与 ETF 可下单 |

> ⚠️ **不要按代码首位数字推断交易所**：沪市国债（`204***.SH`）、深市可转债（`123***.SZ`）、北交所股票（`83****.BJ`）的首位数字都不同于常见板块，凭经验猜测必然出错。

## 时间字段格式

- `insert_time` / `match_time` / `confirm_time` / `cancel_time`：柜���原值，**HHMMSS 整数**（如 `125258` 表示 12:52:58）
- `orderDate` / `trdDate`：**8 位整数**（如 `20260101`）

展示时需自行补齐格式。