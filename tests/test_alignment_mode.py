import pytest

from laser_control.application_controller import ApplicationController
from laser_control.machine_state import MachinePhase


def _connected_app() -> ApplicationController:
    app = ApplicationController(lambda _message: None, None, lambda: "")
    app.connect()
    app.home()
    return app


def test_alignment_mode_enables_only_from_idle() -> None:
    app = _connected_app()

    app.enable_alignment_mode()

    assert app.is_alignment_mode_active()
    assert app.machine_state.alignment_mode_active


@pytest.mark.parametrize("phase", [MachinePhase.RUNNING, MachinePhase.PAUSED, MachinePhase.ALARM, MachinePhase.ERROR])
def test_alignment_mode_blocks_non_idle_phases(phase: MachinePhase) -> None:
    app = _connected_app()
    app.machine_state.transition(phase, phase.value)

    with pytest.raises(RuntimeError, match="Ausrichtmodus"):
        app.enable_alignment_mode()

    assert not app.is_alignment_mode_active()


def test_alignment_pointer_power_is_limited_to_safe_maximum() -> None:
    app = _connected_app()

    power = app.set_alignment_pointer_power(20)

    assert power == 5
    assert app.alignment_controller.pointer_power_percent == 5


def test_disconnect_disables_alignment_mode() -> None:
    app = _connected_app()
    app.enable_alignment_mode()

    app.disconnect()

    assert not app.is_alignment_mode_active()
    assert app.machine_state.phase == MachinePhase.DISCONNECTED


def test_jobstart_disables_alignment_mode_before_streaming() -> None:
    app = _connected_app()
    app.enable_alignment_mode()

    app.start_job("G21\nG90\nG0 X0 Y0\nG1 X1 Y1\nM5", 10.0, 10.0)

    assert not app.is_alignment_mode_active()


def test_emergency_stop_disables_alignment_mode() -> None:
    app = _connected_app()
    app.enable_alignment_mode()

    app.emergency_stop()

    assert not app.is_alignment_mode_active()
    assert app.machine_state.phase == MachinePhase.ALARM


def test_shutdown_controller_ensures_laser_off() -> None:
    app = _connected_app()
    app.enable_alignment_mode()

    app.shutdown_controller()

    assert not app.is_alignment_mode_active()
    assert app.machine_state.phase == MachinePhase.DISCONNECTED
