from __future__ import annotations

import math
from spatial_geometry import bounds, intersection_area, occupied_cells, rect_polygon
from collections import deque
from dataclasses import dataclass
from typing import Callable

from design_models import (
    Direction,
    Furniture,
    FurnitureType,
    PlacedFurniture,
    Room,
    build_items_from_placements,
    validate_layout,
)

DEFAULT_RULE_WEIGHTS = {
    "clearance_violation": 2.0,
    "circulation_penalty": 1.5,
    "pairwise_distance_penalty": 2.0,
    "conversation_penalty": 2.0,
    "visual_balance_penalty": 1.5,
    "alignment_penalty": 1.0,
}


@dataclass
class LayoutScore:
    total: float
    breakdown: dict[str, float]
    violations: list[str]


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def rect_of(item: Furniture) -> tuple[int, int, int, int]:
    return (item.gx, item.gy, item.gx + item.gw, item.gy + item.gd)


def rect_intersection_area_cells(
    a: tuple[int, int, int, int],
    b: tuple[int, int, int, int],
) -> int:
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[2], b[2])
    y1 = min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0
    return (x1 - x0) * (y1 - y0)


def _side_zone(item, direction, depth):
    w, d = item.local_size
    if direction == Direction.NORTH:
        rect = (-w/2, d/2, w/2, d/2+depth)
    elif direction == Direction.EAST:
        rect = (w/2, -d/2, w/2+depth, d/2)
    elif direction == Direction.SOUTH:
        rect = (-w/2, -d/2-depth, w/2, -d/2)
    else:
        rect = (-w/2-depth, -d/2, -w/2, d/2)
    return item.local_rect(rect)


def _local_direction(item, direction, base_direction):
    if base_direction is not None:
        return base_direction
    # Legacy Furniture constructors supply an already rotated cardinal direction.
    from design_models import rotate_direction
    return rotate_direction(direction, -item.rotation)


def build_fall_zone_polygon(item):
    if item.fall_dir is None:
        return None
    return _side_zone(item, _local_direction(item, item.fall_dir, item.base_fall_dir), item.h_cell)


def build_bed_head_zone_polygon(item):
    if item.pillow_side is None:
        raise ValueError(f"{item.name}: bed must have pillow_side")
    return _side_zone(item, _local_direction(item, item.pillow_side, item.base_pillow_side), 2)


def build_fall_zone_rect(item):
    polygon = build_fall_zone_polygon(item)
    return bounds(polygon) if polygon else None


def build_bed_head_zone_rect(item):
    return bounds(build_bed_head_zone_polygon(item))


def total_fall_hazard_overlap_cells(items: list[Furniture]) -> float:
    beds = [item for item in items if item.furniture_type == FurnitureType.BED]
    total = 0.0
    for item in items:
        if item.furniture_type == FurnitureType.BED:
            continue
        zone = build_fall_zone_polygon(item)
        if zone:
            total += sum(intersection_area(zone, bed.footprint) for bed in beds)
    return total


def _distance_penalty(distance: float, minimum: float, maximum: float) -> float:
    if minimum <= distance <= maximum:
        return 0.0
    if distance < minimum:
        return (minimum - distance) / max(1.0, minimum)
    return (distance - maximum) / max(1.0, maximum)


def _iter_cells(rect: tuple[int, int, int, int]) -> list[tuple[int, int]]:
    return [(x, y) for x in range(math.floor(rect[0]), math.ceil(rect[2])) for y in range(math.floor(rect[1]), math.ceil(rect[3]))]


def _build_occupancy(room: Room, items: list[Furniture]) -> list[list[bool]]:
    grid = [[False for _ in range(room.grid_h)] for _ in range(room.grid_w)]
    for item in items:
        if item.ceiling_mounted:
            continue
        for x, y in occupied_cells(item.footprint):
            if 0 <= x < room.grid_w and 0 <= y < room.grid_h:
                grid[x][y] = True
    return grid


def _distance_to_nearest_wall(room: Room, item: Furniture) -> int:
    return min(
        item.gx,
        item.gy,
        room.grid_w - (item.gx + item.gw),
        room.grid_h - (item.gy + item.gd),
    )


def _clearance_polygons(item):
    rule = item.clearance
    if rule is None:
        return []
    w, d = item.local_size
    margin = rule.min_cells
    if rule.mode == "all":
        return [item.local_rect((-w/2-margin, -d/2-margin, w/2+margin, d/2+margin))]
    if rule.mode == "front":
        return [_side_zone(item, Direction.NORTH, margin)]
    directions = (Direction.NORTH, Direction.SOUTH) if w >= d else (Direction.EAST, Direction.WEST)
    return [_side_zone(item, direction, margin) for direction in directions]


def score_clearance_violation(room: Room, items: list[Furniture]) -> tuple[float, list[str]]:
    score = 0.0
    violations = []
    for item in items:
        for zone in _clearance_polygons(item):
            area = sum(intersection_area(zone, other.footprint) for other in items
                       if other.key != item.key and other.ceiling_mounted == item.ceiling_mounted)
            if area > 1e-6:
                score += area
                violations.append(f"{item.name} clearance overlaps occupied area ({area:.2f} cell units squared)")
    return score, violations


def _exit_anchor_cells(room: Room) -> list[tuple[int, int]]:
    # Room normalizes legacy exits into doors; supports every wall and no exit.
    return room.door_anchor_cells()


def score_circulation_penalty(room: Room, items: list[Furniture]) -> tuple[float, list[str]]:
    occupied = _build_occupancy(room, items)
    free_cells = {
        (x, y)
        for x in range(room.grid_w)
        for y in range(room.grid_h)
        if not occupied[x][y]
    }
    if not free_cells:
        return 100.0, ["No free cells remain for circulation"]

    start_cells = [cell for cell in _exit_anchor_cells(room) if cell in free_cells]
    if not start_cells:
        start_cells = [next(iter(free_cells))]

    visited: set[tuple[int, int]] = set()
    queue = deque(start_cells)
    while queue:
        cell = queue.popleft()
        if cell in visited:
            continue
        visited.add(cell)
        x, y = cell
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbor = (x + dx, y + dy)
            if neighbor in free_cells and neighbor not in visited:
                queue.append(neighbor)

    unreachable = free_cells - visited
    components = 0
    remaining = set(free_cells)
    while remaining:
        components += 1
        seed = remaining.pop()
        local = deque([seed])
        chunk = {seed}
        while local:
            x, y = local.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                neighbor = (x + dx, y + dy)
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    chunk.add(neighbor)
                    local.append(neighbor)

    score = (len(unreachable) / max(1, len(free_cells))) * 20.0 + max(0, components - 1) * 5.0
    violations: list[str] = []
    if unreachable:
        violations.append(f"{len(unreachable)} free cells are unreachable from the exit")
    return score, violations


def score_pairwise_distance_penalty(room: Room, items: list[Furniture]) -> tuple[float, list[str]]:
    del room
    item_map = {item.key: item for item in items}
    seen: set[tuple[str, str]] = set()
    score = 0.0
    violations: list[str] = []
    for item in items:
        for rule in item.pairwise_rules:
            other = item_map.get(rule.other_key)
            if other is None:
                continue
            pair_key = tuple(sorted((item.key, other.key)))
            if pair_key in seen:
                continue
            seen.add(pair_key)
            distance = math.dist(item.center, other.center)
            penalty = _distance_penalty(distance, rule.min_distance_cells, rule.max_distance_cells)
            if penalty > 0:
                score += penalty
                violations.append(
                    f"{item.name} to {other.name} distance {distance:.2f} is outside "
                    f"[{rule.min_distance_cells}, {rule.max_distance_cells}]"
                )
    return score, violations


def score_conversation_penalty(room: Room, items: list[Furniture]) -> tuple[float, list[str]]:
    del room
    seats = [item for item in items if item.conversation_seat]
    if len(seats) < 2:
        return 0.0, []

    score = 0.0
    violations: list[str] = []
    for index, left in enumerate(seats):
        for right in seats[index + 1 :]:
            distance = math.dist(left.center, right.center)
            penalty = _distance_penalty(distance, 5.0, 10.0)
            if penalty > 0:
                score += penalty
                violations.append(
                    f"{left.name} to {right.name} distance {distance:.2f} is outside conversation range"
                )
    return score, violations


def score_visual_balance_penalty(room: Room, items: list[Furniture]) -> tuple[float, list[str]]:
    total_area = sum((item.local_size[0] * item.local_size[1]) for item in items)
    if total_area <= 0:
        return 0.0, []

    centroid_x = sum((item.gx + item.gw / 2.0) * (item.local_size[0] * item.local_size[1]) for item in items) / total_area
    centroid_y = sum((item.gy + item.gd / 2.0) * (item.local_size[0] * item.local_size[1]) for item in items) / total_area
    room_center = (room.grid_w / 2.0, room.grid_h / 2.0)
    diagonal = math.hypot(room.grid_w, room.grid_h)
    distance = math.dist((centroid_x, centroid_y), room_center)
    score = distance / max(1.0, diagonal)
    violations = []
    if score > 0.2:
        violations.append("Furniture mass is visually off-center")
    return score, violations


def score_alignment_penalty(room: Room, items: list[Furniture]) -> tuple[float, list[str]]:
    score = 0.0
    violations: list[str] = []
    for item in items:
        if item.furniture_type not in {FurnitureType.STORAGE, FurnitureType.TV_STAND, FurnitureType.BED}:
            continue
        wall_distance = _distance_to_nearest_wall(room, item)
        if wall_distance > 1:
            score += wall_distance - 1
            violations.append(f"{item.name} is not anchored near a wall")
    return score, violations


def evaluate_layout_cost(
    room: Room,
    items: list[Furniture],
    enabled_terms: set[str] | None = None,
    weights: dict[str, float] | None = None,
) -> LayoutScore:
    rule_funcs: dict[str, Callable[[Room, list[Furniture]], tuple[float, list[str]]]] = {
        "clearance_violation": score_clearance_violation,
        "circulation_penalty": score_circulation_penalty,
        "pairwise_distance_penalty": score_pairwise_distance_penalty,
        "conversation_penalty": score_conversation_penalty,
        "visual_balance_penalty": score_visual_balance_penalty,
        "alignment_penalty": score_alignment_penalty,
    }
    active_terms = set(rule_funcs) if enabled_terms is None else set(enabled_terms)
    merged_weights = dict(DEFAULT_RULE_WEIGHTS)
    if weights:
        merged_weights.update(weights)

    validate_layout(room, items)

    breakdown = {name: 0.0 for name in rule_funcs}
    violations: list[str] = []
    for name, func in rule_funcs.items():
        if name not in active_terms:
            continue
        raw_score, local_violations = func(room, items)
        weighted_score = raw_score * merged_weights.get(name, 1.0)
        breakdown[name] = weighted_score
        violations.extend(local_violations)
    return LayoutScore(total=sum(breakdown.values()), breakdown=breakdown, violations=violations)


def evaluate_layout_from_placements(
    room: Room,
    placements: dict[str, PlacedFurniture],
    enabled_terms: set[str] | None = None,
    weights: dict[str, float] | None = None,
) -> LayoutScore:
    items = build_items_from_placements(placements)
    return evaluate_layout_cost(room, items, enabled_terms=enabled_terms, weights=weights)
