#!/usr/bin/env python3
"""Human-style functional placement for heart_v2.

The coordinates below are deliberate functional-block placement, not an
autoplacer.  Re-running the script is safe: footprints are moved to their
specified positions and existing copper is cleared before routing begins.
"""

from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parents[1]
BOARD_PATH = ROOT / "heart_v2.kicad_pcb"


def mm(value: float) -> int:
    return pcbnew.FromMM(value)


def pos(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(x), mm(y))


def add_edge_segment(
    board: pcbnew.BOARD,
    start: tuple[float, float],
    end: tuple[float, float],
) -> None:
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
    shape.SetLayer(pcbnew.Edge_Cuts)
    shape.SetWidth(mm(0.10))
    shape.SetStart(pos(*start))
    shape.SetEnd(pos(*end))
    board.Add(shape)


def add_edge_arc(
    board: pcbnew.BOARD,
    start: tuple[float, float],
    mid: tuple[float, float],
    end: tuple[float, float],
) -> None:
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_ARC)
    shape.SetLayer(pcbnew.Edge_Cuts)
    shape.SetWidth(mm(0.10))
    shape.SetArcGeometry(pos(*start), pos(*mid), pos(*end))
    board.Add(shape)


def normalize_outline(board: pcbnew.BOARD) -> None:
    """Keep the expanded 100 x 32 mm rounded outline reproducible."""
    for drawing in list(board.GetDrawings()):
        if drawing.GetLayer() == pcbnew.Edge_Cuts:
            board.Delete(drawing)

    left, right, top, bottom, radius = 20.0, 120.0, 18.0, 50.0, 2.0
    # Use the physical lower-left board corner as the fabrication and pick/place
    # datum.  KiCad's placement export flips Y, so this gives assembly houses a
    # simple 0..100 mm by 0..32 mm, all-positive coordinate system.
    settings = board.GetDesignSettings()
    settings.SetAuxOrigin(pos(left, bottom))
    settings.SetGridOrigin(pos(left, bottom))
    root_two = 2**0.5
    add_edge_segment(board, (left + radius, top), (right - radius, top))
    add_edge_arc(
        board,
        (right - radius, top),
        (right - radius + radius / root_two, top + radius - radius / root_two),
        (right, top + radius),
    )
    add_edge_segment(board, (right, top + radius), (right, bottom - radius))
    add_edge_arc(
        board,
        (right, bottom - radius),
        (right - radius + radius / root_two, bottom - radius + radius / root_two),
        (right - radius, bottom),
    )
    add_edge_segment(board, (right - radius, bottom), (left + radius, bottom))
    add_edge_arc(
        board,
        (left + radius, bottom),
        (left + radius - radius / root_two, bottom - radius + radius / root_two),
        (left, bottom - radius),
    )
    add_edge_segment(board, (left, bottom - radius), (left, top + radius))
    add_edge_arc(
        board,
        (left, top + radius),
        (left + radius - radius / root_two, top + radius - radius / root_two),
        (left + radius, top),
    )


PLACEMENT: dict[str, tuple[float, float, float]] = {
    # ECG connector and connector-side low-capacitance ESD.
    "J1": (23.4, 35.0, 270),
    "D1": (27.2, 31.00, 90),
    "D2": (27.2, 32.75, 90),
    "D3": (27.2, 34.50, 90),
    "D5": (27.2, 36.25, 90),
    "D4": (27.2, 38.00, 90),
    "C10": (29.5, 41.0, 0),
    "C11": (26.2, 41.0, 0),
    "R12": (23.0, 41.0, 180),

    # Patient current limiting and four symmetric protection chains.
    "R1": (30.0, 30.8, 0),
    "R4": (30.0, 33.0, 0),
    "R6": (30.0, 35.2, 0),
    "R8": (30.0, 37.4, 0),
    "C1": (32.3, 30.32, 90),
    "C4": (32.3, 32.52, 90),
    "C6": (32.3, 34.72, 90),
    "C8": (32.3, 36.92, 90),
    "D6": (34.0, 32.50, 90),
    "D7": (34.0, 29.10, 90),
    "D8": (36.2, 34.70, 90),
    "D9": (36.2, 31.30, 90),
    "D10": (38.4, 36.90, 90),
    "D11": (38.4, 33.50, 90),
    "D12": (40.6, 39.10, 90),
    "D13": (40.6, 35.70, 90),

    # ADC-side current limiting and shunt EMI capacitors.
    "R5": (43.2, 30.0, 0),
    "R2": (43.2, 31.6, 0),
    "R3": (43.2, 33.2, 0),
    "R7": (43.2, 34.8, 0),
    "R9": (43.2, 36.4, 0),
    "C5": (45.8, 29.0, 90),
    "C2": (45.8, 31.0, 90),
    "C3": (45.8, 33.0, 90),
    "C7": (45.8, 35.0, 90),
    "C9": (45.8, 37.0, 90),
    "U1": (52.0, 35.0, 90),

    # RLD, WCT, channel-4 and optional respiration support.
    "R10": (48.0, 40.7, 180),
    "R11": (44.7, 40.7, 180),
    "R13": (51.0, 40.7, 90),
    "R14": (53.0, 41.2, 90),
    "C12": (54.2, 41.2, 90),
    "C13": (47.0, 28.5, 90),
    # Move the channel-4 bias pair one component pitch to the right.  This
    # opens a compact, direct supply-decoupling bay beside the ADS BGA.
    "R16": (61.0, 35.0, 0),
    "R17": (61.0, 37.4, 0),
    "TP1": (60.0, 32.5, 0),
    "TP2": (50.5, 45.5, 0),
    "C26": (34.0, 46.0, 0),
    "R18": (36.2, 46.0, 0),
    "C27": (39.0, 46.0, 0),
    "R19": (41.2, 46.0, 0),
    # ADS GPIO configuration straps form one ordered column at the digital
    # side of the BGA.  Signal pads face the converter; GND pads face out.
    "R52": (64.5, 29.0, 0),
    "R53": (64.5, 30.4, 0),
    # GPIO4 approaches on the inner vertical lane while GPIO3 approaches on
    # the outer lane, so their last two positions are intentionally swapped.
    "R55": (64.5, 31.8, 0),
    "R54": (64.5, 33.2, 0),
    "TP5": (57.6, 31.2, 0),

    # ADS1294R reference and supply bypassing, kept outside the BGA courtyard.
    "C14": (48.5, 24.2, 0),
    "C15": (48.5, 26.1, 0),
    "C16": (52.0, 24.2, 0),
    "C17": (55.1, 24.2, 0),
    "C19": (58.2, 24.2, 0),
    "C20": (64.5, 27.0, 0),
    "C21": (67.0, 27.0, 0),
    # AVDD1 and DVDD decouplers are placed at the package-side power exits.
    # Their signal pads face the BGA and their ground pads face the surrounding
    # reference pour, avoiding long supply stubs across the clock breakout.
    "C24": (57.9, 35.0, 0),
    "C25": (57.9, 36.5, 0),
    "C18": (53.5, 43.0, 180),
    "C22": (56.0, 41.0, 270),
    "C23": (57.6, 41.0, 270),
    "R15": (59.2, 39.2, 180),

    # Battery entry and protected source path.
    "J2": (62.0, 46.5, 0),
    "D14": (59.0, 41.5, 90),
    "F1": (61.5, 42.0, 0),
    "Q1": (65.5, 42.0, 0),
    "R20": (65.8, 46.5, 90),
    "C28": (68.2, 46.3, 90),

    # USB/battery mux and the three regulated rails.
    "U4": (70.5, 42.0, 0),
    "R23": (68.0, 38.8, 0),
    "R24": (70.2, 38.8, 0),
    "R25": (72.7, 45.2, 90),
    "TP4": (75.0, 47.0, 0),
    "C29": (72.9, 38.8, 180),
    "C30": (64.6, 38.8, 0),
    # SYS_RAW output bypass sits beside the U4-to-U5 route instead of at the
    # crowded test-point edge.
    "C31": (72.0, 48.5, 0),
    "C32": (72.0, 35.0, 0),
    "U5": (77.5, 42.0, 0),
    "C33": (80.5, 42.0, 90),
    "U6": (64.3, 22.8, 0),
    "C34": (61.5, 26.5, 0),
    "C35": (68.2, 22.8, 0),
    "U7": (82.0, 25.0, 0),
    "C36": (77.0, 25.0, 0),
    "C37": (86.0, 24.5, 0),

    # RTC hold-up and battery sensing.
    "C39": (76.0, 22.0, 0),
    "C40": (79.7, 22.0, 0),
    "C41": (83.4, 22.0, 0),
    "D15": (87.0, 21.8, 0),
    "R26": (77.8, 45.5, 0),
    "R27": (80.0, 45.5, 0),
    "R28": (82.2, 45.5, 0),
    "C38": (84.4, 45.5, 0),

    # MCU, low-speed clock, IMU and analog-supply filtering.
    "U2": (94.0, 32.0, 0),
    # Lift the 32.768 kHz network above PC14/PC15.  Both crystal traces fan
    # upward together, leaving the complete PC14/BOOT0 lane unobstructed.
    "Y2": (85.5, 28.25, 90),
    "C44": (83.0, 28.0, 90),
    "C45": (83.0, 30.5, 90),
    # Reset pull-up and capacitor form a horizontal supply-node-ground row.
    # The shared node faces the open routing bay below the MCU.
    "R33": (83.7, 41.8, 0),
    "C48": (85.8, 41.8, 0),
    # BOOT0 pull-down is grouped with its test point.  This removes the old
    # branch across the LSE crystal and leaves one straight lane to the MCU.
    "R34": (77.5, 31.0, 270),
    "TP3": (77.5, 29.0, 0),
    "U3": (82.0, 34.5, 270),
    "R38": (84.8, 33.2, 270),
    "R39": (86.2, 34.5, 0),
    "FB1": (84.3, 37.8, 0),
    "C49": (87.0, 36.8, 90),
    "C50": (86.7, 39.4, 0),

    # MCU decoupling ring.
    # C51 moves into the open gap left of the service row.  Its north-side
    # plane drop frees the NRST/SWO landing bay without lengthening a QFN rail.
    "C51": (89.0, 25.8, 0),
    "C52": (92.5, 25.8, 0),
    "C53": (94.5, 25.8, 0),
    "C54": (89.5, 40.0, 0),
    "C55": (91.5, 40.0, 0),
    # Put the digital-rail bulk bypass in the new north service band; this
    # leaves a clean two-row USB resistor/3V3_USB bypass cluster below it.
    "C57": (100.5, 20.5, 0),
    "C58": (93.5, 40.0, 0),
    "C59": (95.5, 40.0, 0),
    "C60": (94.0, 42.5, 0),
    "C62": (97.0, 43.7, 0),

    # USB Pogo interface: contacts on B.Cu, protection and series resistors on top.
    "J3": (94.0, 20.3, 0),
    "F2": (90.0, 21.2, 90),
    "U10": (93.5, 20.7, 180),
    "R21": (98.8, 25.5, 270),
    "R22": (97.2, 25.5, 270),
    "R35": (79.5, 29.0, 90),
    "R36": (80.7, 29.0, 90),
    "C56": (100.5, 24.0, 0),

    # Hidden debug contacts form a second bottom-side service row immediately
    # below USB.  Rotating J5 reverses the pogo order so the signal pads line
    # up with the MCU top-edge fanout; SWO continues the row at its left.
    "J5": (94.5, 23.8, 180),
    "TP6": (89.5, 23.8, 0),
    "R29": (78.4, 36.5, 90),
    "R30": (79.6, 36.5, 90),
    # START is placed directly above its L3 lane; CS is flipped so its signal
    # pad lands on the existing B.Cu SPI bundle without crossing the pull-up.
    "R31": (72.5, 29.5, 90),
    "R32": (76.3, 36.5, 270),
    "D16": (105.5, 22.5, 0),
    "R37": (102.8, 22.5, 0),

    # HSE and the STM32WB internal-SMPS network.
    "Y1": (101.0, 35.0, 180),
    # Keep the HSE shunt beside the crystal, out of the MCU/SMPS escape fan.
    "C42": (103.1, 34.1, 90),
    "C43": (99.2, 38.0, 270),
    "L1": (102.0, 27.8, 180),
    "C46": (103.5, 26.0, 0),
    "L2": (102.0, 30.5, 0),
    "C47": (104.5, 31.0, 90),

    # microSD series damping, pull-ups, load switch and card connector.
    "R41": (105.0, 43.3, 0),
    "R42": (104.5, 41.7, 0),
    "R43": (104.5, 39.7, 0),
    "R44": (104.5, 37.5, 0),
    "R45": (103.8, 44.7, 90),
    "R46": (101.0, 43.3, 0),
    "R47": (101.0, 41.7, 0),
    "R48": (106.0, 49.0, 0),
    "R49": (108.0, 49.0, 0),
    "R50": (110.0, 49.0, 0),
    "R40": (98.0, 46.2, 90),
    "U8": (100.8, 46.5, 0),
    "C61": (96.0, 46.0, 90),
    "C63": (104.0, 47.6, 90),
    "C64": (102.0, 49.0, 0),
    "J4": (112.5, 41.0, 90),

    # RF: filter at the MCU, tuneable pi network, antenna at the far short edge.
    # One millimetre of separation from the QFN opens a clean VDD33 escape
    # while keeping the RF feed short and via-free.
    "U9": (97.3, 38.5, 180),
    "C65": (100.5, 39.0, 90),
    "R51": (102.5, 39.5, 0),
    "C66": (106.0, 32.5, 90),
    "AE1": (117.0, 31.0, 0),
}


def clear_copper(board: pcbnew.BOARD) -> None:
    for item in list(board.GetTracks()):
        board.Delete(item)
    for zone in list(board.Zones()):
        board.Delete(zone)


def add_text(
    board: pcbnew.BOARD,
    text: str,
    x: float,
    y: float,
    layer: int = pcbnew.F_SilkS,
    size: float = 0.8,
    angle: float = 0,
) -> None:
    item = pcbnew.PCB_TEXT(board)
    item.SetText(text)
    item.SetPosition(pos(x, y))
    item.SetLayer(layer)
    item.SetTextSize(pos(size, size))
    item.SetTextThickness(mm(0.12))
    item.SetTextAngle(pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
    if layer == pcbnew.B_SilkS:
        item.SetMirrored(True)
    board.Add(item)


def main() -> None:
    board = pcbnew.LoadBoard(str(BOARD_PATH))
    clear_copper(board)
    normalize_outline(board)

    default_class = board.GetAllNetClasses()["Default"]
    default_class.SetClearance(mm(0.15))
    default_class.SetTrackWidth(mm(0.18))
    default_class.SetViaDiameter(mm(0.50))
    default_class.SetViaDrill(mm(0.20))
    default_class.SetDiffPairWidth(mm(0.18))
    default_class.SetDiffPairGap(mm(0.18))

    board_refs = {fp.GetReference() for fp in board.GetFootprints()}
    missing = sorted(board_refs - PLACEMENT.keys())
    unknown = sorted(PLACEMENT.keys() - board_refs)
    if missing or unknown:
        raise RuntimeError(f"placement mismatch: missing={missing}, unknown={unknown}")

    bottom_only = {"TP6"}
    # These are bare board-contact structures, not parts for the SMT machine:
    # USB/SWD pogo pads and the standalone test pad remain on the PCB but must
    # not appear in the BOM/CPL matching step at JLCPCB.
    non_placement = {"J3", "J5", "TP1", "TP2", "TP3", "TP4", "TP5", "TP6"}
    for fp in list(board.GetFootprints()):
        x, y, angle = PLACEMENT[fp.GetReference()]
        if fp.GetReference() in bottom_only and fp.GetLayer() != pcbnew.B_Cu:
            fp.Flip(fp.GetPosition(), False)
        fp.SetPosition(pos(x, y))
        fp.SetOrientationDegrees(angle)
        # These contact/test structures are already marked `in_bom no` in the
        # schematic.  Keep the PCB-side BOM flag aligned with that source of
        # truth and exclude them from the CPL as well.
        fp.SetExcludedFromBOM(fp.GetReference() in non_placement)
        fp.SetExcludedFromPosFiles(fp.GetReference() in non_placement)
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)

    # Remove old board-level text while preserving footprint graphics and outline.
    for drawing in list(board.GetDrawings()):
        if isinstance(drawing, pcbnew.PCB_TEXT):
            board.Remove(drawing)

    add_text(board, "ECG / PATIENT", 26.0, 22.0)
    add_text(board, "HEART V2  REV A", 66.0, 19.3, size=0.8)
    add_text(board, "ADS1294R", 54.0, 29.5)
    add_text(board, "PWR", 66.0, 49.0, size=0.8)
    add_text(board, "MCU", 91.0, 42.5)
    add_text(board, "SD", 116.0, 49.0)
    add_text(board, "ANT", 116.5, 28.5)
    add_text(board, "DISCONNECT ELECTRODES BEFORE USB", 46.0, 48.8, size=0.8)

    # USB labels align one-for-one with the actual contacts.  The denser J5
    # row uses a left-to-right legend in the open underside area, avoiding the
    # former long string drawn across its SWD approaches.
    for label, x_pos in [
        ("V", 90.19),
        ("D-", 92.73),
        ("D+", 95.27),
        ("G", 97.81),
    ]:
        add_text(board, label, x_pos, 22.3, layer=pcbnew.B_SilkS, size=0.8)
    add_text(
        board,
        "J5 L-R: SWO RST CLK DIO G 3V",
        44.0,
        19.5,
        layer=pcbnew.B_SilkS,
        size=0.8,
    )

    pcbnew.SaveBoard(str(BOARD_PATH), board)


if __name__ == "__main__":
    main()
