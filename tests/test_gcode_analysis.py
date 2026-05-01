from laser_control.gcode_analysis import analyze_gcode


def test_analyze_gcode_reports_bounds_runtime_and_warnings() -> None:
    gcode = "\n".join(
        [
            "G21",
            "G90",
            "M4",
            "G0 X0 Y0 F1200",
            "G1 X20 Y0 S950 F600",
            "G1 X20 Y10 S950 F600",
            "M5",
        ]
    )

    analysis = analyze_gcode(gcode, 10, 10)

    assert analysis.movement_count == 3
    assert analysis.max_x == 20
    assert analysis.max_laser_power_percent == 95
    assert analysis.estimated_runtime_seconds > 0
    assert any("ausserhalb" in warning for warning in analysis.warnings)
    assert any("Sehr hohe Laserleistung" in warning for warning in analysis.warnings)


def test_analyze_gcode_warns_on_relative_positioning() -> None:
    analysis = analyze_gcode("G91\nG0 X1 Y1\nM5", 20, 20)

    assert analysis.uses_relative_positioning
    assert any("Relative Positionierung" in warning for warning in analysis.warnings)
