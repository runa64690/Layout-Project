from dataclasses import dataclass

@dataclass
class Room:
    width: float
    height: float
    exit_x: float
    exit_y: float

@dataclass
class Furniture:
    name: str
    x: float
    y: float
    w: float
    d: float
    h: float