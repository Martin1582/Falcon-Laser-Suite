"""UI-Tests fuer "Motiv entfernen" und "Neues Projekt" im Hauptfenster."""

from dataclasses import fields

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from laser_control.machine_state import MachinePhase
from laser_control.pyside_app import LaserControlWindow
from laser_control.window_project_lifecycle import LOCKED_REASON, NO_SELECTION_REASON

SQUARE_SVG = '<svg width="10mm" height="10mm" viewBox="0 0 10 10"><polyline points="0,0 10,0 10,10 0,10 0,0"/></svg>'


@pytest.fixture
def window():
    QApplication.instance() or QApplication([])
    created = LaserControlWindow()
    # Checkable sidebar sections disable their children while collapsed; open "Projekt" like a user.
    created.sidebar_sections["Projekt"].setChecked(True)
    yield created
    created.close()


def _svg(tmp_path, name: str):
    path = tmp_path / name
    path.write_text(SQUARE_SVG, encoding="utf-8")
    return path


def _png(tmp_path, name: str = "photo.png"):
    from PIL import Image

    path = tmp_path / name
    Image.new("L", (20, 20), 128).save(path, dpi=(254, 254))
    return path


def _import(window, monkeypatch, path) -> None:
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getOpenFileName", lambda *_a, _p=path, **_k: (str(_p), ""))
    window._import_svg()


def _answer(monkeypatch, name: str, answer: bool) -> list:
    """Ersetzt confirm_* im Fenster-Mixin und zeichnet die Aufrufargumente auf."""
    calls: list = []

    def fake(_parent, *args):
        calls.append(args)
        return answer

    monkeypatch.setattr(f"laser_control.window_project_lifecycle.{name}", fake)
    return calls


def _forbid(monkeypatch, name: str) -> None:
    def fail(*_args):
        pytest.fail(f"{name} darf nicht aufgerufen werden")

    monkeypatch.setattr(f"laser_control.window_project_lifecycle.{name}", fail)


def _connect_and_home(window) -> None:
    window.app_controller.switch_controller("Simulator")
    window.app_controller.connect()
    window.app_controller.home()


def _preflight_blockers(window) -> list[str]:
    context = window._job_context(window.app_controller.controller, window.gcode_text.toPlainText())
    return window.workflow.prepare_preflight(context).blockers


def _layer_flags(window) -> dict[str, bool]:
    return {layer.name: layer.enabled for layer in window.layer_panel.layers()}


def _all_cache_keys(window) -> set:
    caches = window.project_workspace.caches
    return {key for f in fields(caches) for key in getattr(caches, f.name)}


def test_remove_button_follows_selection(window, monkeypatch, tmp_path) -> None:
    button = window.project_edit_actions.remove_artwork_button
    assert not button.isEnabled()
    assert button.toolTip() == NO_SELECTION_REASON

    _import(window, monkeypatch, _svg(tmp_path, "logo.svg"))
    assert button.isEnabled()

    _answer(monkeypatch, "confirm_remove_artwork", True)
    window._remove_selected_artwork()
    assert not button.isEnabled()
    assert button.toolTip() == NO_SELECTION_REASON


def test_remove_selected_item_selects_next_and_updates_outputs(window, monkeypatch, tmp_path) -> None:
    for name in ("a.svg", "b.svg", "c.svg"):
        _import(window, monkeypatch, _svg(tmp_path, name))
    first, middle, last = window.laser_project.items
    window._select_artwork_item(middle.item_id)
    window.svg_offset_x.setValue(250.0)  # middle item far right: it defines the job bounds
    assert window.get_transformed_bounds().max_x > 250.0
    calls = _answer(monkeypatch, "confirm_remove_artwork", True)

    window._remove_selected_artwork()

    assert calls == [(middle.name, False)]
    assert [item.item_id for item in window.laser_project.items] == [first.item_id, last.item_id]
    assert window.object_table.rowCount() == 2
    assert window.selected_artwork_item_id == last.item_id
    assert window.svg_offset_x.value() == pytest.approx(last.transform.x_mm)
    assert window.get_transformed_bounds().max_x == pytest.approx(
        max(first.transform.bounds.max_x, last.transform.bounds.max_x)
    )
    assert middle.item_id not in _all_cache_keys(window)
    assert window.object_table.selectionModel().selectedRows()[0].row() == 1


def test_remove_last_item_restores_empty_state(window, monkeypatch, tmp_path) -> None:
    _connect_and_home(window)
    starter_gcode = window.gcode_text.toPlainText()
    _import(window, monkeypatch, _svg(tmp_path, "logo.svg"))
    window._sync_machine_action_buttons()
    assert window.action_buttons["start_job"][0].isEnabled()
    _answer(monkeypatch, "confirm_remove_artwork", True)

    window._remove_selected_artwork()

    assert not window.project_empty_state.isHidden()
    assert window.artwork_source is None and window.artwork_transform is None
    assert window.imported_file is None
    assert window.import_summary_label.text() == "Import: keine Datei geladen"
    for action_id in ("frame", "dry_run", "start_job"):
        assert not window.action_buttons[action_id][0].isEnabled(), action_id
    assert window.gcode_text.toPlainText() == starter_gcode
    assert not window._has_loaded_motif()
    assert window.object_table.selectionModel().selectedRows() == []
    assert window.svg_size_label.text() == "Motiv: keine Datei"
    assert window.preview_position_label.text() == "Motivposition: --"


def test_remove_declined_keeps_project(window, monkeypatch, tmp_path) -> None:
    for name in ("a.svg", "b.svg"):
        _import(window, monkeypatch, _svg(tmp_path, name))
    items_before = list(window.laser_project.items)
    selected_before = window.selected_artwork_item_id
    gcode_before = window.gcode_text.toPlainText()
    calls = _answer(monkeypatch, "confirm_remove_artwork", False)

    window._remove_selected_artwork()

    assert len(calls) == 1
    assert window.laser_project.items == items_before
    assert window.selected_artwork_item_id == selected_before
    assert window.gcode_text.toPlainText() == gcode_before


def test_delete_key_in_object_table_removes_selected_item(window, monkeypatch, tmp_path) -> None:
    _import(window, monkeypatch, _svg(tmp_path, "logo.svg"))
    calls = _answer(monkeypatch, "confirm_remove_artwork", True)
    window.show()
    window.object_table.setFocus()
    QApplication.processEvents()

    QTest.keyClick(window.object_table, Qt.Key.Key_Delete)
    QApplication.processEvents()

    assert len(calls) == 1
    assert window.laser_project.items == []


def test_remove_missing_source_item_clears_preflight_blocker(monkeypatch, tmp_path) -> None:
    QApplication.instance() or QApplication([])
    logo, badge = _svg(tmp_path, "logo.svg"), _svg(tmp_path, "badge.svg")
    source_window = LaserControlWindow()
    for svg in (logo, badge):
        _import(source_window, monkeypatch, svg)
    project_path = tmp_path / "two-sources.laser.json"
    source_window.current_project_path = str(project_path)
    source_window._save_project()
    source_window.close()
    badge.unlink()  # source file moved/deleted after saving

    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getOpenFileName", lambda *_a, **_k: (str(project_path), ""))
    loaded = LaserControlWindow()
    loaded._load_project()
    badge_item = next(item for item in loaded.laser_project.items if item.name == "badge.svg")
    loaded._select_artwork_item(badge_item.item_id)
    loaded._refresh_gcode()
    assert any("Motivquelle nicht geladen" in blocker for blocker in _preflight_blockers(loaded))
    _answer(monkeypatch, "confirm_remove_artwork", True)

    loaded._remove_selected_artwork()

    assert [item.name for item in loaded.laser_project.items] == ["logo.svg"]
    assert not any("Motivquelle nicht geladen" in blocker for blocker in _preflight_blockers(loaded))
    loaded.close()


def test_remove_active_raster_unblocks_vector_job(window, monkeypatch, tmp_path) -> None:
    for path in (_svg(tmp_path, "logo.svg"), _png(tmp_path)):
        _import(window, monkeypatch, path)
    assert window.laser_project.items[1].is_raster
    assert not any(layer.name.startswith("Raster:") for layer in window.layer_panel.layers())
    assert any("Aktives Rastermotiv" in blocker for blocker in _preflight_blockers(window))
    _answer(monkeypatch, "confirm_remove_artwork", True)

    window._remove_selected_artwork()

    context = window._job_context(window.app_controller.controller, "G0 X0 Y0")
    assert context.raster_gcode_available
    assert window.selected_artwork_item_id == window.laser_project.items[0].item_id
    assert not any(layer.name.startswith("Raster:") for layer in window.layer_panel.layers())
    assert not any("Aktives Rastermotiv" in blocker for blocker in _preflight_blockers(window))


@pytest.mark.parametrize(
    ("mode_index", "expected_flags", "layer_comment", "laser_on", "wrong_comment"),
    [
        (1, {"Gravur": False, "Schnitt": True}, "; layer 20: Schnitt", "M3", "; layer 10: Gravur"),
        (0, {"Gravur": True, "Schnitt": False}, "; layer 10: Gravur", "M4", "; layer 20: Schnitt"),
    ],
    ids=["cut_mode", "engrave_mode"],
)
def test_remove_raster_restores_operation_mode_layers(
    window, monkeypatch, tmp_path, mode_index, expected_flags, layer_comment, laser_on, wrong_comment
) -> None:
    """Regression: neither the raster import nor its removal may change the operation-mode layers."""
    window.operation_mode.setCurrentIndex(mode_index)
    _import(window, monkeypatch, _svg(tmp_path, "logo.svg"))
    assert {name: _layer_flags(window)[name] for name in expected_flags} == expected_flags
    _import(window, monkeypatch, _png(tmp_path, "p.png"))
    assert {name: _layer_flags(window)[name] for name in expected_flags} == expected_flags
    layers = window.layer_panel.layers()
    cut_layer = next(layer for layer in layers if layer.name == "Schnitt")
    cut_layer.speed_mm_min = 777  # user tweak after the raster import must survive the removal
    window.layer_panel.set_layers(layers)
    _answer(monkeypatch, "confirm_remove_artwork", True)

    window._remove_selected_artwork()

    flags = _layer_flags(window)
    assert {name: flags[name] for name in expected_flags} == expected_flags
    assert next(layer for layer in window.layer_panel.layers() if layer.name == "Schnitt").speed_mm_min == 777
    gcode = window.gcode_text.toPlainText()
    assert layer_comment in gcode
    assert wrong_comment not in gcode
    assert any(line.startswith(laser_on) for line in gcode.splitlines())


def test_deselect_clears_table_selection_while_rows_remain(window, monkeypatch, tmp_path) -> None:
    """_select_artwork_item(None) must not leave a stale highlighted row behind."""
    for name in ("a.svg", "b.svg"):
        _import(window, monkeypatch, _svg(tmp_path, name))
    assert window.object_table.selectionModel().selectedRows()

    window._select_artwork_item(None)

    assert window.object_table.rowCount() == 2
    assert window.selected_artwork_item_id is None
    assert window.object_table.selectionModel().selectedRows() == []
    assert not window.project_edit_actions.remove_artwork_button.isEnabled()


def test_run_worker_locks_project_edit_buttons_immediately(window, monkeypatch, tmp_path) -> None:
    import threading

    _import(window, monkeypatch, _svg(tmp_path, "logo.svg"))
    actions = window.project_edit_actions
    assert actions.remove_artwork_button.isEnabled() and actions.new_project_button.isEnabled()
    window._sync_position_indicator()  # timer tick: state signature cached, no re-sync on the next tick
    release = threading.Event()

    window._run_worker(lambda: release.wait(5.0))
    try:
        assert window.worker_busy
        assert not actions.remove_artwork_button.isEnabled()
        assert not actions.new_project_button.isEnabled()
        assert actions.remove_artwork_button.toolTip() == LOCKED_REASON
    finally:
        release.set()
        for thread in list(window._worker_threads):
            thread.join(timeout=5.0)
        QApplication.processEvents()  # deliver the queued "finished" signal

    assert not window.worker_busy
    assert actions.remove_artwork_button.isEnabled()


@pytest.mark.parametrize("lock", ["running", "paused", "stopping", "worker_busy"])
def test_project_edit_locked_while_job_runs(window, monkeypatch, tmp_path, lock) -> None:
    _import(window, monkeypatch, _svg(tmp_path, "logo.svg"))
    window.app_controller.switch_controller("Simulator")
    window.app_controller.connect()
    state = window.app_controller.machine_state
    if lock == "worker_busy":
        window.worker_busy = True
        window._sync_machine_action_buttons()
    else:
        if lock == "paused":
            state.transition(MachinePhase.RUNNING, "Job gestartet")
        state.transition(MachinePhase(lock), "Job laeuft")
        assert state.phase == MachinePhase(lock)
        window._sync_position_indicator()  # what the 250 ms machine-state timer runs
    actions = window.project_edit_actions
    _forbid(monkeypatch, "confirm_remove_artwork")
    _forbid(monkeypatch, "confirm_new_project")
    items_before = list(window.laser_project.items)
    gcode_before = window.gcode_text.toPlainText()

    window._remove_selected_artwork()
    window._new_project()

    assert not actions.remove_artwork_button.isEnabled()
    assert not actions.new_project_button.isEnabled()
    assert actions.remove_artwork_button.toolTip() == LOCKED_REASON
    assert actions.new_project_button.toolTip() == LOCKED_REASON
    assert window.laser_project.items == items_before
    assert window.gcode_text.toPlainText() == gcode_before
    window.worker_busy = False


def test_remove_with_generated_test_matrix(window, monkeypatch, tmp_path) -> None:
    _import(window, monkeypatch, _svg(tmp_path, "logo.svg"))
    window._generate_test_matrix()
    matrix_gcode = window.gcode_text.toPlainText()
    calls = _answer(monkeypatch, "confirm_remove_artwork", True)

    window._remove_selected_artwork()

    assert calls == [("logo.svg", True)]
    assert window._generated_job_name is None
    assert window.gcode_text.toPlainText() != matrix_gcode
    assert "Testmatrix verworfen." in window.log_text.toPlainText()


def test_new_project_resets_project_state(window, monkeypatch, tmp_path) -> None:
    window.material_shape.setCurrentText("Kreis")  # Q1: Materialform bleibt erhalten
    start_placement = window._svg_placement_data()
    start_gcode = window.gcode_text.toPlainText()
    start_layers = [(layer.name, layer.layer_type, layer.enabled) for layer in window.layer_panel.layers()]
    for path in (_svg(tmp_path, "logo.svg"), _png(tmp_path)):
        _import(window, monkeypatch, path)
    window.material_points = {1: (1.0, 2.0), 2: (50.0, 2.0), 3: None, 4: None}
    window.material_measurement = {"points": {"1": [1.0, 2.0], "2": [50.0, 2.0]}}
    window._update_material_measurement_label()
    window.current_project_path = str(tmp_path / "old.laser.json")
    window.svg_manual.setChecked(True)
    window.svg_offset_x.setValue(120.0)
    window.svg_margin.setValue(12.0)
    window._update_assistant_panel()
    prepared_before = window.last_prepared_job
    calls = _answer(monkeypatch, "confirm_new_project", True)

    window._new_project()

    assert calls == [(2, False)]
    assert window.laser_project.items == []
    assert _all_cache_keys(window) == set()
    assert window.current_project_path is None
    assert window.material_measurement is None
    assert window.material_points == {1: None, 2: None, 3: None, 4: None}
    assert window.material_measurement_label.text() == "Nicht eingemessen"
    assert window._svg_placement_data() == start_placement
    assert window.material_shape.currentText() == "Kreis"
    assert [(layer.name, layer.layer_type, layer.enabled) for layer in window.layer_panel.layers()] == start_layers
    assert window.gcode_text.toPlainText() == start_gcode
    assert window.selected_artwork_item_id is None and window.artwork_source is None
    # Reset, then re-prepared for the empty project by the assistant refresh: never the old job.
    assert window.last_prepared_job is not prepared_before


def test_new_project_keeps_machine_and_profiles(window, monkeypatch, tmp_path) -> None:
    _connect_and_home(window)
    _import(window, monkeypatch, _svg(tmp_path, "logo.svg"))
    state = window.app_controller.machine_state
    before = {
        "controller": window.app_controller.controller,
        "phase": state.phase,
        "homed": getattr(state, "homed", None),
        "machine_profile": window.machine_profile,
        "material_profiles": list(window.profile_service.names()),
        "profile_name": window.profile_name.currentText(),
        "material_db": window.material_db_records,
        "job_history": window.job_history,
        "connection_mode": window.connection_mode.currentText(),
        "work_area": (window.work_width.value(), window.work_height.value()),
        "operation_mode": window.operation_mode.currentText(),
        "power": window.power_percent.value(),
    }
    _answer(monkeypatch, "confirm_new_project", True)

    window._new_project()

    after = {
        "controller": window.app_controller.controller,
        "phase": state.phase,
        "homed": getattr(state, "homed", None),
        "machine_profile": window.machine_profile,
        "material_profiles": list(window.profile_service.names()),
        "profile_name": window.profile_name.currentText(),
        "material_db": window.material_db_records,
        "job_history": window.job_history,
        "connection_mode": window.connection_mode.currentText(),
        "work_area": (window.work_width.value(), window.work_height.value()),
        "operation_mode": window.operation_mode.currentText(),
        "power": window.power_percent.value(),
    }
    assert after == before
    assert after["job_history"] is before["job_history"]
    assert window.app_controller.machine_state is state


def test_new_project_without_motif_needs_no_confirmation(window, monkeypatch, tmp_path) -> None:
    _forbid(monkeypatch, "confirm_new_project")
    window.current_project_path = str(tmp_path / "old.laser.json")

    window._new_project()

    assert window.current_project_path is None
    assert "Neues Projekt angelegt." in window.log_text.toPlainText()


def test_new_project_after_test_matrix_gates_job_again(window, monkeypatch) -> None:
    _connect_and_home(window)
    window._generate_test_matrix()
    assert window.action_buttons["start_job"][0].isEnabled()
    calls = _answer(monkeypatch, "confirm_new_project", True)

    window._new_project()

    assert calls == [(0, True)]
    assert window._generated_job_name is None
    assert not window.action_buttons["start_job"][0].isEnabled()


def test_new_project_declined_keeps_project(window, monkeypatch, tmp_path) -> None:
    _import(window, monkeypatch, _svg(tmp_path, "logo.svg"))
    window.current_project_path = str(tmp_path / "old.laser.json")
    items_before = list(window.laser_project.items)
    project_before = window.laser_project
    gcode_before = window.gcode_text.toPlainText()
    _answer(monkeypatch, "confirm_new_project", False)

    window._new_project()

    assert window.laser_project is project_before
    assert window.laser_project.items == items_before
    assert window.current_project_path == str(tmp_path / "old.laser.json")
    assert window.gcode_text.toPlainText() == gcode_before


def test_save_after_new_project_asks_for_path(window, monkeypatch, tmp_path) -> None:
    window.current_project_path = str(tmp_path / "old.laser.json")
    window._new_project()
    asked: list = []
    target = tmp_path / "fresh"

    def fake_save_dialog(*_args, **_kwargs):
        asked.append(True)
        return str(target), ""

    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getSaveFileName", fake_save_dialog)
    window._save_project()

    assert asked == [True]
    assert (tmp_path / "fresh.laser.json").exists()
    assert not (tmp_path / "old.laser.json").exists()


def test_import_after_new_project_uses_fresh_offsets(window, monkeypatch, tmp_path) -> None:
    svg = _svg(tmp_path, "logo.svg")
    _import(window, monkeypatch, svg)
    first_position = (window.laser_project.items[0].transform.x_mm, window.laser_project.items[0].transform.y_mm)
    _import(window, monkeypatch, svg)
    assert window.laser_project.items[1].transform.x_mm != pytest.approx(first_position[0])
    _answer(monkeypatch, "confirm_new_project", True)

    window._new_project()
    _import(window, monkeypatch, svg)

    item = window.laser_project.items[0]
    assert len(window.laser_project.items) == 1
    assert (item.transform.x_mm, item.transform.y_mm) == pytest.approx(first_position)


def test_load_project_drops_stale_item_caches(monkeypatch, tmp_path) -> None:
    QApplication.instance() or QApplication([])
    source_window = LaserControlWindow()
    _import(source_window, monkeypatch, _svg(tmp_path, "saved.svg"))
    project_path = tmp_path / "saved.laser.json"
    source_window.current_project_path = str(project_path)
    source_window._save_project()
    source_window.close()

    window = LaserControlWindow()
    _import(window, monkeypatch, _svg(tmp_path, "stale.svg"))
    stale_id = window.laser_project.items[0].item_id
    assert stale_id in window._item_svg_analyses and stale_id in window._item_intelligence_results
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getOpenFileName", lambda *_a, **_k: (str(project_path), ""))

    window._load_project()

    loaded_ids = {item.item_id for item in window.laser_project.items}
    assert stale_id not in loaded_ids
    assert set(window._item_svg_analyses) <= loaded_ids
    assert set(window._item_intelligence_results) <= loaded_ids
    assert _all_cache_keys(window) <= loaded_ids | {"legacy"}
    window.close()
