#!/usr/bin/env python3
"""Generate the placed Holter V1 four-layer PCB with KiCad's pcbnew API.

Run with the Python interpreter bundled in the extracted KiCad 10 AppImage:
  ~/.cache/codex-kicad-10.0.5/AppDir/bin/python3.11 tools/generate_board.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pcbnew

from generate_hardware import HW, PRETTY, build_design, uid


KICAD_ROOT = Path(pcbnew.__file__).resolve().parents[4]
FP_ROOT = KICAD_ROOT / "share" / "kicad" / "footprints"
OUT = HW / "holter_v1.kicad_pcb"


def mm(value: float) -> int:
    return pcbnew.FromMM(value)


def vec(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(x), mm(y))


def add_path(
    board: pcbnew.BOARD,
    net: pcbnew.NETINFO_ITEM,
    points: list[tuple[float, float]],
    *,
    layer: int = pcbnew.F_Cu,
    width: float = 0.15,
    locked: bool = True,
) -> None:
    """Add a deterministic routed path, normally protected from autorouting."""
    for start, end in zip(points, points[1:]):
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(vec(*start)); track.SetEnd(vec(*end))
        track.SetLayer(layer); track.SetWidth(mm(width)); track.SetNet(net)
        track.SetLocked(locked)
        board.Add(track)


def add_via(
    board: pcbnew.BOARD,
    net: pcbnew.NETINFO_ITEM,
    x: float,
    y: float,
    diameter: float = 0.45,
    drill: float = 0.20,
    *,
    locked: bool = True,
) -> None:
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(vec(x, y)); via.SetWidth(mm(diameter)); via.SetDrill(mm(drill))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); via.SetNet(net)
    via.SetLocked(locked)
    board.Add(via)


def pad_xy(board: pcbnew.BOARD, ref: str, number: str) -> tuple[float, float]:
    pad = board.FindFootprintByReference(ref).FindPadByNumber(number)
    position = pad.GetPosition()
    return pcbnew.ToMM(position.x), pcbnew.ToMM(position.y)


def place_table() -> dict[str, tuple[float, float, float]]:
    p: dict[str, tuple[float, float, float]] = {}

    def put(ref: str, x: float, y: float, rot: float = 0) -> None:
        if ref in p:
            raise ValueError(f"duplicate placement for {ref}")
        p[ref] = (x, y, rot)

    # Mechanical anchors and major ICs.
    put("J1", 3.5, 15.0, 90)
    put("U1", 28.5, 15.0, 180)
    # Orient the STM32 RF/HSE pins toward the antenna side.  This makes the
    # MCU-to-MLPF launch and both HSE traces short instead of crossing the
    # digital core area.
    put("U2", 50.0, 15.0, 90)
    put("U3", 63.0, 8.5, 0)
    put("J4", 91.0, 22.5, -90)
    put("AE1", 97.4, 5.2, 0)
    put("J2", 42.0, 27.1, 0)
    put("J3", 79.0, 28.1, 0)
    put("J5", 55.0, 28.5, 0)

    # Electrode connector protection, ordered left-to-right toward the AFE.
    for ref, y in zip(("D1", "D2", "D3", "D4", "D5"), (5.0, 10.0, 15.0, 20.0, 25.0)):
        put(ref, 7.0, y, 90)
    for ref, y in (("R1",5.0),("R4",10.0),("R6",15.0),("R8",20.0),("R11",25.0)):
        put(ref, 10.0, y, 0)
    for ref, y in (("C1",5.0),("C4",10.0),("C6",15.0),("C8",20.0)):
        put(ref, 12.3, y, 90)
    # The two SOD-323 rail clamps are staggered horizontally.  This keeps
    # their courtyards clear while preserving a very short protected node.
    for ref, y in (("D6",4.0),("D8",9.0),("D10",14.0),("D12",19.0)):
        put(ref, 14.5, y, 90)
    for ref, y in (("D7",6.0),("D9",11.0),("D11",16.0),("D13",21.0)):
        put(ref, 16.7, y, 90)
    put("R2", 19.5, 4.2); put("R3", 19.5, 5.8)
    put("C2", 22.0, 3.8, 90); put("C3", 22.0, 6.2, 90)
    for ref, y in (("R5",10.0),("R7",15.0),("R9",20.0),("R10",25.0)):
        put(ref, 19.5 if ref != "R10" else 14.5, y)
    for ref, y in (("C5",10.0),("C7",15.0),("C9",20.0)):
        put(ref, 22.0, y, 90)
    put("C10", 18.0, 26.5, 90)
    put("R12", 8.5, 28.3); put("C11", 12.0, 28.3)

    # ADS1294R bypass/reference components tightly surrounding the BGA.
    for ref, x in zip(("C14","C15","C16","C17","C18","C19"), (24.0,26.2,28.4,30.6,32.8,35.0)):
        put(ref, x, 7.4, 90)
    # C19 tucks into the upper strip to clear the CH4 bias link courtyard.
    p["C19"] = (35.0, 6.5, 90)
    for ref, x in zip(("C20","C21","C22","C23","C24","C25"), (23.0,25.2,27.4,29.6,31.8,34.0)):
        put(ref, x, 22.6, 90)
    put("R13",34.8,24.7); put("R14",37.2,24.7); put("C12",37.5,27.2,90)
    put("C13",34.8,27.2,90); put("R15",39.5,23.0)
    put("R16",36.0,9.3); put("R17",36.0,11.5)
    put("TP1",38.0,9.0); put("TP2",38.0,11.0)
    put("C26",35.0,14.0,90); put("R18",38.0,14.0)
    put("C27",35.0,17.0,90); put("R19",38.0,17.0)
    for ref, y in (("R52",10.0),("R53",13.0),("R54",16.0),("R55",19.0)):
        put(ref, 40.7, y, 90)

    # ADS control pulls and MCU support.
    for ref, y in (("R29",10.0),("R30",13.0),("R31",16.0),("R32",19.0)):
        put(ref, 43.0, y, 90)
    p["R32"] = (40.0, 21.0, 90)
    # Oscillators and their load capacitors sit beside the corresponding MCU
    # pins.  Y1 is on the antenna-facing corner; Y2 is below the LSE pins.
    put("Y1",56.3,10.8,-90); put("C42",58.5,10.0,90); put("C43",58.5,12.0,90)
    put("Y2",44.0,20.5,180); put("C44",42.0,17.8,90); put("C45",44.5,23.0,90)

    # Per-pin MCU bypassing.  Keep the SMPS loop immediately above pins
    # 41/43/44 and place VDDUSB decoupling at the left-side USB supply pin.
    put("C51",55.8,15.3,90); put("C52",45.5,9.0,90)
    put("C53",44.5,16.5,90); put("C54",55.8,17.5,90); put("C55",53.5,9.0,90)
    put("C56",44.5,13.0,90); put("C57",61.0,17.0,90)
    put("L1",48.5,8.8); put("C46",48.5,6.5,90)
    put("L2",51.5,8.8); put("C47",51.5,6.5,90)
    put("R33",48.0,21.5); put("C48",49.8,21.3,90); put("R34",42.5,8.0)
    put("FB1",54.5,20.5); put("C49",52.0,24.5,90); put("C50",55.8,23.0,90)
    put("R35",57.0,19.5); put("R36",59.0,19.5)
    for ref, x in (("TP3",69.0),("TP4",72.0),("TP5",75.0),("TP6",78.0)):
        put(ref, x, 3.0)

    # BMI270 and RF launch. The MLPF sits close to the MCU RF pin; the long
    # section to the antenna is a controlled-impedance top-layer line.
    put("R38",61.5,12.5); put("R39",64.0,12.5)
    put("C58",65.5,7.0,90); put("C59",67.5,7.0,90); put("C60",69.5,7.0,90)
    put("U9",56.0,13.5,180)
    put("C65",90.5,5.2,90); put("R51",93.0,5.2); put("C66",94.0,7.0,0)
    put("R37",85.5,4.2); put("D16",88.0,4.2)

    # Battery protection, RTC reservoir and three regulator rails.
    put("D14",38.0,20.8,90); put("F1",46.0,28.5,90); put("Q1",49.0,24.5)
    put("R20",48.0,28.3,90); put("C28",50.5,28.3,90)
    put("R26",24.0,28.3); put("R27",26.5,28.3); put("R28",29.0,28.3); put("C38",31.5,28.3,90)
    # RTC hold-up parts use the otherwise empty upper strip.  The net is
    # low-current and this releases the dense power-mux area for routing.
    put("D15",33.0,2.4); put("C39",36.0,2.4,90); put("C40",38.5,2.4,90); put("C41",41.0,2.4,90)
    put("U4",62.5,24.8); put("R23",61.0,21.8); put("R24",63.5,21.8); put("R25",64.5,19.0)
    put("C29",60.5,28.3,90); put("C30",62.5,28.3,90); put("C31",64.8,28.3,90)
    put("U5",67.0,25.0); put("U6",71.8,25.0); put("U7",76.2,25.0)
    put("C32",67.0,21.0,90); put("C33",69.0,21.0,90)
    put("C34",71.0,21.0,90); put("C35",73.0,21.0,90)
    put("C36",75.0,21.0,90); put("C37",77.0,21.0,90)

    # USB pogo protection near its bottom-side contacts.
    put("F2",78.5,18.0); put("U10",80.5,23.0)
    put("R21",79.0,20.0,90); put("R22",81.0,20.0,90)

    # Switched microSD rail, source damping and pull-ups.
    put("U8",75.5,11.5)
    put("C61",72.0,9.0,90); put("R40",71.8,13.5,90)
    put("C62",79.0,9.0,90); put("C63",81.5,9.0,90); put("C64",83.5,9.0,90)
    for ref, x, y in (("R41",78.0,14.0),("R42",80.5,14.0),("R43",78.0,16.2),("R44",80.5,16.2)):
        put(ref,x,y)
    for ref, x, y in (
        ("R45",83.0,13.0),("R46",83.0,15.2),("R47",83.0,17.4),
        ("R48",83.0,19.6),("R49",83.0,21.8),("R50",83.0,24.0),
    ):
        put(ref,x,y,90)

    return p


def load_footprint(identifier: str) -> pcbnew.FOOTPRINT:
    nickname, name = identifier.split(":", 1)
    directory = PRETTY if nickname == "Holter" else FP_ROOT / f"{nickname}.pretty"
    footprint = pcbnew.FootprintLoad(str(directory), name)
    if footprint is None:
        raise FileNotFoundError(f"Cannot load {identifier} from {directory}")
    return footprint


def add_outline(board: pcbnew.BOARD) -> None:
    # 100 x 30 mm with 2-mm rounded corners.
    segments = [((2,0),(98,0)),((100,2),(100,28)),((98,30),(2,30)),((0,28),(0,2))]
    for start, end in segments:
        item = pcbnew.PCB_SHAPE(board)
        item.SetShape(pcbnew.SHAPE_T_SEGMENT)
        item.SetStart(vec(*start)); item.SetEnd(vec(*end))
        item.SetLayer(pcbnew.Edge_Cuts); item.SetWidth(mm(0.05))
        board.Add(item)
    arcs = [
        ((2,0),(0.586,0.586),(0,2)),
        ((100,2),(99.414,0.586),(98,0)),
        ((98,30),(99.414,29.414),(100,28)),
        ((0,28),(0.586,29.414),(2,30)),
    ]
    for start, mid, end in arcs:
        item = pcbnew.PCB_SHAPE(board)
        item.SetShape(pcbnew.SHAPE_T_ARC)
        item.SetArcGeometry(vec(*start), vec(*mid), vec(*end))
        item.SetLayer(pcbnew.Edge_Cuts); item.SetWidth(mm(0.05))
        board.Add(item)


def add_text(board: pcbnew.BOARD, text: str, x: float, y: float, layer: int, size: float = 0.8, rot: float = 0) -> None:
    item = pcbnew.PCB_TEXT(board)
    item.SetText(text); item.SetPosition(vec(x,y)); item.SetLayer(layer)
    item.SetTextSize(vec(size,size)); item.SetTextThickness(mm(max(0.12, size * 0.16)))
    item.SetTextAngleDegrees(rot)
    if layer == pcbnew.B_SilkS:
        item.SetMirrored(True)
    board.Add(item)


def polygon(points: list[tuple[float, float]]) -> pcbnew.SHAPE_LINE_CHAIN:
    chain = pcbnew.SHAPE_LINE_CHAIN()
    for x, y in points:
        chain.Append(vec(x,y))
    chain.SetClosed(True)
    return chain


def add_zones(board: pcbnew.BOARD, gnd: pcbnew.NETINFO_ITEM) -> None:
    # Solid reference plane on L2. A top/bottom pour is added after routing.
    plane = pcbnew.ZONE(board)
    plane.SetLayer(pcbnew.In1_Cu); plane.SetNet(gnd)
    plane.SetLocalClearance(mm(0.2)); plane.SetMinThickness(mm(0.15))
    plane.SetThermalReliefGap(mm(0.2)); plane.SetThermalReliefSpokeWidth(mm(0.25))
    plane.AddPolygon(polygon([(0.25,2),(2,0.25),(98,0.25),(99.75,2),(99.75,28),(98,29.75),(2,29.75),(0.25,28)]))
    board.Add(plane)

    # All-layer RF antenna copper keepout. Tracks are allowed only so the
    # controlled feed can reach terminal 1; zone fill and vias remain banned.
    for layer in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
        keepout = pcbnew.ZONE(board)
        keepout.SetIsRuleArea(True); keepout.SetLayer(layer)
        keepout.SetDoNotAllowZoneFills(True); keepout.SetDoNotAllowVias(True)
        keepout.SetDoNotAllowTracks(False); keepout.SetDoNotAllowPads(False); keepout.SetDoNotAllowFootprints(False)
        keepout.AddPolygon(polygon([(94.7,0.2),(99.8,0.2),(99.8,10.2),(94.7,10.2)]))
        board.Add(keepout)


def add_critical_routes(board: pcbnew.BOARD, nets: dict[str, pcbnew.NETINFO_ITEM]) -> None:
    """Route and lock the clock, RF and SMPS loops before general routing."""
    # 32 MHz HSE: both resonator nets stay on F.Cu, short, and via-free.
    add_path(
        board,
        nets["HSE_IN"],
        [pad_xy(board, "U2", "35"), (53.2, 10.5)],
        width=0.10,
    )
    add_path(
        board,
        nets["HSE_IN"],
        [(53.2, 10.5), (53.6, 10.1), pad_xy(board, "Y1", "1")],
        width=0.12,
    )
    add_path(board, nets["HSE_IN"], [pad_xy(board, "Y1", "1"), (55.3, 9.65), (55.3, 8.5), (59.5, 8.5), (59.5, 10.48), pad_xy(board, "C42", "1")], width=0.12)
    add_path(
        board,
        nets["HSE_OUT"],
        [pad_xy(board, "U2", "34"), (54.5, 11.8)],
        width=0.10,
    )
    add_path(board, nets["HSE_OUT"], [(54.5, 11.8), (54.9, 12.2), (56.5, 12.2), (56.85, 11.85), pad_xy(board, "Y1", "3")], width=0.12)
    add_path(
        board,
        nets["HSE_OUT"],
        [pad_xy(board, "Y1", "3"), (57.2, 11.85), (57.8, 12.45), pad_xy(board, "C43", "1")],
        width=0.12,
    )

    # 32.768 kHz LSE: route away from fast digital fan-out and without vias.
    add_path(
        board,
        nets["LSE_IN"],
        [pad_xy(board, "U2", "3"), (47.6, 19.5)],
        width=0.10,
    )
    add_path(
        board,
        nets["LSE_IN"],
        [
            (47.6, 19.5), (47.6, 19.8), (46.1, 19.8),
            (46.1, 19.2), (43.6, 19.2),
            pad_xy(board, "Y2", "1"),
        ],
        width=0.12,
    )
    add_path(
        board,
        nets["LSE_IN"],
        [pad_xy(board, "Y2", "1"), (42.25, 20.0), (42.0, 19.75), pad_xy(board, "C44", "1")],
        width=0.12,
    )
    add_path(
        board,
        nets["LSE_OUT"],
        [pad_xy(board, "U2", "4"), (48.0, 19.5)],
        width=0.10,
    )
    add_path(board, nets["LSE_OUT"], [(48.0, 19.5), (48.5, 20.0), (48.5, 20.5), pad_xy(board, "Y2", "2")], width=0.12)
    add_path(
        board,
        nets["LSE_OUT"],
        [pad_xy(board, "Y2", "2"), (45.8, 21.05), (45.8, 22.1), pad_xy(board, "C45", "1")],
        width=0.12,
    )

    # STM32WB RF launch into ST's matched low-pass filter.
    add_path(
        board,
        nets["RF_MCU"],
        [pad_xy(board, "U2", "31"), (54.5, 13.0)],
        width=0.10,
    )
    add_path(board, nets["RF_MCU"], [(54.5, 13.0), (55.1, 13.6), pad_xy(board, "U9", "A3")], width=0.18)
    # Nominal 50-ohm top-layer line.  The fab must tune its final width to the
    # selected 0.8-mm four-layer stackup while preserving this geometry.
    add_path(
        board,
        nets["RF_FILTER_OUT"],
        [
            pad_xy(board, "U9", "A1"), (57.1, 13.7935), (57.6, 13.2935),
            (60.5, 13.2935), (60.5, 3.0), (62.0, 1.5),
            (92.49, 1.5), pad_xy(board, "R51", "1"),
        ],
        width=0.18,
    )
    add_path(board, nets["RF_FILTER_OUT"], [pad_xy(board, "R51", "1"), (91.5, 5.2), pad_xy(board, "C65", "1")], width=0.18)
    add_path(
        board,
        nets["RF_ANT_FEED"],
        [pad_xy(board, "R51", "2"), pad_xy(board, "AE1", "1")],
        width=0.18,
    )
    add_path(
        board,
        nets["RF_ANT_FEED"],
        [(93.52, 5.2), pad_xy(board, "C66", "1")],
        width=0.18,
    )

    # STM32WB internal-SMPS loop, deliberately compact and on F.Cu only.
    add_path(board, nets["SMPS_IN"], [pad_xy(board, "U2", "44"), (49.6, 10.5)], width=0.10)
    add_path(board, nets["SMPS_IN"], [(49.6, 10.5), (49.2875, 10.1875), pad_xy(board, "L1", "2")], width=0.25)
    add_path(board, nets["SMPS_IN"], [pad_xy(board, "L1", "2"), (49.2875, 8.0), pad_xy(board, "C46", "1")], width=0.25)
    add_path(board, nets["SMPS_SW"], [pad_xy(board, "U2", "43"), (50.0, 10.5)], width=0.10)
    add_path(board, nets["SMPS_SW"], [(50.0, 10.5), (50.7, 9.8), pad_xy(board, "L2", "1")], width=0.25)
    add_path(board, nets["SMPS_FB"], [pad_xy(board, "U2", "41"), (50.8, 10.5)], width=0.10)
    add_path(board, nets["SMPS_FB"], [(50.8, 10.5), (51.3, 10.0), (52.3, 10.0), pad_xy(board, "L2", "2")], width=0.20)
    add_path(board, nets["SMPS_FB"], [pad_xy(board, "L2", "2"), (52.3, 8.0), pad_xy(board, "C47", "1")], width=0.25)

    # Short ground returns into the uninterrupted L2 ground plane.
    ground = nets["GND"]
    for ref, point in (
        ("C42", (58.0, 9.52)), ("C43", (59.2, 11.52)),
        ("C44", (41.3, 17.32)), ("C45", (43.8, 22.52)),
        ("C46", (48.5, 5.0)), ("C47", (51.5, 5.0)),
        ("C65", (90.5, 4.0)), ("C66", (94.3, 7.7)),
    ):
        add_path(board, ground, [pad_xy(board, ref, "2"), point], width=0.20)
        add_via(board, ground, *point)
    add_path(board, ground, [pad_xy(board, "U9", "B3"), pad_xy(board, "U9", "B1")], width=0.15)
    add_path(board, ground, [pad_xy(board, "U9", "A2"), (56.0, 14.5)], width=0.15)
    add_via(board, ground, 56.0, 14.5)


def main() -> None:
    design = build_design()
    placements = place_table()
    physical = [component for component in design.components if component.on_board]
    missing = sorted(component.ref for component in physical if component.ref not in placements)
    extra = sorted(set(placements) - {component.ref for component in physical})
    if missing or extra:
        raise ValueError(f"Placement mismatch: missing={missing}, extra={extra}")

    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    settings = board.GetDesignSettings()
    settings.SetBoardThickness(mm(0.8))
    settings.m_TrackMinWidth = mm(0.10)
    settings.m_MinClearance = mm(0.10)
    settings.m_ViasMinAnnularWidth = mm(0.10)
    settings.m_ViasMinSize = mm(0.45)
    settings.m_MinThroughDrill = mm(0.20)
    settings.m_CopperEdgeClearance = mm(0.20)
    settings.m_HoleClearance = mm(0.20)
    settings.m_SilkClearance = mm(0.15)
    settings.m_MinSilkTextHeight = mm(0.50)
    settings.m_MinSilkTextThickness = mm(0.10)
    default_class = board.GetAllNetClasses()["Default"]
    default_class.SetClearance(mm(0.10))
    default_class.SetTrackWidth(mm(0.15))
    default_class.SetViaDiameter(mm(0.45))
    default_class.SetViaDrill(mm(0.20))

    add_outline(board)

    # Create every named net before assigning pads.
    net_names = sorted({net for component in physical for net in component.nets.values() if net})
    nets: dict[str, pcbnew.NETINFO_ITEM] = {}
    for net_name in net_names:
        net = pcbnew.NETINFO_ITEM(board, net_name)
        board.Add(net); nets[net_name] = net

    for component in physical:
        footprint = load_footprint(component.footprint)
        footprint.SetReference(component.ref); footprint.SetValue(component.value)
        footprint.SetPath(pcbnew.KIID_PATH(uid(f"component/{component.ref}")))
        footprint.SetDNP(component.dnp)
        footprint.SetExcludedFromBOM(not component.in_bom)
        footprint.SetExcludedFromPosFiles(component.dnp or not component.in_bom)
        x, y, rotation = placements[component.ref]
        footprint.SetPosition(vec(x,y)); footprint.SetOrientationDegrees(rotation)
        footprint.Reference().SetVisible(False)
        footprint.Value().SetVisible(False)
        for field in (footprint.Reference(), footprint.Value()):
            field.SetTextSize(vec(0.8,0.8)); field.SetTextThickness(mm(0.12))
        # Dense wearable boards are assembled from the fabrication drawing and
        # position file.  Retain package silk only where it communicates a
        # mechanical boundary; all other reference/body artwork lives on Fab.
        if component.ref not in {"J1", "J2", "J4", "AE1"}:
            for drawing in list(footprint.GraphicalItems()):
                if isinstance(drawing, pcbnew.PCB_SHAPE) and drawing.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                    drawing.SetLayer(pcbnew.F_Fab)
        for pad in footprint.Pads():
            pad_number = pad.GetNumber()
            net_name = component.nets.get(pad_number)
            if net_name:
                pad.SetNet(nets[net_name])
                pad.SetPinFunction(next((pin.name for pin in design.symbol_types[component.kind].pins if pin.number == pad_number), ""))
        board.Add(footprint)

    board.BuildListOfNets()
    add_zones(board, nets["GND"])
    add_critical_routes(board, nets)

    add_text(board, "HOLTER V1 | RESEARCH ONLY", 18, 1.0, pcbnew.F_SilkS, 0.65)
    add_text(board, "DISCONNECT ELECTRODES BEFORE USB", 62, 1.0, pcbnew.F_SilkS, 0.65)
    add_text(board, "ECG", 1.0, 6.0, pcbnew.F_SilkS, 0.8, 90)
    add_text(board, "microSD", 98.7, 17.0, pcbnew.F_SilkS, 0.7, 90)
    add_text(board, "ANT KEEP-OUT", 96.0, 10.8, pcbnew.F_SilkS, 0.55)
    add_text(board, "VBUS  D-  D+  GND", 79.0, 25.2, pcbnew.B_SilkS, 0.55)
    add_text(board, "3V  G  DIO CLK RST", 55.0, 26.0, pcbnew.B_SilkS, 0.5)

    board.SynchronizeNetsAndNetClasses(False)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(OUT), board)
    print(f"Saved {OUT}: {len(physical)} footprints, {len(net_names)} nets")


if __name__ == "__main__":
    main()
