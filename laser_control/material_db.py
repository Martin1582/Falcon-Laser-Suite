import json
import os
from pathlib import Path


LEGACY_MATERIAL_DB_PATH = Path(__file__).resolve().parent.parent / "materials.json"


def material_db_path() -> Path:
    override = os.environ.get("LASER_CONTROL_MATERIAL_DB")
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Laser Control" / "materials.json"
    return LEGACY_MATERIAL_DB_PATH


def load_materials() -> list[dict]:
    path = material_db_path()
    source_path = path if path.exists() else LEGACY_MATERIAL_DB_PATH
    if not source_path.exists():
        return []
    data = json.loads(source_path.read_text(encoding="utf-8"))
    return data.get("materials", [])


def save_materials(materials: list[dict]) -> None:
    path = material_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"materials": materials}, indent=2), encoding="utf-8")


def upsert_material(record: dict) -> list[dict]:
    materials = load_materials()
    for index, existing in enumerate(materials):
        if existing.get("name") == record.get("name"):
            materials[index] = record
            break
    else:
        materials.append(record)
    save_materials(materials)
    return materials


def find_material(name: str) -> dict | None:
    return next((material for material in load_materials() if material.get("name") == name), None)


def delete_material(name: str) -> list[dict]:
    materials = [material for material in load_materials() if material.get("name") != name]
    save_materials(materials)
    return materials
