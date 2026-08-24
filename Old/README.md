# vexpaer's heart — Holter V1

`vexpaer's heart` 是一套开源、可制造的研究型便携 ECG 记录器硬件。主板以
ADS1294R、STM32WB55 和 BMI270 为核心，记录 ECG 与运动数据到 microSD，
并提供 BLE 配置以及断开电极后使用的 USB-Pogo 数据接口。

本仓库包含：

- KiCad 10 主板与 USB-Pogo 底座的原理图、PCB 和项目库；
- 可重复生成设计源文件与生产资料的脚本；
- BOM、坐标文件、Gerber、钻孔文件和厂商上传压缩包；
- ERC/DRC 签核报告以及便于人工审阅的 PDF。

## 安全边界

这是研究/个人工程原型，不是医疗器械，不得用于诊断或临床决策。设计没有
医疗级患者隔离，也没有除颤防护。连接人体电极时严禁连接 USB/Pogo；进行
USB 数据导出或刷机前必须先拔下整条电极线缆。

首次接触人体前应先在 ECG 模拟器和假负载上验证输入漏电、RLD 稳定性、噪声、
电源故障和 ESD 恢复行为。实物还必须完成 RF 匹配、最终外壳内 BLE、热、
microSD 写入峰值以及电池极性/保护板验证。

## 目录

- `hardware/holter_v1/`：100 mm × 30 mm、4 层、0.8 mm 主板；
- `hardware/usb_pogo_dock/`：USB-C 转 4 针 Pogo 底座；
- `production/`：可直接交给 PCB/PCBA 厂商的输出和制造说明；
- `pdf/`：原理图、PCB 铜层和装配图 PDF；
- `docs/`：BOM 源数据、引脚审计与 ERC/DRC 报告；
- `tools/`：设计生成与发布导出脚本。

完整需求见 [HARDWARE_SPEC_V1.md](HARDWARE_SPEC_V1.md)，冻结的工程决策见
[DECISIONS.md](DECISIONS.md)。制造前请阅读 [production/README.md](production/README.md)
和 [docs/HARDWARE_AUDIT.md](docs/HARDWARE_AUDIT.md)。

## 重新生成和检查

需要 KiCad 10，并让 `kicad-cli` 位于 `PATH`；也可通过 `KICAD_CLI` 指定可执行文件。

```bash
# 原理图、项目库和 BOM 源数据
python3 tools/generate_hardware.py

# 从已提交的 Freerouting 中间板重复生成正式主板（用 KiCad 自带 Python）
/path/to/kicad-python tools/finish_main_routes.py \
  hardware/holter_v1/routing_source/holter_v1-freerouted-input.kicad_pcb \
  /tmp/holter_v1-rebuilt.kicad_pcb
cp hardware/holter_v1/holter_v1.kicad_pro /tmp/holter_v1-rebuilt.kicad_pro

# USB-Pogo 底座
python3 tools/generate_dock.py
python3 tools/generate_dock_board.py

# 主板几何/物料审计（同样用 KiCad 自带 Python）
/path/to/kicad-python tools/audit_hardware.py
# 或审计临时重建板：
/path/to/kicad-python tools/audit_hardware.py \
  --board /tmp/holter_v1-rebuilt.kicad_pcb \
  --output /tmp/holter_v1-rebuilt-audit.md

# ERC、DRC、PDF、Gerber、钻孔、BOM、CPL 和制造 ZIP
KICAD_CLI=/path/to/kicad-cli python3 tools/export_release.py
```

`generate_board.py` 只生成未布线的主板起点，不属于正式发布流程。仓库中已提交的
`hardware/holter_v1/holter_v1.kicad_pcb` 是正式签核布线版本；重建结果应先在
临时路径完成 ERC/DRC 和几何审计，再替换正式文件。

## 许可

硬件设计和随附文档以 CERN Open Hardware Licence Version 2 — Strongly Reciprocal
（CERN-OHL-S-2.0）发布。完整条款见 `LICENSE`。
