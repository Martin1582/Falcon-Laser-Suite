from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class MachineLogStatus(StrEnum):
    INFO = "INFO"
    OK = "OK"
    WARNING = "WARNUNG"
    ERROR = "FEHLER"


@dataclass
class MachineLogEntry:
    timestamp: str
    action: str
    status: MachineLogStatus
    details: str = ""
    error: str = ""

    def format(self) -> str:
        suffix_parts = []
        if self.details:
            suffix_parts.append(self.details)
        if self.error:
            suffix_parts.append(f"Fehler: {self.error}")
        suffix = f" - {' | '.join(suffix_parts)}" if suffix_parts else ""
        return f"{self.timestamp} [{self.status.value}] {self.action}{suffix}"


class MachineActionLog:
    def __init__(self) -> None:
        self.entries: list[MachineLogEntry] = []

    def record(
        self,
        action: str,
        status: MachineLogStatus = MachineLogStatus.INFO,
        details: str = "",
        error: str = "",
    ) -> MachineLogEntry:
        entry = MachineLogEntry(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            action=action,
            status=status,
            details=details,
            error=error,
        )
        self.entries.append(entry)
        return entry
