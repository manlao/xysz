# CLI 参考手册

所有命令通过在项目目录执行 `python watchlist.py` 运行。

## 全局参数

所有子命令均可使用：

| 参数 | 说明 |
|------|------|
| `--db PATH` | 指定数据库路径，默认 `data/watchlist.db` |
| `--no-api` | 强制离线模式（添加/刷新操作将被拒绝） |
| `--json` | 列表类命令输出 JSON 格式 |
| `--refresh` | 强制全量刷新行情与基本面（忽略当日已刷新标记） |

---

## 分组管理

```bash
# 新建分组
python watchlist.py group add 半导体 -d "芯片产业链"
python watchlist.py group add 红利策略

# 重命名分组
python watchlist.py group rename 红利策略 高股息

# 列出全部分组（含股票数）
python watchlist.py group list

# 删除分组（非空需 --force，会连带删除组内股票）
python watchlist.py group remove 高股息 --force
```

---

## 添加自选股

```bash
# 添加单只（不指定 -g 进入「默认」分组，名称/行情/基本面自动补全）
python watchlist.py add 000001.SZ
python watchlist.py add 600519.SH -g 白酒 -r "核心仓位"

# 指定自选价（默认=添加时最新价）
python watchlist.py add 601881.SH -g 红利策略 -p 11.09

# 自选原因可留空：不加 -r 即可

# 批量添加（命令行传入代码列表）
python watchlist.py add-batch -g 半导体 --codes 688981.SH 603501.SH 002049.SZ

# 批量添加（从文件读取，每行一码，支持 # 注释）
python watchlist.py add-batch -g 半导体 --file codes.txt
```

> **行为说明**：添加成功后，重算该分组全部股票的行情与基本面，并自动重写 HTML。若当日尚未刷新过，先对全市场自选股做一次全量刷新。

---

## 查询与展示

```bash
# 查看全部（默认显示所有字段）
python watchlist.py list
python watchlist.py list -g 半导体        # 指定分组
python watchlist.py list --json           # JSON 输出

# 单只详情（含所属分组 + 接口资料）
python watchlist.py info 000001.SZ

# 关键词搜索（代码/名称/自选原因）
python watchlist.py search 茅台

# HTML 展示（生成网页，含前端筛选框；增删改后自动重写）
python watchlist.py html
python watchlist.py html -g 半导体 -o d:/report.html --open
```

---

## 删除自选股

```bash
# 删除单只
python watchlist.py remove 000001.SZ                 # 从默认组删
python watchlist.py remove 600519.SH -g 白酒          # 从指定组删
python watchlist.py remove 600519.SH                  # 跨组全删（所有分组中删除）

# 批量删除
python watchlist.py remove-batch --codes 688981.SH 603501.SH
python watchlist.py remove-batch --file codes.txt --all
```

> **行为说明**：删除成功后，自动重写 HTML。

---

## 导出

```bash
python watchlist.py export -o watchlist.csv          # utf-8-sig，Excel 友好
python watchlist.py export -g 半导体 -o semi.csv
```
