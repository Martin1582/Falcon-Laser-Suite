from laser_control.gcode import CUT_MODE, ENGRAVE_MODE
from laser_control.models import MaterialProfile
from laser_control.services.profile_service import ProfileService


def test_profile_service_returns_researched_cut_profile() -> None:
    service = ProfileService()

    cut_profile = service.profile_for("Lindenholz 2 mm", CUT_MODE)
    engrave_profile = service.profile_for("Lindenholz 2 mm", ENGRAVE_MODE)

    assert engrave_profile.power_percent == 40
    assert cut_profile.power_percent == 100
    assert cut_profile.speed_mm_min == 350


def test_profile_service_derives_cut_profile_for_user_material() -> None:
    service = ProfileService([MaterialProfile("User Birch", 60, 1200, 1)])

    cut_profile = service.profile_for("User Birch", CUT_MODE)

    assert cut_profile.power_percent == 80
    assert cut_profile.speed_mm_min == 720
    assert cut_profile.passes == 2


def test_profile_service_exports_and_imports_profiles(tmp_path) -> None:
    path = tmp_path / "profiles.json"
    service = ProfileService()
    service.upsert_mode_profile(MaterialProfile("Custom", 33, 1234, 2), ENGRAVE_MODE)

    service.export_profiles(str(path))
    imported = ProfileService([])
    imported.import_profiles(str(path))

    profile = imported.profile_for("Custom", ENGRAVE_MODE)
    assert profile.power_percent == 33
    assert profile.speed_mm_min == 1234


def test_profile_service_preserves_layer_type_and_notes(tmp_path) -> None:
    path = tmp_path / "profiles.json"
    service = ProfileService()
    service.upsert_mode_profile(MaterialProfile("Acrylic", 55, 900, 2, "Schnitt", "Use air assist"), CUT_MODE)

    service.export_profiles(str(path))
    imported = ProfileService([])
    imported.import_profiles(str(path))

    profile = imported.profile_for("Acrylic", CUT_MODE)
    assert profile.layer_type == "Schnitt"
    assert profile.notes == "Use air assist"


def test_profile_service_persists_new_material_and_loads_after_restart(tmp_path) -> None:
    path = tmp_path / "material_profiles.json"
    service = ProfileService(storage_path=path)

    service.upsert_mode_profile(
        MaterialProfile("Test Kunstleder", 18, 2500, 1, "Gravur", "Startwert", "Kunstleder", 1.5),
        ENGRAVE_MODE,
    )
    restarted = ProfileService(storage_path=path)

    profile = restarted.profile_for("Test Kunstleder", ENGRAVE_MODE)
    assert profile.power_percent == 18
    assert profile.speed_mm_min == 2500
    assert profile.material_type == "Kunstleder"
    assert profile.thickness_mm == 1.5


def test_profile_service_user_file_does_not_drop_defaults(tmp_path) -> None:
    path = tmp_path / "material_profiles.json"
    service = ProfileService(storage_path=path, base_profiles=[])
    service.upsert_mode_profile(MaterialProfile("User Only", 22, 1800, 1), ENGRAVE_MODE)

    restarted = ProfileService(storage_path=path)

    assert "User Only" in restarted.names()
    assert "Lindenholz 2 mm" in restarted.names()


def test_profile_service_handles_corrupt_json_with_defaults(tmp_path) -> None:
    path = tmp_path / "material_profiles.json"
    path.write_text("{kaputt", encoding="utf-8")
    messages: list[str] = []

    service = ProfileService(storage_path=path, log=messages.append)

    assert "Lindenholz 2 mm" in service.names()
    assert path.with_suffix(".json.corrupt").exists()
    assert any("Fallback auf Defaults" in message for message in messages)
