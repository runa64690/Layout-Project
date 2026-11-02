"""Polygon rooms in the existing solver's cell coordinates (one cell = 25cm).

Only v2 constructs these rooms. The rectangular v1 domain and numerical path
remain unchanged. Rings are simple, counterclockwise and have no holes.
"""
from dataclasses import dataclass, field, replace
from functools import cached_property
import math

from shapely.geometry import Polygon, LineString, box

from design_models import Room, CELL_SIZE_M, build_furniture_from_placement
from spatial_geometry import EPSILON


def polygon_parts(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return [geometry] if geometry.area > EPSILON else []
    return [p for g in getattr(geometry, "geoms", []) for p in polygon_parts(g)]


@dataclass
class PolygonOpening:
    key: str
    label: str
    edge_id: str
    offset: float
    length: float
    placed: bool = True
    film: str = "unknown"
    curtains: str = "unknown"


@dataclass
class PolygonRoom(Room):
    boundary: list[tuple[float, float]] = field(default_factory=list)
    vertex_ids: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.polygon = Polygon(self.boundary)
        self.winding = 1 if self.polygon.exterior.is_ccw else -1
        if not self.polygon.is_valid or self.polygon.area <= EPSILON:
            raise ValueError("Room boundary must be a simple polygon with positive area")
        super().__post_init__()

    def edges(self):
        for i, a in enumerate(self.boundary):
            b = self.boundary[(i + 1) % len(self.boundary)]
            length = math.dist(a, b)
            yield self.vertex_ids[i], a, b, ((b[0]-a[0])/length, (b[1]-a[1])/length), length

    def edge(self, edge_id):
        return next((e for e in self.edges() if e[0] == edge_id), None)

    def validate_opening(self, opening):
        edge = self.edge(opening.edge_id)
        if edge is None:
            raise ValueError(f"{opening.key}: unknown wall edge")
        if opening.length <= 0 or opening.offset < 0 or opening.offset + opening.length > edge[4] + EPSILON:
            raise ValueError(f"{opening.key}: opening extends beyond the wall")

    def opening_segment(self, opening):
        self.validate_opening(opening)
        _, a, _, t, _ = self.edge(opening.edge_id)
        return (*[a[i]+t[i]*opening.offset for i in (0, 1)],
                *[a[i]+t[i]*(opening.offset+opening.length) for i in (0, 1)])

    def door_front(self, opening, depth=2):
        if not opening.placed:
            return Polygon()
        ax, ay, bx, by = self.opening_segment(opening)
        _, _, _, t, _ = self.edge(opening.edge_id)
        nx, ny = -t[1]*depth*self.winding, t[0]*depth*self.winding
        return Polygon([(ax, ay), (bx, by), (bx+nx, by+ny), (ax+nx, ay+ny)]).intersection(self.polygon)

    def contains_footprint(self, points):
        return self.polygon.buffer(EPSILON).covers(Polygon(points))

    @cached_property
    def floor_cells(self):
        # Conservative full-cell mask: no phantom route across notches or walls.
        padded = self.polygon.buffer(EPSILON)
        return frozenset((x, y) for x in range(self.grid_w) for y in range(self.grid_h)
                         if padded.covers(box(x, y, x+1, y+1)))

    @cached_property
    def door_connections(self):
        connections = {}
        padded = self.polygon.buffer(EPSILON)
        for door in self.doors:
            if door.placed:
                front = self.door_front(door)
                candidates = [c for c in self.floor_cells if front.intersection(box(c[0], c[1], c[0]+1, c[1]+1)).area > EPSILON]
                ax, ay, bx, by = self.opening_segment(door)
                count = max(1, math.ceil(door.length*2))
                for i in range(count):
                    t = (i+.5)/count
                    point = (ax+(bx-ax)*t, ay+(by-ay)*t)
                    # Use the first resolvable cell at the actual opening, not
                    # every cell in the 50cm clearance zone. A connector makes
                    # the approximation explicit for diagonal boundaries.
                    for cell in sorted(candidates, key=lambda c: math.dist(point, (c[0]+.5, c[1]+.5))):
                        connector = LineString([point, (cell[0]+.5, cell[1]+.5)])
                        if padded.covers(connector):
                            connections.setdefault(cell, []).append(connector)
                            break
        return connections

    def exit_cells(self, blocked=None):
        if blocked is None or blocked.is_empty:
            return set(self.door_connections)
        return {cell for cell, lines in self.door_connections.items()
                if any(line.intersection(blocked).length <= EPSILON for line in lines)}

    def door_anchor_cells(self):
        return sorted(self.door_connections)

    def solid_edges(self):
        for edge_id, a, b, t, length in self.edges():
            intervals = sorted((o.offset, o.offset+o.length) for o in self.doors+self.windows
                               if o.placed and o.edge_id == edge_id)
            start = 0
            for lo, hi in intervals + [(length, length)]:
                if lo > start + EPSILON:
                    yield (tuple(a[i]+t[i]*start for i in (0, 1)),
                           tuple(a[i]+t[i]*lo for i in (0, 1)), t)
                start = max(start, hi)


def validate_polygon_items(room, items):
    for item in items:
        if not room.contains_footprint(item.footprint):
            raise ValueError(f"{item.name}: out of room polygon")
        if not item.ceiling_mounted:
            for door in room.doors:
                if room.door_front(door).intersection(Polygon(item.footprint)).area > EPSILON:
                    raise ValueError(f"Door clearance blocked: {door.key} by {item.name}")


def face_metrics(room, item, face):
    from wall_alignment import face_points, DIRECTION_NORMAL
    angle = item.rotation * math.pi / 2
    nx, ny = DIRECTION_NORMAL[face]
    normal = (math.cos(angle)*nx+math.sin(angle)*ny, -math.sin(angle)*nx+math.cos(angle)*ny)
    points = face_points(item, face)
    for a, b, tangent in room.solid_edges():
        outward = (tangent[1]*room.winding, -tangent[0]*room.winding)
        degrees = math.degrees(math.acos(max(-1, min(1, sum(normal[i]*outward[i] for i in (0, 1))))))
        length = math.dist(a, b)
        along = [sum((p[i]-a[i])*tangent[i] for i in (0, 1)) for p in points]
        gap = max(-sum((p[i]-a[i])*outward[i] for i in (0, 1)) for p in points)
        if max(along)-min(along) <= length+EPSILON:
            yield degrees, gap, max(0, -min(along), max(along)-length)


def polygon_alignment_cost(room, item):
    from wall_alignment import preferred_faces, WALL_GAP
    faces = preferred_faces(item)
    if not faces:
        return 0.0
    return min(((abs(gap-WALL_GAP)+along)*CELL_SIZE_M/.25+degrees/10
                for face in faces for degrees, gap, along in face_metrics(room, item, face)), default=100.0)


def polygon_wall_placements(room, key, placement):
    from wall_alignment import preferred_faces, DIRECTION_NORMAL, WALL_GAP, face_points
    item = build_furniture_from_placement(key, placement)
    for a, b, t in room.solid_edges():
        outward = (t[1]*room.winding, -t[0]*room.winding)
        for face in preferred_faces(item):
            nx, ny = DIRECTION_NORMAL[face]
            rotation = ((math.atan2(ny, nx)-math.atan2(outward[1], outward[0]))/(math.pi/2)) % 4
            candidate = replace(placement, rotation=rotation)
            new = build_furniture_from_placement(key, candidate)
            candidate.gx = item.center[0]-new.gw/2
            candidate.gy = item.center[1]-new.gd/2
            new = build_furniture_from_placement(key, candidate)
            points = face_points(new, face)
            along = [sum((p[i]-a[i])*t[i] for i in (0, 1)) for p in points]
            length = math.dist(a, b)
            if max(along)-min(along) > length+EPSILON:
                continue
            slide = max(0, -min(along)) - max(0, max(along)-length)
            signed = sum((points[0][i]-a[i])*outward[i] for i in (0, 1))
            candidate.gx += t[0]*slide-outward[0]*(signed+WALL_GAP)
            candidate.gy += t[1]*slide-outward[1]*(signed+WALL_GAP)
            yield candidate


def polygon_safety(room, items):
    from design_models import Direction, FurnitureType
    from layout_safety import (SafetyAssessment, SafetyIssue, WindowDistance, HazardScenario,
                               side_zone, polygon_cells, _access_cells, _reachable)
    from wall_alignment import backed_by_wall
    result = SafetyAssessment()
    geometries = []
    targets = [i for i in items if i.furniture_type in (FurnitureType.BED, FurnitureType.SEAT) and not i.ceiling_mounted]
    for item in items:
        zones = []
        if item.ceiling_mounted:
            zones = [("drop", "DOWN", True, item.footprint)]
        elif item.fall_dir is not None:
            directions = list(Direction)
            if backed_by_wall(room, item):
                directions.remove(Direction.SOUTH)
            zones = [("fall", d.value, d == (item.base_fall_dir or Direction.NORTH), side_zone(item, d, item.h_cell)) for d in directions]
        for kind, direction, primary, points in zones:
            geometry = Polygon(points).intersection(room.polygon)
            parts = polygon_parts(geometry)
            if not parts:
                continue
            scenario_id = f"{item.key}:{'drop' if kind == 'drop' else direction}"
            geometries.append((scenario_id, item.key, primary, geometry))
            for part in parts:
                result.scenarios.append(HazardScenario(scenario_id, item.key, kind, direction, primary, list(part.exterior.coords)[:-1]))
            for target in targets:
                if target.key == item.key:
                    continue
                area = geometry.intersection(Polygon(target.footprint)).area * CELL_SIZE_M**2
                if area > 1e-8:
                    result.issues.append(SafetyIssue("exposure", scenario_id, item.key, target.key, area, primary))
                    result.overlap_area_m2 += area
                    if primary:
                        result.primary_overlap_area_m2 += area
    occupied = set().union(*(polygon_cells(i.footprint) for i in items if not i.ceiling_mounted))
    free_base = room.floor_cells - occupied
    starts = {i.key: _access_cells(i) & free_base for i in targets}
    exits = set(room.door_anchor_cells())
    if not exits:
        result.unassessed.append("No raster-resolvable exit: escape routes are not evaluated")
    if not targets:
        result.unassessed.append("No bed or seat: personal exposure and escape are not evaluated")
    if exits and targets:
        for sid, key, primary, geometry in [("baseline", "", True, Polygon())] + geometries:
            blocked = {c for c in free_base if geometry.intersection(box(c[0], c[1], c[0]+1, c[1]+1)).area > EPSILON}
            reachable = _reachable(free_base-blocked, room.exit_cells(geometry))
            for target in targets:
                result.route_checks += 1
                if not (starts[target.key] & reachable):
                    result.failed_route_checks += 1
                    result.issues.append(SafetyIssue("escape_blocked", sid, key, target.key, primary=primary))
    for window in room.windows:
        if window.placed:
            ax, ay, bx, by = room.opening_segment(window)
            for target in targets:
                distance = LineString([(ax, ay), (bx, by)]).distance(Polygon(target.footprint))*CELL_SIZE_M
                result.window_distances.append(WindowDistance(window.key, target.key, distance, 1/(1+distance)))
    result.violation_count = len(result.issues)
    result.status = "unmet" if result.issues else "not_evaluated" if result.unassessed else "met"
    return result
