import pytest

from laser_control.serial_grbl import GrblSerialController, parse_grbl_status_report


class SilentSerial:
    is_open = True

    def write(self, _value: bytes) -> None:
        pass

    def flush(self) -> None:
        pass

    def readline(self) -> bytes:
        return b""


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


class AbortOnWaitController(GrblSerialController):
    def _wait_until_idle(self, timeout_seconds: float) -> None:
        self._abort_requested.set()
        raise RuntimeError("Job durch Stop/Emergency Stop abgebrochen.")


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
    assert controller.state.z_mm == 0.0
    assert controller.state.position_source == "MPos"


def test_parse_grbl_status_report_reads_mpos_fs_and_overrides() -> None:
    report = parse_grbl_status_report("<Run|MPos:12.345,45.678,0.000|FS:1200,55|Ov:100,100,90>")

    assert report is not None
    assert report.state == "Run"
    assert report.mpos_x == 12.345
    assert report.mpos_y == 45.678
    assert report.mpos_z == 0.0
    assert report.feed_rate == 1200.0
    assert report.spindle_value == 55.0
    assert report.override_spindle == 90


def test_parse_grbl_status_report_prefers_wpos_when_both_positions_exist() -> None:
    report = parse_grbl_status_report("<Run|MPos:12.000,45.000,0.000|WPos:2.500,3.500,0.100|FS:1200,55>")

    assert report is not None
    assert report.position_source == "WPos"
    assert report.x_mm == 2.5
    assert report.y_mm == 3.5
    assert report.z_mm == 0.1


def test_parse_grbl_status_report_calculates_wpos_from_mpos_and_wco() -> None:
    report = parse_grbl_status_report("<Idle|MPos:12.000,45.000,0.000|WCO:10.000,40.000,0.000|FS:0,0>")

    assert report is not None
    assert report.position_source == "WPos (MPos-WCO)"
    assert report.x_mm == 2.0
    assert report.y_mm == 5.0
    assert report.z_mm == 0.0


def test_parse_grbl_status_report_reads_wpos() -> None:
    report = parse_grbl_status_report("<Hold|WPos:10.000,20.000,0.100|FS:0,0>")

    assert report is not None
    assert report.state == "Hold"
    assert report.position_source == "WPos"
    assert report.x_mm == 10.0
    assert report.y_mm == 20.0
    assert report.z_mm == 0.1


def test_parse_grbl_status_report_without_position_is_valid() -> None:
    report = parse_grbl_status_report("<Idle|FS:0,0>")

    assert report is not None
    assert report.state == "Idle"
    assert report.x_mm is None
    assert report.feed_rate == 0.0


def test_parse_grbl_status_report_rejects_invalid_line() -> None:
    assert parse_grbl_status_report("ok") is None


def test_motion_command_detection_does_not_treat_g21_as_motion() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")

    assert not controller._is_motion_command("G21")
    assert controller._is_motion_command("G1 X10 Y0")
    assert controller._is_motion_command("$J=G91 X1 Y0 F1200")


def test_pause_sends_realtime_feed_hold_without_ok() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")
    fake = RealtimeSerial([b"<Hold:0|MPos:1.000,2.000,0.000|FS:0,0>\n"])
    controller._serial = fake
    controller.state.connected = True

    controller.pause()

    assert fake.writes[:2] == [b"!", b"?"]
    assert controller.state.paused
    assert controller.state.status == "Hold:0"


def test_resume_sends_realtime_cycle_start_without_ok() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")
    fake = RealtimeSerial([b"<Run|MPos:1.000,2.000,0.000|FS:100,0>\n"])
    controller._serial = fake
    controller.state.connected = True
    controller.state.paused = True
    controller.state.status = "Hold:0"

    controller.resume()

    assert fake.writes[:2] == [b"~", b"?"]
    assert not controller.state.paused
    assert controller.state.status == "Run"


def test_status_query_does_not_expect_ok() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")
    fake = RealtimeSerial([b"<Idle|MPos:3.000,4.000,0.000|FS:0,0>\n"])
    controller._serial = fake
    controller.state.connected = True

    controller.query_status()

    assert fake.writes == [b"?"]
    assert controller.state.status == "Idle"
    assert controller.state.x_mm == 3.0
    assert controller.state.y_mm == 4.0


def test_current_position_prefers_wpos_over_raw_mpos() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")
    fake = RealtimeSerial([b"<Idle|MPos:13.000,23.000,0.000|WPos:10.000,20.000,0.000|FS:0,0>\n"])
    controller._serial = fake
    controller.state.connected = True

    assert controller.current_position() == (10.0, 20.0)
    assert controller.state.position_source == "WPos"
    assert controller.state.x_mm == 10.0
    assert controller.state.y_mm == 20.0


def test_current_position_uses_calculated_wpos_from_mpos_and_wco() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")
    fake = RealtimeSerial([b"<Idle|MPos:13.000,23.000,0.000|WCO:3.000,4.000,0.000|FS:0,0>\n"])
    controller._serial = fake
    controller.state.connected = True

    assert controller.current_position() == (10.0, 19.0)
    assert controller.state.position_source == "WPos (MPos-WCO)"
    assert controller.state.x_mm == 10.0
    assert controller.state.y_mm == 19.0


def test_embedded_status_line_updates_position_during_running_command() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")
    fake = RealtimeSerial([b"<Run|WPos:5.000,6.000,0.000|FS:900,0>\n", b"ok\n"])
    controller._serial = fake
    controller.state.connected = True

    response = controller.send_command("G1 X5 Y6", wait_seconds=0.1)

    assert "<Run" in response
    assert controller.state.status == "Run"
    assert controller.state.position_source == "WPos"
    assert controller.state.x_mm == 5.0
    assert controller.state.y_mm == 6.0
    assert controller.state.feed_rate == 900.0


def test_update_state_from_status_updates_position_while_hold() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")

    controller._update_state_from_status("<Hold|WPos:7.000,8.000,0.000|FS:0,0>")

    assert controller.state.paused
    assert controller.state.status == "Hold"
    assert controller.state.position_source == "WPos"
    assert controller.state.x_mm == 7.0
    assert controller.state.y_mm == 8.0


def test_alignment_pointer_reads_smax_and_disable_sends_m5_s0() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")
    fake = RealtimeSerial([b"$30=1000\n", b"$31=0\n", b"$32=1\n", b"ok\n", b"ok\n", b"ok\n", b"ok\n"])
    controller._serial = fake
    controller.state.connected = True

    controller.enable_alignment_pointer(20)

    assert fake.writes[:2] == [b"$$\n", b"M3 S50\n"]
    assert controller.state.alignment_mode_active
    assert controller.state.pointer_power_percent == 5

    controller.disable_alignment_pointer()

    assert fake.writes == [b"$$\n", b"M3 S50\n", b"M5\n", b"S0\n"]
    assert not controller.state.alignment_mode_active
    assert controller.state.pointer_power_percent == 1


def test_alignment_pointer_uses_255_smax_for_s_value() -> None:
    logs: list[str] = []
    controller = GrblSerialController(log=logs.append, port_getter=lambda: "COM1")
    controller.grbl_settings = {30: 255.0, 31: 0.0, 32: 1.0}
    fake = RealtimeSerial([b"ok\n"])
    controller._serial = fake
    controller.state.connected = True
    controller.state.status = "Idle"

    controller.enable_alignment_pointer(5)

    assert fake.writes == [b"M3 S13\n"]
    assert any("s_max=255" in message for message in logs)
    assert any("calculated_s=13" in message for message in logs)
    assert not any("M5" in write.decode("ascii") or "S0" in write.decode("ascii") for write in fake.writes)


def test_query_settings_stores_alignment_relevant_grbl_parameters() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")
    fake = RealtimeSerial([b"$30=255\n", b"$31=1\n", b"$32=1\n", b"ok\n"])
    controller._serial = fake
    controller.state.connected = True

    settings = controller.query_settings()

    assert fake.writes == [b"$$\n"]
    assert settings[30] == 255.0
    assert settings[31] == 1.0
    assert settings[32] == 1.0


def test_alignment_pointer_test_mode_turns_laser_off_after_duration(monkeypatch) -> None:
    logs: list[str] = []
    controller = GrblSerialController(log=logs.append, port_getter=lambda: "COM1")
    controller.grbl_settings = {30: 1000.0, 31: 0.0, 32: 1.0}
    fake = RealtimeSerial([b"ok\n", b"ok\n", b"ok\n"])
    controller._serial = fake
    controller.state.connected = True
    controller.state.status = "Idle"
    monkeypatch.setattr("laser_control.serial_grbl.time.sleep", lambda _seconds: None)

    controller.test_alignment_pointer(5, duration_seconds=2.0)

    assert fake.writes == [b"M3 S50\n", b"M5\n", b"S0\n"]
    assert not controller.state.alignment_mode_active
    assert any("Testmodus" in message for message in logs)
    assert any("laser-off command sent yes" in message for message in logs)


def test_stop_sets_abort_flag_and_sends_prioritized_soft_reset() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")
    fake = RealtimeSerial([b"Grbl 1.3a ['$' for help]\n"])
    controller._serial = fake
    controller.state.connected = True
    controller.state.paused = True

    controller.stop()

    assert fake.writes[0] == b"\x18"
    assert controller._abort_requested.is_set()
    assert not controller.state.paused
    assert not controller.state.homed
    assert not controller.state.alarm


def test_emergency_stop_sets_alarm_and_sends_prioritized_soft_reset() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")
    fake = RealtimeSerial([b"Grbl 1.3a ['$' for help]\n"])
    controller._serial = fake
    controller.state.connected = True
    controller.state.paused = True

    controller.emergency_stop()

    assert fake.writes[0] == b"\x18"
    assert controller._abort_requested.is_set()
    assert controller.state.alarm
    assert controller.state.status == "EmergencyStop"


def test_wait_until_idle_aborts_when_stop_requested() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")
    controller.state.connected = True
    controller._abort_requested.set()

    with pytest.raises(RuntimeError, match="abgebrochen"):
        controller._wait_until_idle(timeout_seconds=0.1)


def test_aborted_job_does_not_send_followup_m5_after_soft_reset() -> None:
    controller = AbortOnWaitController(log=lambda _message: None, port_getter=lambda: "COM1")
    fake = RealtimeSerial([b"ok\n"] * 8)
    controller._serial = fake
    controller.state.connected = True
    controller.state.homed = True

    with pytest.raises(RuntimeError, match="abgebrochen"):
        controller.start_job("G21\nG90\nM5\nS0\nG0 X1 Y1", 10.0, 10.0)

    assert fake.writes.count(b"M5\n") == 2


def test_disconnect_sets_abort_flag_for_active_job() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")
    fake = RealtimeSerial([])
    controller._serial = fake
    controller.state.connected = True

    controller.disconnect()

    assert controller._abort_requested.is_set()


def test_unlock_sends_dollar_x_and_clears_alarm_without_homing() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")
    serial = RealtimeSerial([b"[MSG:Caution: Unlocked]\r\n", b"ok\r\n"])
    controller._serial = serial
    controller._update_state_from_status("<Alarm|MPos:0.000,0.000,0.000|FS:0,0>")

    controller.unlock()

    assert b"$X\n" in serial.writes
    assert not controller.state.alarm
    assert controller.state.status == "Idle"
    assert not controller.state.homed
    controller.shutdown()


def test_require_ready_follows_profile_homing_policy() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")
    controller._serial = SilentSerial()

    with pytest.raises(RuntimeError, match="Referenzfahrt"):
        controller._require_ready()

    controller.homing_required = False
    controller._require_ready()
    controller.shutdown()


def test_work_offset_is_kept_for_status_reports_without_wco() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")

    controller._update_state_from_status("<Idle|MPos:110.000,220.000,0.000|FS:0,0|WCO:100.000,200.000,0.000>")
    first = (controller.state.x_mm, controller.state.y_mm, controller.state.position_source)
    controller._update_state_from_status("<Idle|MPos:110.000,220.000,0.000|FS:0,0>")
    second = (controller.state.x_mm, controller.state.y_mm, controller.state.position_source)

    assert first == second == (10.0, 20.0, "WPos (MPos-WCO)")

    controller.disconnect(log_message=False)
    controller._update_state_from_status("<Idle|MPos:110.000,220.000,0.000|FS:0,0>")
    assert (controller.state.x_mm, controller.state.y_mm) == (110.0, 220.0)
    controller.shutdown()


def test_frame_is_not_cancelled_by_an_earlier_stop() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")
    controller._serial = RealtimeSerial([b"ok\r\n"] * 20)
    controller.state.homed = True
    controller._abort_requested.set()  # left over from a previous Stop/Disconnect
    abort_seen_while_waiting: list[bool] = []
    controller._wait_until_idle = lambda timeout_seconds: abort_seen_while_waiting.append(
        controller._abort_requested.is_set()
    )

    controller.frame(20.0, 10.0)

    assert abort_seen_while_waiting == [False]
    controller.shutdown()


def test_emergency_stop_sends_soft_reset_before_any_laser_off_command(monkeypatch) -> None:
    monkeypatch.setattr("laser_control.serial_grbl.time.sleep", lambda _seconds: None)
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")
    serial = RealtimeSerial([])  # no acknowledgements at all
    controller._serial = serial
    controller.state.alignment_mode_active = True

    controller.emergency_stop()

    assert serial.writes[0] == b"\x18"
    assert not any(value.startswith((b"M5", b"S0")) for value in serial.writes)
    assert not controller.state.alignment_mode_active
    assert controller.state.alarm
    controller.shutdown()


def test_work_offset_is_read_on_connect_before_any_wco_report() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")
    controller._serial = RealtimeSerial(
        [
            b"[GC:G0 G54 G17 G21 G90 G94 M5 M9 T0 F0 S0.000]\r\n",
            b"ok\r\n",
            b"[G54:3.000,3.000,0.000]\r\n",
            b"[G55:0.000,0.000,0.000]\r\n",
            b"[G92:0.500,0.000,0.000]\r\n",
            b"[TLO:0.000]\r\n",
            b"ok\r\n",
        ]
    )

    controller._load_work_offset()
    # First status report after connecting carries no WCO field.
    controller._update_state_from_status("<Idle|MPos:0.000,0.000,0.000|FS:0,0>")

    assert (controller.state.x_mm, controller.state.y_mm) == (-3.5, -3.0)
    assert controller.state.position_source == "WPos (MPos-WCO)"
    controller.shutdown()


def test_grbl_settings_are_dropped_on_disconnect_so_pointer_power_uses_new_machine() -> None:
    controller = GrblSerialController(log=lambda _message: None, port_getter=lambda: "COM1")
    controller.grbl_settings = {30: 1000.0, 32: 1.0}  # cached from the previous machine
    assert controller._alignment_s_value(5) == 50

    controller.disconnect(log_message=False)
    assert controller.grbl_settings == {}

    # New machine with $30=100: the 5 % pointer must be S5, not S50.
    controller._serial = RealtimeSerial([b"$30=100.000\r\n", b"$32=1\r\n", b"ok\r\n"])
    assert controller._alignment_s_value(5) == 5
    controller.shutdown()
