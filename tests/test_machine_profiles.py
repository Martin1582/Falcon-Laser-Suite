from laser_control.machine_profiles import (
    DEFAULT_MACHINE_PROFILE,
    MachineProfile,
    MachineProfileRepository,
    make_unique_profile_id,
    machine_profile_from_dict,
    machine_profile_to_dict,
    validate_machine_profile,
)


def test_machine_profile_defaults_are_conservative() -> None:
    profile = machine_profile_from_dict({})

    assert profile.machine_name == DEFAULT_MACHINE_PROFILE.machine_name
    assert profile.homing_required is True
    assert profile.machine_has_limit_switches is True
    assert profile.startup_requires_homing is True


def test_machine_profile_roundtrip_preserves_homing_rule() -> None:
    profile = machine_profile_from_dict(
        {
            "machine_name": "Test GRBL",
            "homing_required": False,
            "machine_has_limit_switches": False,
            "startup_requires_homing": False,
        }
    )

    data = machine_profile_to_dict(profile)

    assert data["machine_name"] == "Test GRBL"
    assert data["homing_required"] is False
    assert data["machine_has_limit_switches"] is False
    assert data["startup_requires_homing"] is False


def test_machine_profile_repository_saves_and_loads_active_profile(tmp_path) -> None:
    path = tmp_path / "machine_profiles.json"
    repository = MachineProfileRepository(path)
    profile = MachineProfile(
        profile_id="test-machine",
        name="Test Machine",
        machine_name="Test GRBL",
        controller_type="GRBL ueber USB",
        work_area_width=123.0,
        work_area_height=45.0,
        default_port="COM9",
        baudrate=57600,
        homing_required=False,
    )

    repository.upsert_profile(profile)
    repository.set_active_profile("test-machine")
    loaded = MachineProfileRepository(path)

    assert loaded.active_profile().profile_id == "test-machine"
    assert loaded.active_profile().baudrate == 57600
    assert loaded.active_profile().homing_required is False


def test_machine_profile_repository_falls_back_to_default_for_missing_active(tmp_path) -> None:
    path = tmp_path / "machine_profiles.json"
    path.write_text('{"version": 1, "active_profile_id": "missing", "profiles": []}', encoding="utf-8")

    repository = MachineProfileRepository(path)

    assert repository.active_profile().profile_id == DEFAULT_MACHINE_PROFILE.profile_id


def test_machine_profile_repository_handles_corrupt_json(tmp_path) -> None:
    path = tmp_path / "machine_profiles.json"
    path.write_text("{not json", encoding="utf-8")

    repository = MachineProfileRepository(path)

    assert repository.load_error
    assert repository.active_profile().profile_id == DEFAULT_MACHINE_PROFILE.profile_id


def test_machine_profile_validation_blocks_invalid_values() -> None:
    profile = MachineProfile(
        profile_id="bad",
        name="",
        machine_name="",
        work_area_width=0.0,
        work_area_height=-1.0,
        baudrate=1,
        max_speed=0,
        max_power=150,
    )

    errors = validate_machine_profile(profile)

    assert "Profilname darf nicht leer sein." in errors
    assert "Arbeitsbereich muss groesser als 0 mm sein." in errors
    assert "Maximale Laserleistung muss zwischen 1 und 100 Prozent liegen." in errors


def test_machine_profile_repository_rejects_invalid_profile(tmp_path) -> None:
    path = tmp_path / "machine_profiles.json"
    repository = MachineProfileRepository(path)

    try:
        repository.upsert_profile(MachineProfile(profile_id="invalid", name="", machine_name="Test"))
    except ValueError as exc:
        assert "Profilname darf nicht leer sein" in str(exc)
    else:
        raise AssertionError("Invalid machine profile was saved")


def test_machine_profile_unique_id_gets_suffix() -> None:
    profile_id = make_unique_profile_id("Test Machine", {"test-machine", "test-machine-2"})

    assert profile_id == "test-machine-3"


def test_machine_profile_from_dict_clamps_unsafe_loaded_values() -> None:
    profile = machine_profile_from_dict(
        {
            "machine_name": "Loaded",
            "controller_type": "unknown",
            "work_area_width": -10,
            "baudrate": 1,
            "homing_required": "false",
            "max_speed": 999999,
            "max_power": 150,
        }
    )

    assert profile.controller_type == DEFAULT_MACHINE_PROFILE.controller_type
    assert profile.work_area_width == 1.0
    assert profile.baudrate == 1200
    assert profile.homing_required is False
    assert profile.max_speed == 200000
    assert profile.max_power == 100
