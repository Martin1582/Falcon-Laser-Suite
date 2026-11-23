from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from laser_control.artwork_transform import ArtworkTransform
from laser_control.json_store import read_json_object, write_json_object
from laser_control.models import MaterialProfile


PROJECT_VERSION = 3


@dataclass
class ArtworkItem:
    item_id: str
    name: str
    source_type: str
    transform: ArtworkTransform
    source_path: str | None = None
    layer_assignments: dict = field(default_factory=dict)
    visible: bool = True
    active: bool = True
    source_data: dict = field(default_factory=dict)

    @property
    def is_vector(self) -> bool:
        return self.source_type in {"svg", "vector"}

    @property
    def is_raster(self) -> bool:
        return self.source_type in {"png", "jpg", "jpeg", "raster"}


@dataclass
class LaserProject:
    material_width_mm: float
    material_height_mm: float
    material_name: str = ""
    items: list[ArtworkItem] = field(default_factory=list)

    @property
    def active_items(self) -> list[ArtworkItem]:
        return [item for item in self.items if item.active]


def new_item_id() -> str:
    return uuid4().hex


def transform_to_dict(transform: ArtworkTransform) -> dict:
    return {
        "x_mm": transform.x_mm,
        "y_mm": transform.y_mm,
        "scale": transform.scale,
        "scale_x": transform.scale_x,
        "scale_y": transform.scale_y,
        "uniform_scale": transform.uniform_scale,
        "rotation_deg": transform.rotation_deg,
        "original_width_mm": transform.original_width_mm,
        "original_height_mm": transform.original_height_mm,
        "current_width_mm": transform.current_width_mm,
        "current_height_mm": transform.current_height_mm,
        "autofit_applied": transform.autofit_applied,
        "aspect_locked": transform.aspect_locked,
        "keep_aspect_ratio": transform.keep_aspect_ratio,
        "origin_mode": transform.origin_mode,
    }


def transform_from_dict(data: dict) -> ArtworkTransform:
    transform = ArtworkTransform(
        x_mm=float(data.get("x_mm", 0.0)),
        y_mm=float(data.get("y_mm", 0.0)),
        scale=float(data.get("scale", data.get("uniform_scale", 1.0))),
        original_width_mm=float(data.get("original_width_mm", data.get("current_width_mm", 1.0))),
        original_height_mm=float(data.get("original_height_mm", data.get("current_height_mm", 1.0))),
        current_width_mm=float(data.get("current_width_mm", data.get("original_width_mm", 1.0))),
        current_height_mm=float(data.get("current_height_mm", data.get("original_height_mm", 1.0))),
        rotation_deg=float(data.get("rotation_deg", 0.0)),
        autofit_applied=bool(data.get("autofit_applied", False)),
        aspect_locked=bool(data.get("aspect_locked", data.get("keep_aspect_ratio", True))),
        scale_x=float(data["scale_x"]) if data.get("scale_x") is not None else None,
        scale_y=float(data["scale_y"]) if data.get("scale_y") is not None else None,
        uniform_scale=float(data["uniform_scale"]) if data.get("uniform_scale") is not None else None,
        keep_aspect_ratio=bool(data.get("keep_aspect_ratio", True)),
        origin_mode=str(data.get("origin_mode", "lower_left")),
    )
    transform.validate()
    return transform


def artwork_item_to_dict(item: ArtworkItem) -> dict:
    return {
        "item_id": item.item_id,
        "name": item.name,
        "source_type": item.source_type,
        "source_path": item.source_path,
        "transform": transform_to_dict(item.transform),
        "layer_assignments": item.layer_assignments,
        "visible": item.visible,
        "active": item.active,
        "source_data": item.source_data,
    }


def artwork_item_from_dict(data: dict) -> ArtworkItem:
    return ArtworkItem(
        item_id=str(data.get("item_id") or new_item_id()),
        name=str(data.get("name") or data.get("file_name") or "Motiv"),
        source_type=str(data.get("source_type", "future")),
        source_path=data.get("source_path"),
        transform=transform_from_dict(data.get("transform") or {}),
        layer_assignments=dict(data.get("layer_assignments") or {}),
        visible=bool(data.get("visible", True)),
        active=bool(data.get("active", True)),
        source_data=dict(data.get("source_data") or {}),
    )


def laser_project_to_dict(project: LaserProject) -> dict:
    return {
        "material_width_mm": project.material_width_mm,
        "material_height_mm": project.material_height_mm,
        "material_name": project.material_name,
        "items": [artwork_item_to_dict(item) for item in project.items],
    }


def laser_project_from_dict(data: dict) -> LaserProject:
    return LaserProject(
        material_width_mm=float(data.get("material_width_mm", data.get("width_mm", 1.0))),
        material_height_mm=float(data.get("material_height_mm", data.get("height_mm", 1.0))),
        material_name=str(data.get("material_name", "")),
        items=[artwork_item_from_dict(item) for item in data.get("items", [])],
    )


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
    layers: list | None = None,
    artwork_source: dict | None = None,
    laser_project: LaserProject | dict | None = None,
) -> dict:
    project_payload = laser_project_to_dict(laser_project) if isinstance(laser_project, LaserProject) else laser_project
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
        "layers": layers or [],
        "artwork_source": artwork_source,
        "laser_project": project_payload,
    }


def save_project(path: str, data: dict) -> None:
    write_json_object(path, data)


def load_project(path: str) -> dict:
    data = read_json_object(Path(path))
    if data.get("version") not in (1, 2, PROJECT_VERSION):
        raise ValueError("Nicht unterstuetzte Projektversion.")
    data.setdefault("operation_mode", None)
    data.setdefault("layers", [])
    data.setdefault("artwork_source", None)
    data.setdefault("laser_project", _legacy_laser_project(data))
    return data


def _legacy_laser_project(data: dict) -> dict:
    work_area = data.get("work_area") or {}
    width = float(work_area.get("width_mm", 1.0))
    height = float(work_area.get("height_mm", 1.0))
    material = data.get("material_profile") or {}
    artwork_data = data.get("artwork_source") or {}
    transform_data = artwork_data.get("transform") or {}
    if not artwork_data or not transform_data:
        return {
            "material_width_mm": width,
            "material_height_mm": height,
            "material_name": str(material.get("name", "")),
            "items": [],
        }
    item = {
        "item_id": new_item_id(),
        "name": str(artwork_data.get("file_name") or data.get("imported_file") or "Motiv"),
        "source_type": str(artwork_data.get("source_type", "future")),
        "source_path": data.get("imported_file"),
        "transform": transform_data,
        "layer_assignments": {},
        "visible": True,
        "active": True,
        "source_data": artwork_data,
    }
    return {
        "material_width_mm": width,
        "material_height_mm": height,
        "material_name": str(material.get("name", "")),
        "items": [item],
    }
