from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from design_models import (
    Direction,
    FURNITURE_PRESETS,
    Furniture,
    PlacedFurniture,
    Room,
    build_furniture_from_placement,
    build_items_from_placements,
    clone_placements,
    get_rotated_size,
    rotate_direction,
)
from layout_cost import (
    build_fall_zone_rect,
    evaluate_layout_cost,
    total_fall_hazard_overlap_cells,
)
from mcmc_solver import LayoutSolution, MCMCSolver


class FurnitureLayoutApp:
    CELL_PX = 48
    GRID_MARGIN = 24
    RULE_LABELS = {
        "clearance_violation": "Clearance",
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
        self.placements = {
            key: PlacedFurniture(key=preset.key, label=preset.label)
            for key, preset in FURNITURE_PRESETS.items()
        }
        self.selected_key: str | None = None
        self.candidates: list[LayoutSolution] = []
        self.solver = MCMCSolver()
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
        self.set_result_text("Place furniture manually, then evaluate or generate MCMC suggestions.")

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

        tk.Label(self.side_frame, text="Suggestions", anchor="w").grid(row=3, column=0, sticky="ew")

        self.candidate_frame = tk.Frame(self.side_frame, bd=1, relief="solid", padx=6, pady=6)
        self.candidate_frame.grid(row=4, column=0, sticky="ew")

        tk.Label(self.side_frame, text="Score", anchor="w").grid(row=5, column=0, sticky="ew", pady=(12, 0))
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
        self.result_label.grid(row=6, column=0, sticky="nsew")
        self.side_frame.rowconfigure(6, weight=1)

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

        exit_y0 = y0 + (self.room.grid_h - self.room.exit_by) * self.CELL_PX
        exit_y1 = y0 + (self.room.grid_h - self.room.exit_ay) * self.CELL_PX
        self.canvas.create_line(x0, exit_y0, x0, exit_y1, fill="red", width=4, tags="grid")
        self.canvas.create_text(x0 + 24, exit_y0 - 10, text="EXIT", fill="red", tags="grid")

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

        for key, placement in self.placements.items():
            if not placement.placed or placement.gx is None or placement.gy is None:
                continue

            item = build_furniture_from_placement(key, placement)
            x0, y0, x1, y1 = self.rect_to_canvas(item.gx, item.gy, item.gw, item.gd)

            fall_zone = build_fall_zone_rect(item)
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
            width = 3 if key == self.selected_key else 1
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

    def can_place_furniture(self, key: str, gx: int, gy: int) -> bool:
        preset = FURNITURE_PRESETS[key]
        gw, gd = get_rotated_size(preset.gw, preset.gd, self.placements[key].rotation)
        if gx < 0 or gy < 0 or gx + gw > self.room.grid_w or gy + gd > self.room.grid_h:
            return False
        for other_key, other in self.placements.items():
            if other_key == key or not other.placed or other.gx is None or other.gy is None:
                continue
            other_preset = FURNITURE_PRESETS[other_key]
            other_gw, other_gd = get_rotated_size(other_preset.gw, other_preset.gd, other.rotation)
            if self.rects_overlap(gx, gy, gw, gd, other.gx, other.gy, other_gw, other_gd):
                return False
        return True

    def on_canvas_click(self, event: tk.Event) -> None:
        cell = self.canvas_to_grid(event.x, event.y)
        if cell is None:
            self.clear_selection()
            return
        gx, gy = cell
        clicked = self.find_furniture_at(gx, gy)
        if clicked is not None:
            self.select_furniture(clicked)
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

    def select_furniture(self, key: str) -> None:
        self.selected_key = key
        self.rotate_button.config(state="normal")
        self.draw_furniture()

    def clear_selection(self) -> None:
        self.selected_key = None
        self.rotate_button.config(state="disabled")
        self.draw_furniture()

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
