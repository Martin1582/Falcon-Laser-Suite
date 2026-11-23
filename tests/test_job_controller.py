from laser_control.application_controller import ApplicationController
from laser_control.job_controller import JobController, JobState, PreparedMachineJob
from laser_control.machine_state import MachineEvent, MachineEventType, MachinePhase
from laser_control.models import LaserState


class FakeLaserController:
    def __init__(self) -> None:
        self.state = LaserState(connected=True, homed=True)
        self.calls: list[tuple[str, object]] = []

    def connect(self) -> None:
        self.state.connected = True

    def disconnect(self) -> None:
        self.state = LaserState()

    def get_status(self) -> LaserState:
        return self.state

    def home(self) -> None:
        self.calls.append(("home", None))

    def jog(self, dx_mm: float, dy_mm: float) -> None:
        self.calls.append(("jog", (dx_mm, dy_mm)))

    def frame(self, width_mm: float, height_mm: float, x_mm: float = 0.0, y_mm: float = 0.0) -> None:
        self.calls.append(("frame", (width_mm, height_mm, x_mm, y_mm)))

    def start_job(self, gcode: str, width_mm: float, height_mm: float) -> None:
        self.calls.append(("start_job", (gcode, width_mm, height_mm)))

    def pause(self) -> None:
        self.state.paused = True
        self.calls.append(("pause", None))

    def resume(self) -> None:
        self.state.paused = False
        self.calls.append(("resume", None))

    def stop(self) -> None:
        self.calls.append(("stop", None))

    def emergency_stop(self) -> None:
        self.calls.append(("emergency_stop", None))

    def current_position(self) -> tuple[float, float]:
        return 1.0, 2.0


class AbortingFakeLaserController(FakeLaserController):
    def start_job(self, gcode: str, width_mm: float, height_mm: float) -> None:
        raise RuntimeError("Job durch Stop/Emergency Stop abgebrochen.")


def test_job_controller_delegates_controller_ready_jobs() -> None:
    controller = FakeLaserController()
    job_controller = JobController()

    job_controller.frame(controller, 100.0, 80.0)
    job_controller.start(controller, PreparedMachineJob("G21\nM5", 100.0, 80.0))

    assert controller.calls == [
        ("frame", (100.0, 80.0, 0.0, 0.0)),
        ("start_job", ("G21\nM5", 100.0, 80.0)),
    ]


def test_application_controller_runs_jobs_through_job_controller() -> None:
    app = ApplicationController(lambda _message: None, None, lambda: "")
    fake = FakeLaserController()
    app.controller = fake
    app.machine_state.transition(MachinePhase.IDLE, "Bereit")

    app.frame_job(20.0, 10.0)
    app.start_job("G21\nM5", 20.0, 10.0)

    assert ("frame", (20.0, 10.0, 0.0, 0.0)) in fake.calls
    assert ("start_job", ("G21\nM5", 20.0, 10.0)) in fake.calls


def test_application_controller_blocks_job_outside_idle() -> None:
    messages: list[str] = []
    app = ApplicationController(messages.append, None, lambda: "")

    try:
        app.start_job("G21\nM5", 20.0, 10.0)
    except RuntimeError as exc:
        assert "nicht erlaubt" in str(exc)
    else:
        raise AssertionError("Job start outside idle was not blocked")

    assert app.machine_state.phase == MachinePhase.DISCONNECTED
    assert any("Blockierte Maschinenaktion" in message for message in messages)


def test_job_controller_tracks_pause_resume_status() -> None:
    controller = FakeLaserController()
    job_controller = JobController()
    job_controller.transition(JobState.STREAMING, "test")

    job_controller.pause(controller)
    assert job_controller.status == "paused"
    assert job_controller.state == JobState.PAUSED
    assert controller.state.paused

    job_controller.resume(controller)
    assert job_controller.status == "streaming"
    assert job_controller.state == JobState.STREAMING
    assert not controller.state.paused

    job_controller.stop(controller)
    assert job_controller.status == "stopped"
    assert job_controller.state == JobState.STOPPED


def test_job_controller_tracks_emergency_stop_as_aborted() -> None:
    controller = FakeLaserController()
    job_controller = JobController()

    job_controller.emergency_stop(controller)

    assert job_controller.status == "aborted"
    assert job_controller.state == JobState.ABORTED
    assert ("emergency_stop", None) in controller.calls


def test_job_controller_keeps_stopped_status_after_abort_exception() -> None:
    controller = AbortingFakeLaserController()
    job_controller = JobController()

    try:
        job_controller.start(controller, PreparedMachineJob("G21\nM5", 100.0, 80.0))
    except RuntimeError:
        pass
    else:
        raise AssertionError("Abort exception was not raised")

    assert job_controller.status == "aborted"


def test_job_controller_emits_typed_state_changes() -> None:
    changes: list[tuple[JobState, JobState, str]] = []
    controller = FakeLaserController()
    job_controller = JobController(lambda previous, current, reason: changes.append((previous, current, reason)))

    job_controller.start(controller, PreparedMachineJob("G21\nM5", 100.0, 80.0))

    assert JobState.STREAMING in [change[1] for change in changes]
    assert changes[-1][1] == JobState.COMPLETED


def test_job_controller_handles_machine_hold_and_run_events() -> None:
    job_controller = JobController()
    job_controller.transition(JobState.STREAMING, "test")

    job_controller.handle_machine_event(MachineEvent(MachineEventType.STATUS, MachinePhase.PAUSED, "Hold"))
    assert job_controller.state == JobState.PAUSED

    job_controller.handle_machine_event(MachineEvent(MachineEventType.STATUS, MachinePhase.RUNNING, "Run"))
    assert job_controller.state == JobState.STREAMING


def test_job_controller_marks_alarm_as_failed() -> None:
    job_controller = JobController()
    job_controller.transition(JobState.STREAMING, "test")

    job_controller.handle_machine_event(MachineEvent(MachineEventType.ALARM, MachinePhase.ALARM, "Alarm"))

    assert job_controller.state == JobState.FAILED


def test_job_controller_maps_idle_after_stopping_to_stopped() -> None:
    job_controller = JobController()
    job_controller.transition(JobState.STREAMING, "test")
    job_controller.transition(JobState.STOPPING, "stop")

    job_controller.handle_machine_event(MachineEvent(MachineEventType.STATUS, MachinePhase.IDLE, "Idle"))

    assert job_controller.state == JobState.STOPPED


def test_job_controller_maps_error_and_disconnect_differently() -> None:
    failed = JobController()
    failed.transition(JobState.STREAMING, "test")
    failed.handle_machine_event(MachineEvent(MachineEventType.ERROR, MachinePhase.ERROR, "error:1"))

    aborted = JobController()
    aborted.transition(JobState.STREAMING, "test")
    aborted.handle_machine_event(MachineEvent(MachineEventType.CONNECTION_LOST, MachinePhase.DISCONNECTED, "lost"))

    assert failed.state == JobState.FAILED
    assert aborted.state == JobState.ABORTED


def test_job_controller_can_prepare_new_job_after_completed() -> None:
    controller = FakeLaserController()
    job_controller = JobController()

    job_controller.start(controller, PreparedMachineJob("G21\nM5", 100.0, 80.0))
    job_controller.start(controller, PreparedMachineJob("G21\nM5", 100.0, 80.0))

    assert job_controller.state == JobState.COMPLETED
    assert len([call for call in controller.calls if call[0] == "start_job"]) == 2
