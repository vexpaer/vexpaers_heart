#!/usr/bin/env python3
"""Generate the placed and routed two-layer USB-C pogo dock PCB."""

from __future__ import annotations

from pathlib import Path

import pcbnew

from generate_dock import HW, PRETTY, build_design
from generate_hardware import uid


KICAD_ROOT = Path(pcbnew.__file__).resolve().parents[4]
FP_ROOT = KICAD_ROOT / "share" / "kicad" / "footprints"
OUT = HW / "usb_pogo_dock.kicad_pcb"


def mm(value: float) -> int:
    return pcbnew.FromMM(value)


def vec(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(x), mm(y))


def load_footprint(identifier: str) -> pcbnew.FOOTPRINT:
    nickname, name = identifier.split(":", 1)
    directory = PRETTY if nickname == "Dock" else FP_ROOT / f"{nickname}.pretty"
    footprint = pcbnew.FootprintLoad(str(directory), name)
    if footprint is None:
        raise FileNotFoundError(f"Cannot load {identifier} from {directory}")
    return footprint


def add_outline(board: pcbnew.BOARD) -> None:
    # 42 x 24 mm, 2-mm corner radius.  The USB-C shell intentionally projects
    # through the left edge of the fixture enclosure.
    for start, end in [((2, 0), (40, 0)), ((42, 2), (42, 22)), ((40, 24), (2, 24)), ((0, 22), (0, 2))]:
        shape = pcbnew.PCB_SHAPE(board)
        shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
        shape.SetStart(vec(*start)); shape.SetEnd(vec(*end))
        shape.SetLayer(pcbnew.Edge_Cuts); shape.SetWidth(mm(0.05))
        board.Add(shape)
    for start, mid, end in [
        ((2, 0), (0.586, 0.586), (0, 2)),
        ((42, 2), (41.414, 0.586), (40, 0)),
        ((40, 24), (41.414, 23.414), (42, 22)),
        ((0, 22), (0.586, 23.414), (2, 24)),
    ]:
        shape = pcbnew.PCB_SHAPE(board)
        shape.SetShape(pcbnew.SHAPE_T_ARC)
        shape.SetArcGeometry(vec(*start), vec(*mid), vec(*end))
        shape.SetLayer(pcbnew.Edge_Cuts); shape.SetWidth(mm(0.05))
        board.Add(shape)


def polygon(points: list[tuple[float, float]]) -> pcbnew.SHAPE_LINE_CHAIN:
    chain = pcbnew.SHAPE_LINE_CHAIN()
    for x, y in points:
        chain.Append(vec(x, y))
    chain.SetClosed(True)
    return chain


def add_ground_zones(board: pcbnew.BOARD, gnd: pcbnew.NETINFO_ITEM) -> None:
    outline = [(0.3, 2), (2, 0.3), (40, 0.3), (41.7, 2), (41.7, 22), (40, 23.7), (2, 23.7), (0.3, 22)]
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        zone = pcbnew.ZONE(board)
        zone.SetLayer(layer); zone.SetNet(gnd)
        zone.SetLocalClearance(mm(0.2)); zone.SetMinThickness(mm(0.18))
        zone.SetThermalReliefGap(mm(0.25)); zone.SetThermalReliefSpokeWidth(mm(0.3))
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        zone.AddPolygon(polygon(outline)); board.Add(zone)


def add_text(board: pcbnew.BOARD, text: str, x: float, y: float, layer: int, size: float = 0.7, rot: float = 0) -> None:
    item = pcbnew.PCB_TEXT(board)
    item.SetText(text); item.SetPosition(vec(x, y)); item.SetLayer(layer)
    item.SetTextSize(vec(size, size)); item.SetTextThickness(mm(max(0.12, size * 0.16)))
    item.SetTextAngleDegrees(rot)
    if layer == pcbnew.B_SilkS:
        item.SetMirrored(True)
    board.Add(item)


def add_path(
    board: pcbnew.BOARD,
    net: pcbnew.NETINFO_ITEM,
    points: list[tuple[float, float]],
    *,
    layer: int = pcbnew.F_Cu,
    width: float = 0.2,
) -> None:
    for start, end in zip(points, points[1:]):
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(vec(*start)); track.SetEnd(vec(*end))
        track.SetLayer(layer); track.SetWidth(mm(width)); track.SetNet(net)
        board.Add(track)


def add_via(board: pcbnew.BOARD, net: pcbnew.NETINFO_ITEM, x: float, y: float, diameter: float = 0.6, drill: float = 0.3) -> None:
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(vec(x, y)); via.SetWidth(mm(diameter)); via.SetDrill(mm(drill))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); via.SetNet(net)
    board.Add(via)


def main() -> None:
    design = build_design()
    physical = [component for component in design.components if component.on_board]
    placements = {
        "J1": (5.0, 12.0, -90),
        "R1": (11.0, 5.0, 90), "R2": (11.0, 19.0, -90),
        "D1": (15.0, 6.5, 90), "F1": (19.0, 6.5, 0),
        "U1": (18.0, 12.0, 0), "J2": (34.0, 12.0, 0),
        "R3": (14.0, 18.5, 90), "C1": (18.0, 18.5, 90), "R4": (22.0, 18.5, 90),
        "R5": (25.0, 6.5, 0), "D2": (28.0, 6.5, 180),
    }
    missing = sorted(c.ref for c in physical if c.ref not in placements)
    if missing:
        raise ValueError(f"Missing dock placements: {missing}")

    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)
    settings = board.GetDesignSettings()
    settings.SetBoardThickness(mm(1.6))
    settings.m_TrackMinWidth = mm(0.10)
    settings.m_MinClearance = mm(0.15)
    settings.m_ViasMinSize = mm(0.45)
    settings.m_ViasMinAnnularWidth = mm(0.10)
    settings.m_MinThroughDrill = mm(0.20)
    settings.m_CopperEdgeClearance = mm(0.25)
    settings.m_HoleClearance = mm(0.25)
    settings.m_SilkClearance = mm(0.15)
    settings.m_MinSilkTextHeight = mm(0.5)
    settings.m_MinSilkTextThickness = mm(0.1)
    default_class = board.GetAllNetClasses()["Default"]
    default_class.SetClearance(mm(0.15)); default_class.SetTrackWidth(mm(0.2))
    default_class.SetViaDiameter(mm(0.6)); default_class.SetViaDrill(mm(0.3))
    add_outline(board)

    net_names = sorted({net for component in physical for net in component.nets.values() if net})
    nets: dict[str, pcbnew.NETINFO_ITEM] = {}
    for net_name in net_names:
        net = pcbnew.NETINFO_ITEM(board, net_name)
        board.Add(net); nets[net_name] = net

    for component in physical:
        footprint = load_footprint(component.footprint)
        footprint.SetReference(component.ref); footprint.SetValue(component.value)
        footprint.SetPath(pcbnew.KIID_PATH(uid(f"dock/component/{component.ref}")))
        footprint.SetDNP(component.dnp)
        footprint.SetExcludedFromPosFiles(component.dnp)
        x, y, rotation = placements[component.ref]
        footprint.SetPosition(vec(x, y)); footprint.SetOrientationDegrees(rotation)
        footprint.Reference().SetVisible(False); footprint.Value().SetVisible(False)
        # Assembly references stay available on Fab; the production silk is
        # intentionally limited to interface and safety labels.
        if component.ref not in {"J1", "J2"}:
            for drawing in footprint.GraphicalItems():
                if isinstance(drawing, pcbnew.PCB_SHAPE) and drawing.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                    drawing.SetLayer(pcbnew.F_Fab)
        for pad in footprint.Pads():
            net_name = component.nets.get(pad.GetNumber())
            if net_name:
                pad.SetNet(nets[net_name])
        board.Add(footprint)

    # Four M2 fixture fasteners are board-only mechanical items.
    for index, (x, y) in enumerate(((32, 3.5), (39, 3.5), (32, 20.5), (39, 20.5)), 1):
        hole = load_footprint("MountingHole:MountingHole_2.2mm_M2")
        hole.SetReference(f"H{index}"); hole.SetValue("M2 FIXTURE")
        hole.SetPosition(vec(x, y)); hole.SetBoardOnly(True)
        hole.Reference().SetVisible(False); hole.Value().SetVisible(False)
        board.Add(hole)

    board.BuildListOfNets()
    add_ground_zones(board, nets["GND"])

    def pad_xy(ref: str, number: str) -> tuple[float, float]:
        footprint = board.FindFootprintByReference(ref)
        pad = footprint.FindPadByNumber(number)
        position = pad.GetPosition()
        return pcbnew.ToMM(position.x), pcbnew.ToMM(position.y)

    # USB-C reversible data fan-in.  The interleaved A/B contact order needs
    # one short bottom-layer crossover; the protected onward pair stays on F.Cu.
    dp = nets["USB_DP"]
    dm = nets["USB_DM"]
    add_path(board, dp, [pad_xy("J1", "A6"), (15.0, 11.75)], width=0.10)
    add_path(board, dp, [(15.0, 11.75), (16.2, 11.05), pad_xy("U1", "1")])
    add_path(board, dp, [pad_xy("J1", "B6"), (11.6, 12.75)], width=0.10)
    add_path(board, dp, [(11.6, 12.75), (11.6, 14.3)], width=0.15)
    add_via(board, dp, 11.6, 14.3)
    add_path(board, dp, [(11.6, 14.3), (13.4, 16.0), (17.0, 16.0), (17.0, 10.5)], layer=pcbnew.B_Cu)

    add_path(board, dm, [pad_xy("J1", "B7"), (11.6, 11.25)], width=0.10)
    add_path(board, dm, [(11.6, 11.25), (12.2, 8.8), (20.0, 8.8), (20.8, 10.5), (21.0, 12.0), pad_xy("U1", "3")])
    add_path(board, dm, [pad_xy("J1", "A7"), (12.2, 12.25)], width=0.10)
    add_path(board, dm, [(12.2, 12.25), (12.2, 15.0), (20.2, 15.0), (21.0, 13.0), (21.0, 12.0)])

    # The DP trunk crosses the reversible-connector fan-in on B.Cu; DM remains
    # on F.Cu.  Both are referenced to the opposite-layer ground pour.
    add_path(board, dp, [pad_xy("U1", "1"), (17.5, 9.5)])
    add_via(board, dp, 17.5, 9.5)
    add_path(board, dp, [(17.0, 10.5), (17.5, 9.5), (33.5, 9.5), pad_xy("J2", "3")], layer=pcbnew.B_Cu)
    add_path(board, dm, [pad_xy("U1", "3"), (21.0, 12.0), (21.5, 14.3), (22.0, 14.3),
                         (22.8, 15.5), (23.6, 14.3), (24.4, 15.5), (25.2, 14.3),
                         (31.5, 14.3), pad_xy("J2", "2")])

    # USB-C CC pull-downs.
    add_path(board, nets["CC1"], [pad_xy("J1", "A5"), (10.6, 10.75)], width=0.10)
    add_via(board, nets["CC1"], 10.6, 10.75)
    add_path(board, nets["CC1"], [(10.6, 10.75), (12.5, 9.8), (12.5, 5.5), (11.8, 5.5)], layer=pcbnew.B_Cu, width=0.10)
    add_via(board, nets["CC1"], 11.8, 5.5)
    add_path(board, nets["CC1"], [(11.8, 5.5), pad_xy("R1", "1")], width=0.10)
    add_path(board, nets["CC2"], [pad_xy("J1", "B5"), (10.8, 13.75)], width=0.10)
    add_path(board, nets["CC2"], [(10.8, 13.75), (10.8, 18.0), pad_xy("R2", "1")], width=0.10)

    # Connector VBUS branches, ESD clamp and 500-mA resettable fuse.
    vbus_in = nets["VBUS_CONN"]
    add_path(board, vbus_in, [pad_xy("J1", "A4"), (11.5, 9.55), (12.0, 8.0)], width=0.10)
    add_path(board, vbus_in, [(12.0, 8.0), (12.5, 7.5), pad_xy("D1", "1")], width=0.5)
    add_path(board, vbus_in, [pad_xy("D1", "1"), pad_xy("F1", "1")], width=0.5)
    add_path(board, vbus_in, [pad_xy("J1", "A9"), (10.0, 14.45), (10.0, 15.5), (9.8, 16.0)], width=0.10)
    add_via(board, vbus_in, 9.8, 16.0, 0.45, 0.20)
    add_path(board, vbus_in, [(9.8, 16.0), (9.8, 7.2)], layer=pcbnew.B_Cu, width=0.5)
    add_via(board, vbus_in, 9.8, 7.2, 0.7, 0.35)
    add_path(board, vbus_in, [(9.8, 7.2), (12.0, 8.0)], width=0.10)

    vbus_out = nets["VBUS_POGO"]
    add_path(board, vbus_out, [pad_xy("F1", "2"), pad_xy("R5", "1")], width=0.5)
    add_path(board, vbus_out, [pad_xy("F1", "2"), (20.5, 5.0), (29.5, 5.0), (30.2, 9.0), pad_xy("J2", "1")], width=0.5)
    add_path(board, nets["DOCK_LED_A"], [pad_xy("R5", "2"), pad_xy("D2", "2")])

    # Cable shield is kept distinct from signal ground.  The upper shell tie
    # stays on F.Cu so it does not close a B.Cu loop around the connector-side
    # ground vias; the remaining shell tabs meet the RC/optional bond on F.Cu.
    shell = nets["USB_SHIELD"]
    shell_tabs = sorted(
        [(pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y))
         for p in board.FindFootprintByReference("J1").Pads() if p.GetNumber() == "SH"],
        key=lambda point: (point[1], point[0]),
    )
    left_top, right_top, left_bottom, right_bottom = shell_tabs
    add_path(board, shell, [left_top, right_top], layer=pcbnew.F_Cu, width=0.4)
    add_path(board, shell, [left_top, left_bottom, right_bottom], layer=pcbnew.B_Cu, width=0.4)
    add_path(board, shell, [right_bottom, (9.0, 17.5), (13.0, 17.5), (13.0, 20.5)], layer=pcbnew.B_Cu, width=0.3)
    add_via(board, shell, 13.0, 20.5, 0.6, 0.3)
    add_path(board, shell, [(13.0, 20.5), pad_xy("R3", "1")], width=0.3)
    add_path(board, shell, [pad_xy("R3", "1"), (15.5, 20.5), pad_xy("C1", "1"), (19.5, 20.5), pad_xy("R4", "1")], width=0.3)

    # Stitch the two ground pours together independently of the pogo contact.
    add_via(board, nets["GND"], *pad_xy("J1", "A1"), 0.45, 0.20)
    add_via(board, nets["GND"], *pad_xy("J1", "A12"), 0.45, 0.20)
    for x, y in ((17.8, 13.4), (24.0, 3.0), (24.0, 12.0), (24.0, 21.0), (40.0, 12.0)):
        add_via(board, nets["GND"], x, y, 0.7, 0.35)

    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    add_text(board, "HOLTER V1 USB POGO DOCK", 18.5, 1.2, pcbnew.F_SilkS, 0.65)
    add_text(board, "FIXTURE ONLY", 19.0, 22.8, pcbnew.F_SilkS, 0.65)
    add_text(board, "VBUS  D-  D+  GND", 34.0, 9.1, pcbnew.F_SilkS, 0.55)
    add_text(board, "INTERLOCK: ECG PLUG MUST BE ABSENT", 21.0, 22.8, pcbnew.B_SilkS, 0.55)

    board.SynchronizeNetsAndNetClasses(False)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(OUT), board)
    print(f"Saved placed dock board: {len(physical)} electrical footprints, {len(net_names)} nets")


if __name__ == "__main__":
    main()
