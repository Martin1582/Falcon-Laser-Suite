from types import SimpleNamespace

import laser_control.serial_autodetect as autodetect


def test_looks_like_grbl_accepts_status_report() -> None:
    assert autodetect.looks_like_grbl("<Idle|MPos:0.000,0.000,0.000|FS:0,0>")


def test_list_port_candidates_prioritizes_usb_serial(monkeypatch) -> None:
    ports = [
        SimpleNamespace(device="COM9", description="Bluetooth Port", hwid=""),
        SimpleNamespace(device="COM3", description="USB-SERIAL CH340", hwid="VID:PID"),
    ]
    monkeypatch.setattr(autodetect, "list_ports", SimpleNamespace(comports=lambda: ports))

    candidates = autodetect.list_port_candidates()

    assert candidates[0].device == "COM3"
    assert candidates[0].score > candidates[1].score


def test_find_laser_port_returns_first_grbl_probe_match(monkeypatch) -> None:
    candidates = [
        autodetect.PortCandidate("COM1", "COM1", 10, "first"),
        autodetect.PortCandidate("COM2", "COM2", 10, "second"),
    ]
    monkeypatch.setattr(autodetect, "list_port_candidates", lambda: candidates)
    monkeypatch.setattr(
        autodetect,
        "probe_grbl_port",
        lambda device, baudrate=115200: "ok\n<Idle|MPos:0.000,0.000,0.000>" if device == "COM2" else "",
    )

    detected = autodetect.find_laser_port()

    assert detected is candidates[1]
    assert detected.score >= 100
