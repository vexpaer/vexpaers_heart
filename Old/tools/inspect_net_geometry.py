#!/usr/bin/env python3
"""Print concise pad, via, and track geometry for selected PCB nets."""

from __future__ import annotations

import argparse
from pathlib import Path

import pcbnew


def xy(point: pcbnew.VECTOR2I) -> tuple[float, float]:
    return pcbnew.ToMM(point.x), pcbnew.ToMM(point.y)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("board", type=Path)
    parser.add_argument("nets", nargs="+")
    args = parser.parse_args()

    board = pcbnew.LoadBoard(str(args.board))
    wanted = set(args.nets)
    for net_name in args.nets:
        net = board.FindNet(net_name)
        if net is None:
            raise SystemExit(f"Unknown net: {net_name}")
        print(f"\n[{net_name}] code={net.GetNetCode()}")
        for footprint in sorted(board.GetFootprints(), key=lambda fp: fp.GetReference()):
            for pad in footprint.Pads():
                if pad.GetNetname() != net_name:
                    continue
                layers = ",".join(
                    board.GetLayerName(layer)
                    for layer in range(pcbnew.PCB_LAYER_ID_COUNT)
                    if pad.IsOnLayer(layer)
                )
                print(
                    f"PAD {footprint.GetReference()}-{pad.GetNumber()} "
                    f"at={xy(pad.GetPosition())} layers={layers}"
                )
        for item in board.Tracks():
            if item.GetNetname() not in wanted or item.GetNetname() != net_name:
                continue
            if isinstance(item, pcbnew.PCB_VIA):
                print(
                    f"VIA at={xy(item.GetPosition())} "
                    f"size={pcbnew.ToMM(item.GetWidth())}/{pcbnew.ToMM(item.GetDrillValue())}"
                )
            else:
                print(
                    f"TRACK layer={board.GetLayerName(item.GetLayer())} "
                    f"start={xy(item.GetStart())} end={xy(item.GetEnd())} "
                    f"width={pcbnew.ToMM(item.GetWidth())}"
                )


if __name__ == "__main__":
    main()
