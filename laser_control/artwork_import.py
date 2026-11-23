from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from laser_control.artwork_transform import ArtworkTransform
from laser_control.svg_import import Polyline, import_svg


class ArtworkSourceType(StrEnum):
    VECTOR = "vector"
    RASTER = "raster"


SUPPORTED_VECTOR_EXTENSIONS = {".svg"}
SUPPORTED_RASTER_EXTENSIONS = {".png", ".jpg", ".jpeg"}
SUPPORTED_ARTWORK_EXTENSIONS = SUPPORTED_VECTOR_EXTENSIONS | SUPPORTED_RASTER_EXTENSIONS


@dataclass(frozen=True)
class ArtworkSource:
    source_id: str
    file_path: str
    file_name: str
    source_type: ArtworkSourceType
    width_mm: float
    height_mm: float
    bounding_box: tuple[float, float, float, float]
    layer_id: str = ""
    import_warnings: list[str] = field(default_factory=list)
    transform: ArtworkTransform | None = None


@dataclass(frozen=True)
class RasterImageSource(ArtworkSource):
    pixel_width: int = 0
    pixel_height: int = 0
    dpi: tuple[float, float] | None = None
    color_mode: str = "unknown"
    has_transparency: bool = False
    grayscale_data: bytes = b""
    raster_resolution_mm: float | None = None


@dataclass(frozen=True)
class VectorArtworkSource(ArtworkSource):
    paths: list[Polyline] = field(default_factory=list)
    viewbox: tuple[float, float, float, float] | None = None
    units: str = "mm"
    transforms: list[str] = field(default_factory=list)


class ArtworkImportService:
    def import_file(self, path: str) -> ArtworkSource:
        source_path = Path(path)
        if not source_path.exists():
            raise ValueError(f"Datei nicht gefunden: {source_path}")
        if not source_path.is_file():
            raise ValueError(f"Keine Datei: {source_path}")

        extension = source_path.suffix.lower()
        if extension in SUPPORTED_VECTOR_EXTENSIONS:
            return self._import_svg(source_path)
        if extension in SUPPORTED_RASTER_EXTENSIONS:
            return self._import_raster(source_path)
        raise ValueError(f"Nicht unterstuetztes Dateiformat: {extension or '<ohne Endung>'}")

    def _import_svg(self, path: Path) -> VectorArtworkSource:
        result = import_svg(str(path))
        return VectorArtworkSource(
            source_id=_source_id(path),
            file_path=str(path),
            file_name=path.name,
            source_type=ArtworkSourceType.VECTOR,
            width_mm=result.width_mm,
            height_mm=result.height_mm,
            bounding_box=(0.0, 0.0, result.width_mm, result.height_mm),
            layer_id="vector",
            paths=result.paths,
        )

    def _import_raster(self, path: Path) -> RasterImageSource:
        Image, UnidentifiedImageError = _load_pillow()

        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                pixel_width, pixel_height = image.size
                if pixel_width <= 0 or pixel_height <= 0:
                    raise ValueError("Rasterbild hat keine gueltige Groesse.")
                warnings: list[str] = []
                dpi = _read_dpi(image.info.get("dpi"))
                width_mm, height_mm = _image_size_mm(pixel_width, pixel_height, dpi)
                if dpi is None:
                    warnings.append("Keine DPI-Angabe gefunden; 96 DPI als Standardgroesse verwendet.")
                if pixel_width * pixel_height > 25_000_000:
                    warnings.append("Sehr grosses Rasterbild; Import und spaetere Rastergravur koennen langsam sein.")
                if image.mode in {"RGBA", "LA"} or ("transparency" in image.info):
                    warnings.append("Transparenz wurde fuer die Vorschau in Graustufen zusammengefuehrt.")
                has_transparency = image.mode in {"RGBA", "LA"} or ("transparency" in image.info)
                color_mode = image.mode
                grayscale = image.convert("L")
                return RasterImageSource(
                    source_id=_source_id(path),
                    file_path=str(path),
                    file_name=path.name,
                    source_type=ArtworkSourceType.RASTER,
                    width_mm=width_mm,
                    height_mm=height_mm,
                    bounding_box=(0.0, 0.0, width_mm, height_mm),
                    layer_id="raster",
                    import_warnings=warnings,
                    pixel_width=pixel_width,
                    pixel_height=pixel_height,
                    dpi=dpi,
                    color_mode=color_mode,
                    has_transparency=has_transparency,
                    grayscale_data=grayscale.tobytes(),
                    raster_resolution_mm=width_mm / pixel_width,
                )
        except UnidentifiedImageError as exc:
            raise ValueError(f"Rasterbild konnte nicht gelesen werden: {path.name}") from exc
        except OSError as exc:
            raise ValueError(f"Rasterbild ist beschaedigt oder nicht lesbar: {path.name}") from exc


def supported_file_filter() -> str:
    return (
        "Unterstuetzte Quellen (*.svg *.png *.jpg *.jpeg);;"
        "SVG-Dateien (*.svg);;"
        "Rasterbilder (*.png *.jpg *.jpeg);;"
        "Alle Dateien (*.*)"
    )


def _load_pillow() -> tuple[Any, type[BaseException]]:
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:  # pragma: no cover - exercised through monkeypatch
        raise ValueError(
            "Rasterimport benoetigt Pillow. Bitte Abhaengigkeiten installieren: "
            "python -m pip install -r requirements.txt"
        ) from exc
    return Image, UnidentifiedImageError


def _source_id(path: Path) -> str:
    return path.stem.lower().replace(" ", "-")


def _read_dpi(raw_dpi: object) -> tuple[float, float] | None:
    if not isinstance(raw_dpi, tuple) or len(raw_dpi) < 2:
        return None
    try:
        x_dpi = float(raw_dpi[0])
        y_dpi = float(raw_dpi[1])
    except (TypeError, ValueError):
        return None
    if x_dpi <= 0 or y_dpi <= 0:
        return None
    return x_dpi, y_dpi


def _image_size_mm(pixel_width: int, pixel_height: int, dpi: tuple[float, float] | None) -> tuple[float, float]:
    x_dpi, y_dpi = dpi or (96.0, 96.0)
    return pixel_width / x_dpi * 25.4, pixel_height / y_dpi * 25.4
