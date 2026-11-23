from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot

from laser_control.artwork_import import ArtworkSource, ArtworkSourceType, RasterImageSource, VectorArtworkSource
from laser_control.artwork_transform import ArtworkBounds
from laser_control.raster_analysis import RasterAnalyzer, RasterQualityAnalysis
from laser_control.svg_bezier_analysis import BezierCurveAnalysis, analyze_svg_beziers
from laser_control.svg_import import Point, Polyline, path_bounds
from laser_control.svg_optimization import analyze_svg_paths


@dataclass(frozen=True)
class GeometryAnalysis:
    source_type: str
    path_count: int = 0
    layer_count: int = 1
    segment_count: int = 0
    node_count: int = 0
    open_contours: int = 0
    closed_contours: int = 0
    islands: int = 0
    holes: int = 0
    self_intersections: int = 0
    duplicate_lines: int = 0
    near_duplicate_lines: int = 0
    short_segments: int = 0
    smallest_detail_mm: float = 0.0
    smallest_radius_mm: float | None = None
    bounds: ArtworkBounds | None = None
    total_area_mm2: float = 0.0
    contour_length_mm: float = 0.0
    estimated_runtime_seconds: float = 0.0
    estimated_gcode_lines: int = 0
    fill_rule: str = "unknown"
    stroke_width_mm: float | None = None
    closed_polygons: int = 0
    polygon_hierarchy: str = "unknown"
    bezier: BezierCurveAnalysis | None = None
    raster: RasterQualityAnalysis | None = None
    quality_score: int = 100
    complexity: str = "Niedrig"
    warnings: list[str] = field(default_factory=list)


class GeometryAnalyzer:
    def analyze_source(self, source: ArtworkSource, speed_mm_min: int = 3000) -> GeometryAnalysis:
        if isinstance(source, VectorArtworkSource):
            return self.analyze_vector(
                source.paths,
                speed_mm_min=speed_mm_min,
                bezier=analyze_svg_beziers(source.file_path),
            )
        if isinstance(source, RasterImageSource):
            return self.analyze_raster(source, speed_mm_min=speed_mm_min)
        return GeometryAnalysis(source_type=str(getattr(source, "source_type", "unknown")))

    def analyze_vector(
        self,
        paths: list[Polyline],
        speed_mm_min: int = 3000,
        bezier: BezierCurveAnalysis | None = None,
    ) -> GeometryAnalysis:
        usable_paths = [list(path) for path in paths if len(path) >= 2]
        svg = analyze_svg_paths(usable_paths)
        lengths = [_distance(a, b) for path in usable_paths for a, b in zip(path, path[1:])]
        contour_length = sum(lengths)
        bounds = svg.bounds
        areas = [_polygon_area(path) for path in usable_paths if _is_closed(path)]
        positive_areas = [abs(area) for area in areas if abs(area) > 1e-9]
        total_area = sum(positive_areas)
        intersections = _count_self_intersections(usable_paths)
        holes = _estimate_holes(usable_paths)
        runtime = contour_length / max(1.0, speed_mm_min) * 60.0
        smallest_detail = min((length for length in lengths if length > 0), default=0.0)
        warnings = list(svg.warnings)
        if intersections:
            warnings.append(f"Selbstueberschneidungen erkannt: {intersections}.")
        if holes:
            warnings.append(f"Moegliche Loecher/Inselhierarchie erkannt: {holes}.")
        if bezier and bezier.curve_count:
            warnings.extend(bezier.warnings)
        quality = _quality_score(svg.segment_count, svg.short_segment_count, svg.duplicate_segment_count, intersections)
        return GeometryAnalysis(
            source_type=ArtworkSourceType.VECTOR.value,
            path_count=svg.path_count,
            segment_count=svg.segment_count,
            node_count=sum(len(path) for path in usable_paths),
            open_contours=svg.open_path_count,
            closed_contours=svg.closed_path_count,
            islands=max(0, svg.closed_path_count - holes),
            holes=holes,
            self_intersections=intersections,
            duplicate_lines=svg.duplicate_segment_count,
            near_duplicate_lines=svg.duplicate_segment_count,
            short_segments=svg.short_segment_count,
            smallest_detail_mm=smallest_detail,
            bounds=bounds,
            total_area_mm2=total_area,
            contour_length_mm=contour_length,
            estimated_runtime_seconds=runtime,
            estimated_gcode_lines=svg.estimated_gcode_lines,
            closed_polygons=svg.closed_path_count,
            polygon_hierarchy="moeglich" if holes else "flach",
            bezier=bezier,
            quality_score=quality,
            complexity=_complexity_label(svg.segment_count, svg.short_segment_count, intersections),
            warnings=warnings,
        )

    def analyze_raster(self, source: RasterImageSource, speed_mm_min: int = 3000) -> GeometryAnalysis:
        bounds = ArtworkBounds(0.0, 0.0, source.width_mm, source.height_mm)
        pixels = source.pixel_width * source.pixel_height
        raster = RasterAnalyzer().analyze(source)
        complexity = "Extrem" if pixels > 10_000_000 else ("Hoch" if pixels > 2_000_000 else "Mittel")
        warnings = list(raster.warnings)
        if pixels > 2_000_000:
            warnings.append("Rasterbild ist gross; Rastergravur kann lange dauern.")
        return GeometryAnalysis(
            source_type=ArtworkSourceType.RASTER.value,
            bounds=bounds,
            node_count=pixels,
            smallest_detail_mm=source.raster_resolution_mm or 0.0,
            estimated_runtime_seconds=pixels / max(1.0, speed_mm_min) * 0.01,
            estimated_gcode_lines=max(1, source.pixel_height),
            raster=raster,
            quality_score=raster.raster_quality_score,
            complexity=complexity,
            warnings=warnings,
        )


def _complexity_label(segment_count: int, short_segments: int, intersections: int) -> str:
    if segment_count >= 25_000 or intersections > 50:
        return "Extrem"
    if segment_count >= 10_000 or short_segments >= 1_000 or intersections:
        return "Hoch"
    if segment_count >= 2_000 or short_segments >= 100:
        return "Mittel"
    return "Niedrig"


def _quality_score(segment_count: int, short_segments: int, duplicates: int, intersections: int) -> int:
    penalty = min(30, segment_count // 2_000) + min(25, short_segments // 100) + min(25, duplicates * 2) + min(30, intersections * 3)
    return max(0, min(100, 100 - penalty))


def _distance(start: Point, end: Point) -> float:
    return hypot(end[0] - start[0], end[1] - start[1])


def _is_closed(path: Polyline, tolerance: float = 1e-6) -> bool:
    return len(path) >= 3 and _distance(path[0], path[-1]) <= tolerance


def _polygon_area(path: Polyline) -> float:
    if not _is_closed(path):
        return 0.0
    return sum(
        path[index][0] * path[index + 1][1] - path[index + 1][0] * path[index][1]
        for index in range(len(path) - 1)
    ) / 2.0


def _estimate_holes(paths: list[Polyline]) -> int:
    closed = [path for path in paths if _is_closed(path)]
    if len(closed) < 2:
        return 0
    boxes = []
    for path in closed:
        min_x, min_y, max_x, max_y = path_bounds([path])
        boxes.append((min_x, min_y, max_x, max_y))
    holes = 0
    for index, box in enumerate(boxes):
        for other_index, other in enumerate(boxes):
            if index == other_index:
                continue
            if box[0] > other[0] and box[1] > other[1] and box[2] < other[2] and box[3] < other[3]:
                holes += 1
                break
    return holes


def _count_self_intersections(paths: list[Polyline]) -> int:
    total = 0
    for path in paths:
        segments = list(zip(path, path[1:]))
        for i, first in enumerate(segments):
            for j, second in enumerate(segments[i + 2 :], start=i + 2):
                if i == 0 and j == len(segments) - 1 and _is_closed(path):
                    continue
                if _segments_intersect(first[0], first[1], second[0], second[1]):
                    total += 1
    return total


def _segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    def orient(p: Point, q: Point, r: Point) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1 = orient(a, b, c)
    o2 = orient(a, b, d)
    o3 = orient(c, d, a)
    o4 = orient(c, d, b)
    return o1 * o2 < 0 and o3 * o4 < 0
