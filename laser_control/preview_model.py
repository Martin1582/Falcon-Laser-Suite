from __future__ import annotations

from dataclasses import dataclass, field

from laser_control.artwork_import import ArtworkSourceType, RasterImageSource
from laser_control.artwork_transform import ArtworkTransform, transform_paths
from laser_control.gcode_analysis import GCodeSegment
from laser_control.fill_toolpath import FillToolpath
from laser_control.layers import JobLayer
from laser_control.svg_import import Point, Polyline


@dataclass(frozen=True)
class PreviewBounds:
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


@dataclass(frozen=True)
class PreviewPath:
    path_id: str
    path_type: str
    points: Polyline
    order: int
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PreviewArtworkItem:
    item_id: str
    name: str
    source_type: str
    paths: list[Polyline] = field(default_factory=list)
    raster_source: RasterImageSource | None = None
    transform: ArtworkTransform | None = None
    visible: bool = True
    active: bool = True
    selected: bool = False


@dataclass(frozen=True)
class PreviewLayer:
    layer_id: str
    name: str
    layer_type: str
    order: int
    enabled: bool
    visible: bool
    speed_mm_min: int
    power_percent: int
    passes: int
    paths: list[PreviewPath]

    @property
    def should_render(self) -> bool:
        return self.visible and self.enabled


@dataclass(frozen=True)
class PreviewOptions:
    show_artwork: bool = True
    show_bounds: bool = True
    show_work_area: bool = True
    show_head_position: bool = True
    show_gcode_path: bool = False
    show_overscan: bool = True


@dataclass(frozen=True)
class PreviewHeadPosition:
    x_mm: float
    y_mm: float
    source: str


@dataclass(frozen=True)
class JobPreviewModel:
    layers: list[PreviewLayer]
    work_width_mm: float
    work_height_mm: float
    bounds: PreviewBounds | None = None
    start_position: Point | None = None
    estimated_runtime_seconds: float | None = None
    warnings: list[str] = field(default_factory=list)
    raster_sources: list[RasterImageSource] = field(default_factory=list)
    gcode_segments: list[GCodeSegment] = field(default_factory=list)
    head_position: PreviewHeadPosition | None = None
    options: PreviewOptions = field(default_factory=PreviewOptions)
    fill_toolpaths: list[FillToolpath] = field(default_factory=list)
    artwork_items: list[PreviewArtworkItem] = field(default_factory=list)

    @property
    def render_layers(self) -> list[PreviewLayer]:
        return sorted((layer for layer in self.layers if layer.should_render), key=lambda layer: layer.order)


def build_preview_model(
    paths: list[Polyline],
    layers: list[JobLayer],
    work_width_mm: float,
    work_height_mm: float,
    estimated_runtime_seconds: float | None = None,
    warnings: list[str] | None = None,
    raster_sources: list[RasterImageSource] | None = None,
    artwork_transform: ArtworkTransform | None = None,
    gcode_segments: list[GCodeSegment] | None = None,
    head_position: PreviewHeadPosition | None = None,
    options: PreviewOptions | None = None,
    fill_toolpaths: list[FillToolpath] | None = None,
) -> JobPreviewModel:
    render_paths = transform_paths(paths, artwork_transform) if artwork_transform is not None else paths
    fill_items = list(fill_toolpaths or [])
    fill_by_order = {toolpath.layer_order: toolpath for toolpath in fill_items}
    preview_layers: list[PreviewLayer] = []
    for layer in sorted(layers, key=lambda item: item.order):
        metadata = {
            "layer_name": layer.name,
            "layer_type": layer.layer_type.value,
            "speed_mm_min": layer.speed_mm_min,
            "power_percent": layer.power_percent,
            "passes": layer.passes,
        }
        layer_paths: list[PreviewPath] = []
        fill_toolpath = fill_by_order.get(layer.order)
        if layer.uses_fill and fill_toolpath is not None:
            layer_paths.extend(
                PreviewPath(
                    path_id=f"{layer.layer_type.value}:{layer.order}:fill:{index}",
                    path_type="fill",
                    points=list(segment),
                    order=len(layer_paths) + index,
                    metadata={
                        **metadata,
                        "fill_spacing_mm": fill_toolpath.spacing_mm,
                        "fill_angle_deg": fill_toolpath.angle_deg,
                    },
                )
                for index, segment in enumerate(fill_toolpath.segments)
            )
            if fill_toolpath.overscan_enabled:
                layer_paths.extend(
                    PreviewPath(
                        path_id=f"{layer.layer_type.value}:{layer.order}:overscan:{index}",
                        path_type="overscan",
                        points=[
                            segment.entry,
                            segment.engraving_start,
                            segment.engraving_end,
                            segment.exit,
                        ],
                        order=len(layer_paths) + index,
                        metadata={
                            **metadata,
                            "overscan_mm": fill_toolpath.overscan_mm,
                            "additional_distance_mm": segment.additional_distance_mm,
                        },
                    )
                    for index, segment in enumerate(fill_toolpath.overscan_segments)
                )
        if layer.uses_outline:
            outline_offset = len(layer_paths)
            layer_paths.extend(
                PreviewPath(
                    path_id=f"{layer.layer_type.value}:{layer.order}:outline:{index}",
                    path_type="outline",
                    points=list(polyline),
                    order=outline_offset + index,
                    metadata=metadata,
                )
                for index, polyline in enumerate(render_paths)
                if len(polyline) >= 2
            )
        preview_layers.append(
            PreviewLayer(
                layer_id=f"{layer.layer_type.value}:{layer.order}",
                name=layer.name,
                layer_type=layer.layer_type.value,
                order=layer.order,
                enabled=layer.enabled,
                visible=layer.visible,
                speed_mm_min=layer.speed_mm_min,
                power_percent=layer.power_percent,
                passes=layer.passes,
                paths=layer_paths,
            )
        )
    raster_items = list(raster_sources or [])
    return JobPreviewModel(
        layers=preview_layers,
        work_width_mm=max(1.0, work_width_mm),
        work_height_mm=max(1.0, work_height_mm),
        bounds=_combined_bounds(render_paths, raster_items),
        start_position=_first_point(render_paths) or (_first_raster_start(raster_items)),
        estimated_runtime_seconds=estimated_runtime_seconds,
        warnings=list(warnings or []),
        raster_sources=raster_items,
        gcode_segments=list(gcode_segments or []),
        head_position=head_position,
        options=options or PreviewOptions(),
        fill_toolpaths=fill_items,
    )


def build_multi_item_preview_model(
    items: list[PreviewArtworkItem],
    layers: list[JobLayer],
    work_width_mm: float,
    work_height_mm: float,
    estimated_runtime_seconds: float | None = None,
    warnings: list[str] | None = None,
    gcode_segments: list[GCodeSegment] | None = None,
    head_position: PreviewHeadPosition | None = None,
    options: PreviewOptions | None = None,
    fill_toolpaths_by_item: dict[str, list[FillToolpath]] | None = None,
) -> JobPreviewModel:
    visible_items = [item for item in items if item.visible]
    fill_map = fill_toolpaths_by_item or {}
    preview_layers: list[PreviewLayer] = []
    all_paths: list[Polyline] = []
    raster_items: list[RasterImageSource] = []
    for layer in sorted(layers, key=lambda item: item.order):
        layer_paths: list[PreviewPath] = []
        metadata = {
            "layer_name": layer.name,
            "layer_type": layer.layer_type.value,
            "speed_mm_min": layer.speed_mm_min,
            "power_percent": layer.power_percent,
            "passes": layer.passes,
        }
        for artwork_index, item in enumerate(visible_items):
            if item.raster_source is not None:
                if layer.order == sorted(layers, key=lambda entry: entry.order)[0].order:
                    raster_items.append(item.raster_source)
                continue
            if not item.paths:
                # e.g. a project item whose source file could not be reloaded: nothing to draw.
                continue
            render_paths = transform_paths(item.paths, item.transform) if item.transform is not None else item.paths
            all_paths.extend(render_paths)
            fill_items = fill_map.get(item.item_id, [])
            fill_by_order = {toolpath.layer_order: toolpath for toolpath in fill_items}
            fill_toolpath = fill_by_order.get(layer.order)
            if layer.uses_fill and fill_toolpath is not None:
                layer_paths.extend(
                    PreviewPath(
                        path_id=f"{item.item_id}:{layer.order}:fill:{index}",
                        path_type="fill",
                        points=list(segment),
                        order=len(layer_paths) + index,
                        metadata={**metadata, "artwork_id": item.item_id, "artwork_name": item.name},
                    )
                    for index, segment in enumerate(fill_toolpath.segments)
                )
            if layer.uses_outline:
                outline_offset = len(layer_paths)
                layer_paths.extend(
                    PreviewPath(
                        path_id=f"{item.item_id}:{layer.order}:outline:{index}",
                        path_type="outline",
                        points=list(polyline),
                        order=outline_offset + artwork_index * 10000 + index,
                        metadata={**metadata, "artwork_id": item.item_id, "artwork_name": item.name},
                    )
                    for index, polyline in enumerate(render_paths)
                    if len(polyline) >= 2
                )
        preview_layers.append(
            PreviewLayer(
                layer_id=f"{layer.layer_type.value}:{layer.order}",
                name=layer.name,
                layer_type=layer.layer_type.value,
                order=layer.order,
                enabled=layer.enabled,
                visible=layer.visible,
                speed_mm_min=layer.speed_mm_min,
                power_percent=layer.power_percent,
                passes=layer.passes,
                paths=layer_paths,
            )
        )
    return JobPreviewModel(
        layers=preview_layers,
        work_width_mm=max(1.0, work_width_mm),
        work_height_mm=max(1.0, work_height_mm),
        bounds=_combined_bounds(all_paths, raster_items),
        start_position=_first_point(all_paths) or _first_raster_start(raster_items),
        estimated_runtime_seconds=estimated_runtime_seconds,
        warnings=list(warnings or []),
        raster_sources=raster_items,
        gcode_segments=list(gcode_segments or []),
        head_position=head_position,
        options=options or PreviewOptions(),
        fill_toolpaths=[toolpath for group in fill_map.values() for toolpath in group],
        artwork_items=list(items),
    )


def _calculate_bounds(paths: list[Polyline]) -> PreviewBounds | None:
    points = [point for polyline in paths for point in polyline]
    if not points:
        return None
    return PreviewBounds(
        min_x=min(point[0] for point in points),
        min_y=min(point[1] for point in points),
        max_x=max(point[0] for point in points),
        max_y=max(point[1] for point in points),
    )


def _combined_bounds(paths: list[Polyline], raster_sources: list[RasterImageSource]) -> PreviewBounds | None:
    bounds = _calculate_bounds(paths)
    raster_bounds = [
        _source_preview_bounds(source)
        for source in raster_sources
        if source.source_type == ArtworkSourceType.RASTER
    ]
    all_bounds = ([bounds] if bounds is not None else []) + raster_bounds
    if not all_bounds:
        return None
    return PreviewBounds(
        min_x=min(item.min_x for item in all_bounds),
        min_y=min(item.min_y for item in all_bounds),
        max_x=max(item.max_x for item in all_bounds),
        max_y=max(item.max_y for item in all_bounds),
    )


def _first_point(paths: list[Polyline]) -> Point | None:
    for polyline in paths:
        if polyline:
            return polyline[0]
    return None


def _source_preview_bounds(source: RasterImageSource) -> PreviewBounds:
    if source.transform is not None:
        bounds = source.transform.bounds
        return PreviewBounds(bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y)
    return PreviewBounds(
        min_x=source.bounding_box[0],
        min_y=source.bounding_box[1],
        max_x=source.bounding_box[2],
        max_y=source.bounding_box[3],
    )


def _first_raster_start(raster_sources: list[RasterImageSource]) -> Point | None:
    for source in raster_sources:
        bounds = _source_preview_bounds(source)
        return (bounds.min_x, bounds.min_y)
    return None
