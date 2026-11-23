from laser_control.artwork_import import ArtworkSourceType, RasterImageSource, VectorArtworkSource
from laser_control.geometry_analyzer import GeometryAnalyzer
from laser_control.geometry_optimizer import GeometryOptimizationOptions
from laser_control.laser_intelligence_engine import LaserIntelligenceEngine
from laser_control.material_recommendations import falcon_10w_material_recommendation, material_deviation_warnings
from laser_control.motif_classifier import MotifClass, MotifClassifier
from laser_control.raster_analysis import RasterAnalyzer
from laser_control.svg_bezier_analysis import analyze_svg_beziers
from laser_control.toolpath_optimizer import ToolpathOptimizer, falcon_10w_recommendation


def test_geometry_analyzer_reports_vector_metrics_and_quality() -> None:
    paths = [
        [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)],
        [(20.0, 0.0), (20.01, 0.0), (30.0, 0.0)],
    ]

    analysis = GeometryAnalyzer().analyze_vector(paths, speed_mm_min=3000)

    assert analysis.path_count == 2
    assert analysis.segment_count == 5
    assert analysis.node_count == 7
    assert analysis.open_contours == 1
    assert analysis.closed_contours == 1
    assert analysis.short_segments == 1
    assert analysis.contour_length_mm > 0
    assert 0 <= analysis.quality_score <= 100


def test_motif_classifier_detects_raster_and_logo_like_vector() -> None:
    raster_analysis = GeometryAnalyzer().analyze_raster(
        RasterImageSource(
            source_id="photo",
            file_path="photo.jpg",
            file_name="photo.jpg",
            source_type=ArtworkSourceType.RASTER,
            width_mm=20.0,
            height_mm=10.0,
            bounding_box=(0.0, 0.0, 20.0, 10.0),
            pixel_width=200,
            pixel_height=100,
        )
    )
    logo_analysis = GeometryAnalyzer().analyze_vector(
        [[(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 0.0)] for _ in range(3)]
    )

    classifier = MotifClassifier()

    assert classifier.classify(raster_analysis, "photo.jpg").motif_class == MotifClass.RASTER
    assert classifier.classify(logo_analysis, "logo.svg").motif_class == MotifClass.LOGO


def test_laser_intelligence_engine_keeps_original_paths_and_creates_working_copy() -> None:
    paths = [[(0.0, 0.0), (0.5, 0.01), (1.0, 0.0), (2.0, 0.0)]]
    source = VectorArtworkSource(
        source_id="wolf",
        file_path="wolf.svg",
        file_name="wolf.svg",
        source_type=ArtworkSourceType.VECTOR,
        width_mm=20.0,
        height_mm=10.0,
        bounding_box=(0.0, 0.0, 20.0, 10.0),
        paths=paths,
    )
    original = [[point for point in path] for path in paths]

    result = LaserIntelligenceEngine().analyze_source(
        source,
        GeometryOptimizationOptions(simplify_contours=True, simplify_tolerance_mm=0.02),
    )

    assert source.paths == original
    assert result.working_paths != source.paths
    assert result.optimization_result is not None
    assert result.optimization_result.reduced_segments > 0
    assert result.machine_recommendation.speed_mm_min > 0
    assert result.quality.score <= 100


def test_toolpath_optimizer_sorts_near_objects() -> None:
    paths = [
        [(0.0, 0.0), (1.0, 0.0)],
        [(100.0, 0.0), (101.0, 0.0)],
        [(2.0, 0.0), (3.0, 0.0)],
    ]

    ordered = ToolpathOptimizer().sort_paths_nearest_neighbor(paths)

    assert ordered[0] == paths[0]
    assert ordered[1] == paths[2]


def test_falcon_recommendation_reflects_high_complexity() -> None:
    analysis = GeometryAnalyzer().analyze_vector(
        [[(index * 0.01, 0.0) for index in range(3000)]],
        speed_mm_min=5000,
    )
    classification = MotifClassifier().classify(analysis, "wolf.svg")

    recommendation = falcon_10w_recommendation(analysis, classification)

    assert recommendation.speed_mm_min <= 2500
    assert recommendation.overscan_mm >= 2.0
    assert recommendation.line_spacing_mm > 0


def test_svg_bezier_analysis_detects_cubic_and_quadratic(tmp_path) -> None:
    svg = tmp_path / "curves.svg"
    svg.write_text(
        '<svg width="20mm" height="10mm" viewBox="0 0 20 10">'
        '<path d="M1 8 C 2 1, 8 1, 9 8 Q 12 2, 18 8"/>'
        '</svg>',
        encoding="utf-8",
    )

    analysis = analyze_svg_beziers(str(svg))

    assert analysis.cubic_count == 1
    assert analysis.quadratic_count == 1
    assert analysis.curve_count == 2
    assert analysis.estimated_curve_length_mm > 0
    assert analysis.min_curve_radius_mm is not None
    assert analysis.recommended_flattening_tolerance_mm > 0


def test_laser_intelligence_engine_includes_bezier_and_comparison_report(tmp_path) -> None:
    svg = tmp_path / "logo.svg"
    svg.write_text(
        '<svg width="20mm" height="10mm" viewBox="0 0 20 10">'
        '<path d="M1 5 C 3 1, 7 1, 9 5"/>'
        '</svg>',
        encoding="utf-8",
    )
    source = VectorArtworkSource(
        source_id="logo",
        file_path=str(svg),
        file_name="logo.svg",
        source_type=ArtworkSourceType.VECTOR,
        width_mm=20.0,
        height_mm=10.0,
        bounding_box=(0.0, 0.0, 20.0, 10.0),
        paths=[[(0.0, 0.0), (0.5, 0.01), (1.0, 0.0), (2.0, 0.0)]],
    )
    original = [[point for point in path] for path in source.paths]

    result = LaserIntelligenceEngine().analyze_source(
        source,
        GeometryOptimizationOptions(simplify_contours=True, simplify_tolerance_mm=0.02),
        material_name="Kunstleder",
    )

    assert source.paths == original
    assert result.analysis.bezier is not None
    assert result.analysis.bezier.cubic_count == 1
    assert result.comparison_report is not None
    assert result.comparison_report.segment_reduction_percent >= 0
    assert result.material_recommendation is not None
    assert result.material_recommendation.material_name == "Kunstleder"


def test_raster_analysis_scores_dpi_contrast_and_transparency() -> None:
    source = RasterImageSource(
        source_id="photo",
        file_path="photo.png",
        file_name="photo.png",
        source_type=ArtworkSourceType.RASTER,
        width_mm=100.0,
        height_mm=50.0,
        bounding_box=(0.0, 0.0, 100.0, 50.0),
        pixel_width=20,
        pixel_height=10,
        dpi=(96.0, 96.0),
        color_mode="RGBA",
        has_transparency=True,
        grayscale_data=bytes([0, 255] * 100),
        raster_resolution_mm=5.0,
    )

    analysis = RasterAnalyzer().analyze(source)

    assert analysis.dpi == (96.0, 96.0)
    assert analysis.has_transparency
    assert analysis.contrast_score > 50
    assert analysis.recommended_mode in {"grayscale", "dithering"}
    assert any("Transparenz" in warning for warning in analysis.warnings)
    assert any("Bildaufloesung zu gering" in warning for warning in analysis.warnings)


def test_raster_analysis_warns_when_dpi_is_missing() -> None:
    source = RasterImageSource(
        source_id="scan",
        file_path="scan.jpg",
        file_name="scan.jpg",
        source_type=ArtworkSourceType.RASTER,
        width_mm=20.0,
        height_mm=10.0,
        bounding_box=(0.0, 0.0, 20.0, 10.0),
        pixel_width=200,
        pixel_height=100,
        dpi=None,
        grayscale_data=bytes([120] * 20_000),
        raster_resolution_mm=0.1,
    )

    analysis = RasterAnalyzer().analyze(source)

    assert analysis.raster_quality_score < 100
    assert any("DPI unbekannt" in warning for warning in analysis.warnings)
    assert any("kontrastarm" in warning for warning in analysis.warnings)


def test_material_recommendation_table_and_deviation_warnings() -> None:
    recommendation = falcon_10w_material_recommendation("Sperrholz 3 mm")
    warnings = material_deviation_warnings("Sperrholz 3 mm", 6000, 10, 2)

    assert recommendation is not None
    assert recommendation.engraving_speed_mm_min > 0
    assert recommendation.fill_spacing_mm > 0
    assert any("Startwert" in warning for warning in warnings)
    assert any("Geschwindigkeit" in warning for warning in warnings)
