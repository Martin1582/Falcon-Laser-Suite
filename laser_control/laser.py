from collections.abc import Callable

from laser_control.models import LaserState


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

    def frame(self) -> None:
        self._require_ready()
        self._log("Rahmenfahrt simuliert.")
        self._emit_progress("Bereit", 1, 1)

    def start_job(self, gcode: str) -> None:
        self._require_ready()
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
        self.state.paused = False
        self._log("Job simuliert gestoppt. Laser aus.")
        self._emit_progress("Gestoppt", 0, 1)

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
