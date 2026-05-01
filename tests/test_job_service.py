from laser_control.gcode import CUT_MODE
from laser_control.models import LaserState, MaterialProfile
from laser_control.services.job_service import JobService


class Controller:
    def __init__(self, connected: bool, homed: bool) -> None:
        self.state = LaserState(connected=connected, homed=homed)


def test_job_service_adds_cut_parameter_warnings() -> None:
    service = JobService()
    profile = MaterialProfile("Aggressive", power_percent=95, speed_mm_min=250, passes=5)

    prepared = service.prepare_job("G0 X0 Y0\nG1 X1 Y1 S950\nM5", 20, 20, profile, CUT_MODE)

    assert len(prepared.commands) == 3
    assert any("Leistung" in warning for warning in prepared.warnings)
    assert any("Geschwindigkeit" in warning for warning in prepared.warnings)
    assert any("Durchgaenge" in warning for warning in prepared.warnings)


def test_hardware_preflight_reports_missing_connection_and_homing() -> None:
    warnings = JobService().hardware_preflight_warnings(Controller(False, False), "COM1")

    assert any("nicht verbunden" in warning for warning in warnings)
    assert any("Referenzfahrt" in warning for warning in warnings)
