"""Display/placement geometry, independent of scoring rules and UI frameworks."""
from __future__ import annotations

from design_models import Room, WallOpening, WallSide


def build_door_front_rect(room: Room, opening: WallOpening, depth: int = 2):
    if not opening.placed:
        return None
    room.validate_opening(opening)
    start = opening.offset
    end = start + opening.length
    if opening.wall == WallSide.LEFT:
        return (0, start, min(room.grid_w, depth), end)
    if opening.wall == WallSide.RIGHT:
        return (max(0, room.grid_w - depth), start, room.grid_w, end)
    if opening.wall == WallSide.BOTTOM:
        return (start, 0, end, min(room.grid_h, depth))
    return (start, max(0, room.grid_h - depth), end, room.grid_h)
