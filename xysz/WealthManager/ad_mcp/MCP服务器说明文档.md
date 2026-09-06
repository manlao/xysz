# AmazingData MCP Server 说明文档

## 📋 目录

- [概述](#概述)
- [系统要求](#系统要求)
- [安装配置](#安装配置)
- [快速启动](#快速启动)
- [API 接口](#api-接口)
- [使用示例](#使用示例)
- [最佳实践](#最佳实践)
- [故障排查](#故障排查)
- [技术架构](#技术架构)

---

## 概述

AmazingData MCP Server 是基于 Model Context Protocol (MCP) 协议开发的金融数据服务接口，提供中国银河证券星耀数智 AmazingData 平台的数据访问能力。

### 核心特性

- **丰富的数据接口**: 提供 55 个工具接口，覆盖行情、财务、股东、交易等多维度数据
- **完整字段说明**: 所有接口返回数据的字段都有完整的中文说明，无省略
- **自动认证**: 通过环境变量实现自动登录，无需手动管理会话
- **统一数据格式**: 所有接口返回标准化的 JSON 格式数据
- **完善的错误处理**: 提供详细的错误信息和操作建议
- **资源访问**: 支持通过 MCP Resources 访问开发手册和 API 文档

### 版本信息

- **服务名称**: AmazingData
- **版本**: 1.0.0
- **协议**: MCP (Model Context Protocol)
- **开发框架**: FastMCP
- **最后更新**: 2026-03-05

---

## 系统要求

### 运行环境

- **
- 
- Python**: 3.8 - 3.13
- **操作系统**: Windows / Linux
- **Python 环境**: Anaconda 推荐

### 依赖包

```bash
# 核心依赖
tgw=1.8.0.5
AmazingData=1.0.24
fastmcp=2.10.5
pandas=2.3.0

# PDF 文档读取
PyPDF2=3.0.0
```

---

## 安装配置

### 1. 安装依赖

使用指定的 Anaconda 环境：

```bash
D:\ProgramData\anaconda313\python.exe -m pip install fastmcp pandas PyPDF2
```

### 2. 配置 Claude Desktop

编辑配置文件 `%APPDATA%\Claude\claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "amazingdata": {
      "command": "D:\\ProgramData\\anaconda313\\python.exe",
      "args": ["D:\\WealthManager\\WealthManager\\ad_mcp\\server.py"],
      "env": {
        "USER": "your_username",
        "PASSWORD": "your_password",
        "HOST": "***.***.***.***",
        "PORT": "****"
      }
    }
  }
}
```

---

## 快速启动

### 方式一：直接运行

```bash
cd D:\WealthManager\WealthManager\mcp_server
D:\ProgramData\anaconda313\python.exe server.py
```

### 方式二：通过 Claude Desktop

1. 配置好 `claude_desktop_config.json`
2. 重启 Claude Desktop
3. 在对话中直接使用 MCP 工具

### 验证安装

启动后检查日志文件 `amazingdata_mcp.log`，确认：

```
INFO - 正在登录 AmazingData...
INFO - 登录成功！用户: your_username
INFO - MCP Server 启动成功
```

---

## API 接口

### 接口分类

本服务提供 **55 个工具接口**，分为以下类别：

#### 1. 系统管理接口 (2个)

| 工具名称 | 功能说明 |
|---------|---------|
| `mcp_get_login_status` | 获取当前登录状态 |
| `mcp_logout` | 登出系统 |

#### 2. 基础数据接口 (8个)

| 工具名称 | 功能说明 |
|---------|---------|
| `mcp_code_list` | 获取证券代码列表（A股、指数、ETF、可转债等） |
| `mcp_code_list_future` | 获取期货代码列表 |
| `mcp_code_list_option` | 获取期权代码列表 |
| `mcp_code_info` | 获取证券信息（涨跌停价、昨收价等） |
| `mcp_backward_factor` | 获取复权因子 |
| `mcp_history_code_list` | 获取历史代码列表 |
| `mcp_calendar` | 获取交易日历 |
| `mcp_kzz` | 获取可转债代码表 |

#### 3. 行情数据接口 (2个)

| 工具名称 | 功能说明 |
|---------|---------|
| `mcp_kline` | 查询K线数据（支持日线、分钟线、周线、月线等多周期）<br>• 支持分页参数: `limit`（返回记录数）、`offset`（跳过记录数）<br>• 适用于大数据量查询，避免超时 |
| `mcp_snapshot` | 查询历史快照数据（统一接口，自动识别所有资产类型）<br>• SDK 自动根据证券代码识别资产类型<br>• 支持股票、指数、ETF、债券、期货、期权、回购、港股通<br>• 只查询历史快照，不支持实时订阅 |

#### 4. 股票信息接口 (3个)

| 工具名称 | 功能说明 |
|---------|---------|
| `mcp_stock_basic` | 股票基础信息（上市日期、退市日期、板块等）<br>• 支持 `summary_only` 参数：仅返回统计摘要 |
| `mcp_history_stock_status` | 历史证券状态（ST、停牌、除权除息等） |
| `mcp_bj_code_mapping` | 北交所代码对照表 |

#### 5. 财务报表接口 (5个)

| 工具名称 | 功能说明 |
|---------|---------|
| `mcp_balance_sheet` | 资产负债表 |
| `mcp_cash_flow` | 现金流量表 |
| `mcp_income` | 利润表 |
| `mcp_profit_express` | 业绩快报 |
| `mcp_profit_notice` | 业绩预告 |

#### 5. 股东信息接口 (5个)

| 工具名称 | 功能说明 |
|---------|---------|
| `mcp_share_holder` | 十大股东 |
| `mcp_holder_num` | 股东户数 |
| `mcp_equity_structure` | 股本结构 |
| `mcp_equity_pledge_freeze` | 股权冻结/质押 |
| `mcp_equity_restricted` | 限售股解禁 |

#### 6. 分红配股接口 (2个)

| 工具名称 | 功能说明 |
|---------|---------|
| `mcp_dividend` | 分红数据 |
| `mcp_right_issue` | 配股数据 |

#### 7. 交易数据接口 (4个)

| 工具名称 | 功能说明 |
|---------|---------|
| `mcp_margin_summary` | 融资融券汇总 |
| `mcp_margin_detail` | 融资融券明细 |
| `mcp_long_hu_bang` | 龙虎榜数据 |
| `mcp_block_trading` | 大宗交易数据 |

#### 8. ETF数据接口 (3个)

| 工具名称 | 功能说明 |
|---------|---------|
| `mcp_etf_purchase_redemption` | ETF申购赎回数据 |
| `mcp_etf_fund_share` | ETF基金份额 |
| `mcp_etf_iopv` | ETF收盘IOPV（实时参考净值） |

#### 9. 指数数据接口 (2个)

| 工具名称 | 功能说明 |
|---------|---------|
| `mcp_index_constituent` | 交易所指数成分股 |
| `mcp_index_constituent_weight` | 交易所指数成分股日权重 |

#### 10. 行业数据接口 (4个)

| 工具名称 | 功能说明 |
|---------|---------|
| `mcp_industry_index_info` | 行业指数基本信息 |
| `mcp_industry_index_constituent` | 行业指数成分股 |
| `mcp_industry_index_weight` | 行业指数成分股日权重 |
| `mcp_industry_index_quote` | 行业指数日行情 |

#### 11. 期权数据接口 (3个)

| 工具名称 | 功能说明 |
|---------|---------|
| `mcp_option_basic_info` | 期权基本资料 |
| `mcp_option_contract_info` | 期权标准合约属性 |
| `mcp_option_month_contract_change` | 期权月合约属性变动 |

#### 12. 可转债数据接口 (11个)

| 工具名称 | 功能说明 |
|---------|---------|
| `mcp_convertible_bond_issue` | 可转债发行数据 |
| `mcp_convertible_bond_balance` | 可转债份额数据 |
| `mcp_convertible_bond_conversion` | 可转债转股数据 |
| `mcp_convertible_bond_conversion_change` | 可转债转股变动数据 |
| `mcp_convertible_bond_adjustment` | 可转债修正数据（转股价格调整） |
| `mcp_convertible_bond_redemption` | 可转债赎回数据 |
| `mcp_convertible_bond_resale` | 可转债回售数据 |
| `mcp_convertible_bond_terms` | 可转债回售赎回条款 |
| `mcp_convertible_bond_resale_notice` | 可转债回售条款执行说明 |
| `mcp_convertible_bond_redemption_notice` | 可转债赎回条款执行说明 |
| `mcp_convertible_bond_suspension` | 可转债停复牌信息 |

#### 13. 其他数据接口 (1个)

| 工具名称 | 功能说明 |
|---------|---------|
| `mcp_treasury_yield` | 国债收益率数据 |

### MCP Resources

| 资源 URI | 说明 |
|---------|------|
| `amazingdata://doc/manual` | AmazingData 开发手册（PDF格式） |
| `amazingdata://doc/api-summary` | API 接口摘要 |

---

## 使用示例

### 示例 1: 查询股票K线数据

```python
# 查询平安银行和工商银行的日K线数据
result = await mcp_kline(
    code_list=["000***.SZ", "601***.SH"],
    begin_date=20240101,
    end_date=20240131,
    period="day"
)

# 返回格式
{
    "success": true,
    "count": 42,
    "data": [
        {
            "code": "000***.SZ",
            "date": 20240102,
            "open": 10.50,
            "high": 10.80,
            "low": 10.45,
            "close": 10.75,
            "volume": 123456789,
            "amount": 1234567890.0
        },
        ...
    ]
}
```

### 示例 2: 查询龙虎榜数据

```python
# 查询某股票的龙虎榜数据
result = await mcp_long_hu_bang(
    code_list=["000***.SZ"],
    begin_date=20240101,
    end_date=20240131
)
```

### 示例 3: 查询财务报表

```python
# 查询资产负债表
result = await mcp_balance_sheet(
    code_list=["000***.SZ"],
    begin_date=20230101,
    end_date=20231231
)
```

### 示例 4: 获取证券代码列表

```python
# 获取所有A股代码
result = await mcp_code_list(
    extra_type="EXTRA_STOCK_A"
)

# 获取所有指数代码
result = await mcp_code_list(
    extra_type="EXTRA_INDEX_A"
)
```

### 示例 5: 分页查询大数据量

```python
# 查询多年K线数据，使用分页避免超时
result = await mcp_kline(
    code_list=["000***.SZ"],
    begin_date=20200101,
    end_date=20231231,
    period="day",
    limit=1000,    # 每次返回1000条
    offset=0       # 从第0条开始
)
```

---

## 最佳实践

### 1. 日期参数规范

```python
# ✅ 正确：使用8位整数格式
begin_date = 20240101
end_date = 20240131

# ❌ 错误：字符串格式
begin_date = "2024-01-01"

# ❌ 错误：日期对象
begin_date = datetime.date(2024, 1, 1)
```

### 2. 证券代码格式

```python
# ✅ 正确：带市场后缀
code_list = ["000***.SZ", "600***.SH", "688***.SH"]

# ❌ 错误：不带后缀
code_list = ["000001", "600000"]

# 市场后缀说明
# .SZ - 深圳证券交易所
# .SH - 上海证券交易所
# .BJ - 北京证券交易所
```

### 3. 批量查询优化

```python
# ✅ 推荐：分批查询，每批不超过50个代码
code_list = ["000***.SZ", "000***.SZ", ...]  # 最多50个

# ❌ 不推荐：一次查询过多代码
code_list = [...]  # 超过100个代码
```

### 4. 日期范围控制

```python
# ✅ 推荐：日期范围不超过1年
begin_date = 20240101
end_date = 20241231

# ⚠️ 注意：超过1年可能导致查询超时
begin_date = 20200101
end_date = 20241231  # 建议使用分页参数
```

### 5. 错误处理

```python
try:
    result = await mcp_kline(...)
    if result["success"]:
        data = result["data"]
        # 处理数据
    else:
        # 处理错误
        print(result["error_type"])
        print(result["suggestion"])
except Exception as e:
    # 异常处理
    print(f"查询失败: {e}")
```

### 6. 使用 summary_only 参数

```python
# 快速获取数据概况，不返回详细数据
result = await mcp_stock_basic(
    summary_only=True
)

# 返回格式
{
    "success": true,
    "summary": {
        "total_count": 5000,
        "listed_count": 4800,
        "delisted_count": 200,
        "market_distribution": {
            "SH": 2000,
            "SZ": 2500,
            "BJ": 300
        }
    }
}
```

---

## 故障排查

### 问题 1: 登录失败

**症状**: 启动时提示 "登录失败" 或 "未登录"

**排查步骤**:

1. 检查环境变量是否正确设置
   ```bash
   echo %AMAZINGDATA_USER%
   echo %AMAZINGDATA_PASSWORD%
   ```

2. 验证服务器地址和端口
   ```bash
   ping ***.***.***.***
   telnet ***.***.***.*** ****
   ```

3. 检查用户名和密码是否正确

4. 查看日志文件 `amazingdata_mcp.log`

### 问题 2: 查询数据为空

**症状**: 接口返回 `data: []` 或 `count: 0`

**排查步骤**:

1. 确认已登录
   ```python
   result = await mcp_get_login_status()
   ```

2. 检查日期范围是否正确
   - 确保日期在有效范围内
   - 确保日期范围内有交易日

3. 验证证券代码格式
   ```python
   # 使用 mcp_code_list 验证代码是否存在
   result = await mcp_code_list(extra_type="EXTRA_STOCK_A")
   ```

4. 检查参数类型是否正确

### 问题 3: 查询超时

**症状**: 接口长时间无响应或返回超时错误

**解决方案**:

1. 缩短日期范围（建议不超过1年）
2. 减少查询的代码数量（建议不超过50个）
3. 使用分页参数 `limit` 和 `offset`
4. 避免在高峰时段查询

### 问题 4: 日期参数错误

**症状**: 提示 "日期格式错误" 或 "日期逻辑错误"

**解决方案**:

```python
# ✅ 正确格式
begin_date = 20240101  # 8位整数
end_date = 20240131

# 确保 begin_date <= end_date
if begin_date > end_date:
    begin_date, end_date = end_date, begin_date
```

### 问题 5: PDF 文档读取失败

**症状**: 访问 `amazingdata://doc/manual` 时提示 "PyPDF2 未安装"

**解决方案**:

```bash
D:\ProgramData\anaconda313\python.exe -m pip install PyPDF2
```

---

## 技术架构

### 核心组件

```
┌─────────────────────────────────────────┐
│         Claude Desktop / MCP Client      │
└─────────────────┬───────────────────────┘
                  │ MCP Protocol
┌─────────────────▼───────────────────────┐
│         FastMCP Server (server.py)       │
│  ┌─────────────────────────────────┐    │
│  │  MCP Tools (55个工具接口)       │    │
│  ├─────────────────────────────────┤    │
│  │  MCP Resources (2个资源)        │    │
│  ├─────────────────────────────────┤    │
│  │  认证管理 (自动登录)            │    │
│  ├─────────────────────────────────┤    │
│  │  数据序列化 (DataFrame → JSON)  │    │
│  ├─────────────────────────────────┤    │
│  │  错误处理 (统一错误格式)        │    │
│  └─────────────────────────────────┘    │
└─────────────────┬───────────────────────┘
                  │ AmazingData SDK
┌─────────────────▼───────────────────────┐
│      AmazingData 金融数据平台            │
│      (***.***.***.***:****)             │
└─────────────────────────────────────────┘
```

### 数据流程

1. **请求阶段**
   - Claude Desktop 发送 MCP 请求
   - FastMCP Server 接收并解析请求
   - 验证登录状态和参数

2. **查询阶段**
   - 调用 AmazingData SDK
   - 执行数据查询
   - 获取 DataFrame 结果

3. **处理阶段**
   - 序列化 DataFrame 为 JSON
   - 统一返回格式
   - 错误处理和日志记录

4. **响应阶段**
   - 返回标准化 JSON 数据
   - Claude Desktop 接收并展示

### 关键函数

#### 1. 日期验证

```python
def validate_date_range(begin_date: Optional[int], end_date: Optional[int]) -> tuple[int, int]:
    """
    验证日期范围参数
    - begin_date 默认为 19900101
    - end_date 默认为当前日期
    - 日期格式必须为 YYYYMMDD（8位整数）
    """
```

#### 2. 数据序列化

```python
def serialize_dataframe(df: pd.DataFrame) -> Optional[List[Dict]]:
    """序列化 DataFrame 为字典列表"""

def serialize_dict(ori_dict: Dict[str, pd.DataFrame]) -> Dict[str, Optional[List[Dict]]]:
    """序列化一层字典，value 是 DataFrame 的情况"""

def serialize_nested_dict(nested_dict: Dict[str, Dict[str, pd.DataFrame]]) -> Dict[str, Dict[str, Optional[List[Dict]]]]:
    """序列化两层字典，最内层 value 是 DataFrame 的情况"""
```

#### 3. 错误处理

```python
def handle_error(e: Exception, context: str, **extra_info) -> dict:
    """
    统一的错误处理函数，返回可操作的错误信息
    - 识别错误类型
    - 提供详细建议
    - 记录错误日志
    """
```

#### 4. 登录管理

```python
def ensure_logged_in() -> bool:
    """确保已登录，如果未登录则抛出异常"""
```

### 配置参数

| 参数 | 说明 | 默认值 |
|-----|------|--------|
| `AMAZINGDATA_USER` | 用户名 | 必填 |
| `AMAZINGDATA_PASSWORD` | 密码 | 必填 |
| `AMAZINGDATA_HOST` | 服务器地址 | ***.***.***.*** |
| `AMAZINGDATA_PORT` | 服务器端口 | **** |
| `is_local` | 是否本地存储 | False（禁用） |

### 日志配置

日志文件: `amazingdata_mcp.log`

日志级别: INFO

日志格式: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`

---

## 附录

### A. 证券类型代码

| 代码 | 说明 |
|-----|------|
| `EXTRA_STOCK_A` | 沪深北A股（默认） |
| `EXTRA_INDEX_A` | 沪深北指数 |
| `EXTRA_ETF` | 沪深ETF |
| `EXTRA_KZZ` | 沪深可转债 |
| `SH_A` | 上交所A股 |
| `SZ_A` | 深交所A股 |
| `BJ_A` | 北交所股票 |

### B. K线周期代码

| 代码 | 说明 |
|-----|------|
| `day` | 日线（默认） |
| `min1` | 1分钟线 |
| `min5` | 5分钟线 |
| `min15` | 15分钟线 |
| `min30` | 30分钟线 |
| `min60` | 60分钟线 |
| `week` | 周线 |
| `month` | 月线 |

### C. 返回数据格式

#### 成功响应

```json
{
    "success": true,
    "count": 100,
    "data": [
        {...},
        {...}
    ]
}
```

#### 错误响应

```json
{
    "success": false,
    "context": "查询K线数据",
    "error_type": "invalid_parameter",
    "message": "日期格式错误",
    "suggestion": "请检查参数格式和取值范围",
    "examples": {
        "date_format": "20240101 (YYYYMMDD, 8位整数)"
    }
}
```

### D. 常用查询模板

#### 查询股票基本信息

```python
# 获取股票列表
codes = await mcp_code_list(extra_type="EXTRA_STOCK_A")

# 获取股票详细信息
info = await mcp_code_info(code_list=["000***.SZ"])

# 获取股票基础数据
basic = await mcp_stock_basic(code_list=["000***.SZ"])
```

#### 查询行情数据

```python
# 日K线
kline = await mcp_kline(
    code_list=["000***.SZ"],
    begin_date=20240101,
    end_date=20240131,
    period="day"
)

# 快照数据
snapshot = await mcp_snapshot(
    code_list=["000***.SZ"],
    begin_date=20240101,
    end_date=20240131
)
```

#### 查询财务数据

```python
# 资产负债表
balance = await mcp_balance_sheet(
    code_list=["000***.SZ"],
    begin_date=20230101,
    end_date=20231231
)

# 利润表
income = await mcp_income(
    code_list=["000***.SZ"],
    begin_date=20230101,
    end_date=20231231
)

# 现金流量表
cashflow = await mcp_cash_flow(
    code_list=["000***.SZ"],
    begin_date=20230101,
    end_date=20231231
)
```




