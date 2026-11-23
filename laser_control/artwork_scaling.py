from __future__ import annotations

from dataclasses import dataclass

from laser_control.artwork_transform import ArtworkTransform, normalize_paths, transform_paths
from laser_control.svg_import import Polyline, path_bounds


@dataclass(frozen=True)
class AutoFitResult:
    original_width_mm: float
    original_height_mm: float
    current_width_mm: float
    current_height_mm: float
    scale_factor: float
    offset_x_mm: float
    offset_y_mm: float
    work_width_mm: float
    work_height_mm: float
    applied: bool
    position: str = "zentriert"

    @property
    def scale_percent(self) -> float:
        return self.scale_factor * 100.0

    @property
    def summary(self) -> str:
        if self.applied:
            return (
                "Motiv automatisch eingepasst: "
                f"{self.original_width_mm:.1f} x {self.original_height_mm:.1f} mm -> "
                f"{self.current_width_mm:.1f} x {self.current_height_mm:.1f} mm "
                f"({self.scale_percent:.1f}%, {self.position})"
            )
        return "Motiv passt vollständig in den Arbeitsbereich."


def autofit_to_transform(result: AutoFitResult) -> ArtworkTransform:
    return ArtworkTransform(
        x_mm=result.offset_x_mm,
        y_mm=result.offset_y_mm,
        scale=result.scale_factor,
        original_width_mm=result.original_width_mm,
        original_height_mm=result.original_height_mm,
        current_width_mm=result.current_width_mm,
        current_height_mm=result.current_height_mm,
        autofit_applied=result.applied,
    )
class AutoFitService:
    def fit(
        self,
        source_width_mm: float,
        source_height_mm: float,
        work_width_mm: float,
        work_height_mm: float,
        margin_mm: float = 0.0,
        allow_upscale: bool = False,
    ) -> AutoFitResult:
        if source_width_mm <= 0 or source_height_mm <= 0:
            raise ValueError("Motivgroesse ist unbekannt oder ungueltig.")
        if work_width_mm <= 0 or work_height_mm <= 0:
            raise ValueError("Arbeitsbereich ist ungueltig.")

        margin = max(0.0, margin_mm)
        available_width = max(1.0, work_width_mm - margin * 2)
        available_height = max(1.0, work_height_mm - margin * 2)
        fit_scale = min(available_width / source_width_mm, available_height / source_height_mm)
        scale = fit_scale if allow_upscale else min(1.0, fit_scale)
        current_width = source_width_mm * scale
        current_height = source_height_mm * scale
        offset_x = margin + (available_width - current_width) / 2
        offset_y = margin + (available_height - current_height) / 2
        return AutoFitResult(
            original_width_mm=source_width_mm,
            original_height_mm=source_height_mm,
            current_width_mm=current_width,
            current_height_mm=current_height,
            scale_factor=scale,
            offset_x_mm=offset_x,
            offset_y_mm=offset_y,
            work_width_mm=work_width_mm,
            work_height_mm=work_height_mm,
            applied=scale < 0.999999,
        )

    def fit_transform(
        self,
        source_width_mm: float,
        source_height_mm: float,
        work_width_mm: float,
        work_height_mm: float,
        margin_mm: float = 0.0,
        allow_upscale: bool = False,
    ) -> ArtworkTransform:
        return autofit_to_transform(
            self.fit(
                source_width_mm,
                source_height_mm,
                work_width_mm,
                work_height_mm,
                margin_mm,
                allow_upscale,
            )
        )

    def fit_paths(
        self,
        paths: list[Polyline],
        work_width_mm: float,
        work_height_mm: float,
        margin_mm: float = 0.0,
        allow_upscale: bool = False,
    ) -> tuple[list[Polyline], AutoFitResult]:
        min_x, min_y, max_x, max_y = path_bounds(paths)
        result = self.fit(
            max_x - min_x,
            max_y - min_y,
            work_width_mm,
            work_height_mm,
            margin_mm,
            allow_upscale,
        )
        normalized_paths = normalize_paths(paths)
        transformed = transform_paths(normalized_paths, autofit_to_transform(result))
        return transformed, result
