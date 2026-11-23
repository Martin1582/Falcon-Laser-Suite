from laser_control.artwork_transform import ArtworkTransform
from laser_control.gcode import build_layered_polyline_gcode
from laser_control.layers import JobLayer, LayerType
from laser_control.svg_optimization import (
    analyze_svg_paths,
    count_duplicate_segments,
    optimize_svg_paths,
    remove_duplicate_segments,
    simplify_polyline,
)


def test_svg_analysis_counts_paths_segments_and_short_segments() -> None:
    paths = [
        [(0.0, 0.0), (0.01, 0.0), (1.0, 0.0)],
        [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0)],
    ]

    analysis = analyze_svg_paths(paths)

    assert analysis.path_count == 2
    assert analysis.segment_count == 5
    assert analysis.short_segment_count == 1
    assert analysis.open_path_count == 1
    assert analysis.closed_path_count == 1
    assert analysis.bounds is not None
    assert analysis.estimated_gcode_lines > analysis.segment_count


def test_svg_analysis_rates_strongly_segmented_geometry_high() -> None:
    path = [(index * 0.01, 0.0) for index in range(2501)]

    analysis = analyze_svg_paths([path])

    assert analysis.complexity == "hoch"
    assert analysis.strongly_segmented
    assert any("Konturvereinfachung" in warning for warning in analysis.warnings)


def test_douglas_peucker_reduces_points_and_keeps_open_path_open() -> None:
    path = [(0.0, 0.0), (0.5, 0.01), (1.0, 0.0), (2.0, 0.0)]

    simplified = simplify_polyline(path, 0.02)

    assert simplified == [(0.0, 0.0), (2.0, 0.0)]
    assert simplified[0] != simplified[-1]


def test_douglas_peucker_keeps_closed_path_closed() -> None:
    path = [(0.0, 0.0), (0.5, 0.01), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0)]

    simplified = simplify_polyline(path, 0.02)

    assert simplified[0] == simplified[-1]


def test_optimization_does_not_mutate_original_paths() -> None:
    paths = [[(0.0, 0.0), (0.5, 0.01), (1.0, 0.0)]]
    original_copy = [[point for point in path] for path in paths]

    result = optimize_svg_paths(paths, simplify_enabled=True, tolerance_mm=0.02)

    assert paths == original_copy
    assert result.paths != paths
    assert result.reduced_segments > 0


def test_duplicate_segments_are_detected_and_optionally_removed() -> None:
    paths = [
        [(0.0, 0.0), (1.0, 0.0)],
        [(1.0, 0.0), (0.0, 0.0)],
        [(0.0, 1.0), (1.0, 1.0)],
    ]

    assert count_duplicate_segments(paths, 0.02) == 1
    deduped = remove_duplicate_segments(paths, 0.02)

    assert len(deduped) == 2


def test_gcode_uses_optimized_geometry_when_supplied() -> None:
    paths = [[(0.0, 0.0), (0.5, 0.01), (1.0, 0.0), (2.0, 0.0)]]
    optimized = optimize_svg_paths(paths, simplify_enabled=True, tolerance_mm=0.02).paths
    layer = JobLayer("Gravur", LayerType.ENGRAVE, True, True, 1000, 40, 10)

    original_code = build_layered_polyline_gcode(paths, [layer])
    optimized_code = build_layered_polyline_gcode(optimized, [layer])

    assert len(optimized_code.splitlines()) < len(original_code.splitlines())
    assert "G1 X2.00 Y0.00" in optimized_code


def test_transform_is_applied_after_optimization_without_changing_transform() -> None:
    paths = [[(0.0, 0.0), (0.5, 0.01), (1.0, 0.0), (2.0, 0.0)]]
    transform = ArtworkTransform(10.0, 5.0, 2.0, 2.0, 1.0, 4.0, 2.0)
    optimized = optimize_svg_paths(paths, simplify_enabled=True, tolerance_mm=0.02).paths

    from laser_control.artwork_transform import transform_paths

    transformed = transform_paths(optimized, transform)

    assert transform.x_mm == 10.0
    assert transform.scale == 2.0
    assert transformed[0][0] == (10.0, 5.0)


def test_duplicate_removal_keeps_contours_without_duplicates_intact() -> None:
    from laser_control.fill_toolpath import build_fill_toolpath

    rectangle = [[(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0)]]

    deduped = remove_duplicate_segments(rectangle, 0.02)

    assert deduped == rectangle
    fill = build_fill_toolpath(deduped, "Gravur", 10, spacing_mm=1.0)
    assert not fill.unsafe_fill
    assert fill.line_count == build_fill_toolpath(rectangle, "Gravur", 10, spacing_mm=1.0).line_count


def test_duplicate_removal_only_splits_where_a_duplicate_was_removed() -> None:
    paths = [
        [(0.0, 0.0), (1.0, 0.0)],
        [(5.0, 5.0), (0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 1.0)],
    ]

    deduped = remove_duplicate_segments(paths, 0.02)

    assert deduped == [
        [(0.0, 0.0), (1.0, 0.0)],
        [(5.0, 5.0), (0.0, 0.0)],
        [(1.0, 0.0), (2.0, 0.0), (3.0, 1.0)],
    ]


def test_duplicate_removal_rejoins_a_closed_contour_cut_once() -> None:
    shared_edge = [(4.0, 0.0), (4.0, 4.0)]
    square = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0), (0.0, 0.0)]

    deduped = remove_duplicate_segments([shared_edge, square], 0.02)

    assert deduped == [shared_edge, [(4.0, 4.0), (0.0, 4.0), (0.0, 0.0), (4.0, 0.0)]]
