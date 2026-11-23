import threading
import time

import pytest

from laser_control.application_controller import ApplicationController
from laser_control.machine_profiles import MachineProfile
from laser_control.machine_state import MachineAction, MachinePhase
from laser_control.serial_grbl import GrblSerialController


class RealtimeSerial:
    is_open = True
    port = "COM1"

    def __init__(self, responses: list[bytes]) -> None:
        self.responses = responses
        self.writes: list[bytes] = []

    def write(self, value: bytes) -> None:
        self.writes.append(value)

    def flush(self) -> None:
        pass

    def readline(self) -> bytes:
        if self.responses:
            return self.responses.pop(0)
        return b""

    @property
    def in_waiting(self) -> int:
        if not self.responses:
            return 0
        return len(self.responses[0])

    def read(self, _size: int) -> bytes:
        if self.responses:
            return self.responses.pop(0)
        return b""


def _connected_app() -> ApplicationController:
    app = ApplicationController(lambda _message: None, None, lambda: "")
    app.connect()
    app.home()
    return app


def _wait_for(condition, timeout_seconds: float = 1.0) -> None:
    end_time = time.monotonic() + timeout_seconds
    while time.monotonic() < end_time:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not reached in time")


def test_work_area_trace_enables_only_from_idle() -> None:
    app = _connected_app()
    calls: list[tuple[float, float, int]] = []

    def trace_once(width_mm: float, height_mm: float, feed_mm_min: int, stop_event: threading.Event, _power_percent: int = 5) -> None:
        calls.append((width_mm, height_mm, feed_mm_min))
        stop_event.set()

    app.controller.trace_work_area_once = trace_once

    app.enable_work_area_trace()
    _wait_for(lambda: not app.is_work_area_trace_active())

    assert calls


@pytest.mark.parametrize("phase", [MachinePhase.RUNNING, MachinePhase.PAUSED, MachinePhase.STOPPING, MachinePhase.ALARM, MachinePhase.ERROR])
def test_work_area_trace_blocks_non_idle_phases(phase: MachinePhase) -> None:
    app = _connected_app()
    app.machine_state.transition(phase, phase.value)

    with pytest.raises(RuntimeError, match="Arbeitsflaechenmodus"):
        app.enable_work_area_trace()

    assert not app.is_work_area_trace_active()


def test_work_area_trace_uses_machine_profile_area_and_safe_feed() -> None:
    app = _connected_app()
    app.set_machine_profile(
        MachineProfile(
            profile_id="small",
            name="Small",
            work_area_width=123.0,
            work_area_height=45.0,
            max_speed=1500,
            homing_required=False,
        )
    )
    calls: list[tuple[float, float, int]] = []

    def trace_once(width_mm: float, height_mm: float, feed_mm_min: int, stop_event: threading.Event, _power_percent: int = 5) -> None:
        calls.append((width_mm, height_mm, feed_mm_min))
        stop_event.set()

    app.controller.trace_work_area_once = trace_once

    app.enable_work_area_trace()
    _wait_for(lambda: calls)

    assert calls[0] == (123.0, 45.0, 1500)


def test_work_area_trace_uses_current_workspace_not_machine_profile() -> None:
    app = _connected_app()
    app.set_machine_profile(
        MachineProfile(
            profile_id="falcon",
            name="Falcon",
            work_area_width=400.0,
            work_area_height=415.0,
            max_speed=1500,
            homing_required=False,
        )
    )
    app.set_current_workspace(110.0, 110.0)
    calls: list[tuple[float, float, int]] = []

    def trace_once(width_mm: float, height_mm: float, feed_mm_min: int, stop_event: threading.Event, _power_percent: int = 5) -> None:
        calls.append((width_mm, height_mm, feed_mm_min))
        stop_event.set()

    app.controller.trace_work_area_once = trace_once

    app.enable_work_area_trace()
    _wait_for(lambda: calls)

    assert calls[0] == (110.0, 110.0, 1500)


def test_work_area_trace_uses_non_square_current_workspace() -> None:
    app = _connected_app()
    app.set_current_workspace(200.0, 50.0)
    calls: list[tuple[float, float, int]] = []

    def trace_once(width_mm: float, height_mm: float, feed_mm_min: int, stop_event: threading.Event, _power_percent: int = 5) -> None:
        calls.append((width_mm, height_mm, feed_mm_min))
        stop_event.set()

    app.controller.trace_work_area_once = trace_once

    app.enable_work_area_trace()
    _wait_for(lambda: calls)

    assert calls[0][:2] == (200.0, 50.0)


class NoWaitTraceController(GrblSerialController):
    def _wait_until_idle_or_stopped(self, stop_event: threading.Event, timeout_seconds: float) -> None:
        return


def test_serial_work_area_trace_contains_laser_off_and_profile_path() -> None:
    controller = NoWaitTraceController(log=lambda _message: None, port_getter=lambda: "COM1")
    controller.grbl_settings = {30: 1000.0, 31: 0.0, 32: 1.0}
    fake = RealtimeSerial([b"ok\n"] * 12)
    controller._serial = fake
    controller.state.connected = True

    controller.trace_work_area_once(400.0, 415.0, 1500, threading.Event(), 5)

    assert fake.writes == [
        b"G21\n",
        b"G90\n",
        b"M5\n",
        b"S0\n",
        b"M3 S50\n",
        b"G1 X0.000 Y0.000 F1500\n",
        b"G1 X400.000 Y0.000 F1500\n",
        b"G1 X400.000 Y415.000 F1500\n",
        b"G1 X0.000 Y415.000 F1500\n",
        b"G1 X0.000 Y0.000 F1500\n",
        b"M5\n",
        b"S0\n",
    ]


def test_serial_work_area_trace_uses_g1_not_g0_for_laser_movements() -> None:
    controller = NoWaitTraceController(log=lambda _message: None, port_getter=lambda: "COM1")
    controller.grbl_settings = {30: 1000.0, 31: 0.0, 32: 1.0}
    fake = RealtimeSerial([b"ok\n"] * 12)
    controller._serial = fake
    controller.state.connected = True

    controller.trace_work_area_once(110.0, 110.0, 1000, threading.Event(), 5)

    written = [item.decode("ascii").strip() for item in fake.writes]
    assert "M3 S50" in written
    assert all(not command.startswith("G0 ") for command in written)
    assert "G1 X110.000 Y110.000 F1000" in written
    assert written[-2:] == ["M5", "S0"]


def test_serial_work_area_trace_calculates_five_percent_from_smax() -> None:
    controller = NoWaitTraceController(log=lambda _message: None, port_getter=lambda: "COM1")
    controller.grbl_settings = {30: 1000.0, 31: 0.0, 32: 1.0}
    fake = RealtimeSerial([b"ok\n"] * 12)
    controller._serial = fake
    controller.state.connected = True

    controller.trace_work_area_once(110.0, 110.0, 1000, threading.Event(), 5)

    assert b"M3 S50\n" in fake.writes


def test_work_area_trace_deactivation_stops_repetitions() -> None:
    app = _connected_app()
    rounds = 0

    def trace_once(_width_mm: float, _height_mm: float, _feed_mm_min: int, stop_event: threading.Event, _power_percent: int = 5) -> None:
        nonlocal rounds
        rounds += 1
        stop_event.wait(1.0)

    app.controller.trace_work_area_once = trace_once

    app.enable_work_area_trace()
    _wait_for(lambda: rounds == 1)
    app.disable_work_area_trace("test")
    _wait_for(lambda: not app.is_work_area_trace_active())

    assert rounds == 1


def test_work_area_trace_stop_and_emergency_end_mode() -> None:
    app = _connected_app()

    def trace_once(_width_mm: float, _height_mm: float, _feed_mm_min: int, stop_event: threading.Event, _power_percent: int = 5) -> None:
        stop_event.wait(1.0)

    app.controller.trace_work_area_once = trace_once
    app.enable_work_area_trace()
    _wait_for(app.is_work_area_trace_active)

    app.stop()

    assert not app.is_work_area_trace_active()
    assert app.machine_state.phase == MachinePhase.IDLE
    assert app.machine_state.can_perform(MachineAction.HOME)

    app = _connected_app()
    app.controller.trace_work_area_once = trace_once
    app.enable_work_area_trace()
    _wait_for(app.is_work_area_trace_active)

    app.emergency_stop()

    assert not app.is_work_area_trace_active()
    assert app.machine_state.phase == MachinePhase.ALARM


def test_work_area_trace_stop_clears_serial_queue() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")
    removed_priorities = []

    class FakeExecutor:
        def clear_pending(self, min_priority):
            removed_priorities.append(min_priority)
            return 3

    controller._executor = FakeExecutor()

    controller.stop_work_area_trace()

    assert removed_priorities


def test_home_remains_blocked_while_running_or_stopping() -> None:
    app = _connected_app()
    app.machine_state.transition(MachinePhase.RUNNING, "run")
    assert not app.machine_state.can_perform(MachineAction.HOME)


def test_work_area_trace_stop_keeps_home_blocked_until_controller_reports_idle() -> None:
    app = _connected_app()
    app.machine_state.work_area_trace_active = True
    app.controller.state.work_area_trace_active = True
    app.controller.state.status = "Run"
    app.controller.stop_work_area_trace = lambda: None

    app.disable_work_area_trace("Stop")

    assert app.machine_state.phase == MachinePhase.RUNNING
    assert not app.machine_state.can_perform(MachineAction.HOME)

    app.controller.state.status = "Idle"
    app.sync_from_controller()

    assert app.machine_state.phase == MachinePhase.IDLE
    assert app.machine_state.can_perform(MachineAction.HOME)

    app.machine_state.transition(MachinePhase.STOPPING, "stop")
    assert not app.machine_state.can_perform(MachineAction.HOME)


def test_jobstart_disables_work_area_trace_before_streaming() -> None:
    app = _connected_app()

    def trace_once(_width_mm: float, _height_mm: float, _feed_mm_min: int, stop_event: threading.Event, _power_percent: int = 5) -> None:
        stop_event.wait(1.0)

    app.controller.trace_work_area_once = trace_once
    app.enable_work_area_trace()
    _wait_for(app.is_work_area_trace_active)

    app.start_job("G21\nG90\nG0 X0 Y0\nG1 X1 Y1\nM5", 10.0, 10.0)

    assert not app.is_work_area_trace_active()
