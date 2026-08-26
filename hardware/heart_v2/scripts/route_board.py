#!/usr/bin/env python3
"""Deliberate, reproducible routing for the Heart V2 PCB.

This is not a global autorouter.  Every routed group below is selected by
function and follows a hand-authored topology: patient input first, then clock,
SMPS, RF, USB, storage, power, and finally ordinary low-speed buses.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pcbnew


ROOT = Path(__file__).resolve().parents[1]
BOARD_PATH = ROOT / "heart_v2.kicad_pcb"


def mm(value: float) -> int:
    return pcbnew.FromMM(value)


def xy(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(x), mm(y))


def as_mm(point: pcbnew.VECTOR2I) -> tuple[float, float]:
    return pcbnew.ToMM(point.x), pcbnew.ToMM(point.y)


class Router:
    def __init__(self, board: pcbnew.BOARD) -> None:
        self.board = board
        self.footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}
        self.nets = board.GetNetsByName()

    def pad(self, reference: str, number: str, occurrence: int = 0) -> pcbnew.PAD:
        matches = [
            pad
            for pad in self.footprints[reference].Pads()
            if pad.GetNumber() == str(number)
        ]
        if occurrence >= len(matches):
            raise KeyError(f"pad not found: {reference}.{number}[{occurrence}]")
        return matches[occurrence]

    def point(self, endpoint: tuple[str, str] | tuple[float, float]) -> pcbnew.VECTOR2I:
        if isinstance(endpoint[0], str):
            return self.pad(endpoint[0], endpoint[1]).GetPosition()
        return xy(endpoint[0], endpoint[1])

    def net_name(self, endpoint: tuple[str, str]) -> str:
        return self.pad(endpoint[0], endpoint[1]).GetNetname()

    def net_code(self, name: str) -> int:
        if name not in self.nets:
            raise KeyError(f"net not found: {name}")
        return self.nets[name].GetNetCode()

    def segment(
        self,
        net_name: str,
        start: pcbnew.VECTOR2I,
        end: pcbnew.VECTOR2I,
        layer: int = pcbnew.F_Cu,
        width: float = 0.18,
    ) -> None:
        if start == end:
            return
        track = pcbnew.PCB_TRACK(self.board)
        track.SetStart(start)
        track.SetEnd(end)
        track.SetWidth(mm(width))
        track.SetLayer(layer)
        track.SetNetCode(self.net_code(net_name))
        self.board.Add(track)

    def leg45(
        self,
        net_name: str,
        start: pcbnew.VECTOR2I,
        end: pcbnew.VECTOR2I,
        layer: int = pcbnew.F_Cu,
        width: float = 0.18,
        horizontal_first: bool = True,
    ) -> None:
        sx, sy = as_mm(start)
        ex, ey = as_mm(end)
        dx, dy = ex - sx, ey - sy
        epsilon = 1e-6
        if abs(dx) < epsilon or abs(dy) < epsilon or abs(abs(dx) - abs(dy)) < epsilon:
            self.segment(net_name, start, end, layer, width)
            return

        sign_x = 1.0 if dx > 0 else -1.0
        sign_y = 1.0 if dy > 0 else -1.0
        if horizontal_first:
            if abs(dx) >= abs(dy):
                corner = xy(ex - sign_x * abs(dy), sy)
            else:
                corner = xy(sx, ey - sign_y * abs(dx))
        else:
            if abs(dy) >= abs(dx):
                corner = xy(sx, ey - sign_y * abs(dx))
            else:
                corner = xy(ex - sign_x * abs(dy), sy)
        self.segment(net_name, start, corner, layer, width)
        self.segment(net_name, corner, end, layer, width)

    def connect(
        self,
        start: tuple[str, str],
        end: tuple[str, str],
        *waypoints: tuple[float, float],
        layer: int = pcbnew.F_Cu,
        width: float = 0.18,
        horizontal_first: bool = True,
    ) -> None:
        net_name = self.net_name(start)
        other_net = self.net_name(end)
        if net_name != other_net:
            raise ValueError(f"net mismatch: {start}={net_name}, {end}={other_net}")
        points = [self.point(start), *(xy(*point) for point in waypoints), self.point(end)]
        for first, second in zip(points, points[1:]):
            self.leg45(net_name, first, second, layer, width, horizontal_first)

    def via(
        self,
        net_name: str,
        point: tuple[float, float],
        diameter: float = 0.50,
        drill: float = 0.20,
    ) -> None:
        via = pcbnew.PCB_VIA(self.board)
        via.SetPosition(xy(*point))
        via.SetWidth(mm(diameter))
        via.SetDrill(mm(drill))
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNetCode(self.net_code(net_name))
        self.board.Add(via)

    def change_layer(
        self,
        start: tuple[str, str],
        end: tuple[str, str],
        start_via: tuple[float, float],
        end_via: tuple[float, float],
        *waypoints: tuple[float, float],
        layer: int = pcbnew.B_Cu,
        width: float = 0.18,
    ) -> None:
        net_name = self.net_name(start)
        if net_name != self.net_name(end):
            raise ValueError(f"net mismatch: {start}, {end}")
        self.leg45(net_name, self.point(start), xy(*start_via), pcbnew.F_Cu, width)
        self.via(net_name, start_via)
        route_points = [xy(*start_via), *(xy(*p) for p in waypoints), xy(*end_via)]
        for first, second in zip(route_points, route_points[1:]):
            self.leg45(net_name, first, second, layer, width)
        self.via(net_name, end_via)
        self.leg45(net_name, xy(*end_via), self.point(end), pcbnew.F_Cu, width)

    def path(
        self,
        net_name: str,
        points: Iterable[tuple[float, float]],
        layer: int = pcbnew.F_Cu,
        width: float = 0.18,
    ) -> None:
        vectors = [xy(*point) for point in points]
        for first, second in zip(vectors, vectors[1:]):
            self.segment(net_name, first, second, layer, width)

    def bottom_to_top(
        self,
        start: tuple[str, str],
        end: tuple[str, str],
        via_point: tuple[float, float],
        bottom_waypoints: Iterable[tuple[float, float]] = (),
        top_waypoints: Iterable[tuple[float, float]] = (),
        width: float = 0.18,
    ) -> None:
        net_name = self.net_name(start)
        if net_name != self.net_name(end):
            raise ValueError(f"net mismatch: {start}, {end}")
        bottom = [self.point(start), *(xy(*p) for p in bottom_waypoints), xy(*via_point)]
        for first, second in zip(bottom, bottom[1:]):
            self.leg45(net_name, first, second, pcbnew.B_Cu, width)
        self.via(net_name, via_point)
        top = [xy(*via_point), *(xy(*p) for p in top_waypoints), self.point(end)]
        for first, second in zip(top, top[1:]):
            self.leg45(net_name, first, second, pcbnew.F_Cu, width)

    def plane_drop(
        self,
        start: tuple[str, str],
        via_point: tuple[float, float],
        *,
        layer: int = pcbnew.F_Cu,
        width: float = 0.25,
        diameter: float = 0.50,
    ) -> None:
        net_name = self.net_name(start)
        self.leg45(net_name, self.point(start), xy(*via_point), layer, width)
        self.via(net_name, via_point, diameter=diameter, drill=0.20)

    def zone(
        self,
        net_name: str,
        layer: int,
        points: Iterable[tuple[float, float]],
        clearance: float = 0.15,
    ) -> None:
        zone = pcbnew.ZONE(self.board)
        zone.SetLayer(layer)
        zone.SetNetCode(self.net_code(net_name))
        zone.SetLocalClearance(mm(clearance))
        zone.SetMinThickness(mm(0.15))
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        zone.SetThermalReliefGap(mm(0.20))
        zone.SetThermalReliefSpokeWidth(mm(0.25))
        self.board.Add(zone)
        outline = zone.Outline()
        outline.NewOutline()
        for point in points:
            outline.Append(xy(*point))

    def antenna_keepout(self) -> None:
        keepout = pcbnew.ZONE(self.board)
        keepout.SetIsRuleArea(True)
        keepout.SetLayerSet(pcbnew.LSET.AllCuMask(self.board.GetCopperLayerCount()))
        keepout.SetDoNotAllowZoneFills(True)
        keepout.SetDoNotAllowVias(True)
        keepout.SetDoNotAllowTracks(False)  # the controlled RF feed must enter
        keepout.SetDoNotAllowPads(False)
        keepout.SetDoNotAllowFootprints(False)
        self.board.Add(keepout)
        outline = keepout.Outline()
        outline.NewOutline()
        for point in [(109.8, 18.4), (119.6, 18.4), (119.6, 35.0), (109.8, 35.0)]:
            outline.Append(xy(*point))

    def named_rule_area(
        self, name: str, points: Iterable[tuple[float, float]]
    ) -> None:
        area = pcbnew.ZONE(self.board)
        area.SetIsRuleArea(True)
        area.SetZoneName(name)
        area.SetLayerSet(pcbnew.LSET.AllCuMask(self.board.GetCopperLayerCount()))
        area.SetDoNotAllowZoneFills(False)
        area.SetDoNotAllowVias(False)
        area.SetDoNotAllowTracks(False)
        area.SetDoNotAllowPads(False)
        area.SetDoNotAllowFootprints(False)
        self.board.Add(area)
        outline = area.Outline()
        outline.NewOutline()
        for point in points:
            outline.Append(xy(*point))


def clear_copper(board: pcbnew.BOARD) -> None:
    for item in list(board.GetTracks()):
        board.Delete(item)
    for zone in list(board.Zones()):
        board.Delete(zone)


def route_ecg(r: Router) -> None:
    # Connector-side ESD and current limiting.
    # Each electrode enters its shunt diode from the signal-pad side.  The
    # explicit 45-degree fans avoid grazing the diode's adjacent ground pad.
    r.path("/RA_ELEC", [(25.275, 32.0), (25.925, 31.35), (27.2, 31.35)], width=0.20)
    r.path("/RA_ELEC", [(27.2, 31.35), (28.0, 31.35), (28.55, 30.8), (29.175, 30.8)], width=0.20)
    r.path("/LA_ELEC", [(25.275, 33.2), (25.375, 33.1), (27.2, 33.1)], width=0.20)
    r.path("/LA_ELEC", [(27.2, 33.1), (29.075, 33.1), (29.175, 33.0)], width=0.20)
    r.path("/LL_ELEC", [(25.275, 34.4), (25.725, 34.85), (27.2, 34.85)], width=0.20)
    r.path("/LL_ELEC", [(27.2, 34.85), (28.825, 34.85), (29.175, 35.2)], width=0.20)
    r.path("/RL_ELEC", [(25.275, 35.6), (26.275, 36.6), (27.2, 36.6)], width=0.20)
    r.path("/V5_ELEC", [(25.275, 36.8), (26.825, 38.35), (27.2, 38.35)], width=0.20)
    r.path("/V5_ELEC", [(27.2, 38.35), (28.0, 38.35), (28.95, 37.4), (29.175, 37.4)], width=0.20)

    rl_net = "/RL_ELEC"
    r.segment(rl_net, r.point(("D5", "1")), xy(28.4, 36.6), pcbnew.F_Cu, 0.20)
    r.via(rl_net, (28.4, 36.6))
    r.path(rl_net, [(28.4, 36.6), (28.4, 40.5), (43.0, 40.5)], pcbnew.B_Cu, 0.20)
    r.via(rl_net, (28.2, 40.5))
    r.path(rl_net, [(28.4, 40.5), (28.2, 40.5)], pcbnew.B_Cu, 0.20)
    r.leg45(rl_net, xy(28.2, 40.5), r.point(("C10", "1")), pcbnew.F_Cu, 0.20)
    r.via(rl_net, (43.0, 40.5))
    r.leg45(rl_net, xy(43.0, 40.5), r.point(("R11", "2")), pcbnew.F_Cu, 0.20)
    r.connect(("J1", "6"), ("C11", "1"), width=0.20)
    r.connect(("C11", "1"), ("R12", "1"), width=0.20)

    # Four protected lead nodes.  The one unavoidable topology crossover is
    # moved to B.Cu after the clamp pair, well away from the patient connector.
    for a, b in [
        (("R1", "2"), ("C1", "1")),
        (("C1", "1"), ("D7", "1")),
        (("D7", "1"), ("D6", "2")),
        (("R4", "2"), ("C4", "1")),
        (("C4", "1"), ("D9", "1")),
        (("D9", "1"), ("D8", "2")),
        (("R6", "2"), ("C6", "1")),
        (("C6", "1"), ("D11", "1")),
        (("D11", "1"), ("D10", "2")),
        (("R8", "2"), ("C8", "1")),
        (("C8", "1"), ("D13", "1")),
        (("D13", "1"), ("D12", "2")),
    ]:
        r.connect(a, b, width=0.20)

    r.connect(("D6", "2"), ("R2", "1"), (38.5, 31.5), width=0.20)
    r.connect(("R2", "1"), ("R3", "1"), (41.8, 32.4), width=0.20)
    r.change_layer(("D8", "2"), ("R5", "1"), (37.0, 33.65), (41.5, 30.0), width=0.20)
    r.connect(("D10", "2"), ("R7", "1"), width=0.20)
    r.connect(("D12", "2"), ("R9", "1"), width=0.20)

    # Matched input resistor-to-shunt-cap sections.  BGA fan-in is escaped in
    # its own ordered breakout below, rather than drawing across adjacent balls.
    for resistor, capacitor, ball in [
        (("R5", "2"), ("C5", "1"), ("U1", "H1")),
        (("R2", "2"), ("C2", "1"), ("U1", "H2")),
        (("R3", "2"), ("C3", "1"), ("U1", "G2")),
        (("R7", "2"), ("C7", "1"), ("U1", "G1")),
        (("R9", "2"), ("C9", "1"), ("U1", "F1")),
    ]:
        r.connect(resistor, capacitor, width=0.18)


def route_ads_analog(r: Router) -> None:
    # Outer-row ECG balls can leave on F.Cu.  The two second-row inputs use
    # identical dog-bones and parallel B.Cu fan-in, keeping the electrode-side
    # filtering ordered and visually symmetric.
    r.path(
        "/ADS_CH1P",
        [(45.8, 29.48), (46.3, 29.48), (48.4, 31.58), (48.4, 32.2), (49.2, 32.2)],
        width=0.15,
    )
    r.path(
        "/ADS_CH2P",
        [(45.8, 35.48), (46.4, 35.48), (48.4, 33.48), (48.4, 33.0), (49.2, 33.0)],
        width=0.15,
    )
    r.segment("/ADS_CH3P", r.point(("U1", "F1")), xy(49.6, 34.2), pcbnew.F_Cu, 0.15)
    r.via("/ADS_CH3P", (49.6, 34.2), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_CH3P",
        [(49.6, 34.2), (48.4, 35.4), (48.4, 35.88), (46.8, 37.48)],
        pcbnew.In2_Cu,
        0.15,
    )
    r.via("/ADS_CH3P", (46.8, 37.48))
    r.segment("/ADS_CH3P", xy(46.8, 37.48), r.point(("C9", "1")), pcbnew.F_Cu, 0.15)

    for net_name, ball, escape, landing in [
        ("/ADS_CH1N", ("U1", "H2"), (49.6, 31.8), (46.8, 31.48)),
        ("/ADS_CH2N", ("U1", "G2"), (49.6, 32.6), (46.8, 33.48)),
    ]:
        r.segment(net_name, r.point(ball), xy(*escape), pcbnew.F_Cu, 0.15)
        r.via(net_name, escape, diameter=0.45, drill=0.20)
        r.via(net_name, landing)
    r.path(
        "/ADS_CH1N",
        [(49.6, 31.8), (49.0, 31.2), (47.08, 31.2), (46.8, 31.48)],
        pcbnew.B_Cu,
        0.15,
    )
    r.segment("/ADS_CH1N", xy(46.8, 31.48), r.point(("C2", "1")), pcbnew.F_Cu, 0.15)
    r.path(
        "/ADS_CH2N",
        [(49.6, 32.6), (49.0, 33.2), (47.08, 33.2), (46.8, 33.48)],
        pcbnew.B_Cu,
        0.15,
    )
    r.segment("/ADS_CH2N", xy(46.8, 33.48), r.point(("C3", "1")), pcbnew.F_Cu, 0.15)

    # Channel 4 leaves beneath the BGA as an ordered pair.  CH4P takes the
    # quiet upper corridor before returning to F.Cu; CH4N uses the lower lane.
    r.segment("/ADS_CH4P", r.point(("U1", "E1")), xy(48.4, 34.6), pcbnew.F_Cu, 0.15)
    r.via("/ADS_CH4P", (48.4, 34.6), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_CH4P",
        [(48.4, 34.6), (47.8, 35.2), (45.6, 35.2), (44.8, 34.4), (44.8, 27.5), (61.5, 27.5), (62.0, 28.0)],
        pcbnew.In2_Cu,
        0.15,
    )
    r.via("/ADS_CH4P", (62.0, 28.0))
    r.path(
        "/ADS_CH4P",
        [(62.0, 28.0), (62.8, 28.8), (62.8, 31.0), (61.3, 32.5), (60.0, 32.5)],
        width=0.15,
    )
    r.path(
        "/ADS_CH4P",
        [(60.0, 32.5), (59.4, 33.1), (59.4, 33.9), (60.49, 35.0)],
        width=0.15,
    )

    r.segment("/ADS_CH4N", r.point(("U1", "E2")), xy(49.6, 35.0), pcbnew.F_Cu, 0.15)
    r.via("/ADS_CH4N", (49.6, 35.0), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_CH4N",
        [
            (49.6, 35.0),
            (50.2, 35.6),
            (50.2, 39.8),
            (56.0, 39.8),
            (56.8, 40.6),
            (59.2, 40.6),
            (60.0, 39.8),
            (60.0, 38.5),
        ],
        pcbnew.B_Cu,
        0.15,
    )
    r.via("/ADS_CH4N", (60.0, 38.5))
    r.segment("/ADS_CH4N", xy(60.0, 38.5), r.point(("R17", "1")), pcbnew.F_Cu, 0.15)
    r.path("/ADS_CH4N", [(50.2, 39.8), (50.2, 44.0)], pcbnew.B_Cu, 0.15)
    r.via("/ADS_CH4N", (50.2, 44.0))
    r.segment("/ADS_CH4N", xy(50.2, 44.0), r.point(("TP2", "1")), pcbnew.F_Cu, 0.15)

    # RLD and WCT use separate escape layers so their compact feedback network
    # does not cross the channel-4 pair underneath the BGA.
    r.path(
        "/ADS_RLDIN",
        [(50.8, 37.8), (50.8, 39.3), (51.0, 39.5), (51.0, 40.19)],
        width=0.15,
    )

    r.segment("/ADS_RLDOUT", r.point(("U1", "B3")), xy(51.2, 37.4), pcbnew.F_Cu, 0.15)
    r.via("/ADS_RLDOUT", (51.2, 37.4), diameter=0.45, drill=0.20)
    r.path("/ADS_RLDOUT", [(51.2, 37.4), (49.2, 39.4)], pcbnew.In2_Cu, 0.15)
    r.via("/ADS_RLDOUT", (49.2, 39.4))
    r.segment("/ADS_RLDOUT", xy(49.2, 39.4), r.point(("R10", "1")), pcbnew.F_Cu, 0.15)
    r.path(
        "/ADS_RLDOUT",
        [(48.825, 40.7), (49.5, 41.375), (50.835, 41.375), (51.0, 41.21)],
        width=0.15,
    )
    r.path(
        "/ADS_RLDOUT",
        [(51.0, 41.21), (51.5, 41.71), (53.0, 41.71), (54.2, 41.68)],
        width=0.15,
    )

    r.segment("/ADS_RLDINV", r.point(("U1", "C3")), xy(51.2, 36.6), pcbnew.F_Cu, 0.15)
    r.via("/ADS_RLDINV", (51.2, 36.6), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_RLDINV",
        [(51.2, 36.6), (52.0, 36.6), (53.0, 37.6), (53.0, 39.3)],
        pcbnew.B_Cu,
        0.15,
    )
    r.via("/ADS_RLDINV", (53.0, 39.3))
    r.path(
        "/ADS_RLDINV",
        [(53.0, 39.3), (53.0, 40.69), (54.2, 40.72)],
        width=0.15,
    )

    r.segment("/ADS_WCT", r.point(("U1", "D3")), xy(51.2, 35.8), pcbnew.F_Cu, 0.15)
    r.via("/ADS_WCT", (51.2, 35.8), diameter=0.45, drill=0.20)
    r.segment("/ADS_WCT", r.point(("U1", "F2")), xy(50.4, 34.2), pcbnew.F_Cu, 0.15)
    r.via("/ADS_WCT", (50.4, 34.2), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_WCT",
        [(51.2, 35.8), (50.4, 35.0), (50.4, 34.2), (49.0, 32.8), (49.0, 30.0), (47.8, 28.8)],
        pcbnew.In2_Cu,
        0.15,
    )
    r.via("/ADS_WCT", (47.8, 28.8))
    r.segment("/ADS_WCT", xy(47.8, 28.8), r.point(("C13", "1")), pcbnew.F_Cu, 0.15)


def route_ads_support(r: Router) -> None:
    # Reference and charge-pump capacitors.  Their dog-bones are evenly spaced
    # on the BGA grid; the longer capacitor runs stay below the component side.
    r.segment("/ADS_VREFP", r.point(("U1", "H3")), xy(51.2, 31.8), pcbnew.F_Cu, 0.15)
    r.via("/ADS_VREFP", (51.2, 31.8), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_VREFP",
        [(51.2, 31.8), (51.2, 27.5), (50.6, 26.9), (49.0, 26.9), (48.2, 26.1)],
        pcbnew.B_Cu,
        0.15,
    )
    r.via("/ADS_VREFP", (48.2, 26.1))
    r.segment("/ADS_VREFP", xy(48.2, 26.1), r.point(("C15", "1")), pcbnew.F_Cu, 0.15)
    r.path(
        "/ADS_VREFP",
        [(49.0, 26.9), (46.8, 24.7), (46.8, 24.2)],
        pcbnew.B_Cu,
        0.15,
    )
    r.via("/ADS_VREFP", (46.8, 24.2))
    r.segment("/ADS_VREFP", xy(46.8, 24.2), r.point(("C14", "1")), pcbnew.F_Cu, 0.15)

    r.segment("/ADS_VCAP1", r.point(("U1", "H5")), xy(52.0, 31.8), pcbnew.F_Cu, 0.15)
    r.via("/ADS_VCAP1", (52.0, 31.8), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_VCAP1",
        [(52.0, 31.8), (52.0, 26.0), (51.0, 25.0), (50.4, 24.4), (50.4, 24.2)],
        pcbnew.B_Cu,
        0.15,
    )
    r.via("/ADS_VCAP1", (50.4, 24.2))
    r.segment("/ADS_VCAP1", xy(50.4, 24.2), r.point(("C16", "1")), pcbnew.F_Cu, 0.15)

    r.segment("/ADS_VCAP2", r.point(("U1", "H6")), xy(53.6, 31.8), pcbnew.F_Cu, 0.15)
    r.via("/ADS_VCAP2", (53.6, 31.8), diameter=0.45, drill=0.20)
    r.path("/ADS_VCAP2", [(53.6, 31.8), (53.6, 24.4), (53.8, 24.2)], pcbnew.B_Cu, 0.15)
    r.via("/ADS_VCAP2", (53.8, 24.2))
    r.segment("/ADS_VCAP2", xy(53.8, 24.2), r.point(("C17", "1")), pcbnew.F_Cu, 0.15)

    r.segment("/ADS_VCAP4", r.point(("U1", "G3")), xy(50.4, 32.6), pcbnew.F_Cu, 0.15)
    r.via("/ADS_VCAP4", (50.4, 32.6), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_VCAP4",
        [
            (50.4, 32.6),
            (50.4, 31.8),
            (50.8, 31.4),
            (51.2, 31.0),
            (52.8, 31.0),
            (52.8, 29.6),
            (52.2, 29.0),
            (57.0, 29.0),
        ],
        pcbnew.In2_Cu,
        0.15,
    )
    r.via("/ADS_VCAP4", (57.0, 29.0))
    r.path(
        "/ADS_VCAP4",
        [(57.0, 29.0), (57.0, 24.2)],
        pcbnew.B_Cu,
        0.15,
    )
    r.via("/ADS_VCAP4", (57.0, 24.2))
    r.segment("/ADS_VCAP4", xy(57.0, 24.2), r.point(("C19", "1")), pcbnew.F_Cu, 0.15)

    r.segment("/ADS_VCAP3", r.point(("U1", "B7")), xy(54.4, 37.4), pcbnew.F_Cu, 0.15)
    r.via("/ADS_VCAP3", (54.4, 37.4), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_VCAP3",
        [(54.4, 37.4), (55.4, 38.4), (55.2, 40.2), (54.8, 41.0), (54.8, 42.2)],
        pcbnew.In2_Cu,
        0.15,
    )
    r.via("/ADS_VCAP3", (54.8, 42.2))
    r.segment("/ADS_VCAP3", xy(54.8, 42.2), r.point(("C18", "1")), pcbnew.F_Cu, 0.15)

    # CLK test point is reached directly from the outer BGA row.
    r.connect(("U1", "G8"), ("TP5", "1"), (55.6, 33.0), (57.4, 31.2), width=0.15)


def route_ads_digital(r: Router) -> None:
    # ADS SPI: MOSI, SCLK and CS form a regular B.Cu bundle.  MISO is isolated
    # on L3 so both package fanouts remain monotonic and no artificial
    # crossover is introduced.
    for net_name, ball, escape in [
        ("/ADS_MOSI", ("U1", "H8"), (55.6, 32.2)),
        ("/ADS_SCLK", ("U1", "F8"), (55.6, 33.8)),
        ("/ADS_CS", ("U1", "F7"), (54.4, 34.2)),
        ("/ADS_MISO", ("U1", "E8"), (55.6, 34.6)),
    ]:
        r.segment(net_name, r.point(ball), xy(*escape), pcbnew.F_Cu, 0.15)
        diameter = 0.45 if escape == (54.4, 34.2) else 0.50
        r.via(net_name, escape, diameter=diameter, drill=0.20)

    r.path(
        "/ADS_MOSI",
        [(55.6, 32.2), (59.1, 35.7), (91.0, 35.7), (92.8, 37.5), (92.8, 38.4)],
        pcbnew.B_Cu,
        0.18,
    )
    r.path(
        "/ADS_SCLK",
        [(55.6, 33.8), (58.1, 36.3), (89.0, 36.3), (90.6, 37.9), (90.6, 38.4)],
        pcbnew.B_Cu,
        0.18,
    )
    r.path(
        "/ADS_MISO",
        [(55.6, 34.6), (58.4, 37.4), (90.6, 37.4), (91.6, 38.4)],
        pcbnew.In2_Cu,
        0.18,
    )
    # CS crosses the local DRDY fanout on L3, then joins the regular B.Cu SPI
    # bundle.  The two diagonals remain parallel to MISO and never cross.
    r.path(
        "/ADS_CS",
        [(54.4, 34.2), (56.2, 36.0)],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/ADS_CS", (56.2, 36.0), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_CS",
        [(56.2, 36.0), (57.1, 36.9), (88.1, 36.9), (89.6, 38.4)],
        pcbnew.B_Cu,
        0.18,
    )

    for net_name, target, pad in [
        ("/ADS_CS", (89.6, 38.4), ("U2", "19")),
        ("/ADS_SCLK", (90.6, 38.4), ("U2", "20")),
        ("/ADS_MISO", (91.6, 38.4), ("U2", "21")),
        ("/ADS_MOSI", (92.8, 38.4), ("U2", "22")),
    ]:
        r.via(
            net_name,
            target,
            diameter=0.45 if net_name == "/ADS_MISO" else 0.50,
            drill=0.20,
        )

    r.path(
        "/ADS_CS",
        [(89.6, 38.4), (91.2, 36.8), (91.2, 35.8875)],
        width=0.18,
    )
    r.path(
        "/ADS_SCLK",
        [(90.6, 38.4), (91.6, 37.4), (91.6, 35.8875)],
        width=0.18,
    )
    r.path(
        "/ADS_MISO",
        [(91.6, 38.4), (92.0, 38.0), (92.0, 35.8875)],
        width=0.18,
    )
    r.path(
        "/ADS_MOSI",
        [(92.8, 38.4), (92.4, 38.0), (92.4, 35.8875)],
        width=0.18,
    )

    # START occupies the quiet B.Cu lane above the SPI bundle.  At the MCU it
    # uses one compact L3 bridge, then joins the middle tooth of the orderly
    # SDA/NRST/START staggered QFN fanout.
    r.segment("/ADS_START", r.point(("U1", "G7")), xy(54.4, 32.6), pcbnew.F_Cu, 0.15)
    r.via("/ADS_START", (54.4, 32.6), diameter=0.45, drill=0.20)

    r.path(
        "/ADS_START",
        [
            (54.4, 32.6),
            (55.8, 31.2),
            (87.0, 31.2),
            (87.4, 31.6),
            (87.4, 31.7),
            (88.2, 32.5),
        ],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/ADS_START", (88.2, 32.5), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_START",
        [(88.2, 32.5), (88.3, 32.4), (88.8, 32.4), (89.2, 32.0)],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/ADS_START", (89.2, 32.0), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_START",
        [(89.2, 32.0), (90.1125, 32.0)],
        width=0.15,
    )

    # Package-side configuration branches.  START drops directly onto its
    # existing L3 lane; the flipped CS pull-up lands on the B.Cu CS trace.
    r.segment("/ADS_START", r.point(("R31", "1")), xy(72.5, 31.2), pcbnew.F_Cu, 0.18)
    r.via("/ADS_START", (72.5, 31.2), diameter=0.45, drill=0.20)
    r.segment("/ADS_CS", r.point(("R32", "2")), xy(76.0, 36.9), pcbnew.F_Cu, 0.18)
    r.via("/ADS_CS", (76.0, 36.9), diameter=0.45, drill=0.20)


def route_ads_power(r: Router) -> None:
    # ADS digital supply: tie the three adjacent balls as a short vertical
    # spine, touch both package-side bypass capacitors, then use one dog-bone
    # into a quiet L3 corridor that terminates in the main 3V0_D plane.
    r.path(
        "/3V0_D",
        [(54.8, 35.4), (54.8, 36.2), (54.8, 37.0)],
        width=0.15,
    )
    r.path(
        "/3V0_D",
        [(54.8, 35.4), (55.35, 35.4), (56.7, 35.4), (57.125, 35.0)],
        width=0.15,
    )
    r.path(
        "/3V0_D",
        [(57.125, 35.0), (56.9, 35.225), (56.9, 36.0), (57.42, 36.5)],
        width=0.15,
    )
    r.path(
        "/3V0_D",
        [(54.8, 37.0), (55.2, 37.4), (58.4, 37.4), (59.0, 38.0)],
        width=0.18,
    )
    r.via("/3V0_D", (59.0, 38.0))
    r.path(
        "/3V0_D",
        [
            (59.0, 38.0),
            (58.6, 38.4),
            (58.6, 39.4),
            (60.8, 39.4),
            (61.4, 38.8),
            (69.6, 38.8),
        ],
        pcbnew.In2_Cu,
        0.25,
    )

    # AVDD1 is deliberately local: the ferrite/resistor output first reaches
    # the two bypass capacitors, then fans directly into the outer BGA ball.
    r.path(
        "/ADS_AVDD1",
        [(54.0, 37.8), (54.4, 38.2), (55.0, 38.8), (55.0, 39.6), (56.0, 40.225)],
        width=0.18,
    )
    r.connect(("C22", "1"), ("C23", "1"), width=0.20)
    r.connect(("C23", "1"), ("R15", "2"), width=0.20)



def route_clocks_smps_rf(r: Router) -> None:
    # LSE and HSE are top-layer, via-free, and ordered to avoid crossover.
    r.path(
        "/LSE_IN",
        [(90.1125, 29.6), (89.4, 29.6), (88.8, 29.0), (86.8, 27.0), (85.5, 27.0)],
        width=0.18,
    )
    r.connect(("Y2", "1"), ("C44", "1"), (84.6, 27.0), (83.4, 28.2), width=0.18)
    r.path(
        "/LSE_OUT",
        [(90.1125, 30.0), (89.2, 30.0), (88.7, 29.5), (85.5, 29.5)],
        width=0.18,
    )
    r.connect(("Y2", "2"), ("C45", "1"), (84.6, 29.5), (83.6, 30.5), width=0.18)

    r.connect(
        ("U2", "35"),
        ("Y1", "1"),
        (98.8, 35.2),
        (99.6, 34.4),
        (99.6, 33.4),
        (101.7, 33.4),
        width=0.18,
    )
    r.connect(
        ("Y1", "1"),
        ("C42", "1"),
        (102.3, 34.45),
        width=0.18,
    )
    r.connect(("U2", "34"), ("Y1", "3"), (97.2, 36.5), (99.3, 36.5), width=0.18)
    r.connect(("Y1", "3"), ("C43", "1"), (100.3, 36.2), (99.7, 36.8), width=0.18)

    # STM32WB internal SMPS loop: compact, top layer and no vias.  The QFN
    # exits use a short 0.18 mm neck before widening, preserving clearance to
    # the adjacent 0.4 mm-pitch pads.
    r.path(
        "/SMPS_IN",
        [(97.8875, 31.6), (100.2, 31.6), (100.2, 29.5)],
        width=0.18,
    )
    r.path(
        "/SMPS_IN",
        [(100.2, 29.5), (100.2, 29.1), (100.8, 28.5), (101.2125, 27.8)],
        width=0.30,
    )
    r.connect(("L1", "2"), ("C46", "1"), (101.2, 26.2), width=0.30)
    r.path("/SMPS_SW", [(97.8875, 32.0), (100.6, 32.0)], width=0.18)
    r.path(
        "/SMPS_SW",
        [(100.6, 32.0), (101.2, 31.4), (101.2125, 30.5)],
        width=0.25,
    )
    r.path("/SMPS_FB", [(97.8875, 32.8), (101.3, 32.8)], width=0.18)
    r.path(
        "/SMPS_FB",
        [(101.3, 32.8), (102.2, 31.9), (102.8, 31.9), (102.7875, 30.5)],
        width=0.25,
    )
    r.connect(("L2", "2"), ("C47", "1"), (103.2, 30.5), (104.0, 31.3), width=0.25)

    # RF: filter and matching chain are continuous F.Cu with no via.
    r.connect(
        ("U2", "31"),
        ("U9", "A3"),
        (96.0, 36.6),
        (95.8, 36.8),
        (95.8, 38.7935),
        width=0.24,
    )
    r.connect(
        ("U9", "A1"),
        ("C65", "1"),
        (97.8, 39.2),
        (99.5, 40.0),
        (100.5, 40.0),
        width=0.24,
    )
    r.connect(("C65", "1"), ("R51", "1"), width=0.24)
    r.path(
        "/RF_ANT_FEED",
        [(103.01, 39.5), (103.2, 39.5), (103.2, 36.5), (105.8, 33.4), (106.0, 32.98)],
        width=0.24,
    )
    r.path(
        "/RF_ANT_FEED",
        [(106.0, 32.98), (107.0, 31.98), (114.5, 31.98), (115.55, 31.0)],
        width=0.24,
    )


def route_usb(r: Router) -> None:
    # The expanded north service band keeps every USB transition above the
    # SWD row.  D- uses L3 for the one unavoidable crossover at U10; both
    # post-resistor traces then fan into the QFN together on F.Cu.
    r.bottom_to_top(("J3", "2"), ("U10", "3"), (91.8, 22.4), width=0.18)
    r.via("/USB_DM_POGO", (99.3, 24.3))
    r.path(
        "/USB_DM_POGO",
        [(91.8, 22.4), (92.4, 23.0), (98.0, 23.0), (99.3, 24.3)],
        pcbnew.In2_Cu,
        0.18,
    )
    r.leg45("/USB_DM_POGO", xy(99.3, 24.3), r.point(("R21", "1")), pcbnew.F_Cu, 0.18)

    r.bottom_to_top(("J3", "3"), ("U10", "1"), (94.9, 21.2), width=0.18)
    r.connect(
        ("U10", "1"),
        ("R22", "1"),
        (94.9, 22.1),
        (96.0, 23.2),
        (96.0, 24.0),
        width=0.18,
    )
    r.path(
        "/USB_DM",
        [(98.8, 26.01), (98.8, 26.4), (97.2, 28.0), (97.2, 28.1125)],
        width=0.18,
    )
    r.path(
        "/USB_DP",
        [(97.2, 26.01), (97.2, 26.5), (96.8, 26.9), (96.8, 27.3)],
        width=0.18,
    )
    r.path("/USB_DP", [(96.8, 27.3), (96.8, 28.1125)], width=0.15)

    r.bottom_to_top(("J3", "1"), ("F2", "1"), (88.8, 22.4), width=0.45)
    r.leg45("/VBUS", r.point(("F2", "2")), xy(88.8, 20.4), pcbnew.F_Cu, 0.45)
    r.via("/VBUS", (88.8, 20.4))
    r.path(
        "/VBUS",
        [(88.8, 20.4), (82.0, 20.4), (79.6, 22.8)],
        pcbnew.In2_Cu,
        0.45,
    )
    r.via("/VBUS", (79.6, 22.8))
    r.leg45("/VBUS", xy(79.6, 22.8), r.point(("U7", "1")), pcbnew.F_Cu, 0.45)


def route_usb_vbus_sense(r: Router) -> None:
    # The divider stays beside the USB regulator, where its VBUS branch is
    # short.  The sense output takes one orderly B.Cu perimeter lane around
    # the top and right edges of the MCU, then enters PB8 normal to the bottom
    # package edge.  This avoids weaving through the LSE/I2C cluster at left.
    r.path(
        "/USB_VBUS_SENSE",
        [(80.7, 29.51), (81.3, 30.11)],
        width=0.18,
    )
    r.via("/USB_VBUS_SENSE", (81.3, 30.11), diameter=0.45, drill=0.20)
    r.path(
        "/USB_VBUS_SENSE",
        [
            (81.3, 30.11),
            (82.61, 28.8),
            (88.3, 28.8),
            (89.0, 29.5),
            (90.0, 29.5),
            (90.0, 27.85),
            (98.1, 27.85),
            (98.1, 35.9),
            (93.9, 35.9),
            (93.0, 36.8),
        ],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/USB_VBUS_SENSE", (93.0, 36.8), diameter=0.45, drill=0.20)
    r.path(
        "/USB_VBUS_SENSE",
        [(93.0, 36.8), (93.2, 36.6), (93.2, 35.8875)],
        width=0.18,
    )


def route_sd_card_side(r: Router) -> None:
    # Series parts are aligned with the socket contacts; these card-side runs
    # are short, parallel, and stay on the top reference plane.
    for resistor, pad in [
        ("R41", "2"),
        ("R42", "3"),
        ("R43", "5"),
        ("R44", "7"),
    ]:
        r.connect((resistor, "2"), ("J4", pad), width=0.20)
    r.connect(("R45", "2"), ("J4", "1"), width=0.20)
    r.connect(("R50", "2"), ("J4", "9"), (111.2, 49.0), (112.6, 47.6), width=0.18)


def route_sd_aux_card_side(r: Router) -> None:
    # DAT0/DAT1 pull-ups return to the socket in two straight, parallel B.Cu
    # lanes just under its left edge.  Vias are kept outside the contact and
    # shield pads; the two bottom fanouts sit in the narrow board-edge lane.
    r.path("/SD_DAT0", [(106.51, 49.0), (106.7, 49.19)], width=0.18)
    r.via("/SD_DAT0", (106.7, 49.19))
    r.path(
        "/SD_DAT0",
        [(106.7, 49.19), (106.5, 48.99), (106.5, 38.205), (105.8, 37.505)],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/SD_DAT0", (105.8, 37.505))
    r.path(
        "/SD_DAT0",
        [(105.8, 37.505), (107.05, 37.505)],
        width=0.18,
    )

    r.path("/SD_DAT1", [(108.51, 49.0), (108.7, 49.19)], width=0.18)
    r.via("/SD_DAT1", (108.7, 49.19))
    r.path(
        "/SD_DAT1",
        [(108.7, 49.19), (107.01, 47.5), (107.01, 37.665), (105.8, 36.455)],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/SD_DAT1", (105.8, 36.455))
    r.path(
        "/SD_DAT1",
        [(105.8, 36.455), (107.05, 36.455)],
        width=0.18,
    )


def route_sd_power_enable_local(r: Router) -> None:
    # U8's EN pad faces away from its pull-down.  A single L3 U-shaped link
    # passes beneath the load switch and keeps the component-side fanout free
    # of the CT and output-decoupling nodes.
    r.path("/SD_PWR_EN", [(98.0, 46.71), (97.3, 46.71)], width=0.18)
    r.via("/SD_PWR_EN", (97.3, 46.71))
    r.path(
        "/SD_PWR_EN",
        [(97.3, 46.71), (97.3, 48.7), (102.8, 48.7), (102.8, 47.45)],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/SD_PWR_EN", (102.8, 47.45))
    r.path("/SD_PWR_EN", [(102.8, 47.45), (101.9375, 47.45)], width=0.18)


def route_sd_controls(r: Router) -> None:
    # PC2/PC3 leave the MCU as an ordered two-line fanout, then use the L3
    # northbound channel opened by moving START to B.Cu.  They pass the RTC
    # via on opposite sides, settle into parallel lanes above the MCU, and
    # stay together along the SD-side perimeter.
    r.path(
        "/SD_DETECT",
        [
            (90.1125, 32.8),
            (89.6, 32.8),
            (89.1, 33.2),
            (88.0, 34.2),
            (87.6, 34.6),
            (87.6, 34.8),
        ],
        width=0.15,
    )
    r.via("/SD_DETECT", (87.6, 34.8), diameter=0.45, drill=0.20)
    r.path(
        "/SD_PWR_EN",
        [
            (90.1125, 33.2),
            (89.6, 33.2),
            (89.2, 33.6),
            (88.4, 34.4),
            (88.2, 34.6),
            (88.2, 35.0),
        ],
        width=0.15,
    )
    r.via("/SD_PWR_EN", (88.2, 35.0), diameter=0.45, drill=0.20)

    r.path(
        "/SD_DETECT",
        [
            (87.6, 34.8),
            (87.2, 34.4),
            (86.0, 34.4),
            (85.4, 33.8),
            (85.4, 28.2),
            (86.2, 27.4),
            (87.2, 27.4),
            (87.6, 27.0),
            (88.8, 27.0),
            (89.4, 27.0),
            (89.8, 27.4),
            (90.3, 27.9),
            (97.0, 27.9),
            (97.9, 27.0),
            (108.4, 27.0),
            (109.4, 28.0),
            (109.4, 46.6),
            (110.4, 47.6),
        ],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/SD_DETECT", (110.4, 47.6))
    r.path(
        "/SD_DETECT",
        [(110.4, 47.6), (110.4, 48.89), (110.51, 49.0)],
        width=0.18,
    )

    r.path(
        "/SD_PWR_EN",
        [
            (88.2, 35.0),
            (88.6, 34.6),
            (89.2, 34.4),
            (90.0, 33.6),
            (90.0, 29.8),
            (90.4, 29.4),
            (90.4, 28.8),
            (90.8, 28.4),
            (97.0, 28.4),
            (97.8, 27.6),
            (107.6, 27.6),
            (108.4, 28.4),
            (108.4, 46.0),
            (107.0, 47.4),
            (102.8, 47.4),
            (102.8, 47.45),
        ],
        pcbnew.In2_Cu,
        0.18,
    )


def route_sd_mcu_side(r: Router) -> None:
    # Four QFN signals fan into a checkerboard via field, clear of the shifted
    # SMPS loop.  On B.Cu their progressively wider lanes preserve
    # ordering and arrive at the MCU-side pads of the damping resistors.
    for pad, via_point in [
        ("51", (98.8, 28.3)),
        ("49", (99.6, 28.8)),
        ("48", (98.8, 29.9)),
        ("47", (99.6, 30.4)),
    ]:
        net_name = r.net_name(("U2", pad))
        pad_x, pad_y = as_mm(r.point(("U2", pad)))
        r.path(
            net_name,
            [(pad_x, pad_y), (98.3, pad_y), via_point],
            width=0.18,
        )
        r.via(net_name, via_point, diameter=0.45, drill=0.20)

    r.path(
        "/SD_CS_MCU",
        [(98.8, 28.3), (99.3, 27.8), (99.3, 26.8), (104.8, 26.8), (104.8, 41.8), (103.3, 43.3)],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/SD_CS_MCU", (103.3, 43.3))
    r.segment("/SD_CS_MCU", xy(103.3, 43.3), r.point(("R41", "1")), pcbnew.F_Cu, 0.18)

    r.path(
        "/SD_MOSI_MCU",
        [(99.6, 28.8), (101.6, 29.0), (101.6, 41.3), (102.4, 41.7)],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/SD_MOSI_MCU", (102.4, 41.7))
    r.segment("/SD_MOSI_MCU", xy(102.4, 41.7), r.point(("R42", "1")), pcbnew.F_Cu, 0.18)

    r.path(
        "/SD_MISO_MCU",
        [(98.8, 29.9), (100.8, 29.9), (100.8, 35.5), (101.8, 36.5), (104.0, 36.5)],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/SD_MISO_MCU", (104.0, 36.5))
    r.segment("/SD_MISO_MCU", xy(104.0, 36.5), r.point(("R44", "1")), pcbnew.F_Cu, 0.18)

    r.path(
        "/SD_SCK_MCU",
        [(99.6, 30.4), (100.0, 30.8), (100.0, 38.2), (102.6, 40.2)],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/SD_SCK_MCU", (102.6, 40.2))
    r.path(
        "/SD_SCK_MCU",
        [(102.6, 40.2), (103.4, 40.2), (103.9, 39.7), (103.99, 39.7)],
        width=0.18,
    )


def route_sd_power(r: Router) -> None:
    # Switched card rail.  The output first wraps above U8, then feeds the
    # pull-ups from their pad-1 side so no route crosses a series resistor.
    r.path(
        "/3V0_SD",
        [
            (101.9375, 45.55),
            (102.3, 45.1875),
            (102.3, 44.5),
            (99.7, 44.5),
            (99.7, 43.3),
            (100.49, 43.3),
        ],
        width=0.25,
    )
    r.path("/3V0_SD", [(99.7, 43.3), (99.7, 41.7), (100.49, 41.7)], width=0.25)
    r.path("/3V0_SD", [(102.3, 44.5), (103.1, 44.5), (103.8, 45.2)], width=0.30)

    # Output and pull-up decoupling along the board edge.
    r.path(
        "/3V0_SD",
        [(103.8, 45.21), (104.6, 45.21), (105.3, 45.91), (105.3, 48.55), (104.0, 48.55)],
        width=0.30,
    )
    r.path(
        "/3V0_SD",
        [(104.0, 48.55), (104.0, 48.2), (101.52, 48.2), (101.52, 49.0)],
        width=0.25,
    )
    r.path("/3V0_SD", [(104.0, 48.55), (104.45, 49.0), (105.49, 49.0)], width=0.25)
    r.path(
        "/3V0_SD",
        [(105.49, 49.0), (105.49, 48.2), (107.49, 48.2), (107.49, 49.0)],
        width=0.25,
    )

    # The socket VDD contact changes layer once, between the local output node
    # and the contact fanout, leaving the four SPI lanes unobstructed on top.
    r.change_layer(
        ("R45", "1"),
        ("J4", "4"),
        (104.6, 45.2),
        (105.8, 40.805),
        (105.2, 44.6),
        (105.2, 41.4),
        layer=pcbnew.B_Cu,
        width=0.25,
    )

    r.change_layer(
        ("U8", "3"),
        ("C61", "1"),
        (99.0, 48.1),
        (96.8, 47.2),
        (98.0, 48.1),
        layer=pcbnew.B_Cu,
        width=0.18,
    )


def route_vbus_power(r: Router) -> None:
    # Local USB LDO input fanout.  U7 pins 1 and 3 wrap around the ground pad,
    # and the sense divider leaves vertically from the lower input pin.
    r.path(
        "/VBUS",
        [(76.225, 25.0), (75.6, 24.375), (75.6, 23.6), (78.8, 23.6), (79.6, 22.8)],
        width=0.35,
    )
    r.path(
        "/VBUS",
        [
            (80.8625, 24.05),
            (80.0, 24.05),
            (79.4, 24.65),
            (79.4, 25.35),
            (80.0, 25.95),
            (80.8625, 25.95),
        ],
        width=0.25,
    )
    r.path(
        "/VBUS",
        [
            (80.8625, 25.95),
            (80.2, 26.6125),
            (78.5, 28.3125),
            (78.5, 30.5),
            (79.5, 29.5),
            (79.5, 29.51),
        ],
        width=0.20,
    )

    # Wide top-layer trunk to the power mux; it uses the open corridor between
    # the RTC/USB area and the pull-up row, avoiding both digital bus layers.
    r.path(
        "/VBUS",
        [
            (76.225, 25.0),
            (75.4, 25.825),
            (74.6, 26.625),
            (74.6, 36.5),
            (74.6, 37.875),
            (73.675, 38.8),
        ],
        width=0.35,
    )
    r.path(
        "/VBUS",
        [(73.675, 38.8), (74.4, 39.525), (74.4, 42.75)],
        width=0.25,
    )
    r.segment("/VBUS", xy(74.4, 42.75), r.point(("U4", "5")), pcbnew.F_Cu, 0.18)

    # The opposite mux input pad joins underneath the package, below the ADS
    # bus, and the priority resistor approaches from its signal-side pad.
    r.change_layer(
        ("U4", "3"),
        ("C29", "1"),
        (68.6, 42.25),
        (73.8, 38.0),
        (68.6, 40.6),
        (70.0, 38.8),
        layer=pcbnew.B_Cu,
        width=0.25,
    )
    r.path(
        "/VBUS",
        [(68.6, 42.25), (67.2, 40.85), (66.6, 40.25), (66.6, 39.4)],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/VBUS", (66.6, 39.4))
    r.leg45("/VBUS", xy(66.6, 39.4), r.point(("R23", "1")), pcbnew.F_Cu, 0.18)


def route_battery_and_system_power(r: Router) -> None:
    # Protected battery rail: local bypass branches stay on top; the main
    # current path passes below the mux once and fans out to the ADC divider.
    r.path(
        "/BAT_PROT",
        [(66.4375, 42.0), (67.2, 42.7625), (67.2, 46.075), (68.2, 47.075)],
        width=0.30,
    )
    r.segment("/BAT_PROT", r.point(("Q1", "3")), xy(66.4, 43.2), pcbnew.F_Cu, 0.30)
    r.via("/BAT_PROT", (66.4, 43.2))
    r.path(
        "/BAT_PROT",
        [(66.4, 43.2), (65.5, 42.3), (65.5, 40.5), (64.6, 39.6), (63.0, 39.6)],
        pcbnew.In2_Cu,
        0.30,
    )
    r.via("/BAT_PROT", (63.0, 39.6))
    r.leg45("/BAT_PROT", xy(63.0, 39.6), r.point(("C30", "1")), pcbnew.F_Cu, 0.25)
    r.path(
        "/BAT_PROT",
        [(66.4, 43.2), (67.0, 43.8), (71.8, 43.8), (72.4, 43.2), (72.4, 42.25)],
        pcbnew.B_Cu,
        0.35,
    )
    r.via("/BAT_PROT", (72.4, 42.25))
    r.segment("/BAT_PROT", xy(72.4, 42.25), r.point(("U4", "6")), pcbnew.F_Cu, 0.18)
    r.path(
        "/BAT_PROT",
        [(72.4, 42.25), (73.2, 43.05), (74.8, 43.05), (76.6, 44.8)],
        pcbnew.B_Cu,
        0.25,
    )
    r.via("/BAT_PROT", (76.6, 44.8))
    r.leg45("/BAT_PROT", xy(76.6, 44.8), r.point(("R26", "1")), pcbnew.F_Cu, 0.20)

    # TPS2116 priority node is a quiet control signal; use L3 locally so it
    # does not weave through the two power inputs at the left of the mux.
    r.change_layer(
        ("U4", "4"),
        ("R24", "1"),
        (68.4, 43.0),
        (69.7, 40.0),
        (67.8, 42.4),
        (67.8, 40.4),
        layer=pcbnew.In2_Cu,
        width=0.18,
    )
    r.connect(("R23", "2"), ("R24", "1"), width=0.18)

    # Active-low USB-priority test node.  The mux fanout is on L3 while the
    # resistor and test point are joined on top, clear of its 3V0_D pad.
    r.path("/PWR_USB_N", [(71.65, 41.25), (72.0, 41.25), (72.0, 40.3)], width=0.18)
    r.via("/PWR_USB_N", (72.0, 40.3))
    r.path(
        "/PWR_USB_N",
        [(72.0, 40.3), (73.8, 42.1), (73.8, 44.8), (75.0, 46.0)],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/PWR_USB_N", (75.0, 46.0))
    r.segment("/PWR_USB_N", xy(75.0, 46.0), r.point(("TP4", "1")), pcbnew.F_Cu, 0.18)
    r.path(
        "/PWR_USB_N",
        [(72.7, 44.69), (73.4, 44.69), (74.0, 45.29), (74.0, 46.0), (75.0, 47.0)],
        width=0.18,
    )

    # SYS_RAW first links the two input pins of each LDO around their ground
    # pad, then follows the empty top-layer corridor down to the mux output.
    r.path(
        "/SYS_RAW",
        [
            (63.1625, 21.85),
            (62.4, 21.85),
            (61.8, 22.45),
            (61.8, 23.15),
            (62.4, 23.75),
            (63.1625, 23.75),
        ],
        width=0.30,
    )
    r.path(
        "/SYS_RAW",
        [
            (63.1625, 23.75),
            (62.4, 24.5),
            (60.2, 24.5),
            (59.5, 25.2),
            (59.5, 26.5),
            (60.725, 26.5),
        ],
        width=0.30,
    )
    r.path(
        "/SYS_RAW",
        [
            (63.1625, 23.75),
            (64.0, 24.5875),
            (64.0, 25.5),
            (68.8, 25.5),
            (69.6, 26.3),
            (69.6, 33.4),
            (71.2, 35.0),
            (71.225, 35.0),
        ],
        width=0.35,
    )
    r.path(
        "/SYS_RAW",
        [
            (71.225, 35.0),
            (71.4, 35.175),
            (71.4, 40.6),
            (70.8, 40.6),
            (68.4, 40.6),
        ],
        width=0.25,
    )

    # The bulk capacitor sits below the mux block.  Reuse the existing output
    # via, then take the otherwise empty B.Cu perimeter corridor so the wide
    # rail does not cut through the priority/sense fanout on the front.
    r.path(
        "/SYS_RAW",
        [(75.5, 40.5), (77.5, 42.5), (77.5, 47.7), (70.5, 47.7)],
        pcbnew.B_Cu,
        0.30,
    )
    r.via("/SYS_RAW", (70.5, 47.7))
    r.leg45(
        "/SYS_RAW",
        xy(70.5, 47.7),
        r.point(("C31", "1")),
        pcbnew.F_Cu,
        0.30,
    )
    r.path(
        "/SYS_RAW",
        [(68.4, 40.6), (68.4, 41.75), (69.35, 41.75)],
        width=0.18,
    )
    r.path(
        "/SYS_RAW",
        [(71.65, 41.75), (72.8, 41.75), (72.8, 40.2)],
        width=0.18,
    )
    r.via("/SYS_RAW", (70.8, 40.6))
    r.via("/SYS_RAW", (72.8, 40.2))
    r.path(
        "/SYS_RAW",
        [(70.8, 40.6), (71.4, 41.2), (72.8, 41.2), (72.8, 40.2)],
        pcbnew.B_Cu,
        0.18,
    )
    r.path(
        "/SYS_RAW",
        [(72.8, 40.2), (73.4, 39.6), (74.9, 39.6), (75.5, 40.5)],
        pcbnew.B_Cu,
        0.30,
    )
    r.via("/SYS_RAW", (75.5, 40.5))
    r.leg45("/SYS_RAW", xy(75.5, 40.5), r.point(("U5", "1")), pcbnew.F_Cu, 0.25)
    r.path(
        "/SYS_RAW",
        [
            (76.3625, 41.05),
            (75.5, 41.05),
            (74.8, 41.75),
            (74.8, 42.25),
            (75.5, 42.95),
            (76.3625, 42.95),
        ],
        width=0.25,
    )


def route_local_power_and_support(r: Router) -> None:
    # Small local support links that should not consume a routing layer.
    r.connect(("R11", "1"), ("R10", "2"), width=0.25)
    r.connect(("C26", "2"), ("R18", "1"), width=0.18)
    r.connect(("C27", "2"), ("R19", "1"), width=0.18)
    r.connect(
        ("R37", "2"),
        ("D16", "2"),
        (103.8, 22.0),
        (103.8, 21.4),
        (106.2875, 21.4),
        width=0.18,
    )

    # Remaining local plane entries.
    r.plane_drop(("R15", "1"), (60.2, 40.6), width=0.25, diameter=0.45)
    r.path("/3V0_D", [(96.8, 35.8875), (96.8, 36.8)], width=0.18)
    r.via("/3V0_D", (96.8, 36.8), diameter=0.45, drill=0.20)
    r.path("/3V0_D", [(97.8875, 31.2), (98.4, 31.2), (98.9, 31.0)], width=0.18)
    r.via("/3V0_D", (98.9, 31.0), diameter=0.45, drill=0.20)

    # MCU analog supply: the two QFN pins share one short escape, while both
    # local capacitors sit directly on the ferrite-bead output.
    r.connect(("FB1", "2"), ("C50", "1"), (85.5, 38.2), (85.5, 39.4), width=0.25)
    r.connect(("FB1", "2"), ("C49", "1"), (85.8, 37.8), (86.4, 37.575), width=0.25)
    r.segment("/MCU_VDDA", r.point(("U2", "13")), r.point(("U2", "14")), pcbnew.F_Cu, 0.18)
    r.path(
        "/MCU_VDDA",
        [
            (87.0, 37.575),
            (87.8, 37.575),
            (88.6, 36.775),
            (88.9, 36.475),
            (88.9, 34.6),
            (89.3, 34.2),
            (89.3, 34.0),
            (90.1125, 34.0),
        ],
        width=0.18,
    )

    # RTC hold-up capacitors form a quiet rail along the board edge.  The
    # branch to VBAT stays above the LSE network and remains via-free.
    r.path(
        "/RTC_HOLD",
        [(75.05, 22.0), (75.05, 20.95), (85.95, 20.95), (85.95, 21.8)],
        width=0.25,
    )
    for x_pos in (78.75, 82.45):
        r.segment("/RTC_HOLD", xy(x_pos, 22.0), xy(x_pos, 20.95), pcbnew.F_Cu, 0.25)
    r.path("/RTC_HOLD", [(85.95, 21.8), (86.5, 22.35), (87.0, 22.85), (87.0, 23.2)], width=0.20)
    r.via("/RTC_HOLD", (87.0, 23.2))
    r.path(
        "/RTC_HOLD",
        [(87.0, 23.2), (87.0, 25.8), (88.5, 27.3), (89.2, 28.0)],
        pcbnew.B_Cu,
        0.20,
    )
    r.via("/RTC_HOLD", (89.2, 28.0))
    r.leg45("/RTC_HOLD", xy(89.2, 28.0), r.point(("U2", "1")), pcbnew.F_Cu, 0.20)

    # USB-only 3.3 V rail.  The long supply link uses B.Cu, away from the USB
    # differential pair; the QFN and its decoupler remain on F.Cu.
    r.connect(("U7", "5"), ("C37", "1"), (84.0, 24.05), width=0.25)
    r.path("/3V3_USB", [(85.225, 24.5), (86.0, 25.2)], width=0.25)
    r.via("/3V3_USB", (86.0, 25.2))
    r.path(
        "/3V3_USB",
        [
            (86.0, 25.2),
            (92.1, 25.2),
            (92.5, 24.8),
            (92.5, 24.4),
            (97.0, 24.4),
            (97.5, 24.9),
            (100.0, 24.9),
        ],
        pcbnew.In2_Cu,
        0.25,
    )
    # The QFN supply pad drops straight into L3 below the SWD pair.  This
    # replaces the former F.Cu hook across PA14 and opens two normal fanouts.
    r.path(
        "/3V3_USB",
        [(96.0, 28.1125), (96.0, 27.4)],
        width=0.15,
    )
    r.via("/3V3_USB", (96.0, 27.4), diameter=0.45, drill=0.20)
    r.path(
        "/3V3_USB",
        [(96.0, 27.4), (95.0, 26.4), (95.0, 24.4)],
        pcbnew.In2_Cu,
        0.20,
    )
    r.segment(
        "/3V3_USB",
        r.point(("C56", "1")),
        xy(100.0, 24.9),
        pcbnew.F_Cu,
        0.25,
    )
    r.via("/3V3_USB", (100.0, 24.9))

    # Battery entry, fuse and reverse-polarity MOSFET local routes.
    r.connect(("D14", "1"), ("F1", "1"), width=0.45)
    r.connect(("F1", "1"), ("J2", "1"), (60.7125, 43.9), width=0.45)
    r.connect(("F1", "2"), ("Q1", "2"), (63.0, 42.0), (63.95, 42.95), width=0.45)
    r.segment("/BAT_GATE", r.point(("Q1", "1")), xy(63.8, 40.2875), pcbnew.F_Cu, 0.18)
    r.via("/BAT_GATE", (63.8, 40.2875))
    r.path(
        "/BAT_GATE",
        [(63.8, 40.2875), (62.8, 41.2875), (62.8, 45.0), (64.8, 47.0)],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/BAT_GATE", (64.8, 47.0))
    r.segment("/BAT_GATE", xy(64.8, 47.0), r.point(("R20", "1")), pcbnew.F_Cu, 0.18)


def route_local_signal_branches(r: Router) -> None:
    # Short passive chains are completed before the longer control buses so
    # those buses can route around known, compact local copper.
    r.connect(
        ("R47", "2"),
        ("R42", "2"),
        (102.1, 41.1),
        (105.0, 41.1),
        width=0.18,
    )
    r.connect(
        ("R46", "2"),
        ("R41", "2"),
        (102.2, 42.6),
        (105.5, 42.6),
        width=0.18,
    )

    r.connect(("R26", "2"), ("R27", "1"), width=0.18)
    r.path(
        "/BAT_SENSE_DIV",
        [(79.49, 45.5), (79.49, 46.3), (81.69, 46.3), (81.69, 45.5)],
        width=0.18,
    )
    r.connect(("R28", "2"), ("C38", "1"), width=0.18)

    r.connect(("R35", "2"), ("R36", "1"), width=0.18)


def route_imu_i2c(r: Router) -> None:
    # The rotated IMU and flipped SDA pull-up present both signal pads toward
    # the MCU.  The complete pair is now via-free on F.Cu; this frees B.Cu for
    # the MCU-side control channel and makes the two traces visually ordered.
    r.path(
        "/IMU_SCL",
        [(83.0125, 34.5), (83.6, 34.5), (84.39, 33.71), (84.8, 33.71)],
        width=0.18,
    )
    r.path(
        "/IMU_SCL",
        [
            (84.8, 33.71),
            (85.8, 33.4),
            (86.8, 32.4),
            (87.2, 32.4),
            (87.6, 32.0),
            (87.6, 31.2),
            (88.0, 30.8),
        ],
        pcbnew.F_Cu,
        0.18,
    )
    r.path(
        "/IMU_SCL",
        [(88.0, 30.8), (90.1125, 30.8)],
        pcbnew.F_Cu,
        0.15,
    )

    r.segment("/IMU_SDA", r.point(("U3", "14")), xy(83.6, 33.4), pcbnew.F_Cu, 0.18)
    r.via("/IMU_SDA", (83.6, 33.4))
    r.path(
        "/IMU_SDA",
        [(83.6, 33.4), (84.0, 33.8), (86.8, 33.8)],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/IMU_SDA", (86.8, 33.8))
    r.path("/IMU_SDA", [(86.8, 33.8), (86.8, 34.41), (86.71, 34.5)], width=0.18)
    r.path(
        "/IMU_SDA",
        [
            (86.8, 33.8),
            (87.2, 33.4),
            (87.2, 32.6),
            (87.6, 32.2),
            (87.6, 31.4),
            (88.2, 30.8),
            (88.6, 30.8),
            (89.2, 31.2),
        ],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/IMU_SDA", (89.2, 31.2), diameter=0.45, drill=0.20)
    r.path(
        "/IMU_SDA",
        [(89.2, 31.2), (90.1125, 31.2)],
        width=0.18,
    )


def route_imu_interrupts(r: Router) -> None:
    # INT1 exits the IMU upward, skirts the empty left service bay on F.Cu,
    # and crosses the SPI/control bundle once on a straight lower B.Cu lane.
    # INT2 uses the matching L3 band immediately below ADS_MISO.
    r.path(
        "/IMU_INT1",
        [
            (81.25, 33.2375),
            (81.25, 32.55),
            (80.8, 32.1),
            (76.4, 32.1),
            (76.0, 32.5),
            (76.0, 33.0),
            (75.2, 33.8),
            (75.2, 37.0),
            (76.6, 38.4),
        ],
        width=0.18,
    )
    r.via("/IMU_INT1", (76.6, 38.4), diameter=0.45, drill=0.20)
    r.path(
        "/IMU_INT1",
        [(76.6, 38.4), (77.4, 39.2), (93.6, 39.2), (93.6, 37.8)],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/IMU_INT1", (93.6, 37.8), diameter=0.45, drill=0.20)
    r.path("/IMU_INT1", [(93.6, 37.8), (93.6, 35.8875)], width=0.18)

    r.path(
        "/IMU_INT2",
        [(81.75, 35.7625), (81.75, 37.3), (81.8, 38.2)],
        width=0.18,
    )
    r.via("/IMU_INT2", (81.8, 38.2), diameter=0.45, drill=0.20)
    r.path(
        "/IMU_INT2",
        [(81.8, 38.2), (82.9, 39.3), (93.7, 39.3), (94.4, 38.6)],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/IMU_INT2", (94.4, 38.6), diameter=0.45, drill=0.20)
    r.path(
        "/IMU_INT2",
        [(94.4, 38.6), (94.4, 36.9), (94.0, 36.5), (94.0, 35.8875)],
        width=0.18,
    )


def route_mcu_status(r: Router) -> None:
    # The status LED leaves PB5 normal to the QFN edge, then takes the free
    # B.Cu lane immediately above the USB-sense perimeter route.  Keeping this
    # run north of the MCU avoids both the LSE fanout and the SMPS switch node.
    r.path(
        "/LED_STATUS_N",
        [(92.0, 28.1125), (92.0, 27.6), (91.8, 27.4), (91.8, 27.2)],
        width=0.15,
    )
    r.via("/LED_STATUS_N", (91.8, 27.2), diameter=0.45, drill=0.20)
    r.path(
        "/LED_STATUS_N",
        [
            (91.8, 27.2),
            (91.4, 26.8),
            (91.4, 26.2),
            (92.0, 25.6),
            (103.2, 25.6),
            (104.4, 24.4),
            (104.4, 23.4),
        ],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/LED_STATUS_N", (104.4, 23.4))
    r.path(
        "/LED_STATUS_N",
        [(104.4, 23.4), (104.4, 22.8125), (104.7125, 22.5)],
        width=0.18,
    )


def route_mcu_reset_local(r: Router) -> None:
    # The pull-up and shunt capacitor remain a compact local chain below the
    # MCU.  The service contact now branches from the package escape instead
    # of dragging this quiet RC node across the board.
    r.connect(("R33", "2"), ("C48", "1"), width=0.18)

    # NRST is the centre tooth in the orderly SDA/NRST/START QFN fanout.  Its
    # short horizontal escape passes midway between the two staggered vias;
    # the B.Cu branch then drops below the control bundle before one deliberate
    # F.Cu crossover follows the edge of the analog-supply block.  No via is
    # placed in a QFN pad.
    r.path(
        "/NRST",
        [
            (90.1125, 31.6),
            (88.7, 31.6),
        ],
        width=0.15,
    )
    r.via("/NRST", (88.7, 31.6), diameter=0.45, drill=0.20)
    r.path(
        "/NRST",
        [
            (88.7, 31.6),
            (88.7, 33.6),
            (88.4, 34.0),
            (88.4, 34.2),
            (87.2, 34.2),
            (86.4, 35.0),
            (86.2, 35.1),
        ],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/NRST", (86.2, 35.1), diameter=0.45, drill=0.20)
    r.path(
        "/NRST",
        [
            (86.2, 35.1),
            (85.6, 35.7),
            (84.0, 35.7),
            (83.2, 36.5),
            (82.4, 36.5),
            (82.4, 43.0),
            (84.21, 43.0),
            (84.21, 41.8),
        ],
        width=0.18,
    )

    # A deliberate B.Cu/L3 service branch skirts the LSE and SD-control
    # channels, then lands below the leftmost J5 signal pad.  The two vias sit
    # in open component bays and the final approach is normal to the pogo row.
    r.path(
        "/NRST",
        [
            (88.7, 31.6),
            (88.7, 31.3),
            (87.2, 29.8),
            (85.1, 29.8),
            (84.6, 29.8),
            (84.1, 29.3),
        ],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/NRST", (84.1, 29.3), diameter=0.45, drill=0.20)
    r.path(
        "/NRST",
        [(84.1, 29.3), (84.1, 28.3), (87.2, 25.9), (91.0, 25.9)],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/NRST", (91.0, 25.9), diameter=0.45, drill=0.20)
    r.path(
        "/NRST",
        [(91.0, 25.9), (91.3, 25.6), (91.3, 24.46), (91.96, 23.8)],
        pcbnew.B_Cu,
        0.18,
    )


def route_debug_service(r: Router) -> None:
    # SWCLK takes the lower QFN escape lane, then rises between C52 and C53.
    # SWDIO stays one lane to its right and turns above the decoupler row.  The
    # order is preserved all the way into the reversed bottom-side J5 row, so
    # neither trace crosses the other and both pogo approaches are vertical.
    r.path(
        "/SWCLK",
        [
            (95.6, 28.1125),
            (95.6, 27.6),
            (95.4, 27.4),
            (93.9, 27.4),
            (93.5, 27.0),
            (93.5, 25.1),
        ],
        width=0.15,
    )
    r.via("/SWCLK", (93.5, 25.1), diameter=0.45, drill=0.20)
    r.path(
        "/SWCLK",
        [(93.5, 25.1), (93.23, 24.83), (93.23, 23.8)],
        pcbnew.B_Cu,
        0.18,
    )

    r.path(
        "/SWDIO",
        [
            (96.4, 28.1125),
            (96.4, 25.5),
            (96.0, 25.1),
            (95.8, 25.1),
        ],
        width=0.15,
    )
    r.via("/SWDIO", (95.8, 25.1), diameter=0.45, drill=0.20)
    r.path(
        "/SWDIO",
        [(95.8, 25.1), (94.7, 25.1), (94.5, 24.9), (94.5, 23.8)],
        pcbnew.B_Cu,
        0.18,
    )

    # SWO uses a short L3 crossover around the status-LED via, then remains on
    # the left of NRST all the way into the standalone bottom test pad.
    r.path(
        "/SWO",
        [(92.8, 28.1125), (92.8, 27.0), (93.0, 26.8)],
        width=0.15,
    )
    r.via("/SWO", (93.0, 26.8), diameter=0.45, drill=0.20)
    r.path(
        "/SWO",
        [
            (93.0, 26.8),
            (92.9, 26.7),
            (92.9, 26.4),
            (92.6, 26.1),
            (91.5, 26.1),
            (91.2, 26.4),
            (90.6, 26.4),
        ],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/SWO", (90.6, 26.4), diameter=0.45, drill=0.20)
    r.path(
        "/SWO",
        [(90.6, 26.4), (90.2, 26.0), (90.2, 24.5), (89.5, 23.8)],
        pcbnew.B_Cu,
        0.18,
    )


def route_battery_adc(r: Router) -> None:
    # PA0 follows the outside of the VDDA escape and the MCU decoupling ring.
    # This deliberate F.Cu perimeter route needs no vias and keeps the sampled
    # high-impedance node away from every digital trunk.
    r.path(
        "/BAT_ADC",
        [
            (90.1125, 34.4),
            (89.65, 34.4),
            (89.4, 34.7),
            (89.4, 36.8),
            (88.8, 37.8),
            (88.4, 38.2),
            (88.4, 38.6),
            (88.0, 39.0),
            (88.0, 43.4),
            (87.2, 44.2),
            (86.4, 44.2),
            (86.0, 44.6),
            (84.8, 44.6),
            (84.0, 45.4),
            (83.92, 45.5),
        ],
        width=0.18,
    )


def route_ads_channel2_branches(r: Router) -> None:
    # The optional respiration-injection resistors sit at the lower board
    # edge.  CH2P/N rise as an ordered pair on L3, immediately adjacent to
    # the solid L2 ground reference, and return to F.Cu beside the existing
    # AFE filter endpoints.  This keeps them out of the dense protection row.
    r.path("/ADS_CH2P", [(36.71, 46.0), (36.71, 45.2)], width=0.18)
    r.via("/ADS_CH2P", (36.71, 45.2))
    r.path(
        "/ADS_CH2P",
        [
            (36.71, 45.2),
            (37.5, 44.41),
            (41.2, 44.41),
            (42.0, 43.61),
            (42.0, 41.4),
        ],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/ADS_CH2P", (42.0, 41.4))
    r.path(
        "/ADS_CH2P",
        [(42.0, 41.4), (42.0, 39.6)],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/ADS_CH2P", (42.0, 39.6))
    r.path(
        "/ADS_CH2P",
        [(42.0, 39.6), (42.4, 39.2), (42.4, 37.2), (44.4, 35.2)],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/ADS_CH2P", (44.4, 35.2))
    r.path("/ADS_CH2P", [(44.4, 35.2), (44.025, 34.8)], width=0.18)

    r.path("/ADS_CH2N", [(41.71, 46.0), (41.71, 45.2)], width=0.18)
    r.via("/ADS_CH2N", (41.71, 45.2))
    r.path(
        "/ADS_CH2N",
        [
            (41.71, 45.2),
            (42.2, 44.71),
            (43.6, 43.31),
            (43.6, 34.0),
            (44.0, 33.6),
        ],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/ADS_CH2N", (44.0, 33.6))
    r.path("/ADS_CH2N", [(44.0, 33.6), (44.025, 33.2)], width=0.18)


def route_ads_respiration_modulation(r: Router) -> None:
    # RESP_MODP/N use complementary corridors found between the existing AFE
    # dog-bones: P descends on L3 while N follows the matching B.Cu channel.
    # Both then sweep toward their lower-edge coupling capacitors with only
    # 45-degree changes of direction.
    r.path("/ADS_RESP_MODP", [(51.6, 33.0), (52.0, 33.4)], width=0.15)
    r.via("/ADS_RESP_MODP", (52.0, 33.4), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_RESP_MODP",
        [
            (52.0, 33.4),
            (52.6, 34.0),
            (52.6, 35.6),
            (53.0, 36.0),
            (53.1, 37.0),
            (52.1, 38.0),
            (51.4, 38.0),
            (49.4, 40.0),
            (47.6, 40.0),
            (42.2, 45.4),
            (42.2, 45.8),
            (34.8, 45.8),
            (34.2, 45.2),
            (33.52, 45.2),
        ],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/ADS_RESP_MODP", (33.52, 45.2))
    r.path("/ADS_RESP_MODP", [(33.52, 45.2), (33.52, 46.0)], width=0.18)

    r.path("/ADS_RESP_MODN", [(51.6, 33.8), (52.0, 34.2)], width=0.15)
    r.via("/ADS_RESP_MODN", (52.0, 34.2), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_RESP_MODN",
        [
            (52.0, 34.2),
            (51.0, 34.2),
            (50.4, 33.5),
            (49.6, 33.5),
            (49.1, 34.0),
            (49.1, 34.7),
            (47.5, 36.3),
            (47.5, 37.6),
            (42.4, 42.6),
            (42.4, 43.8),
            (41.4, 44.8),
            (39.4, 44.8),
            (38.8, 45.2),
            (38.52, 45.2),
        ],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/ADS_RESP_MODN", (38.52, 45.2))
    r.path("/ADS_RESP_MODN", [(38.52, 45.2), (38.52, 46.0)], width=0.18)


def route_ads_gpio_ties(r: Router) -> None:
    # The DNP GPIO straps are intentionally kept off the crowded SPI/START
    # channels on B.Cu.  GPIO1 exits toward the upper-right interstitial and
    # follows one clean L3 lane to the ordered pull-down row.
    r.path("/ADS_GPIO1_TIE", [(52.4, 33.8), (52.8, 33.4)], width=0.15)
    r.via("/ADS_GPIO1_TIE", (52.8, 33.4), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_GPIO1_TIE",
        [
            (52.8, 33.4),
            (53.2, 33.0),
            (53.6, 33.0),
            (53.8, 32.8),
            (53.8, 32.4),
            (54.2, 32.0),
            (54.6, 32.0),
            (55.8, 30.8),
            (57.2, 30.8),
            (59.0, 29.0),
            (63.4, 29.0),
        ],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/ADS_GPIO1_TIE", (63.4, 29.0))
    r.path("/ADS_GPIO1_TIE", [(63.4, 29.0), (63.99, 29.0)], width=0.18)

    # GPIO2 uses the next interstitial and a parallel L3 lane below GPIO1.
    # The route stays above the SPI-via fence and lands directly at R53.
    r.path("/ADS_GPIO2_TIE", [(54.0, 34.6), (53.6, 34.2)], width=0.15)
    r.via("/ADS_GPIO2_TIE", (53.6, 34.2), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_GPIO2_TIE",
        [
            (53.6, 34.2),
            (53.6, 33.8),
            (54.0, 33.4),
            (54.8, 33.4),
            (55.2, 33.4),
            (55.6, 33.0),
            (56.0, 33.0),
            (56.4, 32.6),
            (57.4, 32.6),
            (58.0, 32.0),
            (61.8, 32.0),
            (63.4, 30.4),
        ],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/ADS_GPIO2_TIE", (63.4, 30.4))
    r.path("/ADS_GPIO2_TIE", [(63.4, 30.4), (63.99, 30.4)], width=0.18)

    # GPIO3 forms the lower member of the L3 pair leaving the BGA.  It then
    # follows a separate B.Cu lane around the power vias and rises on the
    # outer side of the strap bank, parallel to GPIO4's final vertical.
    r.path("/ADS_GPIO3_TIE", [(53.2, 34.6), (53.6, 35.0)], width=0.15)
    r.via("/ADS_GPIO3_TIE", (53.6, 35.0), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_GPIO3_TIE",
        [
            (53.6, 35.0),
            (53.8, 35.0),
            (55.8, 37.0),
            (56.2, 37.0),
            (57.8, 38.6),
            (58.0, 38.6),
        ],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/ADS_GPIO3_TIE", (58.0, 38.6))
    r.path(
        "/ADS_GPIO3_TIE",
        [
            (58.0, 38.6),
            (59.2, 38.6),
            (60.0, 37.8),
            (62.0, 37.8),
            (62.8, 38.6),
            (63.2, 38.6),
            (63.6, 38.2),
            (64.0, 38.2),
            (64.2, 38.0),
        ],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/ADS_GPIO3_TIE", (64.2, 38.0))
    r.path(
        "/ADS_GPIO3_TIE",
        [(64.2, 38.0), (64.2, 33.4), (63.99, 33.2)],
        width=0.18,
    )

    # GPIO3 crosses the SPI fanout once in the deliberately reserved B.Cu
    # inter-lane, then joins the same ordered L3 bundle outside the package.
    r.path("/ADS_GPIO3_TIE", [(53.2, 34.6), (53.6, 35.0)], width=0.15)
    r.via("/ADS_GPIO3_TIE", (53.6, 35.0), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_GPIO3_TIE",
        [
            (53.6, 35.0),
            (53.2, 35.0),
            (52.8, 34.6),
            (52.8, 34.1),
            (53.2, 33.7),
            (53.6, 33.7),
            (54.0, 33.3),
            (54.4, 33.3),
            (54.8, 32.9),
            (55.2, 32.9),
            (55.6, 33.3),
            (56.0, 33.3),
            (56.8, 34.1),
        ],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/ADS_GPIO3_TIE", (56.8, 34.1))
    r.path(
        "/ADS_GPIO3_TIE",
        [
            (56.8, 34.1),
            (57.2, 33.7),
            (58.4, 33.7),
            (59.0, 34.3),
            (61.0, 34.3),
            (63.4, 31.9),
            (63.4, 31.8),
        ],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/ADS_GPIO3_TIE", (63.4, 31.8))
    r.path("/ADS_GPIO3_TIE", [(63.4, 31.8), (63.99, 31.8)], width=0.18)

    # GPIO4 is the only lower-left escape.  It follows a single B.Cu lane
    # below ADS_CS, then rises on F.Cu beside (not through) the strap bank.
    r.path("/ADS_GPIO4_TIE", [(52.4, 34.6), (52.0, 35.0)], width=0.15)
    r.via("/ADS_GPIO4_TIE", (52.0, 35.0), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_GPIO4_TIE",
        [
            (52.0, 35.0),
            (52.4, 35.4),
            (53.2, 35.4),
            (55.2, 37.4),
            (62.4, 37.4),
            (63.0, 38.0),
        ],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/ADS_GPIO4_TIE", (63.0, 38.0))
    r.path(
        "/ADS_GPIO4_TIE",
        [(63.0, 38.0), (63.0, 32.8), (63.99, 31.8)],
        width=0.18,
    )


def route_ads_gpio_ties_v2(r: Router) -> None:
    """Route the four optional GPIO straps after all mandatory ADS controls."""
    # GPIO1 takes the free upper-left B.Cu channel.  A short L3 bridge crosses
    # the VCAP2 vertical, after which the route returns to B.Cu and lands at
    # the first resistor in the ordered strap bank.
    r.path("/ADS_GPIO1_TIE", [(52.4, 33.8), (52.8, 33.4)], width=0.15)
    r.via("/ADS_GPIO1_TIE", (52.8, 33.4), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_GPIO1_TIE",
        [
            (52.8, 33.4),
            (52.2, 32.8),
            (52.2, 32.4),
            (52.8, 31.8),
            (52.8, 28.6),
            (53.0, 28.4),
        ],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/ADS_GPIO1_TIE", (53.0, 28.4))
    r.path(
        "/ADS_GPIO1_TIE",
        [(53.0, 28.4), (53.2, 28.6), (55.4, 28.6), (55.6, 28.4)],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/ADS_GPIO1_TIE", (55.6, 28.4))
    r.path(
        "/ADS_GPIO1_TIE",
        [
            (55.6, 28.4),
            (56.8, 29.6),
            (62.2, 29.6),
            (62.4, 29.4),
            (62.6, 29.4),
            (62.8, 29.2),
            (63.2, 29.2),
            (63.4, 29.0),
        ],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/ADS_GPIO1_TIE", (63.4, 29.0))
    r.path("/ADS_GPIO1_TIE", [(63.4, 29.0), (63.99, 29.0)], width=0.18)

    # GPIO2 runs below CS on L3, changes layer once outside the BGA service
    # bay, and rises along the left edge of the strap bank.
    r.path("/ADS_GPIO2_TIE", [(54.0, 34.6), (53.6, 34.2)], width=0.15)
    r.via("/ADS_GPIO2_TIE", (53.6, 34.2), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_GPIO2_TIE",
        [(53.6, 34.2), (56.0, 36.6), (56.8, 36.6), (58.2, 38.0)],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/ADS_GPIO2_TIE", (58.2, 38.0), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_GPIO2_TIE",
        [
            (58.2, 38.0),
            (58.8, 38.6),
            (59.2, 38.6),
            (59.6, 38.2),
            (59.6, 37.4),
            (59.8, 37.2),
            (59.8, 37.0),
            (60.8, 36.0),
            (61.0, 36.0),
            (61.0, 34.6),
            (62.2, 33.4),
            (62.2, 33.0),
            (62.6, 32.6),
            (62.6, 31.8),
            (63.2, 31.2),
            (63.2, 30.6),
            (63.4, 30.4),
        ],
        pcbnew.F_Cu,
        0.18,
    )
    r.path("/ADS_GPIO2_TIE", [(63.4, 30.4), (63.99, 30.4)], width=0.18)

    # GPIO3 forms the lower member of the L3 pair leaving the BGA.  It then
    # follows a separate B.Cu lane around the power vias and rises on the
    # outer side of the strap bank, parallel to GPIO4's final vertical.
    r.path("/ADS_GPIO3_TIE", [(53.2, 34.6), (53.6, 35.0)], width=0.15)
    r.via("/ADS_GPIO3_TIE", (53.6, 35.0), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_GPIO3_TIE",
        [
            (53.6, 35.0),
            (53.8, 35.0),
            (55.8, 37.0),
            (56.2, 37.0),
            (57.8, 38.6),
            (58.0, 38.6),
        ],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/ADS_GPIO3_TIE", (58.0, 38.6), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_GPIO3_TIE",
        [
            (58.0, 38.6),
            (59.2, 38.6),
            (60.0, 37.8),
            (62.0, 37.8),
            (62.8, 38.6),
            (63.2, 38.6),
            (63.6, 38.2),
            (64.0, 38.2),
            (64.3, 37.9),
        ],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/ADS_GPIO3_TIE", (64.3, 37.9), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_GPIO3_TIE",
        [(64.3, 37.9), (64.3, 33.5), (63.99, 33.2)],
        width=0.18,
    )

    # GPIO4 leaves the lower-left interstitial, steps below DRDY's local
    # dog-bone, then follows the reserved B.Cu lane beneath the SPI bundle.
    r.path("/ADS_GPIO4_TIE", [(52.4, 34.6), (52.0, 35.0)], width=0.15)
    r.via("/ADS_GPIO4_TIE", (52.0, 35.0), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_GPIO4_TIE",
        [
            (52.0, 35.0),
            (52.4, 35.4),
            (52.4, 36.2),
            (53.6, 37.4),
            (54.2, 38.0),
            (54.8, 38.0),
            (55.4, 37.4),
            (62.4, 37.4),
            (63.0, 38.0),
        ],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/ADS_GPIO4_TIE", (63.0, 38.0))
    r.path(
        "/ADS_GPIO4_TIE",
        [(63.0, 38.0), (63.0, 32.8), (63.99, 31.8)],
        width=0.18,
    )


def route_ads_power_controls(r: Router) -> None:
    # PWDN and RESET leave adjacent BGA interstitials as an ordered pair.
    # Their slow-control trunks use L3 beneath the IMU and MCU, with the two
    # pull-ups tapped in the central service bay.  This keeps the SPI lanes on
    # B.Cu untouched and gives both signals a continuous GND reference.
    r.path("/ADS_PWDN", [(52.4, 33.0), (52.8, 32.6)], width=0.15)
    r.via("/ADS_PWDN", (52.8, 32.6), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_PWDN",
        [
            (52.8, 32.6),
            (52.8, 31.8),
            (53.2, 31.4),
            (53.6, 31.0),
            (55.2, 31.0),
            (56.4, 32.2),
            (75.4, 32.2),
        ],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/ADS_PWDN", (75.4, 32.2))
    r.path(
        "/ADS_PWDN",
        [(75.4, 32.2), (77.4, 34.2), (77.4, 34.8)],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/ADS_PWDN", (77.4, 34.8))
    r.path(
        "/ADS_PWDN",
        [(77.4, 34.8), (78.0, 35.4), (78.0, 35.99), (78.4, 35.99)],
        width=0.18,
    )
    r.path(
        "/ADS_PWDN",
        [
            (77.4, 34.8),
            (78.8, 36.2),
            (95.8, 36.2),
            (98.0, 36.2),
            (98.0, 35.0),
            (98.8, 34.2),
        ],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/ADS_PWDN", (98.8, 34.2), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_PWDN",
        [(98.8, 34.2), (98.6, 34.0), (97.8875, 34.0)],
        width=0.15,
    )

    r.path("/ADS_RESET", [(53.2, 33.0), (53.6, 32.6)], width=0.15)
    r.via("/ADS_RESET", (53.6, 32.6), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_RESET",
        [
            (53.6, 32.6),
            (53.6, 33.0),
            (54.0, 33.4),
            (54.4, 33.4),
            (54.8, 33.0),
            (56.0, 33.0),
            (76.4, 33.0),
            (78.0, 34.6),
            (80.2, 34.6),
        ],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/ADS_RESET", (80.2, 34.6))
    r.path(
        "/ADS_RESET",
        [(80.2, 34.6), (80.2, 35.4), (79.61, 35.99), (79.6, 35.99)],
        width=0.18,
    )
    r.path(
        "/ADS_RESET",
        [
            (80.2, 34.6),
            (81.2, 35.6),
            (95.8, 35.6),
            (97.5, 35.6),
            (97.5, 34.7),
            (98.8, 33.4),
        ],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/ADS_RESET", (98.8, 33.4), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_RESET",
        [(98.8, 33.4), (98.6, 33.6), (97.8875, 33.6)],
        width=0.15,
    )


def route_ads_drdy(r: Router) -> None:
    # DRDY crosses the SCLK dog-bone in the open B.Cu interstitial exposed by
    # moving only the short CS crossover to L3.  This compact fanout keeps all
    # four GPIO dog-bone sites free and rejoins the straight L3 control trunk.
    r.path("/ADS_DRDY", [(53.2, 35.4), (53.6, 35.8)], width=0.15)
    r.via("/ADS_DRDY", (53.6, 35.8), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_DRDY",
        [
            (53.6, 35.8),
            (54.0, 35.4),
            (54.4, 35.0),
            (54.8, 34.6),
            (55.0, 34.4),
            (55.0, 33.8),
            (55.3, 33.3),
            (56.0, 33.3),
            (56.8, 34.1),
        ],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/ADS_DRDY", (56.8, 34.1))
    r.path(
        "/ADS_DRDY",
        [(56.8, 34.1), (75.8, 34.1), (75.8, 34.0)],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/ADS_DRDY", (75.8, 34.0))
    r.path("/ADS_DRDY", [(75.8, 34.0), (79.0, 34.0)], width=0.18)
    r.via("/ADS_DRDY", (79.0, 34.0))
    r.path(
        "/ADS_DRDY",
        [
            (79.0, 34.0),
            (78.8, 33.8),
            (78.8, 33.0),
            (79.2, 32.6),
            (80.8, 32.6),
            (81.0, 32.8),
            (82.8, 32.8),
            (83.2, 32.4),
            (83.8, 32.4),
        ],
        pcbnew.In2_Cu,
        0.18,
    )
    r.via("/ADS_DRDY", (83.8, 32.4), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_DRDY",
        [
            (83.8, 32.4),
            (86.4, 32.4),
            (87.2, 32.4),
            (88.0, 33.2),
        ],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/ADS_DRDY", (88.0, 33.2), diameter=0.45, drill=0.20)
    r.path(
        "/ADS_DRDY",
        [
            (88.0, 33.2),
            (88.4, 33.2),
            (89.2, 32.4),
            (90.1125, 32.4),
        ],
        width=0.15,
    )


def route_mcu_boot(r: Router) -> None:
    # BOOT0 uses the open B.Cu lane between USB_VBUS_SENSE and ADS_START.
    # Its pull-down now sits beside TP3, so the branch is short and does not
    # cut through the LSE crystal or its two load capacitors.
    r.path("/BOOT0", [(90.1125, 30.4), (86.9, 30.4)], width=0.15)
    r.via("/BOOT0", (86.9, 30.4), diameter=0.45, drill=0.20)
    r.path(
        "/BOOT0",
        [(86.9, 30.4), (86.6, 30.7), (77.5, 30.7), (77.5, 29.8)],
        pcbnew.B_Cu,
        0.18,
    )
    r.via("/BOOT0", (77.5, 29.8))
    r.path(
        "/BOOT0",
        [(77.5, 29.0), (77.5, 30.49)],
        width=0.18,
    )


def route_power_planes(r: Router) -> None:
    # L3 is split longitudinally: patient/AFE analog supply on the left and
    # digital supply on the right.  Signal tracks already placed on L3 carve
    # narrow, deterministic channels through these pours.
    r.zone(
        "/3V0_A",
        pcbnew.In2_Cu,
        [(20.4, 18.4), (69.0, 18.4), (69.0, 49.6), (20.4, 49.6)],
    )
    r.zone(
        "/3V0_D",
        pcbnew.In2_Cu,
        [(69.4, 18.4), (109.0, 18.4), (109.0, 49.6), (69.4, 49.6)],
    )

    # ADS1294R AVDD balls: four short same-net rails, each with one dog-bone
    # into the analog plane.
    for x_pos, y_first, y_last, via_point in [
        (49.2, 35.4, 37.8, (48.8, 38.2)),
        (50.0, 35.4, 37.8, (49.6, 38.2)),
        (53.2, 36.2, 37.8, (53.6, 38.2)),
    ]:
        r.path("/3V0_A", [(x_pos, y_first), (x_pos, y_last), via_point], width=0.20)
        r.via("/3V0_A", via_point, diameter=0.45, drill=0.20)
    r.segment("/3V0_A", xy(51.6, 37.8), xy(51.6, 38.6), pcbnew.F_Cu, 0.15)
    r.via("/3V0_A", (51.6, 38.6), diameter=0.45, drill=0.20)
    r.segment("/3V0_A", xy(51.6, 37.0), xy(52.0, 37.4), pcbnew.F_Cu, 0.15)
    r.via("/3V0_A", (52.0, 37.4), diameter=0.45, drill=0.20)

    for endpoint, via_point in [
        (("D6", "1"), (34.8, 33.55)),
        (("D8", "1"), (37.0, 35.75)),
        (("D10", "1"), (39.2, 37.95)),
        (("D12", "1"), (41.4, 39.3)),
        (("R16", "2"), (62.4, 35.0)),
        (("R17", "2"), (62.2, 40.3)),
        (("C20", "1"), (63.7, 27.8)),
        (("C21", "1"), (66.5, 27.8)),
        (("C35", "1"), (68.1, 23.6)),
    ]:
        r.plane_drop(endpoint, via_point, width=0.30)
    # The two analog pull-ups form one straight local rail.  This explicit
    # F.Cu tie is more robust than relying on two L3 islands separated by the
    # ADS control-bus corridor.
    r.path("/3V0_A", [(61.51, 35.0), (61.51, 37.4)], width=0.30)
    r.connect(("U6", "5"), ("C35", "1"), (66.2, 21.85), width=0.35)

    # Digital rail: regulator output, decoupling ring, debug reference and
    # local pull-ups each enter the right-hand plane with a very short stub.
    for endpoint, via_point, layer in [
        (("U5", "5"), (79.3, 40.5), pcbnew.F_Cu),
        (("C33", "1"), (81.2, 42.8), pcbnew.F_Cu),
        (("C52", "1"), (92.4, 26.6), pcbnew.F_Cu),
        (("C53", "1"), (94.0, 26.6), pcbnew.F_Cu),
        (("C54", "1"), (89.0, 40.8), pcbnew.F_Cu),
        (("C55", "1"), (91.0, 40.8), pcbnew.F_Cu),
        (("C58", "1"), (93.0, 40.8), pcbnew.F_Cu),
        (("C59", "1"), (95.0, 40.8), pcbnew.F_Cu),
        (("C60", "1"), (92.5, 42.5), pcbnew.F_Cu),
        (("C62", "1"), (95.5, 43.7), pcbnew.F_Cu),
        (("J5", "1"), (98.0, 23.8), pcbnew.B_Cu),
        (("R29", "1"), (78.4, 38.2), pcbnew.F_Cu),
        (("R30", "1"), (79.6, 38.2), pcbnew.F_Cu),
        (("R32", "1"), (76.6, 34.6), pcbnew.F_Cu),
        (("R38", "1"), (84.8, 31.8), pcbnew.F_Cu),
        (("FB1", "1"), (83.5, 38.6), pcbnew.F_Cu),
        (("R25", "1"), (71.8, 45.7), pcbnew.F_Cu),
        (("U3", "12"), (83.8, 35.0), pcbnew.F_Cu),
        (("R33", "1"), (83.2, 40.8), pcbnew.F_Cu),
        (("D15", "2"), (87.8, 21.4), pcbnew.F_Cu),
        (("U2", "68"), (90.8, 27.2), pcbnew.F_Cu),
        (("L1", "1"), (103.5, 28.4), pcbnew.F_Cu),
        (("C57", "1"), (99.5, 19.7), pcbnew.F_Cu),
        (("R37", "1"), (101.5, 22.5), pcbnew.F_Cu),
        (("U8", "1"), (99.0, 44.8), pcbnew.F_Cu),
        (("R50", "1"), (109.0, 48.3), pcbnew.F_Cu),
    ]:
        diameter = 0.45 if endpoint[0] == "U2" else 0.50
        r.plane_drop(
            endpoint,
            via_point,
            layer=layer,
            width=0.20 if endpoint[0] == "U2" else 0.25,
            diameter=diameter,
        )

    # R50 is the digital-domain card-detect pull-up at the far edge of the SD
    # cluster.  Its short F.Cu run clears the socket shield, then a single B.Cu
    # dogleg passes beneath the local SD-power parts to U8's existing 3V0_D
    # drop.  This avoids a slot in the solid In1 return plane.
    r.path(
        "/3V0_D",
        [(109.0, 48.3), (108.5, 47.8), (108.5, 45.4), (105.9, 45.4)],
        width=0.25,
    )
    r.via("/3V0_D", (105.9, 45.4))
    r.path(
        "/3V0_D",
        [
            (105.9, 45.4),
            (105.9, 46.0),
            (104.9, 47.0),
            (103.7, 47.0),
            (102.9, 46.2),
            (102.9, 45.4),
            (102.3, 44.8),
            (99.0, 44.8),
        ],
        pcbnew.B_Cu,
        0.25,
    )

    # The reset pull-up moved below the MCU to open a real left-side fanout
    # bay, so the IMU SDA pull-up now takes its own short plane entry.
    r.plane_drop(("R39", "1"), (84.8, 34.8), width=0.20)

    # C51 sits beside the debug landing bay.  Approach its plane via from the
    # left and below so the power trace never cuts across the adjacent GND pad.
    r.path(
        "/3V0_D",
        [
            (88.52, 25.8),
            (88.2, 25.8),
            (88.2, 26.0),
            (88.7, 26.5),
            (89.1, 26.5),
        ],
        width=0.25,
    )
    r.via("/3V0_D", (89.1, 26.5))

    # The debug header's 3V reference lies above the USB-only L3 rail while
    # C53 lies below it.  Join their existing drops with one compact L2 dogleg
    # that clears both SWD landing vias; this is a reference feed, not a load
    # current path.
    r.path(
        "/3V0_D",
        [(98.0, 23.8), (96.6, 23.8), (95.2, 24.8), (94.0, 26.6)],
        pcbnew.In1_Cu,
        0.25,
    )

    # With U3 rotated toward the MCU, its remaining two VDD pads escape normal
    # to the left and bottom package edges before dropping into L3.
    r.path(
        "/3V0_D",
        [(80.9875, 34.0), (80.3, 34.0), (79.6, 33.3)],
        width=0.18,
    )
    r.via("/3V0_D", (79.6, 33.3))
    r.path(
        "/3V0_D",
        [(81.25, 35.7625), (81.25, 36.3), (80.5, 37.05), (80.5, 38.2)],
        width=0.18,
    )
    r.via("/3V0_D", (80.5, 38.2))
    # The upper VDD drop joins pad 12 through the quiet B.Cu corridor between
    # the horizontal service buses.
    r.path(
        "/3V0_D",
        [
            (79.6, 33.3),
            (82.4, 33.3),
            (82.8, 33.7),
            (82.8, 34.4),
            (83.4, 35.0),
            (83.8, 35.0),
        ],
        pcbnew.B_Cu,
        0.20,
    )
    # Pad 8 sits beyond three continuous L2/L3 service buses.  A compact L2
    # bridge beneath U3 joins it to the upper VDD drop without introducing a
    # long perimeter route; nearby ground stitching restores the return path.
    r.path(
        "/3V0_D",
        [
            (79.6, 33.3),
            (80.9, 33.3),
            (81.2, 33.6),
            (81.2, 37.1),
            (80.5, 37.8),
            (80.5, 38.2),
        ],
        pcbnew.In1_Cu,
        0.25,
    )
    # QFN VDD pad 30 exits normal to the package edge.  A short left jog only
    # begins after clearing neighbouring PB11, and remains clear of RF1.
    r.path(
        "/3V0_D",
        [(95.6, 35.8875), (95.6, 36.4), (95.2, 36.8), (95.2, 37.2)],
        width=0.18,
    )
    r.via("/3V0_D", (95.2, 37.2), diameter=0.45, drill=0.20)


def add_ground_planes(r: Router) -> None:
    main = [(20.4, 18.4), (119.6, 18.4), (119.6, 49.6), (20.4, 49.6)]
    for layer in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.B_Cu):
        r.zone("/GND", layer, main)
    r.named_rule_area(
        "ADS_BGA_ESCAPE",
        [(47.8, 30.8), (55.2, 30.8), (55.2, 39.2), (47.8, 39.2)],
    )
    r.named_rule_area(
        "MCU_QFN_ESCAPE",
        [(88.5, 27.5), (98.5, 27.5), (98.5, 36.9), (88.5, 36.9)],
    )
    r.antenna_keepout()


def add_ground_stitching(r: Router) -> None:
    # These four stitches tie narrow F/B ground-pour pockets directly into
    # the continuous In1 reference plane.  Each location is centered in its
    # pocket and clear of patient, BGA, SD-power, and LSE copper.
    for point, diameter in [
        # Patient-input and AFE return fence.
        ((28.00, 30.40), 0.45),
        ((27.85, 37.33), 0.45),
        ((46.20, 30.40), 0.45),
        ((56.60, 30.40), 0.45),
        ((46.20, 39.80), 0.45),
        ((56.40, 38.65), 0.45),
        # Power/mux/IMU-side return anchors.
        ((70.00, 21.80), 0.45),
        ((70.00, 46.60), 0.45),
        ((76.00, 39.00), 0.45),
        # MCU, USB, RF and SD local returns.
        ((100.80, 38.00), 0.45),
        ((100.00, 21.80), 0.45),
        ((98.20, 45.40), 0.45),
        ((110.00, 46.20), 0.45),
        ((107.80, 38.60), 0.45),
        ((104.00, 38.40), 0.45),
        ((102.60, 49.18), 0.45),
        ((88.40, 29.94), 0.45),
        ((107.75, 47.44), 0.45),
        # Evenly spaced perimeter ties, outside the antenna keepout.
        ((35.00, 19.00), 0.45),
        ((60.00, 19.00), 0.45),
        ((80.00, 19.00), 0.45),
        ((35.00, 48.80), 0.45),
        ((59.20, 48.80), 0.45),
        ((85.00, 48.80), 0.45),
    ]:
        r.via("/GND", point, diameter=diameter, drill=0.20)


def main() -> None:
    board = pcbnew.LoadBoard(str(BOARD_PATH))
    clear_copper(board)
    router = Router(board)
    route_ecg(router)
    route_ads_analog(router)
    route_ads_support(router)
    route_ads_digital(router)
    route_ads_power(router)
    route_clocks_smps_rf(router)
    route_usb(router)
    route_usb_vbus_sense(router)
    route_sd_card_side(router)
    route_sd_aux_card_side(router)
    route_sd_power_enable_local(router)
    route_sd_controls(router)
    route_sd_mcu_side(router)
    route_sd_power(router)
    route_vbus_power(router)
    route_battery_and_system_power(router)
    route_local_power_and_support(router)
    route_local_signal_branches(router)
    route_imu_i2c(router)
    route_imu_interrupts(router)
    route_mcu_status(router)
    route_mcu_reset_local(router)
    route_debug_service(router)
    route_battery_adc(router)
    route_ads_channel2_branches(router)
    route_ads_respiration_modulation(router)
    route_ads_gpio_ties_v2(router)
    route_ads_power_controls(router)
    route_ads_drdy(router)
    route_mcu_boot(router)
    route_power_planes(router)
    add_ground_planes(router)
    add_ground_stitching(router)
    pcbnew.SaveBoard(str(BOARD_PATH), board)


if __name__ == "__main__":
    main()
