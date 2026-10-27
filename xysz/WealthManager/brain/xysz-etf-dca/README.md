# Everflow (长流)

中国银河证券星耀数智出品的 ETF 定投专家。资深 ETF 研究员人设，基于 `ad-etf-dca` 技能用真实 K 线数据计算场内 ETF 定投方案，输出可视化 HTML 报告。

## 类型

Agent 型（单个 AI 专家）

## 功能

- **正向测算**：每期金额 + 年限 + 预期年化 → 预估期末资产与 IRR，多情景对比
- **历史回测**：真实 K 线逐期成交回测，输出 XIRR、最大回撤、年化波动、总佣金
- **目标反推三连**：每期该投多少（target_amount）/ 需要多高年化（target_return）/ 需要多久（target_duration）
- **费用与份额真实性建模**：佣金逐笔 `max(金额 × 费率, 最低 5 元)`、份额 1 手取整、非交易日顺延
- **定投方案诊断**：成本透视、标的适配性、止盈规则建议

## 使用示例

- 每月定投2000元到沪深300ETF，坚持10年，按年化8%算，到期末能有多少钱？
- 2020年初到2024年底，每月投3000元到中证500ETF，真实收益怎么样？
- 我想10年攒100万，每月只能投5000，需要多高的年化？还是得投更久？

## 依赖

- 星耀数智 `ad-etf-dca` 技能（AmazingData 行情数据）
- AmazingData 环境变量：`AD_USERNAME` / `AD_PASSWORD` / `AD_HOST` / `AD_PORT`

## 头像

头像已自动生成在 `avatars/` 目录下。如需替换为自定义头像，要求：
- 格式：PNG（推荐）或 JPG
- 尺寸：512×512 px
- 大小：单张不超过 500KB

## 内置技能

本专家包自带以下 Skill（位于 `skills/` 目录），安装后无需额外下载即可调用：

| Skill | 能力 |
|-------|------|
| `ad-api` | 星耀数智金融数据 API：三张报表、行情、股东、公告等原始数据 |
| `ad-etf-dca` | 场内 ETF 定投测算与历史回测 |


## 安装

将专家包目录放到专家目录下：

```
~/.workbuddy/plugins/marketplaces/my-experts/plugins/xysz-etf-dca/
```

然后运行注册命令使其可见：

```bash
python3 scripts/register_expert.py <expert-dir>
```
