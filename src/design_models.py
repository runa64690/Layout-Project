from __future__ import annotations

from dataclasses import dataclass, field
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
    TABLE = "TABLE"
    SEAT = "SEAT"
    OTHER = "OTHER"


@dataclass(frozen=True)
class ClearanceRule:
    min_cells: int
    mode: str


@dataclass(frozen=True)
class PairwiseRule:
    other_key: str
    min_distance_cells: int
    max_distance_cells: int


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
    clearance: ClearanceRule | None = None
    pairwise_rules: tuple[PairwiseRule, ...] = ()
    conversation_seat: bool = False


@dataclass
class PlacedFurniture:
    key: str
    label: str
    gx: int | None = None
    gy: int | None = None
    rotation: int = 0
    placed: bool = False


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
    key: str
    name: str
    gx: int
    gy: int
    gw: int
    gd: int
    h_cell: int
    furniture_type: FurnitureType = FurnitureType.OTHER
    rotation: int = 0
    fall_dir: Direction | None = None
    pillow_side: Direction | None = None
    clearance: ClearanceRule | None = None
    pairwise_rules: tuple[PairwiseRule, ...] = field(default_factory=tuple)
    conversation_seat: bool = False

    @property
    def h_m(self) -> float:
        return self.h_cell * CELL_SIZE_M

    @property
    def center(self) -> tuple[float, float]:
        return (self.gx + self.gw / 2.0, self.gy + self.gd / 2.0)


FURNITURE_PRESETS: dict[str, FurniturePreset] = {
    "shelf": FurniturePreset(
        key="shelf",
        label="Shelf",
        gw=4,
        gd=2,
        h_cell=7,
        furniture_type=FurnitureType.STORAGE,
        fall_dir=Direction.NORTH,
        clearance=ClearanceRule(min_cells=2, mode="front"),
    ),
    "bed": FurniturePreset(
        key="bed",
        label="Bed",
        gw=6,
        gd=4,
        h_cell=3,
        furniture_type=FurnitureType.BED,
        pillow_side=Direction.WEST,
        clearance=ClearanceRule(min_cells=2, mode="side"),
        pairwise_rules=(PairwiseRule(other_key="table", min_distance_cells=0, max_distance_cells=3),),
    ),
    "table": FurniturePreset(
        key="table",
        label="Table",
        gw=3,
        gd=2,
        h_cell=3,
        furniture_type=FurnitureType.TABLE,
        clearance=ClearanceRule(min_cells=1, mode="all"),
    ),
    "tv_unit": FurniturePreset(
        key="tv_unit",
        label="TV Unit",
        gw=3,
        gd=2,
        h_cell=2,
        furniture_type=FurnitureType.TV_STAND,
        fall_dir=Direction.NORTH,
        clearance=ClearanceRule(min_cells=1, mode="front"),
    ),
    "chair": FurniturePreset(
        key="chair",
        label="Chair",
        gw=1,
        gd=1,
        h_cell=2,
        furniture_type=FurnitureType.SEAT,
        clearance=ClearanceRule(min_cells=1, mode="front"),
        pairwise_rules=(PairwiseRule(other_key="table", min_distance_cells=1, max_distance_cells=4),),
        conversation_seat=True,
    ),
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


def build_furniture_from_placement(key: str, placement: PlacedFurniture) -> Furniture:
    preset = FURNITURE_PRESETS[key]
    if placement.gx is None or placement.gy is None:
        raise ValueError(f"{key}: placement is incomplete")

    gw, gd = get_rotated_size(preset.gw, preset.gd, placement.rotation)
    return Furniture(
        key=key,
        name=preset.label,
        gx=placement.gx,
        gy=placement.gy,
        gw=gw,
        gd=gd,
        h_cell=preset.h_cell,
        furniture_type=preset.furniture_type,
        rotation=placement.rotation,
        fall_dir=rotate_direction(preset.fall_dir, placement.rotation),
        pillow_side=rotate_direction(preset.pillow_side, placement.rotation),
        clearance=preset.clearance,
        pairwise_rules=preset.pairwise_rules,
        conversation_seat=preset.conversation_seat,
    )


def build_items_from_placements(placements: dict[str, PlacedFurniture]) -> list[Furniture]:
    items: list[Furniture] = []
    for key, placement in placements.items():
        if not placement.placed:
            continue
        items.append(build_furniture_from_placement(key, placement))
    return items


def clone_placements(placements: dict[str, PlacedFurniture]) -> dict[str, PlacedFurniture]:
    return {
        key: PlacedFurniture(
            key=value.key,
            label=value.label,
            gx=value.gx,
            gy=value.gy,
            rotation=value.rotation,
            placed=value.placed,
        )
        for key, value in placements.items()
    }


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
