from laser_control.gcode import ENGRAVE_MODE
from laser_control.layers import build_default_layers
from laser_control.machine_state import MachinePhase
from laser_control.models import LaserState, MaterialProfile
from laser_control.services.job_service import JobService
from laser_control.start_validation import HARDWARE_MODE, StartConditionValidator, StartValidationContext


def _context(
    *,
    state: LaserState | None = None,
    phase: MachinePhase = MachinePhase.IDLE,
    gcode: str = "G0 X0 Y0\nG1 X10 Y10 S400\nM5",
    profile: MaterialProfile | None = None,
    work_width: float = 100.0,
    work_height: float = 80.0,
    layers=None,
    prepared=None,
) -> StartValidationContext:
    profile = profile or MaterialProfile("Holz", 40, 1200, 1)
    layers = build_default_layers(profile, ENGRAVE_MODE) if layers is None else layers
    if prepared is None and gcode.strip():
        try:
            prepared = JobService().prepare_job(gcode, work_width, work_height, profile, ENGRAVE_MODE)
        except ValueError:
            prepared = None
    return StartValidationContext(
        connection_mode=HARDWARE_MODE,
        machine_phase=phase.value,
        controller_state=state or LaserState(connected=True, homed=True, status="Idle"),
        selected_port="COM3",
        gcode=gcode,
        layers=layers,
        material_profile=profile,
        work_width_mm=work_width,
        work_height_mm=work_height,
        prepared=prepared,
    )


def test_start_validation_blocks_disconnected_hardware() -> None:
    result = StartConditionValidator().validate(_context(state=LaserState(connected=False, homed=False)))

    assert not result.passed
    assert any("nicht verbunden" in item for item in result.blocking_errors)


def test_start_validation_blocks_non_idle_states() -> None:
    validator = StartConditionValidator()

    for phase in (MachinePhase.RUNNING, MachinePhase.PAUSED, MachinePhase.STOPPING, MachinePhase.ALARM, MachinePhase.ERROR):
        result = validator.validate(_context(phase=phase))
        assert not result.passed
        assert any("idle" in item or "nicht erlaubt" in item for item in result.blocking_errors)


def test_start_validation_blocks_missing_gcode_and_layers() -> None:
    layers = build_default_layers(MaterialProfile("Holz", 40, 1200, 1), ENGRAVE_MODE)
    for layer in layers:
        layer.enabled = False

    result = StartConditionValidator().validate(_context(gcode="", layers=layers, prepared=None))

    assert not result.passed
    assert any("Keine Jobdaten" in item for item in result.blocking_errors)
    assert any("Keine aktiven Layer" in item for item in result.blocking_errors)


def test_start_validation_blocks_work_area_overflow() -> None:
    result = StartConditionValidator().validate(_context(gcode="G0 X0 Y0\nG1 X200 Y10 S400\nM5"))

    assert not result.passed
    assert any("Arbeitsbereich" in item for item in result.blocking_errors)


def test_start_validation_blocks_invalid_layer_power_and_speed() -> None:
    profile = MaterialProfile("Holz", 40, 1200, 1)
    layers = build_default_layers(profile, ENGRAVE_MODE)
    layers[0].power_percent = 101
    layers[0].speed_mm_min = 0

    result = StartConditionValidator().validate(_context(layers=layers, profile=profile))

    assert not result.passed
    assert any("Laserleistung" in item for item in result.blocking_errors)
    assert any("Geschwindigkeit" in item for item in result.blocking_errors)


def test_start_validation_blocks_missing_homing_unless_explicitly_allowed() -> None:
    blocked = StartConditionValidator().validate(_context(state=LaserState(connected=True, homed=False, status="Idle")))
    allowed_context = _context(state=LaserState(connected=True, homed=False, status="Idle"))
    allowed_context = StartValidationContext(
        **{**allowed_context.__dict__, "homing_required": False, "allow_unhomed_start": True}
    )
    allowed = StartConditionValidator().validate(allowed_context)

    assert not blocked.passed
    assert any("Referenzfahrt" in item for item in blocked.blocking_errors)
    assert allowed.passed
    assert any("ohne erkannte Referenzfahrt" in item for item in allowed.warnings)


def test_start_validation_warns_when_homing_is_optional_but_unconfirmed() -> None:
    context = _context(state=LaserState(connected=True, homed=False, status="Idle"))
    context = StartValidationContext(**{**context.__dict__, "homing_required": False})

    result = StartConditionValidator().validate(context)

    assert result.passed
    assert any("Homing ist laut Maschinenprofil optional" in item for item in result.warnings)


def test_start_validation_allows_valid_hardware_start_conditions() -> None:
    result = StartConditionValidator().validate(_context())

    assert result.passed
    assert not result.blocking_errors


def test_start_validation_uses_machine_profile_limits() -> None:
    context = _context()
    context = StartValidationContext(**{**context.__dict__, "max_speed": 100, "max_power": 30})

    result = StartConditionValidator().validate(context)

    assert not result.passed
    assert any("Maschinenprofil" in item for item in result.blocking_errors)
