from __future__ import annotations

from dataclasses import dataclass

from laser_control.artwork_import import ArtworkSource, VectorArtworkSource
from laser_control.geometry_analyzer import GeometryAnalysis, GeometryAnalyzer
from laser_control.geometry_optimizer import GeometryOptimizationOptions, GeometryOptimizer
from laser_control.intelligence_report import OriginalWorkingCopyReport, build_original_working_copy_report
from laser_control.material_recommendations import FalconMaterialRecommendation, falcon_10w_material_recommendation
from laser_control.motif_classifier import MotifClassification, MotifClassifier
from laser_control.quality_analyzer import QualityAnalyzer, QualityReport
from laser_control.svg_import import Polyline
from laser_control.svg_optimization import SvgOptimizationResult
from laser_control.toolpath_optimizer import FalconMachineRecommendation, ToolpathOptimizer, ToolpathPlan, falcon_10w_recommendation


@dataclass(frozen=True)
class LaserIntelligenceResult:
    analysis: GeometryAnalysis
    classification: MotifClassification
    quality: QualityReport
    machine_recommendation: FalconMachineRecommendation
    material_recommendation: FalconMaterialRecommendation | None
    toolpath_plan: ToolpathPlan | None
    optimization_result: SvgOptimizationResult | None
    comparison_report: OriginalWorkingCopyReport | None
    working_paths: list[Polyline]

    @property
    def summary(self) -> str:
        return (
            f"Laser Intelligence {self.quality.score}% | "
            f"{self.classification.motif_class.value} | "
            f"Komplexitaet {self.analysis.complexity} | "
            f"{self.analysis.segment_count} Segmente"
        )


class LaserIntelligenceEngine:
    def __init__(
        self,
        geometry_analyzer: GeometryAnalyzer | None = None,
        motif_classifier: MotifClassifier | None = None,
        geometry_optimizer: GeometryOptimizer | None = None,
        toolpath_optimizer: ToolpathOptimizer | None = None,
        quality_analyzer: QualityAnalyzer | None = None,
    ) -> None:
        self.geometry_analyzer = geometry_analyzer or GeometryAnalyzer()
        self.motif_classifier = motif_classifier or MotifClassifier()
        self.geometry_optimizer = geometry_optimizer or GeometryOptimizer()
        self.toolpath_optimizer = toolpath_optimizer or ToolpathOptimizer()
        self.quality_analyzer = quality_analyzer or QualityAnalyzer()

    def analyze_source(
        self,
        source: ArtworkSource,
        optimization_options: GeometryOptimizationOptions | None = None,
        speed_mm_min: int = 3000,
        material_name: str = "",
    ) -> LaserIntelligenceResult:
        analysis = self.geometry_analyzer.analyze_source(source, speed_mm_min=speed_mm_min)
        classification = self.motif_classifier.classify(analysis, getattr(source, "file_name", ""))
        quality = self.quality_analyzer.evaluate(analysis, classification)
        recommendation = falcon_10w_recommendation(analysis, classification)
        material_recommendation = falcon_10w_material_recommendation(material_name)
        optimization_result = None
        working_paths: list[Polyline] = []
        toolpath_plan = None
        comparison_report = None
        if isinstance(source, VectorArtworkSource):
            original_paths = [list(path) for path in source.paths]
            options = optimization_options or GeometryOptimizationOptions()
            optimization_result = self.geometry_optimizer.optimize(original_paths, options)
            working_paths = optimization_result.paths
            toolpath_plan = self.toolpath_optimizer.plan(working_paths, classification)
            working_analysis = self.geometry_analyzer.analyze_vector(working_paths, speed_mm_min=speed_mm_min)
            comparison_report = build_original_working_copy_report(analysis, working_analysis, optimization_result)
        return LaserIntelligenceResult(
            analysis=analysis,
            classification=classification,
            quality=quality,
            machine_recommendation=recommendation,
            material_recommendation=material_recommendation,
            toolpath_plan=toolpath_plan,
            optimization_result=optimization_result,
            comparison_report=comparison_report,
            working_paths=working_paths,
        )
