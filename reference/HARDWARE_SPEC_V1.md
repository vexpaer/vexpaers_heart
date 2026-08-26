# Holter V1 Hardware Specification

**项目名称**：Holter V1<br>
**用途**：研究/个人工程原型；连续 ECG + 运动数据记录<br>
**硬件 CAD**：KiCad<br>
**目标生产方式**：PCB 打样 + SMT 贴片，拿到板后通过 SWD/USB 烧录固件<br>
**版本**：V1.0<br>
**状态**：规格冻结；Heart V2 Rev A 制造发布候选已完成 ERC/DRC 签核（2026-08-26）

> 2026-08-23 实施修订：原规格中的 `STM32WB55CGU6 / UFQFPN48` 无法同时提供两组完整、独立的 SPI 引脚。V1 已改为 `STM32WB55RGV6 / VFQFPN68`，ADS1294R 使用 SPI1，microSD 使用 SPI2。本修订属于修复引脚资源冲突，不改变 1 MB Flash、BLE 或 USB FS 功能目标。

> 2026-08-26 机械实施修订：经用户授权，最终 PCB 在原 100 × 30 mm 上限基础上仅向北侧增加 2 mm 服务触点带，成品外形为 **100 × 32 mm**。新增面积用于分离 USB/SWD Pogo 排，不改变 ECG、microSD 或天线端的功能分区；外壳和夹具以最终板框为准。

---

## 1. V1 核心目标

设计一块可放入薄型金属盒中的低功耗可穿戴 ECG 记录主板：

- PCB 最终外形：**32 mm × 100 mm**（含 2 mm 服务触点带）
- PCB 建议厚度：**0.8 mm，4 层**
- 主板总高度目标：**≤ 3 mm**（不计外部电池、导联线、电极）
- 外壳内部高度目标：约 **5 mm**
- 尽量采用**单面贴装**：所有主要器件放在 PCB 同一面，背面尽量只保留测试点、Pogo 接触区和必要铜面
- 5 个体表电极，一根总线从设备引出后分成 5 根电极线
- 连续记录 ECG 和 IMU
- 本地 microSD 存储
- BLE 用于配置、状态、时间同步和短时实时预览
- USB 2.0 Full-Speed 通过 4 个 Pogo 触点进行数据导出和正常固件升级
- 电池可手动更换，主板**不包含充电电路**

> 本项目是研究/工程原型，不作为医疗诊断设备使用。

---

## 2. 已冻结的核心器件

### 2.1 ECG AFE

**TI ADS1294R**

要求：

- 4 通道
- 24-bit 同步 ADC
- SPI 接口
- 默认采样率：**500 SPS**
- CH1~CH3 用于 ECG
- CH4 预留为备用生物电通道
- 使用 ADS1294R 内置：
  - RLD（Right Leg Drive）
  - Lead-off detection
  - Wilson Central Terminal（WCT）
  - 内部参考/时钟方案按 TI datasheet 与官方参考设计实现
- V1 暂不要求启用呼吸阻抗功能，但不得破坏以后启用的可能性

封装优先：
- **NFBGA 8 mm × 8 mm**，以降低面积和高度
- 如果 SMT 厂 BGA 能力/成本不合适，再评估其他可采购封装；任何封装变更必须记录在设计说明中

### 2.2 主控 MCU

**ST STM32WB55RGV6**

要求：

- VFQFPN68，约 **8 × 8 × 1 mm**
- BLE
- USB 2.0 Full-Speed Device
- 1 MB Flash
- MCU 同时负责：
  - ADS1294R SPI 采集
  - microSD SPI 写入
  - IMU 采集
  - BLE
  - USB 数据导出
  - RTC/时间管理
  - 电池电压检测
  - Lead-off 状态处理
- 固定总线分配：
  - SPI1：ADS1294R（PA5/PA6/PA7，PA4 片选）
  - SPI2：microSD（PB13/PB14/PB15；PA10 作为软件控制片选）
  - I²C1：BMI270（PB8/PB9）

### 2.3 IMU

**Bosch BMI270**

要求：

- 6 轴 IMU：3 轴加速度 + 3 轴陀螺仪
- I²C 或 SPI；V1 优先 I²C，以节省 SPI 片选和布线复杂度
- 默认记录频率：**50 Hz**
- 后续固件允许降到 25 Hz
- 用途：活动、姿态变化、运动伪迹辅助判断

### 2.4 存储

**32 GB microSD / microSDHC**

要求：

- **只使用 microSD，不预留 SPI NAND**
- MCU 通过 **SPI 模式**访问 microSD
- 采用超薄、水平侧插卡座
- microSD 与 PCB **平行**
- 卡从外壳侧面/端部沿 PCB 平面滑入
- 卡座总高度优先 **≤ 1.5 mm**
- 优先 push-push 或可靠 push-pull 结构
- 卡槽建议布置在 PCB 的一个短边，外壳对应位置开 microSD 插入口
- 插卡状态检测如卡座支持则接入 MCU

建议文件系统：
- 32 GB：FAT32
- 固件必须使用顺序追加写入，避免大量随机写
- 建议使用 RAM buffer 后按较大 block 写入 microSD，降低功耗和掉电损坏风险

---

## 3. 电极与 ECG 通道定义

### 3.1 五电极

一根总导联线从主机引出，再分成：

1. **RA**
2. **LA**
3. **LL**
4. **RL**
5. **V5**

长期佩戴时可使用躯干化的 Holter 电极布置，而不是四肢末端位置。

建议人体位置：

- RA：右上胸
- LA：左上胸
- LL：左下胸/左下躯干
- RL：右下胸/右下躯干
- V5：左侧 V5 区域（与 V4 同水平、接近左前腋线）

注意：这种长期佩戴布置属于 Holter/监护式躯干电极布置，所得肢体导联形态不能假定与标准静息 12 导联四肢末端放置完全一致。

### 3.2 采集通道

目标：

- **CH1：Lead I = LA - RA**
- **CH2：Lead II = LL - RA**
- **CH3：V5 - WCT**
- **CH4：备用**

其中：

- WCT 由 RA、LA、LL 形成 Wilson Central Terminal
- CH3 必须依据 ADS1294R 的 WCT 推荐电路/寄存器实现，不要把 V5 简单接成 V5-RA

软件可由 CH1、CH2 计算：

- Lead III = Lead II - Lead I
- aVR = -(Lead I + Lead II) / 2
- aVL = Lead I - Lead II / 2
- aVF = Lead II - Lead I / 2

因此 V1 可输出：

- I
- II
- III
- aVR
- aVL
- aVF
- V5

其中前 6 个肢体方向只有 2 个独立自由度；V5 是额外真实胸导联信息。

---

## 4. ECG 输入与人体安全要求

这一部分优先级高于尺寸和 BOM 成本。

### 4.1 原则

- 输入保护、RLD、RC/EMI 网络优先参考 TI ADS129x 官方 ECG 参考设计和 datasheet
- 禁止由 Agent 自行“猜”患者输入保护电路
- 输入保护器件必须关注：
  - 漏电流
  - 输入偏置影响
  - ESD
  - RF/EMI
  - 限流
  - 电极断开状态
- 输入走线尽可能短、对称，远离：
  - USB
  - microSD 时钟
  - MCU 高频时钟
  - BLE RF
  - DC/DC 开关节点

### 4.2 USB 使用安全

**佩戴电极时，不允许连接电脑 USB/Pogo。**

V1 没有医疗级 USB 隔离，因此：

- USB 数据导出/刷机前先拔掉 5 电极导联总线
- Pogo VBUS 不得给锂电池充电
- USB 供电路径与电池路径需要避免反灌
- PCB 上明确丝印/说明：
  - `DISCONNECT ELECTRODES BEFORE USB`

### 4.3 RLD

- RL 电极作为 RLD/偏置驱动电极使用
- RLD 回路必须按照 ADS1294R datasheet 与官方 ECG 参考设计实现
- RLD 稳定性网络必须计算并在原理图中标注设计依据

---

## 5. 电源架构

### 5.1 电池

- 单节 **3.7 V 1000 mAh LiPo**
- 可拆卸
- 用户准备两块电池轮换
- 目标换电周期：约每 **12 小时**
- 主板**不集成充电器**

要求使用带自身保护的电池包，主板额外提供：

- 反接/反灌保护
- 过流保护或合适的保险/限流方案
- 欠压检测
- 电池电压 ADC 采样

### 5.2 电池连接器

- 2-pin
- 低高度
- 侧插
- 带防呆/锁定优先
- 高度目标 ≤ 2 mm 左右
- 最终型号根据 SMT 厂可采购库存决定，但不得使用明显超过 3 mm 的高连接器

### 5.3 电源轨

设计目标：

- 模拟和数字区域分区供电、布局隔离
- 不为了省一个 LDO 而让 microSD/MCU 的数字噪声直接污染 ECG AFE
- 优先评估：
  - `3.0 V_A`：ADS1294R 模拟
  - `3.0 V_D`：STM32WB / ADS1294R DVDD / IMU / microSD
  - `3.3 V_USB`：仅由 USB VBUS 产生，专供 STM32 VDDUSB
- 低噪声 LDO 优先
- 如果必须使用开关电源，开关节点必须远离 AFE，并经过低噪声后级处理；V1 尽量避免不必要的 DC/DC

电池最低工作电压、LDO dropout、STM32 USB VDDUSB 要结合 datasheet 重新核算后冻结。

---

## 6. 换电与 RTC

V1 允许换电时产生几秒钟 ECG 中断，不做真正的无缝热插拔。

要求：

- STM32 RTC 用于绝对时间
- 增加低高度 RTC/backup hold-up 电容
- 目标：拔电池后至少保持 RTC/关键状态 **≥ 60 秒**
- 换电后：
  - 自动重新初始化 ADS1294R、IMU、microSD
  - 建立新 recording segment
  - 在日志中写入 battery swap / reboot 事件
- 如果 RTC hold-up 失效：
  - BLE 或 USB 重新同步时间
  - 禁止悄悄生成错误绝对时间

---

## 7. BLE

用途限定为：

- 配置
- 时间同步
- 电池状态
- microSD 容量
- 电极 lead-off 状态
- 开始/停止记录
- 短时间实时 ECG 预览
- 固件状态/版本信息

BLE **不作为每天数百 MB 数据的主要导出通道**。

### 金属外壳注意

铁盒会显著衰减 2.4 GHz BLE。

PCB 必须：

- 给天线留完整 RF keepout
- 天线尽量位于 PCB 边缘
- 天线位置对应外壳塑料窗口/开口，或接受“开盖后使用 BLE”
- 不允许把 PCB 天线完全压在连续金属盒壁下仍假定 BLE 正常

V1 建议预留匹配网络，使用低高度 2.4 GHz 芯片天线或经验证的 PCB 天线方案。

---

## 8. USB + Pogo 数据接口

### 8.1 外露触点

主机不安装 USB-C 母座。

PCB 上留 4 个镀金平面触点：

1. VBUS
2. D-
3. D+
4. GND

由外部 Pogo Pin 底座连接：

`Holter PCB pads -> Pogo fixture -> USB-C cable -> PC`

建议：

- 触点采用 ENIG
- 2.0~2.54 mm 级别间距，优先便于手工夹具制作
- 触点周围留机械定位空间
- D+/D- 作为 USB 差分对布线
- 加低电容 USB ESD 保护
- VBUS 仅用于 USB 检测/受控供电，不用于电池充电

### 8.2 USB 功能

STM32WB55 使用 USB 2.0 Full-Speed Device。

固件目标支持：

- DFU/Bootloader 固件升级
- 数据导出
- 优先考虑 USB Mass Storage 或自定义 bulk protocol

重要性能预期：

- USB Full-Speed 理论总线速率 12 Mbit/s
- 实际文件导出不会达到 10 MB/s
- 预期有效吞吐约数百 KB/s ~ 1 MB/s 级，需实测优化
- 约 450~500 MB/天的数据，Pogo USB 导出大约是**数分钟到十几分钟级**

如希望几十秒导完，可以直接拔出 microSD 用高速读卡器。

---

## 9. SWD 调试/救砖接口

除 USB Pogo 外，必须保留独立隐藏 SWD 测试点。

至少：

- 3V3
- GND
- SWDIO
- SWCLK
- NRST

要求：

- 不焊排针
- 仅做金属测试 pad
- 可用 Pogo/夹具连接 ST-LINK
- 保证即使 USB Bootloader 损坏仍可重新烧录
- 在 PCB 丝印/装配图中明确 pin definition

---

## 10. ECG 导联总接口

使用**一个低高度多芯接口**连接主机和五电极分线。

目标：

- 5-position 锁定连接器
- RA / LA / LL / RL / V5
- 一根主线从设备出去后，再在远端分成 5 根电极线
- 接口优先放在靠近 ADS1294R 的 PCB 短边
- 连接器高度尽量 ≤ 2 mm
- 具有防呆
- 具备足够插拔寿命

V1 固定使用 6-position 低高度防呆连接器；第 6 pin 定义为：
- spare / shield / cable detect
且不得随意连接人体参考。

---

## 11. PCB 机械与布局

### 11.1 外形

- 最终：32 × 100 mm（含 2 mm 服务触点带）
- 优先做成长条圆角矩形
- PCB：4 层
- 厚度：0.8 mm
- 表面处理：ENIG 优先
- SMT：优先单面装配

### 11.2 推荐功能分区

从一端到另一端：

`ECG connector -> patient protection -> ADS1294R analog zone -> STM32WB digital zone -> microSD / USB zone`

IMU：
- 放在机械上相对稳定的位置
- 避免紧贴 Pogo 接触点和容易被手指按压变形的位置

RF：
- 放在 PCB 边缘
- 远离 ADS1294R 输入端
- 保留天线 keepout

### 11.3 microSD

microSD 放在远离 ECG 模拟输入的一端。

方向：

- 卡片平面与 PCB 平行
- 沿 PCB 长度方向或短边方向水平滑入
- 外壳开槽只需暴露卡的插拔边缘
- 禁止使用垂直插卡座

### 11.4 地与分区

- 使用连续、低阻抗 ground plane
- 通过器件布局实现 analog/digital/RF 分区
- 不要随意把地平面切成多个导致回流绕路的孤立区域
- ECG 输入下方/附近的回流路径、guard、shield 策略必须依据 ADS1294R 参考设计评估

---

## 12. 数据率与存储预算

### ECG

3 个实际 ECG 通道：

- 500 samples/s
- 24 bit = 3 bytes/sample

纯 ECG：

`3 × 500 × 3 × 86400 = 388,800,000 bytes/day`

约 **389 MB/day**（十进制）。

### IMU

若 6 轴全部保存为 16-bit：

- 12 bytes/sample
- 50 Hz

约：

`12 × 50 × 86400 = 51,840,000 bytes/day`

约 **52 MB/day**。

### 总预算

加上：

- block timestamp
- sample counter
- lead-off / event log
- header
- CRC
- 文件系统开销

V1 按 **450~500 MB/day** 规划。

32 GB microSD：

- 理论可保存 60 天以上
- 工程上按**至少 50 天连续数据容量**设计即可

不要给每个 ECG sample 写完整 64-bit timestamp；采用 block timestamp + sample index，降低冗余。

---

## 13. 数据文件原则

固件阶段再详细定义，但硬件/软件接口需预留以下字段：

文件头：

- magic
- file format version
- device serial
- firmware version
- recording start UTC/local time
- ECG sampling rate
- enabled channels
- gain
- electrode configuration
- IMU rate
- calibration information

数据 block：

- block sequence
- block timestamp
- ECG samples CH1/CH2/CH3
- IMU samples
- status / lead-off flags
- CRC

原则：

- microSD 必须保存尽量接近 ADC 原始值的数据
- 不允许只保存经过显示滤波后的 ECG
- 软件滤波可在导出后完成
- 掉电后应尽可能恢复到最后一个完整 block

---

## 14. V1 生产输出要求

KiCad 工程完成后，必须产生：

### 工程文件

- `.kicad_pro`
- `.kicad_sch`
- `.kicad_pcb`

### 检查

- ERC 无未解释严重错误
- DRC 无未解释严重错误
- 所有未连接 pin 有明确理由
- polarity/orientation 检查
- BGA/QFN exposed pad 检查
- microSD 卡插入方向检查
- 天线 keepout 检查
- Pogo pinout 二次检查
- SWD pinout 二次检查

### 生产文件

- Gerber
- Drill
- BOM
- Pick & Place / CPL
- 装配图
- 原理图 PDF
- PCB 3D 截图
- `production.zip`

BOM 应包含：

- Manufacturer
- Manufacturer Part Number
- Value
- Package
- Quantity
- Reference
- 可选的 JLC/LCSC part number

---

## 15. Codex 执行要求

Codex 接到本文件后按以下阶段工作。

### Phase 1 — 器件与参考设计核验

1. 阅读最新版：
   - ADS1294R datasheet
   - ADS129x ECG 官方参考设计/应用资料
   - STM32WB55RG datasheet
   - STM32WB hardware design guidelines
   - BMI270 datasheet
2. 核验所有电压、USB pin、RF、SPI、WCT、RLD、lead-off 配置。
3. 为所有关键器件确认 KiCad symbol/footprint。
4. 建立 `DECISIONS.md`，记录所有实际料号和设计选择。
5. **有任何 datasheet 冲突时，以 datasheet 为准，不照抄本规格里的假设值。**

### Phase 2 — 原理图

模块化建立：

- BATTERY / POWER
- STM32WB55
- BLE RF
- USB POGO
- SWD
- ADS1294R POWER/REFERENCE
- ECG INPUT PROTECTION
- RLD/WCT
- IMU
- MICROSD
- CONNECTORS

完成 ERC 后再进入 PCB。

### Phase 3 — PCB

1. 建立 32 × 100 mm 最终 board outline（含 2 mm 服务触点带）。
2. 先完成机械关键项：
   - ECG connector
   - microSD slot
   - Pogo pads
   - antenna/keepout
3. 再放 ADS1294R 和 patient protection。
4. 再放 MCU/IMU/SD/电源。
5. 优先单面 SMT。
6. 完成 4-layer stackup。
7. 做 DRC。
8. 检查器件实际高度，输出 `HEIGHT_BUDGET.md`。

### Phase 4 — 对抗式审查

至少进行一轮独立审查，重点寻找：

- ECG 输入错误
- WCT/RLD 接法错误
- 电源域错误
- USB VBUS/反灌
- microSD 热插拔/电源问题
- RF 天线被金属外壳屏蔽
- SPI pin 冲突
- SWD 被占用
- 未处理 BOOT/NRST
- 换电 RTC 丢失
- ESD 漏电污染 ECG
- 0402/0201 可制造性
- BGA escape routing
- 生产厂无法贴装的料号
- 高度超过目标

### Phase 5 — 生产包

最终目录建议：

```text
holter/
├── HARDWARE_SPEC_V1.md
├── DECISIONS.md
├── hardware/
│   ├── holter.kicad_pro
│   ├── holter.kicad_sch
│   └── holter.kicad_pcb
├── datasheets/
├── docs/
│   ├── schematic.pdf
│   ├── assembly.pdf
│   ├── HEIGHT_BUDGET.md
│   └── bringup_checklist.md
├── production/
│   ├── gerber/
│   ├── drill/
│   ├── bom.csv
│   ├── cpl.csv
│   └── production.zip
└── firmware/
```

---

## 16. 第一块板上电原则

SMT 板回来后不要直接贴到人体。

Bring-up 顺序：

1. 目检和显微检查
2. 不装电池，检查各电源 rail 对地阻抗
3. 实验室限流电源供电
4. 测试 3.0V/各 rail
5. SWD 识别 STM32WB
6. 烧最小测试固件
7. 测试 USB Pogo
8. 测试 BLE
9. 测试 microSD
10. 测试 IMU
11. ADS1294R internal test signal
12. 外部函数发生器/ECG simulator 输入
13. 检查 RLD/WCT/lead-off
14. 检查噪声、工频、基线漂移
15. **确认 USB 完全断开后**，才进入人体电极实验

V1 不做医疗认证，不得把“能看到 ECG”视为已经满足临床安全或诊断要求。

---

## 17. 当前冻结决策摘要

| 项目 | V1 |
|---|---|
| MCU | STM32WB55RGV6 / VFQFPN68 |
| ECG AFE | ADS1294R |
| ECG 实际通道 | 3 |
| 备用通道 | 1 |
| 电极 | RA / LA / LL / RL / V5 |
| ECG 采样 | 500 SPS / 24 bit |
| IMU | BMI270 / 50 Hz |
| 存储 | 32 GB microSD |
| microSD 方向 | 与 PCB 平行、水平侧插 |
| SPI NAND | 不使用、不预留 |
| BLE | 配置/预览 |
| 高速导出 | USB FS via 4 Pogo pads |
| Pogo | VBUS / D- / D+ / GND |
| 调试 | 独立隐藏 SWD pads |
| 电池 | 3.7V 1000mAh 可更换 |
| 充电 | 主板无充电功能 |
| 导联接口 | Molex Pico-EZmate 6-pin；RA/LA/LL/RL/V5 + shield/detect |
| PCB | 32×100 mm，0.8 mm 4-layer |
| 总板高目标 | ≤3 mm |
| 外壳内部高度目标 | 约5 mm |
| 数据预算 | 约450~500 MB/day |
| USB 与人体 | 禁止同时连接 |
| 制造目标 | JLCPCB Standard PCBA；首批 5 套；ENIG；单面 SMT |
| 外壳 | 金属主体 + 天线端塑料 RF 窗/端盖，闭盖 BLE |
| 人机界面 | 无按键、自动记录、单颗状态 LED |
| USB 夹具 | 独立 USB-C-to-Pogo 小板；与 ECG 插头机械互锁 |
