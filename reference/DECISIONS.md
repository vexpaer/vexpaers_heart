# Holter V1 Implementation Decisions

**冻结日期**：2026-08-23
**决策人**：用户授权“全部按推荐方案”；以下内容作为 V1 原理图、PCB、BOM 和生产文件的统一依据。

## 1. 使用边界

- 仅用于研究和个人工程验证，不用于诊断、监护决策或临床用途。
- 主板没有患者侧隔离，也没有除颤防护。
- 人体电极连接时禁止连接 USB/Pogo；主板和夹具均标注 `DISCONNECT ELECTRODES BEFORE USB`。
- USB 夹具与 ECG 线缆插头采用机械互锁结构，使二者不能同时就位。

## 2. 制造与机械

| 项目 | 决策 |
|---|---|
| 厂商目标 | JLCPCB Standard PCBA |
| 首批数量 | 5 套主板 + 5 套 USB-Pogo 夹具板 |
| 主板 | 100.0 mm × 32.0 mm 圆角长板；北侧新增 2.0 mm 服务触点带 |
| 层叠 | 4 层，0.8 mm；L1 signal/components、L2 GND reference（两处已审计的局部 3V0_D 短桥）、L3 power/signal、L4 signal |
| 表面处理 | ENIG |
| 装配 | 主板主要器件全部在顶层；底层仅 Pogo/SWD 接触面、过孔和必要铜 |
| 外壳 | 金属主体；天线端使用塑料 RF 端盖/窗口，要求闭盖 BLE |
| 电池 | 带保护 1S 3.7 V、约 1000 mAh、低于 5 mm 厚；与主板同平面独立仓，不叠放 |

> 2026-08-26 布局实施例外：用户明确授权在确有必要时扩大板框。最终板仅向北侧
> 增加 2.0 mm（由 100 × 30 mm 改为 100 × 32 mm），用于把 USB 与 SWD Pogo
> 分成两条整齐、可标注的服务排；ECG、天线和卡座所在其余机械基准不变。外壳图
> 和夹具图必须以 100 × 32 mm 最终板框更新。

## 3. 已选关键器件

| 功能 | 制造商料号 | 封装/说明 |
|---|---|---|
| ECG AFE | TI `ADS1294RIZXGT` | NFBGA-64，8 × 8 mm，0.8 mm pitch |
| MCU | ST `STM32WB55RGV6` | VFQFPN68，8 × 8 mm；1 MB Flash |
| IMU | Bosch `BMI270` | LGA-14，3.0 × 2.5 mm |
| 电源选择 | TI `TPS2116DRLR` | SOT-5X3-8；USB 优先、反向电流阻断 |
| 3.0 V 数字 LDO | TI `TPS7A2130PDBVR` | 500 mA，SOT-23-5 |
| 3.0 V 模拟 LDO | TI `TPS7A2030PDBVR` | 300 mA，SOT-23-5 |
| 3.3 V USB LDO | TI `TPS7A2033PDBVR` | 300 mA，SOT-23-5；仅由 VBUS 供电 |
| microSD 负载开关 | TI `TPS22918DBVR` | SOT-23-6；软启动、快速放电 |
| BLE 匹配滤波器 | ST `MLPF-WB55-01E3` | 1.0 × 1.6 mm WLCSP，匹配 STM32WB55Cx/Rx |
| BLE 天线 | Johanson `2450AT18A100E` | 3.2 × 1.6 mm 芯片天线；量产前实机调匹配 |
| microSD 卡座 | Molex `104031-0811` | 水平 push-pull，1.42 mm，带检测 |
| ECG 板端 | Molex `78171-5006` | Pico-EZmate 6-pin，1.2 mm pitch |
| ECG 线端 | Molex `78172-5006` | 6-pin housing；RA/LA/LL/RL/V5/shield-detect |
| 电池板端 | Molex `78171-0002` | Pico-EZmate 2-pin |
| 电池线端 | Molex `78172-0002` | 2-pin housing |

如果 JLC 基础/扩展库没有关键 IC，则使用 JLC 全球代采或由客户预备料；不以“换成电气上不等价的库存料”换取贴装便利。

## 4. 接口与 MCU 引脚冻结

| 信号组 | STM32WB55RGV6 引脚 |
|---|---|
| ADS SPI1 | PA5=SCK、PA6=MISO、PA7=MOSI、PA4=CS |
| ADS 控制 | PB0=PWDN、PB1=RESET、PC0=START、PC1=DRDY |
| microSD SPI2 | PB13=SCK、PB14=MISO、PB15=MOSI；PA10=软件控制 CS |
| microSD | PC2=card detect、PC3=power enable |
| BMI270 I²C1 | PB8=SCL、PB9=SDA、PC4=INT1、PC5=INT2 |
| USB FS | PA11=D-、PA12=D+、PA9=VBUS sense |
| 调试 | PA13=SWDIO、PA14=SWCLK、NRST |
| 其他 | PA0=battery ADC、PB5=status LED、PH3=BOOT0 |

未列出的 GPIO 作为 DNP 测试点或明确 NC，不复用 SWD 引脚。

`SD_CS` 最初分配给 PB12，但该焊盘与 STM32 内部 SMPS/VDD 的必要短支路共用唯一
标准通孔扇出通道。为避免盘中孔、微孔或破坏 SMPS 回路，V1 将片选改到空闲的
PA10；PB12 明确 NC。片选本来就是普通 GPIO 功能，SPI2 的 SCK/MISO/MOSI 硬件
复用保持不变，固件只需将 SD 片选 GPIO 定义为 PA10。

## 5. ECG 通道与保护

- CH1 = LA − RA；CH2 = LL − RA；CH3 = V5 − WCT；CH4 在 V1 中配置内部短路并留测试点。
- RA、LA、LL、V5 每条患者输入采用两段串联限流电阻、低漏电钳位和 C0G EMI 电容；布局在 ECG 接口与 ADS1294R 之间，且保持对称。
- WCT 使用 ADS1294R 内部 WCT mux 组合 RA/LA/LL；WCT 输出仅驱动高阻 CH3N，并按数据手册建议对 AVSS 放置 100 pF。
- RLDOUT 与 RLDINV 之间采用 1 MΩ ∥ 1.5 nF 稳定网络；到 RL 电极使用两只串联 162 kΩ 限流电阻。
- 呼吸阻抗默认不装器件，但保留官方参考拓扑的焊盘。
- 保护网络用于低压、电池供电研究原型的 ESD/EMI/限流，不构成 IEC 60601 合规或除颤防护声明。

## 6. 电源、USB 与换电

- `TPS2116` 选择 USB VBUS 或受保护电池，USB 优先；不存在电池充电路径，也禁止 VBUS 反灌电池。
- `3V0_A` 与 `3V0_D` 分别稳压；STM32 的 `VDDUSB` 使用独立 `3V3_USB`，解决 3.0 V 电源对 USB 供电容差不足的问题。
- microSD 的电源由负载开关控制；所有 SD pull-up 接到开关后的 `3V0_SD`，避免断电反灌。
- RTC VBAT 使用肖特基隔离和低漏电 MLCC 储能，目标保持 60 秒以上；该目标需在首板实测并记录。
- USB/Pogo 顺序固定为 `VBUS / D- / D+ / GND`；另设 5-pad SWD：`3V0_D / GND / SWDIO / SWCLK / NRST`。

## 7. RF 与外壳

- 使用 32 MHz HSE 和 32.768 kHz LSE；STM32 内部 SMPS 网络按 ST AN5165 对应 STM32WB55RG 的推荐值和布局实现。
- RF1 经 `MLPF-WB55-01E3`、50 Ω 受控阻抗走线、可调 π 网络到 `2450AT18A100E`。
- 天线及其 keepout 位于 PCB 最远离 ECG 输入的短边，keepout 内各铜层禁铜，正对塑料 RF 端盖。
- 首板必须在最终外壳、电池和人体邻近条件下测量回波损耗；π 网络的量产值在该测试后冻结。

## 8. 操作默认值

- 无按键；插电池后自动自检、自动继续/新建 recording segment。
- 单颗低电流状态 LED 位于塑料 RF 端盖之后；正常记录时采用很低占空比，允许固件完全关闭。
- microSD 位于远离 ECG 的短边并由小盖板保护。
- BLE 仅用于配置、状态、同步和短时预览；大文件通过断开电极后的 USB 或拔卡导出。

## 9. 仍需由实物验证而非桌面假定的项目

- 芯片天线最终 π 匹配值和闭盖 BLE 范围。
- RLD 环路在人体模拟器/假负载下的稳定性和噪声。
- ECG 输入保护器件的实际漏电、偏置和恢复行为。
- RTC 断电保持时间、microSD 写入峰值和 USB 供电热升。
- 特定批次电池包的保护板阈值、连接器极性和外形公差。
