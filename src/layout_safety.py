"""Version 2: scenario geometry, exposure and raster escape checks.

Sources, assumptions and limits: docs/safety-design.md. No probabilities are
inferred from these geometrical tests or from self-reported mitigation.
"""
from collections import deque
from dataclasses import dataclass, field
from functools import lru_cache
import math

from design_models import CELL_SIZE_M, Direction, FurnitureType
from spatial_geometry import (bounds, intersection_area, intersection_polygon,
                              occupied_cells, polygon_area, rect_polygon)
from wall_alignment import backed_by_wall

EVALUATION_VERSION = 2


@dataclass
class HazardScenario:
    id: str
    source_key: str
    kind: str
    direction: str
    primary: bool
    points: list[tuple[float, float]]


@dataclass
class SafetyIssue:
    kind: str
    scenario_id: str
    source_key: str
    target_key: str
    area_m2: float = 0.0
    primary: bool = False


@dataclass
class WindowDistance:
    window_key: str
    target_key: str
    distance_m: float
    penalty: float


@dataclass
class SafetyAssessment:
    status: str = "not_evaluated"
    violation_count: int = 0
    overlap_area_m2: float = 0.0
    primary_overlap_area_m2: float = 0.0
    route_checks: int = 0
    failed_route_checks: int = 0
    scenarios: list[HazardScenario] = field(default_factory=list)
    issues: list[SafetyIssue] = field(default_factory=list)
    window_distances: list[WindowDistance] = field(default_factory=list)
    unassessed: list[str] = field(default_factory=list)

    @property
    def priority(self):
        # Primary overlap is a tie-breaker, not a claimed likelihood multiplier.
        return (self.violation_count, self.overlap_area_m2, self.primary_overlap_area_m2)


def side_zone(item, direction, depth):
    w, d = item.local_size
    rect = {Direction.NORTH: (-w/2, d/2, w/2, d/2+depth),
            Direction.EAST: (w/2, -d/2, w/2+depth, d/2),
            Direction.SOUTH: (-w/2, -d/2-depth, w/2, -d/2),
            Direction.WEST: (-w/2-depth, -d/2, -w/2, d/2)}[direction]
    return item.local_rect(rect)


def bed_head_polygon(item):
    w, d = item.local_size
    direction = item.base_pillow_side
    if direction is None:
        from design_models import rotate_direction
        direction = rotate_direction(item.pillow_side, -item.rotation)
    if direction is None:
        raise ValueError(f"{item.name}: bed must have pillow_side")
    rect = {Direction.NORTH: (-w/2, d/2-min(2, d), w/2, d/2),
            Direction.SOUTH: (-w/2, -d/2, w/2, -d/2+min(2, d)),
            Direction.EAST: (w/2-min(2, w), -d/2, w/2, d/2),
            Direction.WEST: (-w/2, -d/2, -w/2+min(2, w), d/2)}[direction]
    return item.local_rect(rect)


def build_hazard_scenarios(room, items):
    clip = rect_polygon((0, 0, room.grid_w, room.grid_h))
    scenarios = []
    for item in items:
        if item.ceiling_mounted:
            scenarios.append(HazardScenario(f"{item.key}:drop", item.key, "drop", "DOWN", True,
                                             intersection_polygon(item.footprint, clip)))
        elif item.fall_dir is not None:
            directions = list(Direction)
            # The rear of a sufficiently aligned wall-backed item is supported
            # by the wall in this model; lateral failure is still checked.
            if backed_by_wall(room, item):
                directions.remove(Direction.SOUTH)
            front = item.base_fall_dir or Direction.NORTH
            for direction in directions:
                polygon = intersection_polygon(side_zone(item, direction, item.h_cell), clip)
                if polygon_area(polygon) > 1e-6:
                    scenarios.append(HazardScenario(f"{item.key}:{direction.value}", item.key, "fall",
                                                     direction.value, direction == front, polygon))
    return scenarios


@lru_cache(maxsize=8192)
def _cells(points):
    return frozenset(occupied_cells(list(points)))


def polygon_cells(points):
    return _cells(tuple(points)) if points else frozenset()


def _access_cells(item):
    w, d = item.local_size
    if item.furniture_type == FurnitureType.BED:
        directions = (Direction.NORTH, Direction.SOUTH) if w >= d else (Direction.EAST, Direction.WEST)
    else:
        directions = (Direction.NORTH,)
    return set().union(*(polygon_cells(side_zone(item, direction, 1)) for direction in directions))


@lru_cache(maxsize=64)
def _room_cells(w, h):
    return frozenset((x, y) for x in range(w) for y in range(h))


def _reachable(free, exits):
    visited = set(exits) & free
    queue = deque(visited)
    while queue:
        x, y = queue.popleft()
        for cell in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
            if cell in free and cell not in visited:
                visited.add(cell)
                queue.append(cell)
    return visited


def _point_segment_distance(point, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    t = ((point[0]-a[0])*dx+(point[1]-a[1])*dy) / (dx*dx+dy*dy) if dx or dy else 0
    t = max(0, min(1, t))
    return math.hypot(point[0]-a[0]-t*dx, point[1]-a[1]-t*dy)


def segment_polygon_distance(a, b, points):
    # All valid furniture is inside the room; windows lie on its boundary.
    return min(min(_point_segment_distance(p, a, b) for p in points),
               min(_point_segment_distance(q, p, r) for q in (a, b)
                   for p, r in zip(points, points[1:]+points[:1])))


def assess_safety(room, items):
    if hasattr(room, "boundary"):
        from polygon_room import polygon_safety
        return polygon_safety(room, items)
    result = SafetyAssessment(scenarios=build_hazard_scenarios(room, items))
    targets = [i for i in items if i.furniture_type in (FurnitureType.BED, FurnitureType.SEAT)
               and not i.ceiling_mounted]
    for scenario in result.scenarios:
        for target in targets:
            if scenario.source_key == target.key:
                continue
            area = intersection_area(scenario.points, target.footprint) * CELL_SIZE_M**2
            if area > 1e-8:
                result.issues.append(SafetyIssue("exposure", scenario.id, scenario.source_key,
                                                target.key, area, scenario.primary))
                result.overlap_area_m2 += area
                if scenario.primary:
                    result.primary_overlap_area_m2 += area

    all_cells = _room_cells(room.grid_w, room.grid_h)
    occupied = set().union(*(polygon_cells(i.footprint) for i in items if not i.ceiling_mounted))
    base_free = all_cells - occupied
    starts = {t.key: _access_cells(t) & base_free for t in targets}
    exits = set(room.door_anchor_cells())
    if not exits:
        result.unassessed.append("No placed exit: escape routes are not evaluated")
    if not targets:
        result.unassessed.append("No bed or seat: personal exposure and escape are not evaluated")
    if exits and targets:
        # Each scenario is checked separately, retaining the original footprint
        # conservatively as an obstruction. Never union mutually exclusive falls.
        for scenario in [None] + result.scenarios:
            free = base_free if scenario is None else base_free - polygon_cells(scenario.points)
            reachable = _reachable(free, exits)
            for target in targets:
                result.route_checks += 1
                if not (starts[target.key] & reachable):
                    result.failed_route_checks += 1
                    result.issues.append(SafetyIssue("escape_blocked",
                        scenario.id if scenario else "baseline", scenario.source_key if scenario else "",
                        target.key, primary=scenario.primary if scenario else True))

    for window in room.windows:
        if not window.placed:
            continue
        ax, ay, bx, by = room.opening_segment(window)
        for target in targets:
            distance = segment_polygon_distance((ax, ay), (bx, by), target.footprint)*CELL_SIZE_M
            result.window_distances.append(WindowDistance(window.key, target.key, distance, 1/(1+distance)))
    result.violation_count = len(result.issues)
    result.status = "unmet" if result.issues else "not_evaluated" if result.unassessed else "met"
    return result
