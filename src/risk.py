import math
from models import Room, Furniture

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def point_to_segment_dist(px, py, ax, ay, bx, by):
    abx, aby = bx - ax, by - ay
    apx, apy = px - ax, py - ay
    denom = abx * abx + aby * aby
    if denom == 0:
        return math.hypot(px - ax, py - ay)
    t = (apx * abx + apy * aby) / denom
    t = clamp(t, 0.0, 1.0)
    cx, cy = ax + t * abx, ay + t * aby
    return math.hypot(px - cx, py - cy)

# リスク関数
def risk_v1(room: Room, items: list[Furniture]) -> float:
    total = 0.0
    for f in items:
        cx, cy = f.x + f.w/2, f.y + f.d/2

        dist = point_to_segment_dist(
            cx, cy,
            room.exit_ax, room.exit_ay,
            room.exit_bx, room.exit_by
        )

        total += (1.0 / (dist + 0.2)) * (0.5 + 0.5 * (f.h / 2.0))
    return total