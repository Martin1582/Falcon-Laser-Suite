from __future__ import annotations

from dataclasses import dataclass
from math import cos, isfinite, radians, sin

from laser_control.svg_import import Polyline, path_bounds


@dataclass(frozen=True)
class ArtworkBounds:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width_mm(self) -> float:
        return max(0.0, self.max_x - self.min_x)

    @property
    def height_mm(self) -> float:
        return max(0.0, self.max_y - self.min_y)

    def within(self, work_width_mm: float, work_height_mm: float, tolerance_mm: float = 1e-6) -> bool:
        return (
            self.min_x >= -tolerance_mm
            and self.min_y >= -tolerance_mm
            and self.max_x <= work_width_mm + tolerance_mm
            and self.max_y <= work_height_mm + tolerance_mm
        )


@dataclass(frozen=True)
class ArtworkTransform:
    x_mm: float
    y_mm: float
    scale: float
    original_width_mm: float
    original_height_mm: float
    current_width_mm: float
    current_height_mm: float
    rotation_deg: float = 0.0
    autofit_applied: bool = False
    aspect_locked: bool = True
    scale_x: float | None = None
    scale_y: float | None = None
    uniform_scale: float | None = None
    keep_aspect_ratio: bool = True
    origin_mode: str = "lower_left"

    def __post_init__(self) -> None:
        scale_x = self.scale if self.scale_x is None else self.scale_x
        scale_y = self.scale if self.scale_y is None else self.scale_y
        if self.keep_aspect_ratio or self.aspect_locked:
            uniform = self.scale if self.uniform_scale is None else self.uniform_scale
            scale_x = uniform
            scale_y = uniform
        else:
            uniform = self.uniform_scale
        object.__setattr__(self, "scale_x", scale_x)
        object.__setattr__(self, "scale_y", scale_y)
        object.__setattr__(self, "uniform_scale", uniform)
        object.__setattr__(self, "rotation_deg", self.rotation_deg % 360.0)
        width, height = _rotated_size(
            self.original_width_mm * scale_x,
            self.original_height_mm * scale_y,
            self.rotation_deg,
        )
        object.__setattr__(self, "current_width_mm", width)
        object.__setattr__(self, "current_height_mm", height)

    @property
    def scale_percent(self) -> float:
        return self.scale_x * 100.0

    @property
    def bounds(self) -> ArtworkBounds:
        return ArtworkBounds(
            self.x_mm,
            self.y_mm,
            self.x_mm + self.current_width_mm,
            self.y_mm + self.current_height_mm,
        )

    @property
    def position_label(self) -> str:
        return f"X {self.x_mm:.1f} mm, Y {self.y_mm:.1f} mm"

    def validate(self) -> None:
        values = (
            self.x_mm,
            self.y_mm,
            self.scale,
            self.scale_x,
            self.scale_y,
            self.original_width_mm,
            self.original_height_mm,
            self.current_width_mm,
            self.current_height_mm,
            self.rotation_deg,
        )
        if not all(isfinite(value) for value in values):
            raise ValueError("Artwork-Transform enthaelt ungueltige Zahlenwerte.")
        if self.original_width_mm <= 0 or self.original_height_mm <= 0:
            raise ValueError("Originalgroesse des Motivs ist unbekannt oder ungueltig.")
        if self.scale <= 0 or self.scale_x <= 0 or self.scale_y <= 0:
            raise ValueError("Skalierung muss groesser als 0 sein.")
        if self.current_width_mm <= 0 or self.current_height_mm <= 0:
            raise ValueError("Aktuelle Motivgroesse ist ungueltig.")

    def with_position(self, x_mm: float, y_mm: float) -> ArtworkTransform:
        updated = ArtworkTransform(
            x_mm=x_mm,
            y_mm=y_mm,
            scale=self.scale,
            original_width_mm=self.original_width_mm,
            original_height_mm=self.original_height_mm,
            current_width_mm=self.current_width_mm,
            current_height_mm=self.current_height_mm,
            rotation_deg=self.rotation_deg,
            autofit_applied=False,
            aspect_locked=self.aspect_locked,
            scale_x=self.scale_x,
            scale_y=self.scale_y,
            uniform_scale=self.uniform_scale,
            keep_aspect_ratio=self.keep_aspect_ratio,
            origin_mode=self.origin_mode,
        )
        updated.validate()
        return updated

    def with_width(self, width_mm: float, aspect_locked: bool = True) -> ArtworkTransform:
        if width_mm <= 0:
            raise ValueError("Motivbreite muss groesser als 0 sein.")
        if aspect_locked:
            ratio = width_mm / self.current_width_mm
            scale_x = self.scale_x * ratio
            scale_y = self.scale_y * ratio
        else:
            scale_x, scale_y = _scales_for_target_width(
                width_mm,
                self.original_width_mm,
                self.original_height_mm,
                self.scale_x,
                self.scale_y,
                self.rotation_deg,
            )
        updated = ArtworkTransform(
            x_mm=self.x_mm,
            y_mm=self.y_mm,
            scale=scale_x,
            original_width_mm=self.original_width_mm,
            original_height_mm=self.original_height_mm,
            current_width_mm=width_mm,
            current_height_mm=self.current_height_mm,
            rotation_deg=self.rotation_deg,
            autofit_applied=False,
            aspect_locked=aspect_locked,
            scale_x=scale_x,
            scale_y=scale_y,
            uniform_scale=scale_x if aspect_locked else None,
            keep_aspect_ratio=aspect_locked,
            origin_mode=self.origin_mode,
        )
        updated.validate()
        return updated

    def with_height(self, height_mm: float, aspect_locked: bool = True) -> ArtworkTransform:
        if height_mm <= 0:
            raise ValueError("Motivhoehe muss groesser als 0 sein.")
        if aspect_locked:
            ratio = height_mm / self.current_height_mm
            scale_x = self.scale_x * ratio
            scale_y = self.scale_y * ratio
        else:
            scale_x, scale_y = _scales_for_target_height(
                height_mm,
                self.original_width_mm,
                self.original_height_mm,
                self.scale_x,
                self.scale_y,
                self.rotation_deg,
            )
        updated = ArtworkTransform(
            x_mm=self.x_mm,
            y_mm=self.y_mm,
            scale=scale_x,
            original_width_mm=self.original_width_mm,
            original_height_mm=self.original_height_mm,
            current_width_mm=self.current_width_mm,
            current_height_mm=height_mm,
            rotation_deg=self.rotation_deg,
            autofit_applied=False,
            aspect_locked=aspect_locked,
            scale_x=scale_x,
            scale_y=scale_y,
            uniform_scale=scale_x if aspect_locked else None,
            keep_aspect_ratio=aspect_locked,
            origin_mode=self.origin_mode,
        )
        updated.validate()
        return updated

    def with_scale_percent(self, percent: float) -> ArtworkTransform:
        if percent <= 0:
            raise ValueError("Skalierung muss groesser als 0 Prozent sein.")
        factor = percent / 100.0
        return ArtworkTransform(
            x_mm=self.x_mm,
            y_mm=self.y_mm,
            scale=factor,
            original_width_mm=self.original_width_mm,
            original_height_mm=self.original_height_mm,
            current_width_mm=self.original_width_mm * factor,
            current_height_mm=self.original_height_mm * factor,
            rotation_deg=self.rotation_deg,
            autofit_applied=False,
            aspect_locked=True,
            scale_x=factor,
            scale_y=factor,
            uniform_scale=factor,
            keep_aspect_ratio=True,
            origin_mode=self.origin_mode,
        )

    def with_rotation(self, rotation_deg: float) -> ArtworkTransform:
        return ArtworkTransform(
            x_mm=self.x_mm,
            y_mm=self.y_mm,
            scale=self.scale,
            original_width_mm=self.original_width_mm,
            original_height_mm=self.original_height_mm,
            current_width_mm=self.current_width_mm,
            current_height_mm=self.current_height_mm,
            rotation_deg=rotation_deg,
            autofit_applied=False,
            aspect_locked=self.aspect_locked,
            scale_x=self.scale_x,
            scale_y=self.scale_y,
            uniform_scale=self.uniform_scale,
            keep_aspect_ratio=self.keep_aspect_ratio,
            origin_mode=self.origin_mode,
        )

    def centered_in(self, work_width_mm: float, work_height_mm: float) -> ArtworkTransform:
        return self.with_position(
            (work_width_mm - self.current_width_mm) / 2.0,
            (work_height_mm - self.current_height_mm) / 2.0,
        )

    def original_size(self) -> ArtworkTransform:
        return ArtworkTransform(
            x_mm=self.x_mm,
            y_mm=self.y_mm,
            scale=1.0,
            original_width_mm=self.original_width_mm,
            original_height_mm=self.original_height_mm,
            current_width_mm=self.original_width_mm,
            current_height_mm=self.original_height_mm,
            rotation_deg=self.rotation_deg,
            autofit_applied=False,
            aspect_locked=True,
            scale_x=1.0,
            scale_y=1.0,
            uniform_scale=1.0,
            keep_aspect_ratio=True,
            origin_mode=self.origin_mode,
        )


@dataclass(frozen=True)
class ArtworkItem:
    source_id: str
    file_name: str
    source_type: str
    transform: ArtworkTransform


def transform_paths(paths: list[Polyline], transform: ArtworkTransform) -> list[Polyline]:
    transform.validate()
    angle = radians(transform.rotation_deg)
    cos_a = cos(angle)
    sin_a = sin(angle)
    rotated = [
        [
            (
                x * transform.scale_x * cos_a - y * transform.scale_y * sin_a,
                x * transform.scale_x * sin_a + y * transform.scale_y * cos_a,
            )
            for x, y in polyline
        ]
        for polyline in paths
    ]
    min_x, min_y, _, _ = path_bounds(rotated)
    return [
        [
            (
                x - min_x + transform.x_mm,
                y - min_y + transform.y_mm,
            )
            for x, y in polyline
        ]
        for polyline in rotated
    ]


def normalize_paths(paths: list[Polyline]) -> list[Polyline]:
    min_x, min_y, _, _ = path_bounds(paths)
    return [[(x - min_x, y - min_y) for x, y in polyline] for polyline in paths]


def _rotated_size(width: float, height: float, rotation_deg: float) -> tuple[float, float]:
    angle = radians(rotation_deg % 360.0)
    cos_a = abs(cos(angle))
    sin_a = abs(sin(angle))
    return width * cos_a + height * sin_a, width * sin_a + height * cos_a


def _scales_for_target_width(
    target_width: float,
    original_width: float,
    original_height: float,
    scale_x: float,
    scale_y: float,
    rotation_deg: float,
) -> tuple[float, float]:
    angle = radians(rotation_deg % 360.0)
    cos_a = abs(cos(angle))
    sin_a = abs(sin(angle))
    if cos_a > 1e-9:
        candidate = (target_width - original_height * scale_y * sin_a) / (original_width * cos_a)
        if candidate > 0:
            return candidate, scale_y
    candidate = target_width / max(original_height * sin_a, 1e-9)
    if candidate <= 0:
        raise ValueError("Motivbreite kann mit der aktuellen Rotation nicht gesetzt werden.")
    return scale_x, candidate


def _scales_for_target_height(
    target_height: float,
    original_width: float,
    original_height: float,
    scale_x: float,
    scale_y: float,
    rotation_deg: float,
) -> tuple[float, float]:
    angle = radians(rotation_deg % 360.0)
    cos_a = abs(cos(angle))
    sin_a = abs(sin(angle))
    if cos_a > 1e-9:
        candidate = (target_height - original_width * scale_x * sin_a) / (original_height * cos_a)
        if candidate > 0:
            return scale_x, candidate
    candidate = target_height / max(original_width * sin_a, 1e-9)
    if candidate <= 0:
        raise ValueError("Motivhoehe kann mit der aktuellen Rotation nicht gesetzt werden.")
    return candidate, scale_y
