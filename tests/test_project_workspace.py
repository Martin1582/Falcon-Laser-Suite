import ast
from pathlib import Path

import pytest

from laser_control.artwork_transform import ArtworkTransform
from laser_control.project import ArtworkItem, LaserProject
from laser_control.project_workspace import ProjectWorkspace


def _item(item_id: str) -> ArtworkItem:
    return ArtworkItem(item_id, f"name-{item_id}", "svg", ArtworkTransform(0.0, 0.0, 1.0, 10.0, 10.0, 10.0, 10.0))


def _workspace(*ids: str) -> ProjectWorkspace:
    workspace = ProjectWorkspace(LaserProject(300.0, 200.0, "Holz", [_item(i) for i in ids]))
    for item_id in ids:
        _fill_caches(workspace, item_id)
    return workspace


def _fill_caches(workspace: ProjectWorkspace, item_id: str) -> None:
    caches = workspace.caches
    for cache in (
        caches.sources,
        caches.vector_paths,
        caches.optimized_vector_paths,
        caches.svg_analyses,
        caches.svg_optimization_results,
        caches.original_rasters,
        caches.intelligence_results,
        caches.fill_toolpaths_by_item,
    ):
        cache[item_id] = f"value-{item_id}"


def _all_caches(workspace: ProjectWorkspace) -> list[dict]:
    return workspace.caches._all()


def test_remove_middle_item_selects_following_item():
    workspace = _workspace("a", "b", "c")
    removal = workspace.remove_item("b")
    assert removal.next_selected_id == "c"
    assert removal.removed_index == 1
    assert removal.removed_item.item_id == "b"
    assert [i.item_id for i in workspace.project.items] == ["a", "c"]


def test_remove_last_item_selects_previous_item():
    workspace = _workspace("a", "b", "c")
    assert workspace.remove_item("c").next_selected_id == "b"


def test_remove_only_item_leaves_empty_project():
    workspace = _workspace("a")
    removal = workspace.remove_item("a")
    assert removal.next_selected_id is None
    assert workspace.project.items == []


def test_remove_discards_all_caches_of_item_only():
    workspace = _workspace("a", "b")
    workspace.caches.fill_toolpaths_by_item["legacy"] = "legacy-value"
    workspace.remove_item("a")
    for cache in _all_caches(workspace):
        assert "a" not in cache
    for cache in _all_caches(workspace):
        assert cache["b"] == "value-b"
    assert workspace.caches.fill_toolpaths_by_item["legacy"] == "legacy-value"


def test_remove_item_without_cache_entries_is_tolerated():
    workspace = _workspace("a")
    workspace.project.items.append(_item("missing"))
    removal = workspace.remove_item("missing")
    assert removal.removed_item.item_id == "missing"
    assert [i.item_id for i in workspace.project.items] == ["a"]


def test_remove_unknown_item_raises_and_keeps_state():
    workspace = _workspace("a", "b")
    with pytest.raises(KeyError):
        workspace.remove_item("nope")
    assert [i.item_id for i in workspace.project.items] == ["a", "b"]
    for cache in _all_caches(workspace):
        assert set(cache) == {"a", "b"}


def test_reset_creates_new_empty_project():
    workspace = _workspace("a")
    workspace.caches.fill_toolpaths_by_item["legacy"] = "x"
    old = workspace.project
    workspace.reset(400.0, 300.0, "Acryl")
    assert workspace.project is not old
    assert (workspace.project.material_width_mm, workspace.project.material_height_mm) == (400.0, 300.0)
    assert workspace.project.material_name == "Acryl"
    assert workspace.project.items == []
    assert [i.item_id for i in old.items] == ["a"]
    assert (old.material_width_mm, old.material_name) == (300.0, "Holz")
    assert all(cache == {} for cache in _all_caches(workspace))


def test_replace_project_clears_caches():
    workspace = _workspace("a")
    new_project = LaserProject(100.0, 100.0, items=[_item("z")])
    workspace.replace_project(new_project)
    assert workspace.project is new_project
    assert all(cache == {} for cache in _all_caches(workspace))


def test_project_workspace_has_no_qt_dependency():
    source = Path(__file__).resolve().parents[1] / "laser_control" / "project_workspace.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
    assert not [m for m in modules if m.split(".")[0] in {"PySide6", "PyQt5", "PyQt6"}]
