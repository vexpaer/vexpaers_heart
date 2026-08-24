#!/usr/bin/env python3
"""Generate the USB-C-to-pogo dock schematic, project library and source BOM."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from generate_hardware import (
    Design,
    Pin,
    add_two,
    fp_header,
    q,
    render_schematic,
    render_symbol_library,
    standard_symbol_types,
)


ROOT = Path(__file__).resolve().parents[1]
HW = ROOT / "hardware" / "usb_pogo_dock"
LIB = HW / "libraries"
PRETTY = LIB / "usb_pogo_dock.pretty"
DOCS = ROOT / "docs"


def build_design() -> Design:
    d = Design()
    standard_symbol_types(d)
    d.symbol_type(
        "USB_C_16", "J",
        [
            Pin("A1", "GND"), Pin("A4", "VBUS"), Pin("A5", "CC1"),
            Pin("A6", "D+"), Pin("A7", "D-"), Pin("A8", "SBU1"),
            Pin("A9", "VBUS"), Pin("A12", "GND"),
            Pin("B1", "GND", side="right"), Pin("B4", "VBUS", side="right"),
            Pin("B5", "CC2", side="right"), Pin("B6", "D+", side="right"),
            Pin("B7", "D-", side="right"), Pin("B8", "SBU2", side="right"),
            Pin("B9", "VBUS", side="right"), Pin("B12", "GND", side="right"),
            Pin("SH", "SHIELD", side="bottom"),
        ],
        "USB 2.0 Type-C receptacle configured as a 5 V sink", width=25.4,
    )
    d.symbol_type(
        "POGO4", "J",
        [Pin("1", "VBUS", side="right"), Pin("2", "D-", side="right"),
         Pin("3", "D+", side="right"), Pin("4", "GND", side="right")],
        "Four spring-contact pins aligned to the recorder's bottom pads", width=15.24,
    )
    d.symbol_type(
        "USB_ESD", "U",
        [Pin("1", "D+"), Pin("2", "GND", "power_in"), Pin("3", "D-", side="right")],
        "Two-channel low-capacitance USB 2.0 ESD protection", width=10.16,
    )

    d.note(20, 18, "HOLTER V1 USB-C POGO DOCK", 3.0)
    d.note(20, 26, "FIXTURE ONLY — MECHANICAL INTERLOCK BLOCKS DOCKING WITH ECG HARNESS", 1.8)
    d.note(20, 38, "USB-C SINK / CC TERMINATION / ESD / CURRENT LIMIT", 2.0)
    d.note(165, 38, "POGO CONTACTS: VBUS / D- / D+ / GND", 2.0)

    usb_nets = {
        "A1": "GND", "A4": "VBUS_CONN", "A5": "CC1", "A6": "USB_DP",
        "A7": "USB_DM", "A8": None, "A9": "VBUS_CONN", "A12": "GND",
        "B1": "GND", "B4": "VBUS_CONN", "B5": "CC2", "B6": "USB_DP",
        "B7": "USB_DM", "B8": None, "B9": "VBUS_CONN", "B12": "GND",
        "SH": "USB_SHIELD",
    }
    d.add(
        "J1", "USB-C USB2.0", "USB_C_16",
        "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", usb_nets, 65, 115,
        manufacturer="Korean Hroparts Elec", mpn="TYPE-C-31-M-12",
        datasheet="http://www.krhro.com/uploads/soft/180320/1-1P320120243.pdf",
        description="16-contact horizontal USB Type-C receptacle",
    )
    add_two(d, "R1", "5.1k 1%", "R", "CC1", "GND", 115, 75,
            manufacturer="Yageo", mpn="RC0402FR-075K1L")
    add_two(d, "R2", "5.1k 1%", "R", "CC2", "GND", 115, 95,
            manufacturer="Yageo", mpn="RC0402FR-075K1L")
    add_two(d, "D1", "PESD5V0U1UL", "D_BIDIR", "VBUS_CONN", "GND", 115, 125,
            manufacturer="Nexperia", mpn="PESD5V0U1UL,315",
            description="Connector-side VBUS ESD suppressor")
    add_two(d, "F1", "0.50A PTC", "FUSE", "VBUS_CONN", "VBUS_POGO", 150, 125,
            manufacturer="Bourns", mpn="MF-FSMF050X-2")
    d.add(
        "U1", "TPD2EUSB30DRTR", "USB_ESD", "Package_TO_SOT_SMD:SOT-23",
        {"1": "USB_DP", "2": "GND", "3": "USB_DM"}, 145, 85,
        manufacturer="Texas Instruments", mpn="TPD2EUSB30DRTR",
        datasheet="https://www.ti.com/lit/ds/symlink/tpd2eusb30.pdf",
    )
    d.add(
        "J2", "4x spring pogo", "POGO4", "Dock:Pogo_Dock_4x1_P2.54_Top",
        ["VBUS_POGO", "USB_DM", "USB_DP", "GND"], 205, 100,
        manufacturer="Mill-Max", mpn="0906-series / hand fitted",
        description="Four replaceable spring pins in a keyed fixture",
    )
    add_two(d, "R3", "1M", "R", "USB_SHIELD", "GND", 115, 160,
            manufacturer="Yageo", mpn="RC0603FR-071ML",
            footprint="Resistor_SMD:R_0603_1608Metric")
    add_two(d, "C1", "1nF 1kV C0G", "C", "USB_SHIELD", "GND", 150, 160,
            manufacturer="KEMET", mpn="C1206C102JDGACTU",
            footprint="Capacitor_SMD:C_1206_3216Metric")
    add_two(d, "R4", "0R DNP", "R", "USB_SHIELD", "GND", 185, 160,
            manufacturer="Yageo", mpn="RC0603JR-070RL",
            footprint="Resistor_SMD:R_0603_1608Metric", dnp=True,
            description="Optional direct shield bond after EMC evaluation")
    add_two(d, "R5", "3.3k", "R", "VBUS_POGO", "DOCK_LED_A", 165, 190,
            manufacturer="Yageo", mpn="RC0402FR-073K3L")
    add_two(d, "D2", "Green 0603", "LED", "GND", "DOCK_LED_A", 205, 190,
            manufacturer="Lite-On", mpn="LTST-C190KGKT")

    # Explicit power-source declarations make the connector-fed rails clear
    # to ERC without inventing physical components.
    d.add("#FLG01", "PWR_FLAG", "PWR_FLAG", "", ["VBUS_CONN"], 92, 54,
          in_bom=False, on_board=False)
    d.add("#FLG02", "PWR_FLAG", "PWR_FLAG", "", ["GND"], 112, 54,
          in_bom=False, on_board=False)
    return d


def pogo_footprint() -> str:
    lines = fp_header(
        "Pogo_Dock_4x1_P2.54_Top",
        "Four 2.54-mm pitch through-hole spring contacts; VBUS, D-, D+, GND",
    )
    lines.extend(
        [
            '\t(fp_rect (start -5.1 -2.0) (end 5.1 2.0) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))',
            '\t(fp_rect (start -4.8 -1.7) (end 4.8 1.7) (stroke (width 0.1) (type solid)) (fill none) (layer "F.Fab"))',
            '\t(fp_line (start -4.8 -1.8) (end -3.9 -1.8) (stroke (width 0.15) (type solid)) (layer "F.SilkS"))',
        ]
    )
    for index in range(4):
        x = (index - 1.5) * 2.54
        shape = "rect" if index == 0 else "circle"
        lines.append(
            f'\t(pad {q(index + 1)} thru_hole {shape} (at {x:.3f} 0) '
            '(size 1.9 1.9) (drill 1.0) (layers "*.Cu" "*.Mask"))'
        )
    lines.extend(["\t(embedded_fonts no)", ")", ""])
    return "\n".join(lines)


def write_bom(d: Design) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    fields = ["Reference", "Quantity", "Value", "Manufacturer", "Manufacturer Part Number", "Footprint", "DNP", "Description"]
    with (DOCS / "dock_bom_source.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for c in (item for item in d.components if item.in_bom):
            writer.writerow({
                "Reference": c.ref, "Quantity": 1, "Value": c.value,
                "Manufacturer": c.manufacturer, "Manufacturer Part Number": c.mpn,
                "Footprint": c.footprint, "DNP": "DNP" if c.dnp else "",
                "Description": c.description,
            })


def write_files(d: Design) -> None:
    HW.mkdir(parents=True, exist_ok=True)
    LIB.mkdir(parents=True, exist_ok=True)
    PRETTY.mkdir(parents=True, exist_ok=True)
    schematic = render_schematic(
        d, project_name="usb_pogo_dock", title="Holter V1 USB-C Pogo Dock",
        paper="A4", date="2026-08-24", revision="1.0",
        comments=("Fixture mechanically blocks use with ECG harness", "USB-C sink; no battery charging path"),
        generator="usb_pogo_dock_generator",
    )
    (HW / "usb_pogo_dock.kicad_sch").write_text(schematic, encoding="utf-8")
    (LIB / "usb_pogo_dock.kicad_sym").write_text(render_symbol_library(d), encoding="utf-8")
    (PRETTY / "Pogo_Dock_4x1_P2.54_Top.kicad_mod").write_text(pogo_footprint(), encoding="utf-8")
    (HW / "sym-lib-table").write_text(
        '(sym_lib_table\n  (version 7)\n  (lib (name "Holter")(type "KiCad")(uri "${KIPRJMOD}/libraries/usb_pogo_dock.kicad_sym")(options "")(descr "Dock symbols"))\n)\n',
        encoding="utf-8",
    )
    (HW / "fp-lib-table").write_text(
        '(fp_lib_table\n  (version 7)\n  (lib (name "Dock")(type "KiCad")(uri "${KIPRJMOD}/libraries/usb_pogo_dock.pretty")(options "")(descr "Dock fixture footprints"))\n)\n',
        encoding="utf-8",
    )
    project_path = HW / "usb_pogo_dock.kicad_pro"
    existing_project: dict[str, object] = {}
    if project_path.exists():
        try:
            existing_project = json.loads(project_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing_project = {}
    board_settings = existing_project.get("board", {})

    project = {
        "board": board_settings, "boards": [], "cvpcb": {}, "erc": {}, "libraries": {},
        "meta": {"filename": "usb_pogo_dock.kicad_pro", "version": 3},
        "net_settings": {
            "classes": [
                {
                    "bus_width": 12, "clearance": 0.15, "diff_pair_gap": 0.25,
                    "diff_pair_via_gap": 0.25, "diff_pair_width": 0.2, "line_style": 0,
                    "microvia_diameter": 0.3, "microvia_drill": 0.1, "name": "Default",
                    "pcb_color": "rgba(0, 0, 0, 0.000)", "priority": 2147483647,
                    "schematic_color": "rgba(0, 0, 0, 0.000)", "track_width": 0.2,
                    "tuning_profile": "", "via_diameter": 0.6, "via_drill": 0.3,
                    "wire_width": 6,
                },
            ],
            "meta": {"version": 5}, "net_colors": None, "netclass_assignments": None,
            "netclass_patterns": [],
        },
        "pcbnew": {}, "schematic": {}, "sheets": [], "text_variables": {},
    }
    project_path.write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8")
    write_bom(d)


def main() -> None:
    design = build_design()
    write_files(design)
    print(f"Generated USB pogo dock: {len(design.components)} schematic components")


if __name__ == "__main__":
    main()
