from laser_control.profiles import DEFAULT_CUT_PROFILES, DEFAULT_PROFILES


def test_default_material_profiles_have_matching_cut_presets_for_cuttable_materials() -> None:
    engraving_names = {profile.name for profile in DEFAULT_PROFILES}

    assert "Lindenholz 2 mm" in engraving_names
    assert "Acryl schwarz 4.5 mm" in engraving_names
    assert DEFAULT_CUT_PROFILES["Lindenholz 2 mm"].power_percent == 100
    assert DEFAULT_CUT_PROFILES["Lindenholz 2 mm"].speed_mm_min == 350
    assert DEFAULT_CUT_PROFILES["Acryl schwarz 4.5 mm"].passes == 2
