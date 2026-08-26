#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BOARD="${PROJECT_DIR}/heart_v2.kicad_pcb"
SCHEMATIC="${PROJECT_DIR}/heart_v2.kicad_sch"
DOCS="${PROJECT_DIR}/docs"
OUT="${PROJECT_DIR}/production"
GERBERS="${OUT}/gerbers"
OUT_DOCS="${OUT}/docs"
KICAD_CLI_BIN="${KICAD_CLI:-kicad-cli}"

mkdir -p "${DOCS}" "${GERBERS}" "${OUT_DOCS}"

"${KICAD_CLI_BIN}" sch erc --severity-all --exit-code-violations \
  --output "${DOCS}/erc_final.rpt" "${SCHEMATIC}"
"${KICAD_CLI_BIN}" pcb drc --refill-zones --save-board \
  --exit-code-violations --output "${DOCS}/drc_final.rpt" "${BOARD}"

"${KICAD_CLI_BIN}" pcb export gerbers --check-zones \
  --use-drill-file-origin \
  --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts \
  --output "${GERBERS}" "${BOARD}"
"${KICAD_CLI_BIN}" pcb export drill --format excellon --drill-origin plot \
  --excellon-units mm --excellon-separate-th --generate-map --map-format pdf \
  --generate-report --report-path "${GERBERS}/heart_v2_drill_report.rpt" \
  --output "${GERBERS}" "${BOARD}"
"${KICAD_CLI_BIN}" pcb export ipcd356 \
  --output "${GERBERS}/heart_v2.ipc" "${BOARD}"

FIELDS="Reference,Value,Footprint,Manufacturer,MPN,Datasheet,QUANTITY,DNP"
LABELS="References,Value,Footprint,Manufacturer,MPN,Datasheet,Quantity,DNP"
GROUP="Value,Footprint,Manufacturer,MPN,DNP"
"${KICAD_CLI_BIN}" sch export bom --fields "${FIELDS}" --labels "${LABELS}" \
  --group-by "${GROUP}" --exclude-dnp --output "${OUT}/heart_v2_bom.csv" \
  "${SCHEMATIC}"
"${KICAD_CLI_BIN}" sch export bom --fields "${FIELDS}" --labels "${LABELS}" \
  --group-by "${GROUP}" --output "${OUT}/heart_v2_bom_all.csv" "${SCHEMATIC}"
"${KICAD_CLI_BIN}" pcb export pos --side both --format csv --units mm \
  --use-drill-file-origin --smd-only --exclude-dnp \
  --output "${OUT}/heart_v2_cpl.csv" "${BOARD}"
"${KICAD_CLI_BIN}" pcb export stats --format report --units mm \
  --output "${OUT}/heart_v2_board_stats.rpt" "${BOARD}"

"${KICAD_CLI_BIN}" pcb export pdf --mode-single --check-zones \
  --black-and-white --scale 1 --layers F.Fab,F.Silkscreen,Edge.Cuts \
  --output "${OUT_DOCS}/heart_v2_assembly_top.pdf" "${BOARD}"
"${KICAD_CLI_BIN}" pcb export pdf --mode-single --check-zones \
  --black-and-white --scale 1 --mirror --layers B.Fab,B.Silkscreen,Edge.Cuts \
  --output "${OUT_DOCS}/heart_v2_assembly_bottom.pdf" "${BOARD}"
"${KICAD_CLI_BIN}" pcb export pdf --mode-multipage --check-zones \
  --black-and-white --scale 1 --layers F.Cu,In1.Cu,In2.Cu,B.Cu \
  --common-layers Edge.Cuts --output "${OUT_DOCS}/heart_v2_copper_layers.pdf" \
  "${BOARD}"
"${KICAD_CLI_BIN}" sch export pdf \
  --output "${OUT_DOCS}/heart_v2_schematic.pdf" "${SCHEMATIC}"
