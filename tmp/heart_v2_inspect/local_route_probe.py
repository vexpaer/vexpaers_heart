#!/usr/bin/env python3
"""Coarse local channel probe; output is diagnostic, never copied verbatim."""

import heapq
import math
import sys

import pcbnew


board_path, net = sys.argv[1:3]
ignored_nets = set(net.split(","))
sx, sy, gx, gy, xmin, xmax, ymin, ymax = map(float, sys.argv[3:11])
board = pcbnew.LoadBoard(board_path)
layers = [pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu]
step = float(sys.argv[11]) if len(sys.argv) > 11 else 0.2
start_layer_name = sys.argv[12] if len(sys.argv) > 12 else None
goal_layer_name = sys.argv[13] if len(sys.argv) > 13 else None
start = (sx, sy)
goal = (gx, gy)


def point_segment(point, a, b):
    x, y = point
    u, v = a
    w, z = b
    dx, dy = w - u, z - v
    t = 0 if dx == dy == 0 else max(0, min(1, ((x - u) * dx + (y - v) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - u - t * dx, y - v - t * dy)


def orient(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segment_distance(a, b, c, d):
    values = [orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)]
    if (values[0] == 0 or values[1] == 0 or values[0] * values[1] < 0) and (
        values[2] == 0 or values[3] == 0 or values[2] * values[3] < 0
    ):
        return 0
    return min(
        point_segment(a, c, d),
        point_segment(b, c, d),
        point_segment(c, a, b),
        point_segment(d, a, b),
    )


tracks = {layer: [] for layer in layers}
all_tracks = []
vias = []
for item in board.GetTracks():
    if item.GetNetname() in ignored_nets:
        continue
    if isinstance(item, pcbnew.PCB_VIA):
        p = item.GetPosition()
        vias.append(
            (
                pcbnew.ToMM(p.x),
                pcbnew.ToMM(p.y),
                pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu)) / 2 + 0.24,
            )
        )
    else:
        a, b = item.GetStart(), item.GetEnd()
        obstacle = (
            (pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)),
            (pcbnew.ToMM(b.x), pcbnew.ToMM(b.y)),
            pcbnew.ToMM(item.GetWidth()) / 2 + 0.24,
        )
        all_tracks.append(obstacle)
        if item.GetLayer() in tracks:
            tracks[item.GetLayer()].append(obstacle)

pads = {layer: [] for layer in layers}
all_pads = []
for footprint in board.GetFootprints():
    for pad in footprint.Pads():
        if pad.GetNetname() in ignored_nets:
            continue
        p = pad.GetPosition()
        size = pad.GetSize()
        obstacle = (
            pcbnew.ToMM(p.x),
            pcbnew.ToMM(p.y),
            min(pcbnew.ToMM(size.x), pcbnew.ToMM(size.y)) / 2 + 0.24,
        )
        all_pads.append(obstacle)
        for layer in layers:
            if pad.IsOnLayer(layer):
                pads[layer].append(obstacle)


def clear_move(a, b, layer):
    return (
        all(segment_distance(a, b, c, d) >= radius - 1e-6 for c, d, radius in tracks[layer])
        and all(point_segment((x, y), a, b) >= radius - 1e-6 for x, y, radius in vias)
        and all(point_segment((x, y), a, b) >= radius - 1e-6 for x, y, radius in pads[layer])
    )


def clear_via(point):
    x, y = point
    return (
        all(point_segment(point, c, d) >= radius + 0.135 - 1e-6 for c, d, radius in all_tracks)
        and all(math.hypot(x - u, y - v) >= radius + 0.135 - 1e-6 for u, v, radius in vias)
        and all(math.hypot(x - u, y - v) >= radius + 0.135 - 1e-6 for u, v, radius in all_pads)
    )


def key(point):
    return (round((point[0] - xmin) / step), round((point[1] - ymin) / step))


def point(node):
    return (round(xmin + node[0] * step, 3), round(ymin + node[1] * step, 3))


start_key, goal_key = key(start), key(goal)
distance = {}
previous = {}
queue = []
start_indices = range(len(layers))
if start_layer_name:
    start_indices = [
        index
        for index, layer in enumerate(layers)
        if board.GetLayerName(layer) == start_layer_name
    ]
for layer_index in start_indices:
    node = (*start_key, layer_index)
    distance[node] = 0
    heapq.heappush(queue, (0, 0, node))

directions = [(i, j) for i in (-1, 0, 1) for j in (-1, 0, 1) if i or j]
end = None
while queue:
    _, cost, node = heapq.heappop(queue)
    if distance.get(node) != cost:
        continue
    i, j, layer_index = node
    here = point((i, j))
    if (i, j) == goal_key and (
        goal_layer_name is None or board.GetLayerName(layers[layer_index]) == goal_layer_name
    ):
        end = node
        break
    for di, dj in directions:
        next_key = (i + di, j + dj)
        there = point(next_key)
        if not (xmin <= there[0] <= xmax and ymin <= there[1] <= ymax):
            continue
        if not clear_move(here, there, layers[layer_index]):
            continue
        next_node = (*next_key, layer_index)
        next_cost = cost + math.hypot(di, dj)
        if next_cost < distance.get(next_node, 1e9):
            distance[next_node] = next_cost
            previous[next_node] = node
            heuristic = math.hypot(next_key[0] - goal_key[0], next_key[1] - goal_key[1])
            heapq.heappush(queue, (next_cost + heuristic, next_cost, next_node))
    if (i, j) != start_key and ((i, j) == goal_key or clear_via(here)):
        for next_layer_index in range(len(layers)):
            if next_layer_index == layer_index:
                continue
            next_node = (i, j, next_layer_index)
            next_cost = cost + 4
            if next_cost < distance.get(next_node, 1e9):
                distance[next_node] = next_cost
                previous[next_node] = node
                heuristic = math.hypot(i - goal_key[0], j - goal_key[1])
                heapq.heappush(queue, (next_cost + heuristic, next_cost, next_node))

if end is None:
    print("NO PATH")
    raise SystemExit

path = []
node = end
while True:
    path.append(node)
    if node not in previous:
        break
    node = previous[node]
path.reverse()

compressed = []
for node in path:
    entry = (layers[node[2]], point(node[:2]))
    if len(compressed) > 1 and compressed[-2][0] == compressed[-1][0] == entry[0]:
        a, b, c = compressed[-2][1], compressed[-1][1], entry[1]
        if abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) < 1e-9:
            compressed[-1] = entry
            continue
    compressed.append(entry)

for layer, coordinate in compressed:
    print(board.GetLayerName(layer), coordinate)
