import pytest

from laser_control.gcode import (
    CUT_MODE,
    FALCON_MAX_HEIGHT_MM,
    FALCON_MAX_WIDTH_MM,
    build_dry_run_gcode,
    build_polyline_gcode,
    build_rectangle_frame_gcode,
    prepare_job_gcode,
    validate_falcon_work_area,
)
from laser_control.models import MaterialProfile


def test_prepare_job_gcode_strips_comments_and_appends_m5() -> None:
    gcode = """
    ; header
    G21 ; units
    G0 X0 Y0
    G1 X10 Y5 S400 ; cut
    """

    commands = prepare_job_gcode(gcode, 100.0, 80.0)

    assert commands == ["G21", "G0 X0 Y0", "G1 X10 Y5 S400", "M5"]


def test_prepare_job_gcode_rejects_without_motion() -> None:
    with pytest.raises(ValueError, match="keine Bewegungsbefehle"):
        prepare_job_gcode("G21\nM3 S200\nM5", 80.0, 60.0)


def test_validate_falcon_work_area_rejects_oversize() -> None:
    with pytest.raises(ValueError, match="Falcon-Limit"):
        validate_falcon_work_area(FALCON_MAX_WIDTH_MM + 1, FALCON_MAX_HEIGHT_MM)


def test_build_polyline_gcode_reenables_laser_after_travel_m5() -> None:
    profile = MaterialProfile(name="Test", power_percent=50, speed_mm_min=1200, passes=1)
    paths = [[(0.0, 0.0), (10.0, 0.0)], [(20.0, 0.0), (20.0, 10.0)]]

    lines = build_polyline_gcode(paths, profile).splitlines()

    first_path_start = lines.index("G0 X0.00 Y0.00 F1200")
    second_path_start = lines.index("G0 X20.00 Y0.00 F1200")
    assert lines[first_path_start - 1] == "M5"
    assert lines[first_path_start + 1].startswith("M4")
    assert lines[second_path_start - 1] == "M5"
    assert lines[second_path_start + 1].startswith("M4")


def test_build_polyline_gcode_uses_m3_in_cut_mode() -> None:
    profile = MaterialProfile(name="Cut", power_percent=70, speed_mm_min=900, passes=1)
    paths = [[(0.0, 0.0), (15.0, 0.0)]]

    lines = build_polyline_gcode(paths, profile, CUT_MODE).splitlines()

    assert "M3 ; constant laser power" in lines
    assert "M4 ; dynamic laser power" not in lines


def test_build_rectangle_frame_gcode_uses_mode_specific_laser_command() -> None:
    profile = MaterialProfile(name="Default", power_percent=40, speed_mm_min=1000, passes=1)

    engrave_lines = build_rectangle_frame_gcode(50.0, 30.0, profile).splitlines()
    cut_lines = build_rectangle_frame_gcode(50.0, 30.0, profile, CUT_MODE).splitlines()

    assert "M4 ; dynamic laser power" in engrave_lines
    assert "M3 ; constant laser power" in cut_lines


def test_build_dry_run_gcode_forces_laser_off_and_strips_power() -> None:
    gcode = "\n".join(
        [
            "G21",
            "M4",
            "G0 X0 Y0 F1200",
            "G1 X10 Y0 S500 F1200",
            "S300",
            "M3",
            "G1 X10 Y10 S250 F1200",
            "M5",
        ]
    )

    dry = build_dry_run_gcode(gcode, 100.0, 100.0).splitlines()

    assert dry[0] == "M5"
    assert dry[-1] == "M5"
    assert "M3" not in dry
    assert "M4" not in dry
    assert all(" S" not in line.upper() for line in dry)
