---
name: ad-announcement-analysis
description: 中国银河证券星耀数智公告搜索技能。按分类筛选公告列表，下载PDF原文，转换为Markdown供AI阅读分析。支持股票/ETF/可转债三种标的类型。用户提出公告分析需求时，使用此skill。
---

# 公告搜索 Skill
## 快速上手

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

## 用法

```bash
# 在技能根目录下执行：
cd scripts && python search.py --tag <TAG_ID> [--type stock|fund|bond] [--codes xxx,yyy] [--begin YYYYMMDD] [--pdf]
```

## 工作流

1. 用户提需求 → AI 打开 `references/announcement_categories.md` 查完整 TAG 分类树
2. AI 确定 `--tag` 参数（如 10301=业绩预告, 10408=回购）
3. 执行 `scripts/search.py` 传入参数
4. 不加 `--pdf`：打印公告标题列表，AI 简要回答
5. 加 `--pdf`：下载 PDF → 转 MD → AI 读取 MD 做深度分析

## 参数

| 参数 | 说明 | 示例                              |
|------|------|---------------------------------|
| `--tag` | TAG_ID（必传） | `10301`                         |
| `--type` | stock/fund/bond，默认 stock | `--type bond`                   |
| `--codes` | 逗号分隔代码，不传=全市场 | `--codes 600***.SH,601***.SH`   |
| `--begin` | 起始日期 YYYYMMDD，默认今年元旦 | `--begin 20260601`              |
| `--end` | 结束日期 YYYYMMDD，默认今天 | `--end 20260716`（示例，动态取值）       |
| `--pdf` | 下载 PDF 并转为 Markdown | `--pdf`                         |
| `--limit` | 最多显示 N 条标题（默认全部） | `--limit 50`                    |
| `--local` | 使用本地缓存数据（默认从服务器拉取最新） | `--local`                       |
| `--local-path` | AD 本地数据根目录 | 默认 `D:/AmazingData_local_data/` |

## 示例

```bash
# 全市场股票业绩预告
python scripts/search.py --tag 10301

# 只看前 30 条
python scripts/search.py --tag 10301 --limit 30

# 指定股票，下载PDF转MD
python scripts/search.py --codes 600***.SH,601***.SH --tag 10301 --pdf

# 可转债回购公告
python scripts/search.py --type bond --tag 10408 --begin 20260601

# 全市场股权质押，下载原文
python scripts/search.py --tag 10509 --pdf

# 使用本地缓存（不从服务器拉取）
python scripts/search.py --tag 10301 --local
```

## 注意事项

1. 所有数据接口调用前必须先通过环境变量配置认证信息，然后调用`ad.login()`登录
2. 必须设置以下4个环境变量：`AD_USERNAME`、`AD_PASSWORD`、`AD_HOST`、`AD_PORT`
3. 账号、密码、IP和端口需联系开户营业部申请
4. `MarketData`实例化时必须传入交易日历：`ad.MarketData(base_data.get_calendar())`
5. 支持本地数据缓存（local_path + is_local）和指定日期范围（begin_date + end_date）两种模式，二选一
6. AmazingData限制单点登录，所以同一时间只能有一个AmazingData的登录链接

## Python环境要求

- Python版本: 3.8-3.14
- 操作系统: Linux/Windows
- 依赖包: tgw>=1.0.8.5, AmazingData>=1.0.24