---
name: ad-watchlist
description: 中国银河证券星耀数智自选股管理技能。可本地存储自选股及分组信息，支持多分组管理、自定义分组名称，支持单只 / 批量增减、个股检索，自动生成包含行情、基本面数据的展示页面。
---

# 自选股管理 (ad-watchlist)

基于银河证券「星耀数智」(AmazingData) 数据接口，把自选股与分组信息存进本地 **SQLite**，
提供分组管理、增删改查、搜索，并自动补全行情与基本面、生成 HTML 展示页。
全部通过命令行 `python watchlist.py` 执行。

## 能力覆盖

1. 自选股分组 — 创建 / 重命名 / 列表 / 删除
2. 添加自选股 — 单只 / 批量（联网，自动补全名称、行情、基本面）
3. 删除自选股 — 单只 / 批量
4. 查询展示 — 列表、详情、关键词搜索、CSV 导出
5. HTML 网页 — 分组标签页、分页、排序、前端筛选，增删改后自动重写


- 安装python运行环境(推荐python3.8/3.9/3.10/3.11/3.12/3.13环境)，并安装AmazingData依赖包。
从https://gitee.com/cgs2026/xysz clone整个项目，再用xysz_tools下的wheel文件安装tgw和AmazingData。
```bash
pip install tgw>=1.0.8.7
pip install AmazingData>=1.1.4
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

## 关键行为规则

### 联网要求
- **添加（add/add-batch）和刷新（--refresh）必须联网**才能补全行情与基本面。
- **查询（list/info/search/html/export）支持离线**（`--no-api` 下照常运行）。
- 离线模式下添加/刷新操作直接拒绝，提示需要联网。

### 数据刷新时机
- **当日首次调用**：若当天尚未刷新过，先对全市场自选股做一次全量刷新，再执行具体命令。
- **每次添加**（单只/批量）：重算该分组全部股票的最新数据，并自动重写 HTML。
- **`--refresh`**：强制全量重算，忽略当日已刷新标记。
- 删除操作也会自动重写 HTML。

### 结果展示
- **任何增删改操作完成后，必须自动打开 HTML 展示页给用户看**。HTML 直接生成在当前工作空间下的 `data/watchlist.html`。
- 查询类操作（list/search/info）用文本输出即可，不必打开 HTML。

### 数据库
- SQLite 库文件默认 `data/watchlist.db`，可用 `--db` 指定。
- 三张表：`groups` / `stocks` / `meta`，详见 [references/database-schema.md](references/database_schema.md)。

### 自选价格
- 不指定 `-p` 时，自选价自动取添加时的最新价。
- 自选收益 = (最新价 - 自选价) / 自选价 × 100。

## 数据字段概览

每只自选股包含基础信息（代码/名称/市场/板块/自选原因）、行情（最新价/涨跌/成交额/本周本月今年涨幅）、基本面（PB/PE/股本/市值）及衍生指标（自选收益），共 18 个字段。完整字段定义见 [references/data-fields.md](references/data_fields.md)。

## 参考文档

| 文档 | 说明 |
|------|------|
| [references/cli-reference.md](references/cli_reference.md) | CLI 参考 — 全局参数、分组/添加/查询/删除/导出全部命令示例 |
| [references/data-fields.md](references/data_fields.md) | 数据字段 — 所有 18 个字段的含义和计算方式 |
| [references/database-schema.md](references/database_schema.md) | 数据库 Schema — 三张表的完整列定义与约束 |

## 注意事项

1. 星耀数智的数据接口调用前必须先通过环境变量配置认证信息，然后调用`ad.login()`登录
2. 必须设置以下4个环境变量：`AD_USERNAME`、`AD_PASSWORD`、`AD_HOST`、`AD_PORT`
3. 账号、密码、IP和端口需联系开户营业部申请
4. AmazingData限制单点登录，所以同一时间只能有一个AmazingData的登录链接