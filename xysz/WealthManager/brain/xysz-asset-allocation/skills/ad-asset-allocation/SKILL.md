---
name: ad-asset-allocation
display_name: 星耀数智资产配置
display_name_en: Xingyao Asset Allocation
version: 1.1.0
author: 中国银河证券
description: 中国银河证券星耀数智大类资产配置技能。资产池为黄金(518880)、国债(511010)、宽基(510300/510050/510500/512100/563300 等权合成)、现金(固定年化模拟或短融ETF 511360 实测)，全部前复权（取累计后复权因子归一化）。四种配置方法：固定权重、均值方差(SLSQP+权重边界)、风险平价(等风险贡献)、BL模型(标准He-Litterman后验+MVO，观点JSON输入)。支持历史回测（年/月/周调仓、多模型净值对比、权重演变、绩效表、可视化HTML报告）与当前配置输出。不用于实盘，不构成投资建议。
description_zh: 中国银河证券星耀数智大类资产配置技能。资产池为黄金(518880)、国债(511010)、宽基(510300/510050/510500/512100/563300 等权合成)、现金(固定年化模拟或短融ETF 511360 实测)，全部前复权（取累计后复权因子归一化）。四种配置方法：固定权重、均值方差(SLSQP+权重边界)、风险平价(等风险贡献)、BL模型(标准He-Litterman后验+MVO，观点JSON输入)。支持历史回测（年/月/周调仓、多模型净值对比、权重演变、绩效表、可视化HTML报告）与当前配置输出。不用于实盘，不构成投资建议。
description_en: China Galaxy Securities Xingyao asset allocation skill. Universe - gold (518880), treasury bond ETF (511010), broad-based equity (equal-weight blend of 510300/510050/510500/512100/563300), cash (fixed-yield proxy or short-term bond ETF 511360), all forward-adjusted via normalized cumulative backward-adjustment factors (no event-day link ratio). Four allocation methods - fixed weight, mean-variance (SLSQP with bounds), risk parity (equal risk contribution), Black-Litterman (standard He-Litterman posterior + MVO, views supplied as JSON, collected by asking the user). Historical backtest with yearly/monthly/weekly rebalancing, multi-model NAV comparison, weight evolution, performance table and visual HTML report, plus current allocation output. Not for live trading, not investment advice.

---

# 资产配置 Skill（ad-asset-allocation）

## 快速上手

- 安装python运行环境(推荐python3.8/3.9/3.10/3.11/3.12/3.13/3.14环境)，并安装AmazingData依赖包。
从 https://gitee.com/cgs2026/xysz/releases 下载 tgw 和 AmazingData 的 wheel 文件并安装。
```bash
pip install tgw>=1.0.8.7
pip install AmazingData>=1.1.15
pip install numpy pandas scipy
```
- 实测环境：Python 3.13.9 + AmazingData 1.1.15 + numpy 2.5.3 / pandas 2.3.3 / scipy 1.16.3
- 联系开户营业部申请账号、密码、服务器IP，并设置环境变量：`AD_USERNAME` / `AD_PASSWORD` / `AD_HOST` / `AD_PORT`
  - ⚠️ `AD_PORT` 必须是 **int**（底层 uint16），从环境变量读出后需 `int()` 转换，传字符串会报
    `TypeError: Cfg_server_port_set`
- ⚠️ 直接运行脚本（不走 MCP）时若`import AmazingData` 卡死，需注入
  `NUMBA_CACHE_DIR=<绝对本地目录>`（如 `C:/Users/<user>/AppData/Local/Temp/numba_cache`）与
  `SystemDrive=C:`，详见 `references/model_notes.md`
- 可选：`--local-path D:/AmazingData_local_data/`（AD 本地数据缓存根目录）

## 适用边界

**Use when**：
- 需要黄金/国债/宽基/现金四类资产的历史回测与权重（研究、策略知识讲解、方案演示）
- 对比不同配置方法（固定权重/均值方差/风险平价/BL）在同一资产池上的表现
- 需要把主观观点（如"宽基未来一年涨 8%"）融入配置（BL 观点输入，**AI 须主动向用户提问采集**）

**Not for**：
- 不用于实盘下单与收益承诺；输出为历史统计结果，不代表未来表现
- 不做行业/个股配置（资产池固定为四大类 ETF）
- 不含择时/轮动信号（模型为定期再平衡的静态配置方法）

## 运行前参数确认（AI 必读）

用户在对话中要求回测或配置时，**AI 必须先向用户确认下列参数，确认后再执行命令**；
用户明确说「用默认」或只问概念性问题时（explain 模式）可跳过询问。

| 参数 | CLI | 推荐默认 | 询问话术要点 |
|---|---|---|---|
| 回测区间 | `--period` | 3y（近3年） | 近1年/3年/5年/某自然年度？ |
| 调仓频率 | `--rebalance` | m（月度） | 月度/周度/年度再平衡？ |
| 模型组合 | `--models` | fixed,mv,rp,bl | 四个都跑还是只看某几个？ |
| 风险厌恶 λ | `--lam` | 2.0 | 激进(如1)还是保守(如5)？影响 MV/BL 权重激进度 |
| 权重边界 | `--bounds` | 0,0.6,... 单资产≤60% | 有没有单一资产上限要求（如现金≤40%）？ |
| 估计窗口 | `--lookback` | 244（约1年） | 一般不用改，进阶用户才问 |
| 协方差收缩 | `--shrink` | 0（关） | MV 权重太极端时可建议 0.2 |
| 现金口径 | `--cash-mode` / `--cash-yield` | fixed / 1.8% | 固定年化还是短融ETF实测？收益率多少？ |
| BL 观点 | `--views` | 空=无观点 | **选 BL 就必须主动问用户观点**（见下节），不得自行编造或静默跳过 |
| 固定权重 | `--fixed-weights` | 等权 | 仅 fixed 模型：四类资产各多少比例？ |
| 协方差口径 | `--excess-cov` | 关（原始收益） | 是否剔除系统风险（用沪深300超额收益估 Σ）？ |
| 观点口径 | `--omega` | ratio（标准） | 观点信心水平 conf 的含义按标准比例法（=后验观点权重）解释？ |
| 均值方差窗口 | `--lookback-mv` | 122（半年） | MV 对输入敏感，建议同时开 `--shrink 0.2` |

确认后把参数拼成完整命令执行，用户未表态的项用推荐默认值。例如：
`python search.py --mode backtest --period 1y --models mv,bl --lam 3 --views views.json`

## BL 观点：AI 必须主动向用户提问（AI 必读）

用户选择 BL 模型且**未提供观点**时，AI **必须主动开口向用户提问**，不得自行编造观点、不得静默按"无观点"跑完。
BL 的价值就在于把用户的主观判断注入模型——不问就等于退化成了普通 MVO。

### 第 1 步：先取市场均衡 Π 作为参照系

```bash
python search.py --mode alloc
```

控制台会打印先验 Π。默认口径（244 日窗口、λ=2、等权先验）约为：

| 资产 | 窗口年化 μ | 年化波动 σ | 隐含均衡 Π |
|---|---|---|---|
| 黄金 | 10.4% | 30.1% | **5.9%** |
| 国债 | 2.6% | 0.8% | **0.0%** |
| 宽基 | 3.6% | 20.5% | **3.5%** |
| 现金 | 1.8% | 0.0% | 1.8%（固定年化） |

**提问话术要点：不要问"你觉得黄金能涨多少"**（易得拍脑袋数字），
而是把 Π 摆出来问"**相对市场均衡，你认为该偏离多少**"。

### 第 2 步：向用户提问（必问，按需问 2~3 条）

用 `AskUserQuestion` 一次性把观点问完，选项给区间锚点。**必须问到的两条**：

| 必问项 | 话术 | 选项锚点（Π=参照） | 写进 JSON |
|---|---|---|---|
| 宽基年化预期 | "宽基（沪深300/中证500/中证A500 合成）明年年化收益你看到几个点？市场均衡价是 3.5%" | 悲观 3% / 中性 5% / 乐观 8% | `{"p":{"宽基":1.0},"q":0.05,"conf":0.5}` |
| 黄金相对宽基 | "黄金相对宽基能跑赢几个点？当前均衡是黄金 5.9% vs 宽基 3.5%，即约 2.4 个点" | 跑输 2 点 / 持平 0 点 / 跑赢 3 点 / 强跑赢 5 点 | `{"p":{"黄金":1.0,"宽基":-1.0},"q":0.03,"conf":0.4}` |

**可选追加**（用户主动表达风险偏好时才问）：

| 触发场景 | 话术 | 写进 JSON |
|---|---|---|
| 用户提到避险/市场走弱 | "市场走弱时，国债能顶住宽基多少跌幅？" | `{"p":{"国债":1.0,"宽基":-1.0},"q":0.02,"conf":0.5}` |
| 用户看好黄金绝对点位 | "黄金明年年化你看到几个点？均衡价 5.9%" | `{"p":{"黄金":1.0},"q":0.08,"conf":0.4}` |
| 用户有整体仓位偏好 | "你对总仓位有偏好吗？（如倾向满仓/留现金）" | 用 `--bounds` 表达，不用观点 |

**同时要问清 conf**（信心水平）：若用户说"很确定/比较有把握"→ 0.7；"说不好/大概"→ 0.3；
不表态默认 0.5。**务必向用户解释 conf 的含义是"后验落在该观点上的权重"（0.5 = 五五分）**，
不是"我有多确定"，否则用户会给出 0.9 这种导致权重极端的值。

### 第 3 步：把回答写成 JSON

按 `references/bl_views_example.json` 格式落到 `output/asset_allocation/views_<时间戳>.json`，
再 `--views` 传入。**相对观点必须写成 `1.0/-1.0`**，不能写 `0.1/-0.1`
（P 原样进公式不缩放，0.1/-0.1 配 q=0.03 等于"黄金跑赢宽基 **30** 个百分点"，
实测会把组合推到黄金 100% 满仓；程序已加 `max|p|=1` 归一化防护，但按 1.0/-1.0 书写更清晰）。

**把生成的 JSON 回读给用户确认**，例如"我按你说的写了两条观点：宽基年化 5%（五五把握）、
黄金跑赢宽基 3 个点（四成把握），这样可以吗？"——确认后再跑回测。

### 三条硬约束（提醒用户，必要时调整其观点）

1. **别对国债/现金下绝对观点**。它们 Π≈0，对它们说"年化 3%"等于宣称无风险资产有 3% 超额收益，会把组合推向极端（实测国债单条 3%/conf 0.6 → 黄金 56% + 国债 44%，宽基现金全清零）。要用债券/现金表达观点，请改用**相对观点**。若用户坚持，问清是否知情。
2. **条数 ≤ 资产数（4 条）**。观点数超过资产数时 P 满秩，均衡先验被完全接管，BL 退化成纯主观配置，失去平滑先验的意义。
3. **观点过强要提醒**。若用户给的 q 偏离 Π 超过 5 个百分点或 conf ≥ 0.8，
    提示"这个观点比较激进，权重可能大幅偏移"，并建议先跑
    `param_scan.py --models bl --scan conf` 看权重平均变动% 是否稳定。

若用户对必问两项都选"中性/持平"，生成的 JSON 为（`references/bl_views_example.json` 即此默认档）：

```json
{
  "views": [
    {"p": {"宽基": 1.0}, "q": 0.06, "conf": 0.5},
    {"p": {"黄金": 1.0, "宽基": -1.0}, "q": 0.03, "conf": 0.4}
  ]
}
```

上述配置在默认口径下的实测结果：后验收益 黄金 7.10% / 国债 0.01% / 宽基 4.70% / 现金 0.00%，
权重 黄金 26.7% / 国债 23.6% / 宽基 37.1% / 现金 12.7%（无观点时为等权 25%×4）——
温和偏离均衡、权重变动可控，适合作为默认起点。

## 用法

```bash
cd scripts

# 1) 历史回测（默认近 3 年、月度调仓、四模型对比，输出 HTML 报告 + CSV）
python search.py --mode backtest
python search.py --mode backtest --period 5y --rebalance w          # 近5年周调仓
python search.py --mode backtest --models mv,bl --bounds none      # 只跑两模型、关掉边界
python search.py --mode backtest --views ../references/bl_views_example.json   # 带观点的 BL
python search.py --mode backtest --cash-mode market                # 现金用短融ETF 511360 实测
python search.py --mode backtest --begin 20220101 --end 20241231

# 2) 当前配置（近一年窗口估计，输出各模型权重对比）
python search.py --mode alloc
python search.py --mode alloc --lam 5 --lookback 500

# 3) 策略知识：模型原理讲解（正文在 references/knowledge.md，--topic 取小节标题）
python search.py --mode explain --topic 资产配置
python search.py --mode explain --topic 风险平价
python search.py --mode explain --topic BL观点标定

# 4) 参数标定：conf × λ 网格扫描（观点标定的首选工具）
python param_scan.py --models bl --period 3y --views ../references/bl_views_example.json
python param_scan.py --models bl --period 3y --confs 0.3,0.5,0.7,0.9 --lams 1,2,5
python param_scan.py --models bl --period 3y --excess-cov --out ../output/asset_allocation
```

> **AI 讲解任何概念前，先读 `references/knowledge.md`**——里面已写好四模型原理、
> 前复权/宽基合成/夏普/BL 观点标定等口径说明，不要现编。`--mode explain` 只是
> 该文档的检索入口，主题名即小节标题。

## 模型速览

| 模型 | 一句话 | 关键参数 |
|---|---|---|
| 固定权重 | 按既定比例持有+定期再平衡（默认等权） | `--fixed-weights` |
| 均值方差 | max μᵀw−(λ/2)wᵀΣw，对输入敏感需配边界 | `--lam` `--bounds` `--lookback` `--shrink` |
| 风险平价 | 各资产风险贡献相等，不依赖收益预测 | `--bounds`（建议给现金设上限） |
| BL 模型 | 均衡先验+主观观点→He-Litterman 后验→MVO | `--views` `--lam` `--tau`（默认0.05） |

> `--shrink`（协方差对角收缩，0~0.5）作用于 MV/BL 的 Σ 估计，MV 权重过于集中时可开启（如 0.2）。
> 估计窗口：均值方差默认 122 日（半年，对输入更敏感）、其余默认 244 日；可用
> `--lookback-mv` / `--lookback-bl` 单独覆盖。`--excess-cov` 让 Σ 改用相对沪深300的
> 超额收益协方差（现金保留原始口径），剔除系统风险。

## 输出

输出目录默认 `output/asset_allocation/`（可用 `--out` 指定），文件名均带时间戳，多次运行不覆盖。

- **回测模式 HTML 报告**：净值对比曲线、各模型权重堆叠演变、绩效表（年化/波动/回撤/夏普/卡玛）、
  最新权重表、最近调仓流水、模型与口径说明（fresh-light 风格、移动端适配）
- **回测模式 CSV**：`asset_allocation_backtest_*.html` 同目录下的
  `asset_allocation_nav_<时间戳>.csv`（净值，**只含有效投资期**）、
  `asset_allocation_trades_<时间戳>.csv`（全部调仓流水）、
  `asset_allocation_weights_<时间戳>.csv`（各模型各调仓日权重明细）
- **配置模式（alloc）**：同样输出 HTML 报告（各资产窗口收益/波动卡片 + 各模型权重堆叠条与对比表）
  与 `asset_allocation_alloc_weights_<时间戳>.csv`，便于策略交流场景直接转发
- **控制台**：绩效汇总表 + 最新权重

## 数据口径（重要）

> 各项口径的策略知识版说明在 `references/knowledge.md`（同名小节），本节为速查。

1. **前复权**：全部收益基于前复权价格（含分红再投资）。取星耀数智累计后复权因子
   `get_backward_factor` 并按最新日归一化构建（详见 `references/model_notes.md`）。
   已验证案例：512100 份额合并（2022-09-05）、510300 年度分红。
2. **现金口径**：货币ETF（511880）价格序列不含收益（收益通过份额结转体现），故现金收益
   默认用固定年化 1.8% 模拟（`--cash-yield` 可调），或 `--cash-mode market` 改用短融ETF
   511360 实测收益（年化约 2%、日波动 0.05%、历史最大回撤约 -1%）。实操现金仓位对应 511880。
3. **宽基合成**：5 只宽基 ETF 逐日可得成分等权平均（563300 于 2023-09 上市，此前自动用前 4 只）。
   该合成为**每日等权再平衡**口径，与组合本身的调仓节奏不同；563300 上市后成分由 4 只变 5 只，
   宽基收益序列在该时点存在结构性断点（历史期不含中证A500）。
4. **夏普口径**：夏普 =(组合年化 − rf)/年化波动，rf 默认 0，而组合已含现金仓位收益，
   故该口径偏乐观，跨工具比较需先对齐 rf 与现金口径；年化按**有效投资期**计算
   （窗口估计期不计入年限），244 交易日/年。
5. **BL 观点口径**：标准置信度比例法 `Ω = τ(1−conf)/conf·PΣPᵀ`（等价于 Idzorek 刻度因子法），
   **conf 即"后验期望落在该观点上的权重"**（0.6 ≈ 六成权重给观点）；`--omega legacy`
   是早期不含 τ 的历史口径，会把观点影响压低（conf=0.5 仅约 2.4%），仅用于复现旧结果。
6. **BL 观点时效**：观点在一段回测/全部调仓期中**恒定使用**，不逐期更新或衰减，
   相当于假设该观点在整个样本期内持续有效。
7. **BL 观点归一化**：纯相对观点（系数和为 0）按 `max|p|=1` 自动归一化，q 恒等于年化价差；
   绝对观点不归一化。详见「帮用户定 BL 观点」一节。

## 参考

- **`references/knowledge.md`：知识库（策略知识主文档）**——资产配置/四模型原理/前复权/宽基合成/
  夏普/BL 观点标定/参数标定。**AI 讲解前先读它**，`--mode explain` 即其检索入口
- **`references/model_algorithms.md`：四个模型的完整算法说明**（公式、求解器、退化处理、业界常见变体与 τ/λ 标定）
- `references/model_notes.md`：数据口径与回测口径细节
- `references/bl_views_example.json`：BL 观点输入示例
- He & Litterman (1999), The Intuition Behind Black-Litterman Model Portfolios
- Black & Litterman (1992), Global Portfolio Optimization（贝叶斯视角）
- Idzorek (2005), A Step-By-Step Guide to the Black-Litterman Model（刻度因子/信心水平标定）
- Markowitz (1952), Portfolio Selection（均值方差框架）
