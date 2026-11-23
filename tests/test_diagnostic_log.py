from laser_control.diagnostic_log import DiagnosticLog
from laser_control.serial_grbl import GrblSerialController
from laser_control.serial_consistency import SerialConsistencyTracker


class OkSerial:
    is_open = True

    def __init__(self) -> None:
        self.writes = []
        self._responses = [b"ok\n"]
        self._read_chunks = []
        self.port = "COM1"

    def write(self, value: bytes) -> None:
        self.writes.append(value)

    def flush(self) -> None:
        pass

    def readline(self) -> bytes:
        if self._responses:
            return self._responses.pop(0)
        return b""

    @property
    def in_waiting(self) -> int:
        if not self._read_chunks:
            return 0
        return len(self._read_chunks[0])

    def read(self, _size: int) -> bytes:
        if self._read_chunks:
            return self._read_chunks.pop(0)
        return b""


def test_diagnostic_log_writes_and_exports(tmp_path) -> None:
    source = tmp_path / "diagnostic.log"
    target = tmp_path / "exported.log"
    diagnostic = DiagnosticLog(source)

    diagnostic.app("App bereit")
    diagnostic.tx("G0 X10")
    diagnostic.rx("ok")
    exported = diagnostic.export_to(target)

    content = source.read_text(encoding="utf-8")
    assert "[APP] App bereit" in content
    assert "[TX] G0 X10" in content
    assert "[RX] ok" in content
    assert exported == target
    assert target.read_text(encoding="utf-8") == content


def test_serial_controller_writes_tx_rx_to_diagnostic_log(tmp_path) -> None:
    diagnostic = DiagnosticLog(tmp_path / "serial.log")
    controller = GrblSerialController(
        log=lambda _message: None,
        port_getter=lambda: "COM1",
        diagnostic_log=diagnostic,
    )
    controller._serial = OkSerial()

    controller.send_command("G0 X10", wait_seconds=0.01)

    content = diagnostic.path.read_text(encoding="utf-8")
    assert "[TX] G0 X10" in content
    assert "[RX] ok" in content


def test_serial_controller_logs_consistency_report(tmp_path) -> None:
    diagnostic = DiagnosticLog(tmp_path / "job.log")
    messages = []
    controller = GrblSerialController(
        log=messages.append,
        port_getter=lambda: "COM1",
        diagnostic_log=diagnostic,
    )
    tracker = SerialConsistencyTracker("Job")
    tracker.record_tx("G1 X10.000 Y0.000 F500", expects_ack=True)
    tracker.record_rx("ok")
    tracker.record_tx("?", expects_ack=False)
    tracker.record_rx("<Idle|MPos:10.000,0.000,0.000|FS:0,0>")

    controller._log_consistency_report(tracker.report())

    content = diagnostic.path.read_text(encoding="utf-8")
    assert "[CHECK] Kommunikationsabgleich OK" in content
    assert any("Kommunikationsabgleich OK" in message for message in messages)
