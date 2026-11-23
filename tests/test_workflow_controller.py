from laser_control.gcode import ENGRAVE_MODE
from laser_control.fill_toolpath import build_layer_fill_toolpaths
from laser_control.layers import LayerMode, build_default_layers
from laser_control.machine_log import MachineActionLog, MachineLogStatus
from laser_control.models import LaserState, MaterialProfile
from laser_control.services.job_service import JobService
from laser_control.workflow_controller import JobContext, WorkflowController


class Controller:
    def __init__(self, connected: bool = False, homed: bool = False) -> None:
        self.state = LaserState(connected=connected, homed=homed)


def test_preflight_blocks_hardware_without_connection_and_homing() -> None:
    profile = MaterialProfile("Holz", 40, 1200, 1)
    log = MachineActionLog()
    messages: list[str] = []
    workflow = WorkflowController(JobService(), log, messages.append)

    result = workflow.prepare_preflight(
        JobContext(
            controller=Controller(False, False),
            connection_mode="GRBL ueber USB",
            selected_port="COM1",
            machine_label="Controller",
            work_width_mm=100,
            work_height_mm=80,
            material_profile=profile,
            operation_mode=ENGRAVE_MODE,
            origin_label="Links unten",
            gcode="G0 X0 Y0\nG1 X10 Y10 S400\nM5",
            layers=build_default_layers(profile, ENGRAVE_MODE),
            job_kind="Einzelstueck",
            auto_home_after_success=True,
        )
    )

    assert not result.can_start
    assert any("nicht verbunden" in blocker for blocker in result.blockers)
    assert any("Referenzfahrt" in blocker for blocker in result.blockers)
    assert any(entry.status == MachineLogStatus.ERROR for entry in log.entries)


def test_preflight_accepts_valid_simulator_job_and_summarizes_layers() -> None:
    profile = MaterialProfile("Holz", 40, 1200, 1)
    workflow = WorkflowController(JobService(), MachineActionLog(), lambda _message: None)

    result = workflow.prepare_preflight(
        JobContext(
            controller=Controller(True, True),
            connection_mode="Simulator",
            selected_port="",
            machine_label="Simulator",
            work_width_mm=100,
            work_height_mm=80,
            material_profile=profile,
            operation_mode=ENGRAVE_MODE,
            origin_label="Links unten",
            gcode="G0 X0 Y0\nG1 X10 Y10 S400\nM5",
            layers=build_default_layers(profile, ENGRAVE_MODE),
            job_kind="Einzelstueck",
            auto_home_after_success=True,
        )
    )

    assert result.can_start
    summary = "\n".join(result.summary_lines())
    assert "Aktive Layer: 1" in summary
    assert "Durchgaenge" in summary
    assert "Homing:" in summary
    assert "Ausrichtmodus aktiv: nein" in summary
    assert "Job-Art: Einzelstueck" in summary
    assert "Auto-Home nach Abschluss: Ja" in summary
    assert any("Frame-Test" in warning for warning in result.warnings)
    diagnostics = "\n".join(result.start_condition_lines())
    assert "[OK] PreparedJob vorhanden" in diagnostics
    assert "[OK] GCode vorhanden" in diagnostics
    assert "[OK] Aktive Layer" in diagnostics
    assert "[OK] Frame-Test verlangt (nein - nur Empfehlung)" in diagnostics
    assert "[OK] preflight_confirmed vor Dialog" in diagnostics
    assert "[OK] Startbutton aktiviert" in diagnostics


def test_preflight_summarizes_fill_mode_and_open_contour_warning() -> None:
    profile = MaterialProfile("Holz", 40, 1200, 1)
    workflow = WorkflowController(JobService(), MachineActionLog(), lambda _message: None)
    layers = build_default_layers(profile, ENGRAVE_MODE)
    layers[0].mode = LayerMode.FILL
    layers[0].fill_spacing_mm = 0.08
    layers[0].fill_angle_deg = 45
    paths = [
        [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0)],
        [(20.0, 0.0), (25.0, 5.0)],
    ]
    fills = build_layer_fill_toolpaths(paths, layers)

    result = workflow.prepare_preflight(
        JobContext(
            controller=Controller(True, True),
            connection_mode="Simulator",
            selected_port="",
            machine_label="Simulator",
            work_width_mm=100,
            work_height_mm=80,
            material_profile=profile,
            operation_mode=ENGRAVE_MODE,
            origin_label="Links unten",
            gcode="G0 X0 Y0\nM4\nG1 X10 Y1 S400 F1200\nM5",
            layers=layers,
            fill_toolpaths=fills,
        )
    )

    summary = "\n".join(result.summary_lines())
    assert "Modus Fuellung" in summary
    assert "Fuellabstand: 0.08 mm" in summary
    assert "Fuellwinkel: 45 deg" in summary
    assert "Geschlossene Flaeche: ja" in summary
    assert "Geschaetzte Fuelllinien:" in summary
    assert "Overscan: aus" in summary
    assert not result.can_start
    assert any("offene Kontur" in warning for warning in result.warnings)
    assert any("nicht sicher" in blocker for blocker in result.blockers)


def test_preflight_blocks_fill_without_closed_shape() -> None:
    profile = MaterialProfile("Holz", 40, 1200, 1)
    workflow = WorkflowController(JobService(), MachineActionLog(), lambda _message: None)
    layers = build_default_layers(profile, ENGRAVE_MODE)
    layers[0].mode = LayerMode.FILL
    fills = build_layer_fill_toolpaths([[(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)]], layers)

    result = workflow.prepare_preflight(
        JobContext(
            controller=Controller(True, True),
            connection_mode="Simulator",
            selected_port="",
            machine_label="Simulator",
            work_width_mm=100,
            work_height_mm=80,
            material_profile=profile,
            operation_mode=ENGRAVE_MODE,
            origin_label="Links unten",
            gcode="G0 X0 Y0\nM4\nG1 X10 Y1 S400 F1200\nM5",
            layers=layers,
            fill_toolpaths=fills,
        )
    )

    assert not result.can_start
    assert any("nicht sicher" in blocker for blocker in result.blockers)


def test_preflight_blocks_unsafe_nested_fill() -> None:
    profile = MaterialProfile("Holz", 40, 1200, 1)
    workflow = WorkflowController(JobService(), MachineActionLog(), lambda _message: None)
    layers = build_default_layers(profile, ENGRAVE_MODE)
    layers[0].mode = LayerMode.FILL
    paths = [
        [(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0), (0.0, 0.0)],
        [(5.0, 5.0), (15.0, 5.0), (15.0, 15.0), (5.0, 15.0), (5.0, 5.0)],
    ]
    fills = build_layer_fill_toolpaths(paths, layers)

    result = workflow.prepare_preflight(
        JobContext(
            controller=Controller(True, True),
            connection_mode="Simulator",
            selected_port="",
            machine_label="Simulator",
            work_width_mm=100,
            work_height_mm=80,
            material_profile=profile,
            operation_mode=ENGRAVE_MODE,
            origin_label="Links unten",
            gcode="; G-Code nicht erzeugt\n; SVG-Fuellung bei verschachtelten Konturen aktuell nicht sicher unterstuetzt.",
            layers=layers,
            fill_toolpaths=fills,
        )
    )

    assert not result.can_start
    assert any("nicht sicher" in blocker for blocker in result.blockers)
    assert any("verschachtelten Konturen" in warning for warning in result.warnings)


def test_preflight_allows_outline_mode_for_nested_contours() -> None:
    profile = MaterialProfile("Holz", 40, 1200, 1)
    workflow = WorkflowController(JobService(), MachineActionLog(), lambda _message: None)
    layers = build_default_layers(profile, ENGRAVE_MODE)
    layers[0].mode = LayerMode.OUTLINE

    result = workflow.prepare_preflight(
        JobContext(
            controller=Controller(True, True),
            connection_mode="Simulator",
            selected_port="",
            machine_label="Simulator",
            work_width_mm=100,
            work_height_mm=80,
            material_profile=profile,
            operation_mode=ENGRAVE_MODE,
            origin_label="Links unten",
            gcode="G0 X0 Y0\nG1 X20 Y0 S400\nG1 X20 Y20\nG1 X0 Y20\nG1 X0 Y0\nM5",
            layers=layers,
            fill_toolpaths=[],
        )
    )

    assert result.can_start


def test_preflight_summarizes_active_alignment_mode() -> None:
    profile = MaterialProfile("Holz", 40, 1200, 1)
    workflow = WorkflowController(JobService(), MachineActionLog(), lambda _message: None)

    result = workflow.prepare_preflight(
        JobContext(
            controller=Controller(True, True),
            connection_mode="Simulator",
            selected_port="",
            machine_label="Simulator",
            work_width_mm=100,
            work_height_mm=80,
            material_profile=profile,
            operation_mode=ENGRAVE_MODE,
            origin_label="Links unten",
            gcode="G0 X0 Y0\nG1 X10 Y10 S400\nM5",
            layers=build_default_layers(profile, ENGRAVE_MODE),
            alignment_mode_active=True,
        )
    )

    assert result.can_start
    assert "Ausrichtmodus aktiv: ja" in "\n".join(result.summary_lines())


def test_preflight_marks_optional_unhomed_start_as_explicit_confirmation() -> None:
    profile = MaterialProfile("Holz", 40, 1200, 1)
    workflow = WorkflowController(JobService(), MachineActionLog(), lambda _message: None)

    result = workflow.prepare_preflight(
        JobContext(
            controller=Controller(True, False),
            connection_mode="GRBL ueber USB",
            selected_port="COM1",
            machine_label="Controller",
            work_width_mm=100,
            work_height_mm=80,
            material_profile=profile,
            operation_mode=ENGRAVE_MODE,
            origin_label="Links unten",
            gcode="G0 X0 Y0\nG1 X10 Y10 S400\nM5",
            layers=build_default_layers(profile, ENGRAVE_MODE),
            machine_phase="idle",
            machine_profile_name="Optional Homing Controller",
            homing_required=False,
            allow_unhomed_start=True,
        )
    )

    assert result.can_start
    assert result.requires_unhomed_confirmation
    summary = "\n".join(result.summary_lines())
    assert "Homing laut Maschinenprofil optional" in summary
    assert "Bestaetigung erforderlich" in summary


def test_preflight_blocks_raster_source_until_raster_gcode_exists() -> None:
    profile = MaterialProfile("Holz", 40, 1200, 1)
    workflow = WorkflowController(JobService(), MachineActionLog(), lambda _message: None)

    result = workflow.prepare_preflight(
        JobContext(
            controller=Controller(True, True),
            connection_mode="GRBL ueber USB",
            selected_port="COM1",
            machine_label="Controller",
            work_width_mm=100,
            work_height_mm=80,
            material_profile=profile,
            operation_mode=ENGRAVE_MODE,
            origin_label="Links unten",
            gcode="; Rastergravur-GCode noch nicht verfuegbar.",
            layers=build_default_layers(profile, ENGRAVE_MODE),
            machine_phase="idle",
            source_name="photo.png",
            source_type="raster",
            raster_gcode_available=False,
            autofit_applied=True,
            source_original_width_mm=600.0,
            source_original_height_mm=800.0,
            source_current_width_mm=311.2,
            source_current_height_mm=415.0,
            autofit_scale_percent=51.9,
            autofit_position="zentriert",
        )
    )

    assert not result.can_start
    assert any("Rastergravur-GCode" in blocker for blocker in result.blockers)
    summary = "\n".join(result.summary_lines())
    assert "photo.png" in summary
    assert "AutoFit: Motiv automatisch eingepasst" in summary
    assert "Skalierung: 51.9%" in summary


def test_preflight_summarizes_transform_position_and_current_size() -> None:
    profile = MaterialProfile("Holz", 40, 1200, 1)
    workflow = WorkflowController(JobService(), MachineActionLog(), lambda _message: None)

    result = workflow.prepare_preflight(
        JobContext(
            controller=Controller(True, True),
            connection_mode="Simulator",
            selected_port="",
            machine_label="Simulator",
            work_width_mm=100,
            work_height_mm=80,
            material_profile=profile,
            operation_mode=ENGRAVE_MODE,
            origin_label="Links unten",
            gcode="G0 X10 Y20\nG1 X60 Y45 S400\nM5",
            layers=build_default_layers(profile, ENGRAVE_MODE),
            source_name="motiv.svg",
            source_type="vector",
            autofit_applied=True,
            source_original_width_mm=200.0,
            source_original_height_mm=100.0,
            source_current_width_mm=50.0,
            source_current_height_mm=25.0,
            source_x_mm=10.0,
            source_y_mm=20.0,
            source_bounds_ok=True,
            autofit_scale_percent=25.0,
            head_x_mm=9.0,
            head_y_mm=7.0,
            head_position_source="WPos",
        )
    )

    summary = "\n".join(result.summary_lines())

    assert result.can_start
    assert "Quelle: motiv.svg (vector)" in summary
    assert "Aktuelle Groesse: 50.0 x 25.0 mm" in summary
    assert "Position: X 10.0 mm, Y 20.0 mm" in summary
    assert "Arbeitsbereich: OK" in summary
    assert "Kopfposition: WPos X 9.00 mm, Y 7.00 mm" in summary


def test_preflight_blocks_artwork_outside_work_area() -> None:
    profile = MaterialProfile("Holz", 40, 1200, 1)
    workflow = WorkflowController(JobService(), MachineActionLog(), lambda _message: None)

    result = workflow.prepare_preflight(
        JobContext(
            controller=Controller(True, True),
            connection_mode="Simulator",
            selected_port="",
            machine_label="Simulator",
            work_width_mm=100,
            work_height_mm=80,
            material_profile=profile,
            operation_mode=ENGRAVE_MODE,
            origin_label="Links unten",
            gcode="G0 X-5 Y10\nG1 X10 Y10 S400\nM5",
            layers=build_default_layers(profile, ENGRAVE_MODE),
            source_name="motiv.svg",
            source_type="vector",
            source_original_width_mm=20.0,
            source_original_height_mm=20.0,
            source_current_width_mm=20.0,
            source_current_height_mm=20.0,
            source_x_mm=-5.0,
            source_y_mm=10.0,
            source_bounds_ok=False,
            autofit_scale_percent=100.0,
        )
    )

    assert not result.can_start
    assert any("ausserhalb" in blocker for blocker in result.blockers)
    assert "[BLOCK] Arbeitsbereich OK" in "\n".join(result.start_condition_lines())


def test_preflight_blocks_multi_project_without_active_artwork() -> None:
    profile = MaterialProfile("Kunstleder", 20, 1000, 1)
    workflow = WorkflowController(JobService(), MachineActionLog(), lambda _message: None)

    result = workflow.prepare_preflight(
        JobContext(
            controller=Controller(True, True),
            connection_mode="Simulator",
            selected_port="",
            machine_label="Simulator",
            work_width_mm=100,
            work_height_mm=30,
            material_profile=profile,
            operation_mode=ENGRAVE_MODE,
            origin_label="Links unten",
            gcode="; G-Code nicht erzeugt\n; Kein aktives Motiv vorhanden.",
            layers=build_default_layers(profile, ENGRAVE_MODE),
            source_name="Keine aktiven Motive",
            source_type="multi",
            active_artwork_count=0,
        )
    )

    assert not result.can_start
    assert any("Kein aktives Motiv" in blocker for blocker in result.blockers)


def test_preflight_warns_when_hardware_head_position_is_unknown() -> None:
    profile = MaterialProfile("Holz", 40, 1200, 1)
    workflow = WorkflowController(JobService(), MachineActionLog(), lambda _message: None)

    result = workflow.prepare_preflight(
        JobContext(
            controller=Controller(True, True),
            connection_mode="GRBL ueber USB",
            selected_port="COM1",
            machine_label="Controller",
            work_width_mm=100,
            work_height_mm=80,
            material_profile=profile,
            operation_mode=ENGRAVE_MODE,
            origin_label="Links unten",
            gcode="G0 X0 Y0\nG1 X10 Y10 S400\nM5",
            layers=build_default_layers(profile, ENGRAVE_MODE),
            machine_phase="idle",
            source_name="motiv.svg",
            source_type="vector",
            source_bounds_ok=True,
        )
    )

    assert any("Kopfposition" in warning for warning in result.warnings)
    assert "Kopfposition: --" in "\n".join(result.summary_lines())
