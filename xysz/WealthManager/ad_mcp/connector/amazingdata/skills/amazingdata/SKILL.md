---
name: amazingdata-mcp
description: 星耀数智 AmazingData 金融数据 MCP 连接器使用说明。涵盖 57 个工具：A股/ETF/期权/期货/可转债行情与K线、财务三表、股东结构、两融、龙虎榜、指数成分、国债收益率等。连接器已配置用户凭证（AD_USERNAME/AD_PASSWORD/AD_HOST/AD_PORT 环境变量注入，启动时自动登录）。
---

# 星耀数智 AmazingData MCP 使用说明

## 连接与认证

- 连接器以 stdio 模式启动，启动时读取环境变量 `AD_USERNAME`、`AD_PASSWORD`、`AD_HOST`、`AD_PORT` 自动登录星耀数智数据服务。
- 连接表单中填写用户名、密码及服务器地址/端口（开户时由星耀数智下发，请向用户确认后如实填写）。
- **首次连接较慢属正常**：启动脚本会自动下载并安装运行依赖（需 3~5 分钟）。若用户反馈"工具找不到/连接失败"，很可能是首次安装尚未完成——请告知用户等待 5 分钟后重试，或重启 WorkBuddy 再连接（第二次会秒连，依赖已缓存）。
- 若启动时登录失败（凭证缺失或网络异常），服务仍可用：先调用 `mcp_get_login_status` 检查状态，必要时用 `mcp_login` 显式登录。

## 通用约定（所有数据工具均遵循）

- **日期格式**：8 位整数 `YYYYMMDD`，如 `20240101`；`begin_date` 默认 `19900101`，`end_date` 默认当天。
- **证券代码**：`代码.交易所后缀`，如 `000001.SZ`、`600000.SH`、`510300.SH`（ETF）、可转债如 `113050.SH`。
- **K线周期 period**：`min1`、`min3`、`min5`、`min10`、`min15`、`min30`、`min60`、`min120`、`day`、`week`、`month`、`season`、`year`（共 13 种，对应手册附录 Period 枚举）。
- **建议限制**：单次日期范围不超过 1 年；单次代码数量不超过 50 个。
- **行情惯例**：涨跌颜色遵循 A 股惯例（涨红跌绿）。

## 工具目录

### 登录管理
| 工具 | 用途 |
|---|---|
| `mcp_get_login_status` | 查询当前登录状态（无参数，诊断首选） |
| `mcp_login` | 显式登录，可不传参（用环境变量凭证）或传 username/password/host/port |

### 证券代码与交易日历
| 工具 | 关键参数 |
|---|---|
| `mcp_code_info(security_type)` | 证券代码信息，默认 `EXTRA_STOCK_A` |
| `mcp_code_list(security_type)` | 证券代码列表 |
| `mcp_code_list_future(security_type)` | 期货代码，默认 `EXTRA_FUTURE` |
| `mcp_code_list_option(security_type)` | 期权代码，默认 `EXTRA_OPTION` |
| `mcp_history_code_list(security_type, date)` | 某历史日期的代码列表 |
| `mcp_bj_code_mapping()` | 北交所代码映射 |
| `mcp_calendar(market, date)` | 交易日历，market 为 `SH`/`SZ` 等；**注意不接受 begin_date/end_date** |

### 行情数据
| 工具 | 关键参数 |
|---|---|
| `mcp_kline(code_list, begin_date, end_date, period)` | K 线；`count` 可选；period 见通用约定 |
| `mcp_snapshot(code_list, asset_type)` | 实时快照，asset_type 默认 `auto` |
| `mcp_industry_index_quote(index_code_list, begin_date, end_date)` | 行业指数行情 |
| `mcp_treasury_yield(code_list, begin_date, end_date)` | 国债收益率 |

### 财务报表
| 工具 | 说明 |
|---|---|
| `mcp_balance_sheet(code_list, statement_type, begin_date, end_date)` | 资产负债表 |
| `mcp_cash_flow(code_list, statement_type, ...)` | 现金流量表 |
| `mcp_income(code_list, statement_type, ...)` | 利润表 |
| `mcp_profit_express(code_list, begin_date, end_date)` | 业绩快报 |
| `mcp_profit_notice(code_list, ...)` | 业绩预告 |

`statement_type` 不传时返回全部报告期口径。

### 公司与股东
| 工具 | 用途 |
|---|---|
| `mcp_stock_basic(code_list, summary_only)` | 基础资料，summary_only 精简 |
| `mcp_history_stock_status(code_list, begin_date, end_date)` | 历史 ST/退市等股状态 |
| `mcp_share_holder(code_list, begin_date, end_date)` | 股东 |
| `mcp_holder_num(code_list, begin_date, end_date)` | 股东户数 |
| `mcp_equity_structure(code_list, begin_date, end_date)` | 股本结构 |
| `mcp_equity_pledge_freeze(code_list, begin_date, end_date)` | 股权质押冻结 |
| `mcp_equity_restricted(code_list, begin_date, end_date)` | 限售股 |
| `mcp_dividend(code_list, begin_date, end_date)` | 分红 |
| `mcp_right_issue(code_list, begin_date, end_date)` | 配股 |

### 两融与资金
| 工具 | 用途 |
|---|---|
| `mcp_margin_summary(begin_date, end_date)` | 两融汇总，仅需日期 |
| `mcp_margin_detail(code_list, begin_date, end_date)` | 两融明细 |
| `mcp_long_hu_bang(code_list, begin_date, end_date)` | 龙虎榜 |
| `mcp_block_trading(code_list, begin_date, end_date)` | 大宗交易 |

### 指数
| 工具 | 用途 |
|---|---|
| `mcp_index_constituent(index_code, date)` | 指数成分股 |
| `mcp_index_constituent_weight(index_code, date)` | 指数成分权重 |
| `mcp_industry_index_info(index_type)` | 行业指数目录，默认 `SW` 申万 |
| `mcp_industry_index_constituent(index_code, date)` | 行业指数成分股 |
| `mcp_industry_index_weight(index_code, date)` | 行业指数成分权重 |

### ETF
| 工具 | 用途 |
|---|---|
| `mcp_etf_purchase_redemption(code_list, date)` | 申赎清单 |
| `mcp_etf_fund_share(code_list, begin_date, end_date)` | 基金份额 |
| `mcp_etf_iopv(code_list, begin_date, end_date)` | IOPV 净值估算 |

### 期权
| 工具 | 用途 |
|---|---|
| `mcp_option_basic_info(code_list)` | 期权基本资料 |
| `mcp_option_contract_info(code_list)` | 期权合约信息 |
| `mcp_option_month_contract_change(code_list, begin_date, end_date)` | 期权月度合约变化 |

### 可转债
| 工具 | 用途 |
|---|---|
| `mcp_kzz()` | 可转债概况 |
| `mcp_convertible_bond_issue(code_list, begin_date, end_date)` | 发行 |
| `mcp_convertible_bond_balance(code_list, begin_date, end_date)` | 余额 |
| `mcp_convertible_bond_conversion(code_list)` | 转股情况 |
| `mcp_convertible_bond_conversion_change(code_list, begin_date, end_date)` | 转股变化 |
| `mcp_convertible_bond_adjustment(code_list, begin_date, end_date)` | 条款调整 |
| `mcp_convertible_bond_redemption(code_list)` | 强赎 |
| `mcp_convertible_bond_resale(code_list)` | 回售 |
| `mcp_convertible_bond_terms(code_list)` | 条款 |
| `mcp_convertible_bond_resale_notice(code_list, begin_date, end_date)` | 回售提示 |
| `mcp_convertible_bond_redemption_notice(code_list, begin_date, end_date)` | 强赎提示 |
| `mcp_convertible_bond_suspension(code_list, begin_date, end_date)` | 停复牌 |

### 其他
| 工具 | 用途 |
|---|---|
| `mcp_backward_factor(code_list)` | 后复权因子 |
| `mcp_search_manual(keyword, max_chars)` | 检索开发手册，不确定接口用法时先用它 |

### Resources
| 资源 | 用途 |
|---|---|
| `amazingdata://doc/manual` | 开发手册目录 |
| `amazingdata://doc/api-summary` | 接口摘要 |

## 典型调用示例

```
1. 查 K 线：
   mcp_kline(code_list=["600519.SH"], begin_date=20240601, end_date=20240901, period="day")

2. 查利润表：
   mcp_income(code_list=["600036.SH"], begin_date=20240101, end_date=20241231)

3. 查指数成分：
   mcp_index_constituent(index_code="000300.SH", date=20240901)
```

## 错误处理

所有工具返回带 `success` 字段的 dict。失败时关注 `error_type`：
- `not_logged_in` → 调 `mcp_get_login_status`，再 `mcp_login`；
- `invalid_parameter` → 检查日期为 8 位整数、代码带交易所后缀；
- `connection_error` / `query_failed` → 缩短日期范围、减少代码数量、稍后重试。


