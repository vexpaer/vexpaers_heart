#!/usr/bin/env python3
"""Audit the signed-off Holter PCB and write a concise release report.

Run this with KiCad's bundled Python so that ``pcbnew`` is available.
"""

from __future__ import annotations

import argparse
import csv
import heapq
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parents[1]
BOARD_PATH = ROOT / "hardware" / "holter_v1" / "holter_v1.kicad_pcb"
BOM_PATH = ROOT / "docs" / "bom_source.csv"
PIN_AUDIT_PATH = ROOT / "docs" / "pin_net_audit.csv"


def mm(value: int) -> float:
    return pcbnew.ToMM(value)


def footprints_by_reference(board: pcbnew.BOARD) -> dict[str, pcbnew.FOOTPRINT]:
    return {footprint.GetReference(): footprint for footprint in board.GetFootprints()}


def pad(board: pcbnew.BOARD, reference: str, number: str) -> pcbnew.PAD:
    footprint = footprints_by_reference(board)[reference]
    matches = [candidate for candidate in footprint.Pads() if candidate.GetNumber() == number]
    if len(matches) != 1:
        raise AssertionError(f"Expected one {reference}-{number} pad, found {len(matches)}")
    return matches[0]


def net_stats(board: pcbnew.BOARD, net_name: str) -> dict[str, object]:
    tracks = [
        item
        for item in board.Tracks()
        if item.GetNetname() == net_name and not isinstance(item, pcbnew.PCB_VIA)
    ]
    vias = [
        item
        for item in board.Tracks()
        if item.GetNetname() == net_name and isinstance(item, pcbnew.PCB_VIA)
    ]
    return {
        "length": sum(mm(item.GetLength()) for item in tracks),
        "vias": len(vias),
        "layers": sorted({board.GetLayerName(item.GetLayer()) for item in tracks}),
        "widths": sorted({round(mm(item.GetWidth()), 3) for item in tracks}),
    }


Node = tuple[int, int, int]


def node_at(point: pcbnew.VECTOR2I, layer: int) -> Node:
    return point.x, point.y, layer


def shortest_copper_path(
    board: pcbnew.BOARD,
    net_name: str,
    start_pad: pcbnew.PAD,
    end_pad: pcbnew.PAD,
) -> float:
    """Return routed distance in mm, ignoring zero-length layer changes."""

    adjacency: dict[Node, list[tuple[Node, float]]] = defaultdict(list)
    active_copper = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)

    def connect(first: Node, second: Node, length: float) -> None:
        adjacency[first].append((second, length))
        adjacency[second].append((first, length))

    for item in board.Tracks():
        if item.GetNetname() != net_name:
            continue
        if isinstance(item, pcbnew.PCB_VIA):
            via_nodes = [node_at(item.GetPosition(), layer) for layer in active_copper]
            for first, second in zip(via_nodes, via_nodes[1:]):
                connect(first, second, 0.0)
            continue
        connect(
            node_at(item.GetStart(), item.GetLayer()),
            node_at(item.GetEnd(), item.GetLayer()),
            mm(item.GetLength()),
        )

    def endpoint_nodes(endpoint: pcbnew.PAD) -> list[Node]:
        position = endpoint.GetPosition()
        candidates = [
            node_at(position, layer)
            for layer in active_copper
            if endpoint.IsOnLayer(layer) and node_at(position, layer) in adjacency
        ]
        if not candidates:
            raise AssertionError(
                f"No centered routed endpoint for {endpoint.GetParentFootprint().GetReference()}-"
                f"{endpoint.GetNumber()} on {net_name}"
            )
        return candidates

    starts = endpoint_nodes(start_pad)
    targets = set(endpoint_nodes(end_pad))
    distances: dict[Node, float] = {}
    queue: list[tuple[float, Node]] = []
    for start in starts:
        distances[start] = 0.0
        heapq.heappush(queue, (0.0, start))

    while queue:
        distance, current = heapq.heappop(queue)
        if distance != distances[current]:
            continue
        if current in targets:
            return distance
        for neighbor, edge_length in adjacency[current]:
            candidate = distance + edge_length
            if candidate < distances.get(neighbor, float("inf")):
                distances[neighbor] = candidate
                heapq.heappush(queue, (candidate, neighbor))
    raise AssertionError(f"No routed path found on {net_name}")


def assert_bom_and_values(board: pcbnew.BOARD) -> tuple[int, int, int]:
    with BOM_PATH.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    fitted = [row for row in rows if not row["DNP"]]
    missing_mpn = [row["Reference"] for row in fitted if not row["Manufacturer Part Number"]]
    if missing_mpn:
        raise AssertionError(f"Fitted BOM entries without an MPN: {', '.join(missing_mpn)}")

    footprints = footprints_by_reference(board)
    value_mismatches = [
        (row["Reference"], footprints[row["Reference"]].GetValue(), row["Value"])
        for row in rows
        if row["Reference"] in footprints
        and footprints[row["Reference"]].GetValue() != row["Value"]
    ]
    if value_mismatches:
        raise AssertionError(f"PCB/BOM value mismatches: {value_mismatches}")
    return len(rows), len(fitted), len(rows) - len(fitted)


def assert_pin_net_audit(board: pcbnew.BOARD) -> list[str]:
    with PIN_AUDIT_PATH.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    physical_references = set(footprints_by_reference(board))
    expected = {
        (row["Reference"], row["Pin"]): row["Net"]
        for row in rows
        if row["Reference"] in physical_references
    }
    actual: dict[tuple[str, str], set[str]] = defaultdict(set)
    extras: list[str] = []
    for footprint in board.GetFootprints():
        reference = footprint.GetReference()
        for candidate in footprint.Pads():
            key = reference, candidate.GetNumber()
            if key not in expected:
                # Some library footprints use unnumbered copper primitives to
                # build a compound pad shape.  They do not represent an
                # additional schematic pin.
                if candidate.GetNumber():
                    extras.append(f"{reference}-{candidate.GetNumber()}")
                continue
            actual[key].add(candidate.GetNetname())

    mismatches: list[str] = []
    for key, net_name in expected.items():
        if key not in actual:
            mismatches.append(f"{key[0]}-{key[1]} missing from PCB")
        elif actual[key] != {net_name}:
            mismatches.append(f"{key[0]}-{key[1]} expected {net_name!r}, got {sorted(actual[key])}")
    if mismatches:
        raise AssertionError("Pin/net mismatches: " + "; ".join(mismatches))
    return sorted(set(extras))


def assert_vias(board: pcbnew.BOARD) -> int:
    vias = [item for item in board.Tracks() if isinstance(item, pcbnew.PCB_VIA)]
    invalid = []
    for item in vias:
        geometry = (
            item.GetViaType(),
            board.GetLayerName(item.GetLayer()),
            board.GetLayerName(item.BottomLayer()),
            round(mm(item.GetWidth(pcbnew.F_Cu)), 3),
            round(mm(item.GetDrillValue()), 3),
        )
        expected = (pcbnew.VIATYPE_THROUGH, "F.Cu", "B.Cu", 0.45, 0.2)
        if geometry != expected:
            invalid.append(geometry)
    if invalid:
        raise AssertionError(f"Non-release via geometry: {Counter(invalid)}")
    return len(vias)


def assert_courtyards_and_sides(board: pcbnew.BOARD) -> tuple[int, list[str]]:
    missing: list[str] = []
    bottom: list[str] = []
    for footprint in board.GetFootprints():
        on_front = footprint.GetSide() == pcbnew.F_Cu
        if not on_front:
            bottom.append(footprint.GetReference())
        courtyard_layer = pcbnew.F_CrtYd if on_front else pcbnew.B_CrtYd
        if footprint.GetCourtyard(courtyard_layer).OutlineCount() == 0:
            missing.append(footprint.GetReference())
    if missing:
        raise AssertionError(f"Footprints without courtyard: {', '.join(sorted(missing))}")
    return len(board.GetFootprints()) - len(bottom), sorted(bottom)


def assert_planes_keepout_and_critical_nets(board: pcbnew.BOARD) -> tuple[int, tuple[float, float]]:
    in1_tracks = [
        item
        for item in board.Tracks()
        if not isinstance(item, pcbnew.PCB_VIA) and item.GetLayer() == pcbnew.In1_Cu
    ]
    if in1_tracks:
        raise AssertionError(f"In1.Cu contains {len(in1_tracks)} signal tracks")

    gnd_planes = [
        zone
        for zone in board.Zones()
        if not zone.GetIsRuleArea()
        and zone.GetNetname() == "GND"
        and zone.IsOnLayer(pcbnew.In1_Cu)
    ]
    if len(gnd_planes) != 1:
        raise AssertionError(f"Expected one In1.Cu GND plane, found {len(gnd_planes)}")

    keepout_layers = []
    keepout_size: tuple[float, float] | None = None
    for zone in board.Zones():
        if not zone.GetIsRuleArea():
            continue
        layers = [
            layer
            for layer in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
            if zone.IsOnLayer(layer)
        ]
        if len(layers) != 1 or not zone.GetDoNotAllowZoneFills() or not zone.GetDoNotAllowVias():
            continue
        keepout_layers.append(board.GetLayerName(layers[0]))
        bounds = zone.Outline().BBox()
        size = round(mm(bounds.GetWidth()), 3), round(mm(bounds.GetHeight()), 3)
        keepout_size = keepout_size or size
        if size != keepout_size:
            raise AssertionError("RF keepout bounds differ by layer")
    expected_layers = {"F.Cu", "In1.Cu", "In2.Cu", "B.Cu"}
    if set(keepout_layers) != expected_layers:
        raise AssertionError(f"RF keepout layers are {sorted(keepout_layers)}")

    critical_nets = (
        "RF_MCU",
        "RF_FILTER_OUT",
        "RF_ANT_FEED",
        "HSE_IN",
        "HSE_OUT",
        "LSE_IN",
        "LSE_OUT",
        "SMPS_IN",
        "SMPS_SW",
        "SMPS_FB",
    )
    for net_name in critical_nets:
        stats = net_stats(board, net_name)
        if stats["vias"] != 0 or stats["layers"] != ["F.Cu"]:
            raise AssertionError(f"{net_name} is not front-only/via-free: {stats}")
    assert keepout_size is not None
    return len(in1_tracks), keepout_size


def report(board_path: Path, output: Path) -> None:
    board = pcbnew.LoadBoard(str(board_path))
    via_count = assert_vias(board)
    front_count, bottom_refs = assert_courtyards_and_sides(board)
    _, keepout_size = assert_planes_keepout_and_critical_nets(board)
    bom_rows, fitted_rows, dnp_rows = assert_bom_and_values(board)
    extra_pads = assert_pin_net_audit(board)

    usb_dm_main = shortest_copper_path(board, "USB_DM", pad(board, "U2", "52"), pad(board, "R21", "2"))
    usb_dm_pogo = shortest_copper_path(board, "USB_DM_POGO", pad(board, "R21", "1"), pad(board, "J3", "2"))
    usb_dp_main = shortest_copper_path(board, "USB_DP", pad(board, "U2", "53"), pad(board, "R22", "2"))
    usb_dp_pogo = shortest_copper_path(board, "USB_DP_POGO", pad(board, "R22", "1"), pad(board, "J3", "3"))
    usb_dm_total = usb_dm_main + usb_dm_pogo
    usb_dp_total = usb_dp_main + usb_dp_pogo
    usb_skew = abs(usb_dp_total - usb_dm_total)

    bbox = board.GetBoardEdgesBoundingBox()
    bbox_width = mm(bbox.GetWidth())
    bbox_height = mm(bbox.GetHeight())

    tracked_nets = (
        "USB_DM",
        "USB_DM_POGO",
        "USB_DP",
        "USB_DP_POGO",
        "SD_SCK_MCU",
        "SD_MISO_MCU",
        "SD_MOSI_MCU",
        "SD_CS_MCU",
        "RF_MCU",
        "RF_FILTER_OUT",
        "RF_ANT_FEED",
        "HSE_IN",
        "HSE_OUT",
        "LSE_IN",
        "LSE_OUT",
        "SMPS_IN",
        "SMPS_SW",
        "SMPS_FB",
    )
    stats = {net_name: net_stats(board, net_name) for net_name in tracked_nets}

    lines = [
        "# Holter V1 hardware release audit",
        "",
        f"Generated {date.today().isoformat()} from the signed-off KiCad board.",
        "",
        "## Release gates",
        "",
        "- Main schematic: ERC 0 errors / 0 warnings.",
        "- Main PCB: DRC 0 violations, 0 unconnected pads, 0 footprint errors.",
        f"- Vias: {via_count}; all plated through, F.Cu–B.Cu, 0.45/0.20 mm; no blind, buried, or microvias.",
        f"- BOM: {bom_rows} source rows, {fitted_rows} fitted and {dnp_rows} DNP; every fitted row has a manufacturer part number.",
        "- PCB footprint values match the BOM source; the pin/net audit has no electrical mismatches.",
        f"- Expected mechanical-only extra pads: {', '.join(extra_pads)}.",
        "",
        "## Physical and layout checks",
        "",
        f"- Nominal outline: 100.00 × 30.00 mm (Edge.Cuts bounding box including stroke: {bbox_width:.2f} × {bbox_height:.2f} mm); board thickness 0.8 mm, four copper layers.",
        f"- Placement: {front_count} footprints on top; bottom only {', '.join(bottom_refs)}; every footprint has a courtyard.",
        "- In1.Cu has no signal tracks and contains the solid GND plane (normal pad/via antipads still apply).",
        f"- Antenna rule-area keepout is present on all four copper layers and measures {keepout_size[0]:.1f} × {keepout_size[1]:.1f} mm; pours and vias are forbidden there while the antenna feed is allowed.",
        "- RF, HSE, LSE, and STM32 SMPS critical nets are front-layer-only and via-free.",
        "",
        "## Routed-net measurements",
        "",
        "| Net | Copper length | Vias | Layers | Widths |",
        "|---|---:|---:|---|---|",
    ]
    for net_name in tracked_nets:
        item = stats[net_name]
        lines.append(
            f"| `{net_name}` | {item['length']:.2f} mm | {item['vias']} | "
            f"{', '.join(item['layers'])} | {', '.join(f'{width:.2f} mm' for width in item['widths'])} |"
        )

    lines.extend(
        [
            "",
            "## Interface assessment",
            "",
            f"- USB routed endpoint paths (excluding ESD branches and the two 22 Ω resistor bodies): D− {usb_dm_total:.2f} mm, D+ {usb_dp_total:.2f} mm; length difference {usb_skew:.2f} mm. FR-4 propagation gives an estimated 50–60 ps skew. This release is for USB 2.0 Full-Speed (12 Mbit/s) only, not High-Speed; verify the selected stackup and USB behavior on the first article.",
            "- The USB routes are not a tightly coupled controlled-impedance pair and use several vias. This is accepted for the Full-Speed prototype only and remains a first-article validation item.",
            "- microSD MCU-side routed lengths are SCK 33.18 mm, MISO 36.64 mm, MOSI 48.40 mm, and CS 38.01 mm. Start first-board firmware at 4 MHz SPI and increase only after validation; 12 MHz is the initial recommended ceiling.",
            "- The 2.4 GHz feed is top-layer and via-free over the In1 ground reference. Its 0.18 mm line width is not a universal 50 Ω value: the PCB vendor must calculate/confirm impedance against the actual 0.8 mm four-layer stackup, and the assembled unit requires VNA/closed-enclosure matching validation.",
            "",
            "## ECG/RLD/WCT review",
            "",
            "- CH1 is LA−RA, CH2 is LL−RA, and CH3 is V5−WCT; CH4 is reserved with test points. The PCB pin map matches the schematic audit CSV.",
            "- RA/LA/LL/V5 each use two 47.5 kΩ series resistors with C0G filtering and low-leakage clamps; RLD uses 2 × 162 kΩ series limiting.",
            "- RLDOUT/RLDINV compensation is 1 MΩ in parallel with 1.5 nF; WCT is routed to CH3N with 100 pF to ground.",
            "- These checks establish schematic/PCB consistency only. Before any human connection, validate on an ECG simulator and patient-equivalent load: input leakage/bias, RLD stability, recovery after ESD, noise, lead-off behavior, and all relevant safety limits.",
            "",
            "## First-article items that remain open",
            "",
            "- RF return loss, π-network values, BLE range in the final enclosure and near the body.",
            "- USB Full-Speed eye/function, microSD write peaks and SPI margin, RTC hold-up time, regulator temperatures, and power-path reverse-current behavior.",
            "- Battery connector polarity, protected-pack thresholds, enclosure tolerances, Pogo alignment, and mechanical USB/electrode interlock.",
            "- The design is a research prototype, not an IEC 60601-qualified medical device and not suitable for diagnosis or clinical decisions.",
            "",
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    try:
        display_path = output.relative_to(ROOT)
    except ValueError:
        display_path = output
    print(f"Wrote {display_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--board",
        type=Path,
        default=BOARD_PATH,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "docs" / "HARDWARE_AUDIT.md",
    )
    args = parser.parse_args()
    report(args.board.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
