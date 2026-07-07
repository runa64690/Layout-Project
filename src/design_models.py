from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

CELL_SIZE_M = 0.25


class Direction(str, Enum):
    NORTH = "NORTH"
    EAST = "EAST"
    SOUTH = "SOUTH"
    WEST = "WEST"


class WallSide(str, Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    TOP = "TOP"
    BOTTOM = "BOTTOM"


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
class WallOpening:
    key: str
    label: str
    wall: WallSide = WallSide.LEFT
    offset: int = 0
    length: int = 2
    placed: bool = False


@dataclass
class Room:
    grid_w: int
    grid_h: int
    exit_ax: float | None = None
    exit_ay: float | None = None
    exit_bx: float | None = None
    exit_by: float | None = None
    doors: list[WallOpening] = field(default_factory=list)
    windows: list[WallOpening] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.doors and None not in (self.exit_ax, self.exit_ay, self.exit_bx, self.exit_by):
            self.doors.append(
                WallOpening(
                    key="door_1",
                    label="Door",
                    wall=self._wall_side_from_segment(),
                    offset=self._offset_from_segment(),
                    length=self._length_from_segment(),
                    placed=True,
                )
            )
        self.sync_legacy_exit_fields()

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

    def validate_opening(self, opening: WallOpening) -> None:
        if opening.length <= 0:
            raise ValueError(f"{opening.label}: opening length must be >= 1")
        limit = self.grid_h if opening.wall in {WallSide.LEFT, WallSide.RIGHT} else self.grid_w
        if opening.offset < 0 or opening.offset + opening.length > limit:
            raise ValueError(f"{opening.label}: opening extends beyond the wall")

    def opening_segment(self, opening: WallOpening) -> tuple[float, float, float, float]:
        self.validate_opening(opening)
        if opening.wall == WallSide.LEFT:
            return (0.0, float(opening.offset), 0.0, float(opening.offset + opening.length))
        if opening.wall == WallSide.RIGHT:
            return (float(self.grid_w), float(opening.offset), float(self.grid_w), float(opening.offset + opening.length))
        if opening.wall == WallSide.BOTTOM:
            return (float(opening.offset), 0.0, float(opening.offset + opening.length), 0.0)
        return (float(opening.offset), float(self.grid_h), float(opening.offset + opening.length), float(self.grid_h))

    def door_anchor_cells(self) -> list[tuple[int, int]]:
        anchors: set[tuple[int, int]] = set()
        for door in self.doors:
            if not door.placed:
                continue
            self.validate_opening(door)
            if door.wall == WallSide.LEFT:
                anchors.update((0, y) for y in range(door.offset, door.offset + door.length))
            elif door.wall == WallSide.RIGHT:
                anchors.update((self.grid_w - 1, y) for y in range(door.offset, door.offset + door.length))
            elif door.wall == WallSide.BOTTOM:
                anchors.update((x, 0) for x in range(door.offset, door.offset + door.length))
            else:
                anchors.update((x, self.grid_h - 1) for x in range(door.offset, door.offset + door.length))
        return sorted((x, y) for x, y in anchors if 0 <= x < self.grid_w and 0 <= y < self.grid_h)

    def sync_legacy_exit_fields(self) -> None:
        placed_doors = [door for door in self.doors if door.placed]
        if not placed_doors:
            self.exit_ax = None
            self.exit_ay = None
            self.exit_bx = None
            self.exit_by = None
            return
        self.exit_ax, self.exit_ay, self.exit_bx, self.exit_by = self.opening_segment(placed_doors[0])

    def _wall_side_from_segment(self) -> WallSide:
        if self.exit_ax == 0 and self.exit_bx == 0:
            return WallSide.LEFT
        if self.exit_ax == self.grid_w and self.exit_bx == self.grid_w:
            return WallSide.RIGHT
        if self.exit_ay == 0 and self.exit_by == 0:
            return WallSide.BOTTOM
        return WallSide.TOP

    def _offset_from_segment(self) -> int:
        wall = self._wall_side_from_segment()
        if wall in {WallSide.LEFT, WallSide.RIGHT}:
            return int(min(self.exit_ay or 0.0, self.exit_by or 0.0))
        return int(min(self.exit_ax or 0.0, self.exit_bx or 0.0))

    def _length_from_segment(self) -> int:
        wall = self._wall_side_from_segment()
        if wall in {WallSide.LEFT, WallSide.RIGHT}:
            return max(1, int(abs((self.exit_by or 0.0) - (self.exit_ay or 0.0))))
        return max(1, int(abs((self.exit_bx or 0.0) - (self.exit_ax or 0.0))))


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

    for anchor in room.door_anchor_cells():
        if anchor in occupied:
            raise ValueError(f"Door clearance blocked at cell={anchor} by {occupied[anchor]}")
