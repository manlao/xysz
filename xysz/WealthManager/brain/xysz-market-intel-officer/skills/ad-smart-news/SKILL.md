---
name: ad-smart-news
display_name: 星耀数智智读新闻
display_name_en: Xingyao Smart News Reader
version: 1.1.0
author: 中国银河证券
description: 中国银河证券星耀数智智读新闻技能。查询指定股票的新闻明细，多源去重归并、事实性主题分类、客观统计（按日分布/媒体来源/范围分层/热度TOP/舆情环比），新闻原文html自动下载本地供AI阅读。纯事实整理，不做倾向性判断。用户提出新闻查询、舆情整理、事件梳理、媒体报道汇总等需求时，使用此skill。
description_zh: 中国银河证券星耀数智智读新闻技能。查询指定股票的新闻明细，多源去重归并、事实性主题分类、客观统计（按日分布/媒体来源/范围分层/热度TOP/舆情环比），新闻原文html自动下载本地供AI阅读。纯事实整理，不做倾向性判断。用户提出新闻查询、舆情整理、事件梳理、媒体报道汇总等需求时，使用此skill。
description_en: China Galaxy Securities Xingyao smart news skill. Fetch news details for a given stock with multi-source deduplication, factual topic classification and objective statistics (daily distribution, media sources, scope layers, heat ranking, sentiment change), with original HTML downloaded locally for AI reading. Purely factual, no directional judgment.

---

# 智读新闻 Skill

## 快速上手

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

## 用法

```bash
# 在技能根目录下执行：
cd scripts && python search.py --codes <CODES> [--begin YYYYMMDD] [--end YYYYMMDD] [--limit N]
```

## 工作流

1. 用户提需求 → AI 确定股票代码与日期范围（默认近7天）；用户说"全市场"时 `--codes all`（自动先取全部A股代码，再分批拉取）
2. 执行 `scripts/search.py` 拉取新闻（接口自动下载原文html到本地）
3. 输出：去重后新闻列表（日期/标题/来源/范围分层/主题标签/转载数）+ 统计概览（原始→去重条数、按日分布、来源TOP5、范围分层、主题分布、热度TOP）+ 原文html目录
4. 用户问特定类型事件时加 `--topic` 过滤（如 `--topic 增减持,回购分红`），减少 AI 阅读量
5. 用户问"关注度是否上升"时加 `--prev` 输出舆情热度环比（本期 vs 上一等长区间报道量，纯计数）
6. AI 按需做事实性整理（见下方"AI 整理工作流"），需要原文细节时读取 html 目录下文件
7. 字段含义查 `references/news_fields.md`

## 参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--codes` | 股票代码（必传），逗号分隔；传 `all`（或 `全市场`）取全部A股 | `--codes 601***.SH,600***.SH` / `--codes all` |
| `--begin` | 起始日期 YYYYMMDD，默认近7天 | `--begin 20260915` |
| `--end` | 结束日期 YYYYMMDD，默认今天 | `--end 20260922` |
| `--limit` | 最多显示 N 条（默认全部） | `--limit 50` |
| `--topic` | 按主题过滤，逗号分隔（可选值见统计概览的主题分布） | `--topic 增减持,监管处罚` |
| `--prev` | 输出舆情热度环比：对比上一等长区间报道量（纯计数） | `--prev` |
| `--local` | 使用本地缓存数据（默认从服务器拉取最新） | `--local` |
| `--local-path` | AD 本地数据根目录 | 默认 `D:/AmazingData_local_data/` |

## 示例

```bash
# 某股票近7天新闻
python scripts/search.py --codes 601***.SH

# 指定区间
python scripts/search.py --codes 601***.SH --begin 20260901 --end 20260922

# 多只股票，只看前50条
python scripts/search.py --codes 601***.SH,600***.SH --limit 50

# 全市场新闻（自动先取全部A股代码，再分批拉取合并）
python scripts/search.py --codes all
python scripts/search.py --codes all --begin 20260922 --end 20260926 --prev

# 使用本地缓存（不从服务器拉取）
python scripts/search.py --codes 601***.SH --local
```

## AI 整理工作流（三种模式，均为纯事实层）

### 模式一：单事件深读（用户问"这件事怎么回事"）
1. 从列表选定事件，读取对应 html 原文
2. 提取事件要素：时间、主体、事件类型、关键数字（金额/比例/期限）、进展阶段
3. 串联时间线：按 publish_time 排列事实演进
4. 媒体覆盖事实：首发源、多少家报道、各家的表述

### 模式二：区间汇总（用户问"最近有什么新闻"）
1. 按主题分类汇总（工具已给初分类标签，AI 可修正"其他"类）
2. 每个主题列出代表性事实（标题+日期+关键内容）
3. 报道密度：哪几天报道密集（只报数，不解读）
4. 范围分层：全市场/行业/个股三层分开总结

### 模式三：跟踪比对（用户问"和之前比有什么变化"）
1. 口径对比：不同信源对同一事件的表述差异，并列呈现不评判
2. 进展对比：同一事件新旧披露的事实变化（如金额、期限、范围的更新）

## 合规约束（必须遵守）

1. 输出仅限事实性整理——谁、何时、何事、说了什么
2. **严禁**出现 利好/利空/负面/正面/预警/看多/看空/建议买入/建议卖出 等倾向性表述
3. 主题分类标注的是事件**类型**（如"监管处罚"），不是影响**判断**
4. 输出不构成投资建议，需注明数据来源为新闻报道

## 注意事项

1. 所有数据接口调用前必须先通过环境变量配置认证信息，然后调用`ad.login()`登录
2. 必须设置以下4个环境变量：`AD_USERNAME`、`AD_PASSWORD`、`AD_HOST`、`AD_PORT`
3. 账号、密码、IP和端口需联系开户营业部申请
4. AmazingData限制单点登录，所以同一时间只能有一个AmazingData的登录链接
5. 全市场模式：`--codes all` 先取全部A股代码（沪深北），再按每批 500 只分批拉取；列表默认显示前 50 条（统计概览为全量）；首次运行 html 详情下载量大耗时较长，之后走增量缓存
6. 支持本地数据缓存（local_path + is_local）和指定日期范围（begin_date + end_date）两种模式

## Python环境要求

- Python版本: 3.8-3.14
- 操作系统: Linux/Windows
- 依赖包: tgw>=1.0.8.7, AmazingData>=1.1.15
