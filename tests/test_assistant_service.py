from laser_control.gcode import CUT_MODE, ENGRAVE_MODE
from laser_control.gcode_analysis import analyze_gcode
from laser_control.job_history import JobHistoryEntry
from laser_control.models import MaterialProfile
from laser_control.services.assistant_service import AssistantService


def test_assistant_prefers_matching_successful_history() -> None:
    service = AssistantService()
    profile = MaterialProfile("Lindenholz 2 mm", 100, 350, 1)
    history = [
        JobHistoryEntry(
            timestamp="2026-05-01T10:00:00",
            material_name="Lindenholz 2 mm",
            operation_mode=CUT_MODE,
            power_percent=90,
            speed_mm_min=400,
            passes=1,
            work_width_mm=100,
            work_height_mm=100,
            command_count=10,
            movement_count=4,
            estimated_runtime_seconds=30,
            warning_count=0,
            result="good",
            notes="sauber",
        )
    ]

    analysis = analyze_gcode("G0 X0 Y0\nG1 X10 Y10 S900 F400\nM5", 100, 100)
    advice = service.advise("Lindenholz 2 mm", CUT_MODE, profile, analysis, [], history)

    assert advice.matching_successes == history
    assert any("Letzter guter Job" in item for item in advice.recommendations)


def test_assistant_generates_test_matrix_gcode() -> None:
    service = AssistantService()
    profile = MaterialProfile("Probe", 50, 1000, 1)

    gcode = service.build_test_matrix_gcode("Probe", ENGRAVE_MODE, profile)

    assert "Testmatrix" in gcode
    assert gcode.count("; Feld") == 9
    assert "M4 ; dynamic laser power" in gcode
