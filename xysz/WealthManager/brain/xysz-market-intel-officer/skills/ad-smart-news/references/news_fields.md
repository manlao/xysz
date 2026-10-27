# 新闻字段说明

新闻接口为两步式（手册 §3.5.18）：
1. `get_news_list` → news_list：dict，key 为股票代码，value 为新闻列表 DataFrame
2. `get_news_detail_html(news_list)` → news_detail_html_dir：按 news_id 下载详情并保存为 html（增量跳过已存在），返回 html 目录

## get_news_list 列表字段

| 字段 | 类型 | 说明 |
|------|------|------|
| news_id | string | 新闻 id（html 文件以此命名） |
| stock_code | string | 代码 |
| create_date | string | 创建日期 |
| data_status | int | 数据状态 |

注：列表不含标题等明细字段，明细信息在 html 文件内。

## get_news_detail_html 生成的 html

- 以 news_id 命名，UTF-8 编码，viewport 适配移动端，浅色卡片风格
- 页面结构：`<h1>` 标题 + `<ul class="meta-list">` 元信息（摘要/来源/作者/发布时间/新闻范围，字段为空自动省略）+ 正文（提取 content 中 body 内部内容）
- 新闻范围映射：0-无、1-按全市场、2-按行业、3-按个股
- 明细 DataFrame（skill 内部从 html 解析）：news_id/title/summary/source/author/publish_time/ranges/stock

## 使用约定

1. AI 需要原文细节时直接读取 html 目录下的文件。
2. 多源转载：归一化标题相同视为同一事件，去重保留最早一条；报道数按组内去重
   news_id 计数（同一新闻挂多只股票只算 1 条报道，避免高估）。
3. 主题标签为关键词规则的**事实性初分类**（业绩披露/并购重组/监管处罚/高管变动/
   回购分红/增减持/业务动态/行业政策/宏观/其他），打不准标"其他"，由 AI 精读时修正。
   高管变动按动作词（辞职/聘任/离任等）匹配，不按人物头衔词。
