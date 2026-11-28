"""Projekt plus Motiv-Caches als Qt-freie Einheit.

Das Fenster haelt hier seinen Projektzustand. Entfernen und Zuruecksetzen
laufen ausschliesslich ueber diese Klasse, damit kein Cache vergessen wird.
"""

from dataclasses import dataclass, field, fields
from typing import TYPE_CHECKING

from laser_control.project import ArtworkItem, LaserProject

if TYPE_CHECKING:
    from laser_control.artwork_import import RasterImageSource
    from laser_control.fill_toolpath import FillToolpath
    from laser_control.laser_intelligence_engine import LaserIntelligenceResult
    from laser_control.svg_optimization import SvgOptimizationResult, SvgVectorAnalysis


@dataclass
class ArtworkItemCaches:
    """Alle Caches, die pro Motiv-ID gefuehrt werden.

    Die Felder sind absichtlich veraenderbar: bestehender Code weist Dicts neu zu.
    """

    sources: dict[str, object] = field(default_factory=dict)
    vector_paths: dict[str, list] = field(default_factory=dict)
    optimized_vector_paths: dict[str, list] = field(default_factory=dict)
    svg_analyses: dict[str, "SvgVectorAnalysis"] = field(default_factory=dict)
    svg_optimization_results: dict[str, "SvgOptimizationResult"] = field(default_factory=dict)
    original_rasters: dict[str, "RasterImageSource"] = field(default_factory=dict)
    intelligence_results: dict[str, "LaserIntelligenceResult"] = field(default_factory=dict)
    fill_toolpaths_by_item: dict[str, list["FillToolpath"]] = field(default_factory=dict)

    def discard(self, item_id: str) -> None:
        """Entfernt die Eintraege einer ID; fehlende Eintraege sind kein Fehler."""
        for cache in self._all():
            cache.pop(item_id, None)

    def clear(self) -> None:
        """Leert alle Caches, auch den Sammelschluessel "legacy"."""
        for cache in self._all():
            cache.clear()

    def _all(self) -> list[dict]:
        # Ueber die Felder iterieren, damit ein neuer Cache nicht vergessen werden kann.
        return [getattr(self, f.name) for f in fields(self)]


@dataclass(frozen=True)
class ItemRemoval:
    removed_item: ArtworkItem
    removed_index: int
    next_selected_id: str | None


class ProjectWorkspace:
    """Haelt das aktuelle Projekt und die zugehoerigen Motiv-Caches."""

    def __init__(self, project: LaserProject) -> None:
        self.project = project
        self.caches = ArtworkItemCaches()

    def find_item(self, item_id: str) -> ArtworkItem | None:
        return next((item for item in self.project.items if item.item_id == item_id), None)

    def remove_item(self, item_id: str) -> ItemRemoval:
        """Entfernt Motiv und Caches. Unbekannte ID: KeyError, Zustand unveraendert."""
        items = self.project.items
        index = next((i for i, item in enumerate(items) if item.item_id == item_id), None)
        if index is None:
            raise KeyError(item_id)
        removed = items.pop(index)
        self.caches.discard(item_id)
        # Nachfolger: das Element an derselben Stelle, sonst das neue letzte.
        if index < len(items):
            next_id = items[index].item_id
        else:
            next_id = items[-1].item_id if items else None
        return ItemRemoval(removed, index, next_id)

    def reset(self, material_width_mm: float, material_height_mm: float, material_name: str = "") -> None:
        """Neues, leeres Projekt; die alte Instanz bleibt unveraendert."""
        self.replace_project(LaserProject(material_width_mm, material_height_mm, material_name))

    def replace_project(self, project: LaserProject) -> None:
        """Setzt das Projekt und verwirft alle Caches (sie gehoeren zu den alten IDs)."""
        self.project = project
        self.caches.clear()
