from dataclasses import replace

from PIL import Image
from PySide6.QtWidgets import QApplication

from laser_control.artwork_import import ArtworkImportService, RasterImageSource
from laser_control.work_area_preview import raster_source_image


def _import_png(tmp_path, image: Image.Image) -> RasterImageSource:
    path = tmp_path / "motiv.png"
    image.save(path, dpi=(72, 72))
    source = ArtworkImportService().import_file(str(path))
    assert isinstance(source, RasterImageSource)
    return source


def test_raster_preview_image_reads_rows_without_padding(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    # Width 3 is not divisible by 4: with Qt's default 4-byte row alignment row 1 would start at
    # byte 4 instead of byte 3 and show the wrong pixels.
    image = Image.new("L", (3, 2))
    image.putdata([10, 20, 30, 40, 50, 60])
    source = _import_png(tmp_path, image)

    preview = raster_source_image(source)

    assert preview is not None
    assert (preview.width(), preview.height()) == (3, 2)
    assert [preview.pixelColor(x, 1).red() for x in range(3)] == [40, 50, 60]


def test_raster_preview_image_rejects_inconsistent_pixel_data(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    source = _import_png(tmp_path, Image.new("L", (5, 4), 128))

    assert raster_source_image(replace(source, grayscale_data=source.grayscale_data[:-1])) is None
    assert raster_source_image(replace(source, grayscale_data=b"")) is None


def test_importing_transparent_png_with_odd_width_does_not_crash_preview(monkeypatch, tmp_path) -> None:
    from laser_control.pyside_app import LaserControlWindow

    # Same shape as the crashing user file: RGBA with transparency, 1546 px wide (1546 % 4 == 2).
    png = tmp_path / "logo.png"
    Image.new("RGBA", (1546, 1683), (0, 0, 0, 0)).save(png, dpi=(72, 72))
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getOpenFileName", lambda *_a, **_k: (str(png), ""))
    app = QApplication.instance() or QApplication([])
    window = LaserControlWindow()
    window.resize(1200, 800)
    window.show()

    window._import_svg()
    window.preview.repaint()  # crashed with an access violation before the fix
    app.processEvents()

    assert window.laser_project.items[0].is_raster
    window.close()
