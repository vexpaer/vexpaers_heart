#!/usr/bin/env python3
"""Add the manually reviewed final routes to an autorouted Holter board.

The autorouter result is kept as an input artifact.  This script makes the
small, deterministic set of final connections repeatable and locks them so a
subsequent cleanup pass cannot disturb the reviewed geometry.
"""

from __future__ import annotations

import argparse
import heapq
import math
from pathlib import Path

import pcbnew


def mm(value: float) -> int:
    return pcbnew.FromMM(value)


def vec(point: tuple[float, float]) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(point[0]), mm(point[1]))


def add_path(
    board: pcbnew.BOARD,
    net: pcbnew.NETINFO_ITEM,
    points: list[tuple[float, float]],
    *,
    layer: int,
    width: float = 0.15,
) -> None:
    for start, end in zip(points, points[1:]):
        if math.dist(start, end) < 1e-9:
            continue
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(vec(start))
        track.SetEnd(vec(end))
        track.SetLayer(layer)
        track.SetWidth(mm(width))
        track.SetNet(net)
        track.SetLocked(True)
        board.Add(track)


def add_via(
    board: pcbnew.BOARD,
    net: pcbnew.NETINFO_ITEM,
    point: tuple[float, float],
    *,
    diameter: float = 0.45,
    drill: float = 0.20,
) -> None:
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(vec(point))
    via.SetWidth(mm(diameter))
    via.SetDrill(mm(drill))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(net)
    via.SetLocked(True)
    board.Add(via)


def pad_xy(board: pcbnew.BOARD, reference: str, number: str) -> tuple[float, float]:
    pad = board.FindFootprintByReference(reference).FindPadByNumber(number)
    position = pad.GetPosition()
    return pcbnew.ToMM(position.x), pcbnew.ToMM(position.y)


def point_xy(point: pcbnew.VECTOR2I) -> tuple[float, float]:
    return pcbnew.ToMM(point.x), pcbnew.ToMM(point.y)


def remove_segment(
    board: pcbnew.BOARD,
    net_name: str,
    layer: int,
    start: tuple[float, float],
    end: tuple[float, float],
) -> None:
    def close(left: tuple[float, float], right: tuple[float, float]) -> bool:
        return abs(left[0] - right[0]) < 0.001 and abs(left[1] - right[1]) < 0.001

    for item in list(board.Tracks()):
        if isinstance(item, pcbnew.PCB_VIA):
            continue
        if item.GetNetname() != net_name or item.GetLayer() != layer:
            continue
        actual_start, actual_end = point_xy(item.GetStart()), point_xy(item.GetEnd())
        if (close(actual_start, start) and close(actual_end, end)) or (
            close(actual_start, end) and close(actual_end, start)
        ):
            board.Delete(item)
            return
    raise ValueError(f"Segment not found: {net_name} {start} -> {end}")


def remove_net_tracks_on_layer(board: pcbnew.BOARD, net_name: str, layer: int) -> None:
    targets = [
        item
        for item in board.Tracks()
        if not isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetname() == net_name
        and item.GetLayer() == layer
    ]
    for item in targets:
        board.Delete(item)


def remove_via(
    board: pcbnew.BOARD,
    net_name: str,
    position: tuple[float, float],
) -> None:
    for item in list(board.Tracks()):
        if not isinstance(item, pcbnew.PCB_VIA) or item.GetNetname() != net_name:
            continue
        actual = point_xy(item.GetPosition())
        if abs(actual[0] - position[0]) < 0.001 and abs(actual[1] - position[1]) < 0.001:
            board.Delete(item)
            return
    raise ValueError(f"Via not found: {net_name} at {position}")


def route_grid(
    board: pcbnew.BOARD,
    net: pcbnew.NETINFO_ITEM,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    layer: int,
    width: float = 0.15,
    step: float = 0.20,
    clearance: float = 0.10,
) -> list[tuple[float, float]]:
    """Find a clearance-aware 45-degree route on a compact board grid."""
    max_x, max_y = round(100.0 / step), round(30.0 / step)
    occupied: set[tuple[int, int]] = set()

    def grid(point: tuple[float, float]) -> tuple[int, int]:
        return round(point[0] / step), round(point[1] / step)

    def mark_disc(x: float, y: float, radius: float) -> None:
        gx, gy = grid((x, y))
        cells = math.ceil(radius / step) + 1
        limit = radius + step * 0.55
        for dx in range(-cells, cells + 1):
            for dy in range(-cells, cells + 1):
                if math.hypot(dx * step, dy * step) <= limit:
                    occupied.add((gx + dx, gy + dy))

    def mark_segment(
        first: tuple[float, float], second: tuple[float, float], radius: float
    ) -> None:
        length = math.dist(first, second)
        samples = max(1, math.ceil(length / (step * 0.45)))
        for index in range(samples + 1):
            ratio = index / samples
            mark_disc(
                first[0] + (second[0] - first[0]) * ratio,
                first[1] + (second[1] - first[1]) * ratio,
                radius,
            )

    route_radius = width / 2 + clearance
    for item in board.Tracks():
        if item.GetNetCode() == net.GetNetCode():
            continue
        if isinstance(item, pcbnew.PCB_VIA):
            position = point_xy(item.GetPosition())
            mark_disc(
                *position,
                pcbnew.ToMM(item.GetWidth(layer)) / 2 + route_radius,
            )
        elif item.GetLayer() == layer:
            mark_segment(
                point_xy(item.GetStart()),
                point_xy(item.GetEnd()),
                pcbnew.ToMM(item.GetWidth()) / 2 + route_radius,
            )

    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetCode() == net.GetNetCode() or not pad.IsOnLayer(layer):
                continue
            box = pad.GetBoundingBox()
            left = pcbnew.ToMM(box.GetLeft()) - route_radius
            right = pcbnew.ToMM(box.GetRight()) + route_radius
            top = pcbnew.ToMM(box.GetTop()) - route_radius
            bottom = pcbnew.ToMM(box.GetBottom()) + route_radius
            for gx in range(math.floor(left / step), math.ceil(right / step) + 1):
                for gy in range(math.floor(top / step), math.ceil(bottom / step) + 1):
                    occupied.add((gx, gy))

    edge_cells = math.ceil((0.25 + width / 2) / step)
    for gx in range(max_x + 1):
        for gy in range(max_y + 1):
            if gx < edge_cells or gx > max_x - edge_cells or gy < edge_cells or gy > max_y - edge_cells:
                occupied.add((gx, gy))
            if gx * step >= 94.7 and gy * step <= 10.2:
                occupied.add((gx, gy))

    source, target = grid(start), grid(end)
    occupied.discard(source)
    occupied.discard(target)
    directions = (
        (1, 0), (-1, 0), (0, 1), (0, -1),
        (1, 1), (1, -1), (-1, 1), (-1, -1),
    )
    queue: list[tuple[float, float, tuple[int, int, int]]] = []
    best: dict[tuple[int, int, int], float] = {}
    parent: dict[tuple[int, int, int], tuple[int, int, int] | None] = {}
    for direction_index in range(len(directions)):
        state = (source[0], source[1], direction_index)
        best[state] = 0.0
        parent[state] = None
        heapq.heappush(queue, (math.dist(source, target), 0.0, state))

    final: tuple[int, int, int] | None = None
    while queue:
        _, cost, state = heapq.heappop(queue)
        if cost != best.get(state):
            continue
        x, y, previous_direction = state
        if (x, y) == target:
            final = state
            break
        for direction_index, (dx, dy) in enumerate(directions):
            neighbor = (x + dx, y + dy)
            if not (0 <= neighbor[0] <= max_x and 0 <= neighbor[1] <= max_y):
                continue
            if neighbor in occupied and neighbor != target:
                continue
            if dx and dy and ((x + dx, y) in occupied or (x, y + dy) in occupied):
                continue
            move = math.sqrt(2) if dx and dy else 1.0
            turn = 0.18 if direction_index != previous_direction else 0.0
            new_cost = cost + move + turn
            next_state = (neighbor[0], neighbor[1], direction_index)
            if new_cost >= best.get(next_state, math.inf):
                continue
            best[next_state] = new_cost
            parent[next_state] = state
            estimate = new_cost + math.dist(neighbor, target)
            heapq.heappush(queue, (estimate, new_cost, next_state))

    if final is None:
        source_neighbors = {
            direction: (source[0] + direction[0], source[1] + direction[1]) in occupied
            for direction in directions
        }
        target_neighbors = {
            direction: (target[0] + direction[0], target[1] + direction[1]) in occupied
            for direction in directions
        }
        raise ValueError(
            f"No {board.GetLayerName(layer)} route for {net.GetNetname()}; "
            f"source={source} target={target} blocked={source_neighbors}; "
            f"target_blocked={target_neighbors}"
        )

    cells: list[tuple[int, int]] = []
    cursor: tuple[int, int, int] | None = final
    while cursor is not None:
        cells.append((cursor[0], cursor[1]))
        cursor = parent[cursor]
    cells.reverse()
    compact = [cells[0]]
    previous_delta: tuple[int, int] | None = None
    for first, second in zip(cells, cells[1:]):
        delta = (second[0] - first[0], second[1] - first[1])
        if previous_delta is not None and delta != previous_delta:
            compact.append(first)
        previous_delta = delta
    compact.append(cells[-1])
    points = [start]
    points.extend((x * step, y * step) for x, y in compact[1:-1])
    points.append(end)
    add_path(board, net, points, layer=layer, width=width)
    return points


def route_grid_multilayer(
    board: pcbnew.BOARD,
    net: pcbnew.NETINFO_ITEM,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    width: float = 0.10,
    step: float = 0.10,
    clearance: float = 0.10,
    via_diameter: float = 0.45,
    via_drill: float = 0.20,
    margin: float = 8.0,
    via_cost: float = 24.0,
    start_layer: int = pcbnew.F_Cu,
    end_layer: int = pcbnew.F_Cu,
) -> list[tuple[str, list[tuple[float, float]]]]:
    """Find a clearance-aware route across F.Cu, In2.Cu, and B.Cu.

    In1.Cu is intentionally absent: it is the board's uninterrupted ground
    reference plane.  Through-via sites are checked against copper on every
    routable layer and against all pads, preventing accidental via-in-pad.
    """
    layers = (pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
    layer_index = {layer: index for index, layer in enumerate(layers)}
    if start_layer not in layer_index or end_layer not in layer_index:
        raise ValueError("Multilayer routes may only use F.Cu, In2.Cu, or B.Cu")
    source_layer = layer_index[start_layer]
    target_layer = layer_index[end_layer]

    min_x = max(0.0, min(start[0], end[0]) - margin)
    max_x = min(100.0, max(start[0], end[0]) + margin)
    min_y = max(0.0, min(start[1], end[1]) - margin)
    max_y = min(30.0, max(start[1], end[1]) + margin)
    gx_min, gx_max = math.floor(min_x / step), math.ceil(max_x / step)
    gy_min, gy_max = math.floor(min_y / step), math.ceil(max_y / step)

    def grid(point: tuple[float, float]) -> tuple[int, int]:
        return round(point[0] / step), round(point[1] / step)

    def real(cell: tuple[int, int]) -> tuple[float, float]:
        return round(cell[0] * step, 6), round(cell[1] * step, 6)

    track_occupied = {layer: set() for layer in layers}
    via_occupied: set[tuple[int, int]] = set()

    def in_search_box(cell: tuple[int, int]) -> bool:
        return gx_min <= cell[0] <= gx_max and gy_min <= cell[1] <= gy_max

    def mark_disc(
        occupied: set[tuple[int, int]], x: float, y: float, radius: float
    ) -> None:
        center = grid((x, y))
        cells = math.ceil(radius / step) + 1
        limit = radius + step * 0.55
        for dx in range(-cells, cells + 1):
            for dy in range(-cells, cells + 1):
                cell = (center[0] + dx, center[1] + dy)
                if in_search_box(cell) and math.hypot(dx * step, dy * step) <= limit:
                    occupied.add(cell)

    def mark_rect(
        occupied: set[tuple[int, int]],
        left: float,
        right: float,
        top: float,
        bottom: float,
        inflate: float,
    ) -> None:
        first_x = max(gx_min, math.floor((left - inflate) / step))
        last_x = min(gx_max, math.ceil((right + inflate) / step))
        first_y = max(gy_min, math.floor((top - inflate) / step))
        last_y = min(gy_max, math.ceil((bottom + inflate) / step))
        for gx in range(first_x, last_x + 1):
            for gy in range(first_y, last_y + 1):
                occupied.add((gx, gy))

    def mark_segment(
        occupied: set[tuple[int, int]],
        first: tuple[float, float],
        second: tuple[float, float],
        radius: float,
    ) -> None:
        if (
            max(first[0], second[0]) + radius < min_x
            or min(first[0], second[0]) - radius > max_x
            or max(first[1], second[1]) + radius < min_y
            or min(first[1], second[1]) - radius > max_y
        ):
            return
        length = math.dist(first, second)
        samples = max(1, math.ceil(length / (step * 0.45)))
        for index in range(samples + 1):
            ratio = index / samples
            mark_disc(
                occupied,
                first[0] + (second[0] - first[0]) * ratio,
                first[1] + (second[1] - first[1]) * ratio,
                radius,
            )

    route_inflate = width / 2 + clearance
    via_radius = via_diameter / 2
    via_inflate = via_radius + clearance

    for item in board.Tracks():
        if item.GetNetCode() == net.GetNetCode():
            # Same-net copper may be reused, but existing drill sites still
            # block adjacent new vias.  Exact source/target via cells are
            # reopened below after their roles are known.
            if isinstance(item, pcbnew.PCB_VIA):
                position = point_xy(item.GetPosition())
                other_radius = pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu)) / 2
                mark_disc(via_occupied, *position, other_radius + via_inflate)
            continue
        if isinstance(item, pcbnew.PCB_VIA):
            position = point_xy(item.GetPosition())
            other_radius = pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu)) / 2
            for layer in layers:
                mark_disc(
                    track_occupied[layer],
                    *position,
                    other_radius + route_inflate,
                )
            mark_disc(via_occupied, *position, other_radius + via_inflate)
            continue
        layer = item.GetLayer()
        if layer not in layer_index:
            continue
        first, second = point_xy(item.GetStart()), point_xy(item.GetEnd())
        other_radius = pcbnew.ToMM(item.GetWidth()) / 2
        mark_segment(
            track_occupied[layer], first, second, other_radius + route_inflate
        )
        mark_segment(via_occupied, first, second, other_radius + via_inflate)

    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            pad_layers = [layer for layer in layers if pad.IsOnLayer(layer)]
            if not pad_layers:
                continue
            position = point_xy(pad.GetPosition())
            size = pad.GetSize()
            size_x, size_y = pcbnew.ToMM(size.x), pcbnew.ToMM(size.y)
            circular = pad.GetShape() == pcbnew.PAD_SHAPE_CIRCLE

            if pad.GetNetCode() != net.GetNetCode():
                for layer in pad_layers:
                    if circular:
                        mark_disc(
                            track_occupied[layer],
                            *position,
                            max(size_x, size_y) / 2 + route_inflate,
                        )
                    else:
                        box = pad.GetBoundingBox()
                        mark_rect(
                            track_occupied[layer],
                            pcbnew.ToMM(box.GetLeft()),
                            pcbnew.ToMM(box.GetRight()),
                            pcbnew.ToMM(box.GetTop()),
                            pcbnew.ToMM(box.GetBottom()),
                            route_inflate,
                        )

            # Even a same-net SMD pad is kept clear of new drill holes.  A
            # short surface dogbone must leave the pad before changing layers.
            if circular:
                mark_disc(
                    via_occupied,
                    *position,
                    max(size_x, size_y) / 2 + via_inflate,
                )
            else:
                box = pad.GetBoundingBox()
                mark_rect(
                    via_occupied,
                    pcbnew.ToMM(box.GetLeft()),
                    pcbnew.ToMM(box.GetRight()),
                    pcbnew.ToMM(box.GetTop()),
                    pcbnew.ToMM(box.GetBottom()),
                    via_inflate,
                )

    edge_track = math.ceil((0.20 + width / 2) / step)
    edge_via = math.ceil((0.20 + via_radius) / step)
    for gx in range(gx_min, gx_max + 1):
        for gy in range(gy_min, gy_max + 1):
            for layer in layers:
                if (
                    gx < edge_track
                    or gx > round(100.0 / step) - edge_track
                    or gy < edge_track
                    or gy > round(30.0 / step) - edge_track
                    or (gx * step >= 94.7 and gy * step <= 10.2)
                ):
                    track_occupied[layer].add((gx, gy))
            if (
                gx < edge_via
                or gx > round(100.0 / step) - edge_via
                or gy < edge_via
                or gy > round(30.0 / step) - edge_via
                or (gx * step >= 94.7 and gy * step <= 10.2)
            ):
                via_occupied.add((gx, gy))

    source, target = grid(start), grid(end)
    track_occupied[start_layer].discard(source)
    track_occupied[end_layer].discard(target)
    # A route may intentionally begin at a previously placed dogbone via.
    # Pad keepouts correctly prevent *new* via-in-pad transitions, but must
    # not trap the search on the declared same-net through-via.
    source_has_same_net_via = any(
        isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetCode() == net.GetNetCode()
        and math.dist(point_xy(item.GetPosition()), start) < step * 0.75
        for item in board.Tracks()
    )
    if source_has_same_net_via:
        via_occupied.discard(source)
        for layer in layers:
            track_occupied[layer].discard(source)
    target_has_same_net_via = any(
        isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetCode() == net.GetNetCode()
        and math.dist(point_xy(item.GetPosition()), end) < step * 0.75
        for item in board.Tracks()
    )
    if target_has_same_net_via:
        via_occupied.discard(target)
        for layer in layers:
            track_occupied[layer].discard(target)
    directions = (
        (1, 0),
        (-1, 0),
        (0, 1),
        (0, -1),
        (1, 1),
        (1, -1),
        (-1, 1),
        (-1, -1),
    )
    start_state = (source[0], source[1], source_layer, 8)
    queue: list[tuple[float, float, tuple[int, int, int, int]]] = []
    best = {start_state: 0.0}
    parent: dict[
        tuple[int, int, int, int], tuple[int, int, int, int] | None
    ] = {start_state: None}
    heapq.heappush(queue, (math.dist(source, target), 0.0, start_state))
    final: tuple[int, int, int, int] | None = None
    expanded = 0

    while queue:
        _, cost, state = heapq.heappop(queue)
        if cost != best.get(state):
            continue
        x, y, current_layer_index, previous_direction = state
        if (x, y) == target and current_layer_index == target_layer:
            final = state
            break
        expanded += 1
        if expanded > 2_500_000:
            break

        layer = layers[current_layer_index]
        for direction_index, (dx, dy) in enumerate(directions):
            neighbor = (x + dx, y + dy)
            if not in_search_box(neighbor):
                continue
            if neighbor in track_occupied[layer] and neighbor != target:
                continue
            move = math.sqrt(2) if dx and dy else 1.0
            turn = (
                0.0
                if previous_direction in (8, direction_index)
                else 0.18
            )
            layer_factor = (1.15, 1.00, 1.05)[current_layer_index]
            new_cost = cost + move * layer_factor + turn
            next_state = (
                neighbor[0],
                neighbor[1],
                current_layer_index,
                direction_index,
            )
            if new_cost >= best.get(next_state, math.inf):
                continue
            best[next_state] = new_cost
            parent[next_state] = state
            estimate = new_cost + math.dist(neighbor, target)
            heapq.heappush(queue, (estimate, new_cost, next_state))

        if (x, y) not in via_occupied:
            for next_layer_index in range(len(layers)):
                if next_layer_index == current_layer_index:
                    continue
                next_state = (x, y, next_layer_index, 8)
                new_cost = cost + via_cost
                if new_cost >= best.get(next_state, math.inf):
                    continue
                best[next_state] = new_cost
                parent[next_state] = state
                estimate = new_cost + math.dist((x, y), target)
                heapq.heappush(queue, (estimate, new_cost, next_state))

    if final is None:
        raise ValueError(
            f"No multilayer route for {net.GetNetname()} after {expanded} states; "
            f"source={source} target={target} bounds="
            f"({gx_min},{gy_min})-({gx_max},{gy_max})"
        )

    states: list[tuple[int, int, int, int]] = []
    cursor: tuple[int, int, int, int] | None = final
    while cursor is not None:
        states.append(cursor)
        cursor = parent[cursor]
    states.reverse()

    raw_groups: list[tuple[int, list[tuple[float, float]]]] = [
        (states[0][2], [start])
    ]
    via_points: set[tuple[float, float]] = set()
    for previous, current in zip(states, states[1:]):
        point = real((current[0], current[1]))
        if current[2] != previous[2]:
            raw_groups[-1][1].append(point)
            via_points.add(point)
            raw_groups.append((current[2], [point]))
        elif not raw_groups[-1][1] or raw_groups[-1][1][-1] != point:
            raw_groups[-1][1].append(point)
    raw_groups[-1][1][-1] = end

    def compact(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(points) <= 2:
            return points
        result = [points[0]]
        prior_direction: tuple[int, int] | None = None
        for first, second in zip(points, points[1:]):
            dx = 0 if abs(second[0] - first[0]) < 1e-6 else (1 if second[0] > first[0] else -1)
            dy = 0 if abs(second[1] - first[1]) < 1e-6 else (1 if second[1] > first[1] else -1)
            direction = (dx, dy)
            if prior_direction is not None and direction != prior_direction:
                result.append(first)
            prior_direction = direction
        result.append(points[-1])
        return result

    output: list[tuple[str, list[tuple[float, float]]]] = []
    for group_layer_index, group_points in raw_groups:
        points = compact(group_points)
        if len(points) < 2 or all(math.dist(points[0], point) < 1e-6 for point in points[1:]):
            continue
        layer = layers[group_layer_index]
        add_path(board, net, points, layer=layer, width=width)
        output.append((board.GetLayerName(layer), points))

    existing_vias = [
        point_xy(item.GetPosition())
        for item in board.Tracks()
        if isinstance(item, pcbnew.PCB_VIA) and item.GetNetCode() == net.GetNetCode()
    ]
    layer_by_name = {board.GetLayerName(layer): layer for layer in layers}
    for point in sorted(via_points):
        nearby = [candidate for candidate in existing_vias if math.dist(candidate, point) < step * 0.75]
        if nearby:
            # Grid rounding can put a transition a few hundredths of a
            # millimetre from an existing endpoint via.  Snap each adjoining
            # layer group to that drill instead of creating an overlapping
            # second hole.
            existing = min(nearby, key=lambda candidate: math.dist(candidate, point))
            for layer_name, points in output:
                if math.dist(points[0], point) < 1e-6 or math.dist(points[-1], point) < 1e-6:
                    add_path(
                        board,
                        net,
                        [point, existing],
                        layer=layer_by_name[layer_name],
                        width=width,
                    )
            continue
        add_via(
            board,
            net,
            point,
            diameter=via_diameter,
            drill=via_drill,
        )
    return output


def finish_sd_routes(board: pcbnew.BOARD) -> None:
    """Complete the reviewed STM32-to-microSD SPI fanout."""
    # PB12 is trapped behind the locked SMPS/VDD escape.  PA10 is otherwise
    # unused and can drive chip select as a normal GPIO while PB13/PB14/PB15
    # retain the hardware SPI2 clock/data functions.
    cs_net = board.FindNet("SD_CS_MCU")
    u2 = board.FindFootprintByReference("U2")
    u2.FindPadByNumber("46").SetNetCode(0)
    u2.FindPadByNumber("51").SetNet(cs_net)

    # Shift the unrelated ADS MOSI transition by 0.10 mm to open the PA10
    # surface channel without moving or crossing either USB data net.
    ads_mosi = board.FindNet("ADS_MOSI")
    remove_segment(
        board, "ADS_MOSI", pcbnew.B_Cu, (46.0000, 10.8000), (44.1000, 10.8000)
    )
    remove_via(board, "ADS_MOSI", (46.0000, 10.8000))
    add_path(
        board,
        ads_mosi,
        [(46.0000, 10.8000), (45.9000, 10.8500)],
        layer=pcbnew.In2_Cu,
        width=0.10,
    )
    add_via(board, ads_mosi, (45.9000, 10.8500))
    add_path(
        board,
        ads_mosi,
        [(45.9000, 10.8500), (44.1000, 10.8000)],
        layer=pcbnew.B_Cu,
        width=0.10,
    )

    # PA10 reaches the retained R41 route on F.Cu; the old PB12 anchor via
    # supplies the existing B.Cu transition, so no extra CS via is needed.
    cs_escape = (46.4500, 10.6500)
    add_path(
        board,
        cs_net,
        [
            pad_xy(board, "U2", "51"),
            cs_escape,
            (46.4500, 9.6000),
            (46.8000, 9.2500),
            (46.8000, 8.6000),
            (46.8250, 8.5834),
        ],
        layer=pcbnew.F_Cu,
        width=0.10,
    )

    # Repack MISO one row lower so adjacent PB13 gets its own standard
    # 0.45/0.20 mm SCK through-via.  Preserve the reviewed remote trunk.
    for start, end in (
        ((48.0000, 11.1125), (48.0000, 10.3725)),
        ((48.0000, 10.3725), (48.0925, 10.2800)),
    ):
        remove_segment(board, "SD_MISO_MCU", pcbnew.F_Cu, start, end)
    remove_segment(
        board,
        "SD_MISO_MCU",
        pcbnew.B_Cu,
        (48.6168, 10.8043),
        (48.0925, 10.2800),
    )
    remove_via(board, "SD_MISO_MCU", (48.0925, 10.2800))
    miso_net = board.FindNet("SD_MISO_MCU")
    miso_escape = (47.7500, 10.1000)
    add_path(
        board,
        miso_net,
        [
            pad_xy(board, "U2", "48"),
            (48.0000, 10.5500),
            (47.7500, 10.3000),
            miso_escape,
        ],
        layer=pcbnew.F_Cu,
        width=0.10,
    )
    add_via(board, miso_net, miso_escape)
    add_path(
        board,
        miso_net,
        [miso_escape, (47.7500, 10.8043), (48.6168, 10.8043)],
        layer=pcbnew.B_Cu,
        width=0.10,
    )

    # A 0.05 mm VDD dogleg clears the SCK via without changing the regulator
    # loop topology or moving the inductor/decoupling components.
    remove_segment(
        board, "3V0_D", pcbnew.F_Cu, (48.8000, 10.3500), (48.4000, 9.9500)
    )
    add_path(
        board,
        board.FindNet("3V0_D"),
        [(48.8000, 10.3500), (48.6500, 10.0800), (48.4000, 9.9500)],
        layer=pcbnew.F_Cu,
        width=0.10,
    )

    # This In2 GND spoke is redundant: its exposed-pad and remote-via
    # endpoints both already join the uninterrupted In1 GND plane.
    for start, end in (
        ((48.5250, 12.0500), (48.5250, 10.1444)),
        ((48.5250, 10.1444), (48.3873, 10.0067)),
        ((48.3873, 10.0067), (48.3873, 5.1127)),
    ):
        remove_segment(board, "GND", pcbnew.In2_Cu, start, end)

    sck_net = board.FindNet("SD_SCK_MCU")
    sck_escape = (48.3500, 10.4000)
    add_path(
        board,
        sck_net,
        [pad_xy(board, "U2", "47"), sck_escape],
        layer=pcbnew.F_Cu,
        width=0.10,
    )
    add_via(board, sck_net, sck_escape)
    route_grid_multilayer(
        board,
        sck_net,
        sck_escape,
        pad_xy(board, "R43", "1"),
        width=0.10,
        step=0.10,
        clearance=0.10,
        margin=8.0,
        via_cost=20.0,
        start_layer=pcbnew.B_Cu,
        end_layer=pcbnew.F_Cu,
    )


def finish_routes(board: pcbnew.BOARD) -> None:
    # SWDIO exits the MCU on F.Cu, changes layers outside the QFN courtyard,
    # and approaches the bottom-side pogo pad in a clear vertical channel.
    net = board.FindNet("SWDIO")
    escape = (45.5, 12.6)
    add_path(board, net, [pad_xy(board, "U2", "54"), escape], layer=pcbnew.F_Cu)
    add_via(board, net, escape)

    # The original low-speed LED return occupied the only standard-via fanout
    # site for SWDIO.  Move that whole connection to the otherwise sparse
    # bottom layer, then route SWDIO to its bottom-side pogo contact.
    led_net = board.FindNet("LED_STATUS_N")
    remove_net_tracks_on_layer(board, "LED_STATUS_N", pcbnew.In2_Cu)
    route_grid(
        board,
        led_net,
        (45.2839, 16.8487),
        (83.3030, 4.6972),
        layer=pcbnew.B_Cu,
    )
    route_grid(
        board,
        net,
        escape,
        pad_xy(board, "J5", "3"),
        layer=pcbnew.B_Cu,
    )

    # Open a standard through-via lane for BOOT0 between the neighbouring
    # low-speed crystal and I2C pins.  LSE_OUT stays entirely on F.Cu and is
    # merely folded 0.2 mm closer to its crystal; IMU_SCL moves to the next
    # staggered via site.
    for start, end in (
        ((48.0000, 18.8875), (48.0000, 19.5000)),
        ((48.0000, 19.5000), (48.5000, 20.0000)),
        ((48.5000, 20.0000), (48.5000, 20.5000)),
        ((48.5000, 20.5000), (45.2500, 20.5000)),
    ):
        remove_segment(board, "LSE_OUT", pcbnew.F_Cu, start, end)
    add_path(
        board,
        board.FindNet("LSE_OUT"),
        [
            pad_xy(board, "U2", "4"),
            (48.0000, 20.8000),
            (45.8000, 20.8000),
            (45.8000, 21.0500),
        ],
        layer=pcbnew.F_Cu,
        width=0.12,
    )

    for start, end in (
        ((48.8000, 18.8875), (48.8000, 19.6846)),
        ((48.8000, 19.6846), (48.7750, 19.7096)),
    ):
        remove_segment(board, "IMU_SCL", pcbnew.F_Cu, start, end)
    remove_via(board, "IMU_SCL", (48.7750, 19.7096))
    scl_mcu_escape = (48.8000, 19.7000)
    add_path(
        board,
        board.FindNet("IMU_SCL"),
        [pad_xy(board, "U2", "6"), scl_mcu_escape],
        layer=pcbnew.F_Cu,
        width=0.10,
    )
    add_via(board, board.FindNet("IMU_SCL"), scl_mcu_escape)

    boot0_net = board.FindNet("BOOT0")
    boot0_mcu_escape = (48.4000, 20.3000)
    add_path(
        board,
        boot0_net,
        [pad_xy(board, "U2", "5"), boot0_mcu_escape],
        layer=pcbnew.F_Cu,
        width=0.10,
    )
    add_via(board, boot0_net, boot0_mcu_escape)
    boot0_route_anchor = (44.3000, 21.5000)
    add_path(
        board,
        boot0_net,
        [
            boot0_mcu_escape,
            (48.2500, 20.4500),
            (44.0000, 20.4500),
            (44.0000, 21.5000),
            boot0_route_anchor,
        ],
        layer=pcbnew.B_Cu,
        width=0.10,
    )
    add_via(board, boot0_net, boot0_route_anchor)

    boot0_r34_escape = (41.2000, 8.4000)
    add_path(
        board,
        boot0_net,
        [pad_xy(board, "R34", "1"), (41.6000, 8.0000), boot0_r34_escape],
        layer=pcbnew.F_Cu,
        width=0.10,
    )
    add_via(board, boot0_net, boot0_r34_escape)

    boot0_tp3_escape = (68.2000, 4.6000)
    add_path(
        board,
        boot0_net,
        [pad_xy(board, "TP3", "1"), (68.5000, 3.5000), (68.2000, 3.8000), boot0_tp3_escape],
        layer=pcbnew.F_Cu,
        width=0.10,
    )
    add_via(board, boot0_net, boot0_tp3_escape)

    # Repack the two adjacent IMU interrupt fanouts.  INT1 originally changed
    # layers directly in front of the unrouted INT2 lead.  Moving that via onto
    # its own pin row creates two standard-via channels without touching the
    # neighbouring USB sense or digital-supply fanouts.
    for start, end in (
        ((53.8875, 15.4000), (54.4001, 15.4000)),
        ((54.4001, 15.4000), (54.7121, 15.0880)),
        ((54.7121, 15.0880), (54.7121, 15.0000)),
    ):
        remove_segment(board, "IMU_INT1", pcbnew.F_Cu, start, end)
    for start, end in (
        ((54.7121, 15.0000), (54.8540, 14.8581)),
        ((54.8540, 14.8581), (55.3897, 14.8581)),
        ((55.3897, 14.8581), (55.8153, 15.2837)),
        ((55.8153, 15.2837), (57.1853, 15.2837)),
    ):
        remove_segment(board, "IMU_INT1", pcbnew.B_Cu, start, end)
    remove_via(board, "IMU_INT1", (54.7121, 15.0000))

    int1_net = board.FindNet("IMU_INT1")
    int1_escape = (54.7000, 15.4000)
    add_path(
        board,
        int1_net,
        [pad_xy(board, "U2", "25"), int1_escape],
        layer=pcbnew.F_Cu,
        width=0.10,
    )
    add_via(board, int1_net, int1_escape)

    # Straighten the nearby BMI270 supply branch so its diagonal does not
    # block the INT2 dogbone at the package's right edge.
    remove_segment(
        board, "3V0_D", pcbnew.F_Cu, (64.9914, 9.2500), (65.5000, 8.7414)
    )
    remove_segment(
        board, "3V0_D", pcbnew.F_Cu, (65.5000, 8.7414), (65.5000, 7.4800)
    )
    add_path(
        board,
        board.FindNet("3V0_D"),
        [(64.9914, 9.2500), (65.5000, 9.2500), (65.5000, 7.4800)],
        layer=pcbnew.F_Cu,
    )

    # This redundant In2.Cu GND spoke is already tied through every exposed
    # pad to the uninterrupted In1.Cu plane.  Removing the spoke preserves the
    # ground connection while allowing a through-via to leave INT2.
    remove_segment(
        board, "GND", pcbnew.In2_Cu, (56.0000, 14.5000), (53.4500, 14.5000)
    )
    remove_segment(
        board, "GND", pcbnew.In2_Cu, (53.4500, 14.5000), (52.9500, 15.0000)
    )

    int2_net = board.FindNet("IMU_INT2")
    int2_mcu_escape = (54.7000, 14.8000)
    int2_imu_escape = (64.8000, 8.7500)
    add_path(
        board,
        int2_net,
        [
            pad_xy(board, "U2", "26"),
            (54.3000, 15.0000),
            (54.5000, 14.8000),
            int2_mcu_escape,
        ],
        layer=pcbnew.F_Cu,
        width=0.10,
    )
    add_via(board, int2_net, int2_mcu_escape)
    add_path(
        board,
        int2_net,
        [pad_xy(board, "U3", "9"), int2_imu_escape],
        layer=pcbnew.F_Cu,
        width=0.10,
    )
    add_via(board, int2_net, int2_imu_escape)
    route_grid(
        board,
        int2_net,
        int2_mcu_escape,
        int2_imu_escape,
        layer=pcbnew.B_Cu,
        width=0.10,
        step=0.10,
    )
    add_path(
        board,
        int1_net,
        [
            int1_escape,
            (55.0000, 15.7000),
            (56.8000, 15.7000),
            (57.1853, 15.2837),
        ],
        layer=pcbnew.B_Cu,
        width=0.10,
    )

    # Open a regular two-column via grid for the ADS SPI pins by moving C54
    # one millimetre outward.  Its supply remains tied to the ferrite branch,
    # and its ground lead returns to the original local ground spine.
    for start, end in (
        ((55.8000, 18.4125), (55.8000, 17.9800)),
        ((55.8000, 17.9800), (55.2957, 17.4757)),
        ((55.2957, 17.4757), (55.2957, 16.6573)),
        ((55.2957, 16.6573), (55.8000, 16.1530)),
        ((55.8000, 16.1530), (55.8000, 15.7800)),
    ):
        remove_segment(board, "3V0_D", pcbnew.F_Cu, start, end)
    remove_segment(
        board, "GND", pcbnew.F_Cu, (56.0422, 16.7778), (55.8000, 17.0200)
    )
    remove_segment(
        board, "GND", pcbnew.F_Cu, (59.2678, 16.7778), (56.0422, 16.7778)
    )
    remove_segment(
        board,
        "3V0_D",
        pcbnew.F_Cu,
        (53.7125, 20.5000),
        (55.8000, 18.4125),
    )
    c54 = board.FindFootprintByReference("C54")
    c54_position = point_xy(c54.GetPosition())
    c54.SetPosition(vec((c54_position[0] + 2.2000, c54_position[1])))
    add_path(
        board,
        board.FindNet("GND"),
        [pad_xy(board, "C54", "2"), (58.0000, 16.5000), (58.3000, 16.2250)],
        layer=pcbnew.F_Cu,
    )
    c54_supply_escape = (58.3000, 18.7000)
    add_path(
        board,
        board.FindNet("3V0_D"),
        [pad_xy(board, "C54", "1"), c54_supply_escape],
        layer=pcbnew.F_Cu,
    )
    add_via(board, board.FindNet("3V0_D"), c54_supply_escape)
    route_grid_multilayer(
        board,
        board.FindNet("3V0_D"),
        c54_supply_escape,
        (53.0705, 21.1583),
        width=0.15,
        step=0.10,
        margin=5.0,
        start_layer=pcbnew.B_Cu,
        end_layer=pcbnew.In2_Cu,
    )
    c57_supply_escape = (60.5000, 18.7000)
    add_path(
        board,
        board.FindNet("3V0_D"),
        [pad_xy(board, "C57", "1"), (60.5000, 18.3000), c57_supply_escape],
        layer=pcbnew.F_Cu,
    )
    add_via(board, board.FindNet("3V0_D"), c57_supply_escape)
    remove_segment(
        board, "GND", pcbnew.F_Cu, (59.5100, 17.0200), (59.2678, 16.7778)
    )
    add_via(board, board.FindNet("GND"), (59.5100, 18.5000))
    route_grid_multilayer(
        board,
        board.FindNet("3V0_D"),
        c57_supply_escape,
        c54_supply_escape,
        width=0.15,
        step=0.10,
        margin=3.0,
        start_layer=pcbnew.B_Cu,
        end_layer=pcbnew.B_Cu,
    )

    # Repack the four ADS SPI fanouts as a staggered standard-via grid.  MOSI
    # already occupies the first site; MISO and CS are moved from their long
    # detours, leaving the central site for the previously unrouted clock.
    for start, end in (
        ((53.8875, 17.0000), (54.5088, 17.0000)),
        ((54.5088, 17.0000), (54.8348, 17.3260)),
    ):
        remove_segment(board, "ADS_MISO", pcbnew.F_Cu, start, end)
    remove_segment(
        board,
        "ADS_MISO",
        pcbnew.B_Cu,
        (54.8348, 17.3260),
        (53.7841, 18.3767),
    )
    remove_segment(
        board,
        "ADS_MISO",
        pcbnew.B_Cu,
        (53.7841, 18.3767),
        (43.9168, 18.3767),
    )
    remove_via(board, "ADS_MISO", (54.8348, 17.3260))

    for start, end in (
        ((53.8875, 17.8000), (54.3814, 17.8000)),
        ((54.3814, 17.8000), (54.6091, 18.0277)),
        ((54.6091, 18.0277), (54.6091, 18.3855)),
        ((54.6091, 18.3855), (54.0351, 18.9595)),
        ((54.0351, 18.9595), (53.8121, 18.9595)),
    ):
        remove_segment(board, "ADS_CS", pcbnew.F_Cu, start, end)
    remove_segment(
        board,
        "ADS_CS",
        pcbnew.B_Cu,
        (53.8121, 18.9595),
        (47.2365, 18.9595),
    )
    remove_segment(
        board,
        "ADS_CS",
        pcbnew.B_Cu,
        (47.2365, 18.9595),
        (46.5080, 19.6880),
    )
    remove_segment(
        board,
        "ADS_CS",
        pcbnew.B_Cu,
        (46.5080, 19.6880),
        (41.4154, 19.6880),
    )
    remove_via(board, "ADS_CS", (53.8121, 18.9595))

    # The low-speed VBUS monitor originally crossed the new SPI via grid on
    # B.Cu.  Preserve its two endpoint vias and let it detour around the grid.
    for start, end in (
        ((55.1982, 16.1867), (55.1982, 16.4608)),
        ((55.1982, 16.4608), (56.9774, 18.2400)),
    ):
        remove_segment(board, "USB_VBUS_SENSE", pcbnew.B_Cu, start, end)

    miso_net = board.FindNet("ADS_MISO")
    sclk_net = board.FindNet("ADS_SCLK")
    cs_net = board.FindNet("ADS_CS")
    miso_escape = (55.3500, 17.0000)
    cs_escape = (55.3500, 18.4000)
    add_path(
        board,
        miso_net,
        [pad_xy(board, "U2", "21"), miso_escape],
        layer=pcbnew.F_Cu,
        width=0.10,
    )
    add_via(board, miso_net, miso_escape)
    add_path(
        board,
        cs_net,
        [
            pad_xy(board, "U2", "19"),
            (54.5000, 17.8000),
            (54.8000, 18.1000),
            cs_escape,
        ],
        layer=pcbnew.F_Cu,
        width=0.10,
    )
    add_via(board, cs_net, cs_escape)
    usb_sense_net = board.FindNet("USB_VBUS_SENSE")
    route_grid_multilayer(
        board,
        usb_sense_net,
        (55.1982, 16.1867),
        (56.9774, 18.2400),
        width=0.10,
        step=0.10,
        margin=5.0,
        start_layer=pcbnew.B_Cu,
        end_layer=pcbnew.B_Cu,
    )
    route_grid_multilayer(
        board,
        miso_net,
        miso_escape,
        (43.9168, 18.3767),
        width=0.10,
        step=0.10,
        start_layer=pcbnew.B_Cu,
        end_layer=pcbnew.B_Cu,
    )
    route_grid_multilayer(
        board,
        cs_net,
        cs_escape,
        (41.4154, 19.6880),
        width=0.10,
        step=0.10,
        start_layer=pcbnew.B_Cu,
        end_layer=pcbnew.In2_Cu,
    )
    # Move C55 one millimetre outward, then fan RESET and PWDN through the
    # resulting two-track channel between the locked SMPS and HSE routes.
    for start, end in (
        ((53.5000, 9.4800), (53.6026, 9.3774)),
        ((53.6026, 9.3774), (54.2888, 9.3774)),
    ):
        remove_segment(board, "3V0_D", pcbnew.F_Cu, start, end)
    remove_segment(
        board, "GND", pcbnew.F_Cu, (53.5000, 8.5200), (53.5000, 7.7250)
    )
    c55 = board.FindFootprintByReference("C55")
    c55_position = point_xy(c55.GetPosition())
    c55.SetPosition(vec((c55_position[0] + 1.0000, c55_position[1])))
    add_path(
        board,
        board.FindNet("3V0_D"),
        [pad_xy(board, "C55", "1"), (54.2888, 9.3774)],
        layer=pcbnew.F_Cu,
    )
    add_path(
        board,
        board.FindNet("GND"),
        [
            pad_xy(board, "C55", "2"),
            (54.7000, 8.3200),
            (54.7000, 7.7000),
            (53.5000, 7.7250),
        ],
        layer=pcbnew.F_Cu,
    )

    remove_segment(
        board, "SMPS_FB", pcbnew.F_Cu, (51.3000, 10.0000), (52.3000, 10.0000)
    )
    remove_segment(
        board, "SMPS_FB", pcbnew.F_Cu, (52.3000, 10.0000), (52.2875, 8.8000)
    )
    add_path(
        board,
        board.FindNet("SMPS_FB"),
        [
            (51.3000, 10.0000),
            (51.3000, 9.6000),
            (52.2875, 9.6000),
            (52.2875, 8.8000),
        ],
        layer=pcbnew.F_Cu,
        width=0.20,
    )

    for start, end in (
        ((51.6000, 11.1125), (51.6000, 10.6659)),
        ((51.6000, 10.6659), (51.8648, 10.4011)),
        ((51.8648, 10.4011), (52.5961, 10.4011)),
        ((52.5961, 10.4011), (52.8826, 10.1146)),
    ):
        remove_segment(board, "ADS_RESET", pcbnew.F_Cu, start, end)
    remove_segment(
        board,
        "ADS_RESET",
        pcbnew.B_Cu,
        (52.8826, 10.1146),
        (52.0555, 9.2875),
    )
    remove_via(board, "ADS_RESET", (52.8826, 10.1146))
    reset_net = board.FindNet("ADS_RESET")
    reset_escape = (53.1000, 9.2000)
    add_path(
        board,
        reset_net,
        [
            pad_xy(board, "U2", "39"),
            (51.6000, 10.5000),
            (52.5500, 9.9000),
            reset_escape,
        ],
        layer=pcbnew.F_Cu,
        width=0.10,
    )

    add_via(board, reset_net, reset_escape)
    add_path(
        board,
        reset_net,
        [reset_escape, (52.0555, 9.2875)],
        layer=pcbnew.B_Cu,
        width=0.10,
    )

    pwdn_net = board.FindNet("ADS_PWDN")
    pwdn_escape = (53.7000, 8.6000)
    add_path(
        board,
        pwdn_net,
        [
            pad_xy(board, "U2", "38"),
            (52.0000, 10.5000),
            (52.9200, 9.9000),
            (53.5500, 9.7000),
            pwdn_escape,
        ],
        layer=pcbnew.F_Cu,
        width=0.10,
    )
    add_via(board, pwdn_net, pwdn_escape)
    route_grid(
        board,
        pwdn_net,
        pwdn_escape,
        (43.4887, 9.0013),
        layer=pcbnew.B_Cu,
        width=0.10,
        step=0.10,
    )

    # The original SD chip-select escape crossed the only practical short
    # path from the regulator output to this MCU supply pin.  Remove only its
    # component-side fanout; the long fixed route from the old via to R41 is
    # retained as an anchor for the replacement fanout.
    for start, end in (
        ((48.8000, 11.1125), (48.8000, 10.4194)),
        ((48.8000, 10.4194), (47.9647, 9.5841)),
        ((47.9647, 9.5841), (47.4533, 9.5841)),
        ((47.4533, 9.5841), (46.8250, 8.9558)),
        ((46.8250, 8.9558), (46.8250, 8.5834)),
    ):
        remove_segment(board, "SD_CS_MCU", pcbnew.F_Cu, start, end)

    # Feed the MCU's local digital rail directly from the regulator output.
    # Keep this short branch entirely on the component side; its first escape
    # shares the narrow south-side QFN channel with the SD-card fanout, which
    # is repacked below.
    add_path(
        board,
        board.FindNet("3V0_D"),
        [
            pad_xy(board, "U2", "45"),
            (49.2000, 10.7500),
            (48.8000, 10.3500),
            (48.4000, 9.9500),
            (47.8000, 9.3500),
            (47.7125, 8.8000),
        ],
        layer=pcbnew.F_Cu,
        width=0.10,
    )

    # Free the two central ADS1298 control-pad dogbones.  The D7/C7 ground
    # pair previously crossed the E6 escape and then chained through F6.
    # Give that pair its own short route to a ground via on the package's
    # east side, preserving every ground pad while opening E6 and D6.
    for start, end in (
        ((28.9000, 13.0000), (28.5058, 13.3942)),
        ((28.5058, 13.3942), (27.7058, 13.3942)),
        ((27.7058, 13.3942), (27.3000, 13.8000)),
    ):
        remove_segment(board, "GND", pcbnew.F_Cu, start, end)
    remove_segment(
        board, "GND", pcbnew.F_Cu, (49.5735, 23.7250), (49.5735, 22.9198)
    )
    ads_ground_escape = (30.1000, 13.4000)
    add_path(
        board,
        board.FindNet("GND"),
        [pad_xy(board, "U1", "C7"), ads_ground_escape],
        layer=pcbnew.F_Cu,
        width=0.10,
    )
    add_via(
        board,
        board.FindNet("GND"),
        ads_ground_escape,
    )

    gpio3_net = board.FindNet("ADS_GPIO3_TIE")
    gpio3_escape = (27.7000, 13.4500)
    add_path(
        board,
        gpio3_net,
        [pad_xy(board, "U1", "E6"), gpio3_escape],
        layer=pcbnew.F_Cu,
        width=0.10,
    )
    add_via(
        board,
        gpio3_net,
        gpio3_escape,
    )

    drdy_net = board.FindNet("ADS_DRDY")
    drdy_ads_escape = (29.3000, 14.2000)
    add_path(
        board,
        drdy_net,
        [pad_xy(board, "U1", "D6"), drdy_ads_escape],
        layer=pcbnew.F_Cu,
        width=0.10,
    )
    add_via(
        board,
        drdy_net,
        drdy_ads_escape,
    )

    # The new dogbones cross the old bottom-layer MOSI shortcut.  Keep the
    # endpoint vias, but repack this short digital section on In2.Cu; In1.Cu
    # remains the uninterrupted ground plane.
    remove_segment(
        board,
        "ADS_MOSI",
        pcbnew.B_Cu,
        (25.2292, 12.7206),
        (26.1388, 13.6302),
    )
    remove_segment(
        board,
        "ADS_MOSI",
        pcbnew.B_Cu,
        (26.1388, 13.6302),
        (32.6197, 13.6302),
    )
    # The original F6-to-E4 ground chain is redundant: F6 already returns on
    # its west dogbone and E4 joins the D4/D5/C5 ground row.  Removing only
    # this middle chain opens the row-4/5 escape channel for GPIO4.
    for start, end in (
        ((27.6942, 14.1942), (27.3000, 13.8000)),
        ((27.6942, 14.9942), (27.6942, 14.1942)),
        ((28.1000, 15.4000), (27.6942, 14.9942)),
    ):
        remove_segment(board, "GND", pcbnew.F_Cu, start, end)

    # Move GPIO4 out through the newly opened surface channel, then rejoin
    # its existing bottom-layer route at the reviewed 32.3152 mm via.
    for start, end in (
        ((28.1000, 14.6000), (28.4942, 14.2058)),
        ((28.4942, 14.2058), (31.7143, 14.2058)),
        ((31.7143, 14.2058), (32.3152, 14.8067)),
    ):
        remove_segment(board, "ADS_GPIO4_TIE", pcbnew.F_Cu, start, end)
    remove_via(board, "ADS_GPIO4_TIE", (32.3152, 14.8067))
    gpio4_net = board.FindNet("ADS_GPIO4_TIE")
    gpio4_escape = (26.9000, 15.0500)
    add_path(
        board,
        gpio4_net,
        [pad_xy(board, "U1", "E5"), (27.7000, 15.0000), gpio4_escape],
        layer=pcbnew.F_Cu,
        width=0.10,
    )

    # Preserve the analogue RESP_MODP route while giving the new GPIO4 via
    # the required through-hole clearance on B.Cu.
    remove_segment(
        board,
        "ADS_RESP_MODP",
        pcbnew.B_Cu,
        (24.8948, 15.2960),
        (33.5497, 15.2960),
    )
    add_path(
        board,
        board.FindNet("ADS_RESP_MODP"),
        [
            (24.8948, 15.2960),
            (26.3500, 15.2960),
            (26.6000, 15.5460),
            (27.2000, 15.5460),
            (27.4500, 15.2960),
            (33.5497, 15.2960),
        ],
        layer=pcbnew.B_Cu,
        width=0.15,
    )
    add_via(board, gpio4_net, gpio4_escape)
    add_path(
        board,
        gpio4_net,
        [
            gpio4_escape,
            (27.0000, 14.9500),
            (31.9000, 14.9500),
            (32.1000, 14.8067),
            (32.3152, 14.8067),
        ],
        layer=pcbnew.B_Cu,
        width=0.10,
    )
    # GPIO1's old B.Cu chord occupied the new DRDY dogbone.  Repack that
    # chord around the new through-vias while keeping its endpoint vias.
    for start, end in (
        ((32.9807, 14.2257), (26.9257, 14.2257)),
        ((33.3643, 13.8421), (32.9807, 14.2257)),
        ((39.9133, 11.0202), (37.0914, 13.8421)),
        ((37.0914, 13.8421), (33.3643, 13.8421)),
    ):
        remove_segment(board, "ADS_GPIO1_TIE", pcbnew.B_Cu, start, end)

    # The ADS ground keepout isolates the central C7/D7 dogbone from the
    # In1.Cu plane.  Escape its via on B.Cu before placing the remaining
    # digital routes, then join an existing ground via farther east.
    ground_anchor = (33.0000, 14.0500)
    add_path(
        board,
        board.FindNet("GND"),
        [
            ads_ground_escape,
            (30.3000, 13.6000),
            (30.3000, 14.0500),
            ground_anchor,
        ],
        layer=pcbnew.B_Cu,
        width=0.15,
    )
    row_ground_escape = (31.7000, 14.2000)
    add_path(
        board,
        board.FindNet("GND"),
        [pad_xy(board, "U1", "A5"), row_ground_escape],
        layer=pcbnew.F_Cu,
        width=0.10,
    )
    add_via(board, board.FindNet("GND"), row_ground_escape)
    add_path(
        board,
        board.FindNet("GND"),
        [row_ground_escape, (31.7000, 14.0500)],
        layer=pcbnew.B_Cu,
        width=0.15,
    )
    route_grid_multilayer(
        board,
        board.FindNet("GND"),
        ground_anchor,
        (41.3000, 17.3200),
        width=0.15,
        step=0.10,
        margin=10.0,
        via_cost=24.0,
        start_layer=pcbnew.B_Cu,
        end_layer=pcbnew.B_Cu,
    )

    # Leave the densely packed ADS package on B.Cu before asking the
    # multilayer router to find a legal transition near the tie resistor.
    gpio3_anchor = (29.6500, 13.4500)
    add_path(
        board,
        gpio3_net,
        [
            gpio3_escape,
            gpio3_anchor,
        ],
        layer=pcbnew.B_Cu,
        width=0.10,
    )
    route_grid_multilayer(
        board,
        gpio3_net,
        gpio3_anchor,
        pad_xy(board, "R54", "1"),
        width=0.10,
        step=0.10,
        margin=8.0,
        via_cost=20.0,
        start_layer=pcbnew.B_Cu,
        end_layer=pcbnew.F_Cu,
    )
    route_grid_multilayer(
        board,
        board.FindNet("ADS_GPIO1_TIE"),
        (26.9257, 14.2257),
        (39.9133, 11.0202),
        width=0.10,
        step=0.10,
        margin=10.0,
        via_cost=20.0,
        start_layer=pcbnew.B_Cu,
        end_layer=pcbnew.B_Cu,
    )
    route_grid_multilayer(
        board,
        board.FindNet("ADS_MOSI"),
        (25.2292, 12.7206),
        (32.6197, 13.6302),
        width=0.10,
        step=0.10,
        margin=10.0,
        via_cost=20.0,
        start_layer=pcbnew.B_Cu,
        end_layer=pcbnew.B_Cu,
    )

    # Repack U2 pins 7-10 as an alternating two-row dogbone fanout.  At the
    # QFN's 0.40 mm pitch, this keeps every 0.45/0.20 mm through-via at the
    # standard hole/copper clearance without swapping the order of signals.
    # The original IMU clock/data chords crossed the new fanout area, so keep
    # their remote anchors and replace only the local exits.
    for start, end in (
        ((48.7750, 19.7096), (49.1499, 19.3347)),
        ((49.1499, 19.3347), (53.5437, 19.3347)),
        ((53.5437, 19.3347), (53.6146, 19.4056)),
        ((53.6146, 19.4056), (56.5294, 19.4056)),
        ((56.5294, 19.4056), (58.7555, 17.1795)),
    ):
        remove_segment(board, "IMU_SCL", pcbnew.B_Cu, start, end)
    remove_via(board, "IMU_SCL", (58.7555, 17.1795))
    # The original MCU-side MOSI trunk occupied the same In2.Cu corridor as
    # the final reset/SDA fanout and analogue-rail detour.  Keep its two
    # anchors and let the final multilayer pass rebuild this middle section.
    for start, end in (
        ((54.7133, 16.8578), (52.8327, 18.7384)),
        ((52.8327, 18.7384), (50.2494, 18.7384)),
        ((50.2494, 18.7384), (49.1937, 19.7941)),
        ((49.1937, 19.7941), (49.1937, 20.0675)),
        ((49.1937, 20.0675), (46.4748, 22.7864)),
        ((46.4748, 22.7864), (45.7422, 22.7864)),
        ((45.7422, 22.7864), (43.9250, 20.9692)),
    ):
        remove_segment(board, "ADS_MOSI", pcbnew.In2_Cu, start, end)
    for start, end in (
        ((49.2000, 18.8875), (49.2000, 19.5650)),
        ((49.2000, 19.5650), (49.5954, 19.9604)),
    ):
        remove_segment(board, "IMU_SDA", pcbnew.F_Cu, start, end)
    remove_segment(
        board,
        "IMU_SDA",
        pcbnew.In2_Cu,
        (49.5954, 19.9604),
        (50.4474, 19.1084),
    )
    remove_segment(
        board,
        "IMU_SDA",
        pcbnew.In2_Cu,
        (50.4474, 19.1084),
        (53.0953, 19.1084),
    )
    remove_via(board, "IMU_SDA", (49.5954, 19.9604))

    # Remove the old surface-only NRST branch up to the existing C48/J5
    # junction.  C48 is shifted 0.8 mm left below, opening a straight surface
    # channel from U2 while keeping the reset RC close to the MCU.
    for start, end in (
        ((49.6000, 18.8875), (49.6000, 19.3970)),
        ((49.6000, 19.3970), (49.9971, 19.7941)),
        ((49.9971, 19.7941), (49.9971, 20.0155)),
        ((49.9971, 20.0155), (50.3104, 20.3288)),
        ((50.3104, 20.3288), (50.3104, 21.7800)),
    ):
        remove_segment(board, "NRST", pcbnew.F_Cu, start, end)
    remove_segment(
        board, "NRST", pcbnew.F_Cu, (49.8000, 21.7800), (50.3104, 21.7800)
    )
    remove_segment(
        board, "NRST", pcbnew.F_Cu, (49.5200, 21.5000), (49.8000, 21.7800)
    )
    remove_segment(
        board, "GND", pcbnew.F_Cu, (48.4274, 20.8200), (49.8000, 20.8200)
    )
    remove_segment(
        board, "GND", pcbnew.F_Cu, (48.0534, 21.1940), (48.4274, 20.8200)
    )
    remove_segment(
        board, "GND", pcbnew.F_Cu, (48.0534, 21.8845), (48.0534, 21.1940)
    )
    for start, end in (
        ((48.5674, 22.3985), (48.0534, 21.8845)),
        ((49.0522, 22.3985), (48.5674, 22.3985)),
        ((49.5735, 22.9198), (49.0522, 22.3985)),
    ):
        remove_segment(board, "GND", pcbnew.F_Cu, start, end)

    # ADS_START used to snake through the pin-10 via site.  Preserve its
    # reviewed long bottom-layer route, but replace the MCU-side surface
    # branch with the second row of the staggered fanout.
    for start, end in (
        ((50.0000, 18.8875), (50.0000, 19.4409)),
        ((50.0000, 19.4409), (50.2488, 19.6897)),
        ((50.2488, 19.6897), (50.2488, 19.9111)),
        ((50.2488, 19.9111), (50.7574, 20.4197)),
        ((50.7574, 20.4197), (50.7574, 21.3400)),
    ):
        remove_segment(board, "ADS_START", pcbnew.F_Cu, start, end)
    remove_segment(
        board,
        "ADS_START",
        pcbnew.B_Cu,
        (50.2983, 20.8809),
        (50.7574, 21.3400),
    )
    remove_via(board, "ADS_START", (50.7574, 21.3400))

    # Two existing inner-layer trunks crossed the second dogbone row.  Detour
    # the analogue rail below it and move BAT_ADC slightly farther outward;
    # both retain their original endpoints and 0.15 mm widths.
    remove_segment(
        board,
        "3V0_A",
        pcbnew.In2_Cu,
        (46.5170, 23.1002),
        (49.1285, 20.4887),
    )
    remove_segment(
        board,
        "3V0_A",
        pcbnew.In2_Cu,
        (49.1285, 20.4887),
        (61.7854, 20.4887),
    )
    remove_segment(
        board,
        "BAT_ADC",
        pcbnew.In2_Cu,
        (41.3423, 28.6309),
        (49.0582, 20.9150),
    )
    remove_segment(
        board,
        "BAT_ADC",
        pcbnew.In2_Cu,
        (49.0582, 20.9150),
        (52.4304, 20.9150),
    )

    sda_net = board.FindNet("IMU_SDA")
    sda_mcu_escape = (49.2000, 20.3000)
    add_path(
        board,
        sda_net,
        [
            pad_xy(board, "U2", "7"),
            (49.2000, 19.8000),
            (49.2000, 19.8500),
            sda_mcu_escape,
        ],
        layer=pcbnew.F_Cu,
        width=0.10,
    )
    add_via(board, sda_net, sda_mcu_escape)

    nrst_net = board.FindNet("NRST")
    c48 = board.FindFootprintByReference("C48")
    c48_position = point_xy(c48.GetPosition())
    c48.SetPosition(vec((c48_position[0] + 0.2000, c48_position[1] - 0.0500)))
    c48.SetOrientationDegrees(0.0)
    add_path(
        board,
        nrst_net,
        [pad_xy(board, "U2", "8"), (49.6000, 21.5000), (49.5200, 21.5000)],
        layer=pcbnew.F_Cu,
        width=0.10,
    )
    add_path(
        board,
        nrst_net,
        [pad_xy(board, "C48", "1"), (49.5200, 21.5000)],
        layer=pcbnew.F_Cu,
        width=0.15,
    )
    add_path(
        board,
        nrst_net,
        [
            (49.5200, 21.5000),
            (49.8000, 21.7800),
            (50.3104, 21.7800),
        ],
        layer=pcbnew.F_Cu,
        width=0.15,
    )
    add_path(
        board,
        board.FindNet("GND"),
        [pad_xy(board, "C48", "2"), (50.7000, 21.2500), (51.0000, 21.2000)],
        layer=pcbnew.F_Cu,
        width=0.15,
    )
    add_via(board, board.FindNet("GND"), (51.0000, 21.2000))

    start_net = board.FindNet("ADS_START")
    start_mcu_escape = (50.0000, 20.2000)
    add_path(
        board,
        start_net,
        [pad_xy(board, "U2", "9"), start_mcu_escape],
        layer=pcbnew.F_Cu,
        width=0.10,
    )
    add_via(board, start_net, start_mcu_escape)

    drdy_mcu_escape = (50.4000, 19.7000)
    add_path(
        board,
        drdy_net,
        [pad_xy(board, "U2", "10"), drdy_mcu_escape],
        layer=pcbnew.F_Cu,
        width=0.10,
    )
    add_via(board, drdy_net, drdy_mcu_escape)

    add_path(
        board,
        board.FindNet("3V0_A"),
        [
            (46.5170, 23.1002),
            (48.1000, 21.5172),
            (48.1000, 20.7500),
            (50.8000, 20.7500),
            (51.1000, 20.4500),
            (61.7854, 20.4887),
        ],
        layer=pcbnew.In2_Cu,
        width=0.15,
    )
    add_path(
        board,
        board.FindNet("BAT_ADC"),
        [
            (41.3423, 28.6309),
            (48.0732, 21.9000),
            (51.8000, 21.9000),
            (52.4304, 21.2696),
            (52.4304, 20.9150),
        ],
        layer=pcbnew.In2_Cu,
        width=0.15,
    )

    add_path(
        board,
        sda_net,
        [sda_mcu_escape, (49.2000, 19.2000), (53.0953, 19.1084)],
        layer=pcbnew.In2_Cu,
        width=0.10,
    )
    add_path(
        board,
        start_net,
        [
            start_mcu_escape,
            (50.0000, 20.5000),
            (50.2983, 20.7983),
            (50.2983, 20.8809),
        ],
        layer=pcbnew.B_Cu,
        width=0.10,
    )

    drdy_anchor = (28.8000, 19.6000)
    add_path(
        board,
        drdy_net,
        [
            drdy_ads_escape,
            (29.1000, 14.7000),
            (28.7000, 15.1000),
            (28.3000, 15.5000),
            (27.9000, 15.9000),
            (27.5000, 16.3000),
            (27.4500, 16.7000),
            (27.4000, 17.1000),
            (27.3000, 17.5000),
            (27.5000, 17.8000),
            (28.1500, 17.7500),
            (29.0000, 17.7500),
            (29.0000, 19.6000),
            drdy_anchor,
        ],
        layer=pcbnew.In2_Cu,
        width=0.10,
    )
    add_via(board, drdy_net, drdy_anchor)
    route_grid_multilayer(
        board,
        drdy_net,
        drdy_anchor,
        drdy_mcu_escape,
        width=0.10,
        step=0.10,
        margin=30.0,
        via_cost=20.0,
        start_layer=pcbnew.B_Cu,
        end_layer=pcbnew.B_Cu,
    )
    route_grid_multilayer(
        board,
        board.FindNet("IMU_SCL"),
        scl_mcu_escape,
        (58.7555, 17.1795),
        width=0.10,
        step=0.10,
        margin=10.0,
        via_cost=20.0,
        start_layer=pcbnew.B_Cu,
        end_layer=pcbnew.In2_Cu,
    )

    route_grid_multilayer(
        board,
        board.FindNet("ADS_MOSI"),
        (54.7133, 16.8578),
        (43.9250, 20.9692),
        width=0.10,
        step=0.10,
        margin=12.0,
        via_cost=20.0,
        start_layer=pcbnew.In2_Cu,
        end_layer=pcbnew.In2_Cu,
    )

    # Route the ADS serial clock after every final fanout and power detour so
    # its multilayer search cannot reuse the newly occupied MCU channels.
    route_grid_multilayer(
        board,
        sclk_net,
        pad_xy(board, "U1", "F8"),
        pad_xy(board, "U2", "20"),
        width=0.10,
        step=0.10,
        margin=10.0,
        via_cost=20.0,
    )

    route_grid_multilayer(
        board,
        boot0_net,
        boot0_route_anchor,
        boot0_r34_escape,
        width=0.10,
        step=0.10,
        clearance=0.05,
        margin=12.0,
        via_cost=20.0,
        start_layer=pcbnew.B_Cu,
        end_layer=pcbnew.B_Cu,
    )
    route_grid_multilayer(
        board,
        boot0_net,
        boot0_r34_escape,
        boot0_tp3_escape,
        width=0.10,
        step=0.10,
        clearance=0.05,
        margin=8.0,
        via_cost=20.0,
        start_layer=pcbnew.B_Cu,
        end_layer=pcbnew.B_Cu,
    )

    finish_sd_routes(board)

    # Freerouting imports its layer-changing drills as "buried" vias even
    # when their declared pair is F.Cu-to-B.Cu.  Normalize every such drill to
    # an ordinary plated through-via so the fabrication data cannot be
    # misinterpreted as a blind/buried-via build.
    for item in board.Tracks():
        if not isinstance(item, pcbnew.PCB_VIA):
            continue
        item.SetViaType(pcbnew.VIATYPE_THROUGH)
        item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        item.SetWidth(mm(0.45))
        item.SetDrill(mm(0.20))

    # Keep the routed board's displayed values aligned with the regenerated
    # schematic/BOM.  These parts were refined from generic X7R callouts to
    # the exact 6.3 V X5R production substitutions after routing was frozen.
    production_values = {
        "C14": "10u 6.3V X5R",
        "C16": "22u 6.3V X5R",
        "C28": "10u 6.3V X5R",
        "C31": "22u 6.3V X5R",
        "C33": "10u 6.3V X5R",
        "C35": "10u 6.3V X5R",
        "C63": "22u 6.3V X5R",
    }
    footprints = {footprint.GetReference(): footprint for footprint in board.GetFootprints()}
    for reference, value in production_values.items():
        footprints[reference].SetValue(value)



def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    board = pcbnew.LoadBoard(str(args.input))
    finish_routes(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(args.output), board)
    print(f"Saved manually finished board to {args.output}")


if __name__ == "__main__":
    main()
