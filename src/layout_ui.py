import tkinter as tk
from tkinter import messagebox

from models import (
    Direction,
    Furniture,
    FurnitureType,
    Room,
    FURNITURE_PRESETS,
    PlacedFurniture,
    get_rotated_size,
    rotate_direction,
    validate_layout,
)
from risk import evaluate_layout_risk

class FurnitureLayoutApp:
    CELL_PX = 48
    GRID_MARGIN = 24

    def __init__(self, room: Room) -> None:
        self.room = room
        self.root = tk.Tk()
        self.root.title("家具配置UI")

        self.placements = {
            key: PlacedFurniture(key=preset.key, label=preset.label)
            for key, preset in FURNITURE_PRESETS.items()
        }

        self.selected_key: str | None = None
        self.result_var = tk.StringVar(
            value="家具を配置して「決定」を押すと結果を表示します。"
        )

        # 家具ごとの色設定
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
            bg="white"
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
        self.rotate_button.pack(fill="x", pady=(0,0))

        self.finalize_button = tk.Button(
             self.side_frame,
             text="決定",
             command=self.finalize_layout,
        )
        self.finalize_button.pack(fill="x", pady=(0,12))

        tk.Label(
            self.side_frame,
            text="結果",
            anchor="w",
        ).pack(fill="x")

        self.result_label = tk.Label(
            self.side_frame,
            textvariable=self.result_var,
            justify="left",
            anchor="nw",
            width=32,
            height=20,
            bg="#f3f3f3",
            relief="solid",
            padx=8,
            pady=8,
        )
        self.result_label.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self.on_canvas_click)

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
        self.canvas.create_text(x0 + 24, exit_y0 - 10, text="EXIT", fill="red",tags="grid")

    # ウィンドウの部屋座標とTkinterのキャンバス座標の変換
    # Tkinterのキャンバスは左上原点、部屋座標は左下原点でy軸が逆
    def grid_to_canvas(self, gx: int, gy: int) -> tuple[int, int]:
         x = self.GRID_MARGIN + gx * self.CELL_PX
         y = self.GRID_MARGIN + (self.room.grid_h - gy - 1) * self.CELL_PX
         return x, y
    
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

    # 指定したグリッド座標に家具があるかチェックする
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

        tk.Label(self.palette_frame, text="家具一覧").pack(anchor="w", pady=(0,8))

        for key, placement in self.placements.items():
            state_text = "未配置" if not placement.placed else "配置済み"
            button = tk.Button(
                self.palette_frame,
                text=f"{placement.label} ({state_text})",
                anchor="w",
                command=lambda value=key: self.select_furniture(value),
            )
            button.pack(fill="x", pady=4)

    # 家具矩形を描く(placed=Trueのものだけ)
    def draw_furniture(self) -> None:
         self.canvas.delete("furniture")

         for key, placement in self.placements.items():
             if not placement.placed or placement.gx is None or placement.gy is None:
                 continue
              
             preset = FURNITURE_PRESETS[key]
             gw, gd = get_rotated_size(preset.gw, preset.gd, placement.rotation)
         
             x0, y_bottom = self.grid_to_canvas(placement.gx, placement.gy)
             x1 = x0 + gw * self.CELL_PX
             y1 = y_bottom + self.CELL_PX
             y0 = y1 - gd * self.CELL_PX
         
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
                  text=f"{placement.label}\nR{placement.rotation * 90}",
                  tags=("furniture",),
             )
         
    # 家具をクリックしたときの処理
    # クリック位置に家具を置く(置ける場合のみ)
    def on_canvas_click(self, event: tk.Event) -> None:
         cell = self.canvas_to_grid(event.x, event.y)
         if cell is None:
             self.clear_selection()
             return
         
         gx, gy = cell

         clicked_key =  self.find_furniture_at(gx, gy)
         if clicked_key is not None:
             self.select_furniture(clicked_key)
             return

         if self.selected_key is None:
             return
         
         if not self.can_place_furniture(self.selected_key, gx, gy):
              messagebox.showwarning("配置不可","その位置には置けません。")
              return
         
         placement = self.placements[self.selected_key]
         placement.gx = gx
         placement.gy = gy
         placement.placed = True

         self.draw_palette()
         self.draw_furniture()
         self.invalidate_result()

    def invalidate_result(self) -> None:
         self.result_var.set("配置が変更されました。結果を更新するには「決定」を押してください。")

    # 矩形同士が重なっているかの判定
    def rects_overlap(
             self,
             ax: int,
             ay: int,
             aw: int,
             ad: int,
             bx: int,
             by: int,
             bw: int,
             bd: int
     ) -> bool:
         return not(
              ax + aw <= bx or
              bx + bw <= ax or
              ay + ad <= by or
              by + bd <= ay
         )
    
    # 配置家具が部屋内に収まるかチェックする
    # 自分自身との重なりは無視する
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
                 other.rotation
             )

             if self.rects_overlap(
                 gx, gy, gw, gd, other.gx, other.gy, other_gw, other_gd
             ):
                 return False
         
         return True
    
    def rotate_selected(self) -> None:
         if self.selected_key is None:
              return
         
         placement = self.placements[self.selected_key]
         next_rotation = (placement.rotation + 1) % 4

         old_rotation = placement.rotation
         placement.rotation = next_rotation

         if placement.placed and placement.gx is not None and placement.gy is not None:
             if not self.can_place_furniture(self.selected_key, placement.gx, placement.gy):
                 placement.rotation = old_rotation
                 messagebox.showwarning("回転不可","回転すると家具が部屋外にはみ出すか、他の家具と重なります。")
                 return
             
         self.draw_furniture()
         self.invalidate_result()


    # 家具が全て配置されているかチェックする
    def get_missing_furniture_labels(self) -> list[str]:
         return [
              placement.label
              for placement in self.placements.values()
              if not placement.placed
         ]
    
    # 決定ボタンを押したときの処理
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

    # 選択を解除する(キャンバスの空白をクリックしたときなど)
    def clear_selection(self) -> None:
        self.selected_key = None
        self.rotate_button.config(state="disabled")
        self.draw_furniture()

    def finalize_layout(self) -> None:
         missing = self.get_missing_furniture_labels()
         if missing:
             self.result_var.set("未配置の家具があります: " + ", ".join(missing))
             return
         
         try:
             items = self.build_risk_items()
             validate_layout(self.room, items)
             result = evaluate_layout_risk(self.room, items)
         except ValueError as exc:
             self.result_var.set(f"レイアウトエラー: {exc}")
             return
         
         lines = [f"総合危険度: {result['total']:.3f}", ""]
         lines.append("内訳:")
         for name, score in result["breakdown"].items():
             lines.append(f"- {name}: {score:.3f}")
         
         lines.append("")
         if result["violations"]:
             lines.append("検出内容:")
             lines.extend(f"- {msg}" for msg in result["violations"])
         else:
             lines.append("検出内容: なし")

         self.result_var.set("\n".join(lines))

    def run(self) -> None:
            self.root.mainloop()