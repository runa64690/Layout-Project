import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Circle


def draw_rooms(ax, rooms):
    for room in rooms:
        floor_polygon = room.get("floorPolygon", [])
        if not floor_polygon:
            continue

        points = [(p["x"], p["z"]) for p in floor_polygon]

        patch = Polygon(
            points,
            closed=True,
            fill=False,
            linewidth=2,
        )
        ax.add_patch(patch)

        # 部屋IDを中央に表示
        cx = sum(x for x, z in points) / len(points)
        cz = sum(z for x, z in points) / len(points)
        room_id = room.get("id", "room")
        ax.text(cx, cz, room_id, ha="center", va="center", fontsize=8)


def draw_objects(ax, objects):
    for obj in objects:
        pos = obj.get("position")
        if not pos:
            continue

        x = pos.get("x", 0)
        z = pos.get("z", 0)

        asset_id = obj.get("assetId", "object")
        obj_id = obj.get("id", "")

        # まずは家具を点として描く
        circle = Circle((x, z), radius=0.08, fill=True)
        ax.add_patch(circle)

        label = asset_id
        ax.text(x, z + 0.12, label, fontsize=7, ha="center")

        # 子オブジェクトも薄く確認したい場合
        for child in obj.get("children", []):
            cpos = child.get("position")
            if not cpos:
                continue

            cx = cpos.get("x", 0)
            cz = cpos.get("z", 0)
            child_circle = Circle((cx, cz), radius=0.04, fill=False)
            ax.add_patch(child_circle)


def main():
    input_path = Path("procthor_work/outputs/sample_house_0.json")

    with input_path.open("r", encoding="utf-8") as f:
        house = json.load(f)

    rooms = house.get("rooms", [])
    objects = house.get("objects", [])

    fig, ax = plt.subplots(figsize=(10, 8))

    draw_rooms(ax, rooms)
    draw_objects(ax, objects)

    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x")
    ax.set_ylabel("z")
    ax.set_title("ProcTHOR house 0 - top view")

    ax.grid(True)

    output_path = Path("procthor_work/outputs/sample_house_0_topview.png")
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.show()

    print(f"Saved image to: {output_path}")


if __name__ == "__main__":
    main()