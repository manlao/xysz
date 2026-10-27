# -*- coding: utf-8 -*-
"""会话管理：单进程单登录，行情与柜台并存。

要点（均为实测结论）：

1. ad.login(..., only_trade=True) 只调 trade.init_cgst(user, pwd) 后立即 return，
   **不走 tgw 完整登录**，因此不占用单点登录会话，重复调用幂等。
2. only_trade 会话内行情接口不可用（ad.BaseData() 抛 TypeError）；
   但同一进程内再补一次完整登录，行情与柜台即可同时可用（两种顺序皆可）。
3. ad.login 登录失败会静默 exit(0)（只 print 'login fail'），看不到堆栈，
   因此这里必须自建重试：正常登录失败后用 force_logout 强制踢掉残留会话再试。
"""
import time
import datetime

from common import load_config, current_stage, is_snapshot_stage

# 登录重试的退避间隔（秒）
_RETRY_DELAYS = (0, 3, 6, 12, 20, 30)

_login_ok = False
_trade_ready = False
_config = None
_calendar = None
_calendar_days = None
_md = None


class LoginError(Exception):
    """登录最终失败"""


def config():
    """返回登录配置（首次调用时读环境变量）。"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def ensure_login(verbose=False):
    """完整登录（tgw），供行情接口使用。带 force_logout 重试。"""
    global _login_ok
    if _login_ok:
        return True

    cfg = config()
    import tgw

    last_err = ''
    for i, delay in enumerate(_RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        force = (i > 0)
        try:
            tgw.Close()
        except Exception:
            pass
        c = tgw.Cfg()
        c.username = cfg['AD_USERNAME']
        c.password = cfg['AD_PASSWORD']
        c.server_vip = cfg['AD_HOST']
        c.server_port = cfg['AD_PORT']
        c.force_logout = force
        try:
            ok = tgw.Login(c, tgw.ApiMode.kInternetMode)
        except Exception as e:
            last_err = '%s: %s' % (type(e).__name__, e)
            ok = False
        if ok:
            _login_ok = True
            if verbose:
                print('[登录] 行情会话就绪（尝试 %d 次，force_logout=%s）'
                      % (i + 1, force))
            return True
        last_err = last_err or '柜台返回登录失败（可能被单点登录占用）'

    raise LoginError(
        '行情登录失败，已重试 %d 次。最后原因：%s\n'
        '常见原因：账号密码错误、账号已被其他会话占用（单点登录限制）、服务端异常。\n'
        '建议：等待 60-90 秒后重试；或确认没有其他程序（如 PyCharm 控制台）正在占用该账号。'
        % (len(_RETRY_DELAYS), last_err))


def ensure_trade(verbose=False):
    """初始化交易柜台，供 trade 模块全部接口使用。幂等。"""
    global _trade_ready
    if _trade_ready:
        return True
    cfg = config()
    from AmazingData.trade_center import trade
    trade.init_cgst(cfg['trade_username'], cfg['trade_password'])
    _trade_ready = True
    if verbose:
        print('[登录] 交易柜台就绪')
    return True


def login(need_market=True, need_trade=True, verbose=False):
    """按需建立会话。

    - need_market=False 且 need_trade=True → 只初始化柜台，不占单点登录（用户指定价格下单走这条）
    - need_market=True → 完整登录（行情），必要时一并初始化柜台
    """
    if need_market:
        ensure_login(verbose=verbose)
    if need_trade:
        ensure_trade(verbose=verbose)
    return True


def trade_module():
    """返回已初始化的 trade 模块。"""
    ensure_trade()
    from AmazingData.trade_center import trade
    return trade


def calendar():
    """交易日历（含当日），带缓存。"""
    global _calendar
    if _calendar is None:
        ensure_login()
        _calendar = ad_base().get_calendar()
    return _calendar


def ad_base():
    import AmazingData as ad
    return ad.BaseData()


_calendar_days = None


def calendar_days():
    """交易日历（int 列表，升序），带缓存。"""
    global _calendar_days
    if _calendar_days is None:
        _calendar_days = sorted(int(x) for x in calendar())
    return _calendar_days


def is_trading_day(day=None):
    """判断指定日期（默认今天）是否交易日。

    按日期本身逐日判断——**不做跨日期缓存**，否则传入不同日期会拿到
    首次调用的错误结果。
    """
    day = day or datetime.date.today()
    return int(day.strftime('%Y%m%d')) in set(calendar_days())


def last_completed_trading_day():
    """最近一个「已完成」的交易日。

    今天若是交易日且尚未收盘（盘前/盘中/午休），今日日线尚未生成，
    须取上一个交易日；今天若非交易日，则取日历中 <= today 的最大交易日。
    """
    cal = calendar_days()
    td = int(datetime.date.today().strftime('%Y%m%d'))
    if td in set(cal):
        stage = current_stage(is_trading_day=True)
        # 非交易时段（含盘后）当日日线已生成，可用当日；否则回退上一交易日
        if not is_snapshot_stage(stage):
            return td
    prev = [x for x in cal if x < td]
    if prev:
        return prev[-1]
    raise LoginError('交易日历中找不到可用交易日')


def market_data():
    """返回 ad.MarketData 实例（需先完整登录）。"""
    global _md
    if _md is None:
        ensure_login()
        import AmazingData as ad
        _md = ad.MarketData(calendar())
    return _md


def reset():
    """重置会话状态（测试用）。"""
    global _login_ok, _trade_ready, _config, _calendar, _calendar_days, _md
    _login_ok = False
    _trade_ready = False
    _config = None
    _calendar = None
    _calendar_days = None
    _md = None