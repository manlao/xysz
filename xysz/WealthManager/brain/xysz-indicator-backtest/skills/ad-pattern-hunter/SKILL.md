---
name: ad-pattern-hunter
display_name: 星耀数智形态猎手
display_name_en: Xingyao Pattern Hunter
version: 1.1.0
author: 中国银河证券
description: "中国银河证券星耀数智形态猎手技能。内置34类K线形态识别引擎，分四大族：趋势延续（强趋势延续、趋势回踩、上升通道、上升旗形、三角旗形、阴跌通道、下降旗形）、底部反转（底部反转、V形底、圆弧底、W底、三重底、头肩底、杯柄形、塔形底、岛形底、喇叭形底）、顶部反转（顶部反转、V形顶、圆弧顶、M头、三重顶、头肩顶、塔形顶、岛形顶、喇叭形顶）、整理突破（箱体、上升三角形、下降三角形、对称三角形、上升楔形、下降楔形、平台突破）；规则命中与形状相似度双层评分，支持沪深300/500/1000成分股及全A形态雷达扫描，自动生成可视化HTML报告（K线叠加模板轮廓与评分明细）；支持13个K线周期（分钟至年线），阈值按周期缩放；支持手绘图/K线截图轮廓点列与自定义描述轮廓全池匹配，及单票形态诊断。适用于K线形态、形态选股、形态雷达、双底、双顶、头肩底、头肩顶、三重底、三重顶、圆弧底、圆弧顶、V形反转、三角形、箱体、旗形、楔形、喇叭形、岛形反转、杯柄形、平台突破、形态匹配等场景。仅供形态相似度研究，不构成投资建议。"
description_zh: "中国银河证券星耀数智形态猎手技能。内置34类K线形态识别引擎，分四大族：趋势延续（强趋势延续、趋势回踩、上升通道、上升旗形、三角旗形、阴跌通道、下降旗形）、底部反转（底部反转、V形底、圆弧底、W底、三重底、头肩底、杯柄形、塔形底、岛形底、喇叭形底）、顶部反转（顶部反转、V形顶、圆弧顶、M头、三重顶、头肩顶、塔形顶、岛形顶、喇叭形顶）、整理突破（箱体、上升三角形、下降三角形、对称三角形、上升楔形、下降楔形、平台突破）；规则命中与形状相似度双层评分，支持沪深300/500/1000成分股及全A形态雷达扫描，自动生成可视化HTML报告（K线叠加模板轮廓与评分明细）；支持13个K线周期（分钟至年线），阈值按周期缩放；支持手绘图/K线截图轮廓点列与自定义描述轮廓全池匹配，及单票形态诊断。适用于K线形态、形态选股、形态雷达、双底、双顶、头肩底、头肩顶、三重底、三重顶、圆弧底、圆弧顶、V形反转、三角形、箱体、旗形、楔形、喇叭形、岛形反转、杯柄形、平台突破、形态匹配等场景。仅供形态相似度研究，不构成投资建议。"
description_en: "China Galaxy Securities Xingyao Pattern Hunter skill. Rule-based engine for 34 classic chart patterns in four families: trend continuation (strong trend, pullback, channel, flag, pennant), bottom reversal (V bottom, rounding bottom, double and triple bottom, head-and-shoulders, cup with handle, tower and island bottom, broadening bottom), top reversal (mirrored), and consolidation breakout (range, triangles, wedges). Dual-layer scoring: rule hits plus normalized shape correlation. Scans CSI 300/500/1000 constituents or all A-shares across 13 timeframes with per-timeframe scaled thresholds; also matches profiles from hand-drawn sketches or chart screenshots; single-stock diagnosis supported. Visual HTML report with candlestick, profile overlay and score details. Use for chart pattern scanning and screening, double bottoms and tops, head-and-shoulders, triangles, wedges, islands, breakouts, shape matching. Research only, not investment advice."

---

# 形态猎手 Skill（ad-pattern-hunter）

## 概述

形态猎手基于星耀数智（AmazingData）前复权日线数据，在本地完成 K 线形态识别与全池扫描：

- **34 类形态**分四大族：趋势延续类（8）、底部反转类（10）、顶部反转类（9）、整理突破类（7）；
- **两层评分（0-100）**：规则命中分 × 60% + 形状相似分 × 40%。规则分由可解释子规则（极值点结构、斜率、回撤、位置、量能）加权命中得到；相似分为窗口 z-score 归一化后与该形态标准模板轮廓的 Pearson 相关；
- **三种输入**：固定模板词（走雷达扫描）、手绘图/截图轮廓点列（走轮廓匹配）、自定义文字描述（AI 生成轮廓后走轮廓匹配）；
- **输出**：控制台中文摘要 + 可视化 HTML 报告（K线图与模板轮廓叠加、评分分项、规则命中明细）+ 结构化 JSON。

结果仅用于形态相似度研究，不构成投资建议。

## 前置条件

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
## 使用方法

以下命令中的解释器与路径按实际环境调整（需为已安装 tgw 与 AmazingData 的 Python 环境）：

```bash
python run_analysis.py scan --pattern w_bottom --universe index_all --window 120 --top-n 10
```

### 模式一：模板雷达扫描（scan）

```bash
# 扫描某一类形态（沪深300+中证500+中证1000 成分股合集）
python run_analysis.py scan --pattern w_bottom --universe index_all --window 120

# 全部 34 类形态一次扫描
python run_analysis.py scan --pattern all --universe index300

# 全市场 A 股（约 5000+ 只，首次运行较慢，建议避开交易时段）
python run_analysis.py scan --pattern all --universe allA --window 120
```

### 模式二：外部轮廓匹配（profile）

手绘走势图 / K线截图 / 自定义描述先转为归一化轮廓点列 JSON（见下文「输入路由规则」），再全池匹配：

```bash
python run_analysis.py profile --profile points.json --universe index_all --window 120
```

轮廓 JSON 格式：

```json
{
  "points": [0.52, 0.48, 0.31, 0.35, 0.18, 0.42, 0.61, 0.58, ...],
  "note": "手绘W底右侧抬升，含前置下跌"
}
```

- `points`：纵轴归一化轮廓点列，长度 ≥ 8（推荐 120 点），横轴均匀分布；价格尺度无关，引擎内部做 z-score 归一化；
- `note`：可选，轮廓的文字说明。

### 模式三：单票诊断（check）

```bash
python run_analysis.py check --code 600519.SH --window 120
```

输出该股窗口内 34 类形态的完整评分表与最匹配形态的规则命中明细。

### 输入路由规则

按用户输入选择通道，三条路汇入同一匹配引擎：

1. **图片输入（手绘图 / K线截图）必须直接走图**：由 AI 多模态读取原图，从左到右均匀提取约 120 个相对高度点（归一化到 0~1 或任意尺度均可），写入 `points` 字段后调用 `profile` 模式。**不要**把图片改写成文字描述再搜，**不要**重新绘制合成图；
2. 图片类型不清楚时，先问一句：「这是手绘走势图，还是 K 线截图？」手绘/单线走势按轮廓提取；真实 K 线截图建议裁剪至仅保留主图区域后按其走势轮廓提取；
3. **固定模板词优先走 `scan`**：用户说出下表中的模板词及其同义说法时，直接调用对应形态扫描，不要让 AI 临时生成轮廓；
4. 只有用户描述的是**自定义形态**（非固定模板词）且没有图片时，才由 AI 依据描述生成 120 点轮廓 JSON，走 `profile` 模式；
5. 参数不全时先确认：用户未说周期与窗口时，询问「你想按哪个周期和长度匹配？日线 120 BAR / 日线 60 BAR（当前版本支持日线）」；只有用户说「默认」「你看着办」时才用日线 120 BAR、成分股合集池、Top10；
6. 手绘 W 底 / M 头提醒：轮廓应包含**前置趋势**（W 底先有一段下跌、M 头先有一段上涨），只画最后一个 W/M 会显著降低匹配质量。

### 模板词映射表

| 用户说法（含同义词） | 形态 ID |
|---|---|
| 强趋势延续、强趋势、主升浪 | strong_trend |
| 趋势回踩、均线回踩、突破回踩、回踩不破 | trend_pullback |
| 上升通道、稳步上涨、慢牛爬坡 | channel_up |
| 上升旗形、急涨后窄幅整理 | flag_up |
| 阴跌通道、下降通道、阴跌不止 | channel_down |
| 下降旗形、急跌后窄幅反弹 | flag_down |
| 三角旗形（多）、急涨后收敛整理 | pennant_up |
| 三角旗形（空）、急跌后收敛整理 | pennant_down |
| 杯柄形、杯柄、圆弧底+柄 | cup_handle |
| 塔形底、平底反转（底） | tower_bottom |
| 塔形顶、平底反转（顶） | tower_top |
| 岛形底、岛形反转（底）、跳空缺口反转（底） | island_bottom |
| 岛形顶、岛形反转（顶）、跳空缺口反转（顶） | island_top |
| 喇叭形底、扩散形（底） | broadening_bottom |
| 喇叭形顶、扩散形（顶）、扩三角 | broadening_top |
| 上升楔形、上倾收敛楔形 | rising_wedge |
| 下降楔形、下倾收敛楔形 | falling_wedge |
| 底部反转、筑底、低位转强、底部抬升 | bottom_reversal |
| V形底、急跌后V型反弹 | v_bottom |
| 圆弧底、弧形底、碟形底 | round_bottom |
| W底、双底、二次探底 | w_bottom |
| 三重底 | triple_bottom |
| 头肩底 | head_shoulder_bottom |
| 顶部反转、筑顶、高位滞涨、顶部风险 | top_reversal |
| V形顶、急涨后V型回落 | v_top |
| 圆弧顶、穹形顶、碟形顶 | round_top |
| M头、双顶、二次冲顶回落 | m_top |
| 三重顶 | triple_top |
| 头肩顶 | head_shoulder_top |
| 箱体、震荡整理、横盘整理、平台整理 | range_consolidation |
| 上升三角形 | ascending_triangle |
| 下降三角形 | descending_triangle |
| 对称三角形、收敛三角形 | symmetrical_triangle |
| 平台突破、放量突破、突破平台 | breakout |

## 参数说明

| 参数 | 取值 | 默认 | 说明 |
|---|---|---|---|
| `command` | scan / profile / check | 必填 | 扫描 / 轮廓匹配 / 单票诊断 |
| `--pattern` | 34 类形态 ID（逗号分隔）或 all | all | scan 模式的形态集合 |
| `--profile` | 轮廓 JSON 路径 | 必填（profile 模式） | 见上文格式 |
| `--universe` | index300 / index500 / index1000 / index_all / allA | index_all | 股票池；index_all 为三大指数成分合集（去重约 1800 只） |
| `--timeframe` | min1/min3/min5/min10/min15/min30/min60/min120/day/week/month/season/year | day | K线周期，共 13 个；幅度阈值按周期经验缩放（见 references/pattern_definitions.md §0.6） |
| `--window` | 30 / 60 / 120 | 120 | 匹配窗口 BAR 数 |
| `--top-n` | 正整数 | 10 | 重点候选数量 |
| `--min-score` | 0-100 | 50 | 命中分数线；profile 模式下约束**形状相似分**（模板扫描模式约束总分） |
| `--begin` / `--end` | YYYYMMDD | 近一年 | 扫描区间 |
| `--code` | 如 600519.SH | 必填（check 模式） | 单票诊断对象 |

## 输出报告内容

- **控制台**：登录与数据进度、命中汇总（按形态族分组、各形态命中数与 Top1）、重点候选 TopN 列表；
- **HTML 报告**（`output/pattern_hunter/scan_时间戳.html`）：
  - KPI 行：参与扫描数、命中条数、命中形态数、重点候选数、数据不足跳过数；
  - 重点候选卡片：前复权 K 线图（ECharts）+ 该形态标准模板轮廓叠加 + 成交量，附总分/规则分/相似分/相关系数与逐条规则命中标签；
  - 命中明细表：按形态族与形态分组，总分降序；
  - 评分口径说明；
- **JSON 结果**（`output/pattern_hunter/scan_时间戳.json`）：重点候选的完整结构化字段，供 AI 或程序后续消费。

## 匹配算法说明

各形态的结构定义、子规则与阈值详见 `references/pattern_definitions.md`。要点：

- 识别基于**前复权**日线收盘价的 z-score 归一化窗口序列与局部极值点（pivot）结构；
- 底部类与顶部类互为镜像（同一套结构规则，方向取反），保证口径一致；
- 总分 = 规则命中分 × 60% + 形状相似分 × 40%；候选需同时过两道门槛：规则分达到该形态门槛（默认 30 分），总分达到命中分数线（默认 50 分；宽结构形态如 W底/M头/杯柄形等设有更高的形态级总分门槛，保证区分度）；profile 模式下分数线约束相似分；
- 相似分的模板轮廓为各形态的标准形状函数（如 W 底为标准 W 曲线），profile 模式下替换为外部轮廓。

## 注意事项

1. 所有数据接口调用前必须先通过环境变量配置认证信息，然后调用 `ad.login()` 登录；
2. 必须设置以下4个环境变量：`AD_USERNAME`、`AD_PASSWORD`、`AD_HOST`、`AD_PORT`（端口必须为整数）；
3. AmazingData 限制单点登录，同一账号多处同时登录会互踢；脚本内置登录失败自动重试一次；
4. 前复权采用累计后复权因子归一化（`get_backward_factor`，F(d)=bf(d)/bf(区间末日)），不使用单次复权因子 `get_adj_factor`；无复权因子的股票按不复权处理并打印警告；
5. 全市场（allA）扫描约 5000+ 只，K 线按 100 只/批分批拉取，首次运行耗时较长（数十分钟量级），建议先用 index300 / index_all 验证；`local_path` 本地缓存可加速二次运行；
6. 长期停牌、次新股等窗口内 K 线不足的股票会自动跳过并在结果中注明数量；
7. 多周期说明：非日线周期下幅度类阈值（涨跌幅/回撤/振幅等）按周期经验缩放（如 60 分钟 ×0.62、周线 ×1.6、月线 ×2.2），z 域斜率/R²/相对比例不缩放；缩放因子为方法论经验常量；
8. 分钟周期单股数据量大，建议搭配 index300/index_all 使用；全A × min1 属重度查询；形态命中不代表未来走势，不构成任何投资建议，结果仅供形态相似度研究。
9. season/year 周期注意：A 股历史约 35 年，年线全历史仅 ~35 根、季线 ~140 根——这两个周期下 window 建议选 30（year×120 需 120 年数据，必然全部跳过）；

## Python环境要求

- Python版本: 3.8-3.14
- 操作系统: Linux/Windows
- 依赖包: tgw>=1.0.8.7, AmazingData>=1.1.15, numpy, pandas, scipy
