# 研报摘要字段说明

`get_report_abstract` 返回 dict：key 为股票代码（无标的研报为 `'0'`），value 为该代码的研报摘要 DataFrame。

## 字段列表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 研报摘要 id（MD 文件以此命名） |
| title | string | 题目 |
| des | string | 研报摘要正文 |
| date | string | 发布日期 |
| author | string | 作者 |
| source | string | 发布机构 |
| bcpj | string | 评级（如 买入/增持/中性等，由研报机构给出） |
| pjbh | string | 评级变动（如 上调/下调/维持/首次等） |
| symbol | string | 标的代码 |
| industry | string | 行业 |
| prmax | float | 目标价上限 |
| prmin | float | 目标价下限 |
| classify | string | 研报类型 |
| update_date | string | 更新日期 |

## 使用约定

1. 评级(bcpj)、评级变动(pjbh)、目标价(prmin/prmax)均为**研报机构的观点**，
   skill 输出仅做转述与计数统计，不添加任何倾向性概括。
2. 目标价统计取上下限中点计算均值/中位数。
3. `--codes 0` 表示获取无标的代码的其他研报摘要（宏观/策略等）。
4. `save_report_abstract_md` 以摘要 id 命名逐条保存 Markdown，已存在自动跳过（增量），
   每份 MD 以 `# 题目` 开头，附日期/作者/来源/行业/标的/评级/分类等元信息。
