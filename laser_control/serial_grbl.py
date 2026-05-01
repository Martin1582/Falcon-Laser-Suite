import re
import time
from collections.abc import Callable

from laser_control.gcode import build_safe_frame_gcode, prepare_job_gcode
from laser_control.models import LaserState

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover - depends on local installation
    serial = None
    list_ports = None


LogFn = Callable[[str], None]
ProgressFn = Callable[[str, int, int], None]
NUMBER_PATTERN = r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)"
POSITION_RE = re.compile(rf"[MW]Pos:({NUMBER_PATTERN}),({NUMBER_PATTERN}),{NUMBER_PATTERN}")
STATUS_RE = re.compile(r"<([^|>]+)")


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
    ) -> None:
        self.state = LaserState()
        self._log = log
        self._progress = progress
        self._port_getter = port_getter
        self._baudrate = baudrate
        self._serial = None

    def connect(self) -> None:
        self._emit_progress("Verbinde", 0, 1)
        if serial is None:
            raise RuntimeError("pyserial fehlt. Bitte zuerst 'py -m pip install -r requirements.txt' ausfuehren.")

        port = port_device(self._port_getter())
        if not port:
            raise RuntimeError("Bitte zuerst einen COM-Port auswaehlen.")

        self.disconnect(log_message=False)
        self._log(f"Verbinde mit {port} bei {self._baudrate} Baud...")
        self._serial = serial.Serial(port=port, baudrate=self._baudrate, timeout=0.5, write_timeout=1.0)
        time.sleep(1.8)
        self._serial.reset_input_buffer()

        self._send_raw("\r\n\r\n")
        banner = self._read_available(wait_seconds=0.6)
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
        if self._serial is not None:
            try:
                if self._serial.is_open:
                    self._serial.close()
            finally:
                self._serial = None
        self.state = LaserState()
        if log_message:
            self._log("GRBL getrennt.")
        self._emit_progress("Getrennt", 0, 1)

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

    def frame(self, width_mm: float, height_mm: float) -> None:
        self._require_ready()
        commands = build_safe_frame_gcode(width_mm, height_mm)
        self._log(f"Starte sichere Rahmenfahrt ohne Laser: {width_mm:.0f} x {height_mm:.0f} mm.")
        for index, command in enumerate(commands, start=1):
            self._emit_progress("Rahmenfahrt", index - 1, len(commands))
            self.send_command(command, wait_seconds=5.0)
        self._wait_until_idle(timeout_seconds=60.0)
        self._log("Rahmenfahrt abgeschlossen.")
        self._emit_progress("Bereit", len(commands), len(commands))

    def start_job(self, gcode: str, width_mm: float, height_mm: float) -> None:
        self._require_ready()
        commands = prepare_job_gcode(gcode, width_mm, height_mm)
        self._log_hardware_job_summary(commands, width_mm, height_mm)
        try:
            status_before = self._query_status_text()
            if status_before:
                self._update_state_from_status(status_before)
                self._log("Status vor Jobstart:")
                self._log_response(status_before)
                if self.state.alarm:
                    raise RuntimeError("Controller ist im Alarm-Zustand. Bitte Ursache beheben und erneut homen.")

            for index, command in enumerate(commands, start=1):
                self._emit_progress("Job laeuft", index - 1, len(commands))
                self._log(f"Job {index}/{len(commands)}")
                self.send_command(command, wait_seconds=10.0)

                if index == 1 or index == min(5, len(commands)):
                    status = self._query_status_text()
                    if status:
                        self._update_state_from_status(status)
                        self._log(f"Status nach Zeile {index}:")
                        self._log_response(status)

            self._wait_until_idle(timeout_seconds=120.0)
            final_status = self._query_status_text()
            if final_status:
                self._update_state_from_status(final_status)
                self._log("Status nach Jobende:")
                self._log_response(final_status)
            self._log("Hardware-Job abgeschlossen.")
            self._emit_progress("Bereit", len(commands), len(commands))
        except Exception:
            self._emit_progress("Fehler", 0, 1)
            self._log("Job abgebrochen. Sende Laser aus.")
            self.send_command("M5")
            raise

    def pause(self) -> None:
        self._require_connected()
        self._send_raw("!")
        self.state.paused = True
        self._log("Feed hold gesendet.")
        self._emit_progress("Pausiert", 0, 1)

    def resume(self) -> None:
        self._require_connected()
        self._send_raw("~")
        response = self._read_available(wait_seconds=1.0)
        self._log_response(response)
        self.state.paused = False
        self._log("Fortsetzen gesendet.")
        self._emit_progress("Fortsetzen", 0, 1)

    def stop(self) -> None:
        self._require_connected()
        self._send_raw("\x18")
        time.sleep(1.0)
        response = self._read_available(wait_seconds=1.0)
        self._log_response(response)
        self.state.homed = False
        self.state.paused = False
        self._log("Stop/Reset gesendet. Bitte vor weiterer Bewegung erneut Referenzfahrt ausfuehren.")
        self._emit_progress("Gestoppt", 0, 1)

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
        self._update_state_from_status(response)
        self._log_response(response)
        match = POSITION_RE.search(response)
        if not match:
            raise RuntimeError("Keine Position im Statusreport gefunden.")
        x = float(match.group(1))
        y = float(match.group(2))
        self.state.x_mm = x
        self.state.y_mm = y
        return x, y

    def query_settings(self) -> None:
        self._require_connected()
        response = self.query("$$", wait_seconds=2.0, log_command=True)
        self._log_response(response)

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
        self._send_line(command, log_command=log_command)
        return self._read_until_ok_or_error(wait_seconds)

    def _send_line(self, command: str, log_command: bool) -> None:
        if log_command:
            self._log(f"> {command}")
        self._send_raw(command.strip() + "\n")

    def _send_raw(self, value: str) -> None:
        if self._serial is None or not self._serial.is_open:
            raise RuntimeError("Nicht verbunden.")
        self._serial.write(value.encode("ascii"))
        self._serial.flush()

    def _read_until_ok_or_error(self, wait_seconds: float) -> str:
        end_time = time.monotonic() + wait_seconds
        lines = []
        while time.monotonic() < end_time:
            line = self._clean_response_text(self._serial.readline().decode("ascii", errors="replace")).strip()
            if not line:
                continue
            lines.append(line)
            lowered = line.lower()
            if lowered == "ok" or lowered.startswith("error:"):
                break
        return "\n".join(lines)

    def _read_available(self, wait_seconds: float = 0.2) -> str:
        end_time = time.monotonic() + wait_seconds
        chunks = []
        while time.monotonic() < end_time:
            waiting = self._serial.in_waiting
            if waiting:
                chunks.append(self._clean_response_text(self._serial.read(waiting).decode("ascii", errors="replace")))
            else:
                time.sleep(0.05)
        return "".join(chunks).strip()

    def _clean_response_text(self, value: str) -> str:
        return value.replace("\x1b[0;31m", "").replace("\x1b[0m", "")

    def _query_status_text(self) -> str:
        self._send_raw("?")
        return self._read_available(wait_seconds=0.6)

    def _wait_until_idle(self, timeout_seconds: float) -> None:
        end_time = time.monotonic() + timeout_seconds
        last_status = ""
        while time.monotonic() < end_time:
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

    def _looks_like_grbl(self, response: str) -> bool:
        lowered = response.lower()
        has_grbl_identity = "grbl" in lowered or "[ver:" in lowered or "[opt:" in lowered
        has_status_report = "<" in response and ">" in response and ("mpos:" in lowered or "wpos:" in lowered)
        has_command_ack = any(line.strip().lower() == "ok" for line in response.splitlines())
        return has_grbl_identity or has_status_report or has_command_ack

    def _is_hold_status(self, response: str) -> bool:
        return "<Hold" in response

    def _update_state_from_status(self, response: str) -> None:
        status_match = STATUS_RE.search(response)
        if status_match:
            self.state.status = status_match.group(1)
            self.state.paused = self.state.status.startswith("Hold")
            self.state.alarm = self.state.status.startswith("Alarm")
        position_match = POSITION_RE.search(response)
        if position_match:
            self.state.x_mm = float(position_match.group(1))
            self.state.y_mm = float(position_match.group(2))

    def _combine_responses(self, *responses: str) -> str:
        lines = []
        for response in responses:
            for line in response.splitlines():
                cleaned = line.strip()
                if cleaned:
                    lines.append(cleaned)
        return "\n".join(lines)

    def _log_hardware_job_summary(self, commands: list[str], width_mm: float, height_mm: float) -> None:
        port = getattr(self._serial, "port", port_device(self._port_getter()))
        upper_commands = [command.upper() for command in commands]
        movement_commands = [
            command
            for command in commands
            if command.upper().startswith(("G0", "G1", "G2", "G3", "$J="))
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
        if self._serial is None or not self._serial.is_open:
            raise RuntimeError("Bitte zuerst verbinden.")

    def _require_ready(self) -> None:
        self._require_connected()
        if not self.state.homed:
            raise RuntimeError("Bitte zuerst eine Referenzfahrt ausfuehren.")

    def _emit_progress(self, label: str, current: int, total: int) -> None:
        if self._progress is not None:
            self._progress(label, current, max(1, total))
