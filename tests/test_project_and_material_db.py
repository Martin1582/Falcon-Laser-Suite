import json

from laser_control.material_db import load_materials, save_materials
from laser_control.layers import JobLayer, LayerType, layer_from_dict, layer_to_dict
from laser_control.models import MaterialProfile
from laser_control.artwork_transform import ArtworkTransform
from laser_control.project import ArtworkItem, LaserProject, PROJECT_VERSION, laser_project_from_dict, load_project, project_to_dict, save_project


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


def test_project_persists_layer_state(tmp_path) -> None:
    layer = JobLayer(
        "Schnitt",
        LayerType.CUT,
        visible=True,
        enabled=True,
        speed_mm_min=500,
        power_percent=80,
        order=20,
        passes=3,
    )
    data = project_to_dict(
        100,
        80,
        MaterialProfile("Test", 20, 1000, 1),
        "G0 X0 Y0\nG1 X1 Y1",
        layers=[layer_to_dict(layer)],
    )
    path = tmp_path / "layered.laser.json"

    save_project(str(path), data)
    loaded = load_project(str(path))
    loaded_layer = layer_from_dict(loaded["layers"][0])

    assert loaded_layer.layer_type == LayerType.CUT
    assert loaded_layer.passes == 3
    assert loaded_layer.enabled


def test_project_persists_multiple_artwork_items(tmp_path) -> None:
    project = LaserProject(
        material_width_mm=100.0,
        material_height_mm=30.0,
        material_name="Kunstleder",
        items=[
            ArtworkItem(
                "logo",
                "Logo.svg",
                "svg",
                ArtworkTransform(5.0, 5.0, 1.0, 20.0, 10.0, 20.0, 10.0),
                source_path="logo.svg",
            ),
            ArtworkItem(
                "text",
                "Text.svg",
                "svg",
                ArtworkTransform(45.0, 8.0, 1.0, 40.0, 8.0, 40.0, 8.0),
                source_path="text.svg",
                visible=True,
                active=False,
            ),
        ],
    )
    data = project_to_dict(
        100,
        30,
        MaterialProfile("Kunstleder", 20, 1000, 1),
        "G0 X0 Y0",
        laser_project=project,
    )
    path = tmp_path / "multi.laser.json"

    save_project(str(path), data)
    loaded = load_project(str(path))
    loaded_project = laser_project_from_dict(loaded["laser_project"])

    assert loaded["version"] == PROJECT_VERSION
    assert len(loaded_project.items) == 2
    assert loaded_project.items[0].name == "Logo.svg"
    assert loaded_project.items[1].active is False


def test_project_loader_migrates_legacy_single_artwork_to_first_item(tmp_path) -> None:
    path = tmp_path / "legacy-artwork.laser.json"
    path.write_text(
        json.dumps(
            {
                "version": 2,
                "work_area": {"width_mm": 100, "height_mm": 30},
                "material_profile": {"name": "Kunstleder"},
                "gcode": "G0 X0 Y0",
                "imported_file": "logo.svg",
                "artwork_source": {
                    "file_name": "logo.svg",
                    "source_type": "vector",
                    "transform": {
                        "x_mm": 5,
                        "y_mm": 5,
                        "scale": 1,
                        "original_width_mm": 20,
                        "original_height_mm": 10,
                        "current_width_mm": 20,
                        "current_height_mm": 10,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = load_project(str(path))
    project = laser_project_from_dict(loaded["laser_project"])

    assert len(project.items) == 1
    assert project.items[0].name == "logo.svg"
    assert project.items[0].source_path == "logo.svg"
