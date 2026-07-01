from design_models import Room
from layout_app import FurnitureLayoutApp

def main() -> None:
    room = Room(
        grid_w=12,
        grid_h=12,
        exit_ax=0.0,
        exit_ay=5.0,
        exit_bx=0.0,
        exit_by=7.0
    )
    app = FurnitureLayoutApp(room)
    app.run()

if __name__ == "__main__":
    main()
