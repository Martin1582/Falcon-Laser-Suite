from laser_control.machine_state import MachineEventType, MachinePhase, machine_event_from_state, machine_event_from_status, phase_from_controller_status
from laser_control.models import LaserState


def test_phase_from_controller_status_maps_grbl_hold_and_run() -> None:
    assert phase_from_controller_status("Hold:0") == MachinePhase.PAUSED
    assert phase_from_controller_status("Run") == MachinePhase.RUNNING
    assert phase_from_controller_status("Idle") == MachinePhase.IDLE


def test_machine_event_from_state_marks_alarm_and_disconnect() -> None:
    alarm = machine_event_from_state(LaserState(connected=True, alarm=True, status="Alarm"))
    disconnected = machine_event_from_state(LaserState(connected=False))

    assert alarm.event_type == MachineEventType.ALARM
    assert alarm.phase == MachinePhase.ALARM
    assert disconnected.event_type == MachineEventType.CONNECTION_LOST
    assert disconnected.phase == MachinePhase.DISCONNECTED


def test_machine_event_from_status_centralizes_error_alarm_and_run() -> None:
    run = machine_event_from_status("Run")
    error = machine_event_from_status("error:1")
    disconnected = machine_event_from_status("Idle", connected=False)

    assert run.event_type == MachineEventType.STATUS
    assert run.phase == MachinePhase.RUNNING
    assert error.event_type == MachineEventType.ERROR
    assert error.phase == MachinePhase.ERROR
    assert disconnected.event_type == MachineEventType.CONNECTION_LOST
    assert disconnected.phase == MachinePhase.DISCONNECTED


def test_machine_state_applies_position_event_and_disconnect_reset() -> None:
    from laser_control.machine_state import MachineEvent, MachineState

    state = MachineState(MachinePhase.IDLE)
    state.apply_event(
        MachineEvent(
            MachineEventType.STATUS,
            MachinePhase.RUNNING,
            "Run",
            x_mm=12.34,
            y_mm=56.78,
            z_mm=0.1,
            position_source="MPos",
            feed_rate=1200.0,
        )
    )

    assert state.phase == MachinePhase.RUNNING
    assert state.x_mm == 12.34
    assert state.y_mm == 56.78
    assert state.z_mm == 0.1
    assert state.position_source == "MPos"
    assert state.feed_rate == 1200.0

    state.apply_event(MachineEvent(MachineEventType.CONNECTION_LOST, MachinePhase.DISCONNECTED, "Disconnected"))

    assert state.x_mm is None
    assert state.y_mm is None
    assert state.position_source == ""


def test_machine_event_from_state_keeps_running_position_payload() -> None:
    laser_state = LaserState(
        connected=True,
        homed=True,
        status="Run",
        x_mm=12.34,
        y_mm=56.78,
        z_mm=0.0,
        position_source="WPos",
    )

    event = machine_event_from_state(laser_state)

    assert event.phase == MachinePhase.RUNNING
    assert event.x_mm == 12.34
    assert event.y_mm == 56.78
    assert event.position_source == "WPos"


def test_machine_event_from_state_disconnect_hides_position_payload() -> None:
    laser_state = LaserState(
        connected=False,
        status="Disconnected",
        x_mm=12.34,
        y_mm=56.78,
        position_source="MPos",
    )

    event = machine_event_from_state(laser_state)

    assert event.phase == MachinePhase.DISCONNECTED
    assert event.x_mm is None
    assert event.y_mm is None
    assert event.position_source == ""


def test_machine_state_keeps_live_wpos_through_idle_run_hold_resume_until_disconnect() -> None:
    from laser_control.machine_state import MachineState

    state = MachineState(MachinePhase.IDLE)
    sequence = [
        ("Idle", MachinePhase.IDLE, 1.0, 2.0),
        ("Run", MachinePhase.RUNNING, 3.0, 4.0),
        ("Hold:0", MachinePhase.PAUSED, 5.0, 6.0),
        ("Run", MachinePhase.RUNNING, 7.0, 8.0),
    ]
    for status, phase, x_mm, y_mm in sequence:
        state.apply_event(
            machine_event_from_status(
                status,
                x_mm=x_mm,
                y_mm=y_mm,
                z_mm=0.0,
                position_source="WPos",
            )
        )
        assert state.phase == phase
        assert state.x_mm == x_mm
        assert state.y_mm == y_mm
        assert state.position_source == "WPos"

    state.apply_event(machine_event_from_status("Disconnected", connected=False))

    assert state.phase == MachinePhase.DISCONNECTED
    assert state.x_mm is None
    assert state.y_mm is None
    assert state.position_source == ""
