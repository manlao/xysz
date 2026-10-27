# -*- coding: utf-8 -*-
"""星耀数智模拟交易（ad-sim-trade）

对接星耀数智模拟交易柜台：建组合、限价下单、撤单、查持仓/委托/成交/资金、组合收益与报告。

对外主入口：scripts/trade_cli.py
"""
import sys

# 禁止在 skill 目录内生成 __pycache__ —— 它是三级目录，会导致 WorkBuddy
# 校验时报「目录层级超限」。必须在导入本包之前设置（字节码写入发生在导入阶段）。
sys.dont_write_bytecode = True

__version__ = '1.0.0'
