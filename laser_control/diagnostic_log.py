import os
import shutil
import threading
from datetime import datetime
from pathlib import Path


class DiagnosticLog:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else self._default_path()
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def app(self, message: str) -> None:
        self.write("APP", message)

    def tx(self, message: str) -> None:
        self.write("TX", message)

    def rx(self, message: str) -> None:
        self.write("RX", message)

    def event(self, message: str) -> None:
        self.write("EVENT", message)

    def job(self, message: str) -> None:
        self.write("JOB", message)

    def check(self, message: str) -> None:
        self.write("CHECK", message)

    def write(self, category: str, message: str) -> None:
        timestamp = datetime.now().isoformat(timespec="milliseconds")
        lines = str(message).splitlines() or [""]
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                for line in lines:
                    handle.write(f"{timestamp} [{category}] {line}\n")

    def export_to(self, target_path: str | Path) -> Path:
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.path, target)
        return target

    def _default_path(self) -> Path:
        configured = os.getenv("LASER_CONTROL_DIAGNOSTIC_LOG")
        if configured:
            return Path(configured)
        appdata = os.getenv("APPDATA")
        root = Path(appdata) / "Laser Control" if appdata else Path.home() / ".laser_control"
        filename = f"laser-control-{datetime.now().date().isoformat()}.log"
        return root / "logs" / filename
