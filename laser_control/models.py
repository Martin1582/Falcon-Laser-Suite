from dataclasses import dataclass


@dataclass
class MaterialProfile:
    name: str
    power_percent: int
    speed_mm_min: int
    passes: int


@dataclass
class LaserState:
    connected: bool = False
    homed: bool = False
    paused: bool = False
    status: str = "Disconnected"
    alarm: bool = False
    x_mm: float = 0.0
    y_mm: float = 0.0
