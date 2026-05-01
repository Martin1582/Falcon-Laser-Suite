import json
from pathlib import Path

from laser_control.models import MaterialProfile


PROJECT_VERSION = 2


def project_to_dict(
    width_mm: float,
    height_mm: float,
    profile: MaterialProfile,
    gcode: str,
    imported_paths: list | None = None,
    imported_file: str | None = None,
    material_measurement: dict | None = None,
    svg_placement: dict | None = None,
    operation_mode: str | None = None,
) -> dict:
    return {
        "version": PROJECT_VERSION,
        "work_area": {
            "width_mm": width_mm,
            "height_mm": height_mm,
        },
        "material_profile": {
            "name": profile.name,
            "power_percent": profile.power_percent,
            "speed_mm_min": profile.speed_mm_min,
            "passes": profile.passes,
        },
        "gcode": gcode,
        "imported_paths": imported_paths or [],
        "imported_file": imported_file,
        "material_measurement": material_measurement,
        "svg_placement": svg_placement,
        "operation_mode": operation_mode,
    }


def save_project(path: str, data: dict) -> None:
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_project(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("version") not in (1, PROJECT_VERSION):
        raise ValueError("Nicht unterstuetzte Projektversion.")
    data.setdefault("operation_mode", None)
    return data
