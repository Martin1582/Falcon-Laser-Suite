"""Regression: ein Rasterbild im Projekt darf die Layer und ihre Nutzerparameter nie veraendern."""

import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from laser_control.layer_compat import PARAMETERS_RESET_NOTE
from laser_control.layers import LayerType, layer_to_dict
from laser_control.pyside_app import LaserControlWindow
from laser_control.window_project import LEGACY_LAYER_REPAIR_MESSAGE

SQUARE_SVG = '<svg width="10mm" height="10mm" viewBox="0 0 10 10"><polyline points="0,0 10,0 10,10 0,10 0,0"/></svg>'

# (mode index, active layer type, expected layer comment, laser-on command, layer comment that must be absent)
MODES = [
    pytest.param(1, LayerType.CUT, "; layer 20: Schnitt", "M3", "; layer 10:", id="cut_mode"),
    pytest.param(0, LayerType.ENGRAVE, "; layer 10: Gravur", "M4", "; layer 20:", id="engrave_mode"),
]
MODE_PARAMS = ("mode_index", "active_type", "layer_comment", "laser_on", "wrong_comment")


@pytest.fixture
def window():
    QApplication.instance() or QApplication([])
    created = LaserControlWindow()
    created.sidebar_sections["Projekt"].setChecked(True)
    yield created
    created.close()


@pytest.fixture
def info_dialogs(monkeypatch) -> list:
    """Faengt Hinweisdialoge ab, damit modale Fenster den Test nicht blockieren."""
    calls: list = []
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.information", lambda *args, **_kwargs: calls.append(args))
    return calls


def _svg(tmp_path, name: str = "logo.svg"):
    path = tmp_path / name
    path.write_text(SQUARE_SVG, encoding="utf-8")
    return path


def _png(tmp_path, name: str = "p.png"):
    from PIL import Image

    path = tmp_path / name
    Image.new("L", (20, 20), 128).save(path, dpi=(254, 254))
    return path


def _import(window, monkeypatch, path) -> None:
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getOpenFileName", lambda *_a, _p=path, **_k: (str(_p), ""))
    window._import_svg()


def _snapshot(window) -> list[dict]:
    return [layer_to_dict(layer) for layer in window.layer_panel.layers()]


def _layer(window, layer_type: LayerType):
    return next(layer for layer in window.layer_panel.layers() if layer.layer_type == layer_type)


def _set_layer(window, layer_type: LayerType, **values) -> None:
    layers = window.layer_panel.layers()
    for layer in layers:
        if layer.layer_type == layer_type:
            for key, value in values.items():
                setattr(layer, key, value)
    window.layer_panel.set_layers(layers)
    window._layer_changed()


def _prepare_vector_job(window, monkeypatch, tmp_path, mode_index: int, active_type: LayerType) -> list[dict]:
    """SVG importieren und am aktiven Modus-Layer Nutzerwerte setzen; liefert den Layer-Snapshot."""
    window.operation_mode.setCurrentIndex(mode_index)
    _import(window, monkeypatch, _svg(tmp_path))
    assert _layer(window, active_type).enabled
    _set_layer(window, active_type, passes=3, speed_mm_min=777, power_percent=42)
    return _snapshot(window)


def _raster_item(window):
    return next(item for item in window.laser_project.items if item.is_raster)


def _vector_item(window):
    return next(item for item in window.laser_project.items if not item.is_raster)


def _deactivate_in_object_table(window, item) -> None:
    row = window.laser_project.items.index(item)
    window.object_table.item(row, 1).setCheckState(Qt.CheckState.Unchecked)


def _preflight_blockers(window) -> list[str]:
    context = window._job_context(window.app_controller.controller, window.gcode_text.toPlainText())
    return window.workflow.prepare_preflight(context).blockers


def _save(window, path) -> None:
    window.current_project_path = str(path)
    window._save_project()


def _load(monkeypatch, path) -> tuple[LaserControlWindow, list[str]]:
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getOpenFileName", lambda *_a, **_k: (str(path), ""))
    loaded = LaserControlWindow()
    messages: list[str] = []
    monkeypatch.setattr(loaded, "log", messages.append)
    loaded._load_project()
    return loaded, messages


@pytest.mark.parametrize(MODE_PARAMS, MODES)
def test_raster_import_keeps_layers(
    window, monkeypatch, tmp_path, mode_index, active_type, layer_comment, laser_on, wrong_comment
) -> None:
    snapshot = _prepare_vector_job(window, monkeypatch, tmp_path, mode_index, active_type)

    _import(window, monkeypatch, _png(tmp_path))

    assert _snapshot(window) == snapshot
    assert not any(layer.name.startswith("Raster:") for layer in window.layer_panel.layers())


@pytest.mark.parametrize(MODE_PARAMS, MODES)
def test_raster_import_keeps_vector_gcode_after_deactivating_raster(
    window, monkeypatch, tmp_path, mode_index, active_type, layer_comment, laser_on, wrong_comment
) -> None:
    _prepare_vector_job(window, monkeypatch, tmp_path, mode_index, active_type)
    _import(window, monkeypatch, _png(tmp_path))

    _deactivate_in_object_table(window, _raster_item(window))

    assert _raster_item(window).active is False
    gcode = window.gcode_text.toPlainText()
    assert f"{layer_comment} 777 mm/min 42% 3x" in gcode
    assert wrong_comment not in gcode
    assert sum(1 for line in gcode.splitlines() if line.startswith("; pass")) == 3
    assert any(line.startswith(laser_on) for line in gcode.splitlines())
    assert not any("Aktives Rastermotiv" in blocker for blocker in _preflight_blockers(window))


@pytest.mark.parametrize(MODE_PARAMS, MODES)
def test_selecting_vector_after_raster_import_keeps_layers(
    window, monkeypatch, tmp_path, mode_index, active_type, layer_comment, laser_on, wrong_comment
) -> None:
    snapshot = _prepare_vector_job(window, monkeypatch, tmp_path, mode_index, active_type)
    _import(window, monkeypatch, _png(tmp_path))

    window._select_artwork_item(_vector_item(window).item_id)

    assert _snapshot(window) == snapshot


@pytest.mark.parametrize(MODE_PARAMS, MODES)
def test_mode_switch_with_raster_in_project_enables_mode_layer(
    window, monkeypatch, tmp_path, mode_index, active_type, layer_comment, laser_on, wrong_comment
) -> None:
    window.operation_mode.setCurrentIndex(1 - mode_index)
    _import(window, monkeypatch, _svg(tmp_path))
    _import(window, monkeypatch, _png(tmp_path))

    window.operation_mode.setCurrentIndex(mode_index)

    enabled = {layer.layer_type for layer in window.layer_panel.layers() if layer.enabled}
    assert enabled == {active_type}


def _assert_only_mode_layer_active(window, active_type, layer_comment, wrong_comment) -> None:
    assert not any(layer.name.startswith("Raster:") for layer in window.layer_panel.layers())
    assert {layer.layer_type for layer in window.layer_panel.layers() if layer.enabled} == {active_type}
    gcode = window.gcode_text.toPlainText()
    assert layer_comment in gcode
    assert wrong_comment not in gcode


@pytest.mark.parametrize(MODE_PARAMS, MODES)
def test_material_profile_change_with_raster_keeps_mode_layer(
    window, monkeypatch, tmp_path, mode_index, active_type, layer_comment, laser_on, wrong_comment
) -> None:
    window.operation_mode.setCurrentIndex(mode_index)
    _import(window, monkeypatch, _svg(tmp_path))
    _import(window, monkeypatch, _png(tmp_path))
    other_profile = next(name for name in window.profile_service.names() if name != window.profile_name.currentText())

    window.profile_name.setCurrentText(other_profile)

    assert window.profile_name.currentText() == other_profile
    _assert_only_mode_layer_active(window, active_type, layer_comment, wrong_comment)


@pytest.mark.parametrize(MODE_PARAMS, MODES)
def test_saving_new_material_profile_with_raster_keeps_mode_layer(
    window, monkeypatch, tmp_path, mode_index, active_type, layer_comment, laser_on, wrong_comment
) -> None:
    window.operation_mode.setCurrentIndex(mode_index)
    _import(window, monkeypatch, _svg(tmp_path))
    _import(window, monkeypatch, _png(tmp_path))

    window._save_new_material_profile("Test Raster Material", "Holz", 3.0, 1500, 30, 2, active_type.value)

    assert window.profile_name.currentText() == "Test Raster Material"
    _assert_only_mode_layer_active(window, active_type, layer_comment, wrong_comment)


@pytest.mark.parametrize(MODE_PARAMS, MODES)
def test_remove_raster_keeps_user_layer_state(
    window, monkeypatch, tmp_path, mode_index, active_type, layer_comment, laser_on, wrong_comment
) -> None:
    _prepare_vector_job(window, monkeypatch, tmp_path, mode_index, active_type)
    _import(window, monkeypatch, _png(tmp_path))
    _set_layer(window, LayerType.MARK, enabled=True)
    snapshot = _snapshot(window)
    monkeypatch.setattr("laser_control.window_project_lifecycle.confirm_remove_artwork", lambda *_args: True)

    window._select_artwork_item(_raster_item(window).item_id)
    window._remove_selected_artwork()

    assert not any(item.is_raster for item in window.laser_project.items)
    assert _snapshot(window) == snapshot


@pytest.mark.parametrize(MODE_PARAMS, MODES)
def test_save_load_roundtrip_keeps_layers_with_raster(
    window, monkeypatch, tmp_path, info_dialogs, mode_index, active_type, layer_comment, laser_on, wrong_comment
) -> None:
    snapshot = _prepare_vector_job(window, monkeypatch, tmp_path, mode_index, active_type)
    _import(window, monkeypatch, _png(tmp_path))
    project_path = tmp_path / "roundtrip.laser.json"
    _save(window, project_path)

    loaded, messages = _load(monkeypatch, project_path)
    try:
        assert _snapshot(loaded) == snapshot
        assert not any("Altprojekt" in message for message in messages)
        assert info_dialogs == []
    finally:
        loaded.close()


def _write_legacy_project(window, monkeypatch, tmp_path, mode_index: int):
    """Speichert ein Projekt und bringt es in den Zustand, den der alte Raster-Override hinterliess."""
    window.operation_mode.setCurrentIndex(mode_index)
    _import(window, monkeypatch, _svg(tmp_path))
    _import(window, monkeypatch, _png(tmp_path))
    project_path = tmp_path / "legacy.laser.json"
    _save(window, project_path)
    data = json.loads(project_path.read_text(encoding="utf-8"))
    for layer in data["layers"]:
        if layer["type"] == LayerType.ENGRAVE.value:
            layer.update(name="Raster: p.png", enabled=True)
        elif layer["type"] == LayerType.CUT.value:
            layer["enabled"] = False
    data["gcode"] = "; Laser Control\n; layer 10: Raster: p.png 1200 mm/min 40% 1x\nM4 S400\nM5"
    project_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return project_path


def test_load_legacy_raster_project_repairs_cut_mode(window, monkeypatch, tmp_path, info_dialogs) -> None:
    project_path = _write_legacy_project(window, monkeypatch, tmp_path, mode_index=1)
    original_bytes = project_path.read_bytes()

    loaded, messages = _load(monkeypatch, project_path)
    try:
        engrave = _layer(loaded, LayerType.ENGRAVE)
        assert engrave.name == "Gravur"
        assert engrave.enabled is False
        assert _layer(loaded, LayerType.CUT).enabled is True
        gcode = loaded.gcode_text.toPlainText()
        assert "; layer 20: Schnitt" in gcode
        assert "Raster: p.png" not in gcode
        assert PARAMETERS_RESET_NOTE in messages
        assert any("wieder Layer 'Schnitt'" in message for message in messages)
        assert len(info_dialogs) == 1
        assert PARAMETERS_RESET_NOTE in info_dialogs[0][2]
        assert project_path.read_bytes() == original_bytes
    finally:
        loaded.close()


def test_load_legacy_raster_project_engrave_mode_only_renames(window, monkeypatch, tmp_path, info_dialogs) -> None:
    project_path = _write_legacy_project(window, monkeypatch, tmp_path, mode_index=0)
    original_bytes = project_path.read_bytes()

    loaded, messages = _load(monkeypatch, project_path)
    try:
        assert _layer(loaded, LayerType.ENGRAVE).name == "Gravur"
        assert _layer(loaded, LayerType.ENGRAVE).enabled is True
        assert _layer(loaded, LayerType.CUT).enabled is False
        assert "Raster: p.png" not in loaded.gcode_text.toPlainText()
        assert any("p.png" in message for message in messages)
        # The old import also reset the engraving parameters; the user must be told in this mode too.
        assert PARAMETERS_RESET_NOTE in messages
        assert len(info_dialogs) == 1
        assert PARAMETERS_RESET_NOTE in info_dialogs[0][2]
        assert project_path.read_bytes() == original_bytes
    finally:
        loaded.close()


def test_load_legacy_project_without_items_keeps_stored_gcode(window, monkeypatch, tmp_path, info_dialogs) -> None:
    """Ohne Motive (z. B. gespeicherte Testmatrix) bleibt der gespeicherte G-Code erhalten."""
    project_path = _write_legacy_project(window, monkeypatch, tmp_path, mode_index=1)
    data = json.loads(project_path.read_text(encoding="utf-8"))
    data["laser_project"]["items"] = []
    data["artwork_source"] = None
    data["imported_file"] = None
    data["imported_paths"] = []
    project_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    loaded, messages = _load(monkeypatch, project_path)
    try:
        assert _layer(loaded, LayerType.CUT).enabled is True
        assert loaded.gcode_text.toPlainText() == data["gcode"]
        # The correction is reported even though the G-code is kept.
        repair_notes = [message for message in messages if message.startswith("Altprojekt:")]
        assert len(repair_notes) == 3
        assert len(info_dialogs) == 1
        assert info_dialogs[0][1] == "Projekt laden"
        assert info_dialogs[0][2] == LEGACY_LAYER_REPAIR_MESSAGE.format(notes="\n\n".join(repair_notes))
    finally:
        loaded.close()


def test_cut_mode_preflight_blocks_without_cut_layer(window, monkeypatch, tmp_path) -> None:
    _prepare_vector_job(window, monkeypatch, tmp_path, 1, LayerType.CUT)
    assert not any("Schnitt-Layer" in blocker for blocker in _preflight_blockers(window))

    _set_layer(window, LayerType.CUT, enabled=False)
    _set_layer(window, LayerType.ENGRAVE, enabled=True)

    assert any("Kein Schnitt-Layer aktiv" in blocker for blocker in _preflight_blockers(window))


def test_cut_mode_preflight_does_not_block_generated_test_matrix(window, monkeypatch, tmp_path) -> None:
    _prepare_vector_job(window, monkeypatch, tmp_path, 1, LayerType.CUT)
    _set_layer(window, LayerType.CUT, enabled=False)
    _set_layer(window, LayerType.ENGRAVE, enabled=True)

    window._generate_test_matrix()

    assert not any("Schnitt-Layer" in blocker for blocker in _preflight_blockers(window))


def _matrix_gcode(window) -> str:
    window._generate_test_matrix()
    return window.gcode_text.toPlainText()


def test_load_legacy_project_with_artwork_keeps_saved_test_matrix(window, monkeypatch, tmp_path, info_dialogs) -> None:
    """Testmatrix + Motive + Altlayer: die Reparatur darf die gespeicherte Matrix nicht ersetzen."""
    project_path = _write_legacy_project(window, monkeypatch, tmp_path, mode_index=1)
    data = json.loads(project_path.read_text(encoding="utf-8"))
    data["gcode"] = _matrix_gcode(window)
    project_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    assert data["laser_project"]["items"]

    loaded, messages = _load(monkeypatch, project_path)
    try:
        assert loaded.gcode_text.toPlainText() == data["gcode"]
        assert loaded._generated_job_name == "Testmatrix"
        assert _layer(loaded, LayerType.CUT).enabled is True  # layers are still repaired
        assert PARAMETERS_RESET_NOTE in messages
        assert len(info_dialogs) == 1
    finally:
        loaded.close()


def test_loaded_test_matrix_with_artwork_is_framed_as_generated_job(window, monkeypatch, tmp_path) -> None:
    _import(window, monkeypatch, _svg(tmp_path))
    window.svg_offset_x.setValue(250.0)
    matrix = _matrix_gcode(window)
    project_path = tmp_path / "matrix.laser.json"
    _save(window, project_path)

    loaded, _messages = _load(monkeypatch, project_path)
    try:
        assert loaded.gcode_text.toPlainText() == matrix
        assert loaded._generated_job_name == "Testmatrix"
        frame = loaded.get_transformed_bounds()
        assert frame.max_x < 250.0  # matrix area, not the artwork placed at X 250
        context = loaded._job_context(loaded.app_controller.controller, matrix)
        assert context.source_type == "generated"
    finally:
        loaded.close()


def test_loading_artwork_project_clears_a_previous_generated_job(window, monkeypatch, tmp_path) -> None:
    _import(window, monkeypatch, _svg(tmp_path))
    project_path = tmp_path / "artwork.laser.json"
    _save(window, project_path)
    _matrix_gcode(window)
    assert window._generated_job_name == "Testmatrix"
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getOpenFileName", lambda *_a, **_k: (str(project_path), ""))

    window._load_project()

    assert window._generated_job_name is None
