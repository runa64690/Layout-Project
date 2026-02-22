import os
from models import Direction, Room, Furniture, FurnitureType, validate_layout
from risk import risk_v1, evaluate_layout_risk
from viz import draw_layout

def print_risk(label: str, result: dict) -> None:
    print(f"[{label}] total={result['total']:.3f}")
    for k, v in result["breakdown"].items():
        print(f"  - {k}: {v:.3f}")
    if result["violations"]:
        print("  - violations:")
        for msg in result["violations"]:
            print(f"    * {msg}")
    else:
        print("  - violations: none")

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
            name="Shelf",
            gx=1,
            gy=5,
            gw=4,
            gd=2,
            h_cell=7,
            furniture_type=FurnitureType.STORAGE,
            fall_dir=Direction.EAST,
        ),
        Furniture(
            name="TVStand",
            gx=6,
            gy=5,
            gw=3,
            gd=1,
            h_cell=2,
            furniture_type=FurnitureType.TV_STAND,
            fall_dir=Direction.SOUTH,
        ),
        Furniture(
            name="TV",
            gx=6,
            gy=6,
            gw=2,
            gd=1,
            h_cell=2,
            furniture_type=FurnitureType.TV,
            fall_dir=Direction.SOUTH,
        ),
        Furniture(
            name="Bed",
            gx=4,
            gy=1,
            gw=6,
            gd=4,
            h_cell=3,
            furniture_type=FurnitureType.BED,
            pillow_side=Direction.NORTH,
        ),
    ]

    
    after = [
        Furniture(
            name="Shelf",
            gx=8,
            gy=5,
            gw=4,
            gd=2,
            h_cell=7,
            furniture_type=FurnitureType.STORAGE,
            fall_dir=Direction.EAST,
        ),
        Furniture(
            name="TVStand",
            gx=1,
            gy=1,
            gw=3,
            gd=1,
            h_cell=2,
            furniture_type=FurnitureType.TV_STAND,
            fall_dir=Direction.SOUTH,
        ),
        Furniture(
            name="TV",
            gx=1,
            gy=2,
            gw=2,
            gd=1,
            h_cell=2,
            furniture_type=FurnitureType.TV,
            fall_dir=Direction.SOUTH,
        ),
        Furniture(
            name="Bed",
            gx=4,
            gy=1,
            gw=6,
            gd=4,
            h_cell=3,
            furniture_type=FurnitureType.BED,
            pillow_side=Direction.NORTH,
        ),
    ]

    validate_layout(room, before)
    validate_layout(room, after)

     # legacy score（比較用）
    legacy_before = risk_v1(room, before)
    legacy_after = risk_v1(room, after)
    print(f"[legacy] before={legacy_before:.3f}, after={legacy_after:.3f}")

    # 全てのルールを有効にしてスコアリング
    before_all = evaluate_layout_risk(room, before)
    after_all = evaluate_layout_risk(room, after)

    print_risk("before/all", before_all)
    print_risk("after/all", after_all)

    # ルール別のスコアも個別に出力
    print_risk(
        "before/rule1",
        evaluate_layout_risk(room, before, enabled_rules={"fall_hazard_to_bed"}),
    )
    print_risk(
        "before/rule2",
        evaluate_layout_risk(room, before, enabled_rules={"exit_blocking_tall_items"}),
    )
    print_risk(
        "before/rule3",
        evaluate_layout_risk(room, before, enabled_rules={"tv_hazard_near_bed_head"}),
    )

    draw_layout(
        room,
        before,
        title=f"Before Total={before_all['total']:.3f}",
        save_path="outputs/before.png",
    )
    draw_layout(
        room,
        after,
        title=f"After Total={after_all['total']:.3f}",
        save_path="outputs/after.png",
    )

    

if __name__ == "__main__":
    main()
