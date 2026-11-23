from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SnapResult:
    x_mm: float
    y_mm: float
    vertical_guide_mm: float | None = None
    horizontal_guide_mm: float | None = None


class ArtworkSnapService:
    def __init__(self, threshold_mm: float = 3.0) -> None:
        if threshold_mm < 0:
            raise ValueError("Snap-Toleranz darf nicht negativ sein.")
        self.threshold_mm = threshold_mm

    def snap(
        self,
        x_mm: float,
        y_mm: float,
        artwork_width_mm: float,
        artwork_height_mm: float,
        workspace_width_mm: float,
        workspace_height_mm: float,
        enabled: bool = True,
    ) -> SnapResult:
        if not enabled:
            return SnapResult(x_mm, y_mm)

        x_targets = (
            (0.0, 0.0),
            ((workspace_width_mm - artwork_width_mm) / 2.0, workspace_width_mm / 2.0),
            (workspace_width_mm - artwork_width_mm, workspace_width_mm),
        )
        y_targets = (
            (0.0, 0.0),
            ((workspace_height_mm - artwork_height_mm) / 2.0, workspace_height_mm / 2.0),
            (workspace_height_mm - artwork_height_mm, workspace_height_mm),
        )
        snapped_x, vertical_guide = self._nearest(x_mm, x_targets)
        snapped_y, horizontal_guide = self._nearest(y_mm, y_targets)
        return SnapResult(snapped_x, snapped_y, vertical_guide, horizontal_guide)

    def _nearest(
        self,
        value: float,
        targets: tuple[tuple[float, float], ...],
    ) -> tuple[float, float | None]:
        target_value, guide = min(targets, key=lambda item: abs(value - item[0]))
        if abs(value - target_value) <= self.threshold_mm:
            return target_value, guide
        return value, None
