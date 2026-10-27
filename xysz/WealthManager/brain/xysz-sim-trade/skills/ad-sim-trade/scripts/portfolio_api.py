# -*- coding: utf-8 -*-
"""组合接口封装（4 个）：新建 / 查询列表 / 组合收益 / 收益率曲线

所有接口返回 (res, error_code)；error_code 是字符串，'00000' 成功、None 为入参未校验。
组合接口入参统一用 account_id（资金账户id，即组合编号）。
"""
import session
from common import check, OK_CODE, TradeError, to_date_int

# 每个用户最多只能建 1 个组合（后台限制）
MAX_PORTFOLIO = 1
# 建组合初始资金固定 100 万（按业务要求，不对用户开放为参数）
FIXED_BEGIN_FUND = 1000000.0


def get_list(status=1):
    """查组合列表。status：0-删除 / 1-正常（默认）/ 2-开户中 / 3-开户失败。"""
    tr = session.trade_module()
    df, code = tr.get_portfolio_list(status=int(status))
    check(code, '查询组合列表')
    return df


def _all_names():
    """全部状态的组合名称集合（重名预检用）。"""
    used = set()
    for st in (1, 0, 2, 3):
        tr = session.trade_module()
        df, code = tr.get_portfolio_list(status=st)
        if code == OK_CODE and df is not None and len(df):
            used.update(n for n in df['portfolio_name'].tolist() if n)
    return used


def create(name, description=''):
    """新建组合。

    初始资金固定 100 万；名称必填无默认；建前做重名与配额预检。

    配额规则：**每个用户最多只能建 1 个组合**（后台限制），已建则无法再建。
    """
    if not name or not str(name).strip():
        raise TradeError('组合名称必须由你输入（不提供默认名称）。请指定 --name。')
    name = str(name).strip()
    if len(name) > 50:
        raise TradeError('组合名称不能超过 50 字符，当前 %d 字符' % len(name))

    # 配额预检：每个用户仅可建 1 个组合
    tr = session.trade_module()
    df, code = tr.get_portfolio_list(status=1)
    check(code, '查询组合列表')
    cur = len(df) if df is not None else 0
    if cur >= MAX_PORTFOLIO:
        existing = df.iloc[0].get('portfolio_name') if cur else '-'
        raise TradeError(
            '每个用户最多只能建 1 个组合，当前已有组合「%s」（编号 %s），无法新建。\n'
            '如需在新的组合上操作，请直接使用已有组合。'
            % (existing, df.iloc[0].get('account_id') if cur else '-'))

    # 重名预检
    used = _all_names()
    if name in used:
        raise TradeError('组合名称「%s」已存在，名称不可复用，请换一个名称。' % name)

    res, code = tr.create_portfolio(name, begin_fund=FIXED_BEGIN_FUND,
                                    description=description or '')
    check(code, '新建组合')
    return res


def info(account_ids, date=None):
    """组合收益数据（25 列）。account_ids 支持多个。"""
    if isinstance(account_ids, (int, str)):
        account_ids = [account_ids]
    ids = [int(a) for a in account_ids]
    d = to_date_int(date) if date else None
    tr = session.trade_module()
    df, code = tr.get_portfolio_benefits_info(d, ids)
    check(code, '查询组合收益数据')
    return df


def curve(account_id, begin_date=None, end_date=None, length=None):
    """历史收益率曲线（2 列：date / profit_rate）。"""
    tr = session.trade_module()
    kw = {}
    if begin_date is not None:
        kw['begin_date'] = to_date_int(begin_date)
    if end_date is not None:
        kw['end_date'] = to_date_int(end_date)
    if length is not None:
        kw['len'] = int(length)
    df, code = tr.get_portfolio_benefits_rate(int(account_id), **kw)
    check(code, '查询历史收益率曲线')
    return df