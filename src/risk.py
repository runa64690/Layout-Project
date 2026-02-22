import math
from models import Room, Furniture

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def point_to_segment_dist(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    abx, aby = bx - ax, by - ay
    apx, apy = px - ax, py - ay
    denom = abx * abx + aby * aby

    if denom == 0.0:
        return math.hypot(px - ax, py - ay)
    
    t = (apx * abx + apy * aby) / denom
    t = clamp(t, 0.0, 1.0)
    cx, cy = ax + t * abx, ay + t * aby
    return math.hypot(px - cx, py - cy)

# リスク関数
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