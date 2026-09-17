"""Display/placement geometry, independent of scoring rules and UI frameworks."""
from __future__ import annotations

import math

from design_models import Room, WallOpening, WallSide


def build_window_scatter_rect(room: Room, opening: WallOpening, depth: int = 2):
    if not opening.placed:
        return None
    room.validate_opening(opening)
    if opening.wall == WallSide.LEFT:
        return (0, opening.offset, min(room.grid_w, depth), opening.offset + opening.length)
    if opening.wall == WallSide.RIGHT:
        return (max(0, room.grid_w - depth), opening.offset, room.grid_w, opening.offset + opening.length)
    if opening.wall == WallSide.BOTTOM:
        return (opening.offset, 0, opening.offset + opening.length, min(room.grid_h, depth))
    return (opening.offset, max(0, room.grid_h - depth), opening.offset + opening.length, room.grid_h)


def build_door_front_rect(room: Room, opening: WallOpening, width: int = 4, depth: int = 2):
    if not opening.placed:
        return None
    room.validate_opening(opening)
    limit = room.grid_h if opening.wall in {WallSide.LEFT, WallSide.RIGHT} else room.grid_w
    width = min(width, limit)
    center = opening.offset + opening.length / 2.0
    start = max(0, min(math.floor(center - width / 2.0), limit - width))
    end = start + width
    if opening.wall == WallSide.LEFT:
        return (0, start, min(room.grid_w, depth), end)
    if opening.wall == WallSide.RIGHT:
        return (max(0, room.grid_w - depth), start, room.grid_w, end)
    if opening.wall == WallSide.BOTTOM:
        return (start, 0, end, min(room.grid_h, depth))
    return (start, max(0, room.grid_h - depth), end, room.grid_h)
