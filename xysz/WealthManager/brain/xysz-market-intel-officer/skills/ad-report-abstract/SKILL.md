---
name: ad-report-abstract
display_name: 星耀数智研报摘要
display_name_en: Xingyao Research Report Digest
version: 1.1.0
author: 中国银河证券
description: 中国银河证券星耀数智研报摘要技能。查询指定股票的研报摘要（标题/机构/评级/目标价），输出机构观点客观统计，可逐条保存为Markdown供AI精读。仅转述与计数，不做倾向性判断。用户提出研报摘要、机构观点、评级统计、分析师观点等需求时，使用此skill。
description_zh: 中国银河证券星耀数智研报摘要技能。查询指定股票的研报摘要（标题/机构/评级/目标价），输出机构观点客观统计，可逐条保存为Markdown供AI精读。仅转述与计数，不做倾向性判断。用户提出研报摘要、机构观点、评级统计、分析师观点等需求时，使用此skill。
description_en: China Galaxy Securities Xingyao research report digest skill. Query broker report digests (title, institution, rating, target price) for a given stock, output objective statistics on institutional views, and save each report as Markdown for detailed AI reading. Neutral transcription and counting only, no directional judgment.

---

# 研报摘要 Skill

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
cd scripts && python search.py --codes <CODES> [--begin YYYYMMDD] [--end YYYYMMDD] [--md] [--limit N]
```

## 工作流

1. 用户提需求 → AI 确定股票代码与日期范围
2. 执行 `scripts/search.py` 拉取研报摘要
3. 输出：研报列表（日期/标题/机构/作者/评级/评级变动/目标价区间/类型）+ 机构观点统计（覆盖机构数、评级分布、评级变动、目标价统计）+ 观点共识度（评级TOP1占比、目标价分歧跨度，纯计数）
4. 用户关注"变化"或"空间"时加 `--changes`：评级变动/首次覆盖明细 + 目标价中位数与最新收盘价的算术对比（比值=目标价中位数/现价，纯计算事实，非投资建议）
5. **`des` 字段是研报摘要正文，最重要的精读素材**：AI 默认加 `--des`（每条附前200字），需要完整内容时加 `--md` 逐条保存 Markdown 后读取对应 id 文件
6. 需要精读时：加 `--md` 逐条保存 Markdown → AI 读取 MD 文件，转述提炼各家核心逻辑、对比观点差异
7. 字段含义查 `references/report_fields.md`

## 参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--codes` | 股票代码（必传），逗号分隔；传 `0` 取无标的研报 | `--codes 601***.SH,600***.SH` |
| `--begin` | 起始日期 YYYYMMDD，默认近30天 | `--begin 20260901` |
| `--end` | 结束日期 YYYYMMDD，默认今天 | `--end 20260922` |
| `--md` | 逐条保存为 Markdown（增量，已存在跳过） | `--md` |
| `--changes` | 输出评级变动/首次覆盖明细 + 目标价vs现价算术对比 | `--changes` |
| `--des` | 列表每条附研报摘要正文（des）前 N 字符，默认200，`--des 400` 可调长 | `--des` |
| `--limit` | 最多显示 N 条（默认全部） | `--limit 50` |
| `--local` | 使用本地缓存数据（默认从服务器拉取最新） | `--local` |
| `--local-path` | AD 本地数据根目录 | 默认 `D:/AmazingData_local_data/` |

## 示例

```bash
# 某股票近30天研报摘要
python scripts/search.py --codes 601***.SH

# 列表附摘要正文（AI 精读首选，不必逐个读MD）
python scripts/search.py --codes 601***.SH --des

# 关注变化：评级变动/首次覆盖明细 + 目标价vs现价
python scripts/search.py --codes 601***.SH --changes

# 指定区间 + 保存MD供精读
python scripts/search.py --codes 601***.SH --begin 20260901 --end 20260922 --md

# 多只股票对比覆盖情况
python scripts/search.py --codes 601***.SH,600***.SH

# 无标的研报（宏观/策略等）
python scripts/search.py --codes 0 --md

# 使用本地缓存（不从服务器拉取）
python scripts/search.py --codes 601***.SH --local
```

## AI 精读工作流（--md 之后）

1. 读取 MD 目录下的研报摘要文件（以摘要id命名）
2. 逐篇转述核心逻辑：投资要点、盈利预测、估值方法
3. 对比不同机构观点差异：关注因素、结论分歧点
4. 汇总为客观的机构观点综述

## 合规约束（必须遵守）

1. 评级、目标价均为**研报机构发布的观点**，输出只做转述与计数统计
2. 严禁添加 利好/利空/看多/看空/建议买入/建议卖出 等倾向性表述
3. 输出不构成投资建议，需注明数据来源为券商研报摘要

## 注意事项

1. 所有数据接口调用前必须先通过环境变量配置认证信息，然后调用`ad.login()`登录
2. 必须设置以下4个环境变量：`AD_USERNAME`、`AD_PASSWORD`、`AD_HOST`、`AD_PORT`
3. 账号、密码、IP和端口需联系开户营业部申请
4. AmazingData限制单点登录，所以同一时间只能有一个AmazingData的登录链接
5. 支持本地数据缓存（local_path + is_local）和指定日期范围（begin_date + end_date）两种模式

## Python环境要求

- Python版本: 3.8-3.14
- 操作系统: Linux/Windows
- 依赖包: tgw>=1.0.8.7, AmazingData>=1.1.15
