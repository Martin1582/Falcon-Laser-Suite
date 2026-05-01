import pytest

from laser_control.serial_grbl import GrblSerialController


class SilentSerial:
    is_open = True

    def write(self, _value: bytes) -> None:
        pass

    def flush(self) -> None:
        pass

    def readline(self) -> bytes:
        return b""


def test_send_command_rejects_empty_controller_response() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")
    controller._serial = SilentSerial()

    with pytest.raises(RuntimeError, match="Keine Antwort"):
        controller.send_command("G0 X0", wait_seconds=0.01)


def test_update_state_from_status_tracks_alarm_and_position() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")

    controller._update_state_from_status("<Alarm|MPos:12.500,3.250,0.000|FS:0,0>")

    assert controller.state.status == "Alarm"
    assert controller.state.alarm
    assert controller.state.x_mm == 12.5
    assert controller.state.y_mm == 3.25
