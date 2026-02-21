from dataclasses import dataclass
import os
import math
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# --- Models ---
@dataclass
class Room:
    # 部屋のサイズ
    width: float
    height: float
    # 出口の座標
    exit_x: float
    exit_y: float

@dataclass
class Furniture:
    # 家具の名前と位置・サイズ
    name: str
    x: float
    y: float
    w: float
    d: float
    h: float

# --- Risk (v1: simple) ---
def risk_v1(room: Room, items: list[Furniture]) -> float:
    """仮リスク：出口に近い高い家具ほど危険（あとで差し替える）"""
    total = 0.0
    for f in items:
        # 家具の中心座標
        cx, cy = f.x + f.w/2, f.y + f.d/2
        # 出口からの距離
        dist = math.hypot(cx - room.exit_x, cy - room.exit_y)
        # 距離が近いほど、家具が高いほどリスクが高い
        total += (1.0 / (dist + 0.2)) * (0.5 + 0.5 * (f.h / 2.0))
    return total

# --- Visualization ---
def draw_layout(room: Room, items: list[Furniture], title: str, save_path: str):
    fig, ax = plt.subplots()
    ax.set_xlim(0, room.width)
    ax.set_ylim(0, room.height)
    ax.set_aspect("equal", adjustable="box")

    # room border
    ax.add_patch(patches.Rectangle((0, 0), room.width, room.height, fill=False, linewidth=2))

    # furniture rectangles
    for f in items:
        ax.add_patch(patches.Rectangle((f.x, f.y), f.w, f.d, alpha=0.4))
        ax.text(f.x + f.w/2, f.y + f.d/2, f.name, ha="center", va="center", fontsize=8)

    # exit point
    ax.plot([room.exit_x], [room.exit_y], marker="o")
    ax.text(room.exit_x, room.exit_y, "EXIT", fontsize=8, ha="left", va="bottom")

    ax.set_title(title)
    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=200)
    plt.close(fig)

def main():
    room = Room(width=3.0, height=3.0, exit_x=0.0, exit_y=1.5)

    items = [
        Furniture("Shelf", x=0.3, y=1.2, w=0.8, d=0.3, h=1.8),
        Furniture("Bed",   x=1.4, y=0.4, w=1.9, d=1.0, h=0.6),
    ]

    r = risk_v1(room, items)
    out = "outputs/before.png"
    draw_layout(room, items, title=f"Before  Risk={r:.3f}", save_path=out)
    print("Saved:", out, "Risk:", r)

if __name__ == "__main__":
    main()