from laser_control.machine_actions import MachineActionRegistry
from laser_control.machine_state import MachinePhase, MachineState


def test_machine_action_registry_contains_expected_actions() -> None:
    registry = MachineActionRegistry()
    action_ids = {definition.action_id for definition in registry.all()}

    assert {
        "connect",
        "disconnect",
        "home",
        "jog_x_plus",
        "frame",
        "toggle_work_area_trace",
        "dry_run",
        "start_job",
        "pause",
        "resume",
        "stop",
        "emergency_stop",
    } <= action_ids


def test_work_area_trace_tooltips_explain_stop_and_emergency_behavior() -> None:
    registry = MachineActionRegistry()

    trace_tooltip = registry.get("toggle_work_area_trace").tooltip
    stop_tooltip = registry.get("stop").tooltip
    emergency_tooltip = registry.get("emergency_stop").tooltip

    assert "App-Arbeitsflaeche" in trace_tooltip
    assert "M5/S0" in trace_tooltip
    assert "Sicherheitsstopp bricht sofort ab" in trace_tooltip
    assert "Home" in stop_tooltip
    assert "Reset/Unlock/Re-Homing" in emergency_tooltip


def test_machine_action_registry_derives_enabled_state_from_machine_state() -> None:
    registry = MachineActionRegistry()
    disconnected = MachineState(MachinePhase.DISCONNECTED)
    idle = MachineState(MachinePhase.IDLE)
    running = MachineState(MachinePhase.RUNNING)
    paused = MachineState(MachinePhase.PAUSED)

    assert registry.is_enabled("connect", disconnected)
    assert not registry.is_enabled("start_job", disconnected)
    assert registry.is_enabled("start_job", idle)
    assert registry.is_enabled("toggle_work_area_trace", idle)
    assert registry.is_enabled("pause", running)
    assert registry.is_enabled("stop", running)
    assert not registry.is_enabled("toggle_work_area_trace", running)
    running.work_area_trace_active = True
    assert registry.is_enabled("toggle_work_area_trace", running)
    assert registry.is_enabled("stop", running)
    assert not registry.is_enabled("start_job", running)
    assert not registry.is_enabled("resume", running)
    assert registry.is_enabled("resume", paused)
    assert registry.is_enabled("stop", paused)
    assert registry.is_enabled("emergency_stop", paused)
    assert not registry.is_enabled("stop", idle)
    assert registry.is_enabled("emergency_stop", idle)
