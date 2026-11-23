from laser_control.layers import JobLayer, LayerType
from laser_control.artwork_import import ArtworkSourceType, RasterImageSource
from laser_control.artwork_transform import ArtworkTransform
from laser_control.gcode_analysis import GCodeSegment
from laser_control.preview_model import PreviewHeadPosition, PreviewOptions, build_preview_model
from laser_control.preview_model import PreviewArtworkItem, build_multi_item_preview_model


def test_preview_model_calculates_bounds_and_start_position() -> None:
    model = build_preview_model(
        [[(10.0, 5.0), (20.0, 15.0)], [(2.0, 8.0), (4.0, 12.0)]],
        [_layer("Gravur", LayerType.ENGRAVE, 10)],
        100.0,
        80.0,
    )

    assert model.bounds is not None
    assert model.bounds.min_x == 2.0
    assert model.bounds.max_y == 15.0
    assert model.start_position == (10.0, 5.0)


def test_preview_model_orders_layers_and_filters_render_layers() -> None:
    layers = [
        _layer("Hilfsebene", LayerType.HELPER, 40, enabled=False, visible=True),
        _layer("Schnitt", LayerType.CUT, 20, enabled=True, visible=True),
        _layer("Gravur", LayerType.ENGRAVE, 10, enabled=True, visible=False),
    ]

    model = build_preview_model([[(0.0, 0.0), (1.0, 1.0)]], layers, 100.0, 80.0)

    assert [layer.name for layer in model.layers] == ["Gravur", "Schnitt", "Hilfsebene"]
    assert [layer.name for layer in model.render_layers] == ["Schnitt"]


def test_preview_model_keeps_same_paths_separate_per_layer() -> None:
    paths = [[(0.0, 0.0), (10.0, 0.0)]]
    layers = [
        _layer("Gravur", LayerType.ENGRAVE, 10),
        _layer("Schnitt", LayerType.CUT, 20),
    ]

    model = build_preview_model(paths, layers, 100.0, 80.0)

    assert len(model.render_layers) == 2
    assert model.render_layers[0].paths[0].path_id != model.render_layers[1].paths[0].path_id
    assert model.render_layers[0].paths[0].points == model.render_layers[1].paths[0].points


def test_preview_model_accepts_empty_paths() -> None:
    model = build_preview_model([], [_layer("Gravur", LayerType.ENGRAVE, 10)], 100.0, 80.0)

    assert model.bounds is None
    assert model.start_position is None
    assert model.render_layers[0].paths == []


def test_preview_model_includes_raster_source_bounds() -> None:
    raster = RasterImageSource(
        source_id="image",
        file_path="image.png",
        file_name="image.png",
        source_type=ArtworkSourceType.RASTER,
        width_mm=30.0,
        height_mm=20.0,
        bounding_box=(0.0, 0.0, 30.0, 20.0),
        pixel_width=30,
        pixel_height=20,
        grayscale_data=bytes([128] * 600),
    )

    model = build_preview_model([], [_layer("Raster", LayerType.ENGRAVE, 10)], 100.0, 80.0, raster_sources=[raster])

    assert model.bounds is not None
    assert model.bounds.width_mm == 30.0
    assert model.bounds.height_mm == 20.0
    assert model.raster_sources == [raster]


def test_preview_model_uses_vector_transform() -> None:
    transform = ArtworkTransform(
        x_mm=10.0,
        y_mm=20.0,
        scale=2.0,
        original_width_mm=5.0,
        original_height_mm=5.0,
        current_width_mm=10.0,
        current_height_mm=10.0,
    )

    model = build_preview_model(
        [[(0.0, 0.0), (5.0, 5.0)]],
        [_layer("Gravur", LayerType.ENGRAVE, 10)],
        100.0,
        80.0,
        artwork_transform=transform,
    )

    assert model.bounds is not None
    assert model.bounds.min_x == 10.0
    assert model.bounds.min_y == 20.0
    assert model.bounds.max_x == 20.0
    assert model.bounds.max_y == 30.0
    assert model.start_position == (10.0, 20.0)
    assert model.render_layers[0].paths[0].points == [(10.0, 20.0), (20.0, 30.0)]


def test_multi_item_preview_model_combines_visible_item_bounds() -> None:
    items = [
        PreviewArtworkItem(
            item_id="logo",
            name="Logo.svg",
            source_type="svg",
            paths=[[(0.0, 0.0), (20.0, 10.0)]],
            transform=ArtworkTransform(5.0, 5.0, 1.0, 20.0, 10.0, 20.0, 10.0),
        ),
        PreviewArtworkItem(
            item_id="text",
            name="Text.svg",
            source_type="svg",
            paths=[[(0.0, 0.0), (40.0, 8.0)]],
            transform=ArtworkTransform(45.0, 8.0, 1.0, 40.0, 8.0, 40.0, 8.0),
        ),
    ]

    model = build_multi_item_preview_model(items, [_layer("Gravur", LayerType.ENGRAVE, 10)], 100.0, 30.0)

    assert model.bounds is not None
    assert model.bounds.min_x == 5.0
    assert model.bounds.max_x == 85.0
    assert len(model.render_layers[0].paths) == 2


def test_preview_model_uses_raster_transform_bounds() -> None:
    transform = ArtworkTransform(
        x_mm=5.0,
        y_mm=6.0,
        scale=0.5,
        original_width_mm=40.0,
        original_height_mm=20.0,
        current_width_mm=20.0,
        current_height_mm=10.0,
    )
    raster = RasterImageSource(
        source_id="image",
        file_path="image.jpg",
        file_name="image.jpg",
        source_type=ArtworkSourceType.RASTER,
        width_mm=40.0,
        height_mm=20.0,
        bounding_box=(0.0, 0.0, 40.0, 20.0),
        pixel_width=40,
        pixel_height=20,
        grayscale_data=bytes([128] * 800),
        transform=transform,
    )

    model = build_preview_model([], [_layer("Raster", LayerType.ENGRAVE, 10)], 100.0, 80.0, raster_sources=[raster])

    assert model.bounds is not None
    assert model.bounds.min_x == 5.0
    assert model.bounds.min_y == 6.0
    assert model.bounds.width_mm == 20.0
    assert model.bounds.height_mm == 10.0


def test_preview_model_carries_visibility_head_and_gcode_overlay_data() -> None:
    options = PreviewOptions(
        show_artwork=False,
        show_bounds=True,
        show_work_area=True,
        show_head_position=True,
        show_gcode_path=True,
        show_overscan=False,
    )
    segment = GCodeSegment(0.0, 0.0, 10.0, 10.0, rapid=False, laser_power=300.0)
    head = PreviewHeadPosition(3.0, 4.0, "WPos")

    model = build_preview_model(
        [[(0.0, 0.0), (1.0, 1.0)]],
        [_layer("Gravur", LayerType.ENGRAVE, 10)],
        100.0,
        80.0,
        gcode_segments=[segment],
        head_position=head,
        options=options,
    )

    assert not model.options.show_artwork
    assert model.options.show_gcode_path
    assert not model.options.show_overscan
    assert model.gcode_segments == [segment]
    assert model.head_position == head


def _layer(
    name: str,
    layer_type: LayerType,
    order: int,
    enabled: bool = True,
    visible: bool = True,
) -> JobLayer:
    return JobLayer(
        name=name,
        layer_type=layer_type,
        visible=visible,
        enabled=enabled,
        speed_mm_min=1000,
        power_percent=50,
        order=order,
        passes=1,
    )
