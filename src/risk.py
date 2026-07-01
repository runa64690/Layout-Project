from layout_cost import *
"""

import math
from typing import Callable

from models import Direction, Furniture, FurnitureType, Room

DEFAULT_RULE_WEIGHTS = {
    "fall_hazard_to_bed": 5.0,
    "exit_blocking_by_tall_items": 3.0,
    "tv_fall_zone_near_bed_head": 4.0,
}


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def point_to_segment_dist(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    abx, aby = bx - ax, by - ay
    apx, apy = px - ax, py - ay
    denom = abx * abx + aby * aby

    if denom == 0.0:
        return math.hypot(px - ax, py - ay)

    t = (apx * abx + apy * aby) / denom
    t = clamp(t, 0.0, 1.0)
    cx, cy = ax + t * abx, ay + t * aby
    return math.hypot(px - cx, py - cy)


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


def build_fall_zone_rect(item: Furniture) -> tuple[int, int, int, int] | None:
    if item.fall_dir is None:
        return None

    gx, gy, gw, gd, h = item.gx, item.gy, item.gw, item.gd, item.h_cell

    if item.fall_dir == Direction.NORTH:
        return (gx, gy + gd, gx + gw, gy + gd + h)
    if item.fall_dir == Direction.EAST:
        return (gx + gw, gy, gx + gw + h, gy + gd)
    if item.fall_dir == Direction.SOUTH:
        return (gx, gy - h, gx + gw, gy)
    if item.fall_dir == Direction.WEST:
        return (gx - h, gy, gx, gy + gd)

    return None


def build_bed_head_zone_rect(bed: Furniture) -> tuple[int, int, int, int]:
    if bed.pillow_side is None:
        raise ValueError(f"{bed.name}: bed must have pillow_side")

    gx, gy, gw, gd = bed.gx, bed.gy, bed.gw, bed.gd
    band = 2

    if bed.pillow_side == Direction.NORTH:
        return (gx, gy + gd, gx + gw, gy + gd + band)
    if bed.pillow_side == Direction.SOUTH:
        return (gx, gy - band, gx + gw, gy)
    if bed.pillow_side == Direction.EAST:
        return (gx + gw, gy, gx + gw + band, gy + gd)
    if bed.pillow_side == Direction.WEST:
        return (gx - band, gy, gx, gy + gd)

    raise ValueError(f"{bed.name}: invalid pillow_side")


def risk_v1(room: Room, items: list[Furniture]) -> float:
    total = 0.0

    for item in items:
        cx = item.gx + item.gw / 2.0
        cy = item.gy + item.gd / 2.0
        dist = point_to_segment_dist(
            cx,
            cy,
            room.exit_ax,
            room.exit_ay,
            room.exit_bx,
            room.exit_by,
        )

        height_factor = 0.5 + 0.5 * (item.h_m / 2.0)
        total += (1.0 / (dist + 0.2)) * height_factor

    return total


def score_fall_hazard_to_bed(room: Room, items: list[Furniture]) -> tuple[float, list[str]]:
    del room

    score = 0.0
    violations: list[str] = []
    beds = [item for item in items if item.furniture_type == FurnitureType.BED]

    for item in items:
        if item.furniture_type == FurnitureType.BED:
            continue

        zone = build_fall_zone_rect(item)
        if zone is None:
            continue

        for bed in beds:
            overlap = rect_intersection_area_cells(zone, rect_of(bed))
            if overlap <= 0:
                continue

            raw = 1.0 + 0.1 * overlap
            score += raw
            violations.append(
                f"{item.name} fall zone overlaps with {bed.name} (overlap={overlap} cells)"
            )

    return score, violations


def total_fall_hazard_overlap_cells(items: list[Furniture]) -> int:
    total_overlap = 0
    beds = [item for item in items if item.furniture_type == FurnitureType.BED]

    for item in items:
        if item.furniture_type == FurnitureType.BED:
            continue

        zone = build_fall_zone_rect(item)
        if zone is None:
            continue

        for bed in beds:
            total_overlap += rect_intersection_area_cells(zone, rect_of(bed))

    return total_overlap


def score_exit_blocking_by_tall_items(room: Room, items: list[Furniture]) -> tuple[float, list[str]]:
    score = 0.0
    violations: list[str] = []

    tall_threshold = 5
    near_exit_threshold = 2.0

    for item in items:
        if item.h_cell < tall_threshold:
            continue

        cx = item.gx + item.gw / 2.0
        cy = item.gy + item.gd / 2.0
        dist = point_to_segment_dist(
            cx,
            cy,
            room.exit_ax,
            room.exit_ay,
            room.exit_bx,
            room.exit_by,
        )

        if dist > near_exit_threshold:
            continue

        raw = 1.0 + (near_exit_threshold - dist)
        score += raw
        violations.append(f"[Rule2] {item.name} is near exit dist={dist:.2f}")

    return score, violations


def score_tv_fall_zone_near_bed_head(room: Room, items: list[Furniture]) -> tuple[float, list[str]]:
    del room

    score = 0.0
    violations: list[str] = []

    beds = [item for item in items if item.furniture_type == FurnitureType.BED]
    tv_items = [
        item
        for item in items
        if item.furniture_type in {FurnitureType.TV, FurnitureType.TV_STAND}
    ]

    for bed in beds:
        head_zone = build_bed_head_zone_rect(bed)

        for tv in tv_items:
            fall_zone = build_fall_zone_rect(tv)
            overlap = 0 if fall_zone is None else rect_intersection_area_cells(head_zone, fall_zone)
            if overlap <= 0:
                continue

            raw = 1.0 + 0.1 * overlap
            score += raw

            violations.append(
                f"[TVFallHead] {tv.name} fall zone overlaps {bed.name} head zone ({overlap} cells)"
            )

    return score, violations


def evaluate_layout_risk(
    room: Room,
    items: list[Furniture],
    enabled_rules: set[str] | None = None,
    weights: dict[str, float] | None = None,
) -> dict:
    rule_funcs: dict[str, Callable[[Room, list[Furniture]], tuple[float, list[str]]]] = {
        "fall_hazard_to_bed": score_fall_hazard_to_bed,
        "exit_blocking_by_tall_items": score_exit_blocking_by_tall_items,
        "tv_fall_zone_near_bed_head": score_tv_fall_zone_near_bed_head,
    }

    active_rules = set(rule_funcs.keys()) if enabled_rules is None else set(enabled_rules)

    merged_weights = dict(DEFAULT_RULE_WEIGHTS)
    if weights:
        merged_weights.update(weights)

    breakdown = {name: 0.0 for name in rule_funcs}
    violations: list[str] = []

    for name, fn in rule_funcs.items():
        if name not in active_rules:
            continue

        raw_score, rule_violations = fn(room, items)
        weighted = raw_score * merged_weights.get(name, 1.0)
        breakdown[name] = weighted
        violations.extend(rule_violations)

    total = sum(breakdown.values())

    return {
        "total": total,
        "breakdown": breakdown,
        "violations": violations,
    }
"""
