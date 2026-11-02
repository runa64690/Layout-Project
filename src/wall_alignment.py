"""Furniture faces and solid wall segments shared by scoring and refinement.

Distances are cell units. Constants below are design assumptions, not standards.
"""
import math
from dataclasses import replace

from design_models import CELL_SIZE_M, Direction, FurnitureType, WallSide, build_furniture_from_placement

WALL_GAP = .02 / CELL_SIZE_M
NEAR_WALL = .10 / CELL_SIZE_M
DIRECTION_NORMAL = {Direction.NORTH: (0, 1), Direction.EAST: (1, 0),
                    Direction.SOUTH: (0, -1), Direction.WEST: (-1, 0)}
WALL_NORMAL = {WallSide.LEFT: (-1, 0), WallSide.RIGHT: (1, 0),
               WallSide.BOTTOM: (0, -1), WallSide.TOP: (0, 1)}


def preferred_faces(item):
    if item.furniture_type in {FurnitureType.STORAGE, FurnitureType.TV_STAND}:
        return [Direction.SOUTH]
    if item.furniture_type == FurnitureType.BED:
        w, d = item.local_size
        sides = [Direction.NORTH, Direction.SOUTH] if w >= d else [Direction.EAST, Direction.WEST]
        return list(dict.fromkeys([item.base_pillow_side or Direction.WEST] + sides))
    return []


def solid_segments(room, wall):
    limit = room.grid_h if wall in (WallSide.LEFT, WallSide.RIGHT) else room.grid_w
    intervals = sorted((o.offset, o.offset + o.length) for o in room.doors + room.windows
                       if o.placed and o.wall == wall)
    start = 0
    for lo, hi in intervals:
        if lo > start:
            yield start, lo
        start = max(start, hi)
    if start < limit:
        yield start, limit


def face_points(item, face):
    w, d = item.local_size
    corners = {Direction.NORTH: [(-w/2, d/2), (w/2, d/2)],
               Direction.SOUTH: [(-w/2, -d/2), (w/2, -d/2)],
               Direction.EAST: [(w/2, -d/2), (w/2, d/2)],
               Direction.WEST: [(-w/2, -d/2), (-w/2, d/2)]}
    from spatial_geometry import transform_polygon
    return transform_polygon(corners[face], item.center, item.rotation)


def face_angle(item, face, wall):
    nx, ny = DIRECTION_NORMAL[face]
    a = item.rotation * math.pi/2
    rx, ry = math.cos(a)*nx + math.sin(a)*ny, -math.sin(a)*nx + math.cos(a)*ny
    wx, wy = WALL_NORMAL[wall]
    return math.degrees(math.acos(max(-1, min(1, rx*wx + ry*wy))))


def face_gap(room, item, face, wall):
    points = face_points(item, face)
    if wall == WallSide.LEFT:
        return max(p[0] for p in points)
    if wall == WallSide.RIGHT:
        return max(room.grid_w-p[0] for p in points)
    if wall == WallSide.BOTTOM:
        return max(p[1] for p in points)
    return max(room.grid_h-p[1] for p in points)


def fits_segment(item, face, wall, segment):
    axis = 1 if wall in (WallSide.LEFT, WallSide.RIGHT) else 0
    coordinates = [p[axis] for p in face_points(item, face)]
    return min(coordinates) >= segment[0]-1e-6 and max(coordinates) <= segment[1]+1e-6


def backed_by_wall(room, item):
    if hasattr(room, "boundary"):
        from polygon_room import face_metrics
        return any(degrees <= 5 and gap <= NEAR_WALL and along <= 1e-6
                   for degrees, gap, along in face_metrics(room, item, Direction.SOUTH))
    return any(face_angle(item, Direction.SOUTH, wall) <= 5
               and face_gap(room, item, Direction.SOUTH, wall) <= NEAR_WALL
               and fits_segment(item, Direction.SOUTH, wall, segment)
               for wall in WallSide for segment in solid_segments(room, wall))


def alignment_cost(room, item):
    if hasattr(room, "boundary"):
        from polygon_room import polygon_alignment_cost
        return polygon_alignment_cost(room, item)
    faces = preferred_faces(item)
    if not faces:
        return 0.0
    costs = []
    for wall in WallSide:
        for face in faces:
            for segment in solid_segments(room, wall):
                # Penalize along-wall displacement too; openings cannot be a target.
                axis = 1 if wall in (WallSide.LEFT, WallSide.RIGHT) else 0
                coords = [p[axis] for p in face_points(item, face)]
                span = max(coords)-min(coords)
                if span > segment[1]-segment[0]+1e-6:
                    continue
                along = max(0, segment[0]-min(coords), max(coords)-segment[1])
                gap = abs(face_gap(room, item, face, wall)-WALL_GAP)
                costs.append((gap + along)*CELL_SIZE_M/.25 + face_angle(item, face, wall)/10)
    return min(costs, default=100.0)


def wall_placements(room, key, placement, *, discrete=False):
    """Deterministic refinement candidates, never a Metropolis proposal kernel."""
    if hasattr(room, "boundary"):
        from polygon_room import polygon_wall_placements
        yield from polygon_wall_placements(room, key, placement)
        return
    item = build_furniture_from_placement(key, placement)
    for wall in WallSide:
        for face in preferred_faces(item):
            nx, ny = DIRECTION_NORMAL[face]
            wx, wy = WALL_NORMAL[wall]
            rotation = ((math.atan2(ny, nx)-math.atan2(wy, wx))/(math.pi/2)) % 4
            rotated = replace(placement, rotation=round(rotation) % 4)
            new = build_furniture_from_placement(key, rotated)
            rotated.gx = item.center[0]-new.gw/2
            rotated.gy = item.center[1]-new.gd/2
            gap = 0 if discrete else WALL_GAP
            if wall == WallSide.LEFT:
                rotated.gx = gap
            elif wall == WallSide.RIGHT:
                rotated.gx = room.grid_w-new.gw-gap
            elif wall == WallSide.BOTTOM:
                rotated.gy = gap
            else:
                rotated.gy = room.grid_h-new.gd-gap
            vertical = wall in (WallSide.LEFT, WallSide.RIGHT)
            length = new.gd if vertical else new.gw
            for lo, hi in solid_segments(room, wall):
                if length > hi-lo+1e-6:
                    continue
                candidate = replace(rotated)
                along = candidate.gy if vertical else candidate.gx
                along = max(lo, min(hi-length, along))
                if discrete:
                    along = round(along)
                if vertical:
                    candidate.gy = along
                else:
                    candidate.gx = along
                yield candidate
