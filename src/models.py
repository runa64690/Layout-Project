from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

CELL_SIZE_M = 0.25


class Direction(str, Enum):
    NORTH = "NORTH"
    EAST = "EAST"
    SOUTH = "SOUTH"
    WEST = "WEST"


class FurnitureType(str, Enum):
    BED = "BED"
    TV = "TV"
    TV_STAND = "TV_STAND"
    STORAGE = "STORAGE"
    OTHER = "OTHER"


@dataclass(frozen=True)
class FurniturePreset:
    key: str
    label: str
    gw: int
    gd: int
    h_cell: int
    furniture_type: FurnitureType
    fall_dir: Direction | None = None
    pillow_side: Direction | None = None


@dataclass
class PlacedFurniture:
    key: str
    label: str
    gx: int | None = None
    gy: int | None = None
    rotation: int = 0
    placed: bool = False


FURNITURE_PRESETS = {
    "shelf": FurniturePreset(
        "shelf",
        "本棚",
        4,
        2,
        7,
        FurnitureType.STORAGE,
        fall_dir=Direction.NORTH,
    ),
    "bed": FurniturePreset(
        "bed",
        "ベッド",
        6,
        4,
        3,
        FurnitureType.BED,
        pillow_side=Direction.WEST,
    ),
    "table": FurniturePreset("table", "テーブル", 3, 2, 3, FurnitureType.OTHER),
    "tv_unit": FurniturePreset(
        "tv_unit",
        "テレビ台・テレビ",
        3,
        2,
        2,
        FurnitureType.TV_STAND,
        fall_dir=Direction.NORTH,
    ),
    "chair": FurniturePreset("chair", "椅子", 1, 1, 2, FurnitureType.OTHER),
}


DIRECTION_ORDER = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]


def rotate_direction(direction: Direction | None, quarter_turns: int) -> Direction | None:
    if direction is None:
        return None
    idx = DIRECTION_ORDER.index(direction)
    return DIRECTION_ORDER[(idx + quarter_turns) % 4]


def get_rotated_size(gw: int, gd: int, rotation: int) -> tuple[int, int]:
    if rotation % 2 == 0:
        return gw, gd
    return gd, gw


@dataclass
class Room:
    grid_w: int
    grid_h: int
    exit_ax: float
    exit_ay: float
    exit_bx: float
    exit_by: float

    def assert_rect_inside(self, gx: int, gy: int, gw: int, gd: int, name: str) -> None:
        if gx < 0 or gy < 0:
            raise ValueError(f"{name}: invalid position (gx={gx}, gy={gy})")
        if gw <= 0 or gd <= 0:
            raise ValueError(f"{name}: invalid size (gw={gw}, gd={gd})")
        if gx + gw > self.grid_w or gy + gd > self.grid_h:
            raise ValueError(
                f"{name}: out of room bounds "
                f"(x={gx}..{gx + gw - 1}, y={gy}..{gy + gd - 1})"
            )


@dataclass
class Furniture:
    name: str
    gx: int
    gy: int
    gw: int
    gd: int
    h_cell: int
    furniture_type: FurnitureType = FurnitureType.OTHER
    fall_dir: Direction | None = None
    pillow_side: Direction | None = None

    @property
    def h_m(self) -> float:
        return self.h_cell * CELL_SIZE_M


def validate_layout(room: Room, items: list[Furniture]) -> None:
    occupied: dict[tuple[int, int], str] = {}

    for item in items:
        room.assert_rect_inside(item.gx, item.gy, item.gw, item.gd, item.name)

        if item.h_cell <= 0:
            raise ValueError(f"{item.name}: h_cell must be >= 1")

        if item.furniture_type == FurnitureType.BED and item.pillow_side is None:
            raise ValueError(f"{item.name}: BED must have pillow_side")

        for x in range(item.gx, item.gx + item.gw):
            for y in range(item.gy, item.gy + item.gd):
                key = (x, y)
                if key in occupied:
                    other = occupied[key]
                    raise ValueError(
                        f"Furniture overlap: cell={key} is used by both {other} and {item.name}"
                    )
                occupied[key] = item.name
