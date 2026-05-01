import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class JobHistoryEntry:
    timestamp: str
    material_name: str
    operation_mode: str
    power_percent: int
    speed_mm_min: int
    passes: int
    work_width_mm: float
    work_height_mm: float
    command_count: int
    movement_count: int
    estimated_runtime_seconds: float
    warning_count: int
    result: str
    notes: str = ""


def job_history_path() -> Path:
    override = os.environ.get("LASER_CONTROL_JOB_HISTORY")
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Laser Control" / "job_history.json"
    return Path(__file__).resolve().parent.parent / "job_history.json"


def load_job_history() -> list[JobHistoryEntry]:
    path = job_history_path()
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [JobHistoryEntry(**item) for item in data.get("jobs", [])]


def save_job_history(entries: list[JobHistoryEntry]) -> None:
    path = job_history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"jobs": [asdict(entry) for entry in entries]}, indent=2),
        encoding="utf-8",
    )


def append_job_history(entry: JobHistoryEntry) -> list[JobHistoryEntry]:
    entries = load_job_history()
    entries.append(entry)
    save_job_history(entries)
    return entries


def export_job_history(path: str) -> None:
    entries = load_job_history()
    Path(path).write_text(
        json.dumps({"version": 1, "jobs": [asdict(entry) for entry in entries]}, indent=2),
        encoding="utf-8",
    )


def import_job_history(path: str) -> list[JobHistoryEntry]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = [JobHistoryEntry(**item) for item in data.get("jobs", [])]
    save_job_history(entries)
    return entries


def now_timestamp() -> str:
    return datetime.now().replace(microsecond=0).isoformat()
