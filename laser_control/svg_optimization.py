from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot

from laser_control.artwork_transform import ArtworkBounds
from laser_control.svg_import import Point, Polyline, path_bounds


SHORT_SEGMENT_THRESHOLD_MM = 0.05
HIGH_SEGMENT_COUNT = 10_000
MEDIUM_SEGMENT_COUNT = 2_000


@dataclass(frozen=True)
class SvgVectorAnalysis:
    path_count: int
    closed_path_count: int
    open_path_count: int
    segment_count: int
    short_segment_count: int
    bounds: ArtworkBounds | None
    estimated_gcode_lines: int
    complexity: str
    strongly_segmented: bool
    duplicate_segment_count: int = 0
    probable_filled_shapes: bool = False
    total_segment_length_mm: float = 0.0
    warnings: list[str] = field(default_factory=list)

    @property
    def average_segment_length_mm(self) -> float:
        if self.segment_count <= 0:
            return 0.0
        return self.total_segment_length_mm / self.segment_count


@dataclass(frozen=True)
class SvgOptimizationResult:
    original_analysis: SvgVectorAnalysis
    optimized_analysis: SvgVectorAnalysis
    paths: list[Polyline]
    simplify_enabled: bool = False
    tolerance_mm: float = 0.0
    duplicate_removal_enabled: bool = False

    @property
    def reduced_segments(self) -> int:
        return max(0, self.original_analysis.segment_count - self.optimized_analysis.segment_count)


def analyze_svg_paths(paths: list[Polyline], duplicate_tolerance_mm: float = 0.02) -> SvgVectorAnalysis:
    usable_paths = [list(path) for path in paths if len(path) >= 2]
    segment_lengths = [
        _distance(start, end)
        for path in usable_paths
        for start, end in zip(path, path[1:])
    ]
    segment_count = len(segment_lengths)
    closed_count = sum(1 for path in usable_paths if _is_closed(path))
    open_count = len(usable_paths) - closed_count
    bounds = None
    if usable_paths:
        min_x, min_y, max_x, max_y = path_bounds(usable_paths)
        bounds = ArtworkBounds(min_x, min_y, max_x, max_y)
    short_count = sum(1 for length in segment_lengths if 0.0 < length <= SHORT_SEGMENT_THRESHOLD_MM)
    duplicate_count = count_duplicate_segments(usable_paths, duplicate_tolerance_mm)
    average_length = sum(segment_lengths) / segment_count if segment_count else 0.0
    strongly_segmented = (
        segment_count >= HIGH_SEGMENT_COUNT
        or (segment_count >= MEDIUM_SEGMENT_COUNT and average_length <= 0.15)
        or short_count >= max(100, int(segment_count * 0.25))
    )
    complexity = "hoch" if strongly_segmented or segment_count >= HIGH_SEGMENT_COUNT else (
        "mittel" if segment_count >= MEDIUM_SEGMENT_COUNT or short_count >= 100 else "niedrig"
    )
    probable_filled_shapes = closed_count >= max(8, open_count * 3) and segment_count >= 200
    warnings: list[str] = []
    if strongly_segmented:
        warnings.append(
            "Dieses SVG enthaelt sehr viele kurze Segmente. Eine Konturvereinfachung kann Gravurzeit reduzieren und die Darstellung verbessern."
        )
    if duplicate_count:
        warnings.append(f"Moegliche doppelte Linien erkannt: {duplicate_count}.")
    if probable_filled_shapes:
        warnings.append("Dieses Motiv besteht vermutlich aus geschlossenen Flaechen statt einfachen Gravurlinien.")
    analysis = SvgVectorAnalysis(
        path_count=len(usable_paths),
        closed_path_count=closed_count,
        open_path_count=open_count,
        segment_count=segment_count,
        short_segment_count=short_count,
        bounds=bounds,
        estimated_gcode_lines=5 + segment_count + len(usable_paths) * 3,
        complexity=complexity,
        strongly_segmented=strongly_segmented,
        duplicate_segment_count=duplicate_count,
        probable_filled_shapes=probable_filled_shapes,
        total_segment_length_mm=sum(segment_lengths),
        warnings=warnings,
    )
    return analysis


def optimize_svg_paths(
    paths: list[Polyline],
    simplify_enabled: bool = False,
    tolerance_mm: float = 0.02,
    remove_duplicates: bool = False,
    duplicate_tolerance_mm: float = 0.02,
) -> SvgOptimizationResult:
    original = [list(path) for path in paths]
    optimized = [list(path) for path in original]
    if simplify_enabled:
        optimized = [simplify_polyline(path, tolerance_mm) for path in optimized]
    if remove_duplicates:
        optimized = remove_duplicate_segments(optimized, duplicate_tolerance_mm)
    return SvgOptimizationResult(
        original_analysis=analyze_svg_paths(original, duplicate_tolerance_mm),
        optimized_analysis=analyze_svg_paths(optimized, duplicate_tolerance_mm),
        paths=optimized,
        simplify_enabled=simplify_enabled,
        tolerance_mm=tolerance_mm if simplify_enabled else 0.0,
        duplicate_removal_enabled=remove_duplicates,
    )


def simplify_polyline(path: Polyline, tolerance_mm: float) -> Polyline:
    if len(path) <= 2 or tolerance_mm <= 0:
        return list(path)
    closed = _is_closed(path)
    work = path[:-1] if closed else path
    if len(work) <= 2:
        return list(path)
    simplified = _douglas_peucker(work, tolerance_mm)
    if closed:
        if simplified[0] != simplified[-1]:
            simplified.append(simplified[0])
    return simplified


def count_duplicate_segments(paths: list[Polyline], tolerance_mm: float = 0.02) -> int:
    seen: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    duplicates = 0
    for path in paths:
        for start, end in zip(path, path[1:]):
            key = _segment_key(start, end, tolerance_mm)
            if key in seen:
                duplicates += 1
            else:
                seen.add(key)
    return duplicates


def remove_duplicate_segments(paths: list[Polyline], tolerance_mm: float = 0.02) -> list[Polyline]:
    """Drop segments that were already drawn, keeping the remaining geometry connected.

    Kept segments stay joined in their original polylines, so contours without duplicates come
    back unchanged (closed shapes stay closed and remain usable for fills). A path is only split
    where a duplicate segment is removed.
    """
    seen: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    result: list[Polyline] = []
    for path in paths:
        runs: list[Polyline] = []
        current: Polyline = []
        for start, end in zip(path, path[1:]):
            key = _segment_key(start, end, tolerance_mm)
            if key in seen:
                if len(current) >= 2:
                    runs.append(current)
                current = []
                continue
            seen.add(key)
            if not current:
                current = [start]
            current.append(end)
        if len(current) >= 2:
            runs.append(current)
        # A closed contour cut once: the last run ends where the first run starts - rejoin them.
        if len(runs) > 1 and _is_closed(path) and runs[-1][-1] == runs[0][0]:
            runs[0] = runs.pop() + runs[0][1:]
        result.extend(runs)
    return result


def _douglas_peucker(points: Polyline, tolerance_mm: float) -> Polyline:
    if len(points) <= 2:
        return list(points)
    start = points[0]
    end = points[-1]
    max_distance = -1.0
    split_index = 0
    for index, point in enumerate(points[1:-1], start=1):
        distance = _perpendicular_distance(point, start, end)
        if distance > max_distance:
            max_distance = distance
            split_index = index
    if max_distance <= tolerance_mm:
        return [start, end]
    left = _douglas_peucker(points[: split_index + 1], tolerance_mm)
    right = _douglas_peucker(points[split_index:], tolerance_mm)
    return left[:-1] + right


def _perpendicular_distance(point: Point, line_start: Point, line_end: Point) -> float:
    line_length = _distance(line_start, line_end)
    if line_length == 0:
        return _distance(point, line_start)
    numerator = abs(
        (line_end[1] - line_start[1]) * point[0]
        - (line_end[0] - line_start[0]) * point[1]
        + line_end[0] * line_start[1]
        - line_end[1] * line_start[0]
    )
    return numerator / line_length


def _segment_key(start: Point, end: Point, tolerance_mm: float) -> tuple[tuple[int, int], tuple[int, int]]:
    safe_tolerance = max(0.001, tolerance_mm)
    a = _point_key(start, safe_tolerance)
    b = _point_key(end, safe_tolerance)
    return (a, b) if a <= b else (b, a)


def _point_key(point: Point, tolerance_mm: float) -> tuple[int, int]:
    return round(point[0] / tolerance_mm), round(point[1] / tolerance_mm)


def _is_closed(path: Polyline, tolerance_mm: float = 1e-6) -> bool:
    return len(path) >= 3 and _distance(path[0], path[-1]) <= tolerance_mm


def _distance(start: Point, end: Point) -> float:
    return hypot(end[0] - start[0], end[1] - start[1])
