import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from laser_control.gcode import build_safe_frame_gcode, prepare_job_gcode
from laser_control.models import LaserState
from laser_control.alignment import DEFAULT_POINTER_POWER_PERCENT, MAX_POINTER_POWER_PERCENT
from laser_control.diagnostic_log import DiagnosticLog
from laser_control.serial_executor import SerialExecutor, SerialPriority
from laser_control.serial_consistency import SerialConsistencyReport, SerialConsistencyTracker

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover - depends on local installation
    serial = None
    list_ports = None


LogFn = Callable[[str], None]
ProgressFn = Callable[[str, int, int], None]
NUMBER_PATTERN = r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)"
POSITION_RE = re.compile(rf"([MW]Pos):({NUMBER_PATTERN}),({NUMBER_PATTERN}),({NUMBER_PATTERN})")
WCO_RE = re.compile(rf"WCO:({NUMBER_PATTERN}),({NUMBER_PATTERN}),({NUMBER_PATTERN})")
STATUS_RE = re.compile(r"<([^|>]+)")
FS_RE = re.compile(rf"FS:({NUMBER_PATTERN}),({NUMBER_PATTERN})")
OV_RE = re.compile(r"Ov:(\d+),(\d+),(\d+)")
SETTING_RE = re.compile(r"\$(\d+)=([-+]?(?:\d+(?:\.\d+)?|\.\d+))")
DEFAULT_GRBL_S_MAX = 1000.0


@dataclass(frozen=True)
class GrblStatusReport:
    state: str
    mpos_x: float | None = None
    mpos_y: float | None = None
    mpos_z: float | None = None
    wpos_x: float | None = None
    wpos_y: float | None = None
    wpos_z: float | None = None
    wco_x: float | None = None
    wco_y: float | None = None
    wco_z: float | None = None
    feed_rate: float | None = None
    spindle_value: float | None = None
    override_feed: int | None = None
    override_rapid: int | None = None
    override_spindle: int | None = None

    @property
    def position_source(self) -> str:
        if self.wpos_x is not None:
            return "WPos"
        if self.mpos_x is not None and self.wco_x is not None:
            return "WPos (MPos-WCO)"
        if self.mpos_x is not None:
            return "MPos"
        return ""

    @property
    def x_mm(self) -> float | None:
        if self.wpos_x is not None:
            return self.wpos_x
        if self.mpos_x is not None and self.wco_x is not None:
            return self.mpos_x - self.wco_x
        return self.mpos_x

    @property
    def y_mm(self) -> float | None:
        if self.wpos_y is not None:
            return self.wpos_y
        if self.mpos_y is not None and self.wco_y is not None:
            return self.mpos_y - self.wco_y
        return self.mpos_y

    @property
    def z_mm(self) -> float | None:
        if self.wpos_z is not None:
            return self.wpos_z
        if self.mpos_z is not None and self.wco_z is not None:
            return self.mpos_z - self.wco_z
        return self.mpos_z


def parse_grbl_status_report(response: str) -> GrblStatusReport | None:
    status_match = STATUS_RE.search(response)
    if not status_match:
        return None
    report = GrblStatusReport(state=status_match.group(1))
    values = report.__dict__.copy()
    for position_match in POSITION_RE.finditer(response):
        source = position_match.group(1)
        x = float(position_match.group(2))
        y = float(position_match.group(3))
        z = float(position_match.group(4))
        prefix = "mpos" if source == "MPos" else "wpos"
        values[f"{prefix}_x"] = x
        values[f"{prefix}_y"] = y
        values[f"{prefix}_z"] = z
    fs_match = FS_RE.search(response)
    if fs_match:
        values["feed_rate"] = float(fs_match.group(1))
        values["spindle_value"] = float(fs_match.group(2))
    wco_match = WCO_RE.search(response)
    if wco_match:
        values["wco_x"] = float(wco_match.group(1))
        values["wco_y"] = float(wco_match.group(2))
        values["wco_z"] = float(wco_match.group(3))
    ov_match = OV_RE.search(response)
    if ov_match:
        values["override_feed"] = int(ov_match.group(1))
        values["override_rapid"] = int(ov_match.group(2))
        values["override_spindle"] = int(ov_match.group(3))
    return GrblStatusReport(**values)


def list_serial_ports() -> list[str]:
    if list_ports is None:
        return []

    ports = []
    for port in list_ports.comports():
        label = port.device
        if port.description:
            label = f"{port.device} - {port.description}"
        ports.append(label)
    return ports


def serial_support_available() -> bool:
    return serial is not None and list_ports is not None


def port_device(port_label: str) -> str:
    return port_label.split(" - ", 1)[0].strip()


class GrblSerialController:
    def __init__(
        self,
        log: LogFn,
        port_getter: Callable[[], str],
        progress: ProgressFn | None = None,
        baudrate: int = 115200,
        diagnostic_log: DiagnosticLog | None = None,
    ) -> None:
        self.state = LaserState()
        self._log = log
        self._progress = progress
        self._port_getter = port_getter
        self._baudrate = baudrate
        self._executor = SerialExecutor(self._log_serial_event)
        self._diagnostic_log = diagnostic_log
        self._active_consistency: SerialConsistencyTracker | None = None
        self._abort_requested = threading.Event()
        self._first_position_logged = False
        self._missing_position_logged = False
        self._job_status_polling_logged = False
        self.grbl_settings: dict[int, float] = {}

    @property
    def _serial(self):
        return self._executor.connection

    @_serial.setter
    def _serial(self, connection) -> None:
        self._executor._serial = connection

    def connect(self) -> None:
        self._emit_progress("Verbinde", 0, 1)
        if serial is None:
            raise RuntimeError("pyserial fehlt. Bitte zuerst 'py -m pip install -r requirements.txt' ausfuehren.")

        port = port_device(self._port_getter())
        if not port:
            raise RuntimeError("Bitte zuerst einen COM-Port auswaehlen.")

        self.disconnect(log_message=False)
        self._log(f"Verbinde mit {port} bei {self._baudrate} Baud...")
        self._executor.open_serial(serial, port=port, baudrate=self._baudrate, timeout=0.5, write_timeout=1.0)
        time.sleep(1.8)
        self._executor.reset_input_buffer()

        self._diagnostic_tx("<wake>")
        banner = self._read_available_after_write("\r\n\r\n", wait_seconds=0.6, priority=SerialPriority.CONNECTION)
        info = self.query("$I", wait_seconds=1.0, log_command=True)
        status = self._query_status_text()

        handshake = self._combine_responses(banner, info, status)
        if not self._looks_like_grbl(handshake):
            self.disconnect(log_message=False)
            raise RuntimeError("Keine plausible GRBL-Antwort erhalten. Port, Kabel und eingeschalteten Laser pruefen.")

        self.state.connected = True
        self._log("GRBL verbunden.")
        self._log_response(handshake)
        if self._is_hold_status(handshake):
            self.state.paused = True
            self._log("Controller ist im Hold-Zustand. Mit Fortsetzen (~) oder Stop/Reset fortfahren.")
        else:
            self.send_command("M5")
        self._update_state_from_status(handshake)
        self._emit_progress("Bereit", 1, 1)

    def disconnect(self, log_message: bool = True) -> None:
        if self.state.connected:
            self._abort_requested.set()
            try:
                self.disable_alignment_pointer()
            except Exception as exc:
                if log_message:
                    self._log(f"Fehler beim Ausschalten des Ausrichtlasers vor Disconnect: {exc}")
        try:
            self._executor.close()
        except Exception as exc:
            if log_message:
                self._log(f"Fehler beim Trennen: {exc}")
        self.state = LaserState()
        if log_message:
            self._log("GRBL getrennt.")
        self._emit_progress("Getrennt", 0, 1)

    def get_status(self) -> LaserState:
        if self._executor.is_open:
            try:
                self.query_status()
            except Exception as exc:
                self._log(f"Statusabfrage fehlgeschlagen: {exc}")
                raise
        return self.state

    @property
    def serial_queue_empty(self) -> bool:
        return self._executor.is_queue_empty

    def home(self) -> None:
        self._require_connected()
        self._emit_progress("Referenzfahrt", 0, 1)
        self.send_command("$H", wait_seconds=10.0)
        self.state.homed = True
        self.state.x_mm = 0.0
        self.state.y_mm = 0.0
        self._log("Referenzfahrt abgeschlossen.")
        self._emit_progress("Bereit", 1, 1)

    def jog(self, dx_mm: float, dy_mm: float) -> None:
        self._require_connected()
        command = f"$J=G91 X{dx_mm:.3f} Y{dy_mm:.3f} F1200"
        self.send_command(command)
        self.state.x_mm = max(0.0, self.state.x_mm + dx_mm)
        self.state.y_mm = max(0.0, self.state.y_mm + dy_mm)

    def frame(self, width_mm: float, height_mm: float, x_mm: float = 0.0, y_mm: float = 0.0) -> None:
        self._require_ready()
        if self.state.alignment_mode_active:
            self.disable_alignment_pointer()
        commands = build_safe_frame_gcode(width_mm, height_mm, x_mm=x_mm, y_mm=y_mm)
        self._log(
            "Starte sichere Rahmenfahrt ohne Laser: "
            f"X{x_mm:.2f} Y{y_mm:.2f} -> "
            f"X{x_mm + width_mm:.2f} Y{y_mm:.2f} -> "
            f"X{x_mm + width_mm:.2f} Y{y_mm + height_mm:.2f} -> "
            f"X{x_mm:.2f} Y{y_mm + height_mm:.2f} -> "
            f"X{x_mm:.2f} Y{y_mm:.2f}; "
            f"Groesse {width_mm:.2f} x {height_mm:.2f} mm."
        )
        for index, command in enumerate(commands, start=1):
            self._emit_progress("Rahmenfahrt", index - 1, len(commands))
            self.send_command(command, wait_seconds=5.0)
        self._wait_until_idle(timeout_seconds=60.0)
        self._log("Rahmenfahrt abgeschlossen.")
        self._emit_progress("Bereit", len(commands), len(commands))

    def start_job(self, gcode: str, width_mm: float, height_mm: float) -> None:
        self._require_ready()
        if self.state.alignment_mode_active:
            self.disable_alignment_pointer()
        self._abort_requested.clear()
        commands = prepare_job_gcode(gcode, width_mm, height_mm)
        self._log_hardware_job_summary(commands, width_mm, height_mm)
        consistency = SerialConsistencyTracker("Hardware-Job")
        self._active_consistency = consistency
        try:
            status_before = self._query_status_text()
            if status_before:
                self._update_state_from_status(status_before)
                self._log("Status vor Jobstart:")
                self._log_response(status_before)
                if self.state.alarm:
                    raise RuntimeError("Controller ist im Alarm-Zustand. Bitte Ursache beheben und erneut homen.")

            last_status_poll = 0.0
            self._job_status_polling_logged = False
            self._log("Statuspolling waehrend Job aktiv: '?' als GRBL-Realtime-Statusabfrage, keine ok-Antwort erwartet.")
            for index, command in enumerate(commands, start=1):
                if self._abort_requested.is_set():
                    raise RuntimeError("Job durch Stop/Emergency Stop abgebrochen.")
                self._emit_progress("Job laeuft", index - 1, len(commands))
                self._log(f"Job {index}/{len(commands)}")
                self.send_command(command, wait_seconds=10.0)
                if self._abort_requested.is_set():
                    raise RuntimeError("Job durch Stop/Emergency Stop abgebrochen.")

                now = time.monotonic()
                if index == 1 or index == min(5, len(commands)) or now - last_status_poll >= 0.5:
                    last_status_poll = now
                    if not self._job_status_polling_logged and self.state.status.startswith(("Run", "Hold")):
                        self._job_status_polling_logged = True
                        self._log("Statuspolling bestaetigt: Positionsabfragen laufen waehrend Run/Hold.")
                    status = self._query_status_text()
                    if status:
                        self._update_state_from_status(status)
                        if index == 1 or index == min(5, len(commands)):
                            self._log(f"Status nach Zeile {index}:")
                            self._log_response(status)
                if self.state.paused:
                    self._log("Job-Streaming pausiert: GRBL Hold aktiv.")
                    self._wait_while_paused()

            self._wait_until_idle(timeout_seconds=120.0)
            if self._abort_requested.is_set():
                raise RuntimeError("Job durch Stop/Emergency Stop abgebrochen.")
            final_status = self._query_status_text()
            if final_status:
                self._update_state_from_status(final_status)
                self._log("Status nach Jobende:")
                self._log_response(final_status)
            self._log("Hardware-Job abgeschlossen.")
            self._log_consistency_report(consistency.report())
            self._emit_progress("Bereit", len(commands), len(commands))
        except Exception:
            self._emit_progress("Fehler", 0, 1)
            if self._abort_requested.is_set():
                self._log("Job durch Stop/Emergency Stop/Disconnect abgebrochen. Es wird kein weiterer G-Code gesendet.")
                self._log_consistency_report(consistency.report())
                raise RuntimeError("Job durch Stop/Emergency Stop/Disconnect abgebrochen.") from None
            else:
                self._log("Job abgebrochen. Sende Laser aus.")
                try:
                    self.send_command("M5")
                finally:
                    self._log_consistency_report(consistency.report())
                raise
        finally:
            self._active_consistency = None

    def _wait_while_paused(self) -> None:
        while self.state.paused:
            if self._abort_requested.is_set():
                raise RuntimeError("Job durch Stop/Emergency Stop waehrend Hold abgebrochen.")
            status = self._query_status_text()
            if status:
                self._update_state_from_status(status)
                self._log_response(status)
                if self.state.alarm:
                    raise RuntimeError("Controller meldet Alarm waehrend Pause.")
            time.sleep(0.2)
        self._log("Job-Streaming fortgesetzt.")

    def pause(self) -> None:
        self._require_connected()
        self._diagnostic_tx("! feed hold")
        self._log("Feed Hold angefordert: sende '!' als GRBL-Realtime-Kommando, keine ok-Antwort erwartet.")
        self._send_raw("!", priority=SerialPriority.PAUSE)
        response = self._wait_for_status_prefix(("Hold",), timeout_seconds=3.0, allow_prefixes=("Run", "Idle"))
        if response:
            self._log_response(response)
        self.state.paused = self.state.status.startswith("Hold")
        if not self.state.paused:
            raise RuntimeError("Timeout beim Warten auf Hold-Zustand nach Feed Hold.")
        self._log("GRBL Hold erkannt. Jobstatus pausiert.")
        self._emit_progress("Pausiert", 0, 1)

    def resume(self) -> None:
        self._require_connected()
        self._diagnostic_tx("~ cycle start")
        self._log("Resume angefordert: sende '~' als GRBL-Realtime-Kommando, keine ok-Antwort erwartet.")
        self._send_raw("~", priority=SerialPriority.RESUME)
        response = self._wait_for_status_prefix(("Run", "Idle"), timeout_seconds=3.0, allow_prefixes=("Hold",))
        if response:
            self._log_response(response)
        self.state.paused = self.state.status.startswith("Hold")
        if self.state.paused:
            raise RuntimeError("Timeout beim Warten auf Run/Idle nach Resume.")
        self._log("GRBL Resume erkannt.")
        self._emit_progress("Fortsetzen", 0, 1)

    def stop(self) -> None:
        self._require_connected()
        if self.state.alignment_mode_active:
            self.disable_alignment_pointer()
            self._emit_progress("Bereit", 1, 1)
            return
        self._diagnostic_tx("0x18 soft reset")
        self._abort_requested.set()
        self._log("Kontrollierter Stop angefordert: Queue wird geleert und Ctrl-X priorisiert gesendet.")
        self._executor.clear_pending(min_priority=SerialPriority.MANUAL)
        self._send_raw("\x18", priority=SerialPriority.EMERGENCY)
        time.sleep(1.0)
        response = self._read_available(wait_seconds=1.0, priority=SerialPriority.EMERGENCY)
        self._log_response(response)
        self.state.homed = False
        self.state.paused = False
        self.state.status = "Idle"
        self._log("Kontrollierter Stop/Reset gesendet. Bitte vor weiterer Bewegung erneut Referenzfahrt ausfuehren.")
        self._emit_progress("Gestoppt", 0, 1)

    def emergency_stop(self) -> None:
        self._require_connected()
        if self.state.alignment_mode_active:
            try:
                self.disable_alignment_pointer()
            except Exception as exc:
                self._log(f"Ausrichtlaser konnte vor Sicherheitsstopp nicht bestaetigt ausgeschaltet werden: {exc}")
        self._diagnostic_tx("0x18 emergency soft reset")
        self._abort_requested.set()
        self._log("Sicherheitsstopp angefordert: Queue wird sofort geleert und Ctrl-X mit hoechster Prioritaet gesendet.")
        self._executor.clear_pending(min_priority=SerialPriority.PAUSE)
        self._send_raw("\x18", priority=SerialPriority.EMERGENCY)
        time.sleep(0.5)
        response = self._read_available(wait_seconds=1.0, priority=SerialPriority.EMERGENCY)
        self._log_response(response)
        self.state.homed = False
        self.state.paused = False
        self.state.alarm = True
        self.state.status = "EmergencyStop"
        self._log("Sicherheitsstopp ausgefuehrt. Bewusstes Reset/Unlock/Re-Homing vor weiterer Bewegung erforderlich.")
        self._emit_progress("Sicherheitsstopp", 0, 1)

    def query_status(self) -> None:
        self._require_connected()
        response = self._query_status_text()
        if response:
            self._update_state_from_status(response)
            self._log_response(response)
        else:
            self._log("Keine Statusantwort erhalten.")

    def current_position(self) -> tuple[float, float]:
        self._require_connected()
        response = self._query_status_text()
        report = parse_grbl_status_report(response)
        self._update_state_from_status(response)
        self._log_response(response)
        if report is None or report.x_mm is None or report.y_mm is None:
            raise RuntimeError("Keine Position im Statusreport gefunden.")
        x = report.x_mm
        y = report.y_mm
        self.state.x_mm = x
        self.state.y_mm = y
        self.state.z_mm = report.z_mm or 0.0
        self.state.position_source = report.position_source
        return x, y

    def enable_alignment_pointer(self, power_percent: int = DEFAULT_POINTER_POWER_PERCENT) -> None:
        self._require_connected()
        safe_power = max(DEFAULT_POINTER_POWER_PERCENT, min(MAX_POINTER_POWER_PERCENT, int(power_percent)))
        s_max = self._alignment_s_max()
        s_min = self.grbl_settings.get(31)
        laser_mode = self.grbl_settings.get(32)
        s_value = self._alignment_s_value(safe_power)
        self._log(
            "alignment mode requested: "
            f"machine_state={self.state.status}; connected={self.state.connected}; "
            f"paused={self.state.paused}; alarm={self.state.alarm}; "
            f"pointer_power_percent={safe_power}; s_max={s_max:g}; "
            f"s_min={s_min if s_min is not None else '--'}; "
            f"laser_mode_$32={laser_mode if laser_mode is not None else '--'}; "
            f"calculated_s={s_value}; laser_off_command_sent=no"
        )
        if s_min is not None and s_min > 0 and s_value < s_min:
            self._log(
                f"Ausrichtlaser Hinweis: berechneter S-Wert {s_value} liegt unter $31={s_min:g}; "
                "Laserpunkt kann unsichtbar bleiben."
            )
        command = f"M3 S{s_value}"
        self._log(f"Ausrichtlaser an: command sent {command} ({safe_power}%, M3 konstant).")
        self.send_command(command, wait_seconds=2.0)
        self.state.alignment_mode_active = True
        self.state.pointer_power_percent = safe_power

    def disable_alignment_pointer(self) -> None:
        if not self._executor.is_open:
            self.state.alignment_mode_active = False
            return
        was_active = self.state.alignment_mode_active
        first_error: Exception | None = None
        for command in ("M5", "S0"):
            try:
                self._log(f"Ausrichtlaser aus: command sent {command}.")
                self.send_command(command, wait_seconds=2.0)
            except Exception as exc:  # noqa: BLE001 - try both safety commands
                if first_error is None:
                    first_error = exc
        self.state.alignment_mode_active = False
        self.state.pointer_power_percent = DEFAULT_POINTER_POWER_PERCENT
        if was_active:
            self._log("Ausrichtlaser aus: M5/S0 gesendet.")
        if first_error is not None:
            raise first_error

    def workspace_trace_laser_off(self) -> None:
        self._require_connected()
        first_error: Exception | None = None
        for command in ("M5", "S0"):
            try:
                self._log(f"Arbeitsflaechenmodus Laser aus: command sent {command}.")
                self.send_command(command, wait_seconds=2.0)
            except Exception as exc:  # noqa: BLE001 - try both safety commands
                if first_error is None:
                    first_error = exc
        self.state.alignment_mode_active = False
        self.state.pointer_power_percent = DEFAULT_POINTER_POWER_PERCENT
        self._log("Arbeitsflaechenmodus: M5/S0 gesendet.")
        if first_error is not None:
            raise first_error

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
        self._abort_requested.clear()
        safe_power = max(0, min(MAX_POINTER_POWER_PERCENT, int(power_percent)))
        s_max = self._alignment_s_max()
        s_value = self._alignment_s_value(safe_power) if safe_power > 0 else 0
        commands = [
            "G21",
            "G90",
            "M5",
            "S0",
            f"M3 S{s_value}" if s_value > 0 else "M5",
            f"G1 X0.000 Y0.000 F{safe_feed}",
            f"G1 X{safe_width:.3f} Y0.000 F{safe_feed}",
            f"G1 X{safe_width:.3f} Y{safe_height:.3f} F{safe_feed}",
            f"G1 X0.000 Y{safe_height:.3f} F{safe_feed}",
            f"G1 X0.000 Y0.000 F{safe_feed}",
            "M5",
            "S0",
        ]
        self._log(
            "Arbeitsflaechenmodus: sende Rahmenpfad "
            f"X0/Y0 -> X{safe_width:.1f}/Y0 -> X{safe_width:.1f}/Y{safe_height:.1f} -> "
            f"X0/Y{safe_height:.1f} -> X0/Y0, F{safe_feed}; "
            f"$30={s_max:g}; Laserpunkt={safe_power}%; S{s_value}; Laserbefehl=M3; Bewegungsmodus=G1."
        )
        wait_seconds = max(10.0, (max(safe_width, safe_height) / max(1, safe_feed)) * 60.0 + 5.0)
        for command in commands:
            if stop_event.is_set():
                self._log("Arbeitsflaechenmodus: Stop vor naechstem Befehl erkannt.")
                return
            self.send_command(command, wait_seconds=5.0)
            if self._is_motion_command(command):
                self._wait_until_idle_or_stopped(stop_event, timeout_seconds=wait_seconds)
        self._emit_progress("Arbeitsflaechenmodus", 1, 1)

    def stop_work_area_trace(self) -> None:
        removed = self._executor.clear_pending(min_priority=SerialPriority.MANUAL)
        self._log(f"Arbeitsflaechenmodus Stop: {removed} wartende Bewegung(en) verworfen; keine neuen Runden.")

    def test_alignment_pointer(self, power_percent: int = MAX_POINTER_POWER_PERCENT, duration_seconds: float = 2.0) -> None:
        self._require_connected()
        if self.state.status.strip().lower() not in {"idle", "connected"} and self.state.status:
            raise RuntimeError("Pointer-Test ist nur im Idle-Zustand erlaubt.")
        safe_duration = max(0.1, min(5.0, float(duration_seconds)))
        self._log(
            f"Ausrichtlaser Testmodus: M3 fuer {safe_duration:.1f}s, danach automatisch M5/S0. "
            "Nur bei idle Maschine verwenden."
        )
        self.enable_alignment_pointer(power_percent)
        try:
            time.sleep(safe_duration)
        finally:
            self.disable_alignment_pointer()
            self._log("Ausrichtlaser Testmodus beendet: laser-off command sent yes.")

    def query_settings(self) -> dict[int, float]:
        self._require_connected()
        response = self.query("$$", wait_seconds=2.0, log_command=True)
        self._parse_and_store_settings(response)
        self._log_response(response)
        return dict(self.grbl_settings)

    def send_command(self, command: str, wait_seconds: float = 2.0) -> str:
        self._require_connected()
        response = self.query(command, wait_seconds=wait_seconds, log_command=True)
        self._log_response(response)
        if not response.strip():
            raise RuntimeError(f"Keine Antwort vom Controller bei: {command}")
        if "error:" in response.lower():
            raise RuntimeError(f"GRBL meldet Fehler bei: {command}")
        return response

    def query(self, command: str, wait_seconds: float = 2.0, log_command: bool = False) -> str:
        if log_command:
            self._log(f"> {command}")
        self._diagnostic_tx(command)
        self._record_consistency_tx(command, expects_ack=True)
        response = self._clean_response_text(
            self._executor.query_line(command, wait_seconds=wait_seconds, priority=self._priority_for_command(command))
        )
        self._diagnostic_rx(response)
        self._update_state_from_embedded_status(response)
        return response

    def _parse_and_store_settings(self, response: str) -> None:
        parsed = {int(match.group(1)): float(match.group(2)) for match in SETTING_RE.finditer(response)}
        if not parsed:
            return
        self.grbl_settings.update(parsed)
        s_max = self.grbl_settings.get(30)
        s_min = self.grbl_settings.get(31)
        laser_mode = self.grbl_settings.get(32)
        self._log(
            "GRBL-Parameter gelesen: "
            f"$30={s_max if s_max is not None else '--'}, "
            f"$31={s_min if s_min is not None else '--'}, "
            f"$32={laser_mode if laser_mode is not None else '--'}."
        )

    def _alignment_s_max(self) -> float:
        if 30 not in self.grbl_settings:
            try:
                self._log("Ausrichtlaser Diagnose: $30 unbekannt, frage GRBL Settings ($$) ab.")
                self.query_settings()
            except Exception as exc:  # noqa: BLE001 - fallback keeps alignment usable but logged
                self._log(f"Ausrichtlaser Diagnose: $30 konnte nicht gelesen werden ({exc}); nutze S-Max {DEFAULT_GRBL_S_MAX:g}.")
        s_max = float(self.grbl_settings.get(30, DEFAULT_GRBL_S_MAX))
        if s_max <= 0:
            self._log(f"Ausrichtlaser Diagnose: ungueltiges $30={s_max:g}; nutze S-Max {DEFAULT_GRBL_S_MAX:g}.")
            return DEFAULT_GRBL_S_MAX
        return s_max

    def _alignment_s_value(self, power_percent: int) -> int:
        s_max = self._alignment_s_max()
        return max(1, int(round(max(0, min(100, int(power_percent))) / 100 * s_max)))

    def _send_line(self, command: str, log_command: bool) -> None:
        if log_command:
            self._log(f"> {command}")
        self._diagnostic_tx(command)
        self._record_consistency_tx(command, expects_ack=True)
        self._send_raw(command.strip() + "\n", priority=self._priority_for_command(command))

    def _send_raw(self, value: str, priority: SerialPriority = SerialPriority.MANUAL) -> None:
        self._executor.write_raw(value, priority=priority)

    def _read_until_ok_or_error(self, wait_seconds: float) -> str:
        response = self._executor.read_available(wait_seconds=wait_seconds)
        response = self._clean_response_text(response)
        self._diagnostic_rx(response)
        return response

    def _read_available(self, wait_seconds: float = 0.2, priority: SerialPriority = SerialPriority.MANUAL) -> str:
        response = self._clean_response_text(self._executor.read_available(wait_seconds=wait_seconds, priority=priority))
        self._diagnostic_rx(response)
        return response

    def _read_available_after_write(
        self,
        value: str,
        wait_seconds: float = 0.2,
        priority: SerialPriority = SerialPriority.MANUAL,
    ) -> str:
        response = self._clean_response_text(
            self._executor.read_available_after_write(value, wait_seconds=wait_seconds, priority=priority)
        )
        self._diagnostic_rx(response)
        return response

    def _clean_response_text(self, value: str) -> str:
        return value.replace("\x1b[0;31m", "").replace("\x1b[0m", "")

    def _query_status_text(self) -> str:
        self._diagnostic_tx("?")
        self._record_consistency_tx("?", expects_ack=False)
        response = self._clean_response_text(
            self._executor.query_status_report("?", wait_seconds=0.6, priority=SerialPriority.STATUS)
        )
        self._diagnostic_rx(response)
        return response

    def _wait_until_idle(self, timeout_seconds: float) -> None:
        end_time = time.monotonic() + timeout_seconds
        last_status = ""
        while time.monotonic() < end_time:
            if self._abort_requested.is_set():
                raise RuntimeError("Job durch Stop/Emergency Stop abgebrochen.")
            status = self._query_status_text()
            if status:
                last_status = status
                self._update_state_from_status(status)
                self._log_response(status)
                if self.state.status == "Idle":
                    return
                if self.state.alarm:
                    raise RuntimeError(f"Controller meldet Alarm. Letzter Status: {last_status}")
            time.sleep(0.25)
        raise RuntimeError(f"Timeout beim Warten auf Idle. Letzter Status: {last_status}")

    def _wait_until_idle_or_stopped(self, stop_event: threading.Event, timeout_seconds: float) -> None:
        end_time = time.monotonic() + timeout_seconds
        last_status = ""
        while time.monotonic() < end_time:
            if stop_event.is_set():
                self._log("Arbeitsflaechenmodus: Stop erkannt, warte nicht auf weitere Runde.")
                return
            if self._abort_requested.is_set():
                raise RuntimeError("Arbeitsflaechenmodus durch Stop/Emergency Stop abgebrochen.")
            status = self._query_status_text()
            if status:
                last_status = status
                self._update_state_from_status(status)
                if self.state.status == "Idle":
                    return
                if self.state.alarm:
                    raise RuntimeError(f"Controller meldet Alarm. Letzter Status: {last_status}")
            time.sleep(0.25)
        raise RuntimeError(f"Timeout beim Warten auf Idle im Arbeitsflaechenmodus. Letzter Status: {last_status}")

    def _wait_for_status_prefix(
        self,
        expected_prefixes: tuple[str, ...],
        timeout_seconds: float,
        allow_prefixes: tuple[str, ...] = (),
    ) -> str:
        end_time = time.monotonic() + timeout_seconds
        last_status = ""
        while time.monotonic() < end_time:
            status = self._query_status_text()
            if status:
                last_status = status
                self._update_state_from_status(status)
                if self.state.alarm:
                    raise RuntimeError(f"Controller meldet Alarm. Letzter Status: {last_status}")
                if self.state.status.startswith(expected_prefixes):
                    return status
                if allow_prefixes and self.state.status.startswith(allow_prefixes):
                    time.sleep(0.15)
                    continue
            time.sleep(0.15)
        self._log(f"Timeout beim Warten auf Status {expected_prefixes}. Letzter Status: {last_status}")
        return last_status

    def _looks_like_grbl(self, response: str) -> bool:
        lowered = response.lower()
        has_grbl_identity = "grbl" in lowered or "[ver:" in lowered or "[opt:" in lowered
        has_status_report = "<" in response and ">" in response and ("mpos:" in lowered or "wpos:" in lowered)
        has_command_ack = any(line.strip().lower() == "ok" for line in response.splitlines())
        return has_grbl_identity or has_status_report or has_command_ack

    def _is_hold_status(self, response: str) -> bool:
        return "<Hold" in response

    def _update_state_from_status(self, response: str) -> None:
        report = parse_grbl_status_report(response)
        if report is None:
            if response.strip():
                self._log("Statusparser: keine GRBL-Statuszeile erkannt.")
            return
        previous_source = self.state.position_source
        self.state.status = report.state
        self.state.paused = self.state.status.startswith("Hold")
        self.state.alarm = self.state.status.startswith("Alarm") or self.state.status.startswith("EmergencyStop")
        if report.x_mm is not None and report.y_mm is not None:
            self.state.x_mm = report.x_mm
            self.state.y_mm = report.y_mm
            self.state.z_mm = report.z_mm or 0.0
            self.state.position_source = report.position_source
            if not self._first_position_logged:
                self._first_position_logged = True
                self._log(
                    "Erste Positionsmeldung empfangen: "
                    f"{report.position_source} X{report.x_mm:.3f} Y{report.y_mm:.3f} Z{(report.z_mm or 0.0):.3f}."
                )
            if previous_source and previous_source != report.position_source:
                self._log(f"Statusposition wechselt von {previous_source} auf {report.position_source}.")
        elif not self.state.position_source and not self._missing_position_logged:
            self._missing_position_logged = True
            self._log("Statusparser: keine Positionsdaten in Statusmeldung.")
        self.state.feed_rate = report.feed_rate
        self.state.spindle_value = report.spindle_value
        self.state.override_feed = report.override_feed
        self.state.override_rapid = report.override_rapid
        self.state.override_spindle = report.override_spindle

    def _update_state_from_embedded_status(self, response: str) -> None:
        for line in response.splitlines():
            cleaned = line.strip()
            if cleaned.startswith("<") and ">" in cleaned:
                self._update_state_from_status(cleaned)

    def _combine_responses(self, *responses: str) -> str:
        lines = []
        for response in responses:
            for line in response.splitlines():
                cleaned = line.strip()
                if cleaned:
                    lines.append(cleaned)
        return "\n".join(lines)

    def _log_hardware_job_summary(self, commands: list[str], width_mm: float, height_mm: float) -> None:
        port = self._executor.port or port_device(self._port_getter())
        upper_commands = [command.upper() for command in commands]
        movement_commands = [
            command
            for command in commands
            if self._is_motion_command(command)
        ]
        laser_commands = [
            command
            for command in commands
            if command.upper().startswith(("M3", "M4")) or " S" in command.upper()
        ]

        self._log("=== HARDWARE-JOB START ===")
        self._log(f"Port: {port}, Baud: {self._baudrate}")
        self._log(f"Arbeitsbereich: {width_mm:.1f} x {height_mm:.1f} mm")
        self._log(f"G-Code-Zeilen: {len(commands)}, Bewegungen: {len(movement_commands)}")
        self._log(f"Laser-Aktivbefehle erkannt: {len(laser_commands)}")
        if "M5" not in upper_commands[-1]:
            self._log("Hinweis: Letzte Zeile ist nicht M5; Laser-Aus wird durch Vorbereitung ergaenzt.")
        if not laser_commands:
            self._log("Warnung: Kein M3/M4/S-Wert erkannt. Der Job bewegt ggf. nur ohne sichtbaren Laser.")

        for index, command in enumerate(movement_commands[:3], start=1):
            self._log(f"Erste Bewegung {index}: {command}")
        if movement_commands:
            self._log(f"Letzte Bewegung: {movement_commands[-1]}")
        if self._diagnostic_log is not None:
            self._diagnostic_log.job("=== HARDWARE-JOB START ===")
            self._diagnostic_log.job(f"Port: {port}, Baud: {self._baudrate}")
            self._diagnostic_log.job(f"Arbeitsbereich: {width_mm:.1f} x {height_mm:.1f} mm")
            self._diagnostic_log.job(f"G-Code-Zeilen: {len(commands)}, Bewegungen: {len(movement_commands)}")
            if movement_commands:
                self._diagnostic_log.job(f"Erste Bewegung: {movement_commands[0]}")
                self._diagnostic_log.job(f"Letzte Bewegung: {movement_commands[-1]}")

    def _log_response(self, response: str) -> None:
        previous = None
        count = 0
        for line in response.splitlines():
            cleaned = line.strip()
            if not cleaned:
                continue
            if cleaned == previous:
                count += 1
                continue
            if previous is not None:
                self._log(f"< {previous}" if count == 1 else f"< {previous} ({count}x)")
            previous = cleaned
            count = 1
        if previous is not None:
            self._log(f"< {previous}" if count == 1 else f"< {previous} ({count}x)")

    def _require_connected(self) -> None:
        if not self._executor.is_open:
            raise RuntimeError("Bitte zuerst verbinden.")

    def _require_ready(self) -> None:
        self._require_connected()
        if not self.state.homed:
            raise RuntimeError("Bitte zuerst eine Referenzfahrt ausfuehren.")

    def _emit_progress(self, label: str, current: int, total: int) -> None:
        if self._progress is not None:
            self._progress(label, current, max(1, total))

    def _diagnostic_tx(self, message: str) -> None:
        if self._diagnostic_log is not None:
            self._diagnostic_log.tx(message)

    def _diagnostic_rx(self, message: str) -> None:
        if self._diagnostic_log is not None:
            self._diagnostic_log.rx(message)
        if self._active_consistency is not None:
            self._active_consistency.record_rx(message)

    def _record_consistency_tx(self, command: str, expects_ack: bool) -> None:
        if self._active_consistency is not None:
            self._active_consistency.record_tx(command, expects_ack=expects_ack)

    def _log_consistency_report(self, report: SerialConsistencyReport) -> None:
        status = "OK" if report.is_consistent else "WARNUNG"
        lines = [
            f"Kommunikationsabgleich {status}: "
            f"TX {report.tx_count} gesamt, "
            f"{report.status_query_count} Statusabfragen, "
            f"{report.expected_ack_count} erwartete Antworten, "
            f"{report.ok_count} ok, "
            f"{report.error_count} error, "
            f"{report.alarm_count} Alarm, "
            f"{report.status_count} Statusberichte.",
        ]
        if report.last_command_position and report.last_status_position:
            lines.append(
                "Endposition: "
                f"TX X{report.last_command_position[0]:.3f} Y{report.last_command_position[1]:.3f}, "
                f"RX X{report.last_status_position[0]:.3f} Y{report.last_status_position[1]:.3f}."
            )
        lines.extend(f"Abgleich-Warnung: {warning}" for warning in report.warnings)
        for line in lines:
            self._log(line)
            if self._diagnostic_log is not None:
                self._diagnostic_log.check(line)

    def _is_motion_command(self, command: str) -> bool:
        upper = command.strip().upper()
        if upper.startswith("$J="):
            return True
        head = upper.split(None, 1)[0]
        return head in {"G0", "G00", "G1", "G01", "G2", "G02", "G3", "G03"}

    def _priority_for_command(self, command: str) -> SerialPriority:
        upper = command.strip().upper()
        if upper == "?":
            return SerialPriority.STATUS
        if upper.startswith("$J=") or upper.startswith("$"):
            return SerialPriority.MANUAL
        if self._active_consistency is not None:
            return SerialPriority.JOB
        return SerialPriority.MANUAL

    def _log_serial_event(self, message: str) -> None:
        self._log(f"Serial: {message}")
        if self._diagnostic_log is not None:
            self._diagnostic_log.event(f"Serial: {message}")

    def shutdown(self) -> None:
        self._executor.shutdown()
