from dataclasses import dataclass
from enum import StrEnum

from laser_control.gcode import CUT_MODE
from laser_control.models import MaterialProfile


class LayerType(StrEnum):
    ENGRAVE = "Gravur"
    CUT = "Schnitt"
    MARK = "Markierung"
    HELPER = "Hilfsebene"


class LayerMode(StrEnum):
    OUTLINE = "Kontur"
    FILL = "Fuellung"
    OUTLINE_AND_FILL = "Kontur + Fuellung"


class OverscanMode(StrEnum):
    AUTOMATIC = "Automatisch"
    MANUAL = "Manuell"


@dataclass
class JobLayer:
    name: str
    layer_type: LayerType
    visible: bool
    enabled: bool
    speed_mm_min: int
    power_percent: int
    order: int
    passes: int = 1
    mode: LayerMode = LayerMode.OUTLINE
    fill_spacing_mm: float = 0.08
    fill_angle_deg: int = 0
    overscan_enabled: bool = True
    overscan_mode: OverscanMode = OverscanMode.AUTOMATIC
    overscan_mm: float = 6.0

    @property
    def is_output_layer(self) -> bool:
        return self.enabled and self.layer_type != LayerType.HELPER

    @property
    def uses_outline(self) -> bool:
        return self.mode in {LayerMode.OUTLINE, LayerMode.OUTLINE_AND_FILL}

    @property
    def uses_fill(self) -> bool:
        return self.mode in {LayerMode.FILL, LayerMode.OUTLINE_AND_FILL}


def build_default_layers(profile: MaterialProfile, operation_mode: str) -> list[JobLayer]:
    active_type = LayerType.CUT if operation_mode == CUT_MODE else LayerType.ENGRAVE
    return [
        JobLayer("Gravur", LayerType.ENGRAVE, visible=True, enabled=active_type == LayerType.ENGRAVE, speed_mm_min=profile.speed_mm_min, power_percent=profile.power_percent, order=10, passes=profile.passes),
        JobLayer("Schnitt", LayerType.CUT, visible=True, enabled=active_type == LayerType.CUT, speed_mm_min=profile.speed_mm_min, power_percent=profile.power_percent, order=20, passes=profile.passes),
        JobLayer("Markierung", LayerType.MARK, visible=True, enabled=False, speed_mm_min=profile.speed_mm_min, power_percent=max(1, min(100, profile.power_percent // 2)), order=30, passes=1),
        JobLayer("Hilfsebene", LayerType.HELPER, visible=True, enabled=False, speed_mm_min=profile.speed_mm_min, power_percent=0, order=40, passes=1),
    ]


def active_output_layers(layers: list[JobLayer]) -> list[JobLayer]:
    return sorted((layer for layer in layers if layer.is_output_layer), key=lambda layer: layer.order)


def layer_validation_warnings(layers: list[JobLayer]) -> list[str]:
    warnings: list[str] = []
    output_layers = active_output_layers(layers)
    if not output_layers:
        warnings.append("Keine aktiven Ausgabelayer vorhanden.")
    for layer in output_layers:
        if layer.speed_mm_min <= 0:
            warnings.append(f"Layer '{layer.name}' hat keine gueltige Geschwindigkeit.")
        if layer.power_percent <= 0 or layer.power_percent > 100:
            warnings.append(f"Layer '{layer.name}' hat keine gueltige Laserleistung.")
        if layer.passes <= 0:
            warnings.append(f"Layer '{layer.name}' hat keine gueltige Durchgangszahl.")
        if layer.uses_fill and layer.fill_spacing_mm <= 0:
            warnings.append(f"Layer '{layer.name}' hat keinen gueltigen Fuellabstand.")
        if layer.uses_fill and layer.fill_angle_deg not in {0, 45, 90}:
            warnings.append(f"Layer '{layer.name}' hat keinen unterstuetzten Fuellwinkel.")
        if layer.uses_fill and layer.overscan_enabled and layer.overscan_mode == OverscanMode.MANUAL and layer.overscan_mm <= 0:
            warnings.append(f"Layer '{layer.name}' hat keinen gueltigen manuellen Overscan.")
    return warnings


def layer_to_dict(layer: JobLayer) -> dict:
    return {
        "name": layer.name,
        "type": layer.layer_type.value,
        "visible": layer.visible,
        "enabled": layer.enabled,
        "speed_mm_min": layer.speed_mm_min,
        "power_percent": layer.power_percent,
        "order": layer.order,
        "passes": layer.passes,
        "mode": layer.mode.value,
        "fill_spacing_mm": layer.fill_spacing_mm,
        "fill_angle_deg": layer.fill_angle_deg,
        "overscan_enabled": layer.overscan_enabled,
        "overscan_mode": layer.overscan_mode.value,
        "overscan_mm": layer.overscan_mm,
    }


def layer_from_dict(data: dict) -> JobLayer:
    layer_type = LayerType(data.get("type", LayerType.HELPER.value))
    return JobLayer(
        name=str(data.get("name", layer_type.value)),
        layer_type=layer_type,
        visible=bool(data.get("visible", True)),
        enabled=bool(data.get("enabled", False)),
        speed_mm_min=int(data.get("speed_mm_min", 1000)),
        power_percent=int(data.get("power_percent", 0)),
        order=int(data.get("order", 99)),
        passes=int(data.get("passes", 1)),
        mode=LayerMode(data.get("mode", LayerMode.OUTLINE.value)),
        fill_spacing_mm=float(data.get("fill_spacing_mm", 0.08)),
        fill_angle_deg=int(data.get("fill_angle_deg", 0)),
        overscan_enabled=bool(data.get("overscan_enabled", True)),
        overscan_mode=OverscanMode(data.get("overscan_mode", OverscanMode.AUTOMATIC.value)),
        overscan_mm=float(data.get("overscan_mm", 6.0)),
    )
