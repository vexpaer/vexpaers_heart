#!/usr/bin/env python3
"""Generate the deterministic KiCad sources for Holter V1.

The generated schematic deliberately embeds every symbol definition so it can be
opened on a clean KiCad 10 installation.  Run this script with ordinary Python;
PCB generation is kept in a separate script because it uses KiCad's pcbnew API.
"""

from __future__ import annotations

import csv
import json
import math
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
HW = ROOT / "hardware" / "holter_v1"
LIB = HW / "libraries"
PRETTY = LIB / "holter_v1.pretty"
DOCS = ROOT / "docs"

UUID_NS = uuid.UUID("a5ad17c2-0694-55d5-8bc1-97924848f49c")


def uid(key: str) -> str:
    return str(uuid.uuid5(UUID_NS, key))


def q(value: object) -> str:
    text = str(value)
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def fmt(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.4f}".rstrip("0").rstrip(".")


@dataclass(frozen=True)
class Pin:
    number: str
    name: str
    etype: str = "passive"
    side: str = "left"


@dataclass
class SymbolType:
    name: str
    reference: str
    pins: list[Pin]
    description: str
    width: float = 20.32
    pin_pitch: float = 2.54
    pin_xy: dict[str, tuple[float, float, str]] = field(default_factory=dict)

    def calculate_geometry(self) -> None:
        groups = {
            side: [pin for pin in self.pins if pin.side == side]
            for side in ("left", "right", "top", "bottom")
        }
        rows = max(len(groups["left"]), len(groups["right"]), 2)
        height = max(7.62, (rows + 1) * self.pin_pitch)
        x_body = self.width / 2
        y_top = -height / 2
        y_bottom = height / 2

        for side in ("left", "right"):
            pins = groups[side]
            for index, pin in enumerate(pins):
                y = (index - (len(pins) - 1) / 2) * self.pin_pitch
                if side == "left":
                    self.pin_xy[pin.number] = (-x_body - 2.54, y, side)
                else:
                    self.pin_xy[pin.number] = (x_body + 2.54, y, side)

        for side in ("top", "bottom"):
            pins = groups[side]
            for index, pin in enumerate(pins):
                x = (index - (len(pins) - 1) / 2) * self.pin_pitch
                if side == "top":
                    self.pin_xy[pin.number] = (x, y_top - 2.54, side)
                else:
                    self.pin_xy[pin.number] = (x, y_bottom + 2.54, side)

    @property
    def body_height(self) -> float:
        rows = max(
            len([p for p in self.pins if p.side == "left"]),
            len([p for p in self.pins if p.side == "right"]),
            2,
        )
        return max(7.62, (rows + 1) * self.pin_pitch)


@dataclass
class Component:
    ref: str
    value: str
    kind: str
    footprint: str
    nets: dict[str, str | None]
    x: float
    y: float
    manufacturer: str = ""
    mpn: str = ""
    datasheet: str = ""
    description: str = ""
    dnp: bool = False
    in_bom: bool = True
    on_board: bool = True
    fields: dict[str, str] = field(default_factory=dict)


class Design:
    def __init__(self) -> None:
        self.symbol_types: dict[str, SymbolType] = {}
        self.components: list[Component] = []
        self.notes: list[tuple[float, float, str, float]] = []

    def symbol_type(
        self,
        name: str,
        reference: str,
        pins: Iterable[Pin],
        description: str,
        width: float = 20.32,
    ) -> None:
        item = SymbolType(name, reference, list(pins), description, width)
        item.calculate_geometry()
        self.symbol_types[name] = item

    def add(
        self,
        ref: str,
        value: str,
        kind: str,
        footprint: str,
        nets: Iterable[str | None] | dict[str, str | None],
        x: float,
        y: float,
        *,
        manufacturer: str = "",
        mpn: str = "",
        datasheet: str = "",
        description: str = "",
        dnp: bool = False,
        in_bom: bool = True,
        on_board: bool = True,
        fields: dict[str, str] | None = None,
    ) -> None:
        pins = self.symbol_types[kind].pins
        if isinstance(nets, dict):
            netmap = dict(nets)
        else:
            values = list(nets)
            if len(values) != len(pins):
                raise ValueError(f"{ref}: got {len(values)} nets for {len(pins)} pins")
            netmap = {pin.number: net for pin, net in zip(pins, values)}
        unknown = set(netmap) - {pin.number for pin in pins}
        if unknown:
            raise ValueError(f"{ref}: unknown pins {sorted(unknown)}")
        for pin in pins:
            netmap.setdefault(pin.number, None)
        # KiCad's standard connection grid is 1.27 mm.  Keeping every symbol
        # origin on that grid also keeps all generated pin endpoints on-grid.
        x = round(x / 1.27) * 1.27
        y = round(y / 1.27) * 1.27
        self.components.append(
            Component(
                ref,
                value,
                kind,
                footprint,
                netmap,
                x,
                y,
                manufacturer,
                mpn,
                datasheet,
                description or self.symbol_types[kind].description,
                dnp,
                in_bom,
                on_board,
                fields or {},
            )
        )

    def note(self, x: float, y: float, text: str, size: float = 2.0) -> None:
        self.notes.append((x, y, text, size))


def standard_symbol_types(d: Design) -> None:
    d.symbol_type(
        "R", "R", [Pin("1", "1"), Pin("2", "2", side="right")],
        "Resistor", width=5.08,
    )
    d.symbol_type(
        "C", "C", [Pin("1", "1"), Pin("2", "2", side="right")],
        "Capacitor", width=5.08,
    )
    d.symbol_type(
        "D", "D", [Pin("1", "K"), Pin("2", "A", side="right")],
        "Diode", width=5.08,
    )
    d.symbol_type(
        "D_BIDIR", "D", [Pin("1", "1"), Pin("2", "2", side="right")],
        "Bidirectional low-leakage ESD suppressor", width=5.08,
    )
    d.symbol_type(
        "L", "L", [Pin("1", "1"), Pin("2", "2", side="right")],
        "Inductor or ferrite bead", width=5.08,
    )
    d.symbol_type(
        "FUSE", "F", [Pin("1", "1"), Pin("2", "2", side="right")],
        "Resettable fuse", width=5.08,
    )
    d.symbol_type(
        "LED", "D", [Pin("1", "K"), Pin("2", "A", side="right")],
        "Low-current status LED", width=5.08,
    )
    d.symbol_type(
        "XTAL4", "Y",
        [Pin("1", "X1"), Pin("2", "GND1", side="bottom"), Pin("3", "X2", side="right"), Pin("4", "GND2", side="top")],
        "Four-pad crystal", width=7.62,
    )
    d.symbol_type(
        "XTAL2", "Y", [Pin("1", "X1"), Pin("2", "X2", side="right")],
        "Two-pad crystal", width=7.62,
    )
    d.symbol_type(
        "PMOS", "Q",
        [Pin("1", "G"), Pin("2", "S", side="right"), Pin("3", "D", side="right")],
        "P-channel MOSFET", width=7.62,
    )
    d.symbol_type(
        "ANT", "AE", [Pin("1", "FEED"), Pin("2", "NC", side="right")],
        "2.4 GHz chip antenna; terminal 2 is mechanical NC", width=7.62,
    )
    d.symbol_type(
        "TP", "TP", [Pin("1", "1")], "Test point", width=5.08,
    )
    d.symbol_type(
        "PWR_FLAG", "#FLG", [Pin("1", "pwr", "power_out")],
        "ERC power-source declaration; no physical part", width=5.08,
    )


def ic_symbol_types(d: Design) -> None:
    d.symbol_type(
        "ECG_CONN", "J",
        [Pin(str(i), name, side="right") for i, name in enumerate(("RA", "LA", "LL", "RL", "V5", "SHIELD"), 1)],
        "Molex Pico-EZmate six-position ECG harness connector", width=12.7,
    )
    d.symbol_type(
        "BAT_CONN", "J", [Pin("1", "BAT+", side="right"), Pin("2", "GND", side="right")],
        "Protected 1S LiPo connector", width=10.16,
    )
    d.symbol_type(
        "POGO4", "J",
        [Pin("1", "VBUS", side="right"), Pin("2", "D-", side="right"), Pin("3", "D+", side="right"), Pin("4", "GND", side="right")],
        "Four-contact USB pogo interface", width=12.7,
    )
    d.symbol_type(
        "SWD5", "J",
        [Pin("1", "3V0_D", side="right"), Pin("2", "GND", side="right"), Pin("3", "SWDIO", side="right"), Pin("4", "SWCLK", side="right"), Pin("5", "NRST", side="right")],
        "Five-contact hidden SWD pogo interface", width=12.7,
    )

    ads_grid = {
        "H1": ("IN1P", "input"), "G1": ("IN2P", "input"), "F1": ("IN3P", "input"), "E1": ("IN4P", "input"),
        "D1": ("IN5P", "input"), "C1": ("IN6P", "input"), "B1": ("IN7P", "input"), "A1": ("IN8P", "input"),
        "H2": ("IN1N", "input"), "G2": ("IN2N", "input"), "F2": ("IN3N", "input"), "E2": ("IN4N", "input"),
        "D2": ("IN5N", "input"), "C2": ("IN6N", "input"), "B2": ("IN7N", "input"), "A2": ("IN8N", "input"),
        "H3": ("VREFP", "bidirectional"), "G3": ("VCAP4", "passive"), "F3": ("TESTN_PACE_OUT2", "bidirectional"),
        "E3": ("TESTP_PACE_OUT1", "bidirectional"), "D3": ("WCT", "output"), "C3": ("RLDINV", "bidirectional"),
        "B3": ("RLDOUT", "output"), "A3": ("RLDIN", "input"),
        "H4": ("VREFN", "input"), "G4": ("RESP_MODP", "output"), "F4": ("RESP_MODN", "output"),
        "E4": ("RESV1", "input"), "D4": ("AVSS", "power_in"), "C4": ("RLDREF", "input"),
        "B4": ("AVDD", "power_in"), "A4": ("AVDD", "power_in"),
        "H5": ("VCAP1", "passive"), "G5": ("PWDN", "input"), "F5": ("GPIO1", "bidirectional"),
        "E5": ("GPIO4", "bidirectional"), "D5": ("AVSS", "power_in"), "C5": ("AVSS", "power_in"),
        "B5": ("AVSS", "power_in"), "A5": ("AVSS", "power_in"),
        "H6": ("VCAP2", "passive"), "G6": ("RESET", "input"), "F6": ("DAISY_IN", "input"),
        "E6": ("GPIO3", "bidirectional"), "D6": ("DRDY", "output"), "C6": ("AVDD", "power_in"),
        "B6": ("AVDD", "power_in"), "A6": ("AVDD", "power_in"),
        "H7": ("DGND", "power_in"), "G7": ("START", "input"), "F7": ("CS", "input"),
        "E7": ("GPIO2", "bidirectional"), "D7": ("DGND", "power_in"), "C7": ("DGND", "power_in"),
        "B7": ("VCAP3", "passive"), "A7": ("AVDD1", "power_in"),
        "H8": ("DIN", "input"), "G8": ("CLK", "bidirectional"), "F8": ("SCLK", "input"),
        "E8": ("DOUT", "output"), "D8": ("DVDD", "power_in"), "C8": ("DVDD", "power_in"),
        "B8": ("CLKSEL", "input"), "A8": ("AVSS1", "power_in"),
    }
    ads_pins: list[Pin] = []
    ordered_balls = [f"{col}{row}" for row in range(1, 9) for col in "HGFEDCBA"]
    for index, ball in enumerate(ordered_balls):
        name, etype = ads_grid[ball]
        ads_pins.append(Pin(ball, name, etype, "left" if index < 32 else "right"))
    d.symbol_type(
        "ADS1294R", "U", ads_pins,
        "TI four-channel 24-bit ECG AFE with RLD, WCT and respiration support", width=30.48,
    )

    stm_names = {
        1:"VBAT",2:"PC13",3:"PC14-OSC32_IN",4:"PC15-OSC32_OUT",5:"PH3-BOOT0",6:"PB8",7:"PB9",8:"NRST",
        9:"PC0",10:"PC1",11:"PC2",12:"PC3",13:"VREF+",14:"VDDA",15:"PA0",16:"PA1",17:"PA2",18:"PA3",
        19:"PA4",20:"PA5",21:"PA6",22:"PA7",23:"PA8",24:"PA9",25:"PC4",26:"PC5",27:"PB2",28:"PB10",
        29:"PB11",30:"VDD",31:"RF1",32:"VSSRF",33:"VDDRF",34:"OSC_OUT",35:"OSC_IN",36:"AT0",37:"AT1",
        38:"PB0",39:"PB1",40:"PE4",41:"VFBSMPS",42:"VSSSMPS",43:"VLXSMPS",44:"VDDSMPS",45:"VDD",
        46:"PB12",47:"PB13",48:"PB14",49:"PB15",50:"PC6",51:"PA10",52:"PA11",53:"PA12",54:"PA13",
        55:"VDDUSB",56:"PA14",57:"PA15",58:"PC10",59:"PC11",60:"PC12",61:"PD0",62:"PD1",63:"PB3",
        64:"PB4",65:"PB5",66:"PB6",67:"PB7",68:"VDD",69:"VSS_EP",
    }
    power_names = {"VBAT", "VREF+", "VDDA", "VDD", "VSSRF", "VDDRF", "VSSSMPS", "VDDSMPS", "VDDUSB", "VSS_EP"}
    output_names = {"RF1", "OSC_OUT", "VLXSMPS"}
    stm_pins = []
    for number in range(1, 70):
        name = stm_names[number]
        etype = "power_in" if name in power_names else ("output" if name in output_names else "bidirectional")
        stm_pins.append(Pin(str(number), name, etype, "left" if number <= 35 else "right"))
    d.symbol_type(
        "STM32WB55RG", "U", stm_pins,
        "ST dual-core BLE/802.15.4 MCU, 1 MB Flash, USB FS", width=35.56,
    )

    d.symbol_type(
        "BMI270", "U",
        [
            Pin("1","SDO/ADDR","input"), Pin("2","ASDx","bidirectional"), Pin("3","ASCx","bidirectional"),
            Pin("4","INT1","bidirectional"), Pin("5","VDDIO","power_in"), Pin("6","GNDIO","power_in"), Pin("7","GND","power_in"),
            Pin("8","VDD","power_in","right"), Pin("9","INT2","bidirectional","right"), Pin("10","OCSB","input","right"),
            Pin("11","OSDO","output","right"), Pin("12","CSB","input","right"), Pin("13","SCx/SCL","input","right"),
            Pin("14","SDx/SDA","bidirectional","right"),
        ],
        "Bosch six-axis low-power IMU", width=20.32,
    )
    d.symbol_type(
        "TPS2116", "U",
        [Pin("1","GND","power_in"),Pin("2","VOUT","power_out"),Pin("3","VIN1","power_in"),Pin("4","PR1","input"),
         Pin("5","MODE","input","right"),Pin("6","VIN2","power_in","right"),Pin("7","VOUT","passive","right"),Pin("8","ST","open_collector","right")],
        "TI low-IQ two-input power mux with reverse-current blocking", width=17.78,
    )
    d.symbol_type(
        "LDO5", "U",
        [Pin("1","IN","power_in"),Pin("2","GND","power_in"),Pin("3","EN","input"),Pin("4","NC","no_connect","right"),Pin("5","OUT","power_out","right")],
        "Fixed-output low-noise LDO in SOT-23-5", width=15.24,
    )
    d.symbol_type(
        "LOADSW6", "U",
        [Pin("1","VIN","power_in"),Pin("2","GND","power_in"),Pin("3","CT","passive"),Pin("4","ON","input","right"),Pin("5","QOD","passive","right"),Pin("6","VOUT","power_out","right")],
        "TI controlled-rise-time load switch", width=15.24,
    )
    d.symbol_type(
        "USB_ESD", "U",
        [Pin("1","D+"),Pin("2","GND","power_in"),Pin("3","D-",side="right")],
        "Two-channel low-capacitance USB ESD protection", width=10.16,
    )
    d.symbol_type(
        "MLPF", "U",
        [Pin("A1","OUT"),Pin("A2","GND","power_in"),Pin("A3","IN","input"),Pin("B1","GND","power_in","right"),Pin("B2","GND","power_in","right"),Pin("B3","GND","power_in","right")],
        "ST integrated matching and low-pass filter for STM32WB55Cx/Rx", width=12.7,
    )
    sd_pins = [
        Pin("1","DAT2"),Pin("2","DAT3/CS"),Pin("3","CMD/DI"),Pin("4","VDD","power_in"),Pin("5","CLK","input"),
        Pin("6","VSS","power_in","right"),Pin("7","DAT0/DO","output","right"),Pin("8","DAT1",side="right"),
        Pin("9","DET_A",side="right"),Pin("10","DET_B",side="right"),Pin("SH","SHIELD","power_in","bottom"),
    ]
    d.symbol_type(
        "MICROSD", "J", sd_pins,
        "Molex 104031-0811 microSD push-pull connector with card detect", width=22.86,
    )


def footprint_for(kind: str) -> str:
    table = {
        "R": "Resistor_SMD:R_0402_1005Metric",
        "C": "Capacitor_SMD:C_0402_1005Metric",
        "D": "Diode_SMD:D_SOD-323",
        "D_BIDIR": "Diode_SMD:D_SOD-882",
        "L": "Inductor_SMD:L_0603_1608Metric",
        "FUSE": "Fuse:Fuse_0603_1608Metric",
        "LED": "LED_SMD:LED_0603_1608Metric",
        "XTAL4": "Crystal:Crystal_SMD_2016-4Pin_2.0x1.6mm",
        "PMOS": "Package_TO_SOT_SMD:SOT-23",
        "ANT": "RF_Antenna:Johanson_2450AT18x100_2400-2500Mhz",
        "TP": "TestPoint:TestPoint_Pad_D1.0mm",
    }
    return table[kind]


MURATA_CAP_MPN = {
    ("100n X7R", "Capacitor_SMD:C_0402_1005Metric"): "GRM155R71C104KA88D",
    ("1n X7R", "Capacitor_SMD:C_0402_1005Metric"): "GRM155R71H102KA01D",
    ("10p C0G", "Capacitor_SMD:C_0402_1005Metric"): "GRM1555C1H100JA01D",
    ("1u X7R", "Capacitor_SMD:C_0603_1608Metric"): "GRM188R71C105KA12D",
    ("4.7u X7R", "Capacitor_SMD:C_0603_1608Metric"): "GRM188Z71A475KE15D",
    ("10u 6.3V X5R", "Capacitor_SMD:C_0603_1608Metric"): "GRM188R60J106ME47D",
    ("22u 6.3V X5R", "Capacitor_SMD:C_0603_1608Metric"): "GRM188R60J226MEA0D",
    ("22u 6.3V X5R", "Capacitor_SMD:C_0805_2012Metric"): "GRM21BR60J226ME39L",
}


def add_two(
    d: Design,
    ref: str,
    value: str,
    kind: str,
    net1: str,
    net2: str,
    x: float,
    y: float,
    *,
    footprint: str | None = None,
    manufacturer: str = "",
    mpn: str = "",
    dnp: bool = False,
    description: str = "",
) -> None:
    resolved_footprint = footprint or footprint_for(kind)
    if manufacturer == "Murata" and not mpn:
        mpn = MURATA_CAP_MPN.get((value, resolved_footprint), "")
    d.add(
        ref, value, kind, resolved_footprint, [net1, net2], x, y,
        manufacturer=manufacturer, mpn=mpn, dnp=dnp, description=description,
    )


def build_design() -> Design:
    d = Design()
    standard_symbol_types(d)
    ic_symbol_types(d)

    # Sheet map.  The A0 canvas is intentionally partitioned into reviewable
    # functional blocks while remaining a single flat netlist for PCB parity.
    d.note(20, 18, "HOLTER V1 — RESEARCH PROTOTYPE / NOT A MEDICAL DEVICE", 3.0)
    d.note(20, 25, "PATIENT ELECTRODES MUST BE DISCONNECTED BEFORE USB", 2.5)
    d.note(20, 36, "ECG CONNECTOR + LOW-LEAKAGE INPUT PROTECTION", 2.2)
    d.note(230, 36, "ADS1294R AFE / REFERENCE / WCT / RLD", 2.2)
    d.note(410, 36, "STM32WB55RGV6 / CLOCKS / RF", 2.2)
    d.note(620, 36, "MICROSD + BMI270", 2.2)
    d.note(20, 300, "BATTERY / USB POWER MUX / REGULATORS", 2.2)
    d.note(410, 300, "USB POGO / SWD / STATUS / TEST", 2.2)
    d.note(620, 300, "RF FILTER / MATCH / ANTENNA", 2.2)

    # ------------------------------------------------------------------ ECG
    d.add(
        "J1", "ECG_HARNESS", "ECG_CONN", "Holter:Molex_Pico-EZmate_78171-5006",
        ["RA_ELEC", "LA_ELEC", "LL_ELEC", "RL_ELEC", "V5_ELEC", "CABLE_SHIELD"],
        35, 92, manufacturer="Molex", mpn="78171-5006",
        datasheet="https://www.molex.com/en-us/products/part-detail/781715006",
    )

    # Connector-side bidirectional ESD devices. Their leakage must be verified
    # on the first articles before any human-electrode experiment.
    electrode_y = {"RA_ELEC": 52, "LA_ELEC": 86, "LL_ELEC": 120, "V5_ELEC": 154, "RL_ELEC": 188}
    for ref, net in zip(("D1", "D2", "D3", "D4", "D5"), electrode_y):
        add_two(
            d, ref, "PESD5V0U1UL", "D_BIDIR", net, "GND", 70, electrode_y[net],
            manufacturer="Nexperia", mpn="PESD5V0U1UL,315",
            description="Connector-side low-capacitance ESD suppressor; characterize leakage",
        )

    # Each measurement path has two physical series resistors. RA's first
    # resistor is common, followed by independent CH1N and CH2N branches.
    patient_r_fp = "Resistor_SMD:R_0603_1608Metric"
    add_two(d, "R1", "47.5k 0.1%", "R", "RA_ELEC", "RA_PROT", 95, 52, footprint=patient_r_fp, manufacturer="Yageo", mpn="RT0603BRD0747K5L")
    add_two(d, "R2", "47.5k 0.1%", "R", "RA_PROT", "ADS_CH1N", 150, 46, footprint=patient_r_fp, manufacturer="Yageo", mpn="RT0603BRD0747K5L")
    add_two(d, "R3", "47.5k 0.1%", "R", "RA_PROT", "ADS_CH2N", 150, 58, footprint=patient_r_fp, manufacturer="Yageo", mpn="RT0603BRD0747K5L")
    add_two(d, "C1", "100p C0G", "C", "RA_PROT", "GND", 122, 52, manufacturer="Murata", mpn="GRM1555C1H101JA01D")
    add_two(d, "C2", "100p C0G", "C", "ADS_CH1N", "GND", 178, 46, manufacturer="Murata", mpn="GRM1555C1H101JA01D")
    add_two(d, "C3", "100p C0G", "C", "ADS_CH2N", "GND", 178, 58, manufacturer="Murata", mpn="GRM1555C1H101JA01D")

    channel_specs = [
        ("LA", 4, 4, 86, "ADS_CH1P"),
        ("LL", 6, 6, 120, "ADS_CH2P"),
        ("V5", 8, 8, 154, "ADS_CH3P"),
    ]
    for name, r_first, c_first, y, adc_net in channel_specs:
        electrode = f"{name}_ELEC"
        prot = f"{name}_PROT"
        add_two(d, f"R{r_first}", "47.5k 0.1%", "R", electrode, prot, 95, y, footprint=patient_r_fp, manufacturer="Yageo", mpn="RT0603BRD0747K5L")
        add_two(d, f"R{r_first + 1}", "47.5k 0.1%", "R", prot, adc_net, 150, y, footprint=patient_r_fp, manufacturer="Yageo", mpn="RT0603BRD0747K5L")
        add_two(d, f"C{c_first}", "100p C0G", "C", prot, "GND", 122, y, manufacturer="Murata", mpn="GRM1555C1H101JA01D")
        add_two(d, f"C{c_first + 1}", "100p C0G", "C", adc_net, "GND", 178, y, manufacturer="Murata", mpn="GRM1555C1H101JA01D")

    # Low-leakage rail clamps: upper diode cathode to 3V0_A, lower diode
    # cathode to the signal. BAS116 leakage is far below ordinary ESD diodes.
    for idx, (prot, y) in enumerate((("RA_PROT",52),("LA_PROT",86),("LL_PROT",120),("V5_PROT",154)), start=0):
        add_two(d, f"D{6 + idx*2}", "BAS116", "D", "3V0_A", prot, 122, y - 8, manufacturer="Nexperia", mpn="BAS116,115")
        add_two(d, f"D{7 + idx*2}", "BAS116", "D", prot, "GND", 122, y + 8, manufacturer="Nexperia", mpn="BAS116,115")

    add_two(d, "R10", "162k 0.1%", "R", "ADS_RLDOUT", "RLD_LIMIT_MID", 135, 188, footprint=patient_r_fp, manufacturer="Yageo", mpn="RT0603BRD07162KL")
    add_two(d, "R11", "162k 0.1%", "R", "RLD_LIMIT_MID", "RL_ELEC", 170, 188, footprint=patient_r_fp, manufacturer="Yageo", mpn="RT0603BRD07162KL")
    add_two(d, "C10", "100p C0G DNP", "C", "RL_ELEC", "GND", 198, 188, dnp=True, manufacturer="Murata", mpn="GRM1555C1H101JA01D")
    add_two(d, "R12", "1M", "R", "CABLE_SHIELD", "GND", 95, 214, footprint=patient_r_fp, manufacturer="Yageo", mpn="RC0603FR-071ML")
    add_two(d, "C11", "1nF 100V C0G", "C", "CABLE_SHIELD", "GND", 130, 214, footprint="Capacitor_SMD:C_0603_1608Metric", manufacturer="KEMET", mpn="C0603C102J1GACTU")

    # ADS1294R pin-to-net map using actual NFBGA ball designators.
    ads_nets = {
        "H1":"ADS_CH1P", "H2":"ADS_CH1N", "G1":"ADS_CH2P", "G2":"ADS_CH2N",
        "F1":"ADS_CH3P", "F2":"ADS_WCT", "E1":"ADS_CH4P", "E2":"ADS_CH4N",
        "D1":"3V0_A", "D2":"3V0_A", "C1":"3V0_A", "C2":"3V0_A",
        "B1":"3V0_A", "B2":"3V0_A", "A1":"3V0_A", "A2":"3V0_A",
        "H3":"ADS_VREFP", "G3":"ADS_VCAP4", "F3":None, "E3":None,
        "D3":"ADS_WCT", "C3":"ADS_RLDINV", "B3":"ADS_RLDOUT", "A3":"ADS_RLDIN",
        "H4":"GND", "G4":"ADS_RESP_MODP", "F4":"ADS_RESP_MODN", "E4":"GND",
        "D4":"GND", "C4":None, "B4":"3V0_A", "A4":"3V0_A",
        "H5":"ADS_VCAP1", "G5":"ADS_PWDN", "F5":"ADS_GPIO1_TIE", "E5":"ADS_GPIO4_TIE",
        "D5":"GND", "C5":"GND", "B5":"GND", "A5":"GND",
        "H6":"ADS_VCAP2", "G6":"ADS_RESET", "F6":"GND", "E6":"ADS_GPIO3_TIE",
        "D6":"ADS_DRDY", "C6":"3V0_A", "B6":"3V0_A", "A6":"3V0_A",
        "H7":"GND", "G7":"ADS_START", "F7":"ADS_CS", "E7":"ADS_GPIO2_TIE",
        "D7":"GND", "C7":"GND", "B7":"ADS_VCAP3", "A7":"ADS_AVDD1",
        "H8":"ADS_MOSI", "G8":"ADS_CLK", "F8":"ADS_SCLK", "E8":"ADS_MISO",
        "D8":"3V0_D", "C8":"3V0_D", "B8":"3V0_D", "A8":"GND",
    }
    d.add(
        "U1", "ADS1294RIZXGT", "ADS1294R", "Holter:ADS1294R_ZXG",
        ads_nets, 270, 130, manufacturer="Texas Instruments", mpn="ADS1294RIZXGT",
        datasheet="https://www.ti.com/lit/ds/symlink/ads1294r.pdf",
    )

    add_two(d, "R13", "0R", "R", "ADS_RLDOUT", "ADS_RLDIN", 230, 220, manufacturer="Yageo", mpn="RC0402JR-070RL")
    add_two(d, "R14", "1M", "R", "ADS_RLDOUT", "ADS_RLDINV", 265, 220, manufacturer="Yageo", mpn="RC0402FR-071ML")
    add_two(d, "C12", "1.5nF C0G", "C", "ADS_RLDOUT", "ADS_RLDINV", 300, 220, manufacturer="Murata", mpn="GRM1555C1H152JA01D")
    add_two(d, "C13", "100p C0G", "C", "ADS_WCT", "GND", 335, 220, manufacturer="Murata", mpn="GRM1555C1H101JA01D")
    add_two(d, "R15", "0R", "R", "3V0_A", "ADS_AVDD1", 370, 220, manufacturer="Yageo", mpn="RC0402JR-070RL")

    # Reference, internal charge-pump bypass and local supply decoupling.
    ads_caps = [
        ("C14","10u 6.3V X5R","ADS_VREFP"),("C15","100n X7R","ADS_VREFP"),
        ("C16","22u 6.3V X5R","ADS_VCAP1"),("C17","1u X7R","ADS_VCAP2"),
        ("C18","1u X7R","ADS_VCAP3"),("C19","1u X7R","ADS_VCAP4"),
        ("C20","1u X7R","3V0_A"),("C21","100n X7R","3V0_A"),
        ("C22","1u X7R","ADS_AVDD1"),("C23","100n X7R","ADS_AVDD1"),
        ("C24","1u X7R","3V0_D"),("C25","100n X7R","3V0_D"),
    ]
    for idx, (ref, value, net) in enumerate(ads_caps):
        fp = "Capacitor_SMD:C_0603_1608Metric" if value.startswith(("10u", "22u", "1u")) else footprint_for("C")
        add_two(d, ref, value, "C", net, "GND", 225 + (idx % 6) * 30, 245 + (idx // 6) * 16, footprint=fp, manufacturer="Murata")

    # CH4 is physically biased to AVDD as required for an unused ADS1294R
    # input. Test pads are retained before its two zero-ohm links.
    add_two(d, "R16", "0R", "R", "ADS_CH4P", "3V0_A", 335, 74, manufacturer="Yageo", mpn="RC0402JR-070RL")
    add_two(d, "R17", "0R", "R", "ADS_CH4N", "3V0_A", 335, 86, manufacturer="Yageo", mpn="RC0402JR-070RL")
    d.add("TP1", "CH4P", "TP", footprint_for("TP"), ["ADS_CH4P"], 370, 74, in_bom=False)
    d.add("TP2", "CH4N", "TP", footprint_for("TP"), ["ADS_CH4N"], 370, 86, in_bom=False)

    # Respiration drive coupling is laid out but explicitly DNP in V1.
    add_two(d, "C26", "2.2n C0G DNP", "C", "ADS_RESP_MODP", "RESP_P_AC", 335, 160, dnp=True, manufacturer="Murata", mpn="GRM1555C1H222JA01D")
    add_two(d, "R18", "40.2k 0.1% DNP", "R", "RESP_P_AC", "ADS_CH2P", 370, 160, dnp=True, manufacturer="Yageo", mpn="RT0402BRD0740K2L")
    add_two(d, "C27", "2.2n C0G DNP", "C", "ADS_RESP_MODN", "RESP_N_AC", 335, 176, dnp=True, manufacturer="Murata", mpn="GRM1555C1H222JA01D")
    add_two(d, "R19", "40.2k 0.1% DNP", "R", "RESP_N_AC", "ADS_CH2N", 370, 176, dnp=True, manufacturer="Yageo", mpn="RT0402BRD0740K2L")
    for ref, net, y in (("R52","ADS_GPIO1_TIE",190),("R53","ADS_GPIO2_TIE",202),("R54","ADS_GPIO3_TIE",214),("R55","ADS_GPIO4_TIE",226)):
        add_two(d, ref, "0R", "R", net, "GND", 385, y, manufacturer="Yageo", mpn="RC0402JR-070RL")

    # --------------------------------------------------------------- POWER IN
    d.add(
        "J2", "PROTECTED_1S_LIPO", "BAT_CONN", "Connector_Molex:Molex_Pico-EZmate_78171-0002_1x02-1MP_P1.20mm_Vertical",
        ["BAT_RAW", "GND"], 35, 345, manufacturer="Molex", mpn="78171-0002",
    )
    add_two(d, "D14", "PESD5V0U1UL", "D_BIDIR", "BAT_RAW", "GND", 68, 330, manufacturer="Nexperia", mpn="PESD5V0U1UL,315")
    add_two(d, "F1", "0.50A PTC", "FUSE", "BAT_RAW", "BAT_FUSED", 78, 345, manufacturer="Bourns", mpn="MF-FSMF050X-2")
    d.add(
        "Q1", "DMP2035U", "PMOS", "Package_TO_SOT_SMD:SOT-23",
        {"1":"BAT_GATE", "2":"BAT_FUSED", "3":"BAT_PROT"}, 118, 345,
        manufacturer="Diodes Incorporated", mpn="DMP2035U-7",
        description="P-channel high-side reverse-polarity protection MOSFET",
    )
    add_two(d, "R20", "1M", "R", "BAT_GATE", "GND", 118, 365, manufacturer="Yageo", mpn="RC0402FR-071ML")
    add_two(d, "C28", "10u 6.3V X5R", "C", "BAT_PROT", "GND", 150, 345, footprint="Capacitor_SMD:C_0603_1608Metric", manufacturer="Murata")

    d.add(
        "J3", "USB_POGO", "POGO4", "Holter:Pogo_USB_4x1_P2.54_Bottom",
        ["VBUS_RAW", "USB_DM_POGO", "USB_DP_POGO", "GND"], 430, 350,
        description="ENIG bottom contact pads; VBUS / D- / D+ / GND",
        in_bom=False,
    )
    d.add(
        "U10", "TPD2EUSB30DRTR", "USB_ESD", "Package_TO_SOT_SMD:SOT-23",
        {"1":"USB_DP_POGO", "2":"GND", "3":"USB_DM_POGO"}, 475, 350,
        manufacturer="Texas Instruments", mpn="TPD2EUSB30DRTR",
        datasheet="https://www.ti.com/lit/ds/symlink/tpd2eusb30.pdf",
    )
    add_two(d, "F2", "0.50A PTC", "FUSE", "VBUS_RAW", "VBUS", 455, 325, manufacturer="Bourns", mpn="MF-FSMF050X-2")
    add_two(d, "R21", "22R", "R", "USB_DM_POGO", "USB_DM", 515, 342, manufacturer="Yageo", mpn="RC0402FR-0722RL")
    add_two(d, "R22", "22R", "R", "USB_DP_POGO", "USB_DP", 515, 358, manufacturer="Yageo", mpn="RC0402FR-0722RL")

    d.add(
        "U4", "TPS2116DRLR", "TPS2116", "Holter:Texas_DRL0008A",
        {"1":"GND", "2":"SYS_RAW", "3":"VBUS", "4":"MUX_PR1", "5":"VBUS", "6":"BAT_PROT", "7":"SYS_RAW", "8":"PWR_USB_N"},
        195, 350, manufacturer="Texas Instruments", mpn="TPS2116DRLR",
        datasheet="https://www.ti.com/lit/ds/symlink/tps2116.pdf",
    )
    add_two(d, "R23", "300k", "R", "VBUS", "MUX_PR1", 165, 380, manufacturer="Yageo", mpn="RC0402FR-07300KL")
    add_two(d, "R24", "100k", "R", "MUX_PR1", "GND", 200, 380, manufacturer="Yageo", mpn="RC0402FR-07100KL")
    add_two(d, "C29", "1u X7R", "C", "VBUS", "GND", 165, 322, footprint="Capacitor_SMD:C_0603_1608Metric", manufacturer="Murata")
    add_two(d, "C30", "1u X7R", "C", "BAT_PROT", "GND", 195, 322, footprint="Capacitor_SMD:C_0603_1608Metric", manufacturer="Murata")
    add_two(d, "C31", "22u 6.3V X5R", "C", "SYS_RAW", "GND", 225, 322, footprint="Capacitor_SMD:C_0805_2012Metric", manufacturer="Murata")
    add_two(d, "R25", "100k", "R", "3V0_D", "PWR_USB_N", 235, 380, manufacturer="Yageo", mpn="RC0402FR-07100KL")

    d.add(
        "U5", "TPS7A2130PDBVR", "LDO5", "Package_TO_SOT_SMD:SOT-23-5",
        {"1":"SYS_RAW", "2":"GND", "3":"SYS_RAW", "4":None, "5":"3V0_D"}, 275, 340,
        manufacturer="Texas Instruments", mpn="TPS7A2130PDBVR",
        datasheet="https://www.ti.com/lit/ds/symlink/tps7a21.pdf",
    )
    d.add(
        "U6", "TPS7A2030PDBVR", "LDO5", "Package_TO_SOT_SMD:SOT-23-5",
        {"1":"SYS_RAW", "2":"GND", "3":"SYS_RAW", "4":None, "5":"3V0_A"}, 325, 340,
        manufacturer="Texas Instruments", mpn="TPS7A2030PDBVR",
        datasheet="https://www.ti.com/lit/ds/symlink/tps7a20.pdf",
    )
    d.add(
        "U7", "TPS7A2033PDBVR", "LDO5", "Package_TO_SOT_SMD:SOT-23-5",
        {"1":"VBUS", "2":"GND", "3":"VBUS", "4":None, "5":"3V3_USB"}, 375, 340,
        manufacturer="Texas Instruments", mpn="TPS7A2033PDBVR",
        datasheet="https://www.ti.com/lit/ds/symlink/tps7a20.pdf",
    )
    ldo_caps = [
        ("C32","1u","SYS_RAW",260,380),("C33","10u","3V0_D",290,380),
        ("C34","1u","SYS_RAW",320,400),("C35","10u","3V0_A",350,400),
        ("C36","1u","VBUS",365,380),("C37","4.7u","3V3_USB",395,380),
    ]
    for ref, value, net, x, y in ldo_caps:
        dielectric = "6.3V X5R" if value == "10u" else "X7R"
        add_two(d, ref, f"{value} {dielectric}", "C", net, "GND", x, y, footprint="Capacitor_SMD:C_0603_1608Metric", manufacturer="Murata")

    # Low-current battery monitor and isolated RTC hold-up reservoir.
    add_two(d, "R26", "1M", "R", "BAT_PROT", "BAT_SENSE_DIV", 50, 400, manufacturer="Yageo", mpn="RC0402FR-071ML")
    add_two(d, "R27", "330k", "R", "BAT_SENSE_DIV", "GND", 85, 400, manufacturer="Yageo", mpn="RC0402FR-07330KL")
    add_two(d, "R28", "1k", "R", "BAT_SENSE_DIV", "BAT_ADC", 120, 400, manufacturer="Yageo", mpn="RC0402FR-071KL")
    add_two(d, "C38", "100n X7R", "C", "BAT_ADC", "GND", 150, 400, manufacturer="Murata")
    add_two(d, "D15", "BAT54H", "D", "RTC_HOLD", "3V0_D", 50, 430, manufacturer="Nexperia", mpn="BAT54H,115")
    for index, x in enumerate((85, 115, 145), start=39):
        add_two(d, f"C{index}", "47u 6.3V X5R", "C", "RTC_HOLD", "GND", x, 430, footprint="Capacitor_SMD:C_0805_2012Metric", manufacturer="Murata", mpn="GRM21BR60J476ME15L")

    # ------------------------------------------------------------- MCU + USB
    stm_nets: dict[str, str | None] = {
        "1":"RTC_HOLD", "2":None, "3":"LSE_IN", "4":"LSE_OUT", "5":"BOOT0",
        "6":"IMU_SCL", "7":"IMU_SDA", "8":"NRST", "9":"ADS_START", "10":"ADS_DRDY",
        "11":"SD_DETECT", "12":"SD_PWR_EN", "13":"MCU_VDDA", "14":"MCU_VDDA", "15":"BAT_ADC",
        "16":None, "17":None, "18":None, "19":"ADS_CS", "20":"ADS_SCLK",
        "21":"ADS_MISO", "22":"ADS_MOSI", "23":None, "24":"USB_VBUS_SENSE", "25":"IMU_INT1",
        "26":"IMU_INT2", "27":None, "28":None, "29":None, "30":"3V0_D",
        "31":"RF_MCU", "32":"GND", "33":"3V0_D", "34":"HSE_OUT", "35":"HSE_IN", "36":None,
        "37":None, "38":"ADS_PWDN", "39":"ADS_RESET", "40":None, "41":"SMPS_FB", "42":"GND",
        "43":"SMPS_SW", "44":"SMPS_IN", "45":"3V0_D", "46":None, "47":"SD_SCK_MCU",
        "48":"SD_MISO_MCU", "49":"SD_MOSI_MCU", "50":None, "51":"SD_CS_MCU", "52":"USB_DM",
        "53":"USB_DP", "54":"SWDIO", "55":"3V3_USB", "56":"SWCLK", "57":None,
        "58":None, "59":None, "60":None, "61":None, "62":None,
        "63":"SWO", "64":None, "65":"LED_STATUS_N", "66":None, "67":None,
        "68":"3V0_D", "69":"GND",
    }
    d.add(
        "U2", "STM32WB55RGV6", "STM32WB55RG", "Package_DFN_QFN:QFN-68-1EP_8x8mm_P0.4mm_EP6.4x6.4mm_ThermalVias",
        stm_nets, 485, 145, manufacturer="STMicroelectronics", mpn="STM32WB55RGV6",
        datasheet="https://www.st.com/resource/en/datasheet/stm32wb55rg.pdf",
    )

    # ADS control defaults keep the AFE safe during MCU reset.
    add_two(d, "R29", "100k", "R", "3V0_D", "ADS_PWDN", 410, 225, manufacturer="Yageo", mpn="RC0402FR-07100KL")
    add_two(d, "R30", "100k", "R", "3V0_D", "ADS_RESET", 445, 225, manufacturer="Yageo", mpn="RC0402FR-07100KL")
    add_two(d, "R31", "100k", "R", "ADS_START", "GND", 480, 225, manufacturer="Yageo", mpn="RC0402FR-07100KL")
    add_two(d, "R32", "100k", "R", "3V0_D", "ADS_CS", 515, 225, manufacturer="Yageo", mpn="RC0402FR-07100KL")

    # HSE/LSE and SMPS networks follow the STM32WB hardware note topology.
    d.add("Y1", "32MHz 6pF", "XTAL4", footprint_for("XTAL4"), ["HSE_IN","GND","HSE_OUT","GND"], 425, 260, manufacturer="NDK", mpn="NX2016SA-32M-EXS00A-CS06465")
    add_two(d, "C42", "8.2p C0G", "C", "HSE_IN", "GND", 455, 252, manufacturer="Murata", mpn="GRM1555C1H8R2CA01D")
    add_two(d, "C43", "8.2p C0G", "C", "HSE_OUT", "GND", 455, 268, manufacturer="Murata", mpn="GRM1555C1H8R2CA01D")
    d.add("Y2", "32.768kHz 7pF", "XTAL2", "Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm", ["LSE_IN","LSE_OUT"], 510, 260, manufacturer="NDK", mpn="NX3215SA-32.768K-STD-MUA-14")
    add_two(d, "C44", "10p C0G", "C", "LSE_IN", "GND", 540, 252, manufacturer="Murata")
    add_two(d, "C45", "10p C0G", "C", "LSE_OUT", "GND", 540, 268, manufacturer="Murata")
    add_two(d, "L1", "10nH", "L", "3V0_D", "SMPS_IN", 570, 238, manufacturer="Murata", mpn="LQG15HN10NJ02D")
    add_two(d, "L2", "2.2uH", "L", "SMPS_SW", "SMPS_FB", 570, 258, manufacturer="Murata", mpn="LQM18PN2R2MFRL")
    add_two(d, "C46", "4.7u X7R", "C", "SMPS_IN", "GND", 600, 238, footprint="Capacitor_SMD:C_0603_1608Metric", manufacturer="Murata")
    add_two(d, "C47", "4.7u X7R", "C", "SMPS_FB", "GND", 600, 258, footprint="Capacitor_SMD:C_0603_1608Metric", manufacturer="Murata")

    add_two(d, "R33", "100k", "R", "3V0_D", "NRST", 410, 282, manufacturer="Yageo", mpn="RC0402FR-07100KL")
    add_two(d, "C48", "100n X7R", "C", "NRST", "GND", 445, 282, manufacturer="Murata")
    add_two(d, "R34", "100k", "R", "BOOT0", "GND", 480, 282, manufacturer="Yageo", mpn="RC0402FR-07100KL")
    add_two(d, "FB1", "600R@100MHz", "L", "3V0_D", "MCU_VDDA", 515, 282, manufacturer="Murata", mpn="BLM15AG601SN1D")
    add_two(d, "C49", "1u X7R", "C", "MCU_VDDA", "GND", 550, 282, footprint="Capacitor_SMD:C_0603_1608Metric", manufacturer="Murata")
    add_two(d, "C50", "100n X7R", "C", "MCU_VDDA", "GND", 580, 282, manufacturer="Murata")

    for idx, (net, x, y) in enumerate(
        (("3V0_D",410,205),("3V0_D",440,205),("3V0_D",470,205),("3V0_D",500,205),("3V0_D",530,205),("3V3_USB",560,205)),
        start=51,
    ):
        add_two(d, f"C{idx}", "100n X7R", "C", net, "GND", x, y, manufacturer="Murata")
    add_two(d, "C57", "4.7u X7R", "C", "3V0_D", "GND", 590, 205, footprint="Capacitor_SMD:C_0603_1608Metric", manufacturer="Murata")

    # VBUS detection uses a high-value divider; VDDUSB is never tied to 3.0 V.
    add_two(d, "R35", "470k", "R", "VBUS", "USB_VBUS_SENSE", 555, 330, manufacturer="Yageo", mpn="RC0402FR-07470KL")
    add_two(d, "R36", "680k", "R", "USB_VBUS_SENSE", "GND", 590, 330, manufacturer="Yageo", mpn="RC0402FR-07680KL")

    d.add(
        "J5", "SWD_POGO", "SWD5", "Holter:Pogo_SWD_5x1_P1.27_Bottom",
        ["3V0_D", "GND", "SWDIO", "SWCLK", "NRST"], 435, 410,
        in_bom=False,
    )
    add_two(d, "R37", "2.2k", "R", "3V0_D", "LED_STATUS_A", 500, 405, manufacturer="Yageo", mpn="RC0402FR-072K2L")
    add_two(d, "D16", "GREEN 0603", "LED", "LED_STATUS_N", "LED_STATUS_A", 540, 405, manufacturer="Wurth Elektronik", mpn="150060VS75000")

    # ------------------------------------------------------------------ IMU
    d.add(
        "U3", "BMI270", "BMI270", "Package_LGA:Bosch_LGA-14_3x2.5mm_P0.5mm",
        {"1":"GND","2":None,"3":None,"4":"IMU_INT1","5":"3V0_D","6":"GND","7":"GND",
         "8":"3V0_D","9":"IMU_INT2","10":None,"11":None,"12":"3V0_D","13":"IMU_SCL","14":"IMU_SDA"},
        665, 230, manufacturer="Bosch Sensortec", mpn="BMI270",
        datasheet="https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmi270-ds000.pdf",
    )
    add_two(d, "R38", "4.7k", "R", "3V0_D", "IMU_SCL", 625, 270, manufacturer="Yageo", mpn="RC0402FR-074K7L")
    add_two(d, "R39", "4.7k", "R", "3V0_D", "IMU_SDA", 660, 270, manufacturer="Yageo", mpn="RC0402FR-074K7L")
    add_two(d, "C58", "100n X7R", "C", "3V0_D", "GND", 695, 270, manufacturer="Murata")
    add_two(d, "C59", "100n X7R", "C", "3V0_D", "GND", 725, 270, manufacturer="Murata")
    add_two(d, "C60", "1u X7R", "C", "3V0_D", "GND", 755, 270, footprint="Capacitor_SMD:C_0603_1608Metric", manufacturer="Murata")

    # --------------------------------------------------------------- MICROSD
    d.add(
        "U8", "TPS22918DBVR", "LOADSW6", "Package_TO_SOT_SMD:SOT-23-6",
        {"1":"3V0_D","2":"GND","3":"SD_CT","4":"SD_PWR_EN","5":"GND","6":"3V0_SD"},
        635, 75, manufacturer="Texas Instruments", mpn="TPS22918DBVR",
        datasheet="https://www.ti.com/lit/ds/symlink/tps22918.pdf",
    )
    add_two(d, "C61", "1n X7R", "C", "SD_CT", "GND", 600, 75, manufacturer="Murata")
    add_two(d, "R40", "100k", "R", "SD_PWR_EN", "GND", 600, 95, manufacturer="Yageo", mpn="RC0402FR-07100KL")
    add_two(d, "C62", "1u X7R", "C", "3V0_D", "GND", 670, 70, footprint="Capacitor_SMD:C_0603_1608Metric", manufacturer="Murata")
    add_two(d, "C63", "22u 6.3V X5R", "C", "3V0_SD", "GND", 700, 70, footprint="Capacitor_SMD:C_0805_2012Metric", manufacturer="Murata")
    add_two(d, "C64", "100n X7R", "C", "3V0_SD", "GND", 730, 70, manufacturer="Murata")

    add_two(d, "R41", "22R", "R", "SD_CS_MCU", "SD_DAT3", 620, 120, manufacturer="Yageo", mpn="RC0402FR-0722RL")
    add_two(d, "R42", "22R", "R", "SD_MOSI_MCU", "SD_CMD", 620, 136, manufacturer="Yageo", mpn="RC0402FR-0722RL")
    add_two(d, "R43", "22R", "R", "SD_SCK_MCU", "SD_CLK", 620, 152, manufacturer="Yageo", mpn="RC0402FR-0722RL")
    add_two(d, "R44", "22R", "R", "SD_MISO_MCU", "SD_DAT0", 620, 168, manufacturer="Yageo", mpn="RC0402FR-0722RL")
    for ref, net, y in (("R45","SD_DAT2",112),("R46","SD_DAT3",128),("R47","SD_CMD",144),("R48","SD_DAT0",160),("R49","SD_DAT1",176)):
        add_two(d, ref, "47k", "R", "3V0_SD", net, 660, y, manufacturer="Yageo", mpn="RC0402FR-0747KL")
    add_two(d, "R50", "100k", "R", "3V0_D", "SD_DETECT", 695, 190, manufacturer="Yageo", mpn="RC0402FR-07100KL")
    d.add(
        "J4", "MICROSD", "MICROSD", "Connector_Card:microSD_HC_Molex_104031-0811",
        {"1":"SD_DAT2","2":"SD_DAT3","3":"SD_CMD","4":"3V0_SD","5":"SD_CLK","6":"GND",
         "7":"SD_DAT0","8":"SD_DAT1","9":"SD_DETECT","10":"GND","SH":"GND"},
        750, 145, manufacturer="Molex", mpn="104031-0811",
        datasheet="https://www.molex.com/en-us/products/part-detail/1040310811",
    )

    # ------------------------------------------------------------- RF CHAIN
    d.add(
        "U9", "MLPF-WB55-01E3", "MLPF", "Holter:MLPF-WB55-01E3",
        {"A1":"RF_FILTER_OUT","A2":"GND","A3":"RF_MCU","B1":"GND","B2":"GND","B3":"GND"},
        665, 345, manufacturer="STMicroelectronics", mpn="MLPF-WB55-01E3",
        datasheet="https://www.st.com/resource/en/datasheet/mlpf-wb55-01e3.pdf",
    )
    add_two(d, "C65", "DNP", "C", "RF_FILTER_OUT", "GND", 705, 330, dnp=True, description="RF pi-network shunt tuning position")
    add_two(d, "R51", "0R", "R", "RF_FILTER_OUT", "RF_ANT_FEED", 715, 345, manufacturer="Yageo", mpn="RC0402JR-070RL")
    add_two(d, "C66", "DNP", "C", "RF_ANT_FEED", "GND", 745, 330, dnp=True, description="RF pi-network shunt tuning position")
    d.add(
        "AE1", "2450AT18A100E", "ANT", footprint_for("ANT"), ["RF_ANT_FEED", None],
        780, 345, manufacturer="Johanson Technology", mpn="2450AT18A100E",
        datasheet="https://www.johansontechnology.com/docs/3827/Antenna-2450AT18A0100001E-Rev4.0.pdf",
    )
    d.note(650, 385, "ANTENNA KEEP-OUT: NO COPPER ON ANY LAYER; ALIGN WITH PLASTIC RF ENDCAP", 1.8)

    # Selected engineering test points. Other unused GPIOs are deliberately
    # labelled on U2 and remain routable as DNP bed-of-nails pads if needed.
    for index, (name, x) in enumerate((("BOOT0",590),("PWR_USB_N",615),("ADS_CLK",640),("SWO",665)), start=3):
        d.add(f"TP{index}", name, "TP", footprint_for("TP"), [name], x, 410, in_bom=False)

    # ERC declarations after passive protection/filters. These have no
    # physical footprint and only state which rails have a real source.
    for index, (net, x) in enumerate(
        (("GND",210),("VBUS",235),("BAT_PROT",260),("ADS_AVDD1",285),("MCU_VDDA",310),("RTC_HOLD",335),("SMPS_IN",360)),
        start=1,
    ):
        d.add(
            f"#FLG{index:02d}", "PWR_FLAG", "PWR_FLAG", "", [net], x, 450,
            in_bom=False, on_board=False,
        )

    return d


def symbol_definition(symbol: SymbolType, embedded: bool) -> str:
    name = f"Holter:{symbol.name}" if embedded else symbol.name
    half_w = symbol.width / 2
    half_h = symbol.body_height / 2
    lines = [
        f"\t\t(symbol {q(name)}" if embedded else f"\t(symbol {q(name)}",
        "\t\t\t(pin_names (offset 0.508))" if embedded else "\t\t(pin_names (offset 0.508))",
        "\t\t\t(exclude_from_sim no)" if embedded else "\t\t(exclude_from_sim no)",
        "\t\t\t(in_bom yes)" if embedded else "\t\t(in_bom yes)",
        "\t\t\t(on_board yes)" if embedded else "\t\t(on_board yes)",
    ]
    if not embedded:
        lines.extend(["\t\t(in_pos_files yes)", "\t\t(duplicate_pin_numbers_are_jumpers no)"])
    indent = "\t\t\t" if embedded else "\t\t"
    prop_indent = indent + "\t"
    properties = [
        ("Reference", symbol.reference, 0, -half_h - 2.54, False),
        ("Value", symbol.name, 0, half_h + 2.54, False),
        ("Footprint", "", 0, 0, True),
        ("Datasheet", "", 0, 0, True),
        ("Description", symbol.description, 0, 0, True),
        ("Manufacturer", "", 0, 0, True),
        ("MPN", "", 0, 0, True),
    ]
    for key, value, x, y, hidden in properties:
        lines.extend([f"{indent}(property {q(key)} {q(value)}", f"{prop_indent}(at {fmt(x)} {fmt(y)} 0)"])
        if embedded:
            lines.append(f"{prop_indent}(effects (font (size 1.27 1.27)){' (hide yes)' if hidden else ''})")
        else:
            lines.extend([f"{prop_indent}(show_name no)", f"{prop_indent}(do_not_autoplace no)"])
            if hidden:
                lines.append(f"{prop_indent}(hide yes)")
            lines.append(f"{prop_indent}(effects (font (size 1.27 1.27)))")
        lines.append(f"{indent})")
    lines.extend(
        [
            f"{indent}(symbol {q(symbol.name + '_1_1')}",
            f"{prop_indent}(rectangle",
            f"{prop_indent}\t(start {fmt(-half_w)} {fmt(-half_h)})",
            f"{prop_indent}\t(end {fmt(half_w)} {fmt(half_h)})",
            f"{prop_indent}\t(stroke (width 0.254) (type default))",
            f"{prop_indent}\t(fill (type background))",
            f"{prop_indent})",
        ]
    )
    angle_for = {"left": 0, "right": 180, "top": 90, "bottom": 270}
    for pin in symbol.pins:
        x, y, side = symbol.pin_xy[pin.number]
        lines.extend(
            [
                f"{prop_indent}(pin {pin.etype} line",
                f"{prop_indent}\t(at {fmt(x)} {fmt(y)} {angle_for[side]})",
                f"{prop_indent}\t(length 2.54)",
                f"{prop_indent}\t(name {q(pin.name)} (effects (font (size 0.9 0.9))))",
                f"{prop_indent}\t(number {q(pin.number)} (effects (font (size 0.9 0.9))))",
                f"{prop_indent})",
            ]
        )
    lines.extend([f"{indent})", f"{indent}(embedded_fonts no)"])
    lines.append("\t\t)" if embedded else "\t)")
    return "\n".join(lines)


def render_schematic(
    d: Design,
    *,
    project_name: str = "holter_v1",
    title: str = "Holter V1 — ECG + IMU Recorder",
    paper: str = "A0",
    date: str = "2026-08-23",
    revision: str = "1.0",
    company: str = "Research prototype — not a medical device",
    comments: tuple[str, str] = (
        "DISCONNECT ELECTRODES BEFORE USB",
        "ADS1294R + STM32WB55RGV6 + BMI270 + microSD",
    ),
    generator: str = "holter_v1_generator",
) -> str:
    root_id = uid("schematic/root")
    out = [
        "(kicad_sch",
        "\t(version 20250114)",
        f"\t(generator {q(generator)})",
        "\t(generator_version \"10.0\")",
        f"\t(uuid {q(root_id)})",
        f"\t(paper {q(paper)})",
        "\t(title_block",
        f"\t\t(title {q(title)})",
        f"\t\t(date {q(date)})",
        f"\t\t(rev {q(revision)})",
        f"\t\t(company {q(company)})",
        f"\t\t(comment 1 {q(comments[0])})",
        f"\t\t(comment 2 {q(comments[1])})",
        "\t)",
        "\t(lib_symbols",
    ]
    for symbol in d.symbol_types.values():
        out.append(symbol_definition(symbol, embedded=True))
    out.append("\t)")

    for x, y, note, size in d.notes:
        out.extend(
            [
                f"\t(text {q(note)}",
                "\t\t(exclude_from_sim no)",
                f"\t\t(at {fmt(x)} {fmt(y)} 0)",
                f"\t\t(effects (font (size {fmt(size)} {fmt(size)}) (thickness 0.35)) (justify left bottom))",
                f"\t\t(uuid {q(uid('note/' + note))})",
                "\t)",
            ]
        )

    for component in d.components:
        symbol = d.symbol_types[component.kind]
        comp_id = uid(f"component/{component.ref}")
        out.extend(
            [
                "\t(symbol",
                f"\t\t(lib_id {q('Holter:' + component.kind)})",
                f"\t\t(at {fmt(component.x)} {fmt(component.y)} 0)",
                "\t\t(unit 1)",
                "\t\t(exclude_from_sim no)",
                f"\t\t(in_bom {'yes' if component.in_bom else 'no'})",
                f"\t\t(on_board {'yes' if component.on_board else 'no'})",
                f"\t\t(dnp {'yes' if component.dnp else 'no'})",
                f"\t\t(uuid {q(comp_id)})",
            ]
        )
        prop_y = component.y - symbol.body_height / 2 - 2.54
        value_y = component.y + symbol.body_height / 2 + 2.54
        properties = [
            ("Reference", component.ref, component.x, prop_y, False),
            ("Value", component.value, component.x, value_y, False),
            ("Footprint", component.footprint, component.x, component.y, True),
            ("Datasheet", component.datasheet, component.x, component.y, True),
            ("Description", component.description, component.x, component.y, True),
            ("Manufacturer", component.manufacturer, component.x, component.y, True),
            ("MPN", component.mpn, component.x, component.y, True),
        ]
        properties.extend((key, value, component.x, component.y, True) for key, value in component.fields.items())
        for key, value, x, y, hidden in properties:
            out.extend(
                [
                    f"\t\t(property {q(key)} {q(value)}",
                    f"\t\t\t(at {fmt(x)} {fmt(y)} 0)",
                    f"\t\t\t(effects (font (size 1.0 1.0)){' (hide yes)' if hidden else ''})",
                    "\t\t)",
                ]
            )
        for pin in symbol.pins:
            out.extend(
                [
                    f"\t\t(pin {q(pin.number)}",
                    f"\t\t\t(uuid {q(uid(f'component/{component.ref}/pin/{pin.number}'))})",
                    "\t\t)",
                ]
            )
        out.extend(
            [
                "\t\t(instances",
                f"\t\t\t(project {q(project_name)}",
                f"\t\t\t\t(path {q('/' + root_id)}",
                f"\t\t\t\t\t(reference {q(component.ref)})",
                "\t\t\t\t\t(unit 1)",
                "\t\t\t\t)",
                "\t\t\t)",
                "\t\t)",
                "\t)",
            ]
        )

        # Labels/no-connect markers are placed directly on the pin endpoints.
        for pin in symbol.pins:
            local_x, local_y, side = symbol.pin_xy[pin.number]
            px = component.x + local_x
            # Library-symbol Y coordinates are Cartesian (positive upward),
            # while schematic-sheet coordinates increase downward.
            py = component.y - local_y
            net = component.nets[pin.number]
            if net is None:
                out.extend(
                    [
                        f"\t(no_connect (at {fmt(px)} {fmt(py)})",
                        f"\t\t(uuid {q(uid(f'nc/{component.ref}/{pin.number}'))})",
                        "\t)",
                    ]
                )
            else:
                justify = "right bottom" if side == "left" else "left bottom"
                out.extend(
                    [
                        f"\t(label {q(net)}",
                        f"\t\t(at {fmt(px)} {fmt(py)} 0)",
                        f"\t\t(effects (font (size 0.75 0.75)) (justify {justify}))",
                        f"\t\t(uuid {q(uid(f'label/{component.ref}/{pin.number}/{net}'))})",
                        "\t)",
                    ]
                )

    out.extend(
        [
            "\t(sheet_instances",
            "\t\t(path \"/\" (page \"1\"))",
            "\t)",
            "\t(embedded_fonts no)",
            ")",
            "",
        ]
    )
    return "\n".join(out)


def render_symbol_library(d: Design) -> str:
    parts = [
        "(kicad_symbol_lib",
        "\t(version 20251024)",
        "\t(generator \"kicad_symbol_editor\")",
        "\t(generator_version \"10.0\")",
    ]
    parts.extend(symbol_definition(symbol, embedded=False) for symbol in d.symbol_types.values())
    parts.extend([")", ""])
    return "\n".join(parts)


def fp_header(name: str, description: str, layer: str = "F.Cu") -> list[str]:
    silk = "B.SilkS" if layer == "B.Cu" else "F.SilkS"
    fab = "B.Fab" if layer == "B.Cu" else "F.Fab"
    return [
        f"(footprint {q(name)}",
        "\t(version 20250302)",
        "\t(generator \"holter_v1_generator\")",
        f"\t(layer {q(layer)})",
        f"\t(descr {q(description)})",
        f"\t(property \"Reference\" \"REF**\" (at 0 -5 0) (layer {q(silk)}) (effects (font (size 0.8 0.8) (thickness 0.12))))",
        f"\t(property \"Value\" {q(name)} (at 0 5 0) (layer {q(fab)}) (effects (font (size 0.8 0.8) (thickness 0.12))))",
        "\t(attr smd)",
    ]


def custom_footprints() -> dict[str, str]:
    files: dict[str, str] = {}

    # TI ZXG: 8 x 8 array, 0.8-mm pitch. 0.40-mm NSMD lands preserve a
    # 0.40-mm channel between adjacent pads for JLC's 4-layer process.
    name = "ADS1294R_ZXG"
    lines = fp_header(name, "TI ZXG 64-ball NFBGA, 8x8 mm, 0.8 mm pitch")
    lines.extend(
        [
            "\t(fp_rect (start -4 -4) (end 4 4) (stroke (width 0.1) (type solid)) (fill none) (layer \"F.Fab\"))",
            "\t(fp_rect (start -4.25 -4.25) (end 4.25 4.25) (stroke (width 0.05) (type solid)) (fill none) (layer \"F.CrtYd\"))",
            "\t(fp_line (start -4.1 -4.1) (end -3.2 -4.1) (stroke (width 0.15) (type solid)) (layer \"F.SilkS\"))",
            "\t(fp_line (start -4.1 -4.1) (end -4.1 -3.2) (stroke (width 0.15) (type solid)) (layer \"F.SilkS\"))",
        ]
    )
    for ci, col in enumerate("ABCDEFGH"):
        for row in range(1, 9):
            x = (ci - 3.5) * 0.8
            y = (row - 4.5) * 0.8
            lines.append(f"\t(pad {q(col + str(row))} smd circle (at {fmt(x)} {fmt(y)}) (size 0.4 0.4) (layers \"F.Cu\" \"F.Paste\" \"F.Mask\"))")
    lines.extend(["\t(embedded_fonts no)", ")", ""])
    files[name] = "\n".join(lines)

    name = "Texas_DRL0008A"
    lines = fp_header(name, "Texas Instruments DRL SOT-5X3, 8 pins, 2.1x1.6 mm")
    lines.extend(
        [
            "\t(fp_rect (start -1.05 -0.8) (end 1.05 0.8) (stroke (width 0.1) (type solid)) (fill none) (layer \"F.Fab\"))",
            "\t(fp_rect (start -1.55 -1.05) (end 1.55 1.05) (stroke (width 0.05) (type solid)) (fill none) (layer \"F.CrtYd\"))",
            "\t(fp_circle (center -1.18 -0.95) (end -1.08 -0.95) (stroke (width 0.15) (type solid)) (fill solid) (layer \"F.SilkS\"))",
        ]
    )
    ys = (-0.75, -0.25, 0.25, 0.75)
    for idx, y in enumerate(ys, start=1):
        lines.append(f"\t(pad {q(idx)} smd roundrect (at -1.15 {fmt(y)}) (size 0.75 0.3) (layers \"F.Cu\" \"F.Paste\" \"F.Mask\") (roundrect_rratio 0.2))")
    for idx, y in zip((8, 7, 6, 5), ys):
        lines.append(f"\t(pad {q(idx)} smd roundrect (at 1.15 {fmt(y)}) (size 0.75 0.3) (layers \"F.Cu\" \"F.Paste\" \"F.Mask\") (roundrect_rratio 0.2))")
    lines.extend(["\t(embedded_fonts no)", ")", ""])
    files[name] = "\n".join(lines)

    name = "Molex_Pico-EZmate_78171-5006"
    lines = fp_header(name, "Molex Pico-EZmate 78171-5006, six positions, 1.2-mm pitch")
    lines.extend(
        [
            "\t(fp_rect (start -4.2 -2.45) (end 4.2 2.45) (stroke (width 0.1) (type solid)) (fill none) (layer \"F.Fab\"))",
            "\t(fp_rect (start -4.65 -2.6) (end 4.65 2.6) (stroke (width 0.05) (type solid)) (fill none) (layer \"F.CrtYd\"))",
            "\t(fp_line (start -4.3 -2.55) (end -3.2 -2.55) (stroke (width 0.15) (type solid)) (layer \"F.SilkS\"))",
        ]
    )
    for idx in range(6):
        x = (idx - 2.5) * 1.2
        lines.append(f"\t(pad {q(idx + 1)} smd roundrect (at {fmt(x)} -1.875) (size 0.6 0.85) (layers \"F.Cu\" \"F.Mask\" \"F.Paste\") (roundrect_rratio 0.25))")
    for x in (-4.15, 4.15):
        lines.append(f"\t(pad \"MP\" smd roundrect (at {fmt(x)} 1.9) (size 0.7 0.8) (layers \"F.Cu\" \"F.Mask\" \"F.Paste\") (roundrect_rratio 0.25))")
    lines.extend(["\t(embedded_fonts no)", ")", ""])
    files[name] = "\n".join(lines)

    name = "MLPF-WB55-01E3"
    lines = fp_header(name, "ST MLPF-WB55-01E3, six-pad bumpless CSP, 1.6x1.0 mm")
    lines.extend(
        [
            "\t(fp_rect (start -0.8 -0.5) (end 0.8 0.5) (stroke (width 0.08) (type solid)) (fill none) (layer \"F.Fab\"))",
            "\t(fp_rect (start -0.95 -0.65) (end 0.95 0.65) (stroke (width 0.05) (type solid)) (fill none) (layer \"F.CrtYd\"))",
            "\t(fp_circle (center -0.7 -0.65) (end -0.62 -0.65) (stroke (width 0.12) (type solid)) (fill solid) (layer \"F.SilkS\"))",
        ]
    )
    for row, y in (("A", -0.2935), ("B", 0.2935)):
        for col, x in ((1, -0.5), (2, 0.0), (3, 0.5)):
            lines.append(f"\t(pad {q(row + str(col))} smd roundrect (at {fmt(x)} {fmt(y)}) (size 0.25 0.25) (layers \"F.Cu\" \"F.Paste\" \"F.Mask\") (roundrect_rratio 0.25))")
    lines.extend(["\t(embedded_fonts no)", ")", ""])
    files[name] = "\n".join(lines)

    def pogo(name: str, count: int, pitch: float, pad_w: float, pad_h: float, descr: str) -> str:
        lines = fp_header(name, descr, "B.Cu")
        width = (count - 1) * pitch + pad_w
        lines.extend(
            [
                f"\t(fp_rect (start {fmt(-width/2-0.5)} {fmt(-pad_h/2-0.5)}) (end {fmt(width/2+0.5)} {fmt(pad_h/2+0.5)}) (stroke (width 0.05) (type solid)) (fill none) (layer \"B.CrtYd\"))",
                f"\t(fp_line (start {fmt(-width/2)} {fmt(-pad_h/2-0.25)}) (end {fmt(-width/2+0.8)} {fmt(-pad_h/2-0.25)}) (stroke (width 0.15) (type solid)) (layer \"B.SilkS\"))",
            ]
        )
        for idx in range(count):
            x = (idx - (count - 1) / 2) * pitch
            lines.append(f"\t(pad {q(idx+1)} smd roundrect (at {fmt(x)} 0) (size {fmt(pad_w)} {fmt(pad_h)}) (layers \"B.Cu\" \"B.Mask\") (roundrect_rratio 0.2))")
        lines.extend(["\t(embedded_fonts no)", ")", ""])
        return "\n".join(lines)

    files["Pogo_USB_4x1_P2.54_Bottom"] = pogo(
        "Pogo_USB_4x1_P2.54_Bottom", 4, 2.54, 1.8, 3.0,
        "Four ENIG pogo contact pads on board bottom: VBUS, D-, D+, GND",
    )
    files["Pogo_SWD_5x1_P1.27_Bottom"] = pogo(
        "Pogo_SWD_5x1_P1.27_Bottom", 5, 1.27, 1.0, 1.8,
        "Five hidden SWD ENIG pogo pads on board bottom",
    )
    return files


def write_bom_source(d: Design) -> None:
    path = DOCS / "bom_source.csv"
    fieldnames = ["Reference", "Quantity", "Value", "Manufacturer", "Manufacturer Part Number", "Footprint", "DNP", "Description"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for component in sorted((c for c in d.components if c.in_bom), key=lambda c: (re.sub(r"\d+", "", c.ref), int(re.search(r"\d+", c.ref).group()) if re.search(r"\d+", c.ref) else 0)):
            writer.writerow(
                {
                    "Reference": component.ref,
                    "Quantity": 1,
                    "Value": component.value,
                    "Manufacturer": component.manufacturer,
                    "Manufacturer Part Number": component.mpn,
                    "Footprint": component.footprint,
                    "DNP": "DNP" if component.dnp else "",
                    "Description": component.description,
                }
            )

    net_path = DOCS / "pin_net_audit.csv"
    with net_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["Reference", "Value", "Pin", "Pin name", "Net", "Intentional NC"])
        for component in d.components:
            symbol = d.symbol_types[component.kind]
            for pin in symbol.pins:
                net = component.nets[pin.number]
                writer.writerow([component.ref, component.value, pin.number, pin.name, net or "", "YES" if net is None else ""])


def write_project_files(d: Design) -> None:
    HW.mkdir(parents=True, exist_ok=True)
    LIB.mkdir(parents=True, exist_ok=True)
    PRETTY.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)

    (HW / "holter_v1.kicad_sch").write_text(render_schematic(d), encoding="utf-8")
    (LIB / "holter_v1.kicad_sym").write_text(render_symbol_library(d), encoding="utf-8")
    for name, content in custom_footprints().items():
        (PRETTY / f"{name}.kicad_mod").write_text(content, encoding="utf-8")

    (HW / "sym-lib-table").write_text(
        '(sym_lib_table\n  (version 7)\n  (lib (name "Holter")(type "KiCad")(uri "${KIPRJMOD}/libraries/holter_v1.kicad_sym")(options "")(descr "Holter V1 project symbols"))\n)\n',
        encoding="utf-8",
    )
    (HW / "fp-lib-table").write_text(
        '(fp_lib_table\n  (version 7)\n  (lib (name "Holter")(type "KiCad")(uri "${KIPRJMOD}/libraries/holter_v1.pretty")(options "")(descr "Holter V1 project footprints"))\n)\n',
        encoding="utf-8",
    )
    # Keep KiCad's complete board-rule block when regenerating the schematic.
    # The routed release intentionally uses the fab-capable 0.10/0.10 mm rule
    # set stored in the checked-in project.  Replacing it with an empty board
    # section makes KiCad silently fall back to 0.20 mm defaults and produces
    # more than a thousand false release-rule violations.
    project_path = HW / "holter_v1.kicad_pro"
    existing_project: dict[str, object] = {}
    if project_path.exists():
        try:
            existing_project = json.loads(project_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing_project = {}
    board_settings = existing_project.get("board", {})

    project = {
        "board": board_settings,
        "boards": [],
        "cvpcb": {},
        "erc": {},
        "libraries": {},
        "meta": {"filename": "holter_v1.kicad_pro", "version": 3},
        "net_settings": {
            "classes": [
                {
                    "bus_width": 12,
                    "clearance": 0.1,
                    "diff_pair_gap": 0.15,
                    "diff_pair_via_gap": 0.25,
                    "diff_pair_width": 0.15,
                    "line_style": 0,
                    "microvia_diameter": 0.3,
                    "microvia_drill": 0.1,
                    "name": "Default",
                    "pcb_color": "rgba(0, 0, 0, 0.000)",
                    "priority": 2147483647,
                    "schematic_color": "rgba(0, 0, 0, 0.000)",
                    "track_width": 0.15,
                    "tuning_profile": "",
                    "via_diameter": 0.45,
                    "via_drill": 0.2,
                    "wire_width": 6,
                },
            ],
            "meta": {"version": 5},
            "net_colors": None,
            "netclass_assignments": None,
            "netclass_patterns": [],
        },
        "pcbnew": {},
        "schematic": {},
        "sheets": [],
        "text_variables": {},
    }
    project_path.write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8")
    write_bom_source(d)


def main() -> None:
    design = build_design()
    refs = [component.ref for component in design.components]
    if len(refs) != len(set(refs)):
        duplicates = sorted({ref for ref in refs if refs.count(ref) > 1})
        raise ValueError(f"Duplicate references: {duplicates}")
    write_project_files(design)
    print(f"Generated {len(design.components)} components, {len(design.symbol_types)} symbol types")


if __name__ == "__main__":
    main()
