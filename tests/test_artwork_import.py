import pytest

from laser_control.artwork_import import ArtworkImportService, ArtworkSourceType, RasterImageSource, VectorArtworkSource


def test_artwork_import_detects_svg_vector_source(tmp_path) -> None:
    svg = tmp_path / "shape.svg"
    svg.write_text(
        '<svg width="20mm" height="10mm" viewBox="0 0 20 10"><path d="M0 0 L20 10"/></svg>',
        encoding="utf-8",
    )

    source = ArtworkImportService().import_file(str(svg))

    assert isinstance(source, VectorArtworkSource)
    assert source.source_type == ArtworkSourceType.VECTOR
    assert source.width_mm == 20.0
    assert source.paths


def test_svg_import_converts_y_axis_once_and_preserves_visual_orientation(tmp_path) -> None:
    svg = tmp_path / "asymmetric.svg"
    svg.write_text(
        '<svg width="20mm" height="10mm" viewBox="0 0 20 10"><path d="M2 1 L18 1 L2 9"/></svg>',
        encoding="utf-8",
    )

    source = ArtworkImportService().import_file(str(svg))

    assert isinstance(source, VectorArtworkSource)
    assert source.paths[0] == [(2.0, 9.0), (18.0, 9.0), (2.0, 1.0)]


def test_artwork_import_loads_png_as_raster_source(tmp_path) -> None:
    image_module = pytest.importorskip("PIL.Image")
    image_path = tmp_path / "photo.png"
    image = image_module.new("RGB", (96, 48), color=(128, 128, 128))
    image.save(image_path, dpi=(96, 96))

    source = ArtworkImportService().import_file(str(image_path))

    assert isinstance(source, RasterImageSource)
    assert source.source_type == ArtworkSourceType.RASTER
    assert source.pixel_width == 96
    assert source.pixel_height == 48
    assert round(source.width_mm, 1) == 25.4
    assert source.grayscale_data


def test_png_import_keeps_original_pixel_order_without_mirroring(tmp_path) -> None:
    image_module = pytest.importorskip("PIL.Image")
    image_path = tmp_path / "asymmetric.png"
    image = image_module.new("L", (2, 2))
    image.putdata([10, 20, 30, 40])
    image.save(image_path, dpi=(96, 96))

    source = ArtworkImportService().import_file(str(image_path))

    assert isinstance(source, RasterImageSource)
    assert list(source.grayscale_data) == [10, 20, 30, 40]


def test_artwork_import_loads_jpg_as_raster_source(tmp_path) -> None:
    image_module = pytest.importorskip("PIL.Image")
    image_path = tmp_path / "photo.jpg"
    image = image_module.new("RGB", (32, 16), color=(255, 255, 255))
    image.save(image_path)

    source = ArtworkImportService().import_file(str(image_path))

    assert isinstance(source, RasterImageSource)
    assert source.dpi is None
    assert any("DPI" in warning for warning in source.import_warnings)


def test_artwork_import_rejects_unknown_format(tmp_path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("hello", encoding="utf-8")

    with pytest.raises(ValueError, match="Nicht unterstuetztes Dateiformat"):
        ArtworkImportService().import_file(str(path))


def test_artwork_import_rejects_broken_raster(tmp_path) -> None:
    pytest.importorskip("PIL.Image")
    path = tmp_path / "broken.png"
    path.write_bytes(b"not a png")

    with pytest.raises(ValueError, match="Rasterbild"):
        ArtworkImportService().import_file(str(path))


def test_artwork_import_reports_missing_pillow_with_install_hint(monkeypatch, tmp_path) -> None:
    path = tmp_path / "photo.png"
    path.write_bytes(b"placeholder")

    def missing_pillow() -> tuple[object, type[BaseException]]:
        raise ValueError(
            "Rasterimport benoetigt Pillow. Bitte Abhaengigkeiten installieren: "
            "python -m pip install -r requirements.txt"
        )

    monkeypatch.setattr("laser_control.artwork_import._load_pillow", missing_pillow)

    with pytest.raises(ValueError) as exc_info:
        ArtworkImportService().import_file(str(path))

    message = str(exc_info.value)
    assert "Pillow" in message
    assert "pip install -r requirements.txt" in message
