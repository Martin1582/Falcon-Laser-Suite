from laser_control.application_controller import ApplicationController
from laser_control.controller_interface import LaserController
from laser_control.job_controller import JobState
from laser_control.laser import SimulatedLaserController
from laser_control.machine_state import MachineEvent, MachineEventType, MachinePhase
from laser_control.models import LaserState


class AutoHomeController:
    def __init__(self) -> None:
        self.state = LaserState(connected=True, homed=True, status="Idle")
        self.calls: list[str] = []
        self.serial_queue_empty = True

    def start_job(self, _gcode: str, _width_mm: float, _height_mm: float) -> None:
        self.calls.append("start_job")
        self.state.status = "Idle"

    def workspace_trace_laser_off(self) -> None:
        self.calls.extend(["M5", "S0"])

    def home(self) -> None:
        self.calls.append("$H")
        self.state.homed = True
        self.state.status = "Idle"

    def get_status(self) -> LaserState:
        return self.state


def test_application_controller_uses_common_controller_protocol() -> None:
    messages: list[str] = []
    app = ApplicationController(messages.append, None, lambda: "")

    assert isinstance(app.controller, LaserController)

    app.connect()
    assert app.machine_state.phase == MachinePhase.IDLE

    app.disconnect()
    assert app.machine_state.phase == MachinePhase.DISCONNECTED


def test_simulator_exposes_unified_machine_api() -> None:
    controller = SimulatedLaserController(lambda _message: None)

    controller.connect()
    controller.home()
    controller.frame(100.0, 80.0)
    controller.start_job("G21\nG90\nG0 X0 Y0\nG1 X1 Y1\nM5", 100.0, 80.0)
    controller.emergency_stop()

    assert controller.get_status().connected


def test_application_controller_blocks_invalid_machine_action() -> None:
    messages: list[str] = []
    app = ApplicationController(messages.append, None, lambda: "")

    try:
        app.run_machine_action("Job gestartet", lambda controller: controller.start_job("", 1.0, 1.0))
    except RuntimeError as exc:
        assert "nicht erlaubt" in str(exc)
    else:
        raise AssertionError("Invalid start action was not blocked")

    assert app.machine_state.phase == MachinePhase.DISCONNECTED
    assert app.job_controller.state == JobState.IDLE
    assert any("Blockierte Maschinenaktion" in message for message in messages)


def test_application_controller_maps_grbl_run_status_to_running() -> None:
    app = ApplicationController(lambda _message: None, None, lambda: "")
    app.controller.state = LaserState(connected=True, homed=True, status="Run")
    app.machine_state.transition(MachinePhase.IDLE, "Bereit")

    app.sync_from_controller()

    assert app.machine_state.phase == MachinePhase.RUNNING


def test_application_controller_handles_status_events_for_machine_and_job_state() -> None:
    messages: list[str] = []
    app = ApplicationController(messages.append, None, lambda: "")
    app.machine_state.transition(MachinePhase.IDLE, "Bereit")
    app.job_controller.transition(JobState.STREAMING, "test")

    app.handle_machine_event(MachineEvent(MachineEventType.STATUS, MachinePhase.PAUSED, "Hold"))

    assert app.machine_state.phase == MachinePhase.PAUSED
    assert app.job_controller.state == JobState.PAUSED
    assert any("MachineState" in message for message in messages)
    assert any("JobState" in message for message in messages)


def test_application_controller_logs_error_events_even_without_phase_change() -> None:
    messages: list[str] = []
    app = ApplicationController(messages.append, None, lambda: "")
    app.machine_state.transition(MachinePhase.ERROR, "Fehler")
    app.job_controller.transition(JobState.STREAMING, "test")

    app.handle_machine_event(MachineEvent(MachineEventType.ERROR, MachinePhase.ERROR, "error:1"))

    assert app.job_controller.state == JobState.FAILED
    assert any("MachineEvent: error" in message for message in messages)


def test_application_controller_blocks_hardware_start_without_confirmed_preflight() -> None:
    messages: list[str] = []
    app = ApplicationController(messages.append, None, lambda: "COM3")
    app.connection_mode = "GRBL ueber USB"
    app.controller.state = LaserState(connected=True, homed=True, status="Idle")
    app.machine_state.transition(MachinePhase.IDLE, "Bereit")

    try:
        app.start_job("G21\nG90\nG0 X0 Y0\nM5", 10.0, 10.0)
    except RuntimeError as exc:
        assert "Preflight" in str(exc)
    else:
        raise AssertionError("Hardware start without confirmed preflight was not blocked")

    assert any("Preflight" in message for message in messages)


def test_application_controller_emergency_stop_sets_alarm_and_aborted_job() -> None:
    app = ApplicationController(lambda _message: None, None, lambda: "")
    app.connect()
    app.home()

    app.emergency_stop()

    assert app.machine_state.phase == MachinePhase.ALARM
    assert app.job_controller.state == JobState.ABORTED


def test_auto_home_runs_after_completed_idle_single_job() -> None:
    messages: list[str] = []
    app = ApplicationController(messages.append, None, lambda: "")
    controller = AutoHomeController()
    app.controller = controller
    app.machine_state.transition(MachinePhase.IDLE, "Bereit")

    app.start_job(
        "G21\nG90\nG0 X0 Y0\nM5",
        10.0,
        10.0,
        auto_home_after_success=True,
        job_kind="Einzelstueck",
    )

    assert app.job_controller.state == JobState.COMPLETED
    assert controller.calls == ["start_job", "M5", "S0", "$H"]
    assert app.machine_state.phase == MachinePhase.IDLE
    assert any("Sicherheitspruefung bestanden" in message for message in messages)
    assert any("Home abgeschlossen" in message for message in messages)


def test_auto_home_is_skipped_when_job_fails() -> None:
    messages: list[str] = []
    app = ApplicationController(messages.append, None, lambda: "")
    controller = AutoHomeController()

    def fail_start(_gcode: str, _width_mm: float, _height_mm: float) -> None:
        controller.calls.append("start_job")
        raise RuntimeError("Laser error")

    controller.start_job = fail_start
    app.controller = controller
    app.machine_state.transition(MachinePhase.IDLE, "Bereit")

    try:
        app.start_job("G21\nM5", 10.0, 10.0, auto_home_after_success=True)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Failing job did not raise")

    assert app.job_controller.state == JobState.FAILED
    assert controller.calls == ["start_job"]


def test_auto_home_is_skipped_for_stopped_and_aborted_jobs() -> None:
    for job_state in (JobState.STOPPED, JobState.ABORTED):
        messages: list[str] = []
        app = ApplicationController(messages.append, None, lambda: "")
        controller = AutoHomeController()
        app.controller = controller
        app.machine_state.transition(MachinePhase.IDLE, "Bereit")
        if job_state == JobState.STOPPED:
            app.job_controller.transition(JobState.STOPPING, "stop")
            app.job_controller.transition(JobState.STOPPED, "stop")
        else:
            app.job_controller.transition(JobState.ABORTED, "abort")

        app._handle_auto_home_after_job(True, "Einzelstueck", "Job")

        assert controller.calls == []
        assert any("Auto-Home uebersprungen" in message for message in messages)


def test_auto_home_is_skipped_for_alarm_error_paused_running_or_busy_queue() -> None:
    cases = [
        (MachinePhase.ALARM, "Idle", False, True),
        (MachinePhase.ERROR, "error:1", False, True),
        (MachinePhase.PAUSED, "Hold:0", True, True),
        (MachinePhase.RUNNING, "Run", False, True),
        (MachinePhase.IDLE, "Idle", False, False),
    ]
    for phase, status, paused, queue_empty in cases:
        messages: list[str] = []
        app = ApplicationController(messages.append, None, lambda: "")
        controller = AutoHomeController()
        controller.state.status = status
        controller.state.paused = paused
        controller.state.alarm = phase == MachinePhase.ALARM
        controller.serial_queue_empty = queue_empty
        app.controller = controller
        app.machine_state.transition(MachinePhase.IDLE, "Bereit")
        app.machine_state.transition(phase, status)
        app.job_controller.transition(JobState.STREAMING, "stream")
        app.job_controller.transition(JobState.COMPLETED, "done")

        app._handle_auto_home_after_job(True, "Einzelstueck", "Job")

        assert controller.calls == []
        assert any("Auto-Home uebersprungen" in message for message in messages)


def test_auto_home_is_skipped_when_option_or_job_kind_do_not_match() -> None:
    app = ApplicationController(lambda _message: None, None, lambda: "")
    controller = AutoHomeController()
    app.controller = controller
    app.machine_state.transition(MachinePhase.IDLE, "Bereit")
    app.job_controller.transition(JobState.STREAMING, "stream")
    app.job_controller.transition(JobState.COMPLETED, "done")

    app._handle_auto_home_after_job(False, "Einzelstueck", "Job")
    app._handle_auto_home_after_job(True, "Serie", "Job")

    assert controller.calls == []


def _alarmed_simulator_app() -> ApplicationController:
    app = ApplicationController(lambda _message: None, None, lambda: "")
    app.connect()
    app.home()
    app.emergency_stop()
    assert app.machine_state.phase == MachinePhase.ALARM
    return app


def test_alarm_can_be_cleared_by_homing() -> None:
    app = _alarmed_simulator_app()

    app.home()

    assert app.machine_state.phase == MachinePhase.IDLE
    assert app.controller.state.homed
    assert not app.controller.state.alarm


def test_alarm_can_be_unlocked_without_homing() -> None:
    app = _alarmed_simulator_app()

    app.unlock_alarm()

    assert app.machine_state.phase == MachinePhase.IDLE
    assert not app.controller.state.alarm
    # $X does not reference the machine: jobs still need homing unless the profile allows otherwise.
    assert not app.controller.state.homed


def test_machine_profile_homing_policy_reaches_controller_readiness_check() -> None:
    from dataclasses import replace

    import pytest

    from laser_control.machine_profiles import DEFAULT_MACHINE_PROFILE

    app = ApplicationController(lambda _message: None, None, lambda: "")
    app.connect()
    with pytest.raises(RuntimeError, match="Referenzfahrt"):
        app.controller.frame(10.0, 10.0)

    app.set_machine_profile(replace(DEFAULT_MACHINE_PROFILE, homing_required=False))
    assert app.controller.homing_required is False
    app.controller.frame(10.0, 10.0)

    app.switch_controller("GRBL ueber USB")
    assert app.controller.homing_required is False
    app.shutdown_controller()


def test_emergency_stop_resets_controller_before_blocking_cleanup() -> None:
    calls: list[str] = []

    class RecordingSimulator(SimulatedLaserController):
        def emergency_stop(self) -> None:
            calls.append("emergency_stop")
            super().emergency_stop()

        def disable_alignment_pointer(self) -> None:
            calls.append("laser_off")
            super().disable_alignment_pointer()

    app = ApplicationController(lambda _message: None, None, lambda: "")
    app.controller = RecordingSimulator(lambda _message: None)
    app.connect()
    app.home()
    calls.clear()

    app.emergency_stop()

    assert calls[0] == "emergency_stop"
    assert app.machine_state.phase == MachinePhase.ALARM


def test_machine_profile_baud_rate_reaches_existing_serial_controller() -> None:
    from dataclasses import replace

    from laser_control.machine_profiles import DEFAULT_MACHINE_PROFILE

    app = ApplicationController(lambda _message: None, None, lambda: "")
    app.switch_controller("GRBL ueber USB")
    assert app.controller._baudrate == DEFAULT_MACHINE_PROFILE.baudrate

    app.set_machine_profile(replace(DEFAULT_MACHINE_PROFILE, name="Slow", baudrate=57600))

    assert app.controller._baudrate == 57600
    app.shutdown_controller()
