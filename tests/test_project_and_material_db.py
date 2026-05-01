import json

from laser_control.material_db import load_materials, save_materials
from laser_control.models import MaterialProfile
from laser_control.project import PROJECT_VERSION, load_project, project_to_dict, save_project


def test_project_v2_persists_operation_mode(tmp_path) -> None:
    path = tmp_path / "job.laser.json"
    data = project_to_dict(100, 80, MaterialProfile("Test", 20, 1000, 1), "G0 X0 Y0", operation_mode="cutten")

    save_project(str(path), data)
    loaded = load_project(str(path))

    assert loaded["version"] == PROJECT_VERSION
    assert loaded["operation_mode"] == "cutten"


def test_project_loader_accepts_v1_without_operation_mode(tmp_path) -> None:
    path = tmp_path / "legacy.laser.json"
    path.write_text(json.dumps({"version": 1, "work_area": {}, "material_profile": {}, "gcode": ""}), encoding="utf-8")

    loaded = load_project(str(path))

    assert loaded["operation_mode"] is None


def test_material_db_uses_configurable_path(tmp_path, monkeypatch) -> None:
    path = tmp_path / "materials.json"
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(path))

    save_materials([{"name": "Probe", "width_mm": 10}])

    assert load_materials()[0]["name"] == "Probe"
    assert path.exists()
