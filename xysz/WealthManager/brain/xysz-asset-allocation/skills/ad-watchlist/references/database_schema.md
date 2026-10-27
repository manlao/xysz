# 数据库 Schema

使用 SQLite，库文件默认路径：`data/watchlist.db`。

## 表结构

### groups — 分组

| 列名 | 类型 | 约束 |
|------|------|------|
| id | INTEGER | PRIMARY KEY |
| name | TEXT | UNIQUE, NOT NULL |
| description | TEXT | — |
| created_at | TEXT | — |
| updated_at | TEXT | — |

### stocks — 自选股

| 列名 | 类型 | 约束 |
|------|------|------|
| id | INTEGER | PRIMARY KEY |
| group_id | INTEGER | FOREIGN KEY → groups(id), ON DELETE CASCADE |
| code | TEXT | NOT NULL |
| name | TEXT | — |
| market | TEXT | — |
| list_plate | TEXT | — |
| watch_reason | TEXT | 由旧列 `note` 迁移而来 |
| added_at | TEXT | — |
| updated_at | TEXT | — |
| watch_time | TEXT | 添加时间 |
| watch_price | REAL | 自选价格 |
| last_price | REAL | 最新价（前复权） |
| change_val | REAL | 涨跌额 |
| change_pct | REAL | 涨跌幅 % |
| amount | REAL | 成交额 |
| volume | REAL | 成交量 |
| chg_week | REAL | 本周涨幅 % |
| chg_month | REAL | 本月涨幅 % |
| chg_year | REAL | 今年涨幅 % |
| pb | REAL | 市净率 |
| pe | REAL | 市盈率 TTM |
| tot_share | REAL | 总股本（亿股） |
| float_share | REAL | 流通股本（亿股） |
| tot_mktcap | REAL | 总市值 |
| float_mktcap | REAL | 流通市值 |
| profit_pct | REAL | 自选收益 % |
| data_updated_at | TEXT | 行情数据更新时间 |

**约束与特性**：
- `UNIQUE(group_id, code)` — 同一分组内股票代码不可重复
- 删除分组时级联删除其下所有股票（`ON DELETE CASCADE`）
- `tot_share` / `float_share` 库内以**亿股**存储（旧库万股值在迁移时自动换算）
- `watch_reason` 由旧 `note` 列通过 `ALTER TABLE` 迁移补齐

### meta — 运行态标记

| 列名 | 类型 | 约束 |
|------|------|------|
| key | TEXT | PRIMARY KEY |
| value | TEXT | — |

常用 key：
- `last_refresh_date` — 最近一次全量行情刷新日期
- `factor_refresh_date` — 复权因子缓存刷新日期
