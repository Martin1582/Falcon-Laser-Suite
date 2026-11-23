from __future__ import annotations

from dataclasses import dataclass

from laser_control.svg_import import Polyline
from laser_control.svg_optimization import SvgOptimizationResult, optimize_svg_paths


@dataclass(frozen=True)
class GeometryOptimizationOptions:
    simplify_contours: bool = False
    simplify_tolerance_mm: float = 0.02
    merge_short_segments: bool = False
    short_segment_threshold_mm: float = 0.05
    remove_duplicate_lines: bool = False
    duplicate_tolerance_mm: float = 0.02
    validate_closed_contours: bool = True
    reduce_intermediate_points: bool = False


class GeometryOptimizer:
    def optimize(self, paths: list[Polyline], options: GeometryOptimizationOptions) -> SvgOptimizationResult:
        simplify = options.simplify_contours or options.merge_short_segments or options.reduce_intermediate_points
        tolerance = options.simplify_tolerance_mm
        if options.merge_short_segments:
            tolerance = max(tolerance, options.short_segment_threshold_mm)
        return optimize_svg_paths(
            paths,
            simplify_enabled=simplify,
            tolerance_mm=tolerance,
            remove_duplicates=options.remove_duplicate_lines,
            duplicate_tolerance_mm=options.duplicate_tolerance_mm,
        )
