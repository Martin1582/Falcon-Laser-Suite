"""Reparatur von Altprojekten mit eingebrannter Raster-Layerbelegung (Qt-frei)."""

from dataclasses import replace

from laser_control.gcode import CUT_MODE, ENGRAVE_MODE
from laser_control.layer_compat import (
    CUT_RESTORED_NOTE,
    LEGACY_RASTER_NAME_PREFIX,
    PARAMETERS_RESET_NOTE,
    repair_legacy_raster_layers,
)
from laser_control.layers import LayerMode, LayerType, build_default_layers, layer_to_dict
from laser_control.models import MaterialProfile

PROFILE = MaterialProfile("Holz", 40, 1200, 1)


def _by_type(layers):
    return {layer.layer_type: layer for layer in layers}


def _legacy_layers(operation_mode: str = CUT_MODE, file_name: str = "p.png"):
    """Genau das Muster, das der alte Raster-Override gespeichert hat."""
    layers = build_default_layers(PROFILE, operation_mode)
    for layer in layers:
        if layer.layer_type == LayerType.ENGRAVE:
            layer.name = f"{LEGACY_RASTER_NAME_PREFIX}{file_name}"
            layer.enabled = True
        elif layer.layer_type == LayerType.CUT:
            layer.enabled = False
    return layers


def test_layers_without_prefix_stay_unchanged() -> None:
    layers = build_default_layers(PROFILE, CUT_MODE)
    before = [layer_to_dict(layer) for layer in layers]

    result = repair_legacy_raster_layers(layers, CUT_MODE)

    assert result.notes == []
    assert [layer_to_dict(layer) for layer in result.layers] == before


def test_engrave_mode_only_renames_the_raster_layer() -> None:
    layers = _legacy_layers(ENGRAVE_MODE)

    result = repair_legacy_raster_layers(layers, ENGRAVE_MODE)

    engrave = _by_type(result.layers)[LayerType.ENGRAVE]
    cut = _by_type(result.layers)[LayerType.CUT]
    assert engrave.name == LayerType.ENGRAVE.value
    assert engrave.enabled is True
    assert cut.enabled is False
    assert len(result.notes) == 2
    assert "p.png" in result.notes[0]
    # The old import rebuilt the layers from the material values in both modes.
    assert result.notes[1] == PARAMETERS_RESET_NOTE


def test_cut_mode_restores_cut_layer_for_exact_legacy_pattern() -> None:
    result = repair_legacy_raster_layers(_legacy_layers(CUT_MODE), CUT_MODE)

    layers = _by_type(result.layers)
    assert layers[LayerType.ENGRAVE].name == "Gravur"
    assert layers[LayerType.ENGRAVE].enabled is False
    assert layers[LayerType.CUT].enabled is True
    assert result.notes[1] == CUT_RESTORED_NOTE.format(cut_name="Schnitt", engrave_name="Gravur")
    assert result.notes[2] == PARAMETERS_RESET_NOTE
    assert "Durchgaenge" in result.notes[2]


def test_cut_mode_keeps_flags_the_user_changed_later() -> None:
    layers = _legacy_layers(CUT_MODE)
    _by_type(layers)[LayerType.CUT].enabled = True  # user re-enabled cutting after the import

    result = repair_legacy_raster_layers(layers, CUT_MODE)

    repaired = _by_type(result.layers)
    assert repaired[LayerType.ENGRAVE].name == "Gravur"
    assert repaired[LayerType.ENGRAVE].enabled is True
    assert repaired[LayerType.CUT].enabled is True
    assert len(result.notes) == 2
    assert result.notes[1] == PARAMETERS_RESET_NOTE  # parameters may still have been reset


def test_repair_keeps_layer_parameters() -> None:
    layers = _legacy_layers(CUT_MODE)
    for layer in layers:
        layer.speed_mm_min = 777
        layer.power_percent = 42
        layer.passes = 3
        layer.mode = LayerMode.FILL
        layer.order = layer.order + 1

    result = repair_legacy_raster_layers(layers, CUT_MODE)

    for layer in result.layers:
        assert (layer.speed_mm_min, layer.power_percent, layer.passes, layer.mode) == (777, 42, 3, LayerMode.FILL)
    assert [layer.order for layer in result.layers] == [layer.order for layer in layers]


def test_repair_does_not_mutate_input() -> None:
    layers = _legacy_layers(CUT_MODE)
    before = [layer_to_dict(layer) for layer in layers]

    repair_legacy_raster_layers(layers, CUT_MODE)

    assert [layer_to_dict(layer) for layer in layers] == before


def test_repair_is_idempotent() -> None:
    first = repair_legacy_raster_layers(_legacy_layers(CUT_MODE), CUT_MODE)

    second = repair_legacy_raster_layers(first.layers, CUT_MODE)

    assert second.notes == []
    assert [layer_to_dict(layer) for layer in second.layers] == [layer_to_dict(layer) for layer in first.layers]


def test_prefix_on_non_engrave_layer_is_ignored() -> None:
    layers = build_default_layers(PROFILE, CUT_MODE)
    layers[2] = replace(layers[2], name=f"{LEGACY_RASTER_NAME_PREFIX}x.png")

    result = repair_legacy_raster_layers(layers, CUT_MODE)

    assert result.notes == []
    assert result.layers[2].name == f"{LEGACY_RASTER_NAME_PREFIX}x.png"
