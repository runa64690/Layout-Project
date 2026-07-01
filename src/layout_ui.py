from layout_app import FurnitureLayoutApp
"""

import tkinter as tk
from tkinter import messagebox

from models import (
    Direction,
    Furniture,
    Room,
    FURNITURE_PRESETS,
    PlacedFurniture,
    get_rotated_size,
    rotate_direction,
    validate_layout,
)
from risk import (
    build_fall_zone_rect,
    evaluate_layout_risk,
    total_fall_hazard_overlap_cells,
)


class FurnitureLayoutApp:
    CELL_PX = 48
    GRID_MARGIN = 24
    RULE_LABELS = {
        "fall_hazard_to_bed": "倒壊領域とベッドの重なり",
        "exit_blocking_by_tall_items": "高家具による出口阻害",
        "tv_fall_zone_near_bed_head": "テレビ倒壊領域とベッド頭側の重なり",
    }

    def __init__(self, room: Room) -> None:
        self.room = room
        self.root = tk.Tk()
        self.root.title("家具配置UI")

        self.placements = {
            key: PlacedFurniture(key=preset.key, label=preset.label)
            for key, preset in FURNITURE_PRESETS.items()
        }
        self.selected_key: str | None = None
        self.result_text = "家具を配置して「決定」を押すと結果を表示します。"
        self.furniture_colors = {
            "shelf": "#c97b63",
            "bed": "#7aa6c2",
            "table": "#9b8f7a",
            "tv_unit": "#6c7a89",
            "chair": "#8c6bb1",
        }

        self.build_widgets()
        self.draw_grid()
        self.draw_palette()
        self.draw_furniture()

    def build_widgets(self) -> None:
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.palette_frame = tk.Frame(self.root, padx=12, pady=12)
        self.palette_frame.grid(row=0, column=0, sticky="ns")

        self.canvas = tk.Canvas(
            self.root,
            width=self.room.grid_w * self.CELL_PX + self.GRID_MARGIN * 2,
            height=self.room.grid_h * self.CELL_PX + self.GRID_MARGIN * 2,
            bg="white",
        )
        self.canvas.grid(row=0, column=1, sticky="nsew")

        self.side_frame = tk.Frame(self.root, padx=12, pady=12)
        self.side_frame.grid(row=0, column=2, sticky="ns")

        self.rotate_button = tk.Button(
            self.side_frame,
            text="回転",
            state="disabled",
            command=self.rotate_selected,
        )
        self.rotate_button.pack(fill="x")

        self.finalize_button = tk.Button(
            self.side_frame,
            text="決定",
            command=self.finalize_layout,
        )
        self.finalize_button.pack(fill="x", pady=(0, 12))

        tk.Label(self.side_frame, text="結果", anchor="w").pack(fill="x")

        self.result_label = tk.Text(
            self.side_frame,
            width=36,
            height=22,
            bg="#f3f3f3",
            relief="solid",
            padx=8,
            pady=8,
            wrap="word",
            borderwidth=1,
        )
        self.result_label.pack(fill="both", expand=True)
        self.result_label.insert("1.0", self.result_text)
        self.result_label.config(state="disabled")
        self.canvas.bind("<Button-1>", self.on_canvas_click)

    def set_result_text(self, text: str) -> None:
        self.result_text = text
        self.result_label.config(state="normal")
        self.result_label.delete("1.0", tk.END)
        self.result_label.insert("1.0", text)
        self.result_label.config(state="disabled")

    def draw_grid(self) -> None:
        self.canvas.delete("grid")

        x0 = self.GRID_MARGIN
        y0 = self.GRID_MARGIN
        w = self.room.grid_w * self.CELL_PX
        h = self.room.grid_h * self.CELL_PX

        self.canvas.create_rectangle(x0, y0, x0 + w, y0 + h, tags="grid")

        for col in range(self.room.grid_w + 1):
            x = x0 + col * self.CELL_PX
            self.canvas.create_line(x, y0, x, y0 + h, fill="#cccccc", tags="grid")

        for row in range(self.room.grid_h + 1):
            y = y0 + row * self.CELL_PX
            self.canvas.create_line(x0, y, x0 + w, y, fill="#cccccc", tags="grid")

        exit_y0 = y0 + (self.room.grid_h - self.room.exit_by) * self.CELL_PX
        exit_y1 = y0 + (self.room.grid_h - self.room.exit_ay) * self.CELL_PX
        self.canvas.create_line(x0, exit_y0, x0, exit_y1, fill="red", width=4, tags="grid")
        self.canvas.create_text(x0 + 24, exit_y0 - 10, text="EXIT", fill="red", tags="grid")

    def grid_to_canvas(self, gx: int, gy: int) -> tuple[int, int]:
        x = self.GRID_MARGIN + gx * self.CELL_PX
        y = self.GRID_MARGIN + (self.room.grid_h - gy - 1) * self.CELL_PX
        return x, y

    def rect_to_canvas(self, gx: int, gy: int, gw: int, gd: int) -> tuple[int, int, int, int]:
        x0, y_bottom = self.grid_to_canvas(gx, gy)
        x1 = x0 + gw * self.CELL_PX
        y1 = y_bottom + self.CELL_PX
        y0 = y1 - gd * self.CELL_PX
        return x0, y0, x1, y1

    def canvas_to_grid(self, x: int, y: int) -> tuple[int, int] | None:
        left = self.GRID_MARGIN
        top = self.GRID_MARGIN
        right = left + self.room.grid_w * self.CELL_PX
        bottom = top + self.room.grid_h * self.CELL_PX

        if x < left or x >= right or y < top or y >= bottom:
            return None

        gx = (x - left) // self.CELL_PX
        gy_from_top = (y - top) // self.CELL_PX
        gy = self.room.grid_h - 1 - gy_from_top
        return int(gx), int(gy)

    def find_furniture_at(self, gx: int, gy: int) -> str | None:
        for key, placement in reversed(list(self.placements.items())):
            if not placement.placed or placement.gx is None or placement.gy is None:
                continue

            preset = FURNITURE_PRESETS[key]
            gw, gd = get_rotated_size(preset.gw, preset.gd, placement.rotation)
            if placement.gx <= gx < placement.gx + gw and placement.gy <= gy < placement.gy + gd:
                return key

        return None

    def draw_palette(self) -> None:
        for child in self.palette_frame.winfo_children():
            child.destroy()

        tk.Label(self.palette_frame, text="家具一覧").pack(anchor="w", pady=(0, 8))

        for key, placement in self.placements.items():
            state_text = "未配置" if not placement.placed else "配置済み"
            button = tk.Button(
                self.palette_frame,
                text=f"{placement.label} ({state_text})",
                anchor="w",
                command=lambda value=key: self.select_furniture(value),
            )
            button.pack(fill="x", pady=4)

    def create_bed_head_marker(
        self,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        pillow_side: Direction,
    ) -> tuple[int, int, int, int]:
        marker_depth = min(2 * self.CELL_PX, x1 - x0, y1 - y0)

        if pillow_side == Direction.NORTH:
            return (x0, y0, x1, min(y0 + marker_depth, y1))
        if pillow_side == Direction.SOUTH:
            return (x0, max(y1 - marker_depth, y0), x1, y1)
        if pillow_side == Direction.EAST:
            return (max(x1 - marker_depth, x0), y0, x1, y1)
        if pillow_side == Direction.WEST:
            return (x0, y0, min(x0 + marker_depth, x1), y1)

        raise ValueError(f"invalid pillow_side: {pillow_side}")

    def draw_furniture(self) -> None:
        self.canvas.delete("furniture")
        self.canvas.delete("fall_zone")

        for key, placement in self.placements.items():
            if not placement.placed or placement.gx is None or placement.gy is None:
                continue

            preset = FURNITURE_PRESETS[key]
            gw, gd = get_rotated_size(preset.gw, preset.gd, placement.rotation)
            fall_dir = rotate_direction(preset.fall_dir, placement.rotation)
            x0, y0, x1, y1 = self.rect_to_canvas(placement.gx, placement.gy, gw, gd)

            if fall_dir is not None:
                risk_item = Furniture(
                    name=placement.label,
                    gx=placement.gx,
                    gy=placement.gy,
                    gw=gw,
                    gd=gd,
                    h_cell=preset.h_cell,
                    furniture_type=preset.furniture_type,
                    fall_dir=fall_dir,
                )
                fall_zone = build_fall_zone_rect(risk_item)
                if fall_zone is not None:
                    fx0, fy0, fx1, fy1 = self.rect_to_canvas(
                        fall_zone[0],
                        fall_zone[1],
                        fall_zone[2] - fall_zone[0],
                        fall_zone[3] - fall_zone[1],
                    )
                    self.canvas.create_rectangle(
                        fx0,
                        fy0,
                        fx1,
                        fy1,
                        fill="#f8d8b8",
                        outline="#d97706",
                        width=2,
                        dash=(6, 4),
                        tags=("fall_zone",),
                    )

            color = self.furniture_colors.get(key, "#aaaaaa")
            outline = "#222222"
            width = 3 if key == self.selected_key else 1

            self.canvas.create_rectangle(
                x0,
                y0,
                x1,
                y1,
                fill=color,
                outline=outline,
                width=width,
                tags=("furniture", f"furniture:{key}"),
            )
            self.canvas.create_text(
                (x0 + x1) / 2,
                (y0 + y1) / 2,
                text=f"{placement.label}\nR{placement.rotation * 90}\nH{preset.h_cell}",
                tags=("furniture",),
            )

            if key == "bed":
                pillow_side = rotate_direction(preset.pillow_side, placement.rotation)
                if pillow_side is None:
                    raise ValueError("bed must have pillow_side")

                hx0, hy0, hx1, hy1 = self.create_bed_head_marker(
                    x0,
                    y0,
                    x1,
                    y1,
                    pillow_side,
                )
                self.canvas.create_rectangle(
                    hx0,
                    hy0,
                    hx1,
                    hy1,
                    fill="#eaf3ff",
                    outline="#1f4e79",
                    width=2,
                    tags=("furniture",),
                )

        if self.canvas.find_withtag("fall_zone") and self.canvas.find_withtag("furniture"):
            self.canvas.tag_lower("fall_zone", "furniture")

    def on_canvas_click(self, event: tk.Event) -> None:
        cell = self.canvas_to_grid(event.x, event.y)
        if cell is None:
            self.clear_selection()
            return

        gx, gy = cell
        clicked_key = self.find_furniture_at(gx, gy)
        if clicked_key is not None:
            self.select_furniture(clicked_key)
            return

        if self.selected_key is None:
            return

        if not self.can_place_furniture(self.selected_key, gx, gy):
            messagebox.showwarning("配置エラー", "その位置には配置できません。")
            return

        placement = self.placements[self.selected_key]
        placement.gx = gx
        placement.gy = gy
        placement.placed = True

        self.draw_palette()
        self.draw_furniture()
        self.invalidate_result()

    def invalidate_result(self) -> None:
        self.set_result_text("配置が更新されました。結果を更新するには「決定」を押してください。")

    def rects_overlap(
        self,
        ax: int,
        ay: int,
        aw: int,
        ad: int,
        bx: int,
        by: int,
        bw: int,
        bd: int,
    ) -> bool:
        return not (
            ax + aw <= bx or
            bx + bw <= ax or
            ay + ad <= by or
            by + bd <= ay
        )

    def can_place_furniture(self, key: str, gx: int, gy: int) -> bool:
        preset = FURNITURE_PRESETS[key]
        gw, gd = get_rotated_size(preset.gw, preset.gd, self.placements[key].rotation)

        if gx < 0 or gy < 0:
            return False
        if gx + gw > self.room.grid_w:
            return False
        if gy + gd > self.room.grid_h:
            return False

        for other_key, other in self.placements.items():
            if other_key == key:
                continue
            if not other.placed or other.gx is None or other.gy is None:
                continue

            other_preset = FURNITURE_PRESETS[other_key]
            other_gw, other_gd = get_rotated_size(
                other_preset.gw,
                other_preset.gd,
                other.rotation,
            )

            if self.rects_overlap(gx, gy, gw, gd, other.gx, other.gy, other_gw, other_gd):
                return False

        return True

    def rotate_selected(self) -> None:
        if self.selected_key is None:
            return

        placement = self.placements[self.selected_key]
        old_rotation = placement.rotation
        placement.rotation = (placement.rotation + 1) % 4

        if placement.placed and placement.gx is not None and placement.gy is not None:
            if not self.can_place_furniture(self.selected_key, placement.gx, placement.gy):
                placement.rotation = old_rotation
                messagebox.showwarning(
                    "回転エラー",
                    "回転すると家具が部屋外にはみ出すか、他の家具と重なります。",
                )
                return

        self.draw_furniture()
        self.invalidate_result()

    def get_missing_furniture_labels(self) -> list[str]:
        return [
            placement.label
            for placement in self.placements.values()
            if not placement.placed
        ]

    def build_risk_items(self) -> list[Furniture]:
        items: list[Furniture] = []

        for key, placement in self.placements.items():
            if not placement.placed or placement.gx is None or placement.gy is None:
                continue

            preset = FURNITURE_PRESETS[key]
            gw, gd = get_rotated_size(preset.gw, preset.gd, placement.rotation)
            items.append(
                Furniture(
                    name=placement.label,
                    gx=placement.gx,
                    gy=placement.gy,
                    gw=gw,
                    gd=gd,
                    h_cell=preset.h_cell,
                    furniture_type=preset.furniture_type,
                    fall_dir=rotate_direction(preset.fall_dir, placement.rotation),
                    pillow_side=rotate_direction(preset.pillow_side, placement.rotation),
                )
            )

        return items

    def select_furniture(self, key: str) -> None:
        self.selected_key = key
        self.rotate_button.config(state="normal")
        self.draw_furniture()

    def clear_selection(self) -> None:
        self.selected_key = None
        self.rotate_button.config(state="disabled")
        self.draw_furniture()

    def finalize_layout(self) -> None:
        missing = self.get_missing_furniture_labels()
        if missing:
            self.set_result_text("未配置の家具があります: " + ", ".join(missing))
            return

        try:
            items = self.build_risk_items()
            validate_layout(self.room, items)
            result = evaluate_layout_risk(self.room, items)
            fall_overlap_cells = total_fall_hazard_overlap_cells(items)
        except ValueError as exc:
            self.set_result_text(f"レイアウトエラー: {exc}")
            return

        lines = [f"総合危険度: {result['total']:.3f}", ""]
        lines.append("詳細:")
        for name, score in result["breakdown"].items():
            label = self.RULE_LABELS.get(name, name)
            lines.append(f"- {label}: {score:.3f}")
        lines.append(f"- 倒壊領域とベッドの重なりセル数: {fall_overlap_cells}")

        lines.append("")
        if result["violations"]:
            lines.append("検出ルール:")
            lines.extend(f"- {msg}" for msg in result["violations"])
        else:
            lines.append("検出ルール: なし")

        self.set_result_text("\n".join(lines))

    def run(self) -> None:
        self.root.mainloop()
"""
