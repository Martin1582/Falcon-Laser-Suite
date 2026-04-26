import json
from pathlib import Path


MATERIAL_DB_PATH = Path("materials.json")


def load_materials() -> list[dict]:
    if not MATERIAL_DB_PATH.exists():
        return []
    data = json.loads(MATERIAL_DB_PATH.read_text(encoding="utf-8"))
    return data.get("materials", [])


def save_materials(materials: list[dict]) -> None:
    MATERIAL_DB_PATH.write_text(json.dumps({"materials": materials}, indent=2), encoding="utf-8")


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
