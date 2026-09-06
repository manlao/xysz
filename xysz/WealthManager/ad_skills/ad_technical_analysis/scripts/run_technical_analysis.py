# -*- coding: utf-8 -*-
"""
A股技术面分析脚本

前置条件 - 设置环境变量:
    set AD_USERNAME=your_username
    set AD_PASSWORD=your_password
    set AD_HOST=server_ip
    set AD_PORT=8600

用法:
    python run_technical_analysis.py 60****.SH
    python run_technical_analysis.py 60****.SH --begin 20240101 --end 20260321
    python run_technical_analysis.py 60****.SH --indicator MACD
    python run_technical_analysis.py 60****.SH --category overbought

参数:
    code: 股票代码 (如 60****.SH, 00****.SZ)
    --begin: 开始日期 (默认: 20240101)
    --end: 结束日期 (默认: 今天)
    --indicator: 单个指标名称 (如 MACD, KDJ, RSI, BOLL 等)
    --category: 指标类别 (overbought/trend/energy/volume/ma/path/other)
"""

import sys
import os
import argparse
import json
from datetime import datetime

import AmazingData as ad
import pandas as pd
import numpy as np
from AmazingData.operator.math_function import MathFunction
from AmazingData.operator.statistics_function import StatisticsFunction
from AmazingData.operator.time_series_function import TimeSeriesFunction


# ================================================================
#  TechnicalIndicators 类（完全自包含）
# ================================================================

class TechnicalIndicators:
    """常用技术指标

    所有方法均为静态方法，输入为 pandas Series (OHLCV)，输出为 dict of Series。
    分类: 超买超卖型 / 趋势型 / 能量型 / 成交量型 / 均线型 / 路径型 / 其他型
    """

    # ================================================================
    #  一、超买超卖型
    # ================================================================

    @staticmethod
    def KDJ(close, high, low, n=9, m1=3, m2=3):
        """KDJ 随机指标
        RSV = (CLOSE - LLV(LOW, N)) / (HHV(HIGH, N) - LLV(LOW, N)) * 100
        K = SMA(RSV, M1, 1)
        D = SMA(K, M2, 1)
        J = 3 * K - 2 * D
        """
        llv = TimeSeriesFunction.LLV(low, n)
        hhv = TimeSeriesFunction.HHV(high, n)
        denom = hhv - llv
        denom = denom.replace(0, float('nan'))  # 防止除零
        rsv = (close - llv) / denom * 100
        k = TimeSeriesFunction.SMA(rsv, m1, 1)
        d = TimeSeriesFunction.SMA(k, m2, 1)
        j = 3 * k - 2 * d
        return {'K': k, 'D': d, 'J': j}

    @staticmethod
    def RSI(close, n1=6, n2=12, n3=24):
        """RSI 相对强弱指标
        LC = REF(CLOSE, 1)
        RSI = SMA(MAX(CLOSE-LC, 0), N, 1) / SMA(ABS(CLOSE-LC), N, 1) * 100
        """
        lc = TimeSeriesFunction.REF(close, 1)
        diff = close - lc
        zero = pd.Series(0.0, index=close.index)
        pos_diff = MathFunction.MAX(diff, zero)
        abs_diff = MathFunction.ABS(diff)
        return {
            f'RSI{n1}': TimeSeriesFunction.SMA(pos_diff, n1, 1) / TimeSeriesFunction.SMA(abs_diff, n1, 1) * 100,
            f'RSI{n2}': TimeSeriesFunction.SMA(pos_diff, n2, 1) / TimeSeriesFunction.SMA(abs_diff, n2, 1) * 100,
            f'RSI{n3}': TimeSeriesFunction.SMA(pos_diff, n3, 1) / TimeSeriesFunction.SMA(abs_diff, n3, 1) * 100,
        }

    @staticmethod
    def WR(close, high, low, n1=10, n2=6):
        """WR 威廉指标
        WR = (HHV(HIGH, N) - CLOSE) / (HHV(HIGH, N) - LLV(LOW, N)) * 100
        """
        result = {}
        for n in [n1, n2]:
            hhv = TimeSeriesFunction.HHV(high, n)
            llv = TimeSeriesFunction.LLV(low, n)
            denom = hhv - llv
            denom = denom.replace(0, float('nan'))  # 防止除零
            result[f'WR{n}'] = (hhv - close) / denom * 100
        return result

    @staticmethod
    def CCI(close, high, low, n=14):
            """CCI 顺势指标
            TYP = (HIGH + LOW + CLOSE) / 3
            CCI = (TYP - MA(TYP,N)) * 1000 / (15*AVEDEV (TYP,N))
            """
            typ = (high + low + close) / 3
            cci = (typ - TimeSeriesFunction.MA(typ, n)) * 1000 / (15 * StatisticsFunction.AVEDEV(typ, n))
            return {'CCI': cci}

    @staticmethod
    def ROC(close, n=12, m=6):
            """ROC 变动率指标
            NN = MIN(BARSCOUNT(C), N)
            ROC = (CLOSE - REF(CLOSE, NN)) / REF(CLOSE, NN) * 100
            MAROC = MA(ROC, M)
            """
            ref_close = TimeSeriesFunction.REF(close, n)
            roc = (close - ref_close) / ref_close * 100
            maroc = TimeSeriesFunction.MA(roc, m)
            return {'ROC': roc, 'MAROC': maroc}

    @staticmethod
    def MTM(close, n=12, m=6):
            """MTM 动量指标
            MTM = CLOSE - REF(CLOSE, MIN(BARSCOUNT(C),N))
            MAMTM = MA(MTM, M)
            """
            mtm = close - TimeSeriesFunction.REF(close, n)
            mamtm = TimeSeriesFunction.MA(mtm, m)
            return {'MTM': mtm, 'MAMTM': mamtm}

    @staticmethod
    def BIAS(close, n1=6, n2=12, n3=24):
        """BIAS 乖离率
        BIAS = (CLOSE - MA(CLOSE, N)) / MA(CLOSE, N) * 100
        """
        result = {}
        for n in [n1, n2, n3]:
            ma = TimeSeriesFunction.MA(close, n)
            result[f'BIAS{n}'] = (close - ma) / ma * 100
        return result

    @staticmethod
    def SKDJ(close, high, low, n=9, m=3):
            """SKDJ 慢速随机指标
            LOWV = LLV(LOW, N)
            HIGHV = HHV(HIGH, N)
            RSV = EMA((CLOSE-LOWV)/(HIGHV-LOWV)*100, M)
            K = EMA(RSV, M)
            D = MA(K, M)
            """
            lowv = TimeSeriesFunction.LLV(low, n)
            highv = TimeSeriesFunction.HHV(high, n)
            denom = highv - lowv
            denom = denom.replace(0, float('nan'))  # 防止除零
            rsv = TimeSeriesFunction.EMA((close - lowv) / denom * 100, m)
            k = TimeSeriesFunction.EMA(rsv, m)
            d = TimeSeriesFunction.MA(k, m)
            return {'K': k, 'D': d}

    @staticmethod
    def MFI(close, high, low, volume, n=14, n2=6):
            """MFI 资金流量指标
            TYP = (HIGH + LOW + CLOSE) / 3
            MR = TYP * VOL
            PMF = SUM(IF(TYP>REF(TYP,1), MR, 0), N)
            NMF = SUM(IF(TYP<REF(TYP,1), MR, 0), N)
            MFI = 100 - (100 / (1+ PMF/NMF))
            """
            typ = (high + low + close) / 3
            mr = typ * volume
            ref_typ = TimeSeriesFunction.REF(typ, 1)
            zero = pd.Series(0.0, index=close.index)
            pmf = TimeSeriesFunction.SUM(MathFunction.IF(typ > ref_typ, mr, zero), n)
            nmf = TimeSeriesFunction.SUM(MathFunction.IF(typ < ref_typ, mr, zero), n)
            # 处理除零和全流入/全流出情况
            denom = nmf.replace(0, np.nan)
            mfi = 100 - (100 / (1 + pmf / denom))
            # 只有在“确实没有负资金流”时，才可视情况设为 100
            mfi.loc[(pmf > 0) & (nmf == 0)] = 100
            # 完全无资金流动时设为 50
            mfi.loc[(pmf == 0) & (nmf == 0)] = 50
            return {'MFI': mfi}

    @staticmethod
    def OSC(close, n=20, m=6):
        """OSC 变动速率线
        OSC = (CLOSE - MA(CLOSE, N)) * 100
        MAOSC = EMA(OSC, M)
        """
        osc = (close - TimeSeriesFunction.MA(close, n)) * 100
        maosc = TimeSeriesFunction.EMA(osc, m)
        return {'OSC': osc, 'MAOSC': maosc}

    @staticmethod
    def UDL(close, n1=3, n2=5, n3=10, n4=20, m=6):
        """UDL 引力线
        UDL = (MA(CLOSE,N1)+MA(CLOSE,N2)+MA(CLOSE,N3)+MA(CLOSE,N4)) / 4
        MAUDL = MA(UDL, M)
        """
        udl = (TimeSeriesFunction.MA(close, n1) + TimeSeriesFunction.MA(close, n2) +
               TimeSeriesFunction.MA(close, n3) + TimeSeriesFunction.MA(close, n4)) / 4
        maudl = TimeSeriesFunction.MA(udl, m)
        return {'UDL': udl, 'MAUDL': maudl}

    @staticmethod
    def ACCER(close, n=8):
            """ACCER 幅度涨速
            ACCER = SLOPE(CLOSE,N)/CLOSE
            """
            # slope = StatisticsFunction.SLOPE(close, n)
            # accer = slope / close
            # return {'ACCER': accer}
            # ref_close = TimeSeriesFunction.REF(close, n)
            # accer = (close - ref_close) / ref_close / n * 100
            # return {'ACCER': accer}
            x = np.arange(n, dtype=float)

            def calc_slope(window):
                y = np.array(window, dtype=float)
                if len(y) < n or np.isnan(y).any():
                    return np.nan
            # 一次线性回归 y = a*x + b，返回斜率 a
                slope = np.polyfit(x, y, 1)[0]
                return slope

            slope_series = close.rolling(window=n, min_periods=n).apply(calc_slope, raw=False)
            accer = slope_series / close

            return {'ACCER': accer}

    @staticmethod
    def RCCD(close, n=59, short=26, long=52, m=26):
        """RCCD 异同离差乖离率
        RC = CLOSE / REF(CLOSE, N)
        ARC = SMA(REF(RC, 1), N, 1)
        DIF = MA(ARC, SHORT) - MA(ARC, LONG)
        RCCD = SMA(DIF, M, 1)
        """
        rc = close / TimeSeriesFunction.REF(close, n)
        arc = TimeSeriesFunction.SMA(TimeSeriesFunction.REF(rc, 1), n, 1)
        dif = TimeSeriesFunction.MA(arc, short) - TimeSeriesFunction.MA(arc, long)
        rccd = TimeSeriesFunction.SMA(dif, m, 1)
        return {'DIF': dif, 'RCCD': rccd}

    @staticmethod
    def MARSI(close, m1=10, m2=6):
            """MARSI 相对强弱平均线
            DIF = CLOSE-REF(CLOSE,1);
            VU = IF(DIF>=0,DIF,0);
            VD = IF(DIF<0,-DIF,0);
            MAU1 = MEMA(VU,M1);
            MAD1 = MEMA(VD,M1);
            MAU2 = MEMA(VU,M2);
            MAD2 = MEMA(VD,M2);
            RSI1 = MA(100*MAU1/(MAU1+MAD1),M1);
            RSI2 = MA(100*MAU2/(MAU2+MAD2),M2);
            """
            lc = TimeSeriesFunction.REF(close, 1)
            diff = close - lc
            #zero = pd.Series(0.0, index=close.index)
            # pos_diff = MathFunction.MAX(diff, zero)
            # abs_diff = MathFunction.ABS(diff)
            # rsi = TimeSeriesFunction.SMA(pos_diff, n, 1) / TimeSeriesFunction.SMA(abs_diff, n, 1) * 100
            # marsi = TimeSeriesFunction.MA(rsi, m)
            # return {'RSI': rsi, 'MARSI': marsi}
            zero = pd.Series(0.0, index=close.index)
            vu = MathFunction.IF(diff >= 0, diff, zero)
            vd = MathFunction.IF(diff < 0, -diff, zero)
            mau1 = TimeSeriesFunction.MEMA(vu, m1)
            mad1 = TimeSeriesFunction.MEMA(vd, m1)
            mau2 = TimeSeriesFunction.MEMA(vu, m2)
            mad2 = TimeSeriesFunction.MEMA(vd, m2)
            rsi1_raw = 100 * mau1 / (mau1 + mad1)
            rsi2_raw = 100 * mau2 / (mau2 + mad2)
            rsi1 = TimeSeriesFunction.MA(rsi1_raw, m1)
            rsi2 = TimeSeriesFunction.MA(rsi2_raw, m2)

            return {'RSI1': rsi1, 'RSI2': rsi2}

    # ================================================================
    #  二、趋势型
    # ================================================================

    @staticmethod
    def MACD(close, short=12, long=26, mid=9):
        """MACD 指数平滑异同移动平均线
        DIF = EMA(CLOSE, SHORT) - EMA(CLOSE, LONG)
        DEA = EMA(DIF, MID)
        MACD = 2 * (DIF - DEA)
        """
        dif = TimeSeriesFunction.EMA(close, short) - TimeSeriesFunction.EMA(close, long)
        dea = TimeSeriesFunction.EMA(dif, mid)
        macd = 2 * (dif - dea)
        return {'DIF': dif, 'DEA': dea, 'MACD': macd}

    @staticmethod
    def DMI(close, high, low, n=14, m=6):
            """DMI 趋向指标
            MTR = SUM(MAX(MAX(HIGH-LOW,ABS(HIGH-REF(CLOSE,1))),ABS(REF(CLOSE,1)-LOW)),N)
            HD = HIGH - REF(HIGH, 1)
            LD = REF(LOW, 1) - LOW
            DMP = SUM(IF(HD>0 AND HD>LD, HD, 0), N)
            DMM = SUM(IF(LD>0 AND LD>HD, LD, 0), N)
            PDI = DMP * 100 / MTR
            MDI = DMM * 100 / MTR
            ADX = MA(ABS(MDI-PDI)/(MDI+PDI)*100, M)
            ADXR = (ADX + REF(ADX, M)) / 2
            """
            ref_high = TimeSeriesFunction.REF(high, 1)
            ref_low = TimeSeriesFunction.REF(low, 1)
            ref_close = TimeSeriesFunction.REF(close, 1)
            zero = pd.Series(0.0, index=close.index)

            tr1 = high - low
            tr2 = MathFunction.ABS(high - ref_close)
            tr3 = MathFunction.ABS(ref_close - low)
            mtr_unit = MathFunction.MAX(MathFunction.MAX(tr1, tr2), tr3)
            mtr = TimeSeriesFunction.SUM(mtr_unit, n).replace(0, np.nan)

            hd = high - ref_high
            ld = ref_low - low

            dmp_raw = MathFunction.IF((hd > 0) & (hd > ld), hd, zero)
            dmm_raw = MathFunction.IF((ld > 0) & (ld > hd), ld, zero)

            dmp = TimeSeriesFunction.SUM(dmp_raw, n)
            dmm = TimeSeriesFunction.SUM(dmm_raw, n)

            pdi = dmp * 100 / mtr
            mdi = dmm * 100 / mtr

            denom = (mdi + pdi).replace(0, np.nan)
            dx = MathFunction.ABS(mdi - pdi) / denom * 100
            adx = TimeSeriesFunction.MA(dx, m)
            adxr = (adx + TimeSeriesFunction.REF(adx, m)) / 2
    

            return {'PDI': pdi, 'MDI': mdi, 'ADX': adx, 'ADXR': adxr}

    @staticmethod
    def DMA(close, n1=10, n2=50, m=10):
            """DMA 平行线差指标
            DIF = MA(CLOSE, N1) - MA(CLOSE, N2)
            DIFMA = MA(DIF, M)
            """
            dif = TimeSeriesFunction.MA(close, n1) - TimeSeriesFunction.MA(close, n2)
            difma = TimeSeriesFunction.MA(dif, m)
            return {'DIF': dif, 'AMA': difma}

    @staticmethod
    def TRIX(close, n=12, m=9):
            """TRIX 三重指数平滑移动平均
            MTR = EMA(EMA(EMA(CLOSE, N), N), N)
            TRIX = (MTR - REF(MTR, 1)) / REF(MTR, 1) * 100
            MATRIX = MA(TRIX, M)
            """
            mtr = TimeSeriesFunction.EMA(TimeSeriesFunction.EMA(TimeSeriesFunction.EMA(close, n), n), n)
            ref_mtr = TimeSeriesFunction.REF(mtr, 1)
            trix = (mtr - ref_mtr) / ref_mtr * 100
            matrix = TimeSeriesFunction.MA(trix, m)
            return {'TRIX': trix, 'MATRIX': matrix}

    @staticmethod
    def ARBR(close, open_, high, low, n=26):
            """ARBR 人气意愿指标 (BRAR)
            AR = SUM(HIGH - OPEN, N) / SUM(OPEN - LOW, N) * 100
            BR = SUM(MAX(0, HIGH-REF(CLOSE,1)), N) / SUM(MAX(0, REF(CLOSE,1)-LOW), N) * 100
            """
            ar = (TimeSeriesFunction.SUM(high - open_, n) /
                  TimeSeriesFunction.SUM(open_ - low, n) * 100)
            ref_close = TimeSeriesFunction.REF(close, 1)
            zero = close * 0
            br = (TimeSeriesFunction.SUM(MathFunction.MAX(high - ref_close, zero), n) /
                  TimeSeriesFunction.SUM(MathFunction.MAX(ref_close - low, zero), n) * 100)
            return {'AR': ar, 'BR': br}

    @staticmethod
    def EMV(close, high, low, volume, n=14, m=9):
            """EMV 简易波动指标
            VOLUME = MA(VOL, N) / VOL
            MID = 100 * (HIGH+LOW-REF(HIGH + low, 1)) / (HIGH+LOW)
            EMV = MA(MID*VOLUME*(HIGH-LOW)/MA(HIGH-LOW,N), N)
            MAEMV = MA(EMV, M)
            """
            vol_ratio = TimeSeriesFunction.MA(volume, n) / volume
            high_plus_low = high + low
            mid = 100 * (high + low - TimeSeriesFunction.REF(high_plus_low, 1)) / (high + low)
            hl = high - low
            emv = TimeSeriesFunction.MA(mid * vol_ratio * hl / TimeSeriesFunction.MA(hl, n), n)
            maemv = TimeSeriesFunction.MA(emv, m)
            return {'EMV': emv, 'MAEMV': maemv}

    @staticmethod
    def DPO(close, n=20, m=6):
        """DPO 区间震荡线
        DPO = CLOSE - REF(MA(CLOSE, N), N/2+1)
        MADPO = MA(DPO, M)
        """
        ma_close = TimeSeriesFunction.MA(close, n)
        dpo = close - TimeSeriesFunction.REF(ma_close, n // 2 + 1)
        madpo = TimeSeriesFunction.MA(dpo, m)
        return {'DPO': dpo, 'MADPO': madpo}

    @staticmethod
    def VHF(close, n=28):
        """VHF 十字过滤线
        HCP = HHV(CLOSE, N)
        LCP = LLV(CLOSE, N)
        VHF = (HCP - LCP) / SUM(ABS(CLOSE - REF(CLOSE, 1)), N)
        """
        hcp = TimeSeriesFunction.HHV(close, n)
        lcp = TimeSeriesFunction.LLV(close, n)
        denom = TimeSeriesFunction.SUM(MathFunction.ABS(close - TimeSeriesFunction.REF(close, 1)), n)
        denom = denom.replace(0, float('nan'))  # 防止除零
        vhf = (hcp - lcp) / denom
        return {'VHF': vhf}

    @staticmethod
    def CHO(close, high, low, volume, n1=10, n2=20, m=6):
            """CHO 佳庆指标
            MID = SUM(VOL*(2*CLOSE-HIGH-LOW)/(HIGH+LOW), 0)
            CHO = MA(MID, N1) - MA(MID, N2)
            MACHO = MA(CHO, M)
            """
            mid = TimeSeriesFunction.CUMSUM(volume * (2 * close - high - low) / (high + low))
            cho = (TimeSeriesFunction.MA(mid, n1) - TimeSeriesFunction.MA(mid, n2))/100
            macho = TimeSeriesFunction.MA(cho, m)
            return {'CHO': cho, 'MACHO': macho}

    @staticmethod
    def DBCD(close, n=5, m=16, t=76):
            """DBCD 异同离差乖离率
            BIAS = (CLOSE - MA(CLOSE, N)) / MA(CLOSE, N)
            DIF = BIAS - REF(BIAS, M)
            DBCD = SMA(DIF, T, 1)
            MM = MA(DBCD, 5)
            """
            ma = TimeSeriesFunction.MA(close, n)
            bias = (close - ma) / ma
            dif = bias - TimeSeriesFunction.REF(bias, m)
            dbcd = TimeSeriesFunction.SMA(dif, t, 1)
            mm = TimeSeriesFunction.MA(dbcd, 5)
            return {'DBCD': dbcd, 'MM': mm}

    @staticmethod
    def DDI(close, high, low, n=13, n1=26, m=1, m1=5):
            """DDI 方向标准离差指数
            TR = MAX(ABS(HIGH-REF(HIGH,1)), ABS(LOW-REF(LOW,1)))
            DMZ = IF((HIGH+LOW)<=(REF(HIGH,1)+REF(LOW,1)), 0,MAX(ABS(HIGH-REF(HIGH, 1)),ABS(LOW-REF(LOW, 1))))
            DMF = IF((HIGH+LOW)>=(REF(HIGH,1)+REF(LOW,1)), 0,MAX(ABS(HIGH-REF(HIGH, 1)),ABS(LOW-REF(LOW, 1))))
            DIZ = SUM(DMZ,N) / (SUM(DMZ,N)+SUM(DMF,N))
            DIF = SUM(DMF,N) / (SUM(DMF,N)+SUM(DMZ,N))
            DDI = DIZ - DIF
            ADDI = SMA(DDI, N1, M)
            ADl = MA(ADDI, M1)
            """
            ref_h = TimeSeriesFunction.REF(high, 1)
            ref_l = TimeSeriesFunction.REF(low, 1)
            zero = pd.Series(0.0, index=close.index)
            # TR = MAX(ABS(HIGH-REF(HIGH,1)), ABS(LOW-REF(LOW,1)))
            tr = MathFunction.MAX(
            MathFunction.ABS(high - ref_h),
            MathFunction.ABS(low - ref_l))

            # DMZ / DMF
            dmz = MathFunction.IF(high + low <= ref_h + ref_l, zero, tr)
            dmf = MathFunction.IF(high + low >= ref_h + ref_l, zero, tr)

            sum_dmz = TimeSeriesFunction.SUM(dmz, n)
            sum_dmf = TimeSeriesFunction.SUM(dmf, n)
            denom = (sum_dmz + sum_dmf).replace(0, np.nan)
            diz = sum_dmz / denom
            dif = sum_dmf / denom
            ddi = diz - dif
            addi = TimeSeriesFunction.SMA(ddi, n1, m)
            ad_line = TimeSeriesFunction.MA(addi, m1)

            return {'DDI': ddi, 'ADDI': addi, 'ADL': ad_line}

    @staticmethod
    def JS(close, n=5, m1=5, m2=10, m3=20):
            """JS 加速线
            JS = (CLOSE - REF(CLOSE, N)) / (N * REF(CLOSE, N)) * 100
            MAJ1 = MA(JS, M1); MAJ2 = MA(JS, M2); MAJ3 = MA(JS, M3)
            """
            ref_close = TimeSeriesFunction.REF(close, n)
            js = (close - ref_close) / (n * ref_close) * 100
            return {
                'JS': js,
                f'MAJ{m1}': TimeSeriesFunction.MA(js, m1),
                f'MAJ{m2}': TimeSeriesFunction.MA(js, m2),
                f'MAJ{m3}': TimeSeriesFunction.MA(js, m3),
            }

    @staticmethod
    def QACD(close, n1=12, n2=26, m=9):
            """QACD 快速异同移动平均
            DIF = EMA(CLOSE, N1) - EMA(CLOSE, N2)
            MACD = EMA(DIF, M)
            QACD = DIF - MACD
            """
            dif = TimeSeriesFunction.EMA(close, n1) - TimeSeriesFunction.EMA(close, n2)
            macd = TimeSeriesFunction.EMA(dif, m)
            ddif = dif - macd
            return {'DIF': dif, 'MACD': macd, 'DDIF': ddif}

    @staticmethod
    def UOS(close, high, low, n1=7, n2=14, n3=28, m=6):
            """UOS 终极波动指标
            TH = MAX(HIGH, REF(CLOSE,1)); TL = MIN(LOW, REF(CLOSE,1))
            ACC1 = SUM(CLOSE-TL,N1)/SUM(TH-TL,N1)
            ACC2 = SUM(CLOSE-TL,N2)/SUM(TH-TL,N2)
            ACC3 = SUM(CLOSE-TL,N3)/SUM(TH-TL,N3)
            UOS = (ACC1*N2*N3+ACC2*N1*N3+ACC3*N1*N2)*100/(N1*N2+N1*N3+N2*N3)
            MAUOS = EXPMA(UOS, M)
            """
            ref_c = TimeSeriesFunction.REF(close, 1)
            th = MathFunction.MAX(high, ref_c)
            tl = MathFunction.MIN(low, ref_c)
            acc1 = TimeSeriesFunction.SUM(close - tl, n1) / TimeSeriesFunction.SUM(th - tl, n1)
            acc2 = TimeSeriesFunction.SUM(close - tl, n2) / TimeSeriesFunction.SUM(th - tl, n2)
            acc3 = TimeSeriesFunction.SUM(close - tl, n3) / TimeSeriesFunction.SUM(th - tl, n3)
            uos = (acc1 * n2 * n3 + acc2 * n1 * n3 + acc3 * n1 * n2)  * 100 / (n1 * n2 + n1 * n3 + n2 * n3)
            mauos = TimeSeriesFunction.EMA(uos, m)
            return {'UOS': uos, 'MAUOS': mauos}

    # ================================================================
    #  三、能量型
    # ================================================================

    @staticmethod
    def CR(close, high, low, n=26, m1 = 10, m2 = 20, m3 = 40, m4 = 62):
            """CR 能量指标
            MID = REF(HIGH + LOW, 1)/2
            CR = SUM(MAX(0, HIGH-MID), N) / SUM(MAX(0, MID-LOW), N) * 100
            MA1:REF(MA(CR,M1),M1/2.5+1);
            MA2:REF(MA(CR,M2),M2/2.5+1);
            MA3:REF(MA(CR,M3),M3/2.5+1);
            MA4:REF(MA(CR,M4),M4/2.5+1);
            """
            mid = TimeSeriesFunction.REF(high + low,1)/2
            zero = close * 0
            up = MathFunction.MAX(high-mid, zero)
            down = MathFunction.MAX(mid-low, zero)
            down_sum = TimeSeriesFunction.SUM(down, n).replace(0, np.nan)
            cr = TimeSeriesFunction.SUM(up, n)/down_sum * 100
            ma1 = TimeSeriesFunction.REF(TimeSeriesFunction.MA(cr, m1), int(m1/2.5+1))
            ma2 = TimeSeriesFunction.REF(TimeSeriesFunction.MA(cr, m2), int(m2/2.5+1))
            ma3 = TimeSeriesFunction.REF(TimeSeriesFunction.MA(cr, m3), int(m3/2.5+1))
            ma4 = TimeSeriesFunction.REF(TimeSeriesFunction.MA(cr, m4), int(m4/2.5+1))
            return {'CR': cr,
                    f'MA{m1}': ma1,
                    f'MA{m2}': ma2,
                    f'MA{m3}': ma3,
                    f'MA{m4}': ma4}

    @staticmethod
    def PSY(close, n=12, m=6):
            """PSY 心理线
            PSY = COUNT(CLOSE > REF(CLOSE, 1), N) / N * 100
            MAPSY = MA(PSY, M)
            """
            cond = close > TimeSeriesFunction.REF(close, 1)
            psy = TimeSeriesFunction.COUNT(cond, n) / n * 100
            mapsy = TimeSeriesFunction.MA(psy, m)
            return {'PSY': psy, 'PSYMA': mapsy}

    @staticmethod
    def MASS(high, low, n1=9, n2=25, m=6):
            """MASS 梅斯线
            MASS = SUM(MA(HIGH-LOW, N1) / MA(MA(HIGH-LOW, N1), N1), N2)
            MAMASS = MA(MASS, M)
            """
            hl_ema = TimeSeriesFunction.MA(high - low, n1)
            mass = TimeSeriesFunction.SUM(hl_ema / TimeSeriesFunction.MA(hl_ema, n1), n2)
            mamass = TimeSeriesFunction.MA(mass, m)
            return {'MASS': mass, 'MAMASS': mamass}

    @staticmethod
    def PCNT(close, m = 5):
            """PCNT 幅度比
            PCNT = (CLOSE - REF(CLOSE, 1)) / CLOSE * 100
            MAPCNT = EXPMEMA(PCNT,M)

            """
            ref_close = TimeSeriesFunction.REF(close, 1)
            pcnt = (close - ref_close) / close * 100
            mapcnt = TimeSeriesFunction.EXPMEMA(pcnt, m)
            return {'PCNT': pcnt, 'MAPCNT': mapcnt}

    @staticmethod
    def WAD(close, high, low, m = 30):
            """WAD 威廉多空力度线
            MIDA = CLOSE - MIN(LOW, REF(CLOSE, 1))  (当CLOSE>REF(CLOSE,1))
            MIDB = IF(CLOSE<REF(CLOSE,1),CLOSE-MAX(REF(CLOSE,1),HIGH),0) (当CLOSE<REF(CLOSE,1))
            WAD = SUM(IF(CLOSE>REF(CLOSE,1),MIDA,MIDB),0)
            MAWAD:MA(WAD,M)
            """
            ref_c = TimeSeriesFunction.REF(close, 1)
            mida = close - MathFunction.MIN(low, ref_c)
            midb = MathFunction.IF(close < ref_c, close - MathFunction.MAX(ref_c, high), 0)
            wad = TimeSeriesFunction.SUM(MathFunction.IF(close > ref_c, mida, midb), 0)
            mawad = TimeSeriesFunction.MA(wad, m)
            return {'WAD': wad, 'MAWAD': mawad}

    # ================================================================
    #  四、成交量型
    # ================================================================

    @staticmethod
    def OBV(close, volume, m=30):
            """OBV 能量潮
            若当日收盘价 > 昨日收盘价，OBV = 前日OBV + 今日成交量
            若当日收盘价 < 昨日收盘价，OBV = 前日OBV - 今日成交量
            若当日收盘价 = 昨日收盘价，OBV = 前日OBV
            VA:=IF(CLOSE>REF(CLOSE,1),VOL,-VOL);
            OBV:SUM(IF(CLOSE=REF(CLOSE,1),0,VA),0);
            MAOBV:MA(OBV,M)
            """
            ref_close = TimeSeriesFunction.REF(close, 1)
            direction = MathFunction.SIGN(close - ref_close).fillna(0)  # 首日设为0，避免NaN累积
            obv = TimeSeriesFunction.CUMSUM(direction * volume)
            # 首日OBV等于首日成交量（标准做法）
            if len(obv) > 0 and len(volume) > 0:
                obv.iloc[0] = volume.iloc[0]
            # va = MathFunction.IF(close > ref_close, volume, -volume)
            # obv = TimeSeriesFunction.SUM(MathFunction.IF(close == ref_close, 0, va), 0)
            maobv = TimeSeriesFunction.MA(obv, m)
            return {'OBV': obv, 'MAOBV': maobv}

    @staticmethod
    def VR(close, volume, n=26, m=6):
            """VR 成交量变异率
            AV = SUM(IF(CLOSE>REF(CLOSE,1), VOLUME, 0), N)
            BV = SUM(IF(CLOSE<REF(CLOSE,1), VOLUME, 0), N)
            CV = SUM(IF(CLOSE=REF(CLOSE,1), VOLUME, 0), N)
            VR = (AV + CV/2) / (BV + CV/2) * 100
            MAVR = MA(vr, m)
            """
            ref_close = TimeSeriesFunction.REF(close, 1)
            zero = pd.Series(0.0, index=close.index)
            av = TimeSeriesFunction.SUM(MathFunction.IF(close > ref_close, volume, zero), n)
            bv = TimeSeriesFunction.SUM(MathFunction.IF(close < ref_close, volume, zero), n)
            cv = TimeSeriesFunction.SUM(MathFunction.IF(close == ref_close, volume, zero), n)
            vr = (av + cv / 2) / (bv + cv / 2) * 100
            mavr = TimeSeriesFunction.MA(vr, m)
            return {'VR': vr, 'MAVR': mavr}

    @staticmethod
    def VOLMA(volume, n1=5, n2=10):
        """VOLMA 成交量均线"""
        return {
            f'VOLMA{n1}': TimeSeriesFunction.MA(volume, n1),
            f'VOLMA{n2}': TimeSeriesFunction.MA(volume, n2),
        }

    @staticmethod
    def WVAD(close, open, high, low, volume, n=24, m=6):
            """WVAD 威廉变异离散量
            WVAD = SUM((CLOSE-OPEN)/(HIGH-LOW)*VOL, N)/10000
            MAWVAD = MA(WVAD, M)
            """
            wvad = TimeSeriesFunction.SUM((close - open) / (high - low) * volume, n)/10000
            mawvad = TimeSeriesFunction.MA(wvad, m)
            return {'WVAD': wvad, 'MAWVAD': mawvad}

    @staticmethod
    def VOSC(volume, short=12, long=26):
            """VOSC 成交量震荡
            VOSC = (MA(VOL, SHORT) - MA(VOL, LONG)) / MA(VOL, SHORT) * 100
            """
            ma_short = TimeSeriesFunction.MA(volume, short)
            ma_long = TimeSeriesFunction.MA(volume, long)
            vosc = (ma_short - ma_long) / ma_short * 100
            return {'VOSC': vosc}

    @staticmethod
    def VRSI(volume, n1=6, n2=12, n3=24):
        """VRSI 量相对强弱
        LV = REF(VOL, 1)
        VRSI = SMA(MAX(VOL-LV, 0), N, 1) / SMA(ABS(VOL-LV), N, 1) * 100
        """
        lv = TimeSeriesFunction.REF(volume, 1)
        diff = volume - lv
        zero = pd.Series(0.0, index=volume.index)
        pos_diff = MathFunction.MAX(diff, zero)
        abs_diff = MathFunction.ABS(diff)
        result = {}
        for n in [n1, n2, n3]:
            result[f'VRSI{n}'] = TimeSeriesFunction.SMA(pos_diff, n, 1) / TimeSeriesFunction.SMA(abs_diff, n, 1) * 100
        return result

    @staticmethod
    def VSTD(volume, n=10):
            """VSTD 成交量标准差
            VSTD = STD(VOL, N)
            """
            vstd = StatisticsFunction.STD(volume, n)
            return {'VSTD': vstd}

    @staticmethod
    def AMO(amount, n1=5, n2=10):
            """AMO 成交额均线
            AMOW = MA(AMOUNT/10000, N)
            """
            return {
                'AMOW': amount/10000,
                f'AMO{n1}': TimeSeriesFunction.MA(amount/10000, n1),
                f'AMO{n2}': TimeSeriesFunction.MA(amount/10000, n2),
            }


    @staticmethod
    def TAPI(close, amount, n=6):
            """TAPI 加权指数成交值
            TAPI = AMOUNT / CLOSE
            MATAPI = MA(TAPI, N)
            """
            tapi = amount / close
            matapi = TimeSeriesFunction.MA(tapi, n)
            return {'TAPI': tapi, 'MATAPI': matapi}

    # ================================================================
    #  五、均线型
    # ================================================================

    @staticmethod
    def MA(close, m1=5, m2=10, m3=20, m4=60, m5=0, m6=0, m7=0, m8=0):
            """MA 移动平均线"""
            return {
                f'MA{m1}': TimeSeriesFunction.MA(close, m1),
                f'MA{m2}': TimeSeriesFunction.MA(close, m2),
                f'MA{m3}': TimeSeriesFunction.MA(close, m3),
                f'MA{m4}': TimeSeriesFunction.MA(close, m4),
                f'MA{m5}': TimeSeriesFunction.MA(close, m5),
                f'MA{m6}': TimeSeriesFunction.MA(close, m6),
                f'MA{m7}': TimeSeriesFunction.MA(close, m7),
                f'MA{m8}': TimeSeriesFunction.MA(close, m8),
            }

    @staticmethod
    def EXPMA(close, n1=12, n2=50):
        """EXPMA 指数平均线"""
        return {
            f'EXPMA{n1}': TimeSeriesFunction.EMA(close, n1),
            f'EXPMA{n2}': TimeSeriesFunction.EMA(close, n2),
        }

    @staticmethod
    def BBI(close, m1=3, m2=6, m3=12, m4=24):
            """BBI 多空指标
            BBI = (MA(CLOSE,m1) + MA(CLOSE,m2) + MA(CLOSE,m3) + MA(CLOSE,m4)) / 4
            """
            bbi = (TimeSeriesFunction.MA(close, m1) + TimeSeriesFunction.MA(close, m2) +
                   TimeSeriesFunction.MA(close, m3) + TimeSeriesFunction.MA(close, m4)) / 4
            return {'BBI': bbi}

    @staticmethod
    def AMV(volume, amount, n1=5, n2=13, n3=34, n4=60):
            """AMV 成本价均线
            AMOV = VOL*(OPEN+CLOSE)/2
            AMV = SUM(AMOV, N) / SUM(VOL, N)
            #此处用 AMOUNT 近似 AMOV (成交额 ≈ 成交量*均价)，按成交量加权平均
            """
            return {
                f'AMV{n1}': TimeSeriesFunction.SUM(amount, n1) / TimeSeriesFunction.SUM(volume, n1),
                f'AMV{n2}': TimeSeriesFunction.SUM(amount, n2) / TimeSeriesFunction.SUM(volume, n2),
                f'AMV{n3}': TimeSeriesFunction.SUM(amount, n3) / TimeSeriesFunction.SUM(volume, n3),
                f'AMV{n4}': TimeSeriesFunction.SUM(amount, n4) / TimeSeriesFunction.SUM(volume, n4)
            }

    # ================================================================
    #  六、路径型
    # ================================================================

    @staticmethod
    def BOLL(close, n=20, k=2):
            """BOLL 布林线
            MID = MA(CLOSE, N)
            VART1= POW((CLOSE - MID)
            VART2 = MA(VART1, N)
            VART3 = SQRT(VART2)
            UPPER=MID + K * VART3
            LOWER=MID - K * VART3
            BOLL = REF(MID, 1)
            UB = REF(UPPER, 1)
            LB=REF(LOWER, 1)
            """
            mid = TimeSeriesFunction.MA(close, n)
            #std = StatisticsFunction.STD(close, n)
            vart1 = MathFunction.POW((close- mid), 2)
            vart2 = TimeSeriesFunction.MA(vart1, n)
            vart3= MathFunction.SQRT(vart2)
            upper = mid + k * vart3
            lower = mid - k * vart3
            boll = TimeSeriesFunction.REF(mid, 1)
            ub = TimeSeriesFunction.REF(upper, 1)
            lb = TimeSeriesFunction.REF(lower, 1)
            return {'BOLL': boll, 'UB': ub, 'LB': lb}

    @staticmethod
    def ENE(close, n=25, m1=6, m2=6):
            """ENE 轨道线
            UPPER = MA(CLOSE, N) * (1 + M1/100)
            LOWER = MA(CLOSE, N) * (1 - M2/100)
            ENE = (UPPER + LOWER) / 2
            """
            ma = TimeSeriesFunction.MA(close, n)
            upper = ma * (1 + m1 / 100)
            lower = ma * (1 - m2 / 100)
            ene = (upper + lower) / 2
            return {'UPPER': upper, 'ENE': ene, 'LOWER': lower}

    @staticmethod
    def MIKE(close, high, low, n=10):
            """MIKE 麦克指标
            HLC = REF(MA((HIGH+LOW+CLOSE)/3,N),1);
            HV = EMA(HHV(HIGH,N),3);
            LV = EMA(LLV(LOW,N),3);
            STOR = EMA(2*HV-LV,3);
            MIDR = EMA(HLC+HV-LV,3);
            WEKR = EMA(HLC*2-LV,3);
            WEKS = EMA(HLC*2-HV,3);
            MIDS = EMA(HLC-HV+LV,3);
            STOS = EMA(2*LV-HV,3);
            """
            hlc = TimeSeriesFunction.REF(TimeSeriesFunction.MA((high + low + close) / 3, n), 1)
            hv = TimeSeriesFunction.EMA(TimeSeriesFunction.HHV(high, n),3)
            lv = TimeSeriesFunction.EMA(TimeSeriesFunction.LLV(low, n), 3)
            wr = TimeSeriesFunction.EMA(hlc * 2 - lv, 3)
            mr = TimeSeriesFunction.EMA(hlc + hv - lv, 3)
            sr = TimeSeriesFunction.EMA(2 * hv - lv, 3)
            ws = TimeSeriesFunction.EMA(hlc *2 -hv, 3)
            ms = TimeSeriesFunction.EMA(hlc - hv + lv, 3)
            ss = TimeSeriesFunction.EMA(2 * lv - hv, 3)
            return {'WEKR': wr, 'MIDR': mr, 'STOR': sr, 'WEKS': ws, 'MIDS': ms, 'STOS': ss}

    @staticmethod
    def PBX(close, m1=4, m2=6, m3=9, m4=13, m5=18, m6=24):
            """PBX 瀑布线
            PBX = (EMA(CLOSE, M1) + EMA(CLOSE, 2*M1) + EMA(CLOSE, 4*M1)) / 3
            多条瀑布线
            """
            return {
                f'PBX{m1}': (TimeSeriesFunction.EMA(close, m1) + TimeSeriesFunction.EMA(close, m1 * 2) + TimeSeriesFunction.EMA(close, m1 * 4)) / 3,
                f'PBX{m2}': (TimeSeriesFunction.EMA(close, m2) + TimeSeriesFunction.EMA(close, m2 * 2) + TimeSeriesFunction.EMA(close, m2 * 4)) / 3,
                f'PBX{m3}': (TimeSeriesFunction.EMA(close, m3) + TimeSeriesFunction.EMA(close, m3 * 2) + TimeSeriesFunction.EMA(close, m3 * 4)) / 3,
                f'PBX{m4}': (TimeSeriesFunction.EMA(close, m4) + TimeSeriesFunction.EMA(close, m4 * 2) + TimeSeriesFunction.EMA(close, m4 * 4)) / 3,
                f'PBX{m5}': (TimeSeriesFunction.EMA(close, m5) + TimeSeriesFunction.EMA(close, m5 * 2) + TimeSeriesFunction.EMA(close, m5 * 4)) / 3,
                f'PBX{m6}': (TimeSeriesFunction.EMA(close, m6) + TimeSeriesFunction.EMA(close, m6 * 2) + TimeSeriesFunction.EMA(close, m6 * 4)) / 3,
            }

    @staticmethod
    def XS(close, high, low, n=13):
            """XS 薛斯通道
            SMA_C = SMA(CLOSE, N, 1)
            SMA_H = SMA(HIGH, N, 1)
            SMA_L = SMA(LOW, N, 1)
            UPP = SMA_H * 1.06
            SUP = SMA_C * 1.06
            SDN = SMA_C * 0.94
            LWN = SMA_L * 0.94
            通信达公式如下 --------已修复-------
            VAR2:=CLOSE*VOL;
            VAR3:=EMA((EMA(VAR2,3)/EMA(VOL,3)+EMA(VAR2,6)/EMA(VOL,6)+EMA(VAR2,12)/EMA(VOL,12)+EMA(VAR2,24)/EMA(VOL,24))/4,N);
            SUP:1.06*VAR3;
            SDN:VAR3*0.94;
            VAR4:=EMA(CLOSE,9);
            LUP:EMA(VAR4*1.14,5);
            LDN:EMA(VAR4*0.86,5);
            """
            # sma_c = TimeSeriesFunction.SMA(close, n, 1)
            # sma_h = TimeSeriesFunction.SMA(high, n, 1)
            # sma_l = TimeSeriesFunction.SMA(low, n, 1)
            # upp = sma_h * 1.06
            # sup = sma_c * 1.06
            # sdn = sma_c * 0.94
            # lwn = sma_l * 0.94
            var2 = close * volume
            # part1 = EMA(VAR2,3)/EMA(VOL,3)
            p1 = TimeSeriesFunction.EMA(var2, 3)/TimeSeriesFunction.EMA(volume, 3)
            # part2 = EMA(VAR2,6)/EMA(VOL,6)
            p2 = TimeSeriesFunction.EMA(var2, 6)/TimeSeriesFunction.EMA(volume, 6)
            # part3 = EMA(VAR2,12)/EMA(VOL,12)
            p3 = TimeSeriesFunction.EMA(var2, 12)/TimeSeriesFunction.EMA(volume, 12)
            # part4 = EMA(VAR2,24)/EMA(VOL,24)
            p4 = TimeSeriesFunction.EMA(var2, 24)/TimeSeriesFunction.EMA(volume, 24)
            var3 = TimeSeriesFunction.EMA((p1 + p2 + p3 + p4)/4, n)
            sup = 1.06 * var3
            sdn = var3 * 0.94
            var4 = TimeSeriesFunction.EMA(close, 9)
            lup = TimeSeriesFunction.EMA(var4 * 1.14, 5)
            ldn = TimeSeriesFunction.EMA(var4 * 0.86, 5)
            return {'SUP': sup, 'SDN': sdn, 'LUP': lup, 'LDN': ldn}

    @staticmethod
    def BBIBOLL(close, n=11, m=6):
            """BBIBOLL BBI多空布林线
            BBI = (MA(CLOSE,3)+MA(CLOSE,6)+MA(CLOSE,12)+MA(CLOSE,24))/4
            UPPER = BBI + M * STD(BBI, N)
            LOWER = BBI - M * STD(BBI, N)
            """
            bbi = (TimeSeriesFunction.MA(close, 3) + TimeSeriesFunction.MA(close, 6) +
                   TimeSeriesFunction.MA(close, 12) + TimeSeriesFunction.MA(close, 24)) / 4
            std = StatisticsFunction.STD(bbi, n)
            upper = bbi + m * std
            lower = bbi - m * std
            return {'BBIBOLL': bbi, 'UPPER': upper, 'LOWER': lower}

    # ================================================================
    #  七、其他型
    # ================================================================

    @staticmethod
    def ASI(close, open_, high, low, m1=26, m2=10):
            """ASI 振动升降指标
            A = ABS(HIGH - REF(CLOSE, 1))
            B = ABS(LOW - REF(CLOSE, 1))
            C = ABS(HIGH - REF(LOW, 1))
            D = ABS(REF(CLOSE, 1) - REF(OPEN, 1))
            R = 根据A/B/C大小关系取不同值
            SI = 16 * (CLOSE-REF(CLOSE,1) + (CLOSE-OPEN)/2 + (REF(CLOSE,1)-REF(OPEN,1))/4) / R * MAX(A,B)
            ASI = SUM(SI, 0)  即累计
            LC=REF(CLOSE,1);
            AA=ABS(HIGH-LC);
            BB=ABS(LOW-LC);
            CC=ABS(HIGH-REF(LOW,1));
            DD=ABS(LC-REF(OPEN,1));
            R=IF(AA>BB AND AA>CC,AA+BB/2+DD/4,IF(BB>CC AND BB>AA,BB+AA/2+DD/4,CC+DD/4));
            X=(CLOSE-LC+(CLOSE-OPEN)/2+LC-REF(OPEN,1));
            SI=16*X/R*MAX(AA,BB);
            ASI:SUM(SI,M1);
            ASIT:MA(ASI,M2);
            """
            ref_c = TimeSeriesFunction.REF(close, 1)
            ref_o = TimeSeriesFunction.REF(open_, 1)
            ref_l = TimeSeriesFunction.REF(low, 1)

            aa = MathFunction.ABS(high - ref_c)
            bb = MathFunction.ABS(low - ref_c)
            cc = MathFunction.ABS(high - ref_l)
            dd = MathFunction.ABS(ref_c - ref_o)

            r_a = aa + bb / 2 + dd / 4
            r_b = bb + aa / 2 + dd / 4
            r_c = cc + dd / 4

            r = MathFunction.IF((aa > bb) & (aa > cc), r_a, MathFunction.IF((bb > cc) & (bb > aa), r_b, r_c))
            r = r.replace(0, np.nan)

            x = (close - ref_c + (close - open_) / 2 + ref_c - ref_o)
            si = 16 * x / r * MathFunction.MAX(aa, bb)
            asi = TimeSeriesFunction.SUM(si, m1)
            asit = TimeSeriesFunction.MA(asi, m2)
            return {'SI': si, 'ASI': asi}

    @staticmethod
    def ATR(close, high, low, n=14):
            """ATR 真实波幅均值
            MTR:MAX(MAX((HIGH-LOW),ABS(REF(CLOSE,1)-HIGH)),ABS(REF(CLOSE,1)-LOW));
            ATR = MA(MTR, N)
            """
            mtr = MathFunction.MAX(MathFunction.MAX((high - low), MathFunction.ABS(TimeSeriesFunction.REF(close, 1)- high)), 
                                         MathFunction.ABS(TimeSeriesFunction.REF(close, 1)- low))
            atr = TimeSeriesFunction.MA(mtr, n)
            return {'MTR': mtr, 'ATR': atr}

    @staticmethod
    def SAR(close, high, low, n=4, step=0.02, max_af=0.2):
            """SAR 抛物线转向指标
            初始方向根据前N日趋势判定，加速因子从step开始，每创新高/低增加step，最大max_af
            """
            sar = TimeSeriesFunction.SAR(high, low, close, n, step, max_af)
            return {'SAR': sar}

    @staticmethod
    def CDP(close, high, low):
            """CDP 逆势操作
            CH:=REF(H,1);
            CL:=REF(L,1);
            CC:=REF(C,1);
            CDP:(CH+CL+CC)/3;
            AH:2*CDP+CH-2*CL;
            NH:CDP+CDP-CL;
            NL:CDP+CDP-CH;
            AL:2*CDP-2*CH+CL;
            """
            ref_h = TimeSeriesFunction.REF(high, 1)
            ref_l = TimeSeriesFunction.REF(low, 1)
            ref_c = TimeSeriesFunction.REF(close, 1)
            cdp = (ref_h + ref_l +  ref_c) / 3
            ah = 2 * cdp + ref_h - 2 * ref_l
            nh = 2 * cdp - ref_l
            nl = 2 * cdp - ref_h
            al = 2 * cdp - 2 * ref_h + ref_l
            return {'AH': ah, 'NH': nh, 'CDP': cdp, 'NL': nl, 'AL': al}


# ================================================================
#  工具函数
# ================================================================

def is_stock(code):
    """判断代码是否为股票
    规则: 数字部分为6位，SH市场首位必须是6，SZ市场首位必须是0或3
    """
    parts = code.split('.')
    pure_code, market = parts[0], parts[1].upper()
    if len(pure_code) != 6 or not pure_code.isdigit():
        return False
    if market == 'SH' and pure_code[0] == '6':
        return True
    if market == 'SZ' and pure_code[0] in ('0', '3'):
        return True
    return False


def forward_adjust(df, backward_factor, code):
    """对单只股票的kline DataFrame做前复权（只调整OHLC价格）"""
    df_adj = df.copy()

    if code not in backward_factor.columns:
        print(f"警告: 未找到 {code} 的复权因子，跳过前复权", file=sys.stderr)
        return df_adj

    factor = backward_factor[code]

    if 'kline_time' in df_adj.columns:
        kline_dates = pd.to_datetime(df_adj['kline_time'])
    else:
        kline_dates = pd.to_datetime(df_adj.index)

    factor_aligned = factor.reindex(kline_dates, method='ffill')
    factor_aligned = factor_aligned.values

    latest_factor = factor_aligned[~pd.isna(factor_aligned)][-1]

    adj_ratio = factor_aligned / latest_factor
    for col in ['open', 'high', 'low', 'close']:
        if col in df_adj.columns:
            df_adj[col] = df_adj[col] * adj_ratio

    return df_adj



def run_analysis(code, begin_date, end_date, indicator=None, category=None):
    """运行技术面分析"""

    # 从环境变量读取登录信息
    username = os.environ.get('AD_USERNAME')
    password = os.environ.get('AD_PASSWORD')
    host = os.environ.get('AD_HOST')
    port = os.environ.get('AD_PORT')

    if not all([username, password, host, port]):
        missing = []
        if not username: missing.append('AD_USERNAME')
        if not password: missing.append('AD_PASSWORD')
        if not host: missing.append('AD_HOST')
        if not port: missing.append('AD_PORT')
        print(json.dumps({"error": f"缺少环境变量: {', '.join(missing)}。请先设置: set AD_USERNAME=xxx & set AD_PASSWORD=xxx & set AD_HOST=xxx & set AD_PORT=xxx"}, ensure_ascii=False))
        return

    # 登录
    ad.login(
        username=username,
        password=password,
        host=host,
        port=int(port)
    )

    # 获取数据
    base_data = ad.BaseData()
    calendar = base_data.get_calendar()
    market_data = ad.MarketData(calendar)

    print(f"正在获取 {code} 的K线数据 ({begin_date}-{end_date})...", file=sys.stderr)
    kline_dict = market_data.query_kline(
        [code],
        begin_date=begin_date,
        end_date=end_date,
        period=ad.constant.Period.day.value
    )

    if code not in kline_dict or kline_dict[code] is None or len(kline_dict[code]) == 0:
        print(json.dumps({"error": f"未获取到 {code} 的K线数据"}, ensure_ascii=False))
        return

    df = kline_dict[code]

    # 前复权处理
    if is_stock(code):
        print(f"正在进行前复权处理...", file=sys.stderr)
        backward_factor = base_data.get_backward_factor([code], is_local=False)
        df = forward_adjust(df, backward_factor, code)

    close = df['close']
    open_ = df['open']
    high = df['high']
    low = df['low']
    volume = df['volume']
    amount = df['amount'] if 'amount' in df.columns else close * volume

    TI = TechnicalIndicators

    # 最新价格信息
    last_date = str(df['kline_time'].iloc[-1]) if 'kline_time' in df.columns else "N/A"
    price_info = {
        "open": round(float(open_.iloc[-1]), 2),
        "high": round(float(high.iloc[-1]), 2),
        "low": round(float(low.iloc[-1]), 2),
        "close": round(float(close.iloc[-1]), 2),
        "volume": int(volume.iloc[-1]),
        "amount": round(float(amount.iloc[-1]), 2),
    }

    # 定义所有指标计算（只计算，不判断信号）
    overbought_indicators = [
        ("KDJ", lambda: TI.KDJ(close, high, low)),
        ("RSI", lambda: TI.RSI(close)),
        ("WR", lambda: TI.WR(close, high, low)),
        ("CCI", lambda: TI.CCI(close, high, low)),
        ("ROC", lambda: TI.ROC(close)),
        ("MTM", lambda: TI.MTM(close)),
        ("BIAS", lambda: TI.BIAS(close)),
        ("SKDJ", lambda: TI.SKDJ(close, high, low)),
        ("MFI", lambda: TI.MFI(close, high, low, volume)),
        ("OSC", lambda: TI.OSC(close)),
        ("UDL", lambda: TI.UDL(close)),
        ("ACCER", lambda: TI.ACCER(close)),
        ("RCCD", lambda: TI.RCCD(close)),
        ("MARSI", lambda: TI.MARSI(close)),
    ]

    trend_indicators = [
        ("MACD", lambda: TI.MACD(close)),
        ("DMI", lambda: TI.DMI(close, high, low)),
        ("DMA", lambda: TI.DMA(close)),
        ("TRIX", lambda: TI.TRIX(close)),
        ("ARBR", lambda: TI.ARBR(close, open_, high, low)),
        ("EMV", lambda: TI.EMV(close, high, low, volume)),
        ("DPO", lambda: TI.DPO(close)),
        ("VHF", lambda: TI.VHF(close)),
        ("CHO", lambda: TI.CHO(close, high, low, volume)),
        ("DBCD", lambda: TI.DBCD(close)),
        ("DDI", lambda: TI.DDI(close, high, low)),
        ("JS", lambda: TI.JS(close)),
        ("QACD", lambda: TI.QACD(close)),
        ("UOS", lambda: TI.UOS(close, high, low)),
    ]

    energy_indicators = [
        ("CR", lambda: TI.CR(close, high, low)),
        ("PSY", lambda: TI.PSY(close)),
        ("MASS", lambda: TI.MASS(high, low)),
        ("PCNT", lambda: TI.PCNT(close)),
        ("WAD", lambda: TI.WAD(close, high, low)),
    ]

    volume_indicators = [
        ("OBV", lambda: TI.OBV(close, volume)),
        ("VR", lambda: TI.VR(close, volume)),
        ("VOLMA", lambda: TI.VOLMA(volume)),
        ("WVAD", lambda: TI.WVAD(close, open_, high, low, volume)),
        ("VOSC", lambda: TI.VOSC(volume)),
        ("VRSI", lambda: TI.VRSI(volume)),
        ("VSTD", lambda: TI.VSTD(volume)),
        ("AMO", lambda: TI.AMO(amount)),
        ("TAPI", lambda: TI.TAPI(close, amount)),
    ]

    ma_indicators = [
        ("MA", lambda: TI.MA(close)),
        ("EXPMA", lambda: TI.EXPMA(close)),
        ("BBI", lambda: TI.BBI(close)),
        ("AMV", lambda: TI.AMV(volume, amount)),
    ]

    path_indicators = [
        ("BOLL", lambda: TI.BOLL(close)),
        ("ENE", lambda: TI.ENE(close)),
        ("MIKE", lambda: TI.MIKE(close, high, low)),
        ("PBX", lambda: TI.PBX(close)),
        ("XS", lambda: TI.XS(close, high, low)),
        ("BBIBOLL", lambda: TI.BBIBOLL(close)),
    ]

    other_indicators = [
        ("ASI", lambda: TI.ASI(close, open_, high, low)),
        ("ATR", lambda: TI.ATR(close, high, low)),
        ("SAR", lambda: TI.SAR(close, high, low)),
        ("CDP", lambda: TI.CDP(close, high, low)),
    ]

    all_categories = {
        "overbought_oversold": ("一、超买超卖型", overbought_indicators),
        "trend": ("二、趋势型", trend_indicators),
        "energy": ("三、能量型", energy_indicators),
        "volume": ("四、成交量型", volume_indicators),
        "ma": ("五、均线型", ma_indicators),
        "path": ("六、路径型", path_indicators),
        "other": ("七、其他型", other_indicators),
    }

    # 单指标模式
    if indicator:
        indicator = indicator.upper()
        for cat_key, (cat_name, indicators) in all_categories.items():
            for ind_name, calc_fn in indicators:
                if ind_name.upper() == indicator:
                    try:
                        result = calc_fn()
                        # 格式化指标值为字典
                        values = {}
                        for key, series in result.items():
                            if hasattr(series.iloc[-1], 'item'):
                                value = series.iloc[-1].item()
                            else:
                                value = series.iloc[-1]
                            
                            # 根据数值类型决定保留小数位数
                            if isinstance(value, (int, np.integer)):
                                values[key] = int(value)
                            else:
                                # 对于小数，根据大小决定精度
                                if abs(value) >= 100:
                                    values[key] = round(float(value), 2)
                                elif abs(value) >= 10:
                                    values[key] = round(float(value), 3)
                                elif abs(value) >= 1:
                                    values[key] = round(float(value), 4)
                                else:
                                    values[key] = round(float(value), 6)
                        
                        output = {
                            "code": code,
                            "date": last_date,
                            "price": price_info,
                            "indicator": {
                                "name": ind_name,
                                "values": values
                            },
                            "category": cat_name,
                        }
                        print(json.dumps(output, ensure_ascii=False, indent=2))
                        return
                    except Exception as e:
                        print(json.dumps({"error": f"计算 {indicator} 失败: {str(e)}"}, ensure_ascii=False))
                        return
        print(json.dumps({"error": f"未找到指标: {indicator}"}, ensure_ascii=False))
        return

    # 类别模式或综合模式
    if category:
        categories_to_calc = {category: all_categories[category]} if category in all_categories else {}
        if not categories_to_calc:
            print(json.dumps({"error": f"未找到类别: {category}, 可选: {list(all_categories.keys())}"}, ensure_ascii=False))
            return
    else:
        categories_to_calc = all_categories

    # 计算所有指标
    result_data = {
        "code": code,
        "date": last_date,
        "data_count": len(df),
        "price": price_info,
        "categories": {},
    }

    for cat_key, (cat_name, indicators) in categories_to_calc.items():
        cat_results = []

        for ind_name, calc_fn in indicators:
            try:
                calc_result = calc_fn()
                
                # 格式化指标值为字典
                values = {}
                for key, series in calc_result.items():
                    if hasattr(series.iloc[-1], 'item'):
                        value = series.iloc[-1].item()
                    else:
                        value = series.iloc[-1]
                    
                    # 根据数值类型决定保留小数位数
                    if isinstance(value, (int, np.integer)):
                        values[key] = int(value)
                    else:
                        # 对于小数，根据大小决定精度
                        if abs(value) >= 100:
                            values[key] = round(float(value), 2)
                        elif abs(value) >= 10:
                            values[key] = round(float(value), 3)
                        elif abs(value) >= 1:
                            values[key] = round(float(value), 4)
                        else:
                            values[key] = round(float(value), 6)
                
                cat_results.append({
                    "name": ind_name,
                    "values": values
                })
            except Exception as e:
                cat_results.append({
                    "name": ind_name,
                    "values": {},
                    "error": f"计算失败: {str(e)}"
                })

        result_data["categories"][cat_key] = {
            "name": cat_name,
            "indicators": cat_results,
        }

    print(json.dumps(result_data, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description='A股技术面分析')
    parser.add_argument('code', help='股票代码 (如 60****.SH)')
    parser.add_argument('--begin', type=int, default=20240101, help='开始日期 (如 20240101)')
    parser.add_argument('--end', type=int, default=None, help='结束日期 (如 20260321)')
    parser.add_argument('--indicator', type=str, default=None, help='单个指标名称 (如 MACD, KDJ)')
    parser.add_argument('--category', type=str, default=None,
                        help='指标类别 (overbought_oversold/trend/energy/volume/ma/path/other)')

    args = parser.parse_args()

    if args.end is None:
        args.end = int(datetime.now().strftime('%Y%m%d'))

    run_analysis(args.code, args.begin, args.end, args.indicator, args.category)


if __name__ == '__main__':
    main()
