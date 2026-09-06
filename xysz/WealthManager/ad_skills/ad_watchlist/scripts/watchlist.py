# -*- coding: utf-8 -*-
"""
自选股管理 (ad-watchlist)
========================================================
基于中国银河证券「星耀数智」(AmazingData) 数据接口，将自选股及分组信息
存入本地 SQLite 数据库，方便管理与查询，并支持 HTML 网页展示。

功能（均通过命令行执行）:
  1. 自选股分组：支持创建多个分组
  2. 分组自定义名称：创建时自定义，并支持重命名 / 删除
  3. 自选股信息查询：列表查看、单只详情、关键词搜索、HTML 网页展示
  4. 添加单只自选股（联网补全名称/行情/基本面，离线不允许添加）
  5. 批量添加自选股（命令行传入或读取文件）
  6. 删除单只自选股
  7. 批量删除自选股
  8. 自动刷新：每次添加自选股时重算该分组全部数据；当日首次调用时全量重算
  9. HTML 展示：增删改后自动更新 data/watchlist.html（含行情/基本面全字段，分组标签页+分页+排序）

数据字段（每只自选股）:
  基础：代码、名称、市场、板块、自选价格、自选时间、自选原因(可空)
  行情：最新价(前复权)、涨跌额、涨幅、成交额、成交量、本周/本月/本年涨幅
  基本面：市净率(PB)、市盈率(PE)、总股本(亿)、流通股本(亿)、总市值、流通市值
  衍生：自选收益 = (最新价 - 自选价格) / 自选价格

环境要求:
  - Python 需能 import AmazingData（星耀数智 SDK）以联网补全行情/基本面
  - 凭证环境变量：AD_USERNAME / AD_PASSWORD / AD_HOST / AD_PORT
  - 添加/刷新操作必须联网；list/info/search/html/export 在 --no-api 下可离线查看
"""

import os
import sys
import argparse
import sqlite3
import json
from datetime import datetime, date, timedelta

try:
    import pandas as pd
except ImportError:
    pd = None

# ----------------------------------------------------------------------------
# 基础配置
# ----------------------------------------------------------------------------
DEFAULT_GROUP = "默认"  # 未指定分组时使用的默认分组名

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.environ.get(
    "AD_WATCHLIST_DB",
    os.path.join(_SKILL_DIR, "data", "watchlist.db"),
)
# AmazingData 本地缓存目录（股本结构/复权因子接口需要本地路径，SDK 会自动追加 infodata 后缀）
AD_CACHE = os.path.join(_SKILL_DIR, "data", "ad_cache")
# HTML 自动输出路径
DEFAULT_HTML_PATH = os.path.join(os.getcwd(), "data", "watchlist.html")
# HTML 展示页模板（CSS/JS/骨架，动态数据用占位符 __CSS_RULES__/__META__/__TABS__/__RADIOS__/__PANELS__ 填充）
HTML_TEMPLATE_PATH = os.path.join(_SKILL_DIR, "assets", "templates", "watchlist_template.html")


# ----------------------------------------------------------------------------
# 显示工具
# ----------------------------------------------------------------------------
def display_width(text):
    w = 0
    for ch in str(text):
        w += 2 if ord(ch) > 0x2E80 else 1
    return w


def pad(text, width):
    text = "" if text is None else str(text)
    return text + " " * max(0, width - display_width(text))


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today_str():
    return date.today().strftime("%Y-%m-%d")


# ---- 数值格式化（命令行与 HTML 共用）----
def fmt_price(x):
    return "%.2f" % x if x is not None else "-"


def fmt_pct(x):
    if x is None:
        return "-"
    return ("%+.2f%%" % x)


def fmt_big(x):
    """元 -> 亿/万 展示"""
    if x is None:
        return "-"
    ax = abs(x)
    if ax >= 1e8:
        return "%.2f亿" % (x / 1e8)
    if ax >= 1e4:
        return "%.2f万" % (x / 1e4)
    return "%.2f" % x


def fmt_vol(x):
    if x is None:
        return "-"
    ax = abs(x)
    if ax >= 1e8:
        return "%.2f亿" % (x / 1e8)
    if ax >= 1e4:
        return "%.2f万" % (x / 1e4)
    return "%.0f" % x


def pct_color(x):
    """A股配色：涨红跌绿"""
    if x is None:
        return ""
    if x > 0:
        return "#d4380d"
    if x < 0:
        return "#389e0d"
    return "#555555"


def print_table(headers, rows, json_mode=False):
    if json_mode:
        out = [{headers[i]: ("" if r[i] is None else r[i]) for i in range(len(headers))} for r in rows]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    cols = []
    for i, h in enumerate(headers):
        col_vals = [str(h)] + ["" if r[i] is None else str(r[i]) for r in rows]
        width = max(display_width(v) for v in col_vals)
        cols.append((h, width))
    sep = "-+-".join("-" * w for _, w in cols)
    print(" | ".join(pad(h, w) for h, w in cols))
    print(sep)
    for r in rows:
        print(" | ".join(pad("" if r[i] is None else r[i], w) for i, (_, w) in enumerate(cols)))
    if not rows:
        print("(无记录)")


# ----------------------------------------------------------------------------
# 数据库访问层
# ----------------------------------------------------------------------------
# 新增列（迁移用）：列名 -> 类型
NEW_COLUMNS = {
    "watch_time": "TEXT",        # 自选时间（替代 added_at 语义）
    "watch_price": "REAL",       # 自选价格
    "last_price": "REAL",        # 最新价
    "change_val": "REAL",        # 涨跌额
    "change_pct": "REAL",        # 涨幅 %
    "amount": "REAL",            # 成交额（元）
    "volume": "REAL",            # 成交量
    "chg_week": "REAL",          # 本周涨幅 %
    "chg_month": "REAL",         # 本月涨幅 %
    "chg_year": "REAL",          # 本年涨幅 %
    "pb": "REAL",                # 市净率
    "pe": "REAL",                # 市盈率
    "tot_share": "REAL",         # 总股本（万股）
    "float_share": "REAL",       # 流通股本（万股）
    "tot_mktcap": "REAL",        # 总市值（元）
    "float_mktcap": "REAL",      # 流通市值（元）
    "profit_pct": "REAL",        # 自选收益 %
    "data_updated_at": "TEXT",   # 行情/基本面数据刷新时间
}


class WatchlistDB:
    def __init__(self, db_path):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()
        self._migrate()
        self._ensure_default_group()

    def _init_schema(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS groups (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL UNIQUE,
                description TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS stocks (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id   INTEGER NOT NULL,
                code       TEXT NOT NULL,
                name       TEXT,
                market     TEXT,
                list_plate TEXT,
                watch_reason TEXT,
                added_at   TEXT,
                updated_at TEXT NOT NULL,
                UNIQUE(group_id, code),
                FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_stocks_code ON stocks(code);
            CREATE INDEX IF NOT EXISTS idx_stocks_group ON stocks(group_id);
            """
        )
        self.conn.commit()

    def _migrate(self):
        cur = self.conn.execute("PRAGMA table_info(stocks)")
        existing = set(r[1] for r in cur.fetchall())
        for col, ctype in NEW_COLUMNS.items():
            if col not in existing:
                self.conn.execute("ALTER TABLE stocks ADD COLUMN %s %s" % (col, ctype))
        # 迁移：added_at -> watch_time
        self.conn.execute(
            "UPDATE stocks SET watch_time=added_at WHERE watch_time IS NULL AND added_at IS NOT NULL"
        )
        # 迁移：note -> watch_reason（自选原因，可空）
        try:
            self.conn.execute("ALTER TABLE stocks RENAME COLUMN note TO watch_reason")
        except sqlite3.OperationalError:
            # 旧版本 SQLite 不支持 RENAME COLUMN，退回建列+拷贝
            cur = self.conn.execute("PRAGMA table_info(stocks)")
            if "watch_reason" not in [r[1] for r in cur.fetchall()]:
                self.conn.execute("ALTER TABLE stocks ADD COLUMN watch_reason TEXT")
                self.conn.execute("UPDATE stocks SET watch_reason=note WHERE note IS NOT NULL")
        # 迁移：总股本/流通股本 单位 万股 -> 亿股（旧数据按万股存储，刷新后改为亿股）
        if self.get_meta("share_unit_v2") != "1":
            self.conn.execute(
                "UPDATE stocks SET tot_share = tot_share / 10000.0 "
                "WHERE tot_share IS NOT NULL"
            )
            self.conn.execute(
                "UPDATE stocks SET float_share = float_share / 10000.0 "
                "WHERE float_share IS NOT NULL"
            )
            self.set_meta("share_unit_v2", "1")
        self.conn.commit()

    def _ensure_default_group(self):
        now = _now()
        cur = self.conn.execute("SELECT id FROM groups WHERE name=?", (DEFAULT_GROUP,))
        if cur.fetchone() is None:
            self.conn.execute(
                "INSERT INTO groups(name, description, created_at, updated_at) VALUES(?,?,?,?)",
                (DEFAULT_GROUP, "默认分组", now, now),
            )
            self.conn.commit()

    def close(self):
        self.conn.close()

    # ---- meta ----
    def get_meta(self, key):
        cur = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,))
        r = cur.fetchone()
        return r[0] if r else None

    def set_meta(self, key, value):
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    # ---- 分组 ----
    def get_group(self, name):
        return self.conn.execute("SELECT * FROM groups WHERE name=?", (name,)).fetchone()

    def list_groups(self):
        return self.conn.execute(
            """
            SELECT g.id, g.name, g.description, g.created_at,
                   COUNT(s.id) AS stock_count
            FROM groups g
            LEFT JOIN stocks s ON s.group_id = g.id
            GROUP BY g.id, g.name, g.description, g.created_at
            ORDER BY g.id
            """
        ).fetchall()

    def add_group(self, name, description=""):
        now = _now()
        try:
            self.conn.execute(
                "INSERT INTO groups(name, description, created_at, updated_at) VALUES(?,?,?,?)",
                (name, description, now, now),
            )
            self.conn.commit()
            return True, None
        except sqlite3.IntegrityError:
            return False, "分组名「%s」已存在" % name

    def rename_group(self, old, new):
        if old == new:
            return True, "无需修改"
        if self.conn.execute("SELECT id FROM groups WHERE name=?", (new,)).fetchone():
            return False, "目标分组名「%s」已存在" % new
        if not self.conn.execute("SELECT id FROM groups WHERE name=?", (old,)).fetchone():
            return False, "分组「%s」不存在" % old
        self.conn.execute("UPDATE groups SET name=?, updated_at=? WHERE name=?", (new, _now(), old))
        self.conn.commit()
        return True, None

    def remove_group(self, name, force=False):
        row = self.get_group(name)
        if not row:
            return False, "分组「%s」不存在" % name
        gid = row[0]
        cnt = self.conn.execute("SELECT COUNT(*) FROM stocks WHERE group_id=?", (gid,)).fetchone()[0]
        if cnt > 0 and not force:
            return False, "分组「%s」含 %d 只股票，请先清空或使用 --force 强制删除（同时删除组内股票）" % (name, cnt)
        self.conn.execute("DELETE FROM groups WHERE id=?", (gid,))
        self.conn.commit()
        return True, None

    # ---- 股票 ----
    def add_stock(self, group_name, code, name=None, market=None, list_plate=None, watch_reason=None, watch_price=None):
        grp = self.get_group(group_name)
        if not grp:
            return False, "分组「%s」不存在，请先创建" % group_name
        gid = grp[0]
        now = _now()
        try:
            self.conn.execute(
                """
                INSERT INTO stocks(group_id, code, name, market, list_plate, watch_reason,
                                    added_at, watch_time, watch_price, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (gid, code, name, market, list_plate, watch_reason, now, now, watch_price, now),
            )
            self.conn.commit()
            return True, None
        except sqlite3.IntegrityError:
            return False, "股票 %s 已在分组「%s」中" % (code, group_name)

    def search_stocks(self, keyword):
        kw = "%" + keyword + "%"
        return self.conn.execute(
            """
            SELECT s.code, s.name, g.name, s.watch_price, s.last_price, s.change_pct,
                   s.profit_pct, s.watch_reason
            FROM stocks s JOIN groups g ON s.group_id=g.id
            WHERE s.code LIKE ? OR s.name LIKE ? OR COALESCE(s.watch_reason,'') LIKE ?
            ORDER BY g.id, s.code
            """,
            (kw, kw, kw),
        ).fetchall()

    def get_group_codes(self, group_name):
        grp = self.get_group(group_name)
        if not grp:
            return []
        return [r[0] for r in self.conn.execute(
            "SELECT code FROM stocks WHERE group_id=?", (grp[0],)).fetchall()]

    def all_codes(self):
        return [r[0] for r in self.conn.execute("SELECT DISTINCT code FROM stocks").fetchall()]

    def list_stocks(self, group_name=None, detail=False):
        if group_name:
            grp = self.get_group(group_name)
            if not grp:
                return None
            gid = grp[0]
            rows = self.conn.execute(
                "SELECT s.code, s.name, s.watch_price, s.watch_time, s.last_price, "
                "s.change_pct, s.chg_week, s.chg_month, s.chg_year, s.profit_pct, "
                "s.pb, s.pe, s.tot_mktcap, s.float_mktcap, s.market, s.list_plate, s.watch_reason "
                "FROM stocks s WHERE s.group_id=? ORDER BY s.code", (gid,)).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT s.code, s.name, g.name, s.watch_price, s.watch_time, s.last_price, "
                "s.change_pct, s.chg_week, s.chg_month, s.chg_year, s.profit_pct, "
                "s.pb, s.pe, s.tot_mktcap, s.float_mktcap, s.market, s.list_plate, s.watch_reason "
                "FROM stocks s JOIN groups g ON s.group_id=g.id "
                "ORDER BY g.id, s.code").fetchall()
        return rows

    def get_stock_detail(self, code):
        return self.conn.execute(
            """
            SELECT s.code, s.name, g.name, s.watch_price, s.watch_time, s.last_price,
                   s.change_val, s.change_pct, s.amount, s.volume,
                   s.chg_week, s.chg_month, s.chg_year, s.profit_pct,
                   s.pb, s.pe, s.tot_share, s.float_share, s.tot_mktcap, s.float_mktcap,
                   s.market, s.list_plate, s.watch_reason, s.data_updated_at
            FROM stocks s JOIN groups g ON s.group_id=g.id
            WHERE s.code=?
            """,
            (code,),
        ).fetchall()

    def remove_stock(self, code, group_name=None):
        if group_name:
            grp = self.get_group(group_name)
            if not grp:
                return 0
            cur = self.conn.execute("DELETE FROM stocks WHERE code=? AND group_id=?", (code, grp[0]))
        else:
            cur = self.conn.execute("DELETE FROM stocks WHERE code=?", (code,))
        self.conn.commit()
        return cur.rowcount

    def remove_stocks(self, codes, group_name=None):
        n = 0
        for code in codes:
            n += self.remove_stock(code, group_name)
        return n

    def update_row_data(self, rid, fields):
        """fields: dict 列名->值，写入 stocks 表（按 id）"""
        if not fields:
            return
        sets = ", ".join("%s=?" % k for k in fields)
        vals = list(fields.values()) + [rid]
        self.conn.execute("UPDATE stocks SET %s WHERE id=?" % sets, vals)
        self.conn.commit()


# ----------------------------------------------------------------------------
# 星耀数智数据层
# ----------------------------------------------------------------------------
def login_ad():
    """登录并返回 (base, market, info, today_int, ad)；失败返回 None"""
    try:
        import AmazingData as ad
        ad.login(
            username=os.environ["AD_USERNAME"],
            password=os.environ["AD_PASSWORD"],
            host=os.environ["AD_HOST"],
            port=int(os.environ["AD_PORT"]),
        )
        base = ad.BaseData()
        cal = base.get_calendar()
        today_int = int(cal[-1])
        market = ad.MarketData(cal)
        info = ad.InfoData()
        return (base, market, info, today_int, ad)
    except Exception as e:
        sys.stderr.write("[警告] 星耀数智登录/初始化失败，无法联网：%s\n" % e)
        return None


def compute_quote(df, today_date):
    """由单只股票日线 DataFrame 计算行情与各周期涨幅。today_date: date。
    close 已通过 get_backward_factor 做前复权（price × factor / latest_factor），涨跌幅直接比值。"""
    if df is None or len(df) == 0 or pd is None:
        return None
    d = df.copy()
    d["kline_time"] = pd.to_datetime(d["kline_time"])
    d = d.sort_values("kline_time").reset_index(drop=True)
    last = d.iloc[-1]
    last_price = float(last["close"])
    pre_close = float(d.iloc[-2]["close"]) if len(d) >= 2 else last_price
    change_val = last_price - pre_close
    change_pct = (change_val / pre_close * 100) if pre_close else 0.0
    # 今年涨幅：上一年最后交易日 前复权收盘价
    prev_year = d[d["kline_time"].dt.year < today_date.year]
    year_base = float(prev_year["close"].iloc[-1]) if len(prev_year) else None
    chg_year = (last_price / year_base - 1) * 100 if year_base else None
    # 本月涨幅：上月最后一个交易日 前复权收盘价
    if today_date.month == 1:
        prev_month = d[(d["kline_time"].dt.year == today_date.year - 1) &
                       (d["kline_time"].dt.month == 12)]
    else:
        prev_month = d[(d["kline_time"].dt.year == today_date.year) &
                       (d["kline_time"].dt.month == today_date.month - 1)]
    month_base = float(prev_month["close"].iloc[-1]) if len(prev_month) else None
    chg_month = (last_price / month_base - 1) * 100 if month_base else None
    # 本周涨幅：上周最后一个交易日 前复权收盘价
    monday = today_date - timedelta(days=today_date.weekday())
    prev_week = d[d["kline_time"].dt.date < monday]
    week_base = float(prev_week["close"].iloc[-1]) if len(prev_week) else None
    chg_week = (last_price / week_base - 1) * 100 if week_base else None
    # 当日涨幅：仅 1 条数据时无法计算，返回 None
    pre_close = float(d.iloc[-2]["close"]) if len(d) >= 2 else None
    change_val = (last_price - pre_close) if pre_close else None
    change_pct = (change_val / pre_close * 100) if (pre_close and change_val is not None) else None
    return {
        "last_price": last_price,
        "change_val": change_val,
        "change_pct": change_pct,
        "amount": float(last["amount"]),
        "volume": float(last["volume"]),
        "chg_week": chg_week,
        "chg_month": chg_month,
        "chg_year": chg_year,
    }


def fetch_quotes(codes, market, base, ad, today_int):
    """获取行情并计算各周期涨幅。
    query_kline 返回不复权收盘价，通过 get_backward_factor 做前复权：
    fwd_price = raw_close × backward_factor[t] / backward_factor[last]
    （与 ad-technical-analysis skill 的 forward_adjust 完全一致）"""
    res = {}
    if not codes or ad is None:
        return res
    begin = int(date(today_int // 10000 - 1, 12, 1).strftime("%Y%m%d"))
    try:
        kl = market.query_kline(codes, begin_date=begin, end_date=today_int,
                                period=ad.constant.Period.day.value)
    except Exception as e:
        sys.stderr.write("[警告] 行情获取失败：%s\n" % e)
        return res
    today_date = datetime.strptime(str(today_int), "%Y%m%d").date()

    # 后复权因子（累计单调递增），用于计算前复权 close
    bf_raw = {}
    if base is not None and pd is not None:
        try:
            bf = base.get_backward_factor(codes, is_local=False)
            if bf is not None and not getattr(bf, "empty", True):
                for c in codes:
                    if c in getattr(bf, "columns", []):
                        s = bf[c]
                        if s is not None and len(s):
                            bf_raw[c] = s
        except Exception as e:
            sys.stderr.write("[警告] 后复权因子获取失败（将用不复权价格）：%s\n" % e)

    for c in codes:
        df = kl.get(c)
        if df is None or len(df) == 0:
            continue
        d = df.copy()
        d["kline_time"] = pd.to_datetime(d["kline_time"])
        d = d.sort_values("kline_time").reset_index(drop=True)

        # 前复权：price × backward_factor[t] / latest_factor
        fac = bf_raw.get(c)
        if fac is not None and len(fac):
            fs = fac.copy()
            fs.index = pd.to_datetime(fs.index)
            faligned = fs.reindex(d["kline_time"]).ffill()
            if faligned.notna().any():
                latest_fac = faligned[faligned.notna()].iloc[-1]
                if latest_fac and latest_fac != 0:
                    adj_ratio = faligned.values / latest_fac
                    for col in ["close"]:
                        if col in d.columns:
                            d[col] = d[col].astype(float) * adj_ratio
        else:
            sys.stderr.write("[警告] %s 后复权因子缺失，涨跌幅将使用不复权价格\n" % c)

        # 去除收盘价为 0/缺失的未完成当日Bar
        cl = d["close"].astype(float)
        d = d[cl.notna() & (cl > 0)]
        if len(d) == 0:
            d = df.copy()
            d["kline_time"] = pd.to_datetime(d["kline_time"])
            d = d.sort_values("kline_time").reset_index(drop=True)
        res[c] = compute_quote(d, today_date)
    return res


def fetch_equity(codes, info):
    res = {}
    if not codes:
        return res
    try:
        # is_local=False：强制从服务端取最新股本结构（避免本地空缓存导致市值算不出）
        eq = info.get_equity_structure(codes, local_path=AD_CACHE, is_local=False)
    except Exception as e:
        sys.stderr.write("[警告] 股本结构获取失败：%s\n" % e)
        return res
    if not hasattr(eq, "empty"):
        # 某些版本按 code 返回 dict
        for c in codes:
            df = eq.get(c) if isinstance(eq, dict) else None
            if df is not None and len(df):
                row = df.sort_values("CHANGE_DATE").iloc[-1]
                res[c] = (float(row["TOT_SHARE"]), float(row["FLOAT_A_SHARE"]))
        return res
    for c in codes:
        sub = eq[eq["MARKET_CODE"] == c] if "MARKET_CODE" in eq.columns else eq[eq["code"] == c]
        if len(sub) == 0:
            res[c] = (None, None)
            continue
        row = sub.sort_values("CHANGE_DATE").iloc[-1]
        # 单位换算：原始 TOT_SHARE/FLOAT_A_SHARE 为万股，转换为亿股
        res[c] = (float(row["TOT_SHARE"]) / 10000.0, float(row["FLOAT_A_SHARE"]) / 10000.0)
    return res


def _latest_fin_row(df):
    """取最新报告期财务行：仅合并报表(STATEMENT_TYPE='1')，同报告期取最新公告日，与基本面指标 skill 口径一致。"""
    if df is None or len(df) == 0:
        return None
    if "STATEMENT_TYPE" in df.columns:
        mask = df["STATEMENT_TYPE"].astype(str) == "1"
        if mask.any():
            df = df[mask]
    if df.empty:
        return None
    df = df.sort_values("REPORTING_PERIOD")
    if "ACTUAL_ANN_DATE" in df.columns:
        df = df.drop_duplicates("REPORTING_PERIOD", keep="last")
    return df.iloc[-1]


def _consolidated_inc(df):
    """取合并报表口径（STATEMENT_TYPE='1'）的利润表，按报告期去重（同报告期取最新公告日）。
    与基本面指标 skill 的 _filter_statements 一致。"""
    if df is None or len(df) == 0:
        return None
    mask = pd.Series(True, index=df.index)
    if "STATEMENT_TYPE" in df.columns:
        mask &= df["STATEMENT_TYPE"].astype(str) == "1"
    f = df[mask].copy()
    if f.empty:
        f = df.copy()
    if "ACTUAL_ANN_DATE" in f.columns and "REPORTING_PERIOD" in f.columns:
        f = f.sort_values(["REPORTING_PERIOD", "ACTUAL_ANN_DATE"])
        f = f.drop_duplicates("REPORTING_PERIOD", keep="last")
    else:
        f = f.sort_values("REPORTING_PERIOD").drop_duplicates("REPORTING_PERIOD", keep="last")
    return f


def get_ttm_net_profit(inc_df):
    """归母净利润TTM（滚动12个月），与基本面指标 skill 的 市盈率TTM 口径完全一致。

    算法（与 skill 的 get_ttm 相同）：
      Q1报告期: TTM = Q1本期 + 去年年报 - 去年Q1
      Q2报告期: TTM = Q2本期 + 去年年报 - 去年Q2
      Q3报告期: TTM = Q3本期 + 去年年报 - 去年Q3
      Q4报告期(年报): TTM = 年报值
    返回最新报告期的 TTM 归母净利润（元）。"""
    if inc_df is None or len(inc_df) == 0 or "NET_PRO_EXCL_MIN_INT_INC" not in inc_df.columns:
        return None
    f = _consolidated_inc(inc_df)
    if f is None or len(f) == 0:
        return None
    field = "NET_PRO_EXCL_MIN_INT_INC"
    rp = f["REPORTING_PERIOD"].astype(str)
    ttm = {}
    for i in range(len(f)):
        val = f[field].iloc[i]
        if val is None or (isinstance(val, float) and pd.isna(val)):
            continue
        rp_str = rp.iloc[i]
        yr = rp_str[:4]
        mmdd = rp_str[4:]
        if mmdd == "1231":
            ttm[rp_str] = float(val)
        else:
            prev_yr = str(int(yr) - 1)
            ann = f[rp == (prev_yr + "1231")]
            same = f[rp == (prev_yr + mmdd)]
            if len(ann) and len(same):
                av = ann[field].iloc[-1]
                sv = same[field].iloc[-1]
                if not pd.isna(av) and not pd.isna(sv):
                    ttm[rp_str] = float(val) + float(av) - float(sv)
    if not ttm:
        return None
    return ttm[max(ttm.keys())]


def _consolidated_bs(df):
    """取合并报表口径（STATEMENT_TYPE='1'）的资产负债表，按报告期去重（同报告期取最新公告日）。
    与基本面指标 skill 的 _filter_statements 一致。"""
    if df is None or len(df) == 0:
        return None
    mask = pd.Series(True, index=df.index)
    if "STATEMENT_TYPE" in df.columns:
        mask &= df["STATEMENT_TYPE"].astype(str) == "1"
    f = df[mask].copy()
    if f.empty:
        f = df.copy()
    if "ACTUAL_ANN_DATE" in f.columns and "REPORTING_PERIOD" in f.columns:
        f = f.sort_values(["REPORTING_PERIOD", "ACTUAL_ANN_DATE"])
        f = f.drop_duplicates("REPORTING_PERIOD", keep="last")
    else:
        f = f.sort_values("REPORTING_PERIOD").drop_duplicates("REPORTING_PERIOD", keep="last")
    return f


def fetch_fundamental(codes, info, today_int):
    """取 最新报告期归母净资产（PB 用）与 归母净利润TTM（PE_TTM 用），与基本面指标 skill 一致。
    - PB = 总市值 / (归母净资产 - 其他权益工具)：普通股口径，对应 skill 市净率70
      （其他权益工具=永续债/优先股，会计计入权益但不归属普通股股东，缺失时按 0 处理）
    - PE = 总市值 / 归母净利润TTM：对应 skill 市盈率TTM76，而非静态72"""
    res = {}
    if not codes:
        return res
    beg = int(date(today_int // 10000 - 2, 1, 1).strftime("%Y%m%d"))
    net_asset_map, np_ttm_map = {}, {}
    try:
        bs = info.get_balance_sheet(codes, begin_date=beg, end_date=today_int)
        for c, df in (bs.items() if isinstance(bs, dict) else [(None, bs)]):
            if df is None or len(df) == 0:
                continue
            f = _consolidated_bs(df)
            if f is None or len(f) == 0:
                continue
            row = f.iloc[-1]  # 已按报告期去重，末行=最新报告期
            na_raw = row.get("TOT_SHARE_EQUITY_EXCL_MIN_INT")
            if na_raw is None or (isinstance(na_raw, float) and pd.isna(na_raw)):
                net_asset_map[c] = None
                continue
            na = float(na_raw)
            oth = row.get("OTH_EQUITY_TOOLS")
            if oth is not None and not (isinstance(oth, float) and pd.isna(oth)):
                na = na - float(oth)  # 普通股口径净资产：剔除其他权益工具
            net_asset_map[c] = na
    except Exception as e:
        sys.stderr.write("[警告] 资产负债表获取失败：%s\n" % e)
    try:
        inc = info.get_income(codes, begin_date=beg, end_date=today_int)
        for c, df in (inc.items() if isinstance(inc, dict) else [(None, inc)]):
            if df is None or len(df) == 0:
                continue
            np_ttm_map[c] = get_ttm_net_profit(df)
    except Exception as e:
        sys.stderr.write("[警告] 利润表获取失败：%s\n" % e)
    for c in codes:
        res[c] = (net_asset_map.get(c), np_ttm_map.get(c))
    return res


def refresh_codes(db, codes, api):
    """联网计算并写回这些 code 的全部行情/基本面字段（按行更新，保留各行自选价格）"""
    if not codes or api is None:
        return
    base, market, info, today_int, ad = api
    quotes = fetch_quotes(codes, market, base, ad, today_int)
    equ = fetch_equity(codes, info)
    fin = fetch_fundamental(codes, info, today_int)
    # 取这些 code 的所有行（同 code 可能跨组）
    placeholders = ",".join("?" * len(codes))
    rows = db.conn.execute(
        "SELECT id, code, watch_price FROM stocks WHERE code IN (%s)" % placeholders, codes
    ).fetchall()
    for rid, code, wp in rows:
        q = quotes.get(code) or {}
        tot_share, float_share = equ.get(code, (None, None))
        net_asset, np_ttm = fin.get(code, (None, None))
        last_price = q.get("last_price")
        tot_mktcap = float(last_price) * float(tot_share) * 1e8 if (last_price and tot_share) else None
        float_mktcap = float(last_price) * float(float_share) * 1e8 if (last_price and float_share) else None
        pb = tot_mktcap / net_asset if (tot_mktcap and net_asset) else None
        pe = tot_mktcap / np_ttm if (tot_mktcap and np_ttm) else None
        # 自选价格：保留原值，为空则用最新价（默认自选价=当前价）
        if wp is None and last_price is not None:
            wp = last_price
        profit_pct = (last_price - wp) / wp * 100 if (last_price and wp) else None
        db.update_row_data(rid, {
            "last_price": last_price,
            "change_val": q.get("change_val"),
            "change_pct": q.get("change_pct"),
            "amount": q.get("amount"),
            "volume": q.get("volume"),
            "chg_week": q.get("chg_week"),
            "chg_month": q.get("chg_month"),
            "chg_year": q.get("chg_year"),
            "pb": pb,
            "pe": pe,
            "tot_share": tot_share,
            "float_share": float_share,
            "tot_mktcap": tot_mktcap,
            "float_mktcap": float_mktcap,
            "watch_price": wp,
            "profit_pct": profit_pct,
            "data_updated_at": _now(),
        })


def ensure_daily_refresh(db, api):
    """当日首次调用触发全量刷新。返回是否执行了刷新。"""
    if api is None:
        return False
    today = _now()[:10]
    last = db.get_meta("last_refresh_date")
    if last and last[:10] == today:
        return False
    codes = db.all_codes()
    if codes:
        print("[刷新] 当日首次调用，全量刷新 %d 只自选股行情与基本面..." % len(codes))
        refresh_codes(db, codes, api)
    db.set_meta("last_refresh_date", _now())
    return True


# ----------------------------------------------------------------------------
# HTML 生成
# ----------------------------------------------------------------------------
HTML_COLS = [
    ("idx", "", "text"),
    ("code", "代码", "text"), ("name", "名称", "text"),
    ("watch_price", "自选价", "price"), ("watch_time", "自选时间", "text"),
    ("last_price", "最新价", "price"), ("change_val", "涨跌", "price_pct"),
    ("change_pct", "涨幅", "pct"), ("amount", "成交额", "big"), ("volume", "成交量", "vol"),
    ("chg_week", "周涨幅", "pct"), ("chg_month", "月涨幅", "pct"), ("chg_year", "年涨幅", "pct"),
    ("profit_pct", "自选收益", "pct"), ("pb", "PB", "price"), ("pe", "PE(TTM)", "price"),
    ("tot_share", "总股本(亿)", "share"), ("float_share", "流通股本(亿)", "share"),
    ("tot_mktcap", "总市值", "big"), ("float_mktcap", "流通市值", "big"),
    ("market", "市场", "text"), ("watch_reason", "自选原因", "text"),
]


def _fmt_cell(kind, val):
    """把单个字段格式化为 {v: 排序用原始值, t: 展示文本}。"""
    if val is None or val == "":
        return {"v": None, "t": "-"}
    if kind == "text":
        return {"v": str(val), "t": str(val)}
    if kind == "price":
        return {"v": float(val), "t": fmt_price(val)}
    if kind == "pct":
        return {"v": float(val), "t": fmt_pct(val)}
    if kind == "price_pct":
        return {"v": float(val), "t": fmt_price(val)}
    if kind == "big":
        return {"v": float(val), "t": fmt_big(val)}
    if kind == "vol":
        return {"v": float(val), "t": fmt_vol(val)}
    if kind == "share":
        return {"v": float(val), "t": "%.2f" % val}
    return {"v": str(val), "t": str(val)}


def generate_html(db, group_filter=None):
    groups = db.list_groups()
    group_names = [g[1] for g in groups if (not group_filter or g[1] == group_filter)]

    data = {}
    for gid, gname, gdesc, gcreated, gcount in groups:
        if group_filter and gname != group_filter:
            continue
        rows = db.conn.execute(
            "SELECT code,name,watch_price,watch_time,last_price,change_val,change_pct,amount,volume,"
            "chg_week,chg_month,chg_year,profit_pct,pb,pe,tot_share,float_share,tot_mktcap,float_mktcap,"
            "market,watch_reason FROM stocks WHERE group_id=? ORDER BY code", (gid,)
        ).fetchall()
        recs = []
        for r in rows:
            rec = {}
            for i, (k, t, kind) in enumerate(HTML_COLS):
                if k == "idx":
                    continue  # 序号在 render 阶段注入，不来自 DB
                rec[k] = _fmt_cell(kind, r[i - 1])
            recs.append(rec)
        data[gname] = recs

    # 静态 fallback：每个分组独立表格 + 纯 CSS Tab 切换（不依赖 JS）
    import html as _html
    def _esc(s):
        return _html.escape("" if s is None else str(s), quote=False)
    def _pct_class(v, kind):
        """涨跌幅 CSS 类名：up=涨（红）、down=跌（绿），A股惯例"""
        if v is None:
            return ""
        if kind not in ("pct", "price_pct"):
            return ""
        if v > 0:
            return ' class="up"'
        if v < 0:
            return ' class="down"'
        return ""
    def _col_class(k, kind):
        """特殊列的 CSS 类名"""
        if k == "idx":
            return ' class="idx-col"'
        if k == "code":
            return ' class="code-col"'
        if k == "name":
            return ' class="name-col"'
        return ""
    tabs_html, radios_html, panels_html, css_rules = [], [], [], []
    first_non_empty = None
    for i, gname in enumerate(group_names):
        recs = data.get(gname, [])
        if first_non_empty is None and recs:
            first_non_empty = i
        head = "".join('<th>%s</th>' % _esc(t) for k, t, kind in HTML_COLS)
        if recs:
            body_rows = []
            for idx, rec in enumerate(recs):
                # 注入序号列
                rec["idx"] = {"v": idx + 1, "t": str(idx + 1)}
                tds = []
                for k, t, kind in HTML_COLS:
                    cell = rec.get(k)
                    txt = cell["t"] if cell else "-"
                    raw = cell["v"] if (cell and cell.get("v") is not None) else ""
                    cls = _col_class(k, kind) + _pct_class(cell["v"] if cell else None, kind)
                    tds.append('<td data-v="%s"%s>%s</td>' % (_esc(raw), cls, _esc(txt)))
                body_rows.append("<tr>%s</tr>" % "".join(tds))
            body = "".join(body_rows)
        else:
            body = '<tr><td colspan="%d">（该分组暂无自选股）</td></tr>' % len(HTML_COLS)
        tabs_html.append('<label class="tab" for="gtab-%d">%s</label>' % (i, _esc(gname)))
        panels_html.append('<div class="panel panel-%d"><div class="tbl-wrap"><table class="gtable"><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div></div>' % (i, head, body))
        css_rules.append("#gtab-%d:checked ~ .panel-%d{display:block;}" % (i, i))
        css_rules.append('body:has(#gtab-%d:checked) label[for=gtab-%d]{background:#2563eb;color:#fff;border-color:#2563eb;}' % (i, i))
    # 默认选中：第一个非空分组（若全空则选第一个）
    default_idx = first_non_empty if first_non_empty is not None else 0
    for i in range(len(group_names)):
        radios_html.append('<input type="radio" name="gtab" id="gtab-%d" class="gtab"%s>' % (i, " checked" if i == default_idx else ""))

    # ---- 从模板文件渲染 HTML（模板见 assets/templates/watchlist_template.html）----
    try:
        with open(HTML_TEMPLATE_PATH, "r", encoding="utf-8") as _tf:
            _tpl = _tf.read()
    except FileNotFoundError:
        raise RuntimeError("HTML 模板文件缺失：%s" % HTML_TEMPLATE_PATH)
    _meta = "数据刷新：" + (db.get_meta("last_refresh_date") or "-")
    return (_tpl
            .replace("__CSS_RULES__", "\n".join(css_rules))
            .replace("__META__", _meta)
            .replace("__TABS__", "".join(tabs_html))
            .replace("__RADIOS__", "\n".join(radios_html))
            .replace("__PANELS__", "\n".join(panels_html)))

def auto_html(db, out_path=None):
    out_path = out_path or DEFAULT_HTML_PATH
    html = generate_html(db)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("已生成 HTML 展示页：%s" % out_path)


# ----------------------------------------------------------------------------
# 命令实现
# ----------------------------------------------------------------------------
def cmd_group(db, args, api):
    if args.g_action == "add":
        ok, msg = db.add_group(args.name, args.description or "")
        print("已创建分组「%s」" % args.name if ok else "失败：%s" % msg)
    elif args.g_action == "rename":
        ok, msg = db.rename_group(args.name, args.new_name)
        print("已重命名" if ok and msg is None else ("无需修改" if msg == "无需修改" else "失败：%s" % msg))
    elif args.g_action == "remove":
        ok, msg = db.remove_group(args.name, args.force)
        print("已删除分组「%s」" % args.name if ok else "失败：%s" % msg)
    elif args.g_action == "list":
        rows = db.list_groups()
        print_table(["ID", "分组", "描述", "创建时间", "股票数"],
                    [(r[0], r[1], r[2], r[3], r[4]) for r in rows], args.json)
    auto_html(db)


def cmd_add(db, args, api):
    if api is None:
        print("错误：添加自选股需要联网补全行情与基本面数据；当前未联网或凭证不可用，无法添加。"
              "请联网后执行（不要加 --no-api）。", file=sys.stderr)
        return 1
    code = args.code.upper()
    grp = args.group or DEFAULT_GROUP
    if not db.get_group(grp):
        print("错误：分组「%s」不存在，请先创建。" % grp, file=sys.stderr)
        return 1
    # 联网补全基础信息
    info = api[2]
    name = market = plate = None
    try:
        basic = info.get_stock_basic([code])
        if basic is not None and len(basic):
            row = basic.iloc[0]
            name = row.get("SECURITY_NAME")
            plate = row.get("LISTPLATE_NAME")
            mk = code.split(".")[-1] if "." in code else ""
            market = {"SH": "上海", "SZ": "深圳", "BJ": "北京"}.get(mk.upper(), mk)
    except Exception as e:
        sys.stderr.write("[警告] 基础信息补全失败：%s\n" % e)
    if not name:
        print("错误：未查询到代码 %s 的基础信息，可能代码有误或接口异常。" % code, file=sys.stderr)
        return 1
    ok, msg = db.add_stock(grp, code, name, market, plate, watch_reason=args.reason, watch_price=args.price)
    if not ok:
        print("失败：%s" % msg, file=sys.stderr)
        return 1
    print("已添加 %s（%s）到分组「%s」" % (code, name, grp))
    # 触发：重算该分组全部数据
    codes = db.get_group_codes(grp)
    refresh_codes(db, codes, api)
    auto_html(db)
    return 0


def cmd_add_batch(db, args, api):
    if api is None:
        print("错误：批量添加需要联网补全行情与基本面数据，当前未联网或凭证不可用，无法添加。", file=sys.stderr)
        return 1
    grp = args.group or DEFAULT_GROUP
    if not db.get_group(grp):
        print("错误：分组「%s」不存在，请先创建。" % grp, file=sys.stderr)
        return 1
    codes = []
    if args.codes:
        codes += [c.strip().upper() for c in args.codes if c.strip()]
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    codes.append(line.upper())
    if not codes:
        print("错误：未提供任何代码（--codes 或 --file）。", file=sys.stderr)
        return 1
    added = 0
    for code in codes:
        if db.get_group(grp) is None:
            continue
        info = api[2]
        name = plate = None
        market = {"SH": "上海", "SZ": "深圳", "BJ": "北京"}.get(
            code.split(".")[-1].upper() if "." in code else "", "")
        try:
            basic = info.get_stock_basic([code])
            if basic is not None and len(basic):
                name = basic.iloc[0].get("SECURITY_NAME")
                plate = basic.iloc[0].get("LISTPLATE_NAME")
        except Exception:
            pass
        if not name:
            print("  跳过 %s：未查到基础信息" % code)
            continue
        ok, msg = db.add_stock(grp, code, name, market, plate, watch_reason=args.reason, watch_price=args.price)
        if ok:
            added += 1
            print("  已添加 %s（%s）" % (code, name))
        else:
            print("  跳过 %s：%s" % (code, msg))
    if added:
        refresh_codes(db, db.get_group_codes(grp), api)
        auto_html(db)
    return 0


def cmd_remove(db, args, api):
    n = db.remove_stock(args.code.upper(), args.group)
    print("已删除 %d 条记录（%s）" % (n, args.code.upper()))
    auto_html(db)


def cmd_remove_batch(db, args, api):
    codes = []
    if args.codes:
        codes += [c.strip().upper() for c in args.codes if c.strip()]
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    codes.append(line.upper())
    n = db.remove_stocks(codes, args.group)
    print("已批量删除 %d 条记录" % n)
    auto_html(db)


def cmd_list(db, args, api):
    if args.group and db.get_group(args.group) is None:
        print("错误：分组「%s」不存在。" % args.group, file=sys.stderr)
        return 1
    rows = db.list_stocks(args.group, detail=True)
    if rows is None:
        print("错误：分组「%s」不存在。" % args.group, file=sys.stderr)
        return 1
    if args.group:
        headers = ["代码", "名称", "自选价", "自选时间", "最新价", "涨幅", "周涨幅", "月涨幅",
                   "年涨幅", "自选收益", "PB", "PE", "总市值", "流通市值", "市场", "自选原因"]
        data = [(r[0], r[1], fmt_price(r[2]), r[3], fmt_price(r[4]), fmt_pct(r[5]),
                 fmt_pct(r[6]), fmt_pct(r[7]), fmt_pct(r[8]), fmt_pct(r[9]),
                 fmt_price(r[10]), fmt_price(r[11]), fmt_big(r[12]), fmt_big(r[13]),
                 r[14], r[16]) for r in rows]
    else:
        headers = ["代码", "名称", "分组", "自选价", "最新价", "涨幅", "周涨幅", "月涨幅",
                   "年涨幅", "自选收益", "PB", "PE", "总市值", "流通市值", "市场", "自选原因"]
        data = [(r[0], r[1], r[2], fmt_price(r[3]), fmt_price(r[5]), fmt_pct(r[6]),
                 fmt_pct(r[7]), fmt_pct(r[8]), fmt_pct(r[9]), fmt_pct(r[10]),
                 fmt_price(r[11]), fmt_price(r[12]), fmt_big(r[13]), fmt_big(r[14]),
                 r[15], r[17]) for r in rows]
    print_table(headers, data, args.json)


def cmd_info(db, args, api):
    rows = db.get_stock_detail(args.code.upper())
    if not rows:
        print("未找到 %s" % args.code.upper())
        return
    r = rows[0]
    labels = ["代码", "名称", "所属分组", "自选价格", "自选时间", "最新价", "涨跌额", "涨幅",
              "成交额", "成交量", "本周涨幅", "本月涨幅", "本年涨幅", "自选收益",
              "市净率PB", "市盈率PE", "总股本(亿)", "流通股本(亿)", "总市值", "流通市值",
              "市场", "板块", "自选原因", "数据刷新时间"]
    for i, lab in enumerate(labels):
        v = r[i]
        if i in (3, 5, 6, 14, 15):
            v = fmt_price(v)
        elif i in (7, 10, 11, 12, 13):
            v = fmt_pct(v)
        elif i in (8, 18, 19):
            v = fmt_big(v)
        elif i == 9:
            v = fmt_vol(v)
        elif i in (16, 17):
            v = ("%.2f" % v) if v is not None else "-"
        elif i == 22:  # 自选原因（可空）
            v = v if v else "-"
        print("%-12s: %s" % (lab, v))


def cmd_search(db, args, api):
    rows = db.search_stocks(args.keyword)
    print_table(["代码", "名称", "分组", "自选价", "最新价", "涨幅", "自选收益", "自选原因"],
                [(r[0], r[1], r[2], fmt_price(r[3]), fmt_price(r[4]),
                  fmt_pct(r[5]), fmt_pct(r[6]), r[7]) for r in rows], args.json)


def cmd_html(db, args, api):
    if args.open:
        auto_html(db, args.output)
        import webbrowser
        webbrowser.open("file://" + os.path.abspath(args.output or DEFAULT_HTML_PATH))
    else:
        auto_html(db, args.output)


def cmd_export(db, args, api):
    if args.group and db.get_group(args.group) is None:
        print("错误：分组「%s」不存在。" % args.group, file=sys.stderr)
        return 1
    if args.group:
        rows = db.conn.execute(
            "SELECT code,name,watch_price,watch_time,last_price,change_val,change_pct,amount,volume,"
            "chg_week,chg_month,chg_year,profit_pct,pb,pe,tot_share,float_share,tot_mktcap,float_mktcap,"
            "market,watch_reason FROM stocks WHERE group_id=(SELECT id FROM groups WHERE name=?)",
            (args.group,)).fetchall()
    else:
        rows = db.conn.execute(
            "SELECT code,name,watch_price,watch_time,last_price,change_val,change_pct,amount,volume,"
            "chg_week,chg_month,chg_year,profit_pct,pb,pe,tot_share,float_share,tot_mktcap,float_mktcap,"
            "market,watch_reason FROM stocks").fetchall()
    import csv
    out = args.output or "watchlist_export.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["代码", "名称", "自选价", "自选时间", "最新价", "涨跌额", "涨幅", "成交额", "成交量",
                    "周涨幅", "月涨幅", "年涨幅", "自选收益", "PB", "PE", "总股本(亿)", "流通股本(亿)",
                    "总市值", "流通市值", "市场", "自选原因"])
        for r in rows:
            w.writerow([r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10],
                        r[11], r[12], r[13], r[14], r[15], r[16], r[17], r[18], r[19], r[20]])
    print("已导出 CSV：%s" % out)


# ----------------------------------------------------------------------------
# 入口
# ----------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(description="自选股管理 (ad_watchlist)")
    p.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite 数据库路径")
    p.add_argument("--no-api", action="store_true", help="离线模式：不联网，仅本地查看（添加/刷新将被拒绝）")
    p.add_argument("--json", action="store_true", help="列表/查询输出 JSON")
    p.add_argument("--refresh", action="store_true", help="强制全量刷新行情与基本面")
    sub = p.add_subparsers(dest="cmd", required=True)

    pg = sub.add_parser("group", help="分组管理")
    pg.add_argument("g_action", choices=["add", "rename", "remove", "list"])
    pg.add_argument("name")
    pg.add_argument("new_name", nargs="?", help="rename 时的新名称")
    pg.add_argument("-d", "--description", help="分组描述")
    pg.add_argument("--force", action="store_true", help="remove 时强制删除非空分组")

    pa = sub.add_parser("add", help="添加单只自选股")
    pa.add_argument("code")
    pa.add_argument("-g", "--group", default=DEFAULT_GROUP)
    pa.add_argument("-p", "--price", type=float, help="自选价格（默认=添加时最新价）")
    pa.add_argument("-r", "--reason", help="自选原因（记录添加想法，可留空）")

    pb = sub.add_parser("add-batch", help="批量添加自选股")
    pb.add_argument("-g", "--group", default=DEFAULT_GROUP)
    pb.add_argument("--codes", nargs="*", help="代码列表")
    pb.add_argument("--file", help="代码文件（每行一个，# 开头为注释）")
    pb.add_argument("-p", "--price", type=float, help="自选价格（默认=添加时最新价）")
    pb.add_argument("-r", "--reason", help="自选原因（记录添加想法，可留空，批量时应用到全部）")

    pr = sub.add_parser("remove", help="删除单只自选股")
    pr.add_argument("code")
    pr.add_argument("-g", "--group", help="指定分组（不指定则从所有分组中删除该代码）")

    prb = sub.add_parser("remove-batch", help="批量删除自选股")
    prb.add_argument("--codes", nargs="*")
    prb.add_argument("--file", help="代码文件")
    prb.add_argument("-g", "--group", help="指定分组")

    pl = sub.add_parser("list", help="查询列表")
    pl.add_argument("-g", "--group", help="指定分组")

    pi = sub.add_parser("info", help="单只详情")
    pi.add_argument("code")

    ps = sub.add_parser("search", help="搜索")
    ps.add_argument("keyword")

    ph = sub.add_parser("html", help="生成 HTML 展示页")
    ph.add_argument("-g", "--group", help="仅生成某分组")
    ph.add_argument("-o", "--output", help="输出路径（默认 data/watchlist.html）")
    ph.add_argument("--open", action="store_true", help="生成后用浏览器打开")

    pe = sub.add_parser("export", help="导出 CSV")
    pe.add_argument("-g", "--group", help="指定分组")
    pe.add_argument("-o", "--output", help="输出路径")
    return p


def main():
    args = build_parser().parse_args()
    db = WatchlistDB(args.db)

    api = None
    if not args.no_api:
        api = login_ad()
        if api is None and args.cmd in ("add", "add-batch"):
            db.close()
            print("错误：添加操作必须联网，但星耀数智登录失败。请检查网络与凭证（AD_USERNAME/AD_PASSWORD/AD_HOST/AD_PORT）。",
                  file=sys.stderr)
            return 1
        # 当日首次 / 强制刷新
        if args.refresh and api is not None:
            codes = db.all_codes()
            if codes:
                print("[刷新] 强制全量刷新 %d 只..." % len(codes))
                refresh_codes(db, codes, api)
            db.set_meta("last_refresh_date", _now())
            auto_html(db)
        else:
            ensure_daily_refresh(db, api)

    dispatch = {
        "group": cmd_group,
        "add": cmd_add,
        "add-batch": cmd_add_batch,
        "remove": cmd_remove,
        "remove-batch": cmd_remove_batch,
        "list": cmd_list,
        "info": cmd_info,
        "search": cmd_search,
        "html": cmd_html,
        "export": cmd_export,
    }
    rc = dispatch[args.cmd](db, args, api)
    db.close()
    return rc or 0


if __name__ == "__main__":
    sys.exit(main())
