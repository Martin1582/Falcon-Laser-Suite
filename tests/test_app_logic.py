from laser_control.app import build_cut_mode_warnings, derive_cut_profile_from_engrave
from laser_control.models import MaterialProfile


def test_derive_cut_profile_from_engrave_applies_safer_cut_bias() -> None:
    engrave = MaterialProfile(name="Birch", power_percent=60, speed_mm_min=1200, passes=1)

    cut = derive_cut_profile_from_engrave(engrave)

    assert cut.name == engrave.name
    assert cut.power_percent == 80
    assert cut.speed_mm_min == 720
    assert cut.passes == 2


def test_build_cut_mode_warnings_returns_expected_threshold_messages() -> None:
    warnings = build_cut_mode_warnings(power_percent=95, speed_mm_min=250, passes=5)

    assert len(warnings) == 3
    assert any("Leistung" in item for item in warnings)
    assert any("Geschwindigkeit" in item for item in warnings)
    assert any("Durchgaenge" in item for item in warnings)
