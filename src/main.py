import os
from models import Direction, Room, Furniture, FurnitureType, validate_layout
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
        Furniture(
                 name="Shelf", gx=1, gy=5, gw=4, gd=2, h_cell=7,
                 furniture_type=FurnitureType.STORAGE,
                 fall_dir=Direction.EAST,
        ),
        Furniture(
                 name="Bed", gx=4, gy=1,gw=8, gd=4, h_cell=3,
                 furniture_type=FurnitureType.BED,
                 pillow_side=Direction.NORTH,
        ),
    ]

    validate_layout(room, before)

    # main.py の r1/r2 計算後に一時追加して確認
    from risk import (
        score_fall_hazard_to_bed,
        score_exit_blocking_by_tall_items,
        score_tv_hazard_near_bed_head,
    )

    s1, v1 = score_fall_hazard_to_bed(room, before)
    s2, v2 = score_exit_blocking_by_tall_items(room, before)
    s3, v3 = score_tv_hazard_near_bed_head(room, before)
    print("Rule1:", s1, v1)
    print("Rule2:", s2, v2)
    print("Rule3:", s3, v3)

    r1 = risk_v1(room, before)
    draw_layout(room, before, title=f"Before Risk={r1:.3f}", save_path="outputs/before.png")

    # 棚だけ移動
    after = [
        Furniture(
                 name="Shelf", gx=8, gy=5, gw=4, gd=2, h_cell=7,
                 furniture_type=FurnitureType.STORAGE,
                 fall_dir=Direction.EAST,
        ),
        Furniture(
                 name="Bed", gx=4, gy=1,gw=8, gd=4, h_cell=3,
                 furniture_type=FurnitureType.BED,
                 pillow_side=Direction.NORTH,
        ),
    ]

    validate_layout(room, after)
    r2 = risk_v1(room, after)
    draw_layout(room, after, title=f"After Risk={r2:.3f}", save_path="outputs/after.png")

    print("Before Risk:", r1)
    print("After Risk:", r2)

    

if __name__ == "__main__":
    main()
