import math
from models import Direction, Room, Furniture, FurnitureType

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def point_to_segment_dist(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    # 点(px, py)と線分(ax, ay)-(bx, by)の距離
    abx, aby = bx - ax, by - ay
    apx, apy = px - ax, py - ay
    denom = abx * abx + aby * aby

    if denom == 0.0:
        return math.hypot(px - ax, py - ay)
    
    t = (apx * abx + apy * aby) / denom
    t = clamp(t, 0.0, 1.0)
    cx, cy = ax + t * abx, ay + t * aby
    return math.hypot(px - cx, py - cy)

def rect_of(item: Furniture) -> tuple[int, int, int, int]:
    # 家具矩形を(x0,y0,x1,y1)で返す。
    return (item.gx, item.gy, item.gx + item.gw, item.gy + item.gd)

def rect_intersection_area_cells(
        a: tuple[int, int, int, int],
        b: tuple[int, int, int, int],
) -> int:
    # 2矩形の重なり面積をセル数で返す
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[2], b[2])
    y1 = min(a[3], b[3])

    if x1 <= x0 or y1 <= y0:
        return 0
    return (x1 - x0) * (y1 - y0)


def build_fall_zone_rect(item: Furniture) -> tuple[int, int, int, int] | None:
    # 倒壊領域の矩形を返す(家具外側にh_cellだけ伸ばした帯)
    # fall_dirがNoneのときは倒壊なしとみなす
    if item.fall_dir is None:
        return None
    
    gx, gy, gw, gd, h = item.gx, item.gy, item.gw, item.gd, item.h_cell

    if item.fall_dir == Direction.NORTH:
        return (gx, gy + gd, gx + gw, gy + gd + h)
    elif item.fall_dir == Direction.EAST:
        return (gx + gw, gy, gx + gw + h, gy + gd)
    elif item.fall_dir == Direction.SOUTH:
        return (gx, gy - h, gx + gw, gy)
    elif item.fall_dir == Direction.WEST:
        return (gx - h, gy, gx, gy + gd)
    
    return

def build_bed_head_zone_rect(bed: Furniture) -> tuple[int, int, int, int]:
    # ベッドの枕側の1セル帯を返す
    if bed.pillow_side is None:
        raise ValueError(f"{bed.name}: ベッドのpillow_sideの指定が必要です")
    
    gx, gy, gw, gd = bed.gx, bed.gy, bed.gw, bed.gd

    if bed.pillow_side == Direction.NORTH:
        return (gx, gy + gd, gx + gw, gy + gd + 1)
    if bed.pillow_side == Direction.SOUTH:
        return (gx, gy - 1, gx + gw, gy)
    if bed.pillow_side == Direction.EAST:
        return (gx + gw, gy, gx + gw + 1, gy + gd)
    if bed.pillow_side == Direction.WEST:
        return (gx - 1, gy, gx, gy + gd)
    
    raise ValueError(f"{bed.name}: pillow_sideの値が不正です")


# 旧リスク関数
def risk_v1(room: Room, items: list[Furniture]) -> float:
    #　出口線分に近い家具ほど、かつ背の高い家具ほどリスクが高い簡易モデル
    total = 0.0

    for f in items:
        cx = f.gx + f.gw / 2.0
        cy = f.gy + f.gd / 2.0

        dist = point_to_segment_dist(
            cx, cy,
            room.exit_ax, room.exit_ay,
            room.exit_bx, room.exit_by
        )

        height_factor = 0.5 + 0.5 * (f.h_m / 2.0)
        total += (1.0 / (dist + 0.2)) * height_factor

    return total

# 新リスク関数3種

def score_fall_hazard_to_bed(room: Room, items: list[Furniture]) -> tuple[float, list[str]]:
    # ルール①: 家具の倒壊域にベッドが入ると危険

    del room

    score = 0.0
    violations: list[str] = []

    beds = [f for f in items if f.furniture_type == FurnitureType.BED]

    for item in items:
        if item.furniture_type == FurnitureType.BED:
            continue

        zone = build_fall_zone_rect(item)
        if zone is None:
            continue

        for bed in beds:
            overlap = rect_intersection_area_cells(zone, rect_of(bed))
            if overlap <= 0:
                continue

            # 素点: ベース + 重なり面積
            raw = 1.0 + 0.1 * overlap
            score += raw
            violations.append(f"{item.name}の倒壊域が{bed.name}と重なっています (overlap={overlap} cells)")

    return score, violations

def score_exit_blocking_by_tall_items(room: Room, items: list[Furniture]) -> tuple[float, list[str]]:
    # ルール②: 背の高い家具(h_cell >= 5)が出口線分から2セル以内にあると危険

    score = 0.0
    violations: list[str] = []

    tall_threshold = 5
    near_exit_threshold = 2.0

    for item in items:
        if item.h_cell < tall_threshold:
            continue

        cx = item.gx + item.gw / 2.0
        cy = item.gy + item.gd / 2.0
        dist = point_to_segment_dist(
            cx,
            cy,
            room.exit_ax,
            room.exit_ay,
            room.exit_bx,
            room.exit_by,
        )

        if dist > near_exit_threshold:
            continue

        # 近いほど加点
        raw = 1.0 + (near_exit_threshold - dist)
        score += raw
        violations.append(
            f"[Rule2] {item.name} (h={item.h_cell}) が出口近傍 dist={dist:.2f}"
        )

    return score, violations

def score_tv_hazard_near_bed_head(room: Room, items: list[Furniture]) -> tuple[float, list[str]]:
    # ルール③: テレビなどの画面がベッドの枕側近くにあると危険

    del room

    score = 0.0
    violations: list[str] = []

    beds = [f for f in items if f.furniture_type == FurnitureType.BED]
    tv_items = [
        f
        for f in items
        if f.furniture_type in {FurnitureType.TV, FurnitureType.TV_STAND}
    ]

    for bed in beds:
        head_zone = build_bed_head_zone_rect(bed)

        for tv in tv_items:
            overlap = rect_intersection_area_cells(head_zone, rect_of(tv))
            if overlap <= 0:
                continue

            raw = 1.0 + 0.1 * overlap
            score += raw
            violations.append(
                f"[Rule3] {tv.name} が {bed.name} の枕側帯と重なり ({overlap} cells)"
            )

    return score, violations