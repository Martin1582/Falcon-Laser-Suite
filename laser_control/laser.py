from collections.abc import Callable
import threading

from laser_control.models import LaserState
from laser_control.alignment import DEFAULT_POINTER_POWER_PERCENT, MAX_POINTER_POWER_PERCENT


LogFn = Callable[[str], None]
ProgressFn = Callable[[str, int, int], None]


class SimulatedLaserController:
    def __init__(self, log: LogFn, progress: ProgressFn | None = None) -> None:
        self.state = LaserState()
        self._log = log
        self._progress = progress

    def connect(self) -> None:
        self.state.connected = True
        self._log("Simulator verbunden.")
        self._emit_progress("Bereit", 1, 1)

    def disconnect(self) -> None:
        self.disable_alignment_pointer()
        self.state = LaserState()
        self._log("Simulator getrennt.")
        self._emit_progress("Getrennt", 0, 1)

    def home(self) -> None:
        self._require_connected()
        self.state.homed = True
        self.state.x_mm = 0.0
        self.state.y_mm = 0.0
        self._log("Referenzfahrt simuliert. Position X0 Y0.")
        self._emit_progress("Bereit", 1, 1)

    def jog(self, dx_mm: float, dy_mm: float) -> None:
        self._require_connected()
        self.state.x_mm = max(0.0, self.state.x_mm + dx_mm)
        self.state.y_mm = max(0.0, self.state.y_mm + dy_mm)
        self._log(f"Jog zu X{self.state.x_mm:.1f} Y{self.state.y_mm:.1f}.")

    def current_position(self) -> tuple[float, float]:
        self._require_connected()
        self._log(f"Position X{self.state.x_mm:.1f} Y{self.state.y_mm:.1f}.")
        return self.state.x_mm, self.state.y_mm

    def get_status(self) -> LaserState:
        return self.state

    def frame(
        self,
        width_mm: float | None = None,
        height_mm: float | None = None,
        x_mm: float = 0.0,
        y_mm: float = 0.0,
    ) -> None:
        self._require_ready()
        self.disable_alignment_pointer()
        safe_width = float(width_mm or 0.0)
        safe_height = float(height_mm or 0.0)
        self._log(
            "Rahmenfahrt simuliert: "
            f"X{x_mm:.2f} Y{y_mm:.2f} bis X{x_mm + safe_width:.2f} Y{y_mm + safe_height:.2f}."
        )
        self._emit_progress("Bereit", 1, 1)

    def start_job(self, gcode: str, width_mm: float | None = None, height_mm: float | None = None) -> None:
        self._require_ready()
        self.disable_alignment_pointer()
        command_count = len([line for line in gcode.splitlines() if line.strip()])
        self.state.paused = False
        self._log(f"Job simuliert gestartet ({command_count} Zeilen G-Code).")
        self._emit_progress("Bereit", command_count, max(1, command_count))

    def pause(self) -> None:
        self._require_connected()
        self.state.paused = True
        self._log("Job simuliert pausiert.")
        self._emit_progress("Pausiert", 0, 1)

    def resume(self) -> None:
        self._require_connected()
        self.state.paused = False
        self._log("Job simuliert fortgesetzt.")
        self._emit_progress("Fortsetzen", 0, 1)

    def stop(self) -> None:
        self._require_connected()
        if self.state.alignment_mode_active:
            self.disable_alignment_pointer()
            self._emit_progress("Bereit", 1, 1)
            return
        self.state.paused = False
        self._log("Job simuliert gestoppt. Laser aus.")
        self._emit_progress("Gestoppt", 0, 1)

    def emergency_stop(self) -> None:
        self._require_connected()
        self.disable_alignment_pointer()
        self.state.paused = False
        self.state.alarm = True
        self.state.status = "EmergencyStop"
        self._log("Sicherheitsstopp simuliert. Reset/Homing erforderlich.")
        self._emit_progress("Sicherheitsstopp", 0, 1)

    def enable_alignment_pointer(self, power_percent: int = DEFAULT_POINTER_POWER_PERCENT) -> None:
        self._require_connected()
        safe_power = max(DEFAULT_POINTER_POWER_PERCENT, min(MAX_POINTER_POWER_PERCENT, int(power_percent)))
        self.state.alignment_mode_active = True
        self.state.pointer_power_percent = safe_power
        self._log(f"Ausrichtmodus simuliert aktiv: Laserpunkt {safe_power}%.")
        self._emit_progress("Ausrichtmodus", 1, 1)

    def disable_alignment_pointer(self) -> None:
        if self.state.alignment_mode_active:
            self._log("Ausrichtmodus simuliert deaktiviert. Laser aus.")
        self.state.alignment_mode_active = False
        self.state.pointer_power_percent = DEFAULT_POINTER_POWER_PERCENT

    def workspace_trace_laser_off(self) -> None:
        self._require_connected()
        self.disable_alignment_pointer()
        self._log("Arbeitsflaechenmodus simuliert: M5/S0, Laser aus.")

    def trace_work_area_once(
        self,
        width_mm: float,
        height_mm: float,
        feed_mm_min: int,
        stop_event: threading.Event,
        power_percent: int = MAX_POINTER_POWER_PERCENT,
    ) -> None:
        self._require_connected()
        safe_width = max(0.0, float(width_mm))
        safe_height = max(0.0, float(height_mm))
        safe_feed = max(100, min(3000, int(feed_mm_min)))
        if safe_width <= 0 or safe_height <= 0:
            raise RuntimeError("Arbeitsflaechenmodus: ungueltiger Arbeitsbereich.")
        self.state.work_area_trace_active = True
        safe_power = max(0, min(MAX_POINTER_POWER_PERCENT, int(power_percent)))
        self._log(
            f"Arbeitsflaechenmodus simuliert: Runde F{safe_feed}, "
            f"X{safe_width:.1f} Y{safe_height:.1f}, Laserpunkt {safe_power}%."
        )
        for x_mm, y_mm in ((0.0, 0.0), (safe_width, 0.0), (safe_width, safe_height), (0.0, safe_height), (0.0, 0.0)):
            if stop_event.is_set():
                self._log("Arbeitsflaechenmodus simuliert: Stop erkannt.")
                return
            self.state.x_mm = x_mm
            self.state.y_mm = y_mm
            self.state.position_source = "WPos"
        self._emit_progress("Arbeitsflaechenmodus", 1, 1)

    def stop_work_area_trace(self) -> None:
        self.state.work_area_trace_active = False
        self._log("Arbeitsflaechenmodus simuliert gestoppt. Keine weiteren Runden.")

    def test_alignment_pointer(self, power_percent: int = MAX_POINTER_POWER_PERCENT, duration_seconds: float = 2.0) -> None:
        self._require_connected()
        safe_power = max(DEFAULT_POINTER_POWER_PERCENT, min(MAX_POINTER_POWER_PERCENT, int(power_percent)))
        self._log(f"Ausrichtmodus Test simuliert: Laserpunkt {safe_power}% fuer {duration_seconds:.1f}s, danach aus.")
        self.enable_alignment_pointer(safe_power)
        self.disable_alignment_pointer()

    def _require_connected(self) -> None:
        if not self.state.connected:
            raise RuntimeError("Bitte zuerst verbinden.")

    def _require_ready(self) -> None:
        self._require_connected()
        if not self.state.homed:
            raise RuntimeError("Bitte zuerst eine Referenzfahrt ausfuehren.")

    def _emit_progress(self, label: str, current: int, total: int) -> None:
        if self._progress is not None:
            self._progress(label, current, max(1, total))
