from __future__ import annotations

from typing import Protocol, runtime_checkable

from laser_control.models import LaserState


@runtime_checkable
class LaserController(Protocol):
    """Common machine API used by the UI and workflow layer."""

    state: LaserState
    homing_required: bool

    def connect(self) -> None:
        ...

    def disconnect(self) -> None:
        ...

    def get_status(self) -> LaserState:
        ...

    def home(self) -> None:
        ...

    def jog(self, dx_mm: float, dy_mm: float) -> None:
        ...

    def frame(self, width_mm: float, height_mm: float, x_mm: float = 0.0, y_mm: float = 0.0) -> None:
        ...

    def start_job(self, gcode: str, width_mm: float, height_mm: float) -> None:
        ...

    def pause(self) -> None:
        ...

    def resume(self) -> None:
        ...

    def stop(self) -> None:
        ...

    def emergency_stop(self) -> None:
        ...

    def unlock(self) -> None:
        """Clear an alarm lock without homing (GRBL `$X`). Position stays unreferenced."""
        ...

    def current_position(self) -> tuple[float, float]:
        ...

    def enable_alignment_pointer(self, power_percent: int = 1) -> None:
        ...

    def disable_alignment_pointer(self) -> None:
        ...

    def test_alignment_pointer(self, power_percent: int = 5, duration_seconds: float = 2.0) -> None:
        ...

    def workspace_trace_laser_off(self) -> None:
        ...

    def trace_work_area_once(
        self,
        width_mm: float,
        height_mm: float,
        feed_mm_min: int,
        stop_event,
        power_percent: int = 5,
    ) -> None:
        ...

    def stop_work_area_trace(self) -> None:
        ...
