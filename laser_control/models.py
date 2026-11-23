from dataclasses import dataclass


@dataclass
class MaterialProfile:
    name: str
    power_percent: int
    speed_mm_min: int
    passes: int
    layer_type: str = ""
    notes: str = ""
    material_type: str = ""
    thickness_mm: float | None = None


@dataclass
class LaserState:
    connected: bool = False
    homed: bool = False
    paused: bool = False
    status: str = "Disconnected"
    alarm: bool = False
    x_mm: float = 0.0
    y_mm: float = 0.0
    z_mm: float = 0.0
    position_source: str = ""
    feed_rate: float | None = None
    spindle_value: float | None = None
    override_feed: int | None = None
    override_rapid: int | None = None
    override_spindle: int | None = None
    alignment_mode_active: bool = False
    pointer_power_percent: int = 1
    work_area_trace_active: bool = False
