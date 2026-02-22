import os
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from models import Room, Furniture

# 図の出力
def draw_layout(room: Room, items: list[Furniture], title: str, save_path: str) -> None:
    fig, ax = plt.subplots(figsize=(6, 6))

    # 部屋外枠
    ax.set_xlim(0, room.grid_w)
    ax.set_ylim(0, room.grid_h)
    ax.set_aspect("equal", adjustable="box")

    ax.add_patch(patches.Rectangle((0, 0), room.grid_w, room.grid_h, fill=False, linewidth=2))

    # グリッド線
    ax.set_xticks(range(room.grid_w + 1))
    ax.set_yticks(range(room.grid_h + 1))
    ax.grid(True, linewidth=0.5,alpha=0.4)

    # 家具の描画
    for f in items:
        ax.add_patch(patches.Rectangle((f.gx, f.gy), f.gw, f.gd, alpha=0.45))
        ax.text(
            f.gx + f.gw/2.0,
            f.gy + f.gd/2.0,
            f"{f.name}\n({f.gw}x{f.gd})",
            ha="center",
            va="center",
            fontsize=8,
        )

    #旧:出口を点で表示
    #ax.plot([room.exit_x], [room.exit_y], marker="o")

    #新:出口を線分で表示
    ax.plot(
        [room.exit_ax, room.exit_bx],
        [room.exit_ay, room.exit_by],
        color="red",
        linewidth=2.5,
    )
    ax.text(room.exit_ax, room.exit_ay, "EXIT", fontsize=8, ha="left", va="bottom")

    ax.set_title(title)
    plt.tight_layout()
    
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=200)
    plt.close(fig)