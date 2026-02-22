from dataclasses import dataclass

@dataclass
class Room:
    width: float
    height: float
    exit_ax: float
    exit_ay: float
    exit_bx: float
    exit_by: float

@dataclass
class Furniture:
    name: str
    x: float
    y: float
    w: float
    d: float
    h: float