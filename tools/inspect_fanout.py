#!/usr/bin/env python3
"""Report the closest routed via reached from each pad on one footprint."""

from __future__ import annotations

import argparse
import heapq
import math
from collections import defaultdict
from pathlib import Path

import pcbnew


def point_key(point: pcbnew.VECTOR2I) -> tuple[int, int]:
    return round(pcbnew.ToMM(point.x) * 1000), round(pcbnew.ToMM(point.y) * 1000)


def key_xy(key: tuple[int, int]) -> tuple[float, float]:
    return key[0] / 1000, key[1] / 1000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("board", type=Path)
    parser.add_argument("reference")
    parser.add_argument("pads", nargs="*")
    args = parser.parse_args()

    board = pcbnew.LoadBoard(str(args.board))
    footprint = board.FindFootprintByReference(args.reference)
    wanted = set(args.pads)
    for pad in sorted(footprint.Pads(), key=lambda item: str(item.GetNumber())):
        if not pad.GetNumber() or (wanted and pad.GetNumber() not in wanted):
            continue
        net_name = pad.GetNetname()
        if not net_name:
            continue
        graph: dict[tuple[int, int], list[tuple[tuple[int, int], float, str]]] = defaultdict(list)
        vias: set[tuple[int, int]] = set()
        for item in board.Tracks():
            if item.GetNetname() != net_name:
                continue
            if isinstance(item, pcbnew.PCB_VIA):
                vias.add(point_key(item.GetPosition()))
                continue
            start, end = point_key(item.GetStart()), point_key(item.GetEnd())
            length = math.dist(start, end)
            layer = board.GetLayerName(item.GetLayer())
            graph[start].append((end, length, layer))
            graph[end].append((start, length, layer))
        source = point_key(pad.GetPosition())
        queue = [(0.0, source)]
        distance = {source: 0.0}
        previous: dict[tuple[int, int], tuple[tuple[int, int], str] | None] = {source: None}
        target = None
        while queue:
            cost, node = heapq.heappop(queue)
            if cost != distance.get(node):
                continue
            if node in vias:
                target = node
                break
            for neighbor, weight, layer in graph[node]:
                new_cost = cost + weight
                if new_cost >= distance.get(neighbor, math.inf):
                    continue
                distance[neighbor] = new_cost
                previous[neighbor] = (node, layer)
                heapq.heappush(queue, (new_cost, neighbor))
        if target is None:
            print(f"{pad.GetNumber():>2} {net_name:<20} pad={key_xy(source)} via=NONE")
            continue
        path = []
        cursor = target
        while cursor != source:
            prior, layer = previous[cursor]
            path.append((key_xy(prior), key_xy(cursor), layer))
            cursor = prior
        path.reverse()
        print(
            f"{pad.GetNumber():>2} {net_name:<20} pad={key_xy(source)} "
            f"via={key_xy(target)} path={path}"
        )


if __name__ == "__main__":
    main()
