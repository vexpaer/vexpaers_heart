# PCB_WORKFLOW

## Start command

对 Codex 只需要说：

**按 `PCB_WORKFLOW.md` 从头到尾完成新版 PCB。使用项目里的 heart-pcb skill；自行做合理工程判断并继续，只有缺少无法推导的外部尺寸/器件信息时才停下来问我。**

## 1. Setup

先读 `.agents/skills/heart-pcb/SKILL.md`、`reference/HARDWARE_SPEC_V1.md` 和 `reference/DECISIONS.md`。

确认 KiCad 10 / `kicad-cli` 可用。若没有 `kicad-tool`，安装：

```bash
sudo apt install -y pipx
pipx ensurepath
pipx install "git+https://github.com/mash/kicad-skills.git"
```

用 `kicad-tool` 做查询、render、ERC/DRC/validate；需要实际放置和布线时使用 KiCad 自带 Python/`pcbnew` API。不要直接靠字符串批量改 KiCad 文件。

## 2. Start clean

从 `reference/kicad/` 复制原理图、project、symbol/footprint libraries 到 `hardware/heart_v2/`，建立新的 PCB 文件。

**不要复制或继续修改 `Old/**/.kicad_pcb` 的 tracks/vias，也不要把旧 Freerouting 结果当布局起点。** 旧版只用于查电气连接、器件选择或机械事实。

先确保 schematic/ERC 没有明显问题，再从零做 placement。

## 3. Placement first

按功能块摆：ECG 接口/保护/ADS1294R → 电源 → STM32/时钟 → microSD/USB → RF/天线。连接紧密的器件靠近，去耦贴引脚，器件方向尽量统一；让关键网络天然短，而不是靠后面绕线补救。

L2 保持连续 GND reference。天线端远离 ECG 输入并保留 keepout。先把 RF、晶振、SMPS、ECG 模拟区布局定好，再处理普通数字器件。

## 4. Human-style routing

**禁止 Freerouting 或任何全局自动布线作为最终 PCB。**

按优先级手工式布线：RF → HSE/LSE/SMPS → ECG/RLD/WCT → USB D+/D- → microSD → 电源 → 普通 GPIO。

目标是“一眼像熟练工程师画的板”：
- 走线短、直接，以 45° 为主；同组总线平行、间距一致、扇出规律。
- 能同层就同层；没有必要就不换层、不打 via、不绕蛇形、不随机折返。
- 电源线按电流加宽；普通信号不要为了逃线到处压 0.10 mm。
- USB 成对走、尽量等长且少换层；RF feed 尽量极短、无 via、连续地参考；ECG 输入四路保持对称并远离数字/RF。
- 发现某根线必须大绕路时，优先重新移动器件，而不是接受难看的走线。

每完成一个关键区域就 render 看图；如果视觉上像自动路由的 spaghetti，就重摆/重走。不要仅以 DRC=0 判断完成。

## 5. Finish

补 GND zones、必要 stitching vias 和整洁丝印；再次 render 全板正反面检查元件方向、线束、过孔、回流路径和机械边界。

最终至少做到：
- ERC 0 error，DRC 0 violation，0 unconnected pads。
- RF/USB/SD/ECG 关键网络经过视觉检查和长度/via 检查。
- 输出最终 KiCad 源文件、Gerber/drill、BOM/CPL、装配/铜层 PDF 和简短 audit。

完成后直接汇报最终文件、关键指标和仍需首板实测的项目。不要为了“更保险”额外扩展几十个检查步骤。

> 这是研究原型。接人体前仍需先用 ECG simulator / patient-equivalent load 做电气与噪声验证。
