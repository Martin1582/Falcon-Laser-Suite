from __future__ import annotations

from dataclasses import dataclass, field
from statistics import pstdev

from laser_control.artwork_import import RasterImageSource


@dataclass(frozen=True)
class RasterQualityAnalysis:
    pixel_width: int = 0
    pixel_height: int = 0
    dpi: tuple[float, float] | None = None
    width_mm: float = 0.0
    height_mm: float = 0.0
    color_mode: str = "unknown"
    has_transparency: bool = False
    contrast_score: int = 0
    brightness_mean: float = 0.0
    detail_density_score: int = 0
    raster_quality_score: int = 0
    recommended_line_interval_mm: float = 0.10
    recommended_mode: str = "grayscale"
    warnings: list[str] = field(default_factory=list)


class RasterAnalyzer:
    def analyze(self, source: RasterImageSource) -> RasterQualityAnalysis:
        pixels = list(source.grayscale_data)
        count = len(pixels)
        warnings = list(source.import_warnings)
        if count == 0:
            warnings.append("Rasterbild enthaelt keine Graustufendaten.")
            return RasterQualityAnalysis(warnings=warnings)

        mean = sum(pixels) / count
        stddev = pstdev(pixels) if count > 1 else 0.0
        contrast_score = max(0, min(100, round(stddev / 64 * 100)))
        transitions = _sample_transitions(pixels, source.pixel_width, source.pixel_height)
        detail_density = max(0, min(100, round(transitions / 48 * 100)))
        interval = source.width_mm / max(1, source.pixel_width)
        target_interval = 0.10 if contrast_score < 55 else 0.08
        recommended_mode = "dithering" if contrast_score >= 55 and detail_density >= 40 else "grayscale"
        if source.dpi is None:
            warnings.append("DPI unbekannt - Groesse wurde mit 96 DPI geschaetzt.")
        if contrast_score < 35:
            warnings.append("Bild ist kontrastarm - Kontrasterhoehung empfohlen.")
        if interval > 0.15:
            warnings.append("Bildaufloesung zu gering fuer aktuelle Skalierung.")
        else:
            warnings.append("Bildaufloesung reicht fuer aktuelle Skalierung aus.")
        if source.has_transparency:
            warnings.append("Transparenz vorhanden - Hintergrundwirkung vor Gravur pruefen.")
        quality = 100 - max(0, 35 - contrast_score) - (20 if interval > 0.15 else 0) - (10 if source.dpi is None else 0)
        return RasterQualityAnalysis(
            pixel_width=source.pixel_width,
            pixel_height=source.pixel_height,
            dpi=source.dpi,
            width_mm=source.width_mm,
            height_mm=source.height_mm,
            color_mode=source.color_mode,
            has_transparency=source.has_transparency,
            contrast_score=contrast_score,
            brightness_mean=mean,
            detail_density_score=detail_density,
            raster_quality_score=max(0, min(100, quality)),
            recommended_line_interval_mm=target_interval,
            recommended_mode=recommended_mode,
            warnings=_dedupe(warnings),
        )


def _sample_transitions(pixels: list[int], width: int, height: int) -> float:
    if width <= 1 or height <= 0:
        return 0.0
    rows = min(height, 80)
    step_y = max(1, height // rows)
    diffs: list[int] = []
    for y in range(0, height, step_y):
        row_start = y * width
        row = pixels[row_start : row_start + width]
        step_x = max(1, width // 120)
        for x in range(step_x, len(row), step_x):
            diffs.append(abs(row[x] - row[x - step_x]))
    return sum(diffs) / max(1, len(diffs))


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
