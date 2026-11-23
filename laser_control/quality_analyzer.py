from __future__ import annotations

from dataclasses import dataclass

from laser_control.geometry_analyzer import GeometryAnalysis
from laser_control.motif_classifier import MotifClassification


@dataclass(frozen=True)
class QualityReport:
    score: int
    positives: list[str]
    warnings: list[str]
    recommended_optimizations: list[str]

    @property
    def bar(self) -> str:
        filled = max(0, min(10, round(self.score / 10)))
        return "█" * filled + "░" * (10 - filled)


class QualityAnalyzer:
    def evaluate(self, analysis: GeometryAnalysis, classification: MotifClassification) -> QualityReport:
        score = analysis.quality_score
        positives: list[str] = []
        warnings = list(analysis.warnings)
        recommendations: list[str] = []
        if analysis.duplicate_lines == 0:
            positives.append("keine doppelten Linien")
        else:
            recommendations.append("Doppelte Linien entfernen")
        if analysis.open_contours == 0:
            positives.append("saubere geschlossene Konturen")
        elif classification.recommended_strategy == "reine Kontur":
            positives.append("offene Linien fuer Konturgravur geeignet")
        else:
            warnings.append(f"Offene Konturen: {analysis.open_contours}")
        if analysis.self_intersections == 0:
            positives.append("keine Selbstueberschneidungen erkannt")
        else:
            recommendations.append("Selbstueberschneidungen pruefen")
        if analysis.short_segments > 100 or analysis.complexity in {"Hoch", "Extrem"}:
            recommendations.append("Konturen vereinfachen")
            warnings.append("Viele kurze Segmente koennen Gravurzeit und Linienwirkung verschlechtern.")
        if analysis.bezier and analysis.bezier.curve_count:
            positives.append(f"Bezierkurven analysiert: {analysis.bezier.curve_count}")
            if analysis.bezier.high_curvature_count:
                recommendations.append("Flattening-Toleranz fuer Kurven pruefen")
        if analysis.raster:
            positives.append(f"Rasterkontrast {analysis.raster.contrast_score}%")
            if analysis.raster.contrast_score < 35:
                recommendations.append("Rasterkontrast vor Gravur anheben")
            recommendations.append(f"Rastermodus {analysis.raster.recommended_mode}")
        if analysis.estimated_runtime_seconds > 900:
            warnings.append("Gravurzeit hoch")
            recommendations.append("Toolpath optimieren")
        if "Fuellung" in classification.recommended_strategy:
            recommendations.append("Overscan aktivieren")
        return QualityReport(
            score=max(0, min(100, score)),
            positives=positives or ["SVG valide genug fuer Analyse"],
            warnings=warnings,
            recommended_optimizations=_dedupe(recommendations),
        )


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
