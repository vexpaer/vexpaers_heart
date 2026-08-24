---
name: heart-pcb
description: Rebuild vexpaer's heart PCB with clean, human-style placement and routing in KiCad.
---

# heart-pcb

Follow `PCB_WORKFLOW.md`. Treat `Old/` as archive only.

Core rule: **placement creates easy routing**. Never use Freerouting/global autorouting as the final layout and never copy old PCB tracks/vias into the new board.

Use `kicad-tool` for compact KiCad queries, renders, ERC/DRC and validation. Use KiCad Python/`pcbnew` for placement, tracks, vias, zones and board edits.

For layout:
- group functional blocks and place critical support parts at their pins;
- keep L2 a continuous GND reference;
- route RF/crystals/SMPS/ECG first, then USB/SD/power, then ordinary GPIO;
- prefer short 45° routes, consistent fanout, parallel buses, few vias and few layer changes;
- if a route becomes ugly, move parts and reroute instead of accepting spaghetti;
- keep USB paired, RF extremely short and via-free, ECG inputs symmetric and away from noisy digital/RF areas.

After each major area, render it and inspect the image. A board that passes DRC but looks machine-routed is not finished. Iterate until the whole board is visually orderly, then run final ERC/DRC and manufacturing exports.

Make reasonable engineering choices and keep working. Ask the user only when a genuinely missing external fact prevents progress.
