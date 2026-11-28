# Plan: Motiv entfernen und Neues Projekt

Stand: 2026-11-28, Basis `master` @ `f116591`. Technische Basis bleibt Python 3.12 / PySide6.

## 1. Ziel und Abgrenzung

**Ziel**

1. **Motiv entfernen:** Das in der Objektliste (`object_table`, Spalten S/A/Name/Typ) ausgewählte
   Motiv wird samt aller zugehörigen Caches aus dem Projekt gelöscht. Danach sind Auswahl,
   Vorschau, G-Code, Preflight und Buttons konsistent, auch im Leerzustand.
2. **Neues Projekt:** Projektzustand auf Ausgangszustand zurücksetzen, ohne App-Neustart.

**Nicht Teil des Auftrags**

- Undo/Redo, Mehrfachauswahl, Ungespeichert-Tracking (siehe Designentscheidung D3).
- Änderungen am Projektdateiformat (`PROJECT_VERSION` bleibt 3). Es gibt keine Datenbank-
  Änderung, daher keine Migration und keinen `sql`-Schritt.
- Maschinenverbindung, Maschinenprofil, Materialprofile, Material-DB, Job-Historie,
  Einstellungen und Theme werden von beiden Funktionen nicht angetastet.
- Weitere Aufteilung von `window_artwork.py` / `pyside_app.py` (nur als Folgeaufgabe, Abschnitt 7).
- Kein `network`-Anteil.

## 2. Ausgangslage (im Code verifiziert)

| Thema | Befund |
|---|---|
| Objektliste | `pyside_app.py:337-355` baut `object_table` (SingleSelection, Spalte 2 editierbar). Handler `_refresh_object_table`, `_object_table_item_changed`, `_object_table_selection_changed` in `window_artwork.py:341-397`. Kein Entfernen, keine Tastenkürzel. |
| Projekt-Buttons | `pyside_app.py:336-361`: „Datei importieren", Objektliste, Leerzustand `project_empty_state`, „Speichern", „Laden". Kein „Neues Projekt". |
| Hinweistexte | `window_job.py:330` und `workflow_controller.py:364` raten bereits zu „... deaktivieren oder entfernen". |
| Projektmodell | `project.py`: `LaserProject(material_width_mm, material_height_mm, material_name, items)`, `ArtworkItem(item_id, ..., visible, active, source_data)`. Qt-frei. |
| Item-Caches (alle `dict[item_id, ...]`, `pyside_app.py:100-112`) | `_item_sources`, `_item_vector_paths`, `_item_optimized_vector_paths`, `_item_svg_analyses`, `_item_svg_optimization_results`, `_item_original_rasters`, `_item_intelligence_results`, `_fill_toolpaths_by_item` (enthält zusätzlich den Schlüssel `"legacy"`). |
| Legacy-Zustand des gewählten Motivs | `artwork_source`, `artwork_transform`, `imported_file`, `imported_paths`, `original_imported_paths`, `raster_sources`, `original_raster_source`, `autofit_result`, `fill_toolpaths`, `svg_analysis`, `svg_optimization_result`, `svg_optimized_paths`, `laser_intelligence_result`, `selected_artwork_item_id`. |
| Projektzustand außerhalb `LaserProject` | `current_project_path`, `material_measurement`, `material_points`, `material_point_a/b`, `_generated_job_name`, `_parameter_source`, `last_prepared_job`, Layer im `layer_panel`, Platzierungs-Controls (`_svg_placement_data`, wird mitgespeichert). |
| `_select_artwork_item(None)` | `window_artwork.py:268-279`, wird derzeit **nirgends** aufgerufen (Preview-Signal ist `Signal(str)`). Setzt nur einen Teil des Legacy-Zustands zurück: `imported_file`, `svg_*`, `laser_intelligence_result`, `autofit_result`, `fill_toolpaths` bleiben stehen. |
| `_load_project` | `window_project.py:74-86` setzt Legacy-Felder und vier Caches zurück, **vergisst aber** `_item_optimized_vector_paths`, `_item_svg_analyses`, `_item_svg_optimization_results`, `_item_intelligence_results` (veraltete Einträge alter Item-IDs bleiben liegen). Platzierungs-Restore `window_project.py:188-202` ist ein eigenständiger Block, der sich als Helfer wiederverwenden lässt. |
| `_refresh_object_table` | Setzt bei fehlender Auswahl keine `clearSelection()`; nach dem Schrumpfen der Zeilen könnte eine alte Tabellen-Selektion sichtbar bleiben. |
| Testmatrix | `_generate_test_matrix` (`window_job.py:604-624`) leert Legacy-Felder, **nicht** `laser_project.items`, und setzt `_generated_job_name = "Testmatrix"`. `_refresh_gcode` (`window_job.py:406`) setzt `_generated_job_name = None` und erzeugt den G-Code neu. Auch das bestehende Aktiv-Häkchen ruft `_refresh_gcode` und verwirft damit eine Testmatrix (vgl. Test `test_pyside_generated_test_matrix_can_be_framed_and_started`). |
| Laufender Job | `_start_job` übergibt `gcode` als String-Kopie an den Worker (`window_job.py:139, 195-208`); der Hardware-Job selbst ist von späteren UI-Änderungen unabhängig. Aber: „Als gut/Problem speichern" (`_record_job_result`) liest den **aktuellen** Editor-G-Code, Vorschau/Frame zeigen dann etwas anderes als das, was läuft. Worker-Status: `worker_busy` (`window_machine.py:283-321`), Phasen `RUNNING/PAUSED/STOPPING` (`machine_state.py`). Buttons werden über `_sync_machine_action_buttons` aktualisiert; `_sync_position_indicator` (250-ms-Timer) ruft es bei Phasenwechsel. |
| Größen | `window_artwork.py` 911 Zeilen (über Richtwert), `pyside_app.py` 956 Zeilen, `_build_sidebar` ~240 Zeilen (Methode über Richtwert), `tests/test_pyside_units.py` ~1780 Zeilen. |
| Tests/CI | `pytest`, Qt offscreen über `tests/conftest.py` (isolierter Benutzerspeicher). Kein `pytest-qt` installiert, nicht nachrüsten. CI: flake8 `E9,F63,F7,F82` + pytest auf Python 3.12. |
| UI-Texte | Projektweit Umschrift ohne Umlaute („loeschen", „Uebernehmen"), kein `tr()`. Neue Texte folgen dieser Konvention. |

## 3. Designentscheidungen

### D1 Qt-freie Einheit `ProjectWorkspace` (neu, `laser_control/project_workspace.py`)

Kapselt **das Projekt plus alle Item-Caches** und ist die einzige Stelle, die beim Entfernen
und Zurücksetzen Caches anfasst. Kein Qt-Import.

```python
@dataclass
class ArtworkItemCaches:
    sources: dict[str, object]
    vector_paths: dict[str, list]
    optimized_vector_paths: dict[str, list]
    svg_analyses: dict[str, SvgVectorAnalysis]
    svg_optimization_results: dict[str, SvgOptimizationResult]
    original_rasters: dict[str, RasterImageSource]
    intelligence_results: dict[str, LaserIntelligenceResult]
    fill_toolpaths_by_item: dict[str, list[FillToolpath]]
    def discard(self, item_id: str) -> None: ...   # tolerant, wenn Eintraege fehlen
    def clear(self) -> None: ...                    # inkl. Schluessel "legacy"

@dataclass(frozen=True)
class ItemRemoval:
    removed_item: ArtworkItem
    removed_index: int
    next_selected_id: str | None

class ProjectWorkspace:
    project: LaserProject
    caches: ArtworkItemCaches
    def find_item(self, item_id: str) -> ArtworkItem | None: ...
    def remove_item(self, item_id: str) -> ItemRemoval: ...   # KeyError bei unbekannter ID, dann unveraendert
    def reset(self, material_width_mm: float, material_height_mm: float, material_name: str = "") -> None: ...
    def replace_project(self, project: LaserProject) -> None: ...  # fuer _load_project: Projekt setzen, Caches leeren
```

- Nachfolger-Auswahl: Element, das nach dem Entfernen an `removed_index` steht (das folgende),
  sonst das neue letzte (das vorherige), sonst `None`.
- `reset` erzeugt ein **neues** `LaserProject` (keine Mutation der alten Instanz).
- Größe: Ziel < 120 Zeilen, ≤ 6 öffentliche Methoden.
- Typ-Importe nur aus Qt-freien Modulen (`project`, `svg_optimization`, `artwork_import`,
  `fill_toolpath`, `laser_intelligence_engine`); vorab prüfen, dass diese kein PySide6 importieren,
  sonst `TYPE_CHECKING`-Import.

### D2 Bestehende Zugriffe bleiben, Zustand zieht um (Property-Bindung)

Rund 40 Stellen in mehreren Mixins lesen/schreiben `self._item_*` und `self.laser_project`,
teils per Neuzuweisung (`self._item_optimized_vector_paths = {}` in `window_artwork.py:150-152`,
`self._fill_toolpaths_by_item = {}` in `window_job.py`). Statt alle Aufrufstellen umzuschreiben,
bekommt das Fenster einen kleinen Mixin `ItemStateBindingMixin`
(`laser_control/window_item_state.py`) mit Properties (Getter **und** Setter) für
`laser_project` und die acht Cache-Namen, die auf `self.project_workspace` umleiten.

Nutzen: eine einzige Zustandsquelle, Neuzuweisungen landen automatisch im Workspace, kein Diff
in den übrigen Mixins, Entfernen/Zurücksetzen kann keinen Cache mehr vergessen. Der Fehler in
`_load_project` (vier vergessene Caches) verschwindet nebenbei über `replace_project`.

### D3 Bestätigung statt Ungespeichert-Tracking

- **Entfernen:** immer bestätigen (es gibt kein Undo), Text mit Motivname, Standardknopf „Nein".
- **Neues Projekt:** bestätigen, wenn `_has_loaded_motif()` wahr ist (Motive vorhanden oder
  erzeugter Job/Testmatrix). Leeres Projekt: ohne Rückfrage.
- **Kein Dirty-Tracking in diesem Auftrag.** Begründung: Änderungen entstehen an vielen Stellen
  (Transformation, Vorschau-Drag, Pfeiltasten, Layer, Namen, Häkchen, Material, Einmessen); ein
  verlässliches Flag bräuchte Hooks in all diesen Pfaden und eigene Tests. Halb implementiert
  wäre es gefährlicher als eine ehrliche, immer erscheinende Rückfrage. Folgeaufgabe F3.

### D4 Sperre während Job/Maschinenaktion

Beide Funktionen sind gesperrt, solange `worker_busy` gilt oder die Maschinenphase
`RUNNING`, `PAUSED` oder `STOPPING` ist. Begründung: Der laufende Hardware-Job wäre zwar nicht
betroffen (G-Code-Kopie), aber Job-Ergebnis-Speicherung, Vorschau, Frame und Preflight würden
danach einen anderen Job beschreiben als den laufenden. Umsetzung doppelt:
Buttons deaktiviert (mit Tooltip-Grund) **und** Prüfung im Handler (Lücke zwischen
`_run_worker` und Phasenwechsel). Ob Import/Laden ebenfalls gesperrt werden sollen: offene Frage Q4.

### D5 Entf-Taste in der Objektliste: ja

`QShortcut(QKeySequence.StandardKey.Delete)` mit `Qt.ShortcutContext.WidgetShortcut` direkt am
`object_table`. Damit greift die Taste nicht, während eine Namenszelle editiert wird (Editor
hat den Fokus) und nicht in der Vorschau/G-Code-Editor. Gleicher Ablauf inkl. Bestätigung wie
der Button. Nutzen: erwartetes Verhalten einer Objektliste, kein Risiko durch Bestätigung.

### D6 UI-Teil als eigenes Panel nach bestehendem Muster

Wie `MachinePanel`/`WorkspaceScanPanel`: neues Widget `ProjectEditActions`
(`laser_control/project_edit_actions.py`) mit Buttons und Signalen, plus Dialog-Helfer
`confirm_remove_artwork(...)`/`confirm_new_project(...)` und `install_delete_shortcut(...)`.
Das Fenster verdrahtet nur. So bleibt `pyside_app.py` fast unverändert, und `designer` und
`coder` arbeiten in getrennten Dateien.

### D7 Fensterseite dünn: neuer Mixin `ProjectLifecycleMixin`

`laser_control/window_project_lifecycle.py`, Ziel < 200 Zeilen, Methoden < 40 Zeilen:
`_build_project_edit_controls`, `_remove_selected_artwork`, `_new_project`,
`_project_edit_locked`, `_sync_project_edit_actions`, `_clear_selected_artwork_state`,
`_reset_project_side_state` (Einmessung, Pfad, Parameterquelle, `last_prepared_job`).
`window_artwork.py` wird dabei kürzer, nicht länger.

### D8 Wiederverwendung statt Duplikat

| Duplikat heute | Lösung |
|---|---|
| Legacy-Reset in `_select_artwork_item(None)`, `_load_project`, `_generate_test_matrix` | `_clear_selected_artwork_state()` (vollständig, inkl. `svg_*`, `laser_intelligence_result`, `imported_file`, `autofit_result`, `fill_toolpaths`). Genutzt von `_select_artwork_item(None)`, `_load_project`, `_new_project`. `_generate_test_matrix` bleibt unverändert (setzt bewusst nur Teilmenge, `imported_file` bleibt dort erhalten). |
| Cache-Reset in `_load_project` | `project_workspace.replace_project(...)` |
| Platzierungs-Restore in `_load_project` (`window_project.py:188-202`) | Extrahiert als `ProjectMixin._restore_svg_placement(placement: dict)`; `_new_project` ruft ihn mit einer beim Start gezogenen Kopie von `_svg_placement_data()` (`self._default_svg_placement`, am Ende von `__init__`). Keine doppelten Default-Konstanten. |

## 4. Schritte

| Nr. | Agent | Inhalt | Dateien (nur diese) | Abhängig von |
|---|---|---|---|---|
| 1 | `coder` | Qt-freie Einheit + Unit-Tests | neu: `laser_control/project_workspace.py`, `tests/test_project_workspace.py` | – |
| 2 | `designer` | Panel, Dialoge, Shortcut-Helfer + Widget-Tests | neu: `laser_control/project_edit_actions.py`, `tests/test_project_edit_actions.py` | – |
| 3 | `coder` | Zustand umziehen (D2), `_load_project` entdoppeln (D8) | neu: `laser_control/window_item_state.py`; geändert: `laser_control/pyside_app.py`, `laser_control/window_project.py` | 1 |
| 4 | `coder` | Fenster-Integration Entfernen/Neu (D4, D5, D7) + UI-Tests | neu: `laser_control/window_project_lifecycle.py`, `tests/test_pyside_project_lifecycle.py`; geändert: `laser_control/pyside_app.py`, `laser_control/window_artwork.py`, `laser_control/window_machine.py` | 2, 3 |
| 5 | `designer` | Doku | `README.md`, `CHANGELOG.md` | 2 (Texte) |
| 6 | `qa` | Review + Abnahme | keine Änderungen | 1-5 |

### Schritt 1 – `ProjectWorkspace` (coder)

1. API gemäß D1 umsetzen; Docstrings deutsch, Bezeichner englisch.
2. `remove_item`: Index ermitteln, Item entfernen, `caches.discard`, `ItemRemoval` zurückgeben.
   Unbekannte ID → `KeyError`, Zustand unverändert.
3. `reset`/`replace_project`: neues bzw. übergebenes Projekt setzen, `caches.clear()`.
4. Tests siehe Abschnitt 6.1.

### Schritt 2 – `ProjectEditActions` (designer)

1. `class ProjectEditActions(QWidget)`:
   - Buttons `new_project_button` („Neues Projekt"), `remove_artwork_button` („Motiv entfernen"),
     `objectName`s `projectNewButton`, `projectRemoveArtworkButton`, Mindesthöhe 32 wie `_button`.
   - Signale `new_project_requested = Signal()`, `remove_artwork_requested = Signal()`.
   - `set_remove_state(enabled: bool, reason: str)`, `set_new_project_state(enabled: bool, reason: str)`:
     setzen Enabled + Tooltip (Grund bei deaktiviert, sonst Standardtooltip).
   - Barrierefreiheit: `setAccessibleName`, Tooltip von „Motiv entfernen" nennt die Taste „Entf".
2. `confirm_remove_artwork(parent, item_name: str, discards_generated_job: bool) -> bool` und
   `confirm_new_project(parent, item_count: int, discards_generated_job: bool) -> bool`:
   `QMessageBox.question`, Ja/Nein, Default **Nein**. Textvorschläge (Platzhalter statt
   zusammengesetzter Sätze):
   - Entfernen: Titel „Motiv entfernen", Text „Motiv \"{name}\" aus dem Projekt entfernen?\n\nDie Originaldatei bleibt erhalten. Dieser Schritt kann nicht rueckgaengig gemacht werden." Bei `discards_generated_job` Zusatzzeile „Die erzeugte Testmatrix wird dabei verworfen." (abhängig von Q3).
   - Neu: Titel „Neues Projekt", Text „Aktuelles Projekt verwerfen und ein neues Projekt beginnen?\n\n{count} Motive werden aus der Arbeitsflaeche entfernt. Nicht gespeicherte Aenderungen gehen verloren.\nMaschine, Material- und Maschinenprofile bleiben unveraendert."
3. `install_delete_shortcut(widget: QWidget, handler: Callable[[], None]) -> QShortcut` gemäß D5.
4. Platzierung im Panel: eine Zeile mit beiden Buttons; das Panel kommt im Fenster direkt unter
   die Objektliste (Schritt 4). „Neues Projekt" sitzt optisch bei „Speichern/Laden"? –
   designer entscheidet die Anordnung innerhalb des Panels; Einfügepunkt im Fenster bleibt einer.
5. Keine Fachlogik, keine Fensterzugriffe. Tests siehe 6.2.

### Schritt 3 – Zustand umziehen (coder)

1. `window_item_state.py`: `ItemStateBindingMixin` mit Properties für `laser_project`,
   `_item_sources`, `_item_vector_paths`, `_item_optimized_vector_paths`, `_item_svg_analyses`,
   `_item_svg_optimization_results`, `_item_original_rasters`, `_item_intelligence_results`,
   `_fill_toolpaths_by_item` → `self.project_workspace.project` bzw. `.caches.<feld>`.
   Getter und Setter, kurz und ohne Logik.
2. `pyside_app.py`:
   - Mixin in die Basisliste vor `QMainWindow` aufnehmen.
   - In `__init__` die Zeilen 97 und 100-106, 112 durch
     `self.project_workspace = ProjectWorkspace(LaserProject(300.0, 200.0))` ersetzen
     (vor `_build_layout`). Typannotationen wandern in `ArtworkItemCaches`.
3. `window_project.py`:
   - `_load_project`: Blöcke 74-86 ersetzen durch `self._clear_selected_artwork_state()`
     (kommt in Schritt 4; bis dahin Übergangsweise bestehende Zuweisungen behalten **oder**
     Schritt 3 und 4 in einem coder-Lauf nacheinander erledigen), danach `imported_paths`,
     `original_imported_paths`, `imported_file` aus den Daten setzen, dann
     `self.project_workspace.replace_project(laser_project_from_dict(...))`.
     Reihenfolge so wählen, dass das bisherige Ladeverhalten identisch bleibt.
   - Platzierungs-Restore 188-202 als `_restore_svg_placement(placement: dict)` extrahieren
     (inkl. `_transform_ui_updating`-Klammer und Kommentar), `_load_project` ruft ihn auf.
4. Nach Schritt 3 müssen alle bestehenden Tests unverändert grün sein (reiner Umbau).

### Schritt 4 – Fenster-Integration (coder)

1. `window_project_lifecycle.py` (`ProjectLifecycleMixin`), in `pyside_app.py` in die Mixin-Liste.
2. `_build_project_edit_controls(layout)`: `ProjectEditActions` erzeugen, Signale verbinden,
   `install_delete_shortcut(self.object_table, self._remove_selected_artwork)`; in
   `pyside_app._build_sidebar` genau **ein** Aufruf direkt nach `project_layout.addWidget(self.object_table)`.
3. `_project_edit_locked() -> bool`: `worker_busy` oder Phase in `{RUNNING, PAUSED, STOPPING}`.
4. `_sync_project_edit_actions()`: Entfernen aktiv nur bei existierendem ausgewähltem Item und
   nicht gesperrt; Neu aktiv, wenn nicht gesperrt. Tooltip-Gründe: „Zuerst ein Motiv in der
   Objektliste auswaehlen." / „Waehrend ein Job oder eine Maschinenaktion laeuft nicht moeglich."
   Aufrufe: am Ende von `_refresh_object_table` (`window_artwork.py`) und am Ende von
   `_sync_machine_action_buttons` (`window_machine.py`, eine Zeile, mit `hasattr`-Guard wie dort üblich).
5. `_clear_selected_artwork_state()`: setzt den kompletten Legacy-Zustand (Tabelle Abschnitt 2)
   und `selected_artwork_item_id` zurück. `_select_artwork_item(None)` in `window_artwork.py`
   ruft ihn statt der eigenen Zuweisungen auf und setzt zusätzlich `svg_size_label` auf
   „Motiv: keine Datei" sowie `preview_position_label` auf „Motivposition: --".
6. `_refresh_object_table`: wenn kein Item ausgewählt ist, `self.object_table.clearSelection()`
   (innerhalb der `_object_list_updating`-Klammer).
7. `_remove_selected_artwork()`:
   1. Item holen; `None` → return. Gesperrt → Log + return (kein Dialog).
   2. `confirm_remove_artwork(...)`; Nein → return.
   3. `removal = self.project_workspace.remove_item(item.item_id)`.
   4. `_select_artwork_item(removal.next_selected_id)` (oder `None`).
   5. War das entfernte Item ein Raster: `_sync_layers_from_controls(preserve_states=True)`,
      damit der Layername „Raster: …" verschwindet bzw. zum neuen Raster passt.
   6. `_refresh_gcode()`, `_draw_preview()`, `_update_assistant_panel()`, `_sync_machine_action_buttons()`.
   7. Log: „Motiv entfernt: {name} ({n} Motive im Projekt)"; bei verworfener Testmatrix
      zusätzlich „Testmatrix verworfen." (Q3).
   Methode < 40 Zeilen, ggf. Schritt 5-6 in `_refresh_after_project_change()` auslagern
   (wird auch von `_new_project` genutzt).
8. `_new_project()`:
   1. Gesperrt → Log + return. `_has_loaded_motif()` → `confirm_new_project(...)`; Nein → return.
   2. `self.project_workspace.reset(work_width, work_height, profile_name)`.
   3. `_clear_selected_artwork_state()`.
   4. `_reset_project_side_state()`: `current_project_path=None`, `material_measurement=None`,
      `material_points={1..4: None}`, `material_point_a/b=None`, `_update_material_measurement_label()`,
      `_parameter_source="Materialprofil/Default"`, `last_prepared_job=None`.
   5. `_restore_svg_placement(self._default_svg_placement)` (Umfang abhängig von Q1).
   6. `_sync_layers_from_controls(preserve_states=False)`.
   7. `_refresh_object_table()`, `_refresh_after_project_change()` (setzt über `_refresh_gcode`
      auch `_generated_job_name=None` und erzeugt den Rahmen-Starter-G-Code).
   8. Log „Neues Projekt angelegt."
   Nicht angefasst: `app_controller`/Controller, `connection_mode`, `serial_port`,
   `machine_profile`, `profile_service`/Materialprofile, `material_db_records`, `job_history`,
   Theme, Diagnose-Log, Arbeitsbereich und Material-/Modus-Auswahl (vorbehaltlich Q1).
9. Fenstertitel bleibt „Laser Control" (kein Projektname im Titel heute; nicht einführen).
10. Tests siehe 6.3.

### Schritt 5 – Doku (designer)

- `README.md`, Abschnitt „Current Features": Punkte „remove the selected artwork from the object
  list (button or Delete key, with confirmation)" und „start a new project without restarting
  (machine connection and profiles stay untouched)". In „Code Structure" die neuen Module
  `project_workspace`, `project_edit_actions`, `window_project_lifecycle`, `window_item_state` ergänzen.
- `CHANGELOG.md`, `## Unreleased` → `### Added` (zwei Einträge) und `### Fixed`
  („Loading a project no longer keeps stale SVG/analysis caches of previous items").
- Auffälligkeit, nicht beheben: `Unreleased` enthält zweimal `### Changed`.

## 5. Parallelität

| Phase | Parallel erlaubt | Begründung |
|---|---|---|
| A | Schritt 1 (`coder`) ‖ Schritt 2 (`designer`) | disjunkte neue Dateien |
| B | Schritt 3+4 (`coder`, nacheinander in einem Lauf) ‖ Schritt 5 (`designer`) | Schritt 3/4 ändern `pyside_app.py`, `window_*.py`, Tests; Schritt 5 nur `README.md`/`CHANGELOG.md` |
| C | Schritt 6 (`qa`) | nach allem |

- `designer` ändert in Phase B **nicht** `project_edit_actions.py`; Befunde dazu gehen nach qa
  zurück an `designer`.
- Kein Agent startet einen Server; Tests laufen offscreen.
- Keine Datei wird von zwei Schritten geändert, außer `pyside_app.py` in 3 und 4 – beide beim
  selben `coder`-Lauf.

## 6. Erforderliche Tests

### 6.1 Unit-Tests `tests/test_project_workspace.py` (ohne Qt)

| Test | Erwartung |
|---|---|
| `test_remove_middle_item_selects_following_item` | 3 Items, mittleres entfernt → `next_selected_id` = vorher drittes, `removed_index` = 1 |
| `test_remove_last_item_selects_previous_item` | letztes entfernt → vorheriges |
| `test_remove_only_item_leaves_empty_project` | `next_selected_id is None`, `project.items == []` |
| `test_remove_discards_all_caches_of_item_only` | alle 8 Cache-Dicts ohne die ID, Einträge anderer Items unverändert |
| `test_remove_item_without_cache_entries_is_tolerated` | Item ohne Quelle (fehlende Datei) → kein Fehler |
| `test_remove_unknown_item_raises_and_keeps_state` | `KeyError`, Items und Caches unverändert |
| `test_reset_creates_new_empty_project` | neue Instanz, Maße/Name übernommen, alte Instanz unverändert, alle Caches leer inkl. `"legacy"` |
| `test_replace_project_clears_caches` | Projekt gesetzt, Caches leer |
| `test_project_workspace_has_no_qt_dependency` | `ast`-Prüfung der Imports von `project_workspace.py`: kein `PySide6` |

### 6.2 Widget-Tests `tests/test_project_edit_actions.py` (designer)

- Buttons existieren mit `objectName`, Signale feuern bei Klick (`QTest.mouseClick`).
- `set_remove_state(False, grund)` → deaktiviert, Tooltip = Grund; `True` → Standardtooltip.
- `confirm_*` geben bei gepatchtem `QMessageBox.question` Ja/Nein korrekt zurück, Default-Button Nein.
- `install_delete_shortcut`: Entf auf dem Ziel-Widget ruft den Handler; Entf auf einem anderen Widget nicht.

### 6.3 UI-Tests `tests/test_pyside_project_lifecycle.py` (coder)

Bestätigungen per `monkeypatch` auf `laser_control.window_project_lifecycle.confirm_*`,
Dateien über `tmp_path`, Muster wie in `tests/test_pyside_units.py`.

| Test | Erwartung |
|---|---|
| `test_remove_button_follows_selection` | ohne Motiv deaktiviert; nach Import aktiv; nach Entfernen des letzten deaktiviert |
| `test_remove_selected_item_selects_next_and_updates_outputs` | 3 SVGs mit unterschiedlichen Offsets; mittleres entfernt → 2 Zeilen, Auswahl = folgendes Item, `svg_offset_x` = dessen X, `get_transformed_bounds()` ohne das entfernte Item, Caches ohne dessen ID |
| `test_remove_last_item_restores_empty_state` | `project_empty_state` sichtbar, `artwork_source`/`artwork_transform` `None`, `import_summary_label` „Import: keine Datei geladen", `frame/dry_run/start_job` deaktiviert, G-Code = Rahmen-Starter, `_has_loaded_motif()` falsch, keine Tabellen-Selektion |
| `test_remove_declined_keeps_project` | Nein → Items, Auswahl, G-Code unverändert |
| `test_delete_key_in_object_table_removes_selected_item` | `QTest.keyClick(window.object_table, Qt.Key.Key_Delete)` → Bestätigung aufgerufen, Item entfernt |
| `test_remove_missing_source_item_clears_preflight_blocker` | Szenario wie `test_pyside_preflight_blocks_active_item_whose_source_is_missing`; nach Entfernen kein „Motivquelle nicht geladen"-Blocker |
| `test_remove_active_raster_unblocks_vector_job` | SVG + PNG, PNG entfernt → `raster_gcode_available` wahr, Layername ohne „Raster:" |
| `test_project_edit_locked_while_job_runs` | Phase `RUNNING` (+ `_sync_position_indicator()`) → beide Buttons deaktiviert; direkter Aufruf `_remove_selected_artwork()`/`_new_project()` ändert nichts und ruft keinen Dialog; ebenso bei `worker_busy=True` und `PAUSED` |
| `test_remove_with_generated_test_matrix` | Item + Testmatrix, Item entfernt → Verhalten gemäß Q3 (Default: `_generated_job_name is None`, Matrix-G-Code ersetzt) |
| `test_new_project_resets_project_state` | 2 Items, Einmessung, `current_project_path`, manuelle Platzierung → danach Items/Caches leer, Pfad/Einmessung `None`, Label „Nicht eingemessen", Platzierung = Startwerte, Default-Layer, G-Code = Rahmen-Starter |
| `test_new_project_keeps_machine_and_profiles` | Simulator verbunden + gehomed, Maschinenprofil, Materialprofilliste, `job_history` → nach Neu unverändert, Phase unverändert |
| `test_new_project_without_motif_needs_no_confirmation` | `confirm_new_project` so gepatcht, dass Aufruf den Test scheitern lässt |
| `test_new_project_after_test_matrix_gates_job_again` | Testmatrix ohne Motiv, Neu → `_generated_job_name is None`, `start_job` deaktiviert |
| `test_new_project_declined_keeps_project` | Nein → nichts geändert |
| `test_save_after_new_project_asks_for_path` | gepatchtes `getSaveFileName` wird aufgerufen |
| `test_import_after_new_project_uses_fresh_offsets` | Import nach Neu platziert wie beim ersten Import (Offset 0, da `len(items)==0`) |
| `test_load_project_drops_stale_item_caches` | Regression für Befund `_load_project`: nach Laden enthalten `_item_svg_analyses`/`_item_intelligence_results` nur IDs des geladenen Projekts |

### 6.4 Pflichtprüfungen

- `pytest` komplett grün (heute 368 Tests + neue), lokal mit `QT_QPA_PLATFORM=offscreen`.
- `flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics` ohne Befund (CI-Befehl).
- Manuell (qa, wenn möglich mit Simulator): Import 3 Motive → Entfernen per Button und Entf →
  Leerzustand → Neues Projekt → Import → Speichern/Laden.
- Größenprüfung: `project_workspace.py` < 120, `window_project_lifecycle.py` < 200,
  `window_item_state.py` < 80, `project_edit_actions.py` < 150 Zeilen; keine neue Methode > 40 Zeilen;
  `window_artwork.py` und `pyside_app.py` nicht länger als vorher.

## 7. Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Property-Bindung (D2) und `hasattr(self, "laser_project")`-Guards: vor Anlage von `project_workspace` wirft der Getter `AttributeError` → `hasattr` False (gleiche Semantik wie heute). Wird der Workspace zu spät angelegt, bricht `_build_layout`. | `project_workspace` vor `_build_layout` anlegen; Schritt 3 isoliert mit voller Testsuite prüfen. |
| `_load_project`-Umbau ändert unbemerkt die Reihenfolge (Legacy-Projekte ohne `laser_project`). | Bestehende Ladetests (`test_pyside_load_project_*`, `test_pyside_preflight_blocks_active_item_whose_source_is_missing`) müssen unverändert grün sein. |
| Qt-Selektion nach `setRowCount`-Verkleinerung feuert `itemSelectionChanged` und wählt ungewollt ein Item. | Läuft innerhalb `_object_list_updating`; zusätzlich `clearSelection()` bei leerer Auswahl; Test prüft `selected_artwork_item_id`. |
| Entf-Taste löscht während Namensbearbeitung. | `WidgetShortcut`-Kontext; Bestätigungsdialog als zweite Sicherung. |
| Kurze Lücke zwischen Jobstart-Klick und Phasenwechsel `RUNNING`. | `worker_busy` wird synchron in `_run_worker` gesetzt; Handler prüfen die Sperre selbst. |
| Layer nach Entfernen eines Rasters behalten Rasternamen/-zustand. | `_sync_layers_from_controls(preserve_states=True)` nach Raster-Entfernung; Test. |
| Ein Platzierungs-Snapshot beim Start könnte durch `_apply_machine_profile` schon verändert sein. | Snapshot nur der Platzierungs-Controls (`_svg_placement_data`), nicht des Arbeitsbereichs; Zeitpunkt am Ende von `__init__`, im Test gegen Startwerte prüfen. |
| Nutzer verliert ungespeicherte Arbeit. | Bestätigung (D3); Dirty-Tracking als Folgeaufgabe F3. |

## 8. Fachliche Fragen

**Entschieden am 2026-11-28 vom Nutzer: Die Vorschläge zu Q1–Q5 werden unverändert übernommen.**
Sie sind damit verbindlich (nicht mehr offen).

| Nr. | Frage | Vorschlag (Default, falls keine Antwort vor Schritt 4) |
|---|---|---|
| Q1 | Was setzt „Neues Projekt" zurück? Arbeitsbereich, Materialprofil-Auswahl und Modus (Gravur/Schnitt) werden auch im Projekt gespeichert. Platzierungs-Controls inkl. Materialform und Job-Ursprung ebenfalls. | Arbeitsbereich, Materialauswahl, Leistung/Speed/Passes und Modus **bleiben** (Arbeitsumgebung). Platzierung (Auto/Manuell, Rand, Größe, Rotation, Offsets) auf Startwerte; **Materialform und Job-Ursprung bleiben**. Layer auf Standard. Einmessung wird verworfen. |
| Q2 | Soll die Einmessung (Ecken 1-4) beim Neuen Projekt wirklich verworfen werden? Sie beschreibt das eingelegte Material, nicht das Motiv. | Verwerfen, weil sie im Projekt gespeichert wird; alternativ behalten, wenn typischerweise auf demselben Material weitergearbeitet wird. |
| Q3 | Testmatrix aktiv und Motiv wird entfernt: Matrix verwerfen (wie beim Aktiv-Häkchen heute) oder erhalten? | Verwerfen, Hinweis im Bestätigungsdialog und im Log (konsistent mit bestehendem Verhalten). |
| Q4 | Sollen „Datei importieren", „Laden" und Transformationen während eines laufenden Jobs ebenfalls gesperrt werden? | Nicht in diesem Auftrag; als Folgeaufgabe F4 (gleiche Begründung wie D4). |
| Q5 | Soll beim Entfernen auch die Originaldatei auf der Festplatte angeboten werden zu löschen? | Nein; nur aus dem Projekt entfernen (Dialogtext sagt das ausdrücklich). |

## 9. Abnahmekriterien (prüfbar)

1. In der Projekt-Sektion gibt es „Motiv entfernen" und „Neues Projekt".
2. „Motiv entfernen" ist nur aktiv, wenn ein Motiv ausgewählt ist und kein Job/keine
   Maschinenaktion läuft; der Tooltip nennt bei deaktiviertem Button den Grund.
3. Entfernen per Button oder Entf in der Objektliste zeigt immer eine Bestätigung mit dem
   Motivnamen; „Nein" ändert nichts.
4. Nach dem Entfernen ist das folgende (sonst vorherige) Motiv ausgewählt; Objektliste, Vorschau,
   Transform-Controls, G-Code, Projekt-/Job-Zusammenfassung und Preflight enthalten das entfernte
   Motiv nicht mehr; in keinem der acht Item-Caches steht seine ID.
5. Nach dem Entfernen des letzten Motivs: Leerzustand sichtbar, „Import: keine Datei geladen",
   Frame/Dry Run/Start deaktiviert, G-Code = Rahmen-Starter, keine Tabellen-Selektion.
6. Preflight-Blocker „Motivquelle nicht geladen" bzw. „Aktives Rastermotiv" verschwinden nach
   Entfernen des betroffenen Motivs.
7. „Neues Projekt" fragt nur nach, wenn Motive oder ein erzeugter Job vorhanden sind, und setzt
   danach den in Q1/Q2 festgelegten Umfang zurück; „Speichern" fragt danach nach einem neuen Pfad.
8. Maschinenverbindung und -phase, Maschinenprofil, Materialprofile, Material-DB und
   Job-Historie sind nach „Neues Projekt" unverändert (Test).
9. Während `RUNNING`/`PAUSED`/`STOPPING` oder `worker_busy` sind beide Funktionen gesperrt,
   auch bei direktem Methodenaufruf.
10. `project_workspace.py` importiert kein PySide6; alle Tests aus Abschnitt 6 vorhanden und grün;
    flake8-CI-Befehl ohne Befund; Größen gemäß 6.4.
11. README „Current Features"/„Code Structure" und CHANGELOG „Unreleased" aktualisiert.
12. Projektdateiformat unverändert: mit der alten Version gespeicherte `.laser.json` laden wie bisher.

## 10. Folgeaufgaben (nicht in diesem Auftrag)

- F1 `window_artwork.py` (911 Zeilen) aufteilen, z. B. Transformation (`_apply_svg_placement`,
  `_commit_artwork_transform`, `_transform_*`) und Projekt-Serialisierung
  (`_artwork_source_to_project`, `_transform_from_project`, das `project.transform_from_dict` dupliziert).
- F2 `pyside_app._build_sidebar` (~240 Zeilen) in Sektions-Builder bzw. Panels zerlegen.
- F3 Ungespeichert-Tracking (Dirty-Flag) mit Rückfrage auch beim Laden und Beenden.
- F4 Sperre für Import/Laden/Transformation während laufender Jobs (Q4).
- F5 Übersetzbarkeit (`tr()`) projektweit; heute nicht genutzt.
- F6 `tests/test_pyside_units.py` (~1780 Zeilen) nach Themen aufteilen.

## 11. Hinweise für die Umsetzung

- Arbeit auf eigenem Branch (z. B. `feature/remove-artwork-new-project`); Commit/Push nur nach
  Freigabe. Auffälligkeit: aktueller Branch heißt `master`, CI triggert auf `main`.
- Keine neuen Abhängigkeiten, kein `pytest-qt`.
- Bestehende Tests nicht anpassen, um sie grün zu bekommen; einzige erwartete Teständerung: keine.
