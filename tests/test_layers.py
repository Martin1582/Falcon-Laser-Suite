"""Modusabhaengige Layer-Pruefung fuer den Preflight (Qt-frei)."""

from laser_control.gcode import CUT_MODE, ENGRAVE_MODE
from laser_control.layers import LayerType, build_default_layers, operation_mode_layer_blockers
from laser_control.models import MaterialProfile

PROFILE = MaterialProfile("Holz", 40, 1200, 1)


def _layers(operation_mode: str, enabled: dict[LayerType, bool]):
    layers = build_default_layers(PROFILE, operation_mode)
    for layer in layers:
        layer.enabled = enabled.get(layer.layer_type, False)
    return layers


def test_cut_mode_without_cut_layer_is_blocked() -> None:
    layers = _layers(CUT_MODE, {LayerType.ENGRAVE: True})

    blockers = operation_mode_layer_blockers(layers, CUT_MODE)

    assert len(blockers) == 1
    assert "Schnitt" in blockers[0]
    assert "mit Layer 'Gravur' ausgegeben" in blockers[0]  # names the layer that would actually be used
    assert "Gravieren" in blockers[0]  # names the remedy


def test_cut_mode_blocker_names_several_layers_in_plural() -> None:
    layers = _layers(CUT_MODE, {LayerType.ENGRAVE: True, LayerType.MARK: True})

    blockers = operation_mode_layer_blockers(layers, CUT_MODE)

    assert len(blockers) == 1
    assert "mit den Layern 'Gravur', 'Markierung' ausgegeben" in blockers[0]


def test_cut_mode_with_only_mark_layer_is_blocked() -> None:
    layers = _layers(CUT_MODE, {LayerType.MARK: True})

    assert len(operation_mode_layer_blockers(layers, CUT_MODE)) == 1


def test_cut_mode_with_active_cut_layer_is_fine() -> None:
    layers = _layers(CUT_MODE, {LayerType.ENGRAVE: True, LayerType.CUT: True})

    assert operation_mode_layer_blockers(layers, CUT_MODE) == []


def test_engrave_mode_without_cut_layer_is_fine() -> None:
    layers = _layers(ENGRAVE_MODE, {LayerType.ENGRAVE: True})

    assert operation_mode_layer_blockers(layers, ENGRAVE_MODE) == []


def test_cut_mode_without_any_output_layer_is_left_to_layer_validation() -> None:
    layers = _layers(CUT_MODE, {LayerType.HELPER: True})

    assert operation_mode_layer_blockers(layers, CUT_MODE) == []
