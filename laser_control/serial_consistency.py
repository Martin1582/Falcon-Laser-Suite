import re
from dataclasses import dataclass, field


NUMBER_PATTERN = r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)"
MOVE_RE = re.compile(rf"^(?:G0|G1|G00|G01)\b", re.IGNORECASE)
X_RE = re.compile(rf"\bX({NUMBER_PATTERN})", re.IGNORECASE)
Y_RE = re.compile(rf"\bY({NUMBER_PATTERN})", re.IGNORECASE)
STATUS_POSITION_RE = re.compile(rf"[MW]Pos:({NUMBER_PATTERN}),({NUMBER_PATTERN}),{NUMBER_PATTERN}", re.IGNORECASE)


@dataclass
class SerialConsistencyReport:
    label: str
    tx_count: int
    status_query_count: int
    expected_ack_count: int
    ok_count: int
    error_count: int
    alarm_count: int
    status_count: int
    last_command_position: tuple[float, float] | None
    last_status_position: tuple[float, float] | None
    warnings: list[str] = field(default_factory=list)

    @property
    def missing_ack_count(self) -> int:
        return max(0, self.expected_ack_count - self.ok_count - self.error_count)

    @property
    def is_consistent(self) -> bool:
        return not self.warnings


class SerialConsistencyTracker:
    def __init__(self, label: str, position_tolerance_mm: float = 0.15) -> None:
        self.label = label
        self.position_tolerance_mm = position_tolerance_mm
        self.tx_count = 0
        self.status_query_count = 0
        self.expected_ack_count = 0
        self.ok_count = 0
        self.error_count = 0
        self.alarm_count = 0
        self.status_count = 0
        self.last_command_position: tuple[float, float] | None = None
        self.last_status_position: tuple[float, float] | None = None
        self._modal_x: float | None = None
        self._modal_y: float | None = None

    def record_tx(self, command: str, expects_ack: bool) -> None:
        clean = command.strip()
        self.tx_count += 1
        if clean == "?":
            self.status_query_count += 1
        if expects_ack:
            self.expected_ack_count += 1
        self._record_motion_command(clean)

    def record_rx(self, response: str) -> None:
        for line in response.splitlines():
            clean = line.strip()
            if not clean:
                continue
            lowered = clean.lower()
            if lowered == "ok":
                self.ok_count += 1
            elif lowered.startswith("error:"):
                self.error_count += 1
            elif "alarm" in lowered:
                self.alarm_count += 1
            position_match = STATUS_POSITION_RE.search(clean)
            if position_match:
                self.status_count += 1
                self.last_status_position = (float(position_match.group(1)), float(position_match.group(2)))

    def report(self) -> SerialConsistencyReport:
        warnings = []
        missing_ack_count = max(0, self.expected_ack_count - self.ok_count - self.error_count)
        if missing_ack_count:
            warnings.append(f"{missing_ack_count} erwartete OK/Fehler-Antwort(en) fehlen.")
        if self.ok_count > self.expected_ack_count:
            warnings.append(f"{self.ok_count - self.expected_ack_count} unerwartete OK-Antwort(en) empfangen.")
        if self.error_count:
            warnings.append(f"{self.error_count} GRBL-Fehlerantwort(en) empfangen.")
        if self.alarm_count:
            warnings.append(f"{self.alarm_count} Alarmmeldung(en) empfangen.")
        if self.last_command_position is not None and self.last_status_position is not None:
            dx = abs(self.last_command_position[0] - self.last_status_position[0])
            dy = abs(self.last_command_position[1] - self.last_status_position[1])
            if dx > self.position_tolerance_mm or dy > self.position_tolerance_mm:
                warnings.append(
                    "Endposition weicht ab: "
                    f"TX X{self.last_command_position[0]:.3f} Y{self.last_command_position[1]:.3f}, "
                    f"RX X{self.last_status_position[0]:.3f} Y{self.last_status_position[1]:.3f}."
                )
        return SerialConsistencyReport(
            label=self.label,
            tx_count=self.tx_count,
            status_query_count=self.status_query_count,
            expected_ack_count=self.expected_ack_count,
            ok_count=self.ok_count,
            error_count=self.error_count,
            alarm_count=self.alarm_count,
            status_count=self.status_count,
            last_command_position=self.last_command_position,
            last_status_position=self.last_status_position,
            warnings=warnings,
        )

    def _record_motion_command(self, command: str) -> None:
        if not MOVE_RE.match(command):
            return
        x_match = X_RE.search(command)
        y_match = Y_RE.search(command)
        if x_match:
            self._modal_x = float(x_match.group(1))
        if y_match:
            self._modal_y = float(y_match.group(1))
        if self._modal_x is not None and self._modal_y is not None:
            self.last_command_position = (self._modal_x, self._modal_y)
