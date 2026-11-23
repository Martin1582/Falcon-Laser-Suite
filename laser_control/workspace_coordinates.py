from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkspaceCoordinateMapper:
    """Maps workspace millimeters with lower-left origin to screen pixels."""

    origin_x_px: float
    origin_y_px: float
    width_mm: float
    height_mm: float
    scale_px_per_mm: float

    def to_screen(self, x_mm: float, y_mm: float) -> tuple[float, float]:
        return (
            self.origin_x_px + x_mm * self.scale_px_per_mm,
            self.origin_y_px + (self.height_mm - y_mm) * self.scale_px_per_mm,
        )

    def to_workspace(self, x_px: float, y_px: float) -> tuple[float, float]:
        return (
            (x_px - self.origin_x_px) / self.scale_px_per_mm,
            self.height_mm - (y_px - self.origin_y_px) / self.scale_px_per_mm,
        )

    def rect_to_screen(self, min_x_mm: float, min_y_mm: float, max_x_mm: float, max_y_mm: float) -> tuple[float, float, float, float]:
        left, top = self.to_screen(min_x_mm, max_y_mm)
        right, bottom = self.to_screen(max_x_mm, min_y_mm)
        return left, top, max(1.0, right - left), max(1.0, bottom - top)
