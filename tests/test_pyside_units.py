import pytest
from dataclasses import replace

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGroupBox, QSizePolicy, QWidget
from PySide6.QtWidgets import QDialog

from laser_control.artwork_import import ArtworkSourceType, VectorArtworkSource
from laser_control.artwork_transform import ArtworkTransform
from laser_control.machine_profiles import MachineProfile, MachineProfileRepository
from laser_control.machine_profile_dialog import MachineProfileDialog
from laser_control.machine_state import MachinePhase
from laser_control.layers import LayerMode
from laser_control.models import MaterialProfile
from laser_control.pyside_app import LaserControlWindow
from laser_control.project import project_to_dict, save_project
from laser_control.qt_panels import PreflightDialog


def test_pyside_spin_boxes_show_units(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()

    assert window.work_width.suffix() == " mm"
    assert window.material_db_width.suffix() == " mm"
    assert window.svg_offset_x.suffix() == " mm"
    assert window.power_percent.suffix() == " %"
    assert window.speed_mm_min.suffix() == " mm/min"
    assert window.passes.suffix() == " x"
    assert window.material_shape.currentText() == "Rechteck"
    assert window.job_origin.currentText() == "Links unten"


def test_pyside_theme_switch_toggles_light_and_dark(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.theme_switch.setChecked(False)

    assert not window.dark_mode_enabled
    assert window.theme_switch.text() == "Light"

    window.theme_switch.setChecked(True)

    assert window.dark_mode_enabled
    assert window.theme_switch.text() == "Dark"
    stylesheet = window.styleSheet()
    assert "QScrollBar::handle:vertical" in stylesheet
    assert "QTableWidget::item:selected" in stylesheet
    assert "border-radius" in stylesheet
    assert window.preview.material_surface_color.name() == "#262a30"


def test_pyside_has_right_sidebar(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()

    assert window.right_sidebar.minimumWidth() == 320
    assert window.right_sidebar.maximumWidth() == 350
    assert not window.workspace_splitter.childrenCollapsible()
    assert window.gcode_group.parent() is not None
    assert window.assistant_summary.parent() is not None
    assert window.layer_panel.parent() is not None
    assert window.expert_tabs.count() == 2
    assert window.expert_tabs.tabText(0) == "G-Code"
    assert window.expert_tabs.tabText(1) == "Log"
    assert not window.diagnostics_group.isChecked()
    assert window.expert_tabs.isHidden()
    assert "Material:" in window.material_summary.text()
    assert "Projekt:" in window.project_summary.text()
    assert "Maschine" in window.workflow_status.text()
    assert "Naechster Schritt:" in window.workflow_status.text()


def test_pyside_has_left_sidebar(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()

    assert window.left_sidebar.minimumWidth() == 300
    assert window.left_sidebar.maximumWidth() == 340
    assert window.sidebar_scroll.widget() is window.sidebar_toolbox
    assert window.sidebar_scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert not window.main_splitter.childrenCollapsible()
    assert list(window.sidebar_sections) == ["Maschine", "Positionierung", "Projekt", "Job", "Diagnose"]
    assert window.sidebar_sections["Maschine"].isChecked()
    assert window.sidebar_sections["Job"].isChecked()
    assert not window.sidebar_sections["Positionierung"].isChecked()
    assert not window.sidebar_sections["Projekt"].isChecked()
    assert not window.sidebar_sections["Diagnose"].isChecked()


def test_pyside_machine_sidebar_keeps_secondary_actions_collapsed(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()

    assert not window.machine_panel.advanced_group.isChecked()
    assert window.machine_panel.refresh_button.isHidden()
    assert window.machine_panel.detect_button.isHidden()
    assert window.machine_panel.profile_edit_button.isHidden()

    window.machine_panel.advanced_group.setChecked(True)

    assert not window.machine_panel.refresh_button.isHidden()
    assert not window.machine_panel.detect_button.isHidden()
    assert not window.machine_panel.profile_edit_button.isHidden()


def test_pyside_compact_layout_prioritizes_preview(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.resize(1600, 980)
    window.show()
    app.processEvents()

    assert window.preview.isVisible()
    assert window.preview.height() >= 400
    assert window.status_panel.height() <= 28
    assert window.workflow_status.maximumHeight() == 58
    assert window.svg_size_label.maximumHeight() == 22
    assert window.transform_button.isVisible()
    assert window.transform_body.isHidden()
    assert window.expert_tabs.isHidden()
    window.close()


def test_pyside_empty_states_and_context_controls(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.layer_panel.set_layers([])
    window._refresh_object_table()
    window._update_job_summary()

    assert "Noch keine Motive" in window.project_summary.text()
    assert not window.project_empty_state.isHidden()
    assert not window.layer_panel.empty_state.isHidden()
    assert not window.layer_panel.isEnabled()
    assert not window.transform_group.isEnabled()
    assert not window.action_buttons["frame"][0].isEnabled()
    assert not window.action_buttons["dry_run"][0].isEnabled()
    assert not window.action_buttons["start_job"][0].isEnabled()


def test_pyside_transform_dialog_opens(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])
    opened = []

    def fake_exec(dialog) -> QDialog.DialogCode:
        opened.append(dialog.windowTitle())
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr("PySide6.QtWidgets.QDialog.exec", fake_exec)
    window = LaserControlWindow()

    window._open_transform_dialog()

    assert opened == ["Motiv transformieren"]
    assert window.transform_body.isHidden()


def test_pyside_transform_dialog_accepts_values_and_updates_preview(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    window.original_imported_paths = [[(0.0, 0.0), (20.0, 0.0), (20.0, 10.0), (0.0, 10.0)]]
    window.artwork_transform = ArtworkTransform(0.0, 0.0, 1.0, 20.0, 10.0, 20.0, 10.0)
    window._commit_artwork_transform(window.artwork_transform)

    def fake_exec(dialog) -> QDialog.DialogCode:
        window.svg_offset_x.setValue(100.0)
        window.svg_offset_y.setValue(50.0)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr("PySide6.QtWidgets.QDialog.exec", fake_exec)

    window._open_transform_dialog()

    assert window.artwork_transform is not None
    assert window.artwork_transform.x_mm == 100.0
    assert window.artwork_transform.y_mm == 50.0
    assert window.preview.preview_model.bounds is not None
    assert window.preview.preview_model.bounds.min_x == 100.0
    assert window.preview.preview_model.bounds.min_y == 50.0
    assert "G0 X100.00 Y50.00" in window.gcode_text.toPlainText()


def test_pyside_transform_dialog_cancel_restores_previous_values(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    window.original_imported_paths = [[(0.0, 0.0), (20.0, 0.0), (20.0, 10.0), (0.0, 10.0)]]
    original_transform = ArtworkTransform(12.0, 8.0, 1.0, 20.0, 10.0, 20.0, 10.0)
    window.artwork_transform = original_transform
    window._commit_artwork_transform(window.artwork_transform)

    def fake_exec(dialog) -> QDialog.DialogCode:
        window.svg_offset_x.setValue(100.0)
        window.svg_offset_y.setValue(50.0)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr("PySide6.QtWidgets.QDialog.exec", fake_exec)

    window._open_transform_dialog()

    assert window.artwork_transform == original_transform
    assert window.svg_auto.isChecked()
    assert window.preview.preview_model.bounds is not None
    assert window.preview.preview_model.bounds.min_x == 12.0
    assert window.preview.preview_model.bounds.min_y == 8.0
    assert "G0 X12.00 Y8.00" in window.gcode_text.toPlainText()
    assert "G0 X100.00 Y50.00" not in window.gcode_text.toPlainText()


def test_pyside_material_tab_contains_jog_and_sidebar_controls_expand(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.sidebar_sections["Positionierung"].setChecked(True)
    position_page = window.sidebar_sections["Positionierung"].findChild(QWidget)
    group_titles = [group.title() for group in position_page.findChildren(QGroupBox)]

    assert "Position / Jog" in group_titles
    assert "Projekt" in window.sidebar_sections
    assert window.serial_port.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert window.connection_mode.view().minimumWidth() >= 260


def test_pyside_material_measurement_uses_all_set_corners(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.material_points = {
        1: (10.0, 5.0),
        2: (110.0, 6.0),
        3: (112.0, 85.0),
        4: (8.0, 84.0),
    }

    window._apply_material_measurement()

    assert window.work_width.value() == 104.0
    assert window.work_height.value() == 80.0
    assert "Ecke 4" in window.material_measurement_label.text()
    assert len(window.material_measurement["points"]) == 4


def test_pyside_new_material_profile_can_be_saved_and_selected(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()

    profile = window._save_new_material_profile(
        "Falcon Sperrholz 3mm",
        "Sperrholz",
        3.0,
        1200,
        42,
        2,
        "Gravur",
        "sauberer Test",
    )

    assert profile.name == "Falcon Sperrholz 3mm"
    assert window.profile_name.currentText() == "Falcon Sperrholz 3mm"
    assert window.profile_name.findText("Falcon Sperrholz 3mm") >= 0
    assert window.speed_mm_min.value() == 1200
    assert window.power_percent.value() == 42
    assert window.passes.value() == 2
    assert "Typ: Sperrholz" in profile.notes
    assert "Staerke: 3.00 mm" in profile.notes
    assert "Materialprofil angelegt" in window.log_text.toPlainText()
    assert (tmp_path / "material_profiles.json").exists()

    restarted = LaserControlWindow()
    assert restarted.profile_name.findText("Falcon Sperrholz 3mm") >= 0


@pytest.mark.parametrize(
    ("name", "speed", "power", "passes"),
    [
        ("", 1200, 40, 1),
        ("Falcon Test", 0, 40, 1),
        ("Falcon Test", 1200, 101, 1),
        ("Falcon Test", 1200, 40, 0),
    ],
)
def test_pyside_invalid_material_profile_is_blocked(monkeypatch, tmp_path, name, speed, power, passes) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()

    with pytest.raises(ValueError):
        window._save_new_material_profile(name, "", 0.0, speed, power, passes, "Gravur")


def test_pyside_duplicate_material_profile_updates_existing_record(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window._save_new_material_profile("Test Kunstleder", "Kunstleder", 1.0, 2000, 20, 1, "Gravur")
    window._save_new_material_profile("Test Kunstleder", "Kunstleder", 1.0, 2400, 22, 2, "Gravur")

    restarted = LaserControlWindow()
    profile = restarted.profile_service.profile_for("Test Kunstleder", restarted.operation_mode.currentText())

    assert restarted.profile_name.findText("Test Kunstleder") >= 0
    assert profile.speed_mm_min == 2400
    assert profile.power_percent == 22
    assert profile.passes == 2


def test_pyside_auto_fit_default_margin_is_half_mm(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.work_width.setValue(80.0)
    window.work_height.setValue(80.0)
    window.original_imported_paths = [[(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]]

    window._apply_svg_placement()

    xs = [point[0] for polyline in window.imported_paths for point in polyline]
    assert window.svg_margin.value() == 0.5
    assert max(xs) - min(xs) == 79.0


def test_pyside_svg_fit_button_uses_current_margin_without_overwriting_user_value(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.work_width.setValue(80.0)
    window.work_height.setValue(80.0)
    window.original_imported_paths = [[(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]]
    window.svg_manual.setChecked(True)
    window.svg_manual_width.setValue(50.0)
    window.svg_margin.setValue(0.0)

    window._apply_svg_placement()
    assert "50.0 x 50.0 mm" in window.svg_size_label.text()

    window._fit_svg_to_material()

    xs = [point[0] for polyline in window.imported_paths for point in polyline]
    ys = [point[1] for polyline in window.imported_paths for point in polyline]
    assert window.svg_auto.isChecked()
    assert window.svg_margin.value() == 0.0
    assert max(xs) - min(xs) == 80.0
    assert max(ys) - min(ys) == 80.0
    assert "80.0 x 80.0 mm" in window.svg_size_label.text()


def test_pyside_auto_fit_preserves_existing_user_margin(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.work_width.setValue(80.0)
    window.work_height.setValue(80.0)
    window.svg_margin.setValue(5.0)
    window.original_imported_paths = [[(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]]

    window._apply_svg_placement()

    xs = [point[0] for polyline in window.imported_paths for point in polyline]
    assert window.svg_margin.value() == 5.0
    assert max(xs) - min(xs) == 70.0


def test_pyside_load_project_preserves_saved_margin(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])
    project_path = tmp_path / "saved-margin.laser.json"
    data = project_to_dict(
        80.0,
        80.0,
        MaterialProfile("Test", 50, 1000, 1),
        "",
        imported_paths=[[(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]],
        svg_placement={"mode": "Automatisch", "margin": 5.0},
    )
    save_project(str(project_path), data)
    monkeypatch.setattr(
        "PySide6.QtWidgets.QFileDialog.getOpenFileName",
        lambda *_args, **_kwargs: (str(project_path), ""),
    )
    window = LaserControlWindow()

    window._load_project()
    window._apply_svg_placement()

    xs = [point[0] for polyline in window.imported_paths for point in polyline]
    assert window.svg_margin.value() == 5.0
    assert max(xs) - min(xs) == 70.0


def test_pyside_manual_transform_drives_preview_and_gcode(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.original_imported_paths = [[(0.0, 0.0), (100.0, 0.0), (100.0, 50.0)]]
    window.svg_manual.setChecked(True)
    window.svg_manual_width.setValue(50.0)
    window.svg_offset_x.setValue(12.0)
    window.svg_offset_y.setValue(8.0)

    window._apply_svg_placement()

    assert window.artwork_transform is not None
    assert window.artwork_transform.x_mm == 12.0
    assert window.artwork_transform.y_mm == 8.0
    assert window.artwork_transform.current_width_mm == 50.0
    assert window.artwork_transform.current_height_mm == 25.0
    assert "G0 X12.00 Y8.00" in window.gcode_text.toPlainText()
    assert "G1 X62.00 Y33.00" in window.gcode_text.toPlainText()
    assert window.preview.preview_model.bounds is not None
    assert window.preview.preview_model.bounds.min_x == 12.0
    assert window.preview.preview_model.bounds.min_y == 8.0


def test_pyside_transformed_bounds_drive_preview_preflight_and_frame(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    window.original_imported_paths = [[(0.0, 0.0), (80.0, 0.0), (80.0, 60.0), (0.0, 60.0), (0.0, 0.0)]]
    window.artwork_transform = ArtworkTransform(250.0, 40.0, 1.0, 80.0, 60.0, 80.0, 60.0)
    window._commit_artwork_transform(window.artwork_transform)

    bounds = window.get_transformed_bounds()
    preflight = window.workflow.prepare_preflight(
        window._job_context(window.app_controller.controller, window.gcode_text.toPlainText())
    )
    frame_width, frame_height = window._frame_dimensions()

    assert (bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y) == (250.0, 40.0, 330.0, 100.0)
    assert window.preview.preview_model.bounds is not None
    assert window.preview.preview_model.bounds.min_x == bounds.min_x
    assert window.preview.preview_model.bounds.min_y == bounds.min_y
    assert preflight.context.source_x_mm == bounds.min_x
    assert preflight.context.source_y_mm == bounds.min_y
    assert frame_width == bounds.width_mm
    assert frame_height == bounds.height_mm
    assert "G0 X250.00 Y40.00" in window.gcode_text.toPlainText()


def test_pyside_frame_uses_right_side_artwork_bounds(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    window.original_imported_paths = [[(0.0, 0.0), (80.0, 0.0), (80.0, 60.0), (0.0, 60.0), (0.0, 0.0)]]
    window.artwork_transform = ArtworkTransform(250.0, 40.0, 1.0, 80.0, 60.0, 80.0, 60.0)
    window._commit_artwork_transform(window.artwork_transform)
    calls = []
    monkeypatch.setattr(window, "_run_worker", lambda action, allow_while_busy=False: action())
    monkeypatch.setattr(window.workflow, "run_machine_action", lambda _name, action, _success=None: action())
    monkeypatch.setattr(window.app_controller, "frame_job", lambda width, height, x=0.0, y=0.0: calls.append((width, height, x, y)))

    window._frame_job()

    assert calls == [(80.0, 60.0, 250.0, 40.0)]


def test_pyside_frame_bounds_include_scaled_artwork(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    window.original_imported_paths = [[(0.0, 0.0), (80.0, 0.0), (80.0, 60.0), (0.0, 60.0), (0.0, 0.0)]]
    window.artwork_transform = ArtworkTransform(100.0, 50.0, 0.5, 80.0, 60.0, 40.0, 30.0)
    window._commit_artwork_transform(window.artwork_transform)

    bounds = window.get_transformed_bounds()

    assert (bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y) == (100.0, 50.0, 140.0, 80.0)
    assert window._frame_dimensions() == (40.0, 30.0)


def test_pyside_frame_bounds_use_axis_aligned_rotation_bounds(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    window.original_imported_paths = [[(0.0, 0.0), (80.0, 0.0), (80.0, 60.0), (0.0, 60.0), (0.0, 0.0)]]
    window.artwork_transform = ArtworkTransform(100.0, 50.0, 1.0, 80.0, 60.0, 80.0, 60.0, rotation_deg=90.0)
    window._commit_artwork_transform(window.artwork_transform)

    bounds = window.get_transformed_bounds()

    assert round(bounds.width_mm, 6) == 60.0
    assert round(bounds.height_mm, 6) == 80.0
    assert window._frame_dimensions() == (bounds.width_mm, bounds.height_mm)


def test_pyside_preview_visibility_switches_only_affect_render_options(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.original_imported_paths = [[(0.0, 0.0), (10.0, 0.0)]]
    window._apply_svg_placement()
    before_paths = list(window.imported_paths)

    window.preview_options["artwork"].setChecked(False)
    window.preview_options["gcode"].setChecked(True)

    assert not window.preview.preview_model.options.show_artwork
    assert window.preview.preview_model.options.show_gcode_path
    assert window.imported_paths == before_paths


def test_pyside_import_summary_uses_transform_values(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    transform = ArtworkTransform(
        x_mm=12.0,
        y_mm=8.0,
        scale=0.5,
        original_width_mm=100.0,
        original_height_mm=50.0,
        current_width_mm=50.0,
        current_height_mm=25.0,
        autofit_applied=True,
    )
    window.artwork_transform = transform
    window.artwork_source = VectorArtworkSource(
        source_id="logo",
        file_path="logo.svg",
        file_name="logo.svg",
        source_type=ArtworkSourceType.VECTOR,
        width_mm=50.0,
        height_mm=25.0,
        bounding_box=(12.0, 8.0, 62.0, 33.0),
        transform=transform,
    )

    window._update_import_summary()

    text = window.import_summary_label.text()
    assert "logo.svg" in text
    assert "Vektor" in text
    assert "Original 100.0 x 50.0 mm" in text
    assert "Aktuell 50.0 x 25.0 mm" in text
    assert "X 12.0 Y 8.0" in text
    assert "AutoFit ja" in text
    assert "Arbeitsbereich OK" in text


def test_pyside_preview_head_position_uses_machine_state_position(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.app_controller.machine_state.x_mm = 9.0
    window.app_controller.machine_state.y_mm = 7.0
    window.app_controller.machine_state.position_source = "WPos"

    window._draw_preview()

    assert window.preview.preview_model.head_position is not None
    assert window.preview.preview_model.head_position.x_mm == 9.0
    assert window.preview.preview_model.head_position.y_mm == 7.0
    assert window.preview.preview_model.head_position.source == "WPos"


def test_pyside_preview_head_position_ignores_raw_mpos_for_workspace_marker(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.app_controller.machine_state.x_mm = 9.0
    window.app_controller.machine_state.y_mm = 7.0
    window.app_controller.machine_state.position_source = "MPos"

    window._draw_preview()

    assert window.preview.preview_model.head_position is None


def test_pyside_preview_head_position_accepts_calculated_wpos(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.app_controller.machine_state.x_mm = 2.0
    window.app_controller.machine_state.y_mm = 5.0
    window.app_controller.machine_state.position_source = "WPos (MPos-WCO)"

    window._draw_preview()

    assert window.preview.preview_model.head_position is not None
    assert window.preview.preview_model.head_position.source == "WPos (MPos-WCO)"


def test_pyside_prepared_job_segments_feed_preview_overlay(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.imported_paths = [[(0.0, 0.0), (10.0, 10.0)]]
    window._refresh_gcode()
    window.preview_options["gcode"].setChecked(True)
    window._draw_preview()

    assert window.preview.preview_model.options.show_gcode_path
    assert window.preview.preview_model.gcode_segments


def test_pyside_circle_material_auto_fit_uses_centered_diameter(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.work_width.setValue(100.0)
    window.work_height.setValue(80.0)
    window.material_shape.setCurrentText("Kreis")
    window.original_imported_paths = [[(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]]

    window._apply_svg_placement()

    xs = [point[0] for polyline in window.imported_paths for point in polyline]
    ys = [point[1] for polyline in window.imported_paths for point in polyline]
    assert min(xs) == 10.5
    assert max(xs) == 89.5
    assert min(ys) == 0.5
    assert max(ys) == 79.5
    assert "Kreis" in window.svg_size_label.text()
    assert window._material_shape_warnings()


def test_pyside_layer_panel_tracks_operation_mode(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    assert [layer.name for layer in window._current_layers()] == ["Gravur", "Schnitt", "Markierung", "Hilfsebene"]
    assert [layer.name for layer in window._current_layers() if layer.is_output_layer] == ["Gravur"]

    window.operation_mode.setCurrentText("cutten")

    assert [layer.name for layer in window._current_layers() if layer.is_output_layer] == ["Schnitt"]


def test_pyside_manual_material_values_update_active_layer_gcode_and_preflight(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.imported_paths = [[(0.0, 0.0), (10.0, 0.0)]]
    window.power_percent.setValue(25)
    window.speed_mm_min.setValue(2200)
    window.passes.setValue(2)
    window._refresh_gcode()

    active_layers = [layer for layer in window._current_layers() if layer.is_output_layer]
    assert active_layers[0].power_percent == 25
    assert active_layers[0].speed_mm_min == 2200
    assert active_layers[0].passes == 2
    assert "S250 F2200" in window.gcode_text.toPlainText()
    assert window.gcode_text.toPlainText().count("; pass 2") == 1

    preflight = window.workflow.prepare_preflight(
        window._job_context(window.app_controller.controller, window.gcode_text.toPlainText())
    )
    summary = "\n".join(preflight.summary_lines())
    assert "2200 mm/min, 25% Leistung, 2 Durchgaenge" in summary
    assert "Quelle: manuell" in summary
    assert "2200 mm/min, 25%, 2 Durchgaenge" in summary


def test_pyside_layer_table_values_override_material_profile_for_gcode(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.imported_paths = [[(0.0, 0.0), (10.0, 0.0)]]
    layers = window._current_layers()
    layers[0].power_percent = 30
    layers[0].speed_mm_min = 1800
    layers[0].passes = 3
    window.layer_panel.set_layers(layers)
    window._layer_changed()

    assert "S300 F1800" in window.gcode_text.toPlainText()
    assert window.gcode_text.toPlainText().count("; pass 3") == 1


def test_pyside_layer_panel_uses_workflow_friendly_headers(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    headers = [window.layer_panel.table.horizontalHeaderItem(index).text() for index in range(window.layer_panel.table.columnCount())]

    assert headers == [
        "Aktiv",
        "Sichtbar",
        "Name",
        "Modus",
        "Speed",
        "Power",
        "Passes",
    ]
    assert window.layer_panel.layer_detail_label.text()


def test_pyside_workflow_summary_updates_when_job_is_loaded(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.imported_paths = [[(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)]]
    window._refresh_gcode()
    window._draw_preview()
    window._update_assistant_panel()

    assert "Jobgroesse:" in window.project_summary.text()
    assert "Material:" in window.material_summary.text()
    assert "[x] Datei/Job" in window.workflow_status.text()
    assert "Arbeitsbereich:" in window.assistant_summary.toPlainText()


def test_pyside_imports_raster_as_blocked_preview_source(monkeypatch, tmp_path) -> None:
    image_module = pytest.importorskip("PIL.Image")
    image_path = tmp_path / "photo.png"
    image_module.new("RGB", (20, 10), color=(128, 128, 128)).save(image_path)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getOpenFileName", lambda *_args, **_kwargs: (str(image_path), ""))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window._import_svg()

    assert window.raster_sources
    # The raster does not take over a layer; it stays labelled in the size label instead.
    assert [layer.name for layer in window.layer_panel.layers()] == ["Gravur", "Schnitt", "Markierung", "Hilfsebene"]
    assert "Raster: photo.png" in window.svg_size_label.text()
    assert "Rastergravur-GCode" in window.gcode_text.toPlainText()
    assert "Rasterbild" in window.assistant_summary.toPlainText()


def test_pyside_autofits_large_raster_to_work_area(monkeypatch, tmp_path) -> None:
    image_module = pytest.importorskip("PIL.Image")
    image_path = tmp_path / "large.png"
    image_module.new("RGB", (2000, 1000), color=(128, 128, 128)).save(image_path, dpi=(96, 96))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getOpenFileName", lambda *_args, **_kwargs: (str(image_path), ""))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.work_width.setValue(300.0)
    window.work_height.setValue(200.0)
    window._import_svg()

    source = window.raster_sources[0]
    assert source.width_mm <= 300.0
    assert source.height_mm <= 200.0
    assert window.autofit_result is not None
    assert window.autofit_result.applied
    assert round(source.width_mm / source.height_mm, 2) == 2.0


def test_pyside_has_single_visible_machine_action_surface(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()

    assert "connect" in window.action_buttons
    assert "start_job" in window.action_buttons
    assert len(window.action_buttons["connect"]) == 1
    assert len(window.action_buttons["start_job"]) == 1
    assert set(window.machine_panel.action_buttons).issubset(set(window.action_buttons))


def test_pyside_job_page_exposes_auto_home_single_piece_option(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    preflight = window.workflow.prepare_preflight(
        window._job_context(window.app_controller.controller, window.gcode_text.toPlainText())
    )

    assert window.job_kind.currentText() == "Einzelstueck"
    assert window.auto_home_after_job.isChecked()
    assert "Auto-Home nach Abschluss: Ja" in "\n".join(preflight.summary_lines())


def test_pyside_machine_action_buttons_follow_machine_state(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.app_controller.machine_state.phase = MachinePhase.DISCONNECTED
    window._sync_machine_action_buttons()

    assert window.action_buttons["connect"][0].isEnabled()
    assert not window.action_buttons["start_job"][0].isEnabled()

    window.app_controller.machine_state.phase = MachinePhase.IDLE
    window._sync_machine_action_buttons()

    assert not window.action_buttons["connect"][0].isEnabled()
    assert not window.action_buttons["start_job"][0].isEnabled()

    window.imported_paths = [[(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)]]
    window._refresh_gcode()
    window._sync_machine_action_buttons()

    assert window.action_buttons["start_job"][0].isEnabled()


def test_pyside_status_panel_reflects_machine_state(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.app_controller.machine_state.phase = MachinePhase.ALARM
    window.app_controller.machine_state.message = "Alarm"
    window.status_panel.update_machine_state(window.app_controller.machine_state, "GRBL", "COM3", "Alarm")

    assert "Alarm" in window.status_panel.machine_state_label.text()
    assert "COM3" in window.status_panel.machine_state_label.text()


def test_pyside_status_panel_reflects_machine_position(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.app_controller.controller.state.connected = True
    window.app_controller.controller.state.status = "Run"
    window.app_controller.controller.state.x_mm = 12.345
    window.app_controller.controller.state.y_mm = 45.678
    window.app_controller.controller.state.z_mm = 0.2
    window.app_controller.controller.state.position_source = "MPos"
    window.app_controller.controller.state.feed_rate = 1200.0

    window._sync_connection_indicator()

    assert "MPos" in window.status_panel.position_label.text()
    assert "12.35" in window.status_panel.position_label.text()
    assert "45.68" in window.status_panel.position_label.text()
    assert "F 1200" in window.status_panel.position_label.text()


def test_pyside_progress_position_update_does_not_override_running_state(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.app_controller.machine_state.phase = MachinePhase.RUNNING
    window.app_controller.controller.state.connected = True
    window.app_controller.controller.state.status = "Idle"
    window.app_controller.controller.state.x_mm = 1.0
    window.app_controller.controller.state.y_mm = 2.0
    window.app_controller.controller.state.position_source = "MPos"

    window._set_progress("Job laeuft", 1, 10)

    assert window.app_controller.machine_state.phase == MachinePhase.RUNNING
    assert "1.00" in window.status_panel.position_label.text()


def test_pyside_position_indicator_updates_running_without_idle_gate(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.app_controller.machine_state.phase = MachinePhase.RUNNING
    window.app_controller.controller.state.connected = True
    window.app_controller.controller.state.status = "Run"
    window.app_controller.controller.state.x_mm = 9.87
    window.app_controller.controller.state.y_mm = 6.54
    window.app_controller.controller.state.z_mm = 0.1
    window.app_controller.controller.state.position_source = "WPos"

    window._sync_position_indicator()

    assert window.app_controller.machine_state.phase == MachinePhase.RUNNING
    assert "WPos" in window.status_panel.position_label.text()
    assert "9.87" in window.status_panel.position_label.text()
    assert "6.54" in window.status_panel.position_label.text()


def test_pyside_alignment_indicator_reflects_active_mode(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.app_controller.switch_controller("Simulator")
    window.app_controller.connect()
    window.app_controller.enable_alignment_mode()
    window._sync_connection_indicator()

    assert window.alignment_button.isChecked()
    assert "Ausrichtmodus aktiv" in window.alignment_status.text()
    assert "Laserpunkt aktiv" in window.alignment_status.text()

    window.app_controller.disable_alignment_mode("test")
    window._sync_connection_indicator()

    assert not window.alignment_button.isChecked()
    assert window.alignment_status.text() == "Ausrichtmodus aus"


def test_pyside_work_area_trace_indicator_reflects_active_mode(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.app_controller.switch_controller("Simulator")
    window.app_controller.connect()
    window.app_controller.machine_state.work_area_trace_active = True
    window.app_controller.controller.state.work_area_trace_active = True
    window._sync_work_area_trace_indicator()

    assert window.work_area_trace_button.isChecked()
    assert "Arbeitsflaechenmodus aktiv" in window.work_area_trace_status.text()
    assert "Laser aus" in window.work_area_trace_status.text()
    assert "aktuellen Segment" in window.work_area_trace_status.text()
    assert "Sicherheitsstopp" in window.work_area_trace_status.text()

    window.app_controller.machine_state.work_area_trace_active = False
    window.app_controller.controller.state.work_area_trace_active = False
    window._sync_work_area_trace_indicator()

    assert not window.work_area_trace_button.isChecked()
    assert window.work_area_trace_status.text() == "Arbeitsflaechenmodus aus"


def test_pyside_work_area_trace_status_is_in_dedicated_panel(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()

    assert window.workspace_scan_panel.trace_button is window.work_area_trace_button
    assert window.workspace_scan_panel.status_label is window.work_area_trace_status


def test_pyside_transform_controls_update_rotation_size_and_position(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.original_imported_paths = [[(0.0, 0.0), (20.0, 0.0), (20.0, 10.0)]]
    window.artwork_transform = ArtworkTransform(0.0, 0.0, 1.0, 20.0, 10.0, 20.0, 10.0)
    window._sync_transform_controls()

    window._rotate_artwork(90.0)
    window._center_artwork()

    assert window.artwork_transform is not None
    assert window.artwork_transform.rotation_deg == 90.0
    assert round(window.artwork_transform.current_width_mm, 6) == 10.0
    assert round(window.artwork_transform.current_height_mm, 6) == 20.0
    assert round(window.artwork_transform.x_mm, 6) == (window.work_width.value() - 10.0) / 2.0
    assert round(window.artwork_transform.y_mm, 6) == (window.work_height.value() - 20.0) / 2.0
    assert window.artwork_rotation.value() == 90.0


def test_pyside_preview_selects_and_drags_artwork(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    window.resize(1400, 900)
    window.show()
    window.original_imported_paths = [[(0.0, 0.0), (20.0, 0.0), (20.0, 10.0), (0.0, 10.0), (0.0, 0.0)]]
    window.artwork_transform = ArtworkTransform(10.0, 10.0, 1.0, 20.0, 10.0, 20.0, 10.0)
    window._commit_artwork_transform(window.artwork_transform)
    app.processEvents()
    mapper = window.preview._coordinate_mapper()
    press_x, press_y = mapper.to_screen(15.0, 15.0)
    target_x, target_y = mapper.to_screen(55.0, 45.0)

    QTest.mousePress(window.preview, Qt.MouseButton.LeftButton, pos=QPoint(round(press_x), round(press_y)))
    QTest.mouseMove(window.preview, QPoint(round(target_x), round(target_y)))
    QTest.mouseRelease(window.preview, Qt.MouseButton.LeftButton, pos=QPoint(round(target_x), round(target_y)))
    app.processEvents()

    assert window.preview.artwork_selected
    assert window.artwork_transform is not None
    assert window.artwork_transform.x_mm == pytest.approx(50.0, abs=1.0)
    assert window.artwork_transform.y_mm == pytest.approx(40.0, abs=1.0)
    assert window.svg_offset_x.value() == window.artwork_transform.x_mm
    assert "Motiv ausgewaehlt" in window.preview_position_label.text()
    window.close()


@pytest.mark.parametrize(
    ("key", "modifier", "expected_x", "expected_y"),
    [
        (Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier, 11.0, 10.0),
        (Qt.Key.Key_Up, Qt.KeyboardModifier.ShiftModifier, 10.0, 20.0),
        (Qt.Key.Key_Left, Qt.KeyboardModifier.ControlModifier, 9.9, 10.0),
    ],
)
def test_pyside_preview_arrow_nudging(
    monkeypatch,
    tmp_path,
    key,
    modifier,
    expected_x,
    expected_y,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    window.show()
    window.original_imported_paths = [[(0.0, 0.0), (20.0, 0.0), (20.0, 10.0), (0.0, 10.0), (0.0, 0.0)]]
    window.artwork_transform = ArtworkTransform(10.0, 10.0, 1.0, 20.0, 10.0, 20.0, 10.0)
    window._commit_artwork_transform(window.artwork_transform)
    window.preview._set_artwork_selected(True)
    window.preview.setFocus()

    QTest.keyClick(window.preview, key, modifier)
    app.processEvents()

    assert window.artwork_transform is not None
    assert round(window.artwork_transform.x_mm, 1) == expected_x
    assert round(window.artwork_transform.y_mm, 1) == expected_y
    window.close()


def test_pyside_preview_drag_outside_workspace_updates_preflight_bounds(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    window.original_imported_paths = [[(0.0, 0.0), (20.0, 0.0), (20.0, 10.0), (0.0, 10.0), (0.0, 0.0)]]
    window.artwork_transform = ArtworkTransform(0.0, 0.0, 1.0, 20.0, 10.0, 20.0, 10.0)
    window._commit_artwork_transform(window.artwork_transform)

    window._move_artwork_from_preview(-5.0, 15.0)
    context = window._job_context(window.app_controller.controller, window.gcode_text.toPlainText())
    preflight = window.workflow.prepare_preflight(context)

    assert window.artwork_transform is not None
    assert window.artwork_transform.x_mm == -5.0
    assert context.source_bounds_ok is False
    assert any("ausserhalb" in blocker for blocker in preflight.blockers)
    assert "X-5.00" in window.gcode_text.toPlainText()


def test_pyside_fill_layer_updates_toolpath_preview_and_gcode(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.original_imported_paths = [[(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0)]]
    window.artwork_transform = ArtworkTransform(0.0, 0.0, 1.0, 10.0, 5.0, 10.0, 5.0)
    window._commit_artwork_transform(window.artwork_transform)
    mode = window.layer_panel.table.cellWidget(0, 3)
    mode.setCurrentIndex(mode.findData(LayerMode.FILL.value))
    window.layer_panel.table.setCurrentCell(0, 2)
    spacing = window.layer_panel.fill_spacing
    spacing.setCurrentIndex(spacing.findData(0.20))
    window._layer_changed()

    model = window._build_preview_model()

    assert window.fill_toolpaths
    assert window.fill_toolpaths[0].line_count == 25
    assert {path.path_type for path in model.render_layers[0].paths} == {"fill", "overscan"}
    assert "; fill spacing 0.20 mm" in window.gcode_text.toPlainText()
    assert "; overscan Automatisch" in window.gcode_text.toPlainText()


def test_pyside_layer_exposes_automatic_and_manual_overscan(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.original_imported_paths = [[(20.0, 0.0), (30.0, 0.0), (30.0, 2.0), (20.0, 2.0), (20.0, 0.0)]]
    window.artwork_transform = ArtworkTransform(0.0, 0.0, 1.0, 30.0, 2.0, 30.0, 2.0)
    window._commit_artwork_transform(window.artwork_transform)
    mode = window.layer_panel.table.cellWidget(0, 3)
    mode.setCurrentIndex(mode.findData(LayerMode.FILL.value))
    window.layer_panel.table.setCurrentCell(0, 2)

    assert window.layer_panel.overscan_enabled.isEnabled()
    assert window.layer_panel.overscan_enabled.isChecked()
    assert window.preview_options["overscan"].isChecked()

    manual_index = window.layer_panel.overscan_mode.findData("Manuell")
    window.layer_panel.overscan_mode.setCurrentIndex(manual_index)
    window.layer_panel.overscan_value.setValue(3.5)
    window._layer_changed()

    assert window.fill_toolpaths[0].overscan_mm == 3.5
    assert "; overscan Manuell 3.50 mm" in window.gcode_text.toPlainText()


def test_pyside_fill_controls_are_disabled_for_raster_source(monkeypatch, tmp_path) -> None:
    image_module = pytest.importorskip("PIL.Image")
    image_path = tmp_path / "photo.png"
    image_module.new("RGB", (20, 10), color=(128, 128, 128)).save(image_path)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getOpenFileName", lambda *_args, **_kwargs: (str(image_path), ""))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window._import_svg()

    mode = window.layer_panel.table.cellWidget(0, 3)
    assert mode is not None
    assert not mode.isEnabled()
    assert not window.layer_panel.fill_spacing.isEnabled()
    assert "Vektor" in window.layer_panel.fill_info.text()


def test_preflight_dialog_start_button_uses_can_start_without_frame_requirement(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    window.connection_mode.setCurrentText("Simulator")
    window.app_controller.switch_controller("Simulator")
    window.imported_paths = [[(0.0, 0.0), (10.0, 0.0)]]
    window._refresh_gcode()

    preflight = window.workflow.prepare_preflight(
        window._job_context(window.app_controller.controller, window.gcode_text.toPlainText())
    )
    dialog = PreflightDialog(preflight, window)

    assert preflight.can_start
    assert dialog.start_button.isEnabled()
    assert "Frame-Test verlangt (nein - nur Empfehlung)" in dialog.summary.toPlainText()
    assert "Startbutton aktiviert" in dialog.summary.toPlainText()


def test_preflight_dialog_rechecks_unhomed_confirmation(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    window.connection_mode.setCurrentText("GRBL ueber USB")
    window.serial_port.addItem("COM1")
    window.serial_port.setCurrentText("COM1")
    window.machine_profile = replace(window.machine_profile, homing_required=False)
    window.app_controller.set_machine_profile(window.machine_profile)
    window.app_controller.controller.state.connected = True
    window.app_controller.controller.state.homed = False
    window.app_controller.machine_state.transition(MachinePhase.IDLE, "Bereit")
    window.imported_paths = [[(0.0, 0.0), (10.0, 0.0)]]
    window._refresh_gcode()

    preflight = window.workflow.prepare_preflight(
        window._job_context(window.app_controller.controller, window.gcode_text.toPlainText())
    )
    dialog = PreflightDialog(preflight, window)

    assert preflight.can_start
    assert dialog.unhomed_confirmation is not None
    assert not dialog.start_button.isEnabled()
    assert "Referenzfahrt" in dialog.start_hint.text()
    assert "Referenzfahrt" in dialog.start_button.toolTip()
    dialog.unhomed_confirmation.setChecked(True)
    assert dialog.start_button.isEnabled()


def test_preflight_dialog_enables_hardware_start_when_all_conditions_are_met(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    window.connection_mode.setCurrentText("GRBL ueber USB")
    window.serial_port.addItem("COM1")
    window.serial_port.setCurrentText("COM1")
    window.app_controller.set_machine_profile(window.machine_profile)
    window.app_controller.controller.state.connected = True
    window.app_controller.controller.state.homed = True
    window.app_controller.controller.state.status = "Idle"
    window.app_controller.machine_state.transition(MachinePhase.IDLE, "Bereit")
    window.imported_paths = [[(0.0, 0.0), (10.0, 0.0)]]
    window._refresh_gcode()

    preflight = window.workflow.prepare_preflight(
        window._job_context(window.app_controller.controller, window.gcode_text.toPlainText())
    )
    dialog = PreflightDialog(preflight, window)
    diagnostics = dialog.summary.toPlainText()

    assert preflight.can_start
    assert dialog.unhomed_confirmation is None
    assert dialog.start_button.isEnabled()
    assert "Start ist freigegeben" in dialog.start_hint.text()
    assert "[OK] Maschine verbunden" in diagnostics
    assert "[OK] Homing OK" in diagnostics
    assert "[OK] Startbutton aktiviert" in diagnostics


def test_pyside_svg_analysis_is_shown_after_vector_import(monkeypatch, tmp_path) -> None:
    svg = tmp_path / "complex.svg"
    points = " ".join(f"{index * 0.01},0" for index in range(260))
    svg.write_text(
        f'<svg width="10mm" height="5mm" viewBox="0 0 10 5"><polyline points="{points}"/></svg>',
        encoding="utf-8",
    )
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getOpenFileName", lambda *_args, **_kwargs: (str(svg), ""))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window._import_svg()

    assert window.svg_analysis is not None
    assert "Segmente" in window.svg_analysis_label.text()
    assert "SVG" in window.import_summary_label.text()


def test_pyside_laser_intelligence_is_shown_in_sidebar_and_preflight(monkeypatch, tmp_path) -> None:
    svg = tmp_path / "logo.svg"
    svg.write_text(
        '<svg width="12mm" height="6mm" viewBox="0 0 12 6">'
        '<polyline points="0,0 12,0 12,6 0,6 0,0"/>'
        '<polyline points="2,2 10,2 10,4 2,4 2,2"/>'
        '</svg>',
        encoding="utf-8",
    )
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getOpenFileName", lambda *_args, **_kwargs: (str(svg), ""))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window._import_svg()

    warnings = window._svg_preflight_warnings()

    assert window.laser_intelligence_result is not None
    assert "Laser Intelligence" in window.laser_intelligence_label.text()
    assert "Falcon 10W" in window.laser_intelligence_label.text()
    assert any("Laser Intelligence" in warning for warning in warnings)


def test_pyside_preflight_shows_falcon_material_recommendation(monkeypatch, tmp_path) -> None:
    svg = tmp_path / "logo.svg"
    svg.write_text(
        '<svg width="12mm" height="6mm" viewBox="0 0 12 6">'
        '<polyline points="0,0 12,0 12,6 0,6 0,0"/>'
        '</svg>',
        encoding="utf-8",
    )
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getOpenFileName", lambda *_args, **_kwargs: (str(svg), ""))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.profile_name.addItem("Kunstleder")
    window.profile_name.setCurrentText("Kunstleder")
    window.power_percent.setValue(18)
    window.speed_mm_min.setValue(2500)
    window.passes.setValue(1)
    window._import_svg()

    warnings = window._svg_preflight_warnings()

    assert any("Materialempfehlung Falcon 10W" in warning for warning in warnings)
    assert any("Kunstleder" in warning for warning in warnings)


def test_pyside_svg_optimization_feeds_preview_and_gcode(monkeypatch, tmp_path) -> None:
    svg = tmp_path / "line.svg"
    svg.write_text(
        '<svg width="10mm" height="5mm" viewBox="0 0 10 5">'
        '<polyline points="0,2 1,2.01 2,2 3,2 4,2"/>'
        '</svg>',
        encoding="utf-8",
    )
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getOpenFileName", lambda *_args, **_kwargs: (str(svg), ""))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window._import_svg()
    original_lines = window.gcode_text.toPlainText().splitlines()
    window.svg_simplify_enabled.setChecked(True)
    window.svg_tolerance.setCurrentIndex(window.svg_tolerance.findData(0.02))
    optimized_lines = window.gcode_text.toPlainText().splitlines()
    model = window._build_preview_model()

    assert window.svg_optimization_result is not None
    assert window.svg_optimization_result.reduced_segments > 0
    assert len(optimized_lines) < len(original_lines)
    assert model.bounds is not None
    assert len(model.render_layers[0].paths[0].points) < len(window.original_imported_paths[0])


def test_pyside_work_area_trace_uses_same_workspace_values_as_preview(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    window.work_width.setValue(110.0)
    window.work_height.setValue(110.0)
    window._draw_preview()

    assert window.preview.preview_model.work_width_mm == 110.0
    assert window.preview.preview_model.work_height_mm == 110.0
    assert window.app_controller.current_workspace_width == 110.0
    assert window.app_controller.current_workspace_height == 110.0


def test_pyside_machine_profile_selection_updates_active_profile(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    profile_path = tmp_path / "machine_profiles.json"
    monkeypatch.setenv("LASER_CONTROL_MACHINE_PROFILES", str(profile_path))
    repository = MachineProfileRepository(profile_path)
    repository.upsert_profile(
        MachineProfile(
            profile_id="small-test",
            name="Small Test",
            machine_name="Small GRBL",
            work_area_width=123.0,
            work_area_height=45.0,
            default_port="COM7",
            baudrate=57600,
            homing_required=False,
        )
    )
    app = QApplication.instance() or QApplication([])

    window = LaserControlWindow()
    index = window.machine_panel.profile_select.findData("small-test")
    window.machine_panel.profile_select.setCurrentIndex(index)

    assert window.machine_profile.profile_id == "small-test"
    assert window.work_width.value() == 123.0
    assert window.work_height.value() == 45.0
    assert window.app_controller.machine_profile.baudrate == 57600


def test_pyside_machine_profile_editor_updates_active_profile(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    profile_path = tmp_path / "machine_profiles.json"
    monkeypatch.setenv("LASER_CONTROL_MACHINE_PROFILES", str(profile_path))
    app = QApplication.instance() or QApplication([])

    class FakeProfileDialog:
        is_new_profile = True

        def __init__(self, *_args) -> None:
            self.saved_profile = MachineProfile(
                profile_id="editor-test",
                name="Editor Test",
                machine_name="Editor GRBL",
                work_area_width=222.0,
                work_area_height=111.0,
                default_port="COM8",
                baudrate=57600,
                homing_required=True,
                max_speed=8000,
                max_power=90,
            )

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr("laser_control.window_machine.MachineProfileDialog", FakeProfileDialog)
    window = LaserControlWindow()

    window._edit_machine_profiles()

    loaded = MachineProfileRepository(profile_path)
    assert loaded.active_profile().profile_id == "editor-test"
    assert window.machine_panel.profile_select.findData("editor-test") >= 0
    assert window.work_width.value() == 222.0
    assert window.work_height.value() == 111.0
    assert window.app_controller.machine_profile.baudrate == 57600


def test_pyside_blocks_profile_switch_while_connected(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    profile_path = tmp_path / "machine_profiles.json"
    monkeypatch.setenv("LASER_CONTROL_MACHINE_PROFILES", str(profile_path))
    repository = MachineProfileRepository(profile_path)
    repository.upsert_profile(MachineProfile(profile_id="blocked-test", name="Blocked Test", machine_name="Blocked GRBL"))
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.warning", lambda *_args, **_kwargs: None)
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    window.app_controller.machine_state.transition(MachinePhase.IDLE, "Bereit")
    window.app_controller.controller.state.connected = True

    index = window.machine_panel.profile_select.findData("blocked-test")
    window.machine_panel.profile_select.setCurrentIndex(index)

    assert window.machine_profile.profile_id != "blocked-test"
    assert window.machine_profile_repository.active_profile_id() != "blocked-test"


def test_pyside_logs_blocked_profile_change(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(tmp_path / "materials.json"))
    profile_path = tmp_path / "machine_profiles.json"
    monkeypatch.setenv("LASER_CONTROL_MACHINE_PROFILES", str(profile_path))
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.warning", lambda *_args, **_kwargs: None)
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    window.app_controller.machine_state.transition(MachinePhase.IDLE, "Bereit")
    window.app_controller.controller.state.connected = True

    window._block_machine_profile_change("__profile_editor__", window.app_controller.machine_state.phase.value)

    assert any("profilwechsel" in entry.action.lower() for entry in window.machine_action_log.entries)


def test_machine_profile_dialog_creates_profile_with_conservative_defaults(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    dialog = MachineProfileDialog([], "missing")

    dialog._create_new_profile()
    dialog.profile_name.setText("Dialog Test")
    dialog.machine_name.setText("Dialog GRBL")
    dialog.work_area_width.setValue(300.0)
    dialog.work_area_height.setValue(200.0)
    dialog.baudrate.setValue(115200)
    dialog._save_profile()

    assert dialog.saved_profile is not None
    assert dialog.saved_profile.profile_id == "dialog-test"
    assert dialog.saved_profile.homing_required is True
    assert dialog.saved_profile.work_area_width == 300.0


def test_pyside_pause_and_stop_enable_when_worker_switches_to_running() -> None:
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    window.app_controller.switch_controller("Simulator")
    window.app_controller.connect()
    window._sync_connection_indicator()
    assert not window.action_buttons["pause"][0].isEnabled()
    assert not window.action_buttons["stop"][0].isEnabled()

    # A worker thread streams a job: it changes the machine state without finishing yet.
    window.app_controller.machine_state.transition(MachinePhase.RUNNING, "Job gestartet")
    window._sync_position_indicator()  # what the 250 ms machine-state timer runs

    assert window.action_buttons["pause"][0].isEnabled()
    assert window.action_buttons["stop"][0].isEnabled()
    assert not window.action_buttons["start_job"][0].isEnabled()
    window.close()


def test_pyside_load_project_keeps_first_item_when_other_item_was_selected(monkeypatch, tmp_path) -> None:
    svg = tmp_path / "logo.svg"
    svg.write_text(
        '<svg width="10mm" height="10mm" viewBox="0 0 10 10"><polyline points="0,0 10,0 10,10 0,10 0,0"/></svg>',
        encoding="utf-8",
    )
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getOpenFileName", lambda *_args, **_kwargs: (str(svg), ""))
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    window._import_svg()
    window._import_svg()
    first, second = window.laser_project.items
    window._select_artwork_item(second.item_id)
    window.svg_offset_x.setValue(first.transform.x_mm + 123.0)  # move only the selected item
    window.svg_offset_y.setValue(first.transform.y_mm + 45.0)
    saved = {item.item_id: (item.transform.x_mm, item.transform.y_mm) for item in window.laser_project.items}
    assert saved[first.item_id] != saved[second.item_id]
    project_path = tmp_path / "two-items.laser.json"
    window.current_project_path = str(project_path)
    window._save_project()
    window.close()

    monkeypatch.setattr(
        "PySide6.QtWidgets.QFileDialog.getOpenFileName",
        lambda *_args, **_kwargs: (str(project_path), ""),
    )
    loaded = LaserControlWindow()
    loaded._load_project()

    restored = {item.item_id: (item.transform.x_mm, item.transform.y_mm) for item in loaded.laser_project.items}
    assert restored == saved
    selected = loaded._selected_artwork_item()
    assert loaded.svg_offset_x.value() == pytest.approx(selected.transform.x_mm)
    loaded.close()


def test_pyside_preflight_blocks_active_item_whose_source_is_missing(monkeypatch, tmp_path) -> None:
    logo = tmp_path / "logo.svg"
    badge = tmp_path / "badge.svg"
    for svg in (logo, badge):
        svg.write_text(
            '<svg width="10mm" height="10mm" viewBox="0 0 10 10"><polyline points="0,0 10,0 10,10 0,10 0,0"/></svg>',
            encoding="utf-8",
        )
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    for svg in (logo, badge):
        monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getOpenFileName", lambda *_a, _p=svg, **_k: (str(_p), ""))
        window._import_svg()
    project_path = tmp_path / "two-sources.laser.json"
    window.current_project_path = str(project_path)
    window._save_project()
    window.close()
    badge.unlink()  # source file moved/deleted after saving

    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getOpenFileName", lambda *_a, **_k: (str(project_path), ""))
    loaded = LaserControlWindow()
    loaded._load_project()
    loaded._refresh_gcode()
    preflight = loaded.workflow.prepare_preflight(
        loaded._job_context(loaded.app_controller.controller, loaded.gcode_text.toPlainText())
    )

    assert not preflight.can_start
    assert any("Motivquelle nicht geladen" in blocker and "badge.svg" in blocker for blocker in preflight.blockers)
    loaded.close()


def test_pyside_vector_transform_matches_geometry_not_svg_document(monkeypatch, tmp_path) -> None:
    svg = tmp_path / "padded.svg"
    # 100 x 100 mm document containing only a 10 x 10 mm square in its centre.
    svg.write_text(
        '<svg width="100mm" height="100mm" viewBox="0 0 100 100"><polyline points="45,45 55,45 55,55 45,55 45,45"/></svg>',
        encoding="utf-8",
    )
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getOpenFileName", lambda *_a, **_k: (str(svg), ""))
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    window._import_svg()

    def toolpath_width() -> float:
        xs = [point[0] for path in window._active_vector_items()[0][2] for point in path]
        return max(xs) - min(xs)

    transform = window.laser_project.items[0].transform
    assert transform.current_width_mm == pytest.approx(toolpath_width())
    assert transform.current_width_mm == pytest.approx(10.0)
    window.close()


def test_pyside_deactivated_selected_raster_does_not_block_vector_job(monkeypatch, tmp_path) -> None:
    from PIL import Image

    svg = tmp_path / "logo.svg"
    svg.write_text(
        '<svg width="10mm" height="10mm" viewBox="0 0 10 10"><polyline points="0,0 10,0 10,10 0,10 0,0"/></svg>',
        encoding="utf-8",
    )
    png = tmp_path / "photo.png"
    Image.new("L", (20, 20), 128).save(png, dpi=(254, 254))
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    for path in (svg, png):
        monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getOpenFileName", lambda *_a, _p=path, **_k: (str(_p), ""))
        window._import_svg()
    raster_item = window.laser_project.items[1]
    assert raster_item.is_raster and window.selected_artwork_item_id == raster_item.item_id
    def raster_available() -> bool:
        return window._job_context(window.app_controller.controller, "G0 X0 Y0").raster_gcode_available

    assert not raster_available()

    raster_item.active = False  # user unticks the raster in the object list; it stays selected

    assert raster_available()
    window.close()


def test_pyside_generated_test_matrix_can_be_framed_and_started() -> None:
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    window.app_controller.switch_controller("Simulator")
    window.app_controller.connect()
    window.app_controller.home()

    window._generate_test_matrix()

    for action_id in ("frame", "dry_run", "start_job"):
        assert window.action_buttons[action_id][0].isEnabled(), action_id

    # Regenerating G-code from the (empty) artwork replaces the matrix and gates the job again.
    window._refresh_gcode()
    window._sync_machine_action_buttons()
    assert not window.action_buttons["start_job"][0].isEnabled()
    window.close()


def test_pyside_test_matrix_frames_its_own_gcode_not_imported_artwork(monkeypatch, tmp_path) -> None:
    svg = tmp_path / "logo.svg"
    svg.write_text(
        '<svg width="10mm" height="10mm" viewBox="0 0 10 10"><polyline points="0,0 10,0 10,10 0,10 0,0"/></svg>',
        encoding="utf-8",
    )
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getOpenFileName", lambda *_a, **_k: (str(svg), ""))
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    window._import_svg()
    window.svg_offset_x.setValue(250.0)
    window.svg_offset_y.setValue(250.0)
    artwork_bounds = window.get_transformed_bounds()
    assert artwork_bounds.min_x == pytest.approx(250.0)

    window._generate_test_matrix()

    frame = window.get_transformed_bounds()
    gcode_bounds = window._gcode_bounds()
    assert gcode_bounds is not None
    assert (frame.min_x, frame.min_y, frame.max_x, frame.max_y) == (
        gcode_bounds.min_x, gcode_bounds.min_y, gcode_bounds.max_x, gcode_bounds.max_y,
    )
    assert frame.max_x < 250.0
    context = window._job_context(window.app_controller.controller, window.gcode_text.toPlainText())
    assert context.source_type == "generated" and context.active_artwork_count is None
    window.close()


def test_pyside_profile_default_port_matches_decorated_port_labels(monkeypatch) -> None:
    from laser_control.machine_profiles import DEFAULT_MACHINE_PROFILE

    monkeypatch.setattr(
        "laser_control.window_machine.list_serial_ports",
        lambda: ["COM3 - Bluetooth", "COM9 - USB Serial Device"],
    )
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    window.machine_profile = replace(DEFAULT_MACHINE_PROFILE, default_port="COM9")

    window._refresh_ports()

    assert window.serial_port.currentText() == "COM9 - USB Serial Device"
    window.serial_port.setCurrentIndex(0)
    window._apply_machine_profile(replace(DEFAULT_MACHINE_PROFILE, default_port="com9"))
    assert window.serial_port.currentText() == "COM9 - USB Serial Device"
    window.close()
