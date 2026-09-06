# 技术指标说明文档
版本: 3.0
本文档基于AmazingData算子函数实现的常用技术指标。所有指标方法均为静态方法，输入为pandas Series (OHLCV)，输出为dict of Series。共分为七类: 超买超卖型、趋势型、能量型、成交量型、均线型、路径型、其他型。

## 一、超买超卖型
超买超卖型指标用于衡量市场买卖力量的强弱，判断价格是否处于超买或超卖区域。

### 指标列表
| 序号 | 指标名称 | 中文名称 | 输出 |
| --- | --- | --- | --- |
| 1 | KDJ | 随机指标 | K, D, J |
| 2 | RSI | 相对强弱指标 | RSI6, RSI12, RSI24 |
| 3 | WR | 威廉指标 | WR10, WR6 |
| 4 | CCI | 顺势指标 | CCI |
| 5 | ROC | 变动率指标 | ROC, MAROC |
| 6 | MTM | 动量指标 | MTM, MAMTM |
| 7 | BIAS | 乖离率 | BIAS6, BIAS12, BIAS24 |
| 8 | SKDJ | 慢速随机指标 | K, D |
| 9 | MFI | 资金流量指标 | MFI |
| 10 | OSC | 变动速率线 | OSC, MAOSC |
| 11 | UDL | 引力线 | UDL, MAUDL |
| 12 | ACCER | 幅度涨速 | ACCER |
| 13 | RCCD | 异同离差乖离率 | DIF, RCCD |
| 14 | MARSI | 相对强弱平均线 | RSI1, RSI2 |

### 指标说明
#### （1）KDJ(close, high, low, n=9, m1=3, m2=3) 随机指标
- **说明**: 通过最高价、最低价及收盘价之间的关系来判断超买超卖，K>80超买，K<20超卖
- **公式**: RSV=(CLOSE-LLV(LOW,N))/(HHV(HIGH,N)-LLV(LOW,N))*100; K=SMA(RSV,M1,1); D=SMA(K,M2,1); J=3*K-2*D
- **输出**: K, D, J

#### （2）RSI(close, n1=6, n2=12, n3=24) 相对强弱指标
- **说明**: 通过比较一段时期内的平均收盘涨幅和平均收盘跌幅来分析买卖力量，RSI>80超买，RSI<20超卖
- **公式**: LC=REF(CLOSE,1); RSI=SMA(MAX(CLOSE-LC,0),N,1)/SMA(ABS(CLOSE-LC),N,1)*100
- **输出**: RSI6, RSI12, RSI24

#### （3）WR(close, high, low, n1=10, n2=6) 威廉指标
- **说明**: 利用最高价、最低价和收盘价来判断超买超卖，WR>80超卖，WR<20超买
- **公式**: WR=(HHV(HIGH,N)-CLOSE)/(HHV(HIGH,N)-LLV(LOW,N))*100
- **输出**: WR10, WR6

#### （4）CCI(close, high, low, n=14) 顺势指标
- **说明**: 测量价格偏离统计平均值的程度，CCI>100超买，CCI<-100超卖
- **公式**: TYP=(HIGH+LOW+CLOSE)/3; CCI=(TYP-MA(TYP,N))* 1000/(15*AVEDEV(TYP,N))
- **输出**: CCI

#### （5）ROC(close, n=12, m=6) 变动率指标
- **说明**: 当前价格与N日前价格的变化百分比，反映价格变动速度
- **公式**:NN = MIN(BARSCOUNT(C), N); ROC=(CLOSE-REF(CLOSE,NN))/REF(CLOSE,NN)*100; MAROC=MA(ROC,M)
- **输出**: ROC, MAROC

#### （6）MTM(close, n=12, m=6) 动量指标
- **说明**: 当前价格与N日前价格的差值，反映价格变动的绝对动量
- **公式**: MTM = CLOSE - REF(CLOSE, MIN(BARSCOUNT(C),N)); MAMTM=MA(MTM,M)
- **输出**: MTM, MAMTM

#### （7）BIAS(close, n1=6, n2=12, n3=24) 乖离率
- **说明**: 收盘价与移动平均线之间的偏离程度，正值表示价格高于均线，负值表示低于均线
- **公式**: BIAS=(CLOSE-MA(CLOSE,N))/MA(CLOSE,N)*100
- **输出**: BIAS6, BIAS12, BIAS24

#### （8）SKDJ(close, high, low, n=9, m=3) 慢速随机指标
- **说明**: KDJ的慢速版本，通过双重平滑减少噪音，更适合中长线判断超买超卖
- **公式**: RSV=EMA((CLOSE-LLV(LOW,N))/(HHV(HIGH,N)-LLV(LOW,N))*100,M); K=EMA(RSV,M); D=MA(K,M)
- **输出**: K, D

#### （9）MFI(close, high, low, volume, n=14, n2=6) 资金流量指标
- **说明**: 结合价格和成交量的RSI变体，MFI>80超买，MFI<20超卖
- **公式**: TYP=(HIGH+LOW+CLOSE)/3; MR=TYP*VOL; PMF=SUM(IF(TYP>REF(TYP,1),MR,0),N); NMF=SUM(IF(TYP< REF(TYP,1),MR,0),N); MFI = 100-(100/(1+PMF/NMF))
- **输出**: MFI

#### （10）OSC(close, n=20, m=6) 变动速率线
- **说明**: 当前价格与移动平均线的差值放大100倍，反映价格偏离均线的速率
- **公式**: OSC=(CLOSE-MA(CLOSE,N))*100; MAOSC=EMA(OSC,M)
- **输出**: OSC, MAOSC

#### （11）UDL(close, n1=3, n2=5, n3=10, n4=20, m=6) 引力线
- **说明**: 将不同周期均线综合平均，反映价格的引力中心
- **公式**: UDL=(MA(CLOSE,N1)+MA(CLOSE,N2)+MA(CLOSE,N3)+MA(CLOSE,N4))/4; MAUDL=MA(UDL,M)
- **输出**: UDL, MAUDL

#### （12）ACCER(close, n=8) 幅度涨速
- **说明**: 价格变动幅度除以周期数，衡量单位时间内的价格变动速率
- **公式**: ACCER = SLOPE(CLOSE,N)/CLOSE
- **输出**: ACCER

#### （13）RCCD(close, n=59, short=26, long=52, m=26) 异同离差乖离率
- **说明**: 通过价格比率的短长期均线差值来判断趋势变化，类似MACD的变体
- **公式**: RC=CLOSE/REF(CLOSE,N); ARC=SMA(REF(RC,1),N,1); DIF=MA(ARC,SHORT)-MA(ARC,LONG); RCCD=SMA(DIF,M,1)
- **输出**: DIF, RCCD

#### （14）MARSI(close, m1=10, m2=6) 相对强弱平均线
- **说明**: RSI的移动平均线，平滑RSI波动，更适合判断中期超买超卖
- **公式**:  DIF = CLOSE-REF(CLOSE,1);
            VU = IF(DIF>=0,DIF,0);
            VD = IF(DIF<0,-DIF,0);
            MAU1 = MEMA(VU,M1);
            MAD1 = MEMA(VD,M1);
            MAU2 = MEMA(VU,M2);
            MAD2 = MEMA(VD,M2);
            RSI1 = MA(100*MAU1/(MAU1+MAD1),M1);
            RSI2 = MA(100*MAU2/(MAU2+MAD2),M2);
- **输出**: RSI1, RSI2

## 二、趋势型
趋势型指标用于判断市场的运行方向和趋势强度，帮助投资者识别多空趋势。

### 指标列表
| 序号 | 指标名称 | 中文名称 | 输出 |
| --- | --- | --- | --- |
| 1 | MACD | 指数平滑异同移动平均线 | DIF, DEA, MACD |
| 2 | DMI | 趋向指标 | PDI, MDI, ADX, ADXR |
| 3 | DMA | 平行线差指标 | DIF, DIFMA |
| 4 | TRIX | 三重指数平滑移动平均 | TRIX, MATRIX |
| 5 | ARBR | 人气意愿指标 | AR, BR |
| 6 | EMV | 简易波动指标 | EMV, MAEMV |
| 7 | DPO | 区间震荡线 | DPO, MADPO |
| 8 | VHF | 十字过滤线 | VHF |
| 9 | CHO | 佳庆指标 | CHO, MACHO |
| 10 | DBCD | 异同离差乖离率 | DBCD, MM |
| 11 | DDI | 方向标准离差指数 | DDI, ADDI, AD |
| 12 | JS | 加速线 | JS, MAJ5, MAJ10, MAJ20 |
| 13 | QACD | 快速异同移动平均 | DIF, MACD, DDIF |
| 14 | UOS | 终极指标 | UOS, MAUOS |

### 指标说明
#### （1）MACD(close, short=12, long=26, mid=9) 指数平滑异同移动平均线
- **说明**: 由快慢均线的聚合与分离来判断买卖时机，DIF为快慢线差值，DEA为DIF的均线，MACD柱为两者差值的2倍
- **公式**: DIF=EMA(CLOSE,SHORT)-EMA(CLOSE,LONG); DEA=EMA(DIF,MID); MACD=2*(DIF-DEA)
- **输出**: DIF, DEA, MACD

#### （2）DMI(close, high, low, n=14, m=6) 趋向指标
- **说明**: 通过分析多空双方力量的变化来判断趋势，PDI > MDI多头占优，PDI < MDI空头占优，ADX衡量趋势强度
- **公式**: MTR = SUM(MAX(MAX(HIGH-LOW,ABS(HIGH-REF(CLOSE,1))),ABS(REF(CLOSE,1)-LOW)),N);
            HD = HIGH - REF(HIGH, 1);
            LD = REF(LOW, 1) - LOW;
            DMP = SUM(IF(HD>0 AND HD>LD, HD, 0), N);
            DMM = SUM(IF(LD>0 AND LD>HD, LD, 0), N);
            PDI = DMP * 100 / MTR;
            MDI = DMM * 100 / MTR;
            ADX = MA(ABS(MDI-PDI)/(MDI+PDI)*100, M);
            ADXR = (ADX + REF(ADX, M)) / 2;
- **输出**: PDI, MDI, ADX, ADXR

#### （3）DMA(close, n1=10, n2=50, m=10) 平行线差指标
- **说明**: 短期均线与长期均线的差值，反映多空力量对比
- **公式**: DIF=MA(CLOSE,N1)-MA(CLOSE,N2); AMA=MA(DIF,M)
- **输出**: DIF, DIFMA

#### （4）TRIX(close, n=12, m=9) 三重指数平滑移动平均
- **说明**: 对收盘价进行三次指数平滑后求变化率，过滤短期波动，反映中长期趋势
- **公式**: TR=EMA(EMA(EMA(CLOSE,N),N),N); TRIX=(TR-REF(TR,1))/REF(TR,1)*100; MATRIX=MA(TRIX,M)
- **输出**: TRIX, MATRIX

#### （5）ARBR(close, open_, high, low, n=26) 人气意愿指标
- **说明**: AR反映开盘价在最高最低价之间的位置(人气指标)，BR反映收盘价在最高最低价之间的位置(意愿指标)
- **公式**: AR=SUM(HIGH-OPEN,N)/SUM(OPEN-LOW,N)*100; BR=SUM(MAX(0,HIGH-REF(CLOSE,1)),N)/SUM(MAX(0,REF(CLOSE,1)-LOW),N)*100
- **输出**: AR, BR

#### （6）EMV(close, high, low, volume, n=14, m=9) 简易波动指标
- **说明**: 结合价格变动幅度和成交量来衡量价格波动的难易程度，EMV>0多头占优，EMV<0空头占优
- **公式**: VOLUME=MA(VOL,N)/VOL; MID=100*(HIGH+LOW-REF(HIGH+LOW, 1))/(HIGH+LOW); EMV=MA(MID*VOLUME*(HIGH-LOW)/MA(HIGH-LOW,N),N); MAEMV=MA(EMV,M)
- **输出**: EMV, MAEMV

#### （7）DPO(close, n=20, m=6) 区间震荡线
- **说明**: 去除趋势后的价格震荡，用于识别价格周期和超买超卖
- **公式**: DPO=CLOSE-REF(MA(CLOSE,N),N/2+1); MADPO=MA(DPO,M)
- **输出**: DPO, MADPO

#### （8）VHF(close, n=28) 十字过滤线
- **说明**: 衡量市场是处于趋势状态还是震荡状态，VHF值越大趋势越明显
- **公式**: HCP=HHV(CLOSE,N); LCP=LLV(CLOSE,N); VHF=(HCP-LCP)/SUM(ABS(CLOSE-REF(CLOSE,1)),N)
- **输出**: VHF

#### （9）CHO(close, high, low, volume, n1=10, n2=20, m=6) 佳庆指标
- **说明**: 基于累积/派发线(AD线)的短长期均线差值，反映资金流入流出的趋势变化
- **公式**: MID=CUMSUM(VOL*(2*CLOSE-HIGH-LOW)/(HIGH+LOW)); CHO=MA(MID,N1)-MA(MID,N2); MACHO=MA(CHO,M)
- **输出**: CHO, MACHO

#### （10）DBCD(close, n=5, m=16, t=17) 异同离差乖离率
- **说明**: 乖离率的变化量经平滑处理后的指标，用于判断价格偏离均线的加速或减速
- **公式**: BIAS=(CLOSE-MA(CLOSE,N))/MA(CLOSE,N); DIF=BIAS-REF(BIAS,M); DBCD=SMA(DIF,T,1); MM=MA(DBCD,5)
- **输出**: DBCD, MM

#### （11）DDI(close, high, low, n=13, n1=26, m=1, m1=5) 方向标准离差指数
- **说明**: 通过最高价和最低价的变化方向来判断多空力量，DDI>0多头占优，DDI<0空头占优
- **公式**: TR = MAX(ABS(HIGH-REF(HIGH,1)), ABS(LOW-REF(LOW,1)));
            DMZ = IF((HIGH+LOW)<=(REF(HIGH,1)+REF(LOW,1)), 0,MAX(ABS(HIGH-REF(HIGH, 1)),ABS(LOW-REF(LOW, 1))));
            DMF = IF((HIGH+LOW)>=(REF(HIGH,1)+REF(LOW,1)), 0,MAX(ABS(HIGH-REF(HIGH, 1)),ABS(LOW-REF(LOW, 1))));
            DIZ = SUM(DMZ,N) / (SUM(DMZ,N)+SUM(DMF,N));
            DIF = SUM(DMF,N) / (SUM(DMF,N)+SUM(DMZ,N));
            DDI = DIZ - DIF;
            ADDI = SMA(DDI, N1, M);
            ADl = MA(ADDI, M1);
- **输出**: DDI, ADDI, ADl

#### （12）JS(close, high, low, n=5, m1=5, m2=10, m3=20) 加速线
- **说明**: 价格变动百分比及其多周期均线，反映价格加速上涨或下跌的程度
- **公式**: JS=(CLOSE-REF(CLOSE,N))/(N*REF(CLOSE,N)*100; MAJ=MA(JS,M); MAJ2 = MA(JS, M2); MAJ3 = MA(JS, M3)
- **输出**: JS, MAJ5, MAJ10, MAJ20

#### （13）QACD(close, n1=12, n2=26, m=9) 快速异同移动平均
- **说明**: MACD的变体，QACD为DIF与其均线的差值，反映短期动量变化
- **公式**: DIF=EMA(CLOSE,N1)-EMA(CLOSE,N2); MACD=EMA(DIF,M); DDIF=DIF-MACD
- **输出**: DIF, MACD, DDIF

#### （14）UOS(close, high, low, n1=7, n2=14, n3=28, m=6) 终极指标
- **说明**: 综合三个不同周期的买压比率，消除单一周期的偏差，UOS>50多头，UOS<50空头
- **公式**: TH = MAX(HIGH, REF(CLOSE,1)); TL = MIN(LOW, REF(CLOSE,1));
            ACC1 = SUM(CLOSE-TL,N1)/SUM(TH-TL,N1);
            ACC2 = SUM(CLOSE-TL,N2)/SUM(TH-TL,N2);
            ACC3 = SUM(CLOSE-TL,N3)/SUM(TH-TL,N3);
            UOS = (ACC1*N2*N3+ACC2*N1*N3+ACC3*N1*N2)*100/(N1*N2+N1*N3+N2*N3);
            MAUOS = EXPMA(UOS, M)
- **输出**: UOS, MAUOS

## 三、能量型
能量型指标通过分析多空双方的力量对比，衡量市场参与者的情绪和意愿。

### 指标列表
| 序号 | 指标名称 | 中文名称 | 输出 |
| --- | --- | --- | --- |
| 1 | CR | 能量指标 | CR, MA1, MA2, MA3, MA4 |
| 2 | PSY | 心理线 | PSY, PSYMA |
| 3 | MASS | 梅斯线 | MASS, MAMASS |
| 4 | PCNT | 幅度比 | PCNT, MAPCNT |
| 5 | WAD | 威廉多空力度线 | WAD, MAWAD |

### 指标说明
#### （1）CR(close, high, low, n=26, m1 = 10, m2 = 20, m3 = 40, m4 = 62) 能量指标
- **说明**: 以昨日中间价为基准，衡量多空双方的能量对比，CR>200超买，CR<40超卖
- **公式**: MID = REF(HIGH + LOW, 1)/2
            CR = SUM(MAX(0, HIGH-MID), N) / SUM(MAX(0, MID-LOW), N) * 100
            MA1:REF(MA(CR,M1),M1/2.5+1);
            MA2:REF(MA(CR,M2),M2/2.5+1);
            MA3:REF(MA(CR,M3),M3/2.5+1);
            MA4:REF(MA(CR,M4),M4/2.5+1);
- **输出**: CR, MA1, MA2, MA3, MA4

#### （2）PSY(close, n=12, m=6) 心理线
- **说明**: 统计N日内上涨天数的比例，反映投资者的心理预期，PSY>75超买，PSY<25超卖
- **公式**: PSY=COUNT(CLOSE>REF(CLOSE,1),N)/N*100; MAPSY=MA(PSY,M)
- **输出**: PSY, PSYMA

#### （3）MASS(high, low, n1=9, n2=25, m=6) 梅斯线
- **说明**: 通过最高价与最低价波幅的指数平滑比值累计，判断趋势反转信号
- **公式**: MASS=SUM(EMA(HIGH-LOW,N1)/EMA(EMA(HIGH-LOW,N1),N1),N2); MAMASS=MA(MASS,M)
- **输出**: MASS, MAMASS

#### （4）PCNT(close, m = 5) 幅度比
- **说明**: 当日收盘价相对于前一日收盘价的涨跌幅百分比
- **公式**: PCNT=(CLOSE-REF(CLOSE,1))/CLOSE*100; MAPCNT = EXPMEMA(PCNT,M)
- **输出**: PCNT, MAPCNT

#### （5）WAD(close, high, low, m = 30) 威廉多空力度线
- **说明**: 通过累计多空力度来判断趋势，WAD上升表示多方力量增强，下降表示空方力量增强
- **公式**:  MIDA = CLOSE - MIN(LOW, REF(CLOSE, 1))  (当CLOSE>REF(CLOSE,1));
            MIDB = IF(CLOSE < REF(CLOSE,1),CLOSE-MAX(REF(CLOSE,1),HIGH),0) (当CLOSE < REF(CLOSE,1));
            WAD = SUM(IF(CLOSE>REF(CLOSE,1),MIDA,MIDB),0);
            MAWAD:MA(WAD,M);
- **输出**: WAD, MAWAD

## 四、成交量型
成交量型指标结合成交量与价格变化，分析资金流向和买卖力量。

### 指标列表
| 序号 | 指标名称 | 中文名称 | 输出 |
| --- | --- | --- | --- |
| 1 | OBV | 能量潮 | OBV, MAOBV |
| 2 | VR | 成交量变异率 | VR, MAVR |
| 3 | VOLMA | 成交量均线 | VOLMA5, VOLMA10 |
| 4 | WVAD | 威廉变异离散量 | WVAD, MAWVAD |
| 5 | VOSC | 成交量震荡 | VOSC |
| 6 | VRSI | 量相对强弱 | VRSI6, VRSI12, VRSI24 |
| 7 | VSTD | 成交量标准差 | VSTD |
| 8 | AMO | 成交额均线 | AMOW, AMO5, AMO10 |
| 9 | HSL | 换手线 | HSL, MAHSL |
| 10 | TAPI | 加权指数成交值 | TAPI, MATAPI |

### 指标说明
#### （1）OBV(close, volume, m=30) 能量潮
- **说明**: 通过累计成交量的正负来衡量买卖压力，OBV上升表示买方力量增强
- **公式**: 若收盘价>昨收: OBV=前日OBV+今日成交量; 若收盘价<昨收: OBV=前日OBV-今日成交量
            VA:=IF(CLOSE>REF(CLOSE,1),VOL,-VOL);
            OBV:SUM(IF(CLOSE=REF(CLOSE,1),0,VA),0);
            MAOBV:MA(OBV,M)
- **输出**: OBV, MAOBV

#### （2）VR(close, volume, n=26, m=6) 成交量变异率
- **说明**: 通过上涨日与下跌日的成交量比值来判断市场人气，VR>450超买，VR<70超卖
- **公式**: AV=SUM(IF(C>REF(C,1),VOL,0),N); BV=SUM(IF(C < REF(C,1),VOL,0),N); CV=SUM(IF(C=REF(C,1),VOL,0),N); VR=(AV+CV/2)/(BV+CV/2)*100, MAVR=MA(VR, M)
- **输出**: VR, MAVR

#### （3）VOLMA(volume, n1=5, n2=10) 成交量均线
- **说明**: 成交量的简单移动平均线，用于判断成交量的趋势变化
- **公式**: VOLMA=MA(VOLUME,N)
- **输出**: VOLMA5, VOLMA10

#### （4）WVAD(close, open_, high, low, volume, n=24, m=6) 威廉变异离散量
- **说明**: 结合价格涨跌幅与成交量，衡量多空双方的实际力量对比
- **公式**: WVAD=SUM((CLOSE-OPEN)/(HIGH-LOW)*VOL,N); MAWVAD=MA(WVAD,M)/10000
- **输出**: WVAD, MAWVAD

#### （5）VOSC(volume, short=12, long=26) 成交量震荡
- **说明**: 短期成交量均线与长期成交量均线的偏离百分比，反映成交量的变化趋势
- **公式**: VOSC=(MA(VOL,SHORT)-MA(VOL,LONG))/MA(VOL,SHORT)*100
- **输出**: VOSC

#### （6）VRSI(volume, n1=6, n2=12, n3=24) 量相对强弱
- **说明**: 将RSI的计算方法应用于成交量，衡量成交量的相对强弱
- **公式**: LV=REF(VOL,1); VRSI=SMA(MAX(VOL-LV,0),N,1)/SMA(ABS(VOL-LV),N,1)*100
- **输出**: VRSI6, VRSI12, VRSI24

#### （7）VSTD(volume, n=10) 成交量标准差
- **说明**: 成交量在N日内的标准差，衡量成交量的波动程度
- **公式**: VSTD=STD(VOL,N)
- **输出**: VSTD

#### （8）AMO(amount, n1=5, n2=10) 成交额均线
- **说明**: 成交额的简单移动平均线，用于判断资金流入流出的趋势
- **公式**: ANMOW = AMOUNT/10000; AMO=MA(AMOUNT,N)
- **输出**: AMOW, AMO5, AMO10

#### （9）HSL(close, turnover_rate, n=5, m=10) 换手线
- **说明**: 换手率的移动平均线，反映市场交投活跃程度的趋势变化
- **公式**: HSL:IF((SETCODE==0||SETCODE==1||SETCODE==2),100*VOL,VOL)/(FINANCE(7)/100); MAHSL:MA(HSL,N);
- **输出**: HSL, MAHSL

#### （10）TAPI(close, amount, n=6) 加权指数成交值
- **说明**: 成交额与收盘价的比值，衡量每单位价格对应的成交金额
- **公式**: TAPI=AMOUNT/CLOSE; MATAPI=MA(TAPI,N)
- **输出**: TAPI, MATAPI

## 五、均线型
均线型指标通过对价格进行不同方式的平均处理，反映价格的趋势方向和支撑压力。

### 指标列表
| 序号 | 指标名称 | 中文名称 | 输出 |
| --- | --- | --- | --- |
| 1 | MA | 移动平均线 | MA5, MA10, MA20, MA60 |
| 2 | EXPMA | 指数平均线 | EXPMA12, EXPMA50 |
| 3 | BBI | 多空指标 | BBI |
| 4 | AMV | 成本价均线 | AMV5, AMV13, AMV34, AMV60 |

### 指标说明
#### （1）MA(close, n1=5, n2=10, n3=20, n4=60) 移动平均线
- **说明**: N日简单移动平均线，算法: (X1+X2+...+Xn)/N
- **公式**: MA(CLOSE, N)
- **输出**: MA5, MA10, MA20, MA60

#### （2）EXPMA(close, n1=12, n2=50) 指数平均线
- **说明**: N日指数移动平均线，对近期数据赋予更大权重
- **公式**: EMA(CLOSE, N)
- **输出**: EXPMA12, EXPMA50

#### （3）BBI(close, m1=3, m2=6, m3=12, m4=24) 多空指标
- **说明**: 将不同周期的移动平均线加权平均，综合反映多空力量
- **公式**: BBI=(MA(CLOSE,m1)+MA(CLOSE,m2)+MA(CLOSE,m3)+MA(CLOSE,m4))/4
- **输出**: BBI

#### （4）AMV(volume, amount, n1=5, n2=13, n3=34, n4=60) 成本价均线
- **说明**: 以成交均价(成交额/成交量)的移动平均线，反映市场平均持仓成本
- **公式**: AMOV = VOL*(OPEN+CLOSE)/2; AMV = SUM(AMOV, N) / SUM(VOL, N)
- **输出**: AMV5, AMV13, AMV34, AMV60

## 六、路径型
路径型指标通过构建价格运行的上下轨道，帮助判断价格的支撑与压力位。

### 指标列表
| 序号 | 指标名称 | 中文名称 | 输出 |
| --- | --- | --- | --- |
| 1 | BOLL | 布林线 | BOLL, UB, LB |
| 2 | ENE | 轨道线 | UPPER, ENE, LOWER |
| 3 | MIKE | 麦克指标 | WEKR, MIDR, STOR, WEKS, MIDS, STOS |
| 4 | PBX | 瀑布线 | PBX4, PBX6, PBX9, PBX13, PBX18, PBX24 |
| 5 | XS | 薛斯通道 | SUP, SDN, LUP, LDN |
| 6 | BBIBOLL | BBI多空布林线 | BBIBOLL, UPPER, LOWER |

### 指标说明
#### （1）BOLL(close, n=20, k=2) 布林线
- **说明**: 以移动平均线为中轨，上下各加减K倍标准差构成通道，价格触及上轨为超买，触及下轨为超卖
- **公式**:  MID=MA(CLOSE,N); VART1= POW((CLOSE-MID), 2); VART2 = MA(VART1, N); VART3 = SQRT(VART2); UPPER=MID+K*VART3; LOWER=MID-K*VART3; BOLL = REF(MID, 1); UB = REF(UPPER, 1), LB=REF(LOWER, 1)
- **输出**: BOLL, UB, LB

#### （2）ENE(close, n=25, m1=6, m2=6) 轨道线
- **说明**: 以移动平均线为基准，按固定百分比上下偏移构成轨道
- **公式**: UPPER=MA(CLOSE,N)*(1+M1/100); LOWER=MA(CLOSE,N)*(1-M2/100); ENE=(UPPER+LOWER)/2
- **输出**: UPPER, ENE, LOWER

#### （3）MIKE(close, high, low, n=10) 麦克指标
- **说明**: 利用典型价格与最高最低价构建三条压力线(WR/MR/SR)和三条支撑线(WS/MS/SS)
- **公式**: HLC = REF(MA((HIGH+LOW+CLOSE)/3,N),1);
            HV = EMA(HHV(HIGH,N),3);
            LV = EMA(LLV(LOW,N),3);
            STOR = EMA(2*HV-LV,3);
            MIDR = EMA(HLC+HV-LV,3);
            WEKR = EMA(HLC*2-LV,3);
            WEKS = EMA(HLC*2-HV,3);
            MIDS = EMA(HLC-HV+LV,3);
            STOS = EMA(2*LV-HV,3);
- **输出**: WEKR, MIDR, STOR, WEKS, MIDS, STOS

#### （4）PBX(close, m1=4, m2=6, m3=9, m4=13, m5=18, m6=24) 瀑布线
- **说明**: 多条不同周期的三重EMA均线，形似瀑布，用于判断趋势方向和支撑压力
- **公式**: PBX=(EMA(CLOSE,M)+EMA(CLOSE,2*M)+EMA(CLOSE,4*M))/3
- **输出**: PBX4, PBX6, PBX9, PBX13, PBX18, PBX24

#### （5）XS(close, high, low, n=13) 薛斯通道
- **说明**: 基于最高价、收盘价、最低价的SMA构建四条通道线，形成内外两个通道
- **公式**: VAR2:=CLOSE*VOL;
            VAR3:=EMA((EMA(VAR2,3)/EMA(VOL,3)+EMA(VAR2,6)/EMA(VOL,6)+EMA(VAR2,12)/EMA(VOL,12)+EMA(VAR2,24)/EMA(VOL,24))/4,N);
            SUP:1.06*VAR3;
            SDN:VAR3*0.94;
            VAR4:=EMA(CLOSE,9);
            LUP:EMA(VAR4*1.14,5);
            LDN:EMA(VAR4*0.86,5);
- **输出**: SUP, SDN, LUP, LDN

#### （6）BBIBOLL(close, n=11, m=6) BBI多空布林线
- **说明**: 以BBI多空指标为中轨，加减K倍标准差构成布林通道，结合多空判断与通道分析
- **公式**: BBI=(MA(C,3)+MA(C,6)+MA(C,12)+MA(C,24))/4; UPPER=BBI+M*STD(BBI,N); LOWER=BBI-M*STD(BBI,N)
- **输出**: BBIBOLL, UPPER, LOWER

## 七、其他型
其他常用技术指标，包括振动升降、真实波幅、抛物线转向、逆势操作等。

### 指标列表
| 序号 | 指标名称 | 中文名称 | 输出 |
| --- | --- | --- | --- |
| 1 | ASI | 振动升降指标 | SI, ASI |
| 2 | ATR | 真实波幅均值 | TR, ATR |
| 3 | SAR | 抛物线转向指标 | SAR |
| 4 | CDP | 逆势操作 | AH, NH, CDP, NL, AL |

### 指标说明
#### （1）ASI(close, open_, high, low) 振动升降指标
- **说明**: 以开盘、最高、最低、收盘价与前一日价格比较，计算出真实的价格变动量并累计
- **公式**: A = ABS(HIGH - REF(CLOSE, 1));
            B = ABS(LOW - REF(CLOSE, 1));
            C = ABS(HIGH - REF(LOW, 1));
            D = ABS(REF(CLOSE, 1) - REF(OPEN, 1));
            R = 根据A/B/C大小关系取不同值;
            SI = 8 * (CLOSE-REF(CLOSE,1) + (CLOSE-OPEN)/2 + (REF(CLOSE,1)-REF(OPEN,1))/4) / R * MAX(A,B);
            ASI = SUM(SI, 0)  即累计
- **输出**: SI, ASI

#### （2）ATR(close, high, low, n=14) 真实波幅均值
- **说明**: 真实波幅的N日移动平均，衡量市场波动性大小
- **公式**:  MTR:MAX(MAX((HIGH-LOW),ABS(REF(CLOSE,1)-HIGH)),ABS(REF(CLOSE,1)-LOW)); ATR = MA(MTR, N)
- **输出**: MTR, ATR

#### （3）SAR(close, high, low, n=4, step=0.02, max_af=0.2) 抛物线转向指标
- **说明**: 随时间推移不断调整止损点位，当价格跌破SAR时为卖出信号，突破SAR时为买入信号
- **公式**: 初始方向根据前N日趋势判定，加速因子从step开始，每创新高/低增加step，最大max_af
- **输出**: SAR

#### （4）CDP(close, high, low) 逆势操作
- **说明**: 根据前一日价格计算今日的最高值(AH)、近高值(NH)、均价(CDP)、近低值(NL)、最低值(AL)五个价位
- **公式**: CH:=REF(H,1);
            CL:=REF(L,1);
            CC:=REF(C,1);
            CDP:(CH+CL+CC)/3;
            AH:2*CDP+CH-2*CL;
            NH:CDP+CDP-CL;
            NL:CDP+CDP-CH;
            AL:2*CDP-2*CH+CL;
- **输出**: AH, NH, CDP, NL, AL

### API案例
```python
import AmazingData as ad
import config_user
from demo.technical_indicators import TechnicalIndicators

# 登录
ad.login(username=config_user.user['username'],
         password=config_user.user['password'],
         host=config_user.user['host'],
         port=config_user.user['port'])

# 获取数据
base_data_object = ad.BaseData()
calendar = base_data_object.get_calendar()
market_data_object = ad.MarketData(calendar)
code = '000001.SH'
kline_day = market_data_object.query_kline([code], begin_date=20230101, end_date=20260101, period=ad.constant.Period.day.value)
df = kline_day[code]

close = df['close']
open_ = df['open']
high = df['high']
low = df['low']
volume = df['volume']
amount = df['amount'] if 'amount' in df.columns else close * volume

TI = TechnicalIndicators
```

# ========== 超买超卖型 ==========
```python
# KDJ - 随机指标
kdj = TI.KDJ(close, high, low)

# RSI - 相对强弱指标
rsi = TI.RSI(close)

# WR - 威廉指标
wr = TI.WR(close, high, low)

# CCI - 顺势指标
cci = TI.CCI(close, high, low)

# ROC - 变动率指标
roc = TI.ROC(close)

# MTM - 动量指标
mtm = TI.MTM(close)

# BIAS - 乖离率
bias = TI.BIAS(close)

# SKDJ - 慢速随机指标
skdj = TI.SKDJ(close, high, low)

# MFI - 资金流量指标
mfi = TI.MFI(close, high, low, volume)

# OSC - 变动速率线
osc = TI.OSC(close)

# UDL - 引力线
udl = TI.UDL(close)

# ACCER - 幅度涨速
accer = TI.ACCER(close)

# RCCD - 异同离差乖离率
rccd = TI.RCCD(close)

# MARSI - 相对强弱平均线
marsi = TI.MARSI(close)
```

# ========== 趋势型 ==========
```python
# MACD - 指数平滑异同移动平均线
macd = TI.MACD(close)

# DMI - 趋向指标
dmi = TI.DMI(close, high, low)

# DMA - 平行线差指标
dma = TI.DMA(close)

# TRIX - 三重指数平滑移动平均
trix = TI.TRIX(close)

# ARBR - 人气意愿指标
arbr = TI.ARBR(close, open_, high, low)

# EMV - 简易波动指标
emv = TI.EMV(close, high, low, volume)

# DPO - 区间震荡线
dpo = TI.DPO(close)

# VHF - 十字过滤线
vhf = TI.VHF(close)

# CHO - 佳庆指标
cho = TI.CHO(close, high, low, volume)

# DBCD - 异同离差乖离率
dbcd = TI.DBCD(close)

# DDI - 方向标准离差指数
ddi = TI.DDI(close, high, low)

# JS - 加速线
js = TI.JS(close, high, low)

# QACD - 快速异同移动平均
qacd = TI.QACD(close)

# UOS - 终极指标
uos = TI.UOS(close, high, low)
```

# ========== 能量型 ==========
```python
# CR - 能量指标
cr = TI.CR(close, high, low)

# PSY - 心理线
psy = TI.PSY(close)

# MASS - 梅斯线
mass = TI.MASS(high, low)

# PCNT - 幅度比
pcnt = TI.PCNT(close)

# WAD - 威廉多空力度线
wad = TI.WAD(close, high, low)
```

# ========== 成交量型 ==========
```python
# OBV - 能量潮
obv = TI.OBV(close, volume)

# VR - 成交量变异率
vr = TI.VR(close, volume)

# VOLMA - 成交量均线
vol_ma = TI.VOLMA(volume)

# WVAD - 威廉变异离散量
wvad = TI.WVAD(close, open_, high, low, volume)

# VOSC - 成交量震荡
vosc = TI.VOSC(volume)

# VRSI - 量相对强弱
vrsi = TI.VRSI(volume)

# VSTD - 成交量标准差
vstd = TI.VSTD(volume)

# AMO - 成交额均线
amo = TI.AMO(amount)

# TAPI - 加权指数成交值
tapi = TI.TAPI(close, amount)
```

# ========== 均线型 ==========
```python
# MA - 移动平均线
ma = TI.MA(close)

# EXPMA - 指数平均线
expma = TI.EXPMA(close)

# BBI - 多空指标
bbi = TI.BBI(close)

# AMV - 成本价均线
amv = TI.AMV(volume, amount)
```

# ========== 路径型 ==========
```python
# BOLL - 布林线
boll = TI.BOLL(close)

# ENE - 轨道线
ene = TI.ENE(close)

# MIKE - 麦克指标
mike = TI.MIKE(close, high, low)

# PBX - 瀑布线
pbx = TI.PBX(close)

# XS - 薛斯通道
xs = TI.XS(close, high, low)

# BBIBOLL - BBI多空布林线
bbiboll = TI.BBIBOLL(close)
```

# ========== 其他型 ==========
```python
# ASI - 振动升降指标
asi = TI.ASI(close, open_, high, low)

# ATR - 真实波幅均值
atr = TI.ATR(close, high, low)

# SAR - 抛物线转向指标
sar = TI.SAR(close, high, low)

# CDP - 逆势操作
cdp = TI.CDP(close, high, low)
```

### 应用案例
以下示例展示各类技术指标的典型调用方式与结果获取方法。所有指标方法均返回 dict of Series，可通过键名获取对应指标序列。

#### 案例一: 超买超卖型指标
##### KDJ 随机指标
```python
# 计算KDJ指标 (默认参数 n=9, m1=3, m2=3)
kdj = TI.KDJ(close, high, low)

# 获取K、D、J三条线
k_line = kdj['K']
d_line = kdj['D']
j_line = kdj['J']

# 查看最近5日的值
print(k_line.tail(5))
print(d_line.tail(5))
print(j_line.tail(5))

# 自定义参数
kdj_custom = TI.KDJ(close, high, low, n=14, m1=5, m2=5)
```

##### RSI 相对强弱指标
```python
# 计算RSI指标 (默认三个周期: 6, 12, 24)
rsi = TI.RSI(close)

# 获取不同周期的RSI
rsi6 = rsi['RSI6']
rsi12 = rsi['RSI12']
rsi24 = rsi['RSI24']

# 查看最近值
print(rsi6.tail(5))

# 自定义周期
rsi_custom = TI.RSI(close, n1=7, n2=14, n3=21)
```

##### CCI 顺势指标
```python
# 计算CCI指标
cci = TI.CCI(close, high, low, n=14)

# 获取CCI序列
cci_line = cci['CCI']
print(cci_line.tail(5))
```

##### BIAS 乖离率
```python
# 计算BIAS指标
bias = TI.BIAS(close)

# 获取不同周期的乖离率
bias6 = bias['BIAS6']
bias12 = bias['BIAS12']
bias24 = bias['BIAS24']
print(bias6.tail(5))
```

#### 案例二: 趋势型指标
##### MACD 指数平滑异同移动平均线
```python
# 计算MACD指标
macd = TI.MACD(close)

# 获取DIF、DEA、MACD柱
dif = macd['DIF']
dea = macd['DEA']
macd_bar = macd['MACD']

# 查看最近值
print(dif.tail(5))
print(dea.tail(5))
print(macd_bar.tail(5))

# 自定义参数
macd_custom = TI.MACD(close, short=10, long=22, mid=7)
```

##### DMI 趋向指标
```python
# 计算DMI指标
dmi = TI.DMI(close, high, low)

# 获取PDI、MDI、ADX、ADXR
pdi = dmi['PDI']
mdi = dmi['MDI']
adx = dmi['ADX']
adxr = dmi['ADXR']
print(pdi.tail(5))
print(mdi.tail(5))
```

##### TRIX 三重指数平滑移动平均
```python
# 计算TRIX指标
trix = TI.TRIX(close)

# 获取TRIX和MATRIX
trix_line = trix['TRIX']
matrix_line = trix['MATRIX']
print(trix_line.tail(5))
```

##### CHO 佳庆指标
```python
# 计算CHO指标 (需要成交量)
cho = TI.CHO(close, high, low, volume)

# 获取CHO和MACHO
cho_line = cho['CHO']
macho_line = cho['MACHO']
print(cho_line.tail(5))
```

#### 案例三: 能量型指标
##### CR 能量指标
```python
# 计算CR指标
cr = TI.CR(close, high, low, n=26)

# 获取CR序列
cr_line = cr['CR']
print(cr_line.tail(5))
```

##### PSY 心理线
```python
# 计算PSY指标
psy = TI.PSY(close, n=12, m=6)

# 获取PSY和MAPSY
psy_line = psy['PSY']
mapsy_line = psy['MAPSY']
print(psy_line.tail(5))
```

##### WAD 威廉多空力度线
```python
# 计算WAD指标
wad = TI.WAD(close, high, low)

# 获取WAD和MAWAD
wad_line = wad['WAD']
mawad_line = wad['MAWAD']
print(wad_line.tail(5))
```

#### 案例四: 成交量型指标
##### OBV 能量潮
```python
# 计算OBV指标
obv = TI.OBV(close, volume)

# 获取OBV序列
obv_line = obv['OBV']
print(obv_line.tail(5))
```

##### VR 成交量变异率
```python
# 计算VR指标
vr = TI.VR(close, volume, n=26)

# 获取VR序列
vr_line = vr['VR']
print(vr_line.tail(5))
```

##### WVAD 威廉变异离散量
```python
# 计算WVAD指标
wvad = TI.WVAD(close, open_, high, low, volume)

# 获取WVAD和MAWVAD
wvad_line = wvad['WVAD']
mawvad_line = wvad['MAWVAD']
print(wvad_line.tail(5))
```

##### AMO 成交额均线
```python
# 计算AMO指标 (需要成交额数据)
amo = TI.AMO(amount)

# 获取不同周期的成交额均线
amo5 = amo['AMO5']
amo10 = amo['AMO10']
print(amo5.tail(5))
```

#### 案例五: 均线型指标
##### MA 移动平均线
```python
# 计算MA指标 (默认 5, 10, 20, 60日均线)
ma = TI.MA(close)

# 获取各周期均线
ma5 = ma['MA5']
ma10 = ma['MA10']
ma20 = ma['MA20']
ma60 = ma['MA60']
print(ma5.tail(5))
print(ma20.tail(5))

# 自定义周期
ma_custom = TI.MA(close, n1=3, n2=7, n3=14, n4=30)
```

##### EXPMA 指数平均线
```python
# 计算EXPMA指标
expma = TI.EXPMA(close)

# 获取指数均线
expma12 = expma['EXPMA12']
expma50 = expma['EXPMA50']
print(expma12.tail(5))
```

##### AMV 成本价均线
```python
# 计算AMV指标 (需要成交量和成交额)
amv = TI.AMV(volume, amount)

# 获取各周期成本价均线
amv5 = amv['AMV5']
amv13 = amv['AMV13']
amv34 = amv['AMV34']
print(amv5.tail(5))
```

#### 案例六: 路径型指标
##### BOLL 布林线
```python
# 计算BOLL指标
boll = TI.BOLL(close, n=20, k=2)

# 获取上轨、中轨、下轨
upper = boll['UPPER']
mid = boll['MID']
lower = boll['LOWER']
print(upper.tail(5))
print(mid.tail(5))
print(lower.tail(5))
```

##### PBX 瀑布线
```python
# 计算PBX指标
pbx = TI.PBX(close)

# 获取各条瀑布线
pbx4 = pbx['PBX4']
pbx9 = pbx['PBX9']
pbx18 = pbx['PBX18']
print(pbx4.tail(5))
```

##### BBIBOLL BBI多空布林线
```python
# 计算BBIBOLL指标
bbiboll = TI.BBIBOLL(close)

# 获取BBI中轨、上轨、下轨
bbi_mid = bbiboll['BBIBOLL']
bbi_upper = bbiboll['UPPER']
bbi_lower = bbiboll['LOWER']
print(bbi_mid.tail(5))
```

#### 案例七: 其他型指标
##### ATR 真实波幅均值
```python
# 计算ATR指标
atr = TI.ATR(close, high, low, n=14)

# 获取TR和ATR
tr_line = atr['TR']
atr_line = atr['ATR']
print(atr_line.tail(5))
```

##### SAR 抛物线转向指标
```python
# 计算SAR指标
sar = TI.SAR(close, high, low)

# 获取SAR序列
sar_line = sar['SAR']
print(sar_line.tail(5))

# 自定义参数
sar_custom = TI.SAR(close, high, low, n=4, step=0.02, max_af=0.2)
```

##### CDP 逆势操作
```python
# 计算CDP指标
cdp = TI.CDP(close, high, low)

# 获取五个价位
ah = cdp['AH']    # 最高值
nh = cdp['NH']    # 近高值
cdp_line = cdp['CDP']  # 均价
nl = cdp['NL']    # 近低值
al = cdp['AL']    # 最低值
print(cdp_line.tail(5))
```
