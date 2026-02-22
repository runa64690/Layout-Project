import os
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from models import Room, Furniture

# 図の出力
def draw_layout(room: Room, items: list[Furniture], title: str, save_path: str):
    fig, ax = plt.subplots()
    ax.set_xlim(0, room.width)
    ax.set_ylim(0, room.height)
    ax.set_aspect("equal", adjustable="box")

    ax.add_patch(patches.Rectangle((0, 0), room.width, room.height, fill=False, linewidth=2))

    for f in items:
        ax.add_patch(patches.Rectangle((f.x, f.y), f.w, f.d, alpha=0.4))
        ax.text(f.x + f.w/2, f.y + f.d/2, f.name, ha="center", va="center", fontsize=8)

    #旧:出口を点で表示
    #ax.plot([room.exit_x], [room.exit_y], marker="o")

    #新:出口を線分で表示
    ax.plot([room.exit_ax, room.exit_bx], [room.exit_ay, room.exit_by],color="red", linewidth=2)
    ax.text(room.exit_ax, room.exit_ay, "EXIT", fontsize=8, ha="left", va="bottom")

    ax.set_title(title)
    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=200)
    plt.close(fig)