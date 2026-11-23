"""Gemeinsame Konstanten und Worker-Signale der Qt-Oberflaeche."""

from PySide6.QtCore import QObject, Signal


AUTO_FIT_MARGIN_MM = 0.5
MATERIAL_SHAPE_RECTANGLE = "Rechteck"
MATERIAL_SHAPE_CIRCLE = "Kreis"
JOB_ORIGIN_LOWER_LEFT = "Links unten"
JOB_ORIGIN_CENTER = "Mitte"


class WorkerSignals(QObject):
    log = Signal(str)
    progress = Signal(str, int, int)
    error = Signal(str)
    finished = Signal(bool)
    port_detected = Signal(str)
