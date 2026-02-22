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
            raise ValueError(f"{f.name}: BED は pillow_side が必須です")
        
        for x in range(f.gx, f.gx + f.gw):
            for y in range(f.gy, f.gy + f.gd):
                key = (x, y)
                if key in occupied:
                    other = occupied[key]
                    raise ValueError(
                        f"重なり検出: cell={key} が {other} と {f.name} で重複しています"
                    )
                occupied[key] = f.name