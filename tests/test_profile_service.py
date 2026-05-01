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
