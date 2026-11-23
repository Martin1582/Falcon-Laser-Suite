from laser_control.serial_consistency import SerialConsistencyTracker


def test_serial_consistency_accepts_matching_tx_rx_and_position() -> None:
    tracker = SerialConsistencyTracker("Test")

    tracker.record_tx("G0 X5.000 Y5.000 F500", expects_ack=True)
    tracker.record_rx("ok")
    tracker.record_tx("G1 X48.730 Y33.070 S100 F500", expects_ack=True)
    tracker.record_rx("ok")
    tracker.record_tx("?", expects_ack=False)
    tracker.record_rx("<Idle|MPos:48.725,33.075,0.000|FS:0,0>")

    report = tracker.report()

    assert report.is_consistent
    assert report.expected_ack_count == 2
    assert report.ok_count == 2
    assert report.status_query_count == 1
    assert report.last_command_position == (48.73, 33.07)
    assert report.last_status_position == (48.725, 33.075)


def test_serial_consistency_reports_missing_ack_and_position_mismatch() -> None:
    tracker = SerialConsistencyTracker("Test", position_tolerance_mm=0.1)

    tracker.record_tx("G1 X70.000 Y70.000 F500", expects_ack=True)
    tracker.record_tx("?", expects_ack=False)
    tracker.record_rx("<Idle|MPos:68.000,70.000,0.000|FS:0,0>")

    report = tracker.report()

    assert not report.is_consistent
    assert report.missing_ack_count == 1
    assert any("fehlen" in warning for warning in report.warnings)
    assert any("Endposition weicht ab" in warning for warning in report.warnings)
