from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# risk_v2互換のためにセルの高さ→m変換
CELL_SIZE_M = 0.25

# 家具の方向
class Direction(str, Enum):
    NORTH = "NORTH"
    EAST = "EAST"
    SOUTH = "SOUTH"
    WEST = "WEST"

# 家具の種類
class FurnitureType(str, Enum):
    BED = "BED"
    TV = "TV"
    TV_STAND = "TV_STAND"
    STORAGE = "STORAGE"
    OTHER = "OTHER"

# 家具の固定サイズ、高さ、種別、初期向きを持つプリセット
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

# 家具配置UI上での配置状態を持つ
@dataclass
class PlacedFurniture:
    key: str
    label: str
    gx: int | None = None
    gy: int | None = None
    rotation: int = 0
    placed: bool = False

# 家具のプリセット辞書
FURNITURE_PRESETS = {
    "shelf": FurniturePreset("shelf","本棚",4,2,7,FurnitureType.STORAGE, fall_dir=Direction.EAST),
    "bed": FurniturePreset("bed","ベッド",6,4,3,FurnitureType.BED, pillow_side=Direction.NORTH),
    "table": FurniturePreset("table","テーブル",3,2,3,FurnitureType.OTHER),
    "tv_unit": FurniturePreset("tv_unit","テレビ台・テレビ",3,2,2,FurnitureType.OTHER),
    "chair": FurniturePreset("chair","椅子",1,1,2,FurnitureType.OTHER),
}

# 家具配置UIの回転ヘルパー
DIRECTION_ORDER = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]

def rotate_direction(direction: Direction | None, quarter_turns: int) -> Direction | None:
    if direction is None:
        return None
    idx = DIRECTION_ORDER.index(direction)
    return DIRECTION_ORDER[(idx + quarter_turns) % 4]

def get_rotated_size(gw: int,gd: int,rotation: int) -> tuple[int,int]:
    if rotation % 2 == 0:
        return gw, gd
    return gd, gw

@dataclass
class Room:
    # グリッドサイズ
    grid_w: int
    grid_h: int

    # 出口線分
    exit_ax: float
    exit_ay: float
    exit_bx: float
    exit_by: float

    def assert_rect_inside(self, gx: int, gy: int, gw: int, gd: int, name: str) -> None:
        # 家具の矩形が部屋内に収まっているか確認する
        if gx < 0 or gy < 0:
            raise ValueError(f"{name}: 座標が負です (gx={gx}, gy={gy})")
        if gw <= 0 or gd <= 0:
            raise ValueError(f"{name}: サイズが不正です (gw={gw},gd={gd})")
        if gx + gw > self.grid_w or gy + gd > self.grid_h:
            raise ValueError(
                f"{name}: 部屋からはみ出しています "
                f"(x={gx}..{gx + gw - 1},y={gy}..{gy + gd - 1})"
            )

@dataclass
class Furniture:
    name: str

    # グリッド座標(左下原点)
    gx: int
    gy: int

    # グリッドサイズ(幅・奥行)
    gw: int
    gd: int

    # 高さはセル数で保持
    h_cell: int

    furniture_type: FurnitureType = FurnitureType.OTHER
    fall_dir: Direction | None = None
    pillow_side: Direction | None = None

    @property
    def h_m(self) -> float:
        return self.h_cell * CELL_SIZE_M


def validate_layout(room: Room, items: list[Furniture]) -> None:
    # 部屋内チェックと重なりチェックを行う
    occupied: dict[tuple[int, int], str] = {}

    for f in items:
        room.assert_rect_inside(f.gx, f.gy, f.gw, f.gd, f.name)
        
        if f.h_cell <= 0:
            raise ValueError(f"{f.name}: h_cell は 1以上にしてください")
        
        if f.furniture_type == FurnitureType.BED and f.pillow_side is None:
            raise ValueError(f"{f.name}: BED must have pillow_side")
        
        for x in range(f.gx, f.gx + f.gw):
            for y in range(f.gy, f.gy + f.gd):
                key = (x, y)
                if key in occupied:
                    other = occupied[key]
                    raise ValueError(
                        f"Furniture overlap: cell={key} is used by both {other} and {f.name}"
                    )
                occupied[key] = f.name