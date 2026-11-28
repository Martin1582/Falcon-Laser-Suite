"""Korrektur von Altprojekten, in denen der fruehere Raster-Override die Layer veraendert hat.

Bis zu diesem Fix hat ein Raster-Import den Gravur-Layer in "Raster: <Datei>" umbenannt und
aktiviert und im Modus Cutten den Schnitt-Layer abgeschaltet. Layernamen sind in der Oberflaeche
nicht editierbar; das Praefix ist daher ein verlaessliches Erkennungsmerkmal.
"""

from dataclasses import dataclass, replace

from laser_control.gcode import CUT_MODE
from laser_control.layers import JobLayer, LayerType

LEGACY_RASTER_NAME_PREFIX = "Raster: "

RENAMED_NOTE = "Altprojekt: Layer '{old_name}' wurde wieder in '{new_name}' umbenannt."
CUT_RESTORED_NOTE = "Altprojekt: Im Modus Cutten ist wieder Layer '{cut_name}' statt '{engrave_name}' aktiv."
# Der alte Raster-Import hat in beiden Modi alle Layer aus den Materialwerten neu aufgebaut.
PARAMETERS_RESET_NOTE = (
    "Altprojekt: Beim damaligen Rasterimport koennen Leistung, Geschwindigkeit und Durchgaenge "
    "der Layer auf die Materialwerte zurueckgesetzt worden sein. Bitte die Werte der aktiven Layer "
    "pruefen; die urspruenglichen Werte sind in der Datei nicht mehr enthalten."
)


@dataclass(frozen=True)
class LayerRepairResult:
    layers: list[JobLayer]
    notes: list[str]  # leer = nichts geaendert


def repair_legacy_raster_layers(layers: list[JobLayer], operation_mode: str) -> LayerRepairResult:
    """Liefert korrigierte Kopien der Layer; die Eingabe bleibt unveraendert, der Aufruf ist idempotent.

    Leistung, Geschwindigkeit, Durchgaenge und Fuellung werden nicht angefasst: die vor dem
    Raster-Import gueltigen Werte sind nicht gespeichert und lassen sich nicht rekonstruieren.
    """
    repaired = [replace(layer) for layer in layers]
    engrave = _legacy_raster_layer(repaired)
    if engrave is None:
        return LayerRepairResult(repaired, [])
    notes = [RENAMED_NOTE.format(old_name=engrave.name, new_name=LayerType.ENGRAVE.value)]
    engrave.name = LayerType.ENGRAVE.value
    cut = next((layer for layer in repaired if layer.layer_type == LayerType.CUT), None)
    # Nur das exakte Muster des alten Overrides; jeder andere Zustand stammt vom Nutzer.
    if operation_mode == CUT_MODE and cut is not None and engrave.enabled and not cut.enabled:
        engrave.enabled = False
        cut.enabled = True
        notes.append(CUT_RESTORED_NOTE.format(cut_name=cut.name, engrave_name=engrave.name))
    notes.append(PARAMETERS_RESET_NOTE)
    return LayerRepairResult(repaired, notes)


def _legacy_raster_layer(layers: list[JobLayer]) -> JobLayer | None:
    return next(
        (
            layer
            for layer in layers
            if layer.layer_type == LayerType.ENGRAVE and layer.name.startswith(LEGACY_RASTER_NAME_PREFIX)
        ),
        None,
    )
