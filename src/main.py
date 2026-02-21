import os
from models import Room, Furniture
from risk import risk_v1
from viz import draw_layout

# メイン
def main():
    os.makedirs("outputs", exist_ok=True)

    room = Room(width=3.0, height=3.0, exit_x=0.0, exit_y=1.5)

    before = [
        Furniture("Shelf", x=0.3, y=1.2, w=0.8, d=0.3, h=1.8),
        Furniture("Bed",   x=1.4, y=0.4, w=1.9, d=1.0, h=0.6),
    ]
    r1 = risk_v1(room, before)
    draw_layout(room, before, title=f"Before  Risk={r1:.3f}", save_path="outputs/before.png")

    after = [
        Furniture("Shelf", x=2.0, y=1.2, w=0.8, d=0.3, h=1.8),
        Furniture("Bed",   x=1.4, y=0.4, w=1.9, d=1.0, h=0.6),
    ]
    r2 = risk_v1(room, after)
    draw_layout(room, after, title=f"After   Risk={r2:.3f}", save_path="outputs/after.png")

    print("Before Risk:", r1)
    print("After  Risk:", r2)

if __name__ == "__main__":
    main()