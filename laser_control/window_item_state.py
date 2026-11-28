"""Bindet die historischen Zustandsnamen des Fensters an den ProjectWorkspace.

Viele Mixins lesen und schreiben `self.laser_project` und die `self._item_*`-Caches
direkt, teils per Neuzuweisung (`self._item_optimized_vector_paths = {}`). Statt alle
Aufrufstellen umzuschreiben, leiten diese Properties auf `self.project_workspace` um.
So gibt es genau eine Zustandsquelle, und Entfernen/Zuruecksetzen kann keinen Cache
vergessen.

Solange `project_workspace` noch nicht existiert, wirft der Getter `AttributeError`;
`hasattr(self, "laser_project")`-Guards verhalten sich damit wie vorher.
"""

from laser_control.project import LaserProject


def _cache_property(field_name: str) -> property:
    """Property fuer ein Feld von `project_workspace.caches` (Getter und Setter)."""

    def getter(self) -> dict:
        return getattr(self.project_workspace.caches, field_name)

    def setter(self, value: dict) -> None:
        setattr(self.project_workspace.caches, field_name, value)

    return property(getter, setter, doc=f"project_workspace.caches.{field_name}")


class ItemStateBindingMixin:
    """Mixin fuer LaserControlWindow: Projekt und Motiv-Caches liegen im ProjectWorkspace."""

    @property
    def laser_project(self) -> LaserProject:
        return self.project_workspace.project

    @laser_project.setter
    def laser_project(self, project: LaserProject) -> None:
        self.project_workspace.project = project

    _item_sources = _cache_property("sources")
    _item_vector_paths = _cache_property("vector_paths")
    _item_optimized_vector_paths = _cache_property("optimized_vector_paths")
    _item_svg_analyses = _cache_property("svg_analyses")
    _item_svg_optimization_results = _cache_property("svg_optimization_results")
    _item_original_rasters = _cache_property("original_rasters")
    _item_intelligence_results = _cache_property("intelligence_results")
    _fill_toolpaths_by_item = _cache_property("fill_toolpaths_by_item")
