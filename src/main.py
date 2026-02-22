import os
from models import Room, Furniture, validate_layout
from risk import risk_v1
from viz import draw_layout

# メイン
def main() -> None:
    os.makedirs("outputs", exist_ok=True)

    room = Room(
        grid_w=12,
        grid_h=12,
        exit_ax=0.0,
        exit_ay=5.0,
        exit_bx=0.0,
        exit_by=7.0,
    )

    # セル数を直接指定
    before = [
        Furniture(name="Shelf", gx=1, gy=5, gw=4, gd=2, h_m=1.8),
        Furniture(name="Bed", gx=4, gy=1,gw=8, gd=4, h_m=0.6),
    ]

    validate_layout(room, before)
    r1 = risk_v1(room, before)
    draw_layout(room, before, title=f"Before　Risk={r1:3f}", save_path="outputs/before.png")

    # 棚だけ移動
    after = [
        Furniture(name="Shelf", gx=8, gy=5, gw=4, gd=2, h_m=1.8),
        Furniture(name="Bed", gx=4, gy=1,gw=8, gd=4, h_m=0.6),
    ]

    validate_layout(room, after)
    r2 = risk_v1(room, after)
    draw_layout(room, after, title=f"After　Risk={r2:3f}", save_path="outputs/after.png")

    print("Before Risk:", r1)
    print("After Risk:", r2)

if __name__ == "__main__":
    main()
