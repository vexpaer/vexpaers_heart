#!/usr/bin/env python3
"""Create the clean four-layer heart_v2 board shell.

This script intentionally creates a new PCB.  It never reads an archived PCB,
so no legacy tracks, vias, zones, or placement can leak into the rebuild.
"""

from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parents[1]
BOARD_PATH = ROOT / "heart_v2.kicad_pcb"


def mm(value: float) -> int:
    return pcbnew.FromMM(value)


def point(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(x), mm(y))


def add_segment(board: pcbnew.BOARD, start: tuple[float, float], end: tuple[float, float]) -> None:
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
    shape.SetLayer(pcbnew.Edge_Cuts)
    shape.SetWidth(mm(0.10))
    shape.SetStart(point(*start))
    shape.SetEnd(point(*end))
    board.Add(shape)


def add_arc(
    board: pcbnew.BOARD,
    start: tuple[float, float],
    mid: tuple[float, float],
    end: tuple[float, float],
) -> None:
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_ARC)
    shape.SetLayer(pcbnew.Edge_Cuts)
    shape.SetWidth(mm(0.10))
    shape.SetArcGeometry(point(*start), point(*mid), point(*end))
    board.Add(shape)


def main() -> None:
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)

    settings = board.GetDesignSettings()
    settings.SetBoardThickness(mm(0.80))
    settings.m_MinClearance = mm(0.15)
    settings.m_TrackMinWidth = mm(0.15)
    settings.m_ViasMinSize = mm(0.45)
    settings.m_MinThroughDrill = mm(0.20)
    settings.m_ViasMinAnnularWidth = mm(0.125)
    settings.m_HoleToHoleMin = mm(0.25)
    settings.m_CopperEdgeClearance = mm(0.25)
    settings.m_SilkClearance = mm(0.15)

    default_class = board.GetAllNetClasses()["Default"]
    default_class.SetClearance(mm(0.15))
    default_class.SetTrackWidth(mm(0.18))
    default_class.SetViaDiameter(mm(0.50))
    default_class.SetViaDrill(mm(0.20))
    default_class.SetDiffPairWidth(mm(0.18))
    default_class.SetDiffPairGap(mm(0.18))

    # 100.0 mm x 32.0 mm envelope, 2.0 mm corner radius.  The extra 2 mm at
    # the north edge is a dedicated bottom-side USB/SWD service-contact band.
    left, right, top, bottom, radius = 20.0, 120.0, 18.0, 50.0, 2.0
    settings.SetAuxOrigin(point(left, bottom))
    settings.SetGridOrigin(point(left, bottom))
    add_segment(board, (left + radius, top), (right - radius, top))
    add_arc(
        board,
        (right - radius, top),
        (right - radius + radius / 2**0.5, top + radius - radius / 2**0.5),
        (right, top + radius),
    )
    add_segment(board, (right, top + radius), (right, bottom - radius))
    add_arc(
        board,
        (right, bottom - radius),
        (right - radius + radius / 2**0.5, bottom - radius + radius / 2**0.5),
        (right - radius, bottom),
    )
    add_segment(board, (right - radius, bottom), (left + radius, bottom))
    add_arc(
        board,
        (left + radius, bottom),
        (left + radius - radius / 2**0.5, bottom - radius + radius / 2**0.5),
        (left, bottom - radius),
    )
    add_segment(board, (left, bottom - radius), (left, top + radius))
    add_arc(
        board,
        (left, top + radius),
        (left + radius - radius / 2**0.5, top + radius - radius / 2**0.5),
        (left + radius, top),
    )

    board.GetTitleBlock().SetTitle("Heart V2 - ECG + IMU Recorder")
    board.GetTitleBlock().SetRevision("2.0")
    board.GetTitleBlock().SetCompany("Research prototype - not a medical device")
    board.GetTitleBlock().SetComment(0, "DISCONNECT ELECTRODES BEFORE USB")

    pcbnew.SaveBoard(str(BOARD_PATH), board)


if __name__ == "__main__":
    main()
