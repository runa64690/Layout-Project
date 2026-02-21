import math
from models import Room, Furniture

# リスク関数
def risk_v1(room: Room, items: list[Furniture]) -> float:
    total = 0.0
    for f in items:
        cx, cy = f.x + f.w/2, f.y + f.d/2
        dist = math.hypot(cx - room.exit_x, cy - room.exit_y)
        total += (1.0 / (dist + 0.2)) * (0.5 + 0.5 * (f.h / 2.0))
    return total