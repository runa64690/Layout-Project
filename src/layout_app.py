from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from design_models import (
    Direction,
    FURNITURE_PRESETS,
    Furniture,
    PlacedFurniture,
    Room,
    WallOpening,
    WallSide,
    build_furniture_from_placement,
    build_items_from_placements,
    clone_placements,
    get_rotated_size,
    rotate_direction,
)
from layout_cost import (
    build_door_front_rect,
    build_fall_zone_rect,
    build_window_scatter_rect,
    evaluate_layout_cost,
    total_fall_hazard_overlap_cells,
)
from mcmc_solver import LayoutSolution, MCMCSolver


class FurnitureLayoutApp:
    CELL_PX = 48
    GRID_MARGIN = 24
    RULE_LABELS = {
        "clearance_violation": "Clearance",
        "door_front_clearance_penalty": "Door front clear",
        "door_front_fall_penalty": "Door front fall",
        "window_scatter_penalty": "Window scatter",
        "circulation_penalty": "Circulation",
        "pairwise_distance_penalty": "Pairwise",
        "conversation_penalty": "Conversation",
        "visual_balance_penalty": "Balance",
        "alignment_penalty": "Wall anchor",
    }

    def __init__(self, room: Room) -> None:
        self.room = room
        self.root = tk.Tk()
        self.root.title("Furniture Layout MCMC")
        if not self.room.doors:
            self.room.doors.append(WallOpening(key="door_1", label="Door", length=2))
        if not self.room.windows:
            self.room.windows.append(WallOpening(key="window_1", label="Window", wall=WallSide.TOP, length=2))
        self.room.sync_legacy_exit_fields()
        self.placements = {
            key: PlacedFurniture(key=preset.key, label=preset.label)
            for key, preset in FURNITURE_PRESETS.items()
        }
        self.selected_key: str | None = None
        self.selected_opening: tuple[str, int] | None = None
        self.hover_key: str | None = None
        self.dragging_key: str | None = None
        self.drag_origin: tuple[int | None, int | None, int] | None = None
        self.drag_hover_cell: tuple[int, int] | None = None
        self.candidates: list[LayoutSolution] = []
        self.solver = MCMCSolver()
        self.show_hazard_zones = tk.BooleanVar(value=True)
        self.furniture_colors = {
            "shelf": "#c97b63",
            "bed": "#7aa6c2",
            "table": "#9b8f7a",
            "tv_unit": "#6c7a89",
            "chair": "#8c6bb1",
        }
        self.opening_colors = {"door": "#cc2936", "window": "#1d4ed8"}

        self.build_widgets()
        self.draw_grid()
        self.draw_palette()
        self.draw_furniture()
        self.set_result_text("Select furniture or an opening from the left, then click the room to place it.")

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
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Motion>", self.on_canvas_hover)
        self.canvas.bind("<Leave>", self.on_canvas_leave)

        self.side_frame = tk.Frame(self.root, padx=12, pady=12)
        self.side_frame.grid(row=0, column=2, sticky="nsew")
        self.side_frame.columnconfigure(0, weight=1)

        self.rotate_button = tk.Button(self.side_frame, text="Rotate", state="disabled", command=self.rotate_selected)
        self.rotate_button.grid(row=0, column=0, sticky="ew")

        self.evaluate_button = tk.Button(self.side_frame, text="Evaluate", command=self.evaluate_current_layout)
        self.evaluate_button.grid(row=1, column=0, sticky="ew", pady=(8, 0))

        self.generate_button = tk.Button(
            self.side_frame,
            text="Generate Suggestions",
            command=self.generate_suggestions,
        )
        self.generate_button.grid(row=2, column=0, sticky="ew", pady=(8, 12))

        self.hazard_zone_toggle = tk.Checkbutton(
            self.side_frame,
            text="Show hazard zones",
            variable=self.show_hazard_zones,
            command=self.draw_furniture,
        )
        self.hazard_zone_toggle.grid(row=3, column=0, sticky="w", pady=(2, 12))

        tk.Label(self.side_frame, text="Suggestions", anchor="w").grid(row=4, column=0, sticky="ew")

        self.candidate_frame = tk.Frame(self.side_frame, bd=1, relief="solid", padx=6, pady=6)
        self.candidate_frame.grid(row=5, column=0, sticky="ew")

        tk.Label(self.side_frame, text="Score", anchor="w").grid(row=6, column=0, sticky="ew", pady=(12, 0))
        self.result_label = tk.Text(
            self.side_frame,
            width=38,
            height=18,
            bg="#f3f3f3",
            relief="solid",
            padx=8,
            pady=8,
            wrap="word",
            borderwidth=1,
        )
        self.result_label.grid(row=7, column=0, sticky="nsew")
        self.side_frame.rowconfigure(7, weight=1)

    def set_result_text(self, text: str) -> None:
        self.result_label.config(state="normal")
        self.result_label.delete("1.0", tk.END)
        self.result_label.insert("1.0", text)
        self.result_label.config(state="disabled")

    def draw_grid(self) -> None:
        self.canvas.delete("grid")
        x0 = self.GRID_MARGIN
        y0 = self.GRID_MARGIN
        width = self.room.grid_w * self.CELL_PX
        height = self.room.grid_h * self.CELL_PX
        self.canvas.create_rectangle(x0, y0, x0 + width, y0 + height, tags="grid")

        for col in range(self.room.grid_w + 1):
            x = x0 + col * self.CELL_PX
            self.canvas.create_line(x, y0, x, y0 + height, fill="#cccccc", tags="grid")
        for row in range(self.room.grid_h + 1):
            y = y0 + row * self.CELL_PX
            self.canvas.create_line(x0, y, x0 + width, y, fill="#cccccc", tags="grid")
        self._draw_openings("door", self.room.doors, "DOOR")
        self._draw_openings("window", self.room.windows, "WINDOW")

    def draw_palette(self) -> None:
        for child in self.palette_frame.winfo_children():
            child.destroy()

        tk.Label(self.palette_frame, text="Furniture").pack(anchor="w", pady=(0, 8))
        for key, placement in self.placements.items():
            state = "placed" if placement.placed else "unplaced"
            button = tk.Button(
                self.palette_frame,
                text=f"{placement.label} ({state})",
                anchor="w",
                command=lambda value=key: self.select_furniture(value),
            )
            button.pack(fill="x", pady=4)

        tk.Label(self.palette_frame, text="Openings").pack(anchor="w", pady=(12, 8))
        for index, door in enumerate(self.room.doors):
            self._add_opening_button("door", index, door)
        for index, window in enumerate(self.room.windows):
            self._add_opening_button("window", index, window)

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

    def draw_furniture(self) -> None:
        self.canvas.delete("furniture")
        self.canvas.delete("fall_zone")
        self.canvas.delete("window_zone")
        self.canvas.delete("door_zone")
        self.canvas.delete("preview")

        if self.show_hazard_zones.get():
            self.draw_door_front_zones()
            self.draw_window_zones()

        for key, placement in self.placements.items():
            if not placement.placed or placement.gx is None or placement.gy is None:
                continue

            item = build_furniture_from_placement(key, placement)
            x0, y0, x1, y1 = self.rect_to_canvas(item.gx, item.gy, item.gw, item.gd)

            fall_zone = build_fall_zone_rect(item)
            if self.show_hazard_zones.get() and fall_zone is not None:
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
            width = 3 if key == self.selected_key else 1
            if key == self.hover_key:
                width = max(width, 2)
            self.canvas.create_rectangle(
                x0,
                y0,
                x1,
                y1,
                fill=color,
                outline="#222222",
                width=width,
                tags=("furniture", f"furniture:{key}"),
            )
            self.canvas.create_text(
                (x0 + x1) / 2,
                (y0 + y1) / 2,
                text=f"{placement.label}\nR{placement.rotation * 90}",
                tags=("furniture",),
            )

            if key == "bed":
                pillow_side = rotate_direction(FURNITURE_PRESETS[key].pillow_side, placement.rotation)
                if pillow_side is not None:
                    hx0, hy0, hx1, hy1 = self.create_bed_head_marker(x0, y0, x1, y1, pillow_side)
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
        if self.canvas.find_withtag("window_zone") and self.canvas.find_withtag("furniture"):
            self.canvas.tag_lower("window_zone", "furniture")
        if self.canvas.find_withtag("door_zone") and self.canvas.find_withtag("furniture"):
            self.canvas.tag_lower("door_zone", "furniture")
        self.draw_drag_preview()

    def _draw_openings(self, kind: str, openings: list[WallOpening], label: str) -> None:
        for index, opening in enumerate(openings):
            if not opening.placed:
                continue
            x0, y0, x1, y1 = self.opening_to_canvas(opening)
            width = 6 if self.selected_opening == (kind, index) else 4
            color = self.opening_colors[kind]
            self.canvas.create_line(x0, y0, x1, y1, fill=color, width=width, tags=("grid", f"opening:{kind}:{index}"))
            self.canvas.create_text((x0 + x1) / 2, (y0 + y1) / 2 - 10, text=label, fill=color, tags="grid")

    def draw_window_zones(self) -> None:
        for window in self.room.windows:
            scatter_zone = build_window_scatter_rect(self.room, window)
            if scatter_zone is None:
                continue
            x0, y0, x1, y1 = self.rect_to_canvas(
                scatter_zone[0],
                scatter_zone[1],
                scatter_zone[2] - scatter_zone[0],
                scatter_zone[3] - scatter_zone[1],
            )
            self.canvas.create_rectangle(
                x0,
                y0,
                x1,
                y1,
                fill="#dbeafe",
                outline="#2563eb",
                width=2,
                dash=(4, 3),
                tags=("window_zone",),
            )

    def draw_door_front_zones(self) -> None:
        for door in self.room.doors:
            front_zone = build_door_front_rect(self.room, door)
            if front_zone is None:
                continue
            x0, y0, x1, y1 = self.rect_to_canvas(
                front_zone[0],
                front_zone[1],
                front_zone[2] - front_zone[0],
                front_zone[3] - front_zone[1],
            )
            self.canvas.create_rectangle(
                x0,
                y0,
                x1,
                y1,
                fill="#fee2e2",
                outline="#dc2626",
                width=2,
                dash=(5, 4),
                tags=("door_zone",),
            )

    def _add_opening_button(self, kind: str, index: int, opening: WallOpening) -> None:
        state = "placed" if opening.placed else "unplaced"
        button = tk.Button(
            self.palette_frame,
            text=f"{opening.label} ({state})",
            anchor="w",
            command=lambda value=(kind, index): self.select_opening(*value),
        )
        button.pack(fill="x", pady=4)

    def opening_to_canvas(self, opening: WallOpening) -> tuple[int, int, int, int]:
        ax, ay, bx, by = self.room.opening_segment(opening)
        left = self.GRID_MARGIN
        top = self.GRID_MARGIN
        x0 = left + ax * self.CELL_PX
        x1 = left + bx * self.CELL_PX
        y0 = top + (self.room.grid_h - ay) * self.CELL_PX
        y1 = top + (self.room.grid_h - by) * self.CELL_PX
        return int(x0), int(y0), int(x1), int(y1)

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
        return (x0, y0, min(x0 + marker_depth, x1), y1)

    def find_furniture_at(self, gx: int, gy: int) -> str | None:
        for key, placement in reversed(list(self.placements.items())):
            if not placement.placed or placement.gx is None or placement.gy is None:
                continue
            preset = FURNITURE_PRESETS[key]
            gw, gd = get_rotated_size(preset.gw, preset.gd, placement.rotation)
            if placement.gx <= gx < placement.gx + gw and placement.gy <= gy < placement.gy + gd:
                return key
        return None

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
        return not (ax + aw <= bx or bx + bw <= ax or ay + ad <= by or by + bd <= ay)

    def can_place_furniture(self, key: str, gx: int, gy: int, ignore_key: str | None = None) -> bool:
        preset = FURNITURE_PRESETS[key]
        gw, gd = get_rotated_size(preset.gw, preset.gd, self.placements[key].rotation)
        if gx < 0 or gy < 0 or gx + gw > self.room.grid_w or gy + gd > self.room.grid_h:
            return False
        for anchor_x, anchor_y in self.room.door_anchor_cells():
            if gx <= anchor_x < gx + gw and gy <= anchor_y < gy + gd:
                return False
        for door in self.room.doors:
            front_rect = build_door_front_rect(self.room, door)
            if front_rect is None:
                continue
            if self.rects_overlap(gx, gy, gw, gd, front_rect[0], front_rect[1], front_rect[2] - front_rect[0], front_rect[3] - front_rect[1]):
                return False
        for other_key, other in self.placements.items():
            if other_key == key or other_key == ignore_key or not other.placed or other.gx is None or other.gy is None:
                continue
            other_preset = FURNITURE_PRESETS[other_key]
            other_gw, other_gd = get_rotated_size(other_preset.gw, other_preset.gd, other.rotation)
            if self.rects_overlap(gx, gy, gw, gd, other.gx, other.gy, other_gw, other_gd):
                return False
        return True

    def draw_drag_preview(self) -> None:
        if self.dragging_key is None or self.drag_hover_cell is None:
            return
        gx, gy = self.drag_hover_cell
        preset = FURNITURE_PRESETS[self.dragging_key]
        gw, gd = get_rotated_size(preset.gw, preset.gd, self.placements[self.dragging_key].rotation)
        x0, y0, x1, y1 = self.rect_to_canvas(gx, gy, gw, gd)
        allowed = self.can_place_furniture(self.dragging_key, gx, gy, ignore_key=self.dragging_key)
        outline = "#15803d" if allowed else "#b91c1c"
        fill = "#bbf7d0" if allowed else "#fecaca"
        self.canvas.create_rectangle(
            x0,
            y0,
            x1,
            y1,
            fill=fill,
            outline=outline,
            width=2,
            dash=(4, 3),
            stipple="gray25",
            tags=("preview",),
        )

    def on_canvas_click(self, event: tk.Event) -> None:
        cell = self.canvas_to_grid(event.x, event.y)
        if cell is None:
            self.clear_selection()
            return
        gx, gy = cell
        clicked = self.find_furniture_at(gx, gy)
        if clicked is not None:
            self.select_furniture(clicked)
            placement = self.placements[clicked]
            self.dragging_key = clicked
            self.drag_origin = (placement.gx, placement.gy, placement.rotation)
            self.drag_hover_cell = (gx, gy)
            self.draw_furniture()
            return
        if self.selected_opening is not None:
            kind, index = self.selected_opening
            if not self.place_opening(kind, index, gx, gy):
                messagebox.showwarning("Placement error", "Openings must fit on a wall and cannot overlap.")
                return
            self.draw_grid()
            self.draw_palette()
            self.set_result_text("Opening updated. Click another wall cell to move it, or place furniture.")
            return
        if self.selected_key is None:
            return
        if not self.can_place_furniture(self.selected_key, gx, gy):
            messagebox.showwarning("Placement error", "That cell is blocked or out of bounds.")
            return
        placement = self.placements[self.selected_key]
        placement.gx = gx
        placement.gy = gy
        placement.placed = True
        self.draw_palette()
        self.draw_furniture()
        self.set_result_text("Placement updated. Evaluate or generate new suggestions.")

    def on_canvas_drag(self, event: tk.Event) -> None:
        if self.dragging_key is None:
            return
        cell = self.canvas_to_grid(event.x, event.y)
        self.drag_hover_cell = cell
        self.draw_furniture()

    def on_canvas_release(self, event: tk.Event) -> None:
        if self.dragging_key is None:
            return
        key = self.dragging_key
        cell = self.canvas_to_grid(event.x, event.y)
        placement = self.placements[key]
        if cell is not None:
            gx, gy = cell
            if self.can_place_furniture(key, gx, gy, ignore_key=key):
                placement.gx = gx
                placement.gy = gy
                placement.placed = True
                self.set_result_text("Placement updated. Evaluate or generate new suggestions.")
            elif self.drag_origin is not None:
                placement.gx, placement.gy, placement.rotation = self.drag_origin
                placement.placed = placement.gx is not None and placement.gy is not None
                messagebox.showwarning("Placement error", "That cell is blocked or out of bounds.")
        elif self.drag_origin is not None:
            placement.gx, placement.gy, placement.rotation = self.drag_origin
            placement.placed = placement.gx is not None and placement.gy is not None
        self.dragging_key = None
        self.drag_origin = None
        self.drag_hover_cell = None
        self.draw_palette()
        self.draw_furniture()

    def on_canvas_hover(self, event: tk.Event) -> None:
        cell = self.canvas_to_grid(event.x, event.y)
        hover_key = None
        if cell is not None:
            hover_key = self.find_furniture_at(*cell)
        if hover_key != self.hover_key:
            self.hover_key = hover_key
            self.draw_furniture()

    def on_canvas_leave(self, event: tk.Event) -> None:
        del event
        changed = self.hover_key is not None
        self.hover_key = None
        if changed:
            self.draw_furniture()

    def select_furniture(self, key: str) -> None:
        self.selected_key = key
        self.selected_opening = None
        self.rotate_button.config(state="normal")
        self.draw_furniture()
        self.draw_grid()

    def select_opening(self, kind: str, index: int) -> None:
        self.selected_opening = (kind, index)
        self.selected_key = None
        self.rotate_button.config(state="disabled")
        self.draw_furniture()
        self.draw_grid()

    def clear_selection(self) -> None:
        self.selected_key = None
        self.selected_opening = None
        self.dragging_key = None
        self.drag_origin = None
        self.drag_hover_cell = None
        self.rotate_button.config(state="disabled")
        self.draw_furniture()
        self.draw_grid()

    def rotate_selected(self) -> None:
        if self.selected_key is None:
            return
        placement = self.placements[self.selected_key]
        old_rotation = placement.rotation
        placement.rotation = (placement.rotation + 1) % 4
        if placement.placed and placement.gx is not None and placement.gy is not None:
            if not self.can_place_furniture(self.selected_key, placement.gx, placement.gy):
                placement.rotation = old_rotation
                messagebox.showwarning("Rotate error", "Rotation would cause overlap or leave the room.")
                return
        self.draw_furniture()
        self.set_result_text("Rotation updated. Evaluate or generate new suggestions.")

    def place_opening(self, kind: str, index: int, gx: int, gy: int) -> bool:
        opening = self.room.doors[index] if kind == "door" else self.room.windows[index]
        old_state = (opening.wall, opening.offset, opening.length, opening.placed)
        wall = self.nearest_wall(gx, gy)
        limit = self.room.grid_h if wall in {WallSide.LEFT, WallSide.RIGHT} else self.room.grid_w
        offset_basis = gy if wall in {WallSide.LEFT, WallSide.RIGHT} else gx
        opening.wall = wall
        opening.offset = max(0, min(limit - opening.length, offset_basis))
        opening.placed = True
        if self.openings_overlap(kind, index) or (kind == "door" and self.is_door_blocked()):
            opening.wall, opening.offset, opening.length, opening.placed = old_state
            return False
        self.room.sync_legacy_exit_fields()
        return True

    def nearest_wall(self, gx: int, gy: int) -> WallSide:
        distances = {
            WallSide.LEFT: gx,
            WallSide.RIGHT: self.room.grid_w - 1 - gx,
            WallSide.BOTTOM: gy,
            WallSide.TOP: self.room.grid_h - 1 - gy,
        }
        return min(distances, key=distances.get)

    def openings_overlap(self, kind: str, index: int) -> bool:
        opening = self.room.doors[index] if kind == "door" else self.room.windows[index]
        try:
            self.room.validate_opening(opening)
        except ValueError:
            return True
        candidates = [("door", i, value) for i, value in enumerate(self.room.doors)] + [
            ("window", i, value) for i, value in enumerate(self.room.windows)
        ]
        for other_kind, other_index, other in candidates:
            if (other_kind, other_index) == (kind, index) or not other.placed:
                continue
            if opening.wall != other.wall:
                continue
            opening_end = opening.offset + opening.length
            other_end = other.offset + other.length
            if max(opening.offset, other.offset) < min(opening_end, other_end):
                return True
        return False

    def is_door_blocked(self) -> bool:
        for anchor_x, anchor_y in self.room.door_anchor_cells():
            if self.find_furniture_at(anchor_x, anchor_y) is not None:
                return True
        return False

    def evaluate_current_layout(self) -> None:
        missing = [placement.label for placement in self.placements.values() if not placement.placed]
        if missing:
            self.set_result_text("Missing furniture: " + ", ".join(missing))
            return

        try:
            items = build_items_from_placements(self.placements)
            score = evaluate_layout_cost(self.room, items)
            fall_overlap = total_fall_hazard_overlap_cells(items)
        except ValueError as exc:
            self.set_result_text(f"Layout error: {exc}")
            return

        lines = [f"Total cost: {score.total:.3f}", ""]
        lines.append("Breakdown:")
        for name, value in score.breakdown.items():
            label = self.RULE_LABELS.get(name, name)
            lines.append(f"- {label}: {value:.3f}")
        lines.append(f"- Fall overlap cells: {fall_overlap}")
        lines.append("")
        if score.violations:
            lines.append("Violations:")
            lines.extend(f"- {message}" for message in score.violations[:10])
        else:
            lines.append("Violations: none")
        self.set_result_text("\n".join(lines))

    def generate_suggestions(self) -> None:
        fixed_keys = {key for key, placement in self.placements.items() if placement.placed}
        if len(fixed_keys) == len(self.placements):
            fixed_keys = set()
        self.set_result_text("Running MCMC search...")
        self.root.update_idletasks()
        self.candidates = self.solver.generate_layout_candidates(
            self.room,
            self.placements,
            fixed_keys=fixed_keys,
            candidate_count=3,
            sample_count=900,
            burn_in=250,
            sample_stride=15,
        )
        self.render_candidates()
        if not self.candidates:
            self.set_result_text("No suggestions generated.")
            return
        best = self.candidates[0]
        self.set_result_text(
            "Generated suggestions.\n"
            f"Best cost: {best.cost:.3f}\n"
            f"Accepted steps: {best.accepted_steps}\n"
            "Choose a candidate to apply it."
        )

    def render_candidates(self) -> None:
        for child in self.candidate_frame.winfo_children():
            child.destroy()

        if not self.candidates:
            tk.Label(self.candidate_frame, text="No suggestions yet.").pack(anchor="w")
            return

        for index, candidate in enumerate(self.candidates, start=1):
            button = tk.Button(
                self.candidate_frame,
                text=f"Candidate {index}  cost={candidate.cost:.2f}",
                anchor="w",
                command=lambda value=index - 1: self.apply_candidate(value),
            )
            button.pack(fill="x", pady=3)

    def apply_candidate(self, index: int) -> None:
        candidate = self.candidates[index]
        self.placements = clone_placements(candidate.placements)
        self.draw_palette()
        self.draw_furniture()
        self.evaluate_current_layout()

    def run(self) -> None:
        self.root.mainloop()
