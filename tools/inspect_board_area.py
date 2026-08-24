#!/usr/bin/env python3
"""List copper objects near one board coordinate for route planning."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import pcbnew


def xy(point: pcbnew.VECTOR2I) -> tuple[float, float]:
    return pcbnew.ToMM(point.x), pcbnew.ToMM(point.y)


def segment_distance(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    if dx == 0 and dy == 0:
        return math.dist(point, start)
    ratio = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy)))
    closest = (start[0] + ratio * dx, start[1] + ratio * dy)
    return math.dist(point, closest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("board", type=Path)
    parser.add_argument("x", type=float)
    parser.add_argument("y", type=float)
    parser.add_argument("--radius", type=float, default=2.0)
    args = parser.parse_args()

    board = pcbnew.LoadBoard(str(args.board))
    center = (args.x, args.y)
    print(f"center={center} radius={args.radius}")
    for footprint in sorted(board.GetFootprints(), key=lambda fp: fp.GetReference()):
        for pad in footprint.Pads():
            position = xy(pad.GetPosition())
            if math.dist(center, position) > args.radius:
                continue
            size = pad.GetSize()
            print(
                f"PAD {footprint.GetReference()}-{pad.GetNumber()} net={pad.GetNetname()} "
                f"at={position} size=({pcbnew.ToMM(size.x):.3f},{pcbnew.ToMM(size.y):.3f})"
            )
    for item in board.Tracks():
        if isinstance(item, pcbnew.PCB_VIA):
            position = xy(item.GetPosition())
            if math.dist(center, position) <= args.radius:
                print(f"VIA net={item.GetNetname()} at={position} size={pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu)):.3f}")
            continue
        start, end = xy(item.GetStart()), xy(item.GetEnd())
        if segment_distance(center, start, end) <= args.radius:
            print(
                f"TRACK {board.GetLayerName(item.GetLayer())} net={item.GetNetname()} "
                f"{start}->{end} width={pcbnew.ToMM(item.GetWidth()):.3f}"
            )


if __name__ == "__main__":
    main()
