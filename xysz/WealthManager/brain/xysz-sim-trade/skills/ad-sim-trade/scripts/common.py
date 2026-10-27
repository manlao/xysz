# -*- coding: utf-8 -*-
"""公共工具：环境变量读取、错误码中文翻译、代码校验、费率计算、时段判定

被 session.py / price_resolver.py / trade_api.py / portfolio_api.py / trade_cli.py 复用。
"""
import os
import re
import datetime

# ---------------------------------------------------------------- 环境变量

ENV_REQUIRED = ('AD_USERNAME', 'AD_PASSWORD', 'AD_HOST', 'AD_PORT')


class ConfigError(Exception):
    """环境变量缺失或不合法"""


def load_config():
    """读取登录配置。

    统一用 AD_* 一套变量（同一套账号同时覆盖行情与柜台）；
    AD_TRADE_* 为可选覆盖项，未设时回落到 AD_*。

    返回 dict：username / password / host / port（int）
    """
    cfg = {}
    missing = []
    for k in ENV_REQUIRED:
        v = os.environ.get(k)
        if not v:
            missing.append(k)
        cfg[k] = v
    if missing:
        raise ConfigError(
            '缺少环境变量：%s\n请先配置后再使用：\n'
            '  Windows CMD      : set AD_USERNAME=xxx & set AD_PASSWORD=xxx '
            '& set AD_HOST=xxx & set AD_PORT=xxx\n'
            '  Windows PowerShell: $env:AD_USERNAME="xxx"; $env:AD_PASSWORD="xxx"; '
            '$env:AD_HOST="xxx"; $env:AD_PORT="xxx'
            % '、'.join(missing))

    # 柜台专用覆盖项（可选）
    cfg['trade_username'] = os.environ.get('AD_TRADE_USERNAME') or cfg['AD_USERNAME']
    cfg['trade_password'] = os.environ.get('AD_TRADE_PASSWORD') or cfg['AD_PASSWORD']
    cfg['trade_host'] = os.environ.get('AD_TRADE_HOST') or cfg['AD_HOST']
    cfg['trade_port'] = int(os.environ.get('AD_TRADE_PORT') or cfg['AD_PORT'])

    try:
        # 端口必须是 int：传字符串会报 Cfg_server_port_set
        cfg['AD_PORT'] = int(cfg['AD_PORT'])
    except (TypeError, ValueError):
        raise ConfigError('AD_PORT 必须是整数，当前值：%r' % cfg['AD_PORT'])
    return cfg


# ---------------------------------------------------------------- 错误码

OK_CODE = '00000'

# SDK 层
_ERROR_CODES = {
    # 通用
    '00000': '正常',
    '30001': '权限验证失败',
    '30002': '处理异常',
    '30003': '查股东代码失败',
    '30004': '处理失败',
    # 组合类
    '101': '账号为空或无效',
    '1001': '组合不存在',
    '1002': '该组合不属于当前账户',
    '1003': '参数校验失败 / 归属校验拒绝',
    '10001': '组合名称为空或格式错误',
    '10002': '组合名称已存在',
    '10003': '初始资金不合法',
    '10004': '渠道标识不合法',
    '10005': '系统异常，请稍后重试',
    '10006': '组合数量已达上限（最多 5 个）',
    '5000': '系统错误，请稍后重试',
    # 交易类
    '-1000': '处理异常，请稍后再试',
    '-1001': '登录非 A 股模块',
    '-1002': '登录资金账号生成错误',
    '-1003': '登录写资金账号映射错误',
    '-1004': '登录写用户信息错误',
    '-1005': '查询用户信息错误',
    '-1006': '查询用户历史信息错误',
    '-1007': '查询历史日期错误',
    '-1008': '查询委托请求参数错误',
    '-1009': '查询交易市场错误',
    '-1010': '查询股东代码错误',
    '-1011': '查询股票代码错误',
    '-1013': '行情服务缺少涨跌停数据',
    '-1014': '买入价格超出涨跌停',
    '-1015': '卖出价格超出涨跌停',
    '-1016': '下单获取用户信息错误',
    '-1017': '下单请求价格错误',
    '-1018': '股票数量超过总资产限额比例',
    '-1019': '买入数目非整数手',
    '-1020': '买入可用资金不足',
    '-1021': '卖出查无持仓',
    '-1022': '卖出持仓数目不足',
    '-1023': '卖出数目非整数手',
    '-1024': '委托编号生成错误',
    '-1025': '委托索引插入失败',
    '-1026': '委托记录插入数据库失败',
    '-1027': '委托重试超时',
    '-1028': '委托记录插入内存失败',
    '-1029': '撤单查无委托记录',
    '-1030': '该委托单不能撤单',
    '-1031': '非交易时段不能下单',
    '-1032': '登录读用户信息错误',
    '-1033': '登录创建用户索引错误',
    '-1034': '交易请求被限制',
    '-1035': '订单撮合失败',
    '-1036': '登录参数非法',
    '-1037': '找不到用户数据库',
    '-1038': '写入数据库错误',
    '-1039': '查询资金历史数据库错误',
    '-1042': '查询持仓数据库错误',
    '-1043': '查询交易数据库错误',
    '-1044': '查询收益率错误',
    '-1045': '获取交易参数异常，请稍后重试',
    '-1046': '没有查询到数据',
    '-1047': '没有查到组合信息',
    '-1048': '组合创建读取用户信息错误',
    '-1049': '组合创建写入错误',
    '-1050': '组合名字重复错误',
    '-1051': '组合初始资金错误',
    '-1052': '组合生成 ID 错误',
    '-1053': '组合持仓数据不为空',
    '-1054': '组合存在未结算资金',
    '-1055': '组合更新数据错误',
    '-1056': '暂无数据',
    '-1057': '登录写用户交易信息错误',
    '-1058': '组合已有数据',
    '-1059': '组合已经结束',
    '-1060': '写用户信息错误',
    '-1061': '当前无成交，下单失败',
    '-1066': '账号类型不具备该类型品种的交易权限',
    '-1071': '今日提交委托次数已达上限，若有挂单未成交，请先撤单',
    '-1072': '持仓标的已达到最大值，无法新提交买入委托',
    '-1073': '涨跌幅度为 20% 的品种市值已达最大值，无法新提交买入委托',
    '-1074': '组合近 3 个月最大回撤达阈值，触发暂停买入',
    '-1082': '非交易日期不能下单',
    '-1083': '无涨跌停禁止市价单',
    '-1101': '买卖价格不符合最小价差要求',
    '-1102': '无法获取最小交易单位',
    '-1103': '无法获取交易汇率',
    '-1201': '委托方向错误',
    '-1301': '委托类型错误',
    '-1302': '委托数量超过最大限额',
    '-1401': '资产账户属性错误',
    '-1502': '股票的可买数量不足',
    '-10086': '获取风控信息失败',
    '-1611': '不在限价委托有效价格范围内',
    '-1612': '成交编号生成失败',
    '-1650': '非交易时段不能撤单',
    '-1701': '不满足保护限价要求',
    '-1702': '不满足保护限价要求，委托超出涨跌停',
    '-1800': '查询历史日期区间超过限制',
}

# 入参未通过校验的常见原因（error_code 为 None 时给用户的定位方向）
_LOCAL_CHECK_HINTS = (
    '入参未通过校验，请求未发出。常见原因：证券代码格式或市场后缀不合法'
    '（须为「代码.市场」，后缀仅 SH/SZ/BJ，且代码与后缀须匹配）、'
    '查询类 code 未传 list、日期格式非 8 位整数、'
    'side 超出 Buy/Sell、组合名称为空。详细原因见日志。'
)


class TradeError(Exception):
    """柜台调用失败（已带中文原因）"""

    def __init__(self, message, code=None, action=''):
        super().__init__(message)
        self.code = code
        self.action = action


def explain_code(code):
    """把 error_code 翻译为中文说明。

    error_code 是字符串类型：'00000' 成功、None 表示入参未校验、其他为具体错误码（可能带负号）。
    """
    if code == OK_CODE:
        return '成功'
    if code is None:
        return _LOCAL_CHECK_HINTS
    return _ERROR_CODES.get(str(code), '未知错误码')


def check(code, action):
    """断言调用成功，失败抛 TradeError（带中文原因）。"""
    if code == OK_CODE:
        return True
    raise TradeError('%s 失败：%s（错误码 %s）' % (action, explain_code(code), code),
                     code=code, action=action)


# ---------------------------------------------------------------- 代码校验

# 板块判断：科创板 688/689 开头，创业板 300/301 开头
_STAR = ('688', '689')
_CHINEXT = ('300', '301')

# 下单支持的证券类型（与柜台 trade.py 的 _ORDER_ALLOWED_TYPES 一致）
ORDER_ALLOWED_TYPES = ('EXTRA_STOCK_A', 'EXTRA_ETF')


def _security_type_info():
    """取 AmazingData 官方的代码规则表（格式校验的权威来源）。"""
    from AmazingData.config.security_type_config import security_type_info
    return security_type_info


def _is_security_type(code, sec_type):
    """调用官方 is_security_type 判断证券类型。

    注意：底层是 re.match 前缀匹配，格式的权威校验由本模块的 fullmatch 负责。
    """
    from AmazingData.utils.security_type import is_security_type
    return bool(is_security_type(code, sec_type))


def parse_code(code):
    """校验并解析证券代码，返回 (code6, market)。

    格式校验采用 AmazingData 官方 `security_type_config.base_type` 正则做
    **fullmatch**，与柜台 `trade._split_code` 完全一致——不自行推断代码段与
    市场的对应关系（那是易错点，例如沪市国债、深市可转债、北交所股票的首位
    数字与常见板块都不同，凭首位猜测必然出错）。
    """
    if not isinstance(code, str):
        raise TradeError('证券代码必须是字符串，当前值：%r' % (code,))
    text = code.strip()
    if text.count('.') != 1:
        raise TradeError(
            '证券代码格式非法：%s\n应为「代码.市场」形式，如 600***.SH、510***.SH、'
            '159***.SZ，市场后缀仅支持 SH / SZ / BJ。' % code)
    c6, suffix = text.split('.')
    suffix = suffix.upper()
    base = _security_type_info()['base_type']
    patterns = {'SH': base.get('MARKET_SH'),
                'SZ': base.get('MARKET_SZ'),
                'BJ': base.get('BJ_A')}.get(suffix)
    if not patterns:
        raise TradeError(
            '证券代码 %s 的市场后缀非法，仅支持 SH / SZ / BJ。' % code)
    if not any(re.fullmatch(p, text) for p in patterns):
        raise TradeError(
            '证券代码 %s 与市场后缀 .%s 不匹配（校验规则取自 AmazingData 官方 '
            'security_type_config，请核对代码所属交易所）。' % (code, suffix))
    return c6, suffix


def is_tradable(code):
    """判断是否可下单：仅支持股票与 ETF。

    与柜台 `trade._check_order_type` 同一判定口径（EXTRA_STOCK_A / EXTRA_ETF）。
    """
    return any(_is_security_type(code, t) for t in ORDER_ALLOWED_TYPES)


def board_of(code6):
    """判断板块：main / star / chinext / bse。

    入参可以是 6 位纯代码或「代码.市场」完整形式。
    """
    c6 = str(code6).strip()
    if '.' in c6:
        c6 = c6.split('.')[0]
    if '.' in str(code6) and str(code6).strip().upper().endswith('.BJ'):
        return 'bse'
    if c6.startswith(_STAR):
        return 'star'
    if c6.startswith(_CHINEXT):
        return 'chinext'
    return 'main'


def is_etf_like(code6):
    """判断是否场内基金（ETF），用官方 is_security_type 的 EXTRA_ETF 口径。

    用于费率与最小价位；可下单与否仍以 is_tradable 为准。
    """
    text = str(code6).strip()
    if '.' not in text:
        # 纯 6 位代码无法判定类型，交由调用方传入完整形式
        return False
    return _is_security_type(text.upper(), 'EXTRA_ETF')


def price_tick(code6):
    """最小价格变动单位：ETF 0.001，股票 0.01。"""
    return 0.001 if is_etf_like(code6) else 0.01


def limit_pct_of(code6):
    """涨跌幅比例：科创板/创业板 20%，其余 10%。"""
    return 0.20 if board_of(code6) in ('star', 'chinext') else 0.10


# ---------------------------------------------------------------- 费率

# 品种：佣金比例、印花税率、过户费率、单笔最低佣金
FEE_TABLE = {
    'stock': (0.0003, 0.0005, 0.00001, 5.0),
    'bse': (0.0015, 0.0005, 0.00001, 5.0),
    'fund': (0.0003, 0.0, 0.0, 5.0),
}


def estimate_fee(code6, amount):
    """估算交易费用。

    返回 dict：commission 佣金 / stamp_tax 印花税 / transfer_fee 过户费 / total 合计。
    印花税仅股票收取，场内基金不收；佣金有单笔最低 5 元。
    """
    b = board_of(code6)
    if b == 'bse':
        rate, stamp, transfer, minimum = FEE_TABLE['bse']
    elif is_etf_like(code6):
        rate, stamp, transfer, minimum = FEE_TABLE['fund']
    else:
        rate, stamp, transfer, minimum = FEE_TABLE['stock']
    commission = max(amount * rate, minimum) if amount > 0 else 0.0
    stamp_tax = amount * stamp
    transfer_fee = amount * transfer
    return {
        'commission': round(commission, 2),
        'stamp_tax': round(stamp_tax, 2),
        'transfer_fee': round(transfer_fee, 2),
        'total': round(commission + stamp_tax + transfer_fee, 2),
    }


# ---------------------------------------------------------------- 时段

# 时间常量（HHMM 秒或 datetime.time）
T_PRE_OPEN = (9, 15, 0)
T_AM_OPEN = (9, 30, 0)
T_AM_CLOSE = (11, 30, 0)
T_PM_OPEN = (13, 0, 0)
T_PM_CLOSE = (15, 0, 0)
T_SETTLE = (16, 30, 0)   # 盘后结算
T_CLEAR = (17, 0, 0)    # 盘后清算
T_DIVIDEND = (17, 30, 0)  # 盘后分红

STAGE_PRE = '盘前'
STAGE_PRE_OPEN = '早盘前段'
STAGE_AM = '上午连续竞价'
STAGE_NOON = '午间休市'
STAGE_PM = '下午连续竞价'
STAGE_AFTER_CLOSE = '盘后至结算'
STAGE_AFTER_SETTLE = '盘后结算后'
STAGE_AFTER_CLEAR = '盘后清算后'
STAGE_AFTER_DIV = '盘后分红后'
STAGE_NON_TRADING_DAY = '非交易日'


def _hm(t):
    return t[0] * 3600 + t[1] * 60 + t[2]


def current_stage(now=None, is_trading_day=True):
    """判定当前所处阶段。

    先看是否交易日，再按时间落阶段。

    时间口径（三个概念勿混）：
    - **撮合时段** 9:30–11:30 / 13:00–15:00，委托实际撮合的窗口；
    - **09:15** 是快照数据的起始点（取价参数下界），此时尚未进入撮合时段，
      挂单会被拒（`-1031`），故单独归为「早盘前段」；
    - 午休 11:30–13:00 可挂单可撤单，但均延后到 13:00 生效。
    """
    now = now or datetime.datetime.now()
    if not is_trading_day:
        return STAGE_NON_TRADING_DAY
    sec = now.hour * 3600 + now.minute * 60 + now.second
    if sec < _hm(T_PRE_OPEN):
        return STAGE_PRE
    if sec < _hm(T_AM_OPEN):
        return STAGE_PRE_OPEN
    if sec < _hm(T_AM_CLOSE):
        return STAGE_AM
    if sec < _hm(T_PM_OPEN):
        return STAGE_NOON
    if sec < _hm(T_PM_CLOSE):
        return STAGE_PM
    if sec < _hm(T_SETTLE):
        return STAGE_AFTER_CLOSE
    if sec < _hm(T_CLEAR):
        return STAGE_AFTER_SETTLE
    if sec < _hm(T_DIVIDEND):
        return STAGE_AFTER_CLEAR
    return STAGE_AFTER_DIV


def is_snapshot_stage(stage):
    """该阶段是否应走「当日快照取价」。

    含早盘前段（09:15–09:30）：此时已有快照数据，虽不能下单，但取价仍应取
    当日最新价而非前收盘价。
    """
    return stage in (STAGE_PRE_OPEN, STAGE_AM, STAGE_PM, STAGE_NOON)


def noon_price_window(now):
    """午休时段的取价查询窗口。

    返回 (begin_time, end_time)：结束固定 11:31:00，开始从 11:29 起按三角数回退。
    时间戳为 9 位 HHMMSS000。
    """
    end_time = 113100000
    base = datetime.datetime(now.year, now.month, now.day, 11, 29, 0)
    return base, end_time


def today_str():
    return datetime.date.today().strftime('%Y%m%d')


def to_date_int(d):
    """datetime/date/str(YYYYMMDD) → 8 位 int。"""
    if isinstance(d, str):
        s = d.replace('-', '').replace('/', '')
        if len(s) != 8 or not s.isdigit():
            raise TradeError('日期格式非法：%s，应为 8 位整数（如 20260907）' % d)
        return int(s)
    if isinstance(d, datetime.datetime):
        return int(d.strftime('%Y%m%d'))
    if isinstance(d, datetime.date):
        return int(d.strftime('%Y%m%d'))
    if isinstance(d, int):
        return d
    raise TradeError('无法解析日期：%r' % (d,))


def fmt_money(v):
    """金额格式化：None → '-'，否则千分位两位小数。"""
    if v is None:
        return '-'
    try:
        return '{:,.2f}'.format(float(v))
    except (TypeError, ValueError):
        return '-'


def fmt_num(v, nd=2):
    if v is None:
        return '-'
    try:
        return ('{:,.%df}' % nd).format(float(v))
    except (TypeError, ValueError):
        return '-'


def fmt_pct(v, nd=2):
    """比例格式化：None → '-'，否则加百分号。0.0523 → '5.23%'。"""
    if v is None:
        return '-'
    try:
        return '{:.{nd}f}%'.format(float(v) * 100, nd=nd)
    except (TypeError, ValueError):
        return '-'