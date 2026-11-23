from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from laser_control.geometry_analyzer import GeometryAnalysis


class MotifClass(StrEnum):
    TEXT = "Schrift"
    LOGO = "Logo"
    POLYGON_ART = "Polygon-Art"
    TECHNICAL_DRAWING = "Technische Zeichnung"
    ORNAMENT = "Ornament"
    MANDALA = "Mandala"
    PHOTO = "Foto"
    RASTER = "Rasterbild"
    QR_CODE = "QR-Code"
    BARCODE = "Barcode"
    NAMEPLATE = "Typenschild"


@dataclass(frozen=True)
class MotifClassification:
    motif_class: MotifClass
    confidence: int
    reason: str
    recommended_strategy: str


class MotifClassifier:
    def classify(self, analysis: GeometryAnalysis, file_name: str = "") -> MotifClassification:
        lowered = file_name.lower()
        if analysis.source_type == "raster":
            if "qr" in lowered:
                return MotifClassification(MotifClass.QR_CODE, 80, "Dateiname und Rasterquelle deuten auf QR-Code.", "Kontur/Raster pruefen")
            if "barcode" in lowered or "ean" in lowered:
                return MotifClassification(MotifClass.BARCODE, 80, "Dateiname deutet auf Barcode.", "reine Kontur oder hoher Kontrast")
            return MotifClassification(MotifClass.RASTER, 75, "Rasterquelle importiert.", "Rastergravur")
        if any(token in lowered for token in ("text", "schrift", "font", "name")):
            return MotifClassification(MotifClass.TEXT, 75, "Dateiname deutet auf Schrift.", "Kontur")
        if analysis.open_contours > analysis.closed_contours * 3 and analysis.segment_count < 3_000:
            return MotifClassification(MotifClass.TECHNICAL_DRAWING, 70, "Viele offene Linien und moderate Segmentzahl.", "reine Kontur")
        if analysis.closed_contours > 20 and analysis.holes > 5:
            return MotifClassification(MotifClass.MANDALA, 65, "Viele geschlossene Konturen mit Hierarchie.", "Kontur optimieren")
        if analysis.segment_count > 10_000:
            return MotifClassification(MotifClass.POLYGON_ART, 70, "Sehr hohe Segmentzahl.", "Kontur optimieren")
        if analysis.closed_contours >= 3 and analysis.total_area_mm2 > 0:
            return MotifClassification(MotifClass.LOGO, 65, "Geschlossene Flaechenkonturen erkannt.", "Kontur + Fuellung")
        return MotifClassification(MotifClass.ORNAMENT, 55, "Allgemeines Vektormotiv.", "Kontur")
