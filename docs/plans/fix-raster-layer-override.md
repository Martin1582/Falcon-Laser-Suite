# Plan: Bugfix Raster-Import überschreibt Gravur-/Schnitt-Layer

Stand: 2026-11-28, Branch `feature/remove-artwork-new-project` @ `c916e45`.
Technische Basis bleibt Python 3.12 / PySide6. Keine Datenbank betroffen, kein `sql`-, kein `network`-Anteil.

## 1. Ziel und Abgrenzung

**Fehler (von qa belegt, hier im Code bestätigt):** Modus „Cutten“, Schnitt-Layer auf 3 Durchgänge,
SVG im Projekt → `; layer 20: Schnitt … 3x`, M3. Nach dem Import eines PNG/JPG kommt das SVG über
den Gravur-Layer heraus (`; layer 10: Raster: p.png … 1x`), Schnitt ist aus, die 3 Durchgänge sind weg.
Das bleibt beim Deaktivieren des Rasters und bei Auswahl des SVG so und wird mit dem Projekt gespeichert.

**Ziel**

1. Die Rasterdarstellung verändert die Layer und ihre Nutzerparameter nie mehr, weder beim Import
   noch bei Moduswechsel, Materialwechsel, Auswahl, Deaktivieren, Entfernen oder Laden.
2. Bestehende Projektdateien mit eingebrannter Raster-Belegung werden beim Laden erkannt, sichtbar
   korrigiert und protokolliert (kein stiller Datenverlust, keine stille Weiterverwendung des
   falschen G-Codes).
3. Der lokale Workaround `_sync_layers_after_raster_removal()` entfällt.
4. Optional (Frage F3): Preflight-Warnung, wenn im Modus „Cutten“ kein Schnitt-Layer aktiv ist.

**Nicht Teil des Auftrags**

- Rastergravur-G-Code und eigene Raster-Parameter (Folgeaufgabe, Abschnitt 7).
- Änderung des Projektformats: `PROJECT_VERSION` bleibt 3 (Begründung in Abschnitt 3.3).
- Weitere Aufteilung von `window_artwork.py` (909 Zeilen) oder `pyside_app.py`; der Fix lässt
  `window_artwork.py` um eine Zeile schrumpfen.
- Die weiteren Befunde W1/W2 (Abschnitt 2.2), außer der Nutzer entscheidet anders (F4, F5).

## 2. Ausgangslage (im Code verifiziert)

### 2.1 Ursachen

| # | Stelle | Befund |
|---|---|---|
| U1 | `laser_control/window_materials.py:53-61` `_sync_layers_from_controls` | Bei nicht-leerem `raster_sources` wird ENGRAVE in „Raster: <Datei>“ umbenannt und aktiviert, CUT deaktiviert. Bestätigt. Wirkt bei **jedem** Aufruf, also auch bei `_on_operation_mode_changed` (`:224-227`) und `_save_new_material_profile` (`:215`, beide `preserve_states=False`): Wer bei einem Raster im Projekt auf „Cutten“ umschaltet, bekommt Schnitt sofort wieder ausgeschaltet. Bei `_profile_selected`/`_material_settings_changed` (`preserve_states=True`) wirkt nur die Umbenennung. |
| U2 | `laser_control/window_artwork.py:437` | Raster-Import ruft `_sync_layers_from_controls(preserve_states=False)`: Layer werden aus `build_default_layers` neu gebaut, Nutzerparameter (Passes, Speed, Power, Fill-Modus, Overscan, Reihenfolge) gehen verloren. Der SVG-Zweig (`:413-425`) ruft die Synchronisation **nicht** auf. Bestätigt. |
| U3 | `window_artwork.py:267-295` `_select_artwork_item`, `:371-385` `_object_table_item_changed` | Synchronisieren die Layer nicht. Bestätigt. Nach dem Fix ist das korrekt so, weil die Layer dann nicht mehr vom Raster abhängen; hier ist **keine** Änderung nötig. |
| U4 | `laser_control/window_project.py:185-192` | Gespeicherte Layer werden 1:1 übernommen. Zusätzlich: `:193` setzt den **gespeicherten G-Code** in den Editor, ohne ihn neu zu erzeugen. Preflight und Start (`_job_context(..., gcode_text)`) arbeiten mit diesem Text. Ein Altprojekt würde also auch nach einer Layer-Korrektur weiter mit `; layer 10: Raster: … 1x` laufen, bis zufällig `_refresh_gcode()` ausgelöst wird. |
| U5 | `laser_control/window_project_lifecycle.py:93-108` `_sync_layers_after_raster_removal` | Workaround: ruft U1 erneut auf und biegt danach die enabled-Flags zurück. Nach Beseitigung von U1/U2 wirkungslos bzw. sogar schädlich (überschreibt einen vom Nutzer bewusst gesetzten Layerzustand beim Entfernen eines Rasters). Wird entfernt. |

**Warum die Raster-Belegung fachlich nichts bewirkt:** Raster-Ausgabe nutzt keine Layer.
`_refresh_gcode` (`window_job.py:420-435`) schreibt bei reinem Raster nur einen Platzhalter-Kommentar,
der Preflight blockiert aktive Raster über `raster_gcode_available` (`workflow_controller.py:362-366`,
`window_job.py:311-316`). Die Vorschau zeichnet Raster unabhängig von Layer-Zustand und -Name
(`preview_model.py:197-206`, `:240-244`; `work_area_preview.py:159-161`). Die Belegung ist reine
Beschriftung mit Nebenwirkung auf die Vektorausgabe.

Layer-Namen sind im `LayerPanel` nicht editierbar (`qt_panels.py:136-164` übernimmt `name` aus
`_layers`). Ein ENGRAVE-Layer mit Namen `"Raster: …"` kann also **nur** durch U1 entstanden sein und
ist ein verlässliches Erkennungsmerkmal für Altprojekte.

### 2.2 Weitere Befunde (nicht Teil des Fixes, nur gemeldet)

| # | Befund |
|---|---|
| W1 | `LayerPanel.set_fill_available(False, …)` (`qt_panels.py:166-177`) setzt den Modus aller Fill-Layer dauerhaft auf „Kontur“. Ausgelöst, sobald kein aktives Vektormotiv da ist (`window_job.py:421`, `:493`, `:498`), z. B. wenn nur noch das Raster aktiv ist. Reaktiviert der Nutzer das SVG, bleibt „Kontur“ stehen. Gleiches Muster wie der Hauptfehler (Nutzerparameter gehen durch einen Anzeigezustand verloren), aber nicht rasterspezifisch. Siehe F4. |
| W2 | Beim Laden wird generell der gespeicherte G-Code statt eines aus Layern und Motiven neu erzeugten verwendet (U4). Für Projekte mit Motiven können Editor und Layer auseinanderlaufen. Siehe F5. |

## 3. Lösungsvarianten und Empfehlung

### 3.1 Varianten

| Variante | Beschreibung | Bewertung |
|---|---|---|
| **A – Override ersatzlos entfernen** | Block `window_materials.py:53-61` löschen, Aufruf `window_artwork.py:437` löschen, Workaround U5 löschen. Raster wird wie bisher in Objektliste, Größenlabel (`Raster: <Datei>`), Vorschau-Beschriftung und Job-Zusammenfassung angezeigt, nur nicht mehr im Layer-Panel. | Kleinster Eingriff (nur Löschungen in Produktivcode). Löst Import-, Deaktivieren-, Auswahl-, Moduswechsel-, Materialwechsel- und Entfernen-Szenario an der Wurzel, weil kein Pfad mehr existiert, der Layer vom Raster abhängig macht. Laden braucht zusätzlich die Altdaten-Korrektur (3.3). |
| B – Raster-Belegung nur abgeleitet anzeigen | Layer-Zustand bleibt unverändert; `LayerPanel` zeigt bei aktivem Raster eine abgeleitete Beschriftung. | Gleiches Ergebnis wie A, aber zusätzlicher Code im Panel und ein neuer Zustandskanal Fenster→Panel, nur für Kosmetik. Die Info steht bereits an vier anderen Stellen. Nicht nötig. |
| C – Nur umstellen, wenn ausschließlich ein aktives Raster ausgegeben würde | Override bleibt, aber bedingt; beim Aktivieren eines SVG zurückstellen. | Verändert weiterhin Layer-Zustand und muss ihn bei jedem Aktiv-, Auswahl-, Entfernen- und Ladeereignis wiederherstellen. Das ist genau die Workaround-Kette, die U5 schon zeigt. Ohne Raster-G-Code ohne jeden Nutzen. Abgelehnt. |
| D – Eigener Raster-Layer (`LayerType.RASTER`) nur für die Vorschau | Fünfter Layer im Panel. | Greift in Layer-Modell, Panel, Vorschau, Persistenz und G-Code-Filter ein, bevor es Raster-G-Code gibt. Gehört in die Folgeaufgabe „Rastergravur“, nicht in einen Bugfix. |

### 3.2 Empfehlung: Variante A

Begründung: Sie ist die einzige Variante, die keinen neuen Zustand einführt, und alle Szenarien
korrekt löst, weil die Abhängigkeit „Layer hängen von `raster_sources` ab“ verschwindet. Es bleibt
kein Ereignis übrig, bei dem etwas wiederhergestellt werden müsste. Für künftigen Raster-G-Code
existiert mit `ArtworkItem.layer_assignments` bereits ein passender, unbenutzter Ort für
Raster-Parameter pro Motiv (Abschnitt 7).

### 3.3 Altprojekte (Layer „Raster: …“ gespeichert)

Neue Qt-freie Einheit `laser_control/layer_compat.py` (eigene Datei, damit sie parallel zu
Schritt S4 in `layers.py` bearbeitet werden kann):

```python
LEGACY_RASTER_NAME_PREFIX = "Raster: "

@dataclass(frozen=True)
class LayerRepairResult:
    layers: list[JobLayer]
    notes: list[str]          # leer = nichts geändert

def repair_legacy_raster_layers(layers: list[JobLayer], operation_mode: str) -> LayerRepairResult: ...
```

Regeln (rein, verändert die Eingabe nicht, Kopien über `dataclasses.replace`, idempotent):

1. Kein ENGRAVE-Layer mit Präfix `"Raster: "` → unverändert, `notes == []`.
2. Präfix gefunden → ENGRAVE-Layer heißt wieder `LayerType.ENGRAVE.value` („Gravur“). Hinweis.
3. Zusätzlich nur wenn `operation_mode == CUT_MODE` **und** ENGRAVE aktiv **und** CUT inaktiv
   (genau das Muster von U1): ENGRAVE aus, CUT an. Hinweis mit Aufforderung, Leistung, Geschwindigkeit
   und Durchgänge des Schnitt-Layers zu prüfen. Weicht der Zustand von diesem Muster ab, hat der
   Nutzer ihn danach selbst geändert → Flags bleiben (nur Umbenennung).
4. Speed/Power/Passes/Fill werden **nicht** angefasst. Die ursprünglichen Werte sind in der Datei
   nicht mehr vorhanden (U2 hat sie beim Import überschrieben) und lassen sich nicht rekonstruieren;
   darum der ausdrückliche Prüfhinweis statt eines geratenen Wertes.

Einbindung in `window_project.py`: Zeilen 185-192 wandern in einen neuen Helfer
`_restore_layers(data) -> list[str]` (< 40 Zeilen, `_load_project` wird dadurch kürzer, nicht länger).
Wenn `notes` nicht leer ist:
- jeder Hinweis über `self.log(...)`,
- nach `gcode_text.setPlainText(...)` einmal `_refresh_gcode()`, damit Editor, Preflight und Start
  den korrigierten Layern entsprechen (U4). Ohne Korrektur bleibt das bisherige Ladeverhalten
  unverändert (siehe F5).
- Art der Nutzerinformation: siehe F2.

**Kein stiller Datenverlust:** Die Datei auf der Platte wird beim Laden nicht verändert; die Korrektur
wird erst mit dem nächsten Speichern geschrieben. Bis dahin ist der Originalzustand per „nicht
speichern“ erhalten. Jede Änderung wird protokolliert.

**Projektformat:** Keine neuen Felder, keine Strukturänderung, die Korrektur erkennt Altdaten am
Inhalt und ist idempotent. Ältere App-Versionen können neu gespeicherte Dateien weiterhin lesen.
`PROJECT_VERSION` bleibt 3, `project.py` bleibt unverändert.

### 3.4 Preflight-Absicherung (abhängig von F3)

Vorschlag: neue reine Funktion in `laser_control/layers.py`

```python
def operation_mode_layer_warnings(layers: list[JobLayer], operation_mode: str) -> list[str]: ...
```

- `operation_mode == CUT_MODE`, mindestens ein aktiver Ausgabelayer, aber kein aktiver CUT-Layer →
  Warnung, z. B. „Modus Cutten: Kein Schnitt-Layer aktiv. Die Motive werden mit den Werten von
  Layer 'Gravur' ausgegeben.“ (Layernamen über Platzhalter, keine Satzbausteine).
- Sonst `[]`.
- Aufruf in `WorkflowController.prepare_preflight` (`workflow_controller.py:339`, direkt nach
  `layer_validation_warnings`), **nicht** bei `context.source_type == "generated"` (Testmatrix hat
  eigene Parameter).

Warnung statt Blocker, weil Gravieren mit M3 im Modus „Cutten“ ein legitimer Anwendungsfall sein kann
und `layer_validation_warnings` bereits als Warnung läuft. Ein Blocker würde diesen Fall verhindern.

## 4. Schritte

| Schritt | Agent | Inhalt | Dateien (ausschließlich) |
|---|---|---|---|
| S0 | Hauptagent | Fragen F1-F5 mit dem Nutzer klären. Backup nach CLAUDE.md nur, wenn der Hauptagent den Fix als kritisch einstuft (keine DB-Migration, keine Löschung von Nutzerdaten; empfohlen wegen der Altprojekt-Korrektur). | – |
| S1 | `coder` | **Tests zuerst**, die den Fehler zeigen und auf `c916e45` rot sind (Liste 4.1). Für S3/S4 gegen die in 3.3/3.4 festgelegten Signaturen. Lauf protokollieren: welche Tests rot, mit welcher Meldung. | neu `tests/test_pyside_raster_layers.py`, neu `tests/test_layer_compat.py`, `tests/test_workflow_controller.py` (nur wenn F3 = ja), neu oder erweitert `tests/test_layers.py` (nur wenn F3 = ja) |
| S2 | `coder` | **Wurzel-Fix (Variante A):** Block `window_materials.py:53-61` löschen, danach unbenutzten Import `LayerType` entfernen. Aufruf `window_artwork.py:437` löschen. `_sync_layers_after_raster_removal` samt Aufruf (`:86-87`) und unbenutzten Importen (`LayerType`, `build_default_layers`, `:7`) in `window_project_lifecycle.py` löschen, Docstring ggf. anpassen. Bestehende Tests, die das Fehlverhalten festschreiben, gezielt umstellen (4.2). | `laser_control/window_materials.py`, `laser_control/window_artwork.py`, `laser_control/window_project_lifecycle.py`, `tests/test_pyside_units.py` (nur Zeile ~829), `tests/test_pyside_project_lifecycle.py` (nur Zeilen ~207, ~236) |
| S3 | `coder` | **Altprojekte:** `layer_compat.py` nach 3.3; `_restore_layers` in `window_project.py`, Log-Hinweise, `_refresh_gcode()` nach Korrektur. Nutzerinformation nach F2. | neu `laser_control/layer_compat.py`, `laser_control/window_project.py` |
| S4 | `coder` | **Preflight-Warnung** (nur wenn F3 = ja) nach 3.4; Doku ergänzen. | `laser_control/layers.py`, `laser_control/workflow_controller.py`, `docs/preflight.md` |
| S5 | `designer` | Wortlaut von Log-Hinweis (S3), ggf. Dialogtext (F2) und Preflight-Warnung (S4) prüfen: verständlich, ohne Fachjargon, Platzhalter statt zusammengesetzter Sätze, Umlaut-Schreibweise wie im übrigen Code (ae/oe/ue). Liefert Texte als Vorschlag an `coder`, ändert selbst keine Dateien aus S2-S4. | keine (Rückmeldung an Hauptagent) |
| S6 | `qa` | Review und Abnahme nach Abschnitt 6, inkl. eigener Reproduktion des qa-Szenarios. | – |

### 4.1 Neue Tests (S1, test-first)

`tests/test_pyside_raster_layers.py` (eigene Datei, damit `tests/test_pyside_units.py` mit ~1780 Zeilen
nicht weiter wächst; Fixture und Helfer `_svg`, `_png`, `_import`, `_answer` wie in
`tests/test_pyside_project_lifecycle.py`). Alle UI-Tests parametrisiert über `cut_mode` / `engrave_mode`
(`operation_mode.setCurrentIndex(1/0)`), aktiver Layer = CUT bzw. ENGRAVE.

Gemeinsame Vorbereitung: SVG importieren, am aktiven Layer `passes = 3`, `speed_mm_min = 777`,
`power_percent = 42` setzen (`layer_panel.set_layers` + `_layer_changed()`), Snapshot
`[layer_to_dict(l) for l in layer_panel.layers()]` merken.

| Test | Schritt | Erwartung |
|---|---|---|
| `test_raster_import_keeps_layers` | PNG importieren | Layer-Snapshot unverändert (alle Felder); kein Layername beginnt mit `"Raster:"`. |
| `test_raster_import_keeps_vector_gcode_after_deactivating_raster` | PNG importieren, Raster in Objektliste deaktivieren (`item.active = False` über die Tabellen-Checkbox Spalte 1, damit `_object_table_item_changed` läuft) | G-Code enthält `; layer 20: Schnitt 777 mm/min 42% 3x` bzw. `; layer 10: Gravur 777 mm/min 42% 3x`, genau 3 `; pass`-Blöcke, im Cut-Modus `M3`-Zeilen und kein `; layer 10:`, im Gravur-Modus `M4` und kein `; layer 20:`. |
| `test_selecting_vector_after_raster_import_keeps_layers` | PNG importieren, SVG über `_select_artwork_item` auswählen | Snapshot unverändert. |
| `test_mode_switch_with_raster_in_project_enables_mode_layer` | Ohne Parametersetzen: SVG + PNG, dann Modus wechseln | Im Zielmodus ist genau der Modus-Layer aktiv (Cut → nur Schnitt), unabhängig vom Raster. |
| `test_remove_raster_keeps_user_layer_state` | PNG importieren, danach Nutzer schaltet zusätzlich Markierung an, Raster entfernen | Snapshot inkl. Markierung = an bleibt (belegt, dass U5 weg ist und nichts zurückbiegt). |
| `test_save_load_roundtrip_keeps_layers_with_raster` | SVG + PNG, speichern, in neuem Fenster laden | Geladene Layer == Snapshot; kein Hinweis im Log. |
| `test_load_legacy_raster_project_repairs_cut_mode` | Projekt speichern (Cut-Modus), JSON nachträglich in Altzustand bringen: ENGRAVE `name = "Raster: p.png"`, `enabled = True`, CUT `enabled = False`, `gcode` = alter Text mit `; layer 10: Raster: p.png`; laden | ENGRAVE heißt „Gravur“ und ist aus, CUT ist an; Editor-G-Code enthält `; layer 20: Schnitt` und nicht `Raster: p.png`; Log enthält den Prüfhinweis. Datei auf der Platte unverändert (Bytevergleich). |
| `test_load_legacy_raster_project_engrave_mode_only_renames` | wie oben im Gravur-Modus | nur Umbenennung, Flags unverändert. |

`tests/test_layer_compat.py` (Qt-frei): unveränderte Layer ohne Präfix; Umbenennung; Flag-Korrektur nur
bei Cut-Modus + genauem U1-Muster; keine Flag-Korrektur, wenn Nutzer den Zustand danach geändert hat
(z. B. beide aktiv); Parameter unverändert; Eingabeliste nicht mutiert; Idempotenz (zweiter Aufruf
liefert `notes == []`).

Nur bei F3 = ja: `tests/test_layers.py` für `operation_mode_layer_warnings` (Cut ohne CUT → Warnung;
Cut mit CUT → keine; Gravur-Modus → keine; keine aktiven Layer → keine, das deckt
`layer_validation_warnings` ab) und `tests/test_workflow_controller.py`: Warnung erscheint in
`prepare_preflight(...).warnings`, nicht in `blockers`, und nicht bei `source_type == "generated"`.

### 4.2 Bestehende Tests, die das Fehlverhalten festschreiben (S2)

Diese Assertions prüfen genau den Fehler und werden **ersetzt, nicht gelöscht**:

| Test | Alt | Neu |
|---|---|---|
| `tests/test_pyside_units.py:829` `test_pyside_imports_raster_as_blocked_preview_source` | `"Raster" in layer_panel.layers()[0].name` | Layernamen sind `["Gravur", "Schnitt", "Markierung", "Hilfsebene"]` und `"Raster: photo.png"` steht in `svg_size_label.text()` (Raster bleibt sichtbar gekennzeichnet). Übrige Assertions bleiben. |
| `tests/test_pyside_project_lifecycle.py:207` `test_remove_active_raster_unblocks_vector_job` | `any(name.startswith("Raster:"))` | `not any(...)`; Blocker-Assertions bleiben. |
| `tests/test_pyside_project_lifecycle.py:236` `test_remove_raster_restores_operation_mode_layers` | `_layer_flags(window)["Raster: p.png"] is True` | Flags nach dem PNG-Import == `expected_flags` (Import ändert nichts). Restlicher Test (Speed 777 überlebt, G-Code-Kommentar, M3/M4) bleibt unverändert als Regressionstest. |

Keine weiteren bestehenden Tests werden angepasst. Fällt ein anderer Test, ist das ein Befund und
geht an den Hauptagenten.

## 5. Parallelisierung

```
S0 ─► S1 ─┬─► S2 ─┐
          ├─► S3 ─┼─► S6 (qa)
          └─► S4 ─┘
S5 (designer) parallel zu S2-S4, Texte fließen vor S6 in S3/S4 ein
```

- S1 zuerst und allein (test-first, legt die Signaturen fest).
- S2, S3, S4 haben disjunkte Dateimengen (siehe Tabelle) und dürfen parallel laufen.
  `layer_compat.py` ist bewusst eine eigene Datei, damit S3 und S4 nicht beide `layers.py` ändern.
- Die neue Testdatei `tests/test_pyside_raster_layers.py` gehört nur S1; S2-S4 ändern sie nicht.
  Muss ein Test nachgeschärft werden, geht das über den Hauptagenten zurück an S1.
- Empfehlung trotzdem: Der Umfang ist klein (geschätzt < 150 geänderte Zeilen inkl. Tests). Ein
  `coder` (sonnet), der S1-S4 nacheinander erledigt, ist hier effizienter als drei parallele.
- Kein Schritt startet einen Server.

## 6. Abnahmekriterien und Prüfungen

**Fachlich**

1. qa-Szenario: Cut-Modus, Schnitt-Layer 3 Durchgänge, SVG, PNG importieren → G-Code
   `; layer 20: Schnitt … 3x`, M3, kein `; layer 10:`. Gleiches nach Deaktivieren des Rasters, nach
   Auswahl des SVG und nach Speichern/Laden.
2. Gravur-Modus analog mit `; layer 10: Gravur … 3x`, M4.
3. Moduswechsel und Materialwechsel mit Raster im Projekt schalten den Layer des Zielmodus an, nicht
   die Gravur.
4. Aktives Raster blockiert den Start weiterhin (`Aktives Rastermotiv: …`), deaktiviertes nicht.
5. Altprojekt mit „Raster: …“-Layer im Cut-Modus wird beim Laden korrigiert, der Editor-G-Code
   entspricht den korrigierten Layern, ein Hinweis zur Prüfung der Schnittparameter erscheint, die
   Datei auf der Platte bleibt bis zum Speichern unverändert.
6. Projekte ohne Präfix laden exakt wie bisher (Layer und G-Code unverändert).
7. Nur bei F3 = ja: Cut-Modus ohne aktiven Schnitt-Layer erzeugt die Preflight-Warnung, keinen Blocker.

**Code**

8. Im Produktivcode gibt es keinen Pfad mehr, der Layer abhängig von `raster_sources` ändert
   (`grep "Raster: "` in `laser_control/` trifft nur Labels/Vorschau/Status und `layer_compat.py`).
9. `_sync_layers_after_raster_removal` existiert nicht mehr; keine unbenutzten Importe.
10. `window_artwork.py` wird nicht länger (Soll: 908 Zeilen), `_load_project` wird nicht länger, alle
    neuen oder geänderten Methoden < 40 Zeilen, `layer_compat.py` und neue Funktionen Qt-frei.
11. `PROJECT_VERSION` bleibt 3, `project.py` unverändert, keine neuen Abhängigkeiten.
12. Keine bestehenden Tests abgeschwächt; Änderungen nur wie in 4.2.

**Prüfungen (Befehle ausführen und Ergebnis berichten)**

- S1-Nachweis: neue Tests auf dem Stand vor S2/S3 rot (Ausgabe festhalten).
- `python -m pytest` vollständig grün (Basis 407 + neue Tests; Anzahl nennen).
- `python -m flake8 laser_control tests --select=E9,F63,F7,F82` ohne Befund (wie CI).
- Optional, falls im Projekt eingerichtet: `ruff check` auf die geänderten Dateien.
- Manueller Rauchtest durch `qa` oder Nutzer: App starten, qa-Szenario 1 in der Oberfläche
  nachstellen, G-Code-Panel prüfen.

## 7. Risiken

| Risiko | Bewertung / Gegenmaßnahme |
|---|---|
| Nutzer vermisst „Raster: …“ im Layer-Panel | Raster bleibt in Objektliste (Typ), Größenlabel, Vorschau-Beschriftung und Job-Zusammenfassung erkennbar. Siehe F1. |
| Falsch-positive Altdaten-Korrektur | Präfix kann nur durch U1 entstehen (Namen nicht editierbar); Flags werden nur beim exakten U1-Muster im Cut-Modus geändert; jede Änderung wird protokolliert; Datei bleibt bis zum Speichern unverändert. Restrisiko: Nutzer hatte im Cut-Modus bewusst „Gravur an / Schnitt aus“ nach dem Rasterimport stehen lassen. Siehe F2. |
| Verlorene Schnittparameter in Altprojekten sind nicht wiederherstellbar | Nicht behebbar (Werte nie gespeichert). Gegenmaßnahme: ausdrücklicher Prüfhinweis; Preflight-Warnung (F3) fängt zusätzlich „kein Schnitt-Layer“ ab. |
| `_refresh_gcode()` beim Laden ersetzt gespeicherten G-Code | Nur wenn korrigiert wurde. Ein im Altprojekt gespeicherter Testmatrix-G-Code hat keine Motive; `_refresh_gcode` würde ihn durch den Rahmen-G-Code ersetzen. Gegenmaßnahme: Neu-Erzeugung nur, wenn `laser_project.items` nicht leer ist (in S3 umsetzen, Test in 4.1 ergänzen, falls Aufwand gering). |
| Künftiger Raster-G-Code braucht Parameter | Folgeaufgabe: Raster-Parameter pro Motiv über `ArtworkItem.layer_assignments` oder eigenen Layer-Typ; nicht über Umbelegung der Vektorlayer. |
| Parallelarbeit kollidiert | Dateimengen in Abschnitt 4 disjunkt; Testdatei nur S1. |

## 8. Fachliche Fragen

**Entschieden am 2026-11-28 vom Nutzer (verbindlich):** Vorschläge zu F1, F2, F4 und F5 werden
übernommen. **F3 abweichend vom Vorschlag als Blocker**, nicht als Warnung: Im Modus „Cutten“
mit mindestens einem aktiven Ausgabelayer, aber ohne aktiven Schnitt-Layer blockiert der Preflight
den Start (Ausnahme wie in 3.4: `source_type == "generated"`, Testmatrix). Der Blockertext nennt die
Abhilfe (Schnitt-Layer aktivieren oder Modus „Gravieren“ wählen). Abschnitt 3.4 ist entsprechend
als Blocker umzusetzen (Funktionsname z. B. `operation_mode_layer_blockers`).

- **F1 – Rasterkennzeichnung im Layer-Panel:** Soll das Layer-Panel bei einem Raster im Projekt
  weiterhin einen Hinweis zeigen?
  *Vorschlag:* Nein. Das Raster ist an vier Stellen sichtbar und Layer haben mit Rasterausgabe noch
  nichts zu tun. Kommt Raster-G-Code, bekommt das Raster eigene Parameter (Folgeaufgabe).
- **F2 – Nutzerinformation bei korrigiertem Altprojekt:** Nur Log-Eintrag, oder zusätzlich ein
  Hinweisdialog (`QMessageBox.information`) beim Laden?
  *Vorschlag:* Hinweisdialog plus Log. Der Nutzer muss die Schnittparameter aktiv prüfen, weil sie
  nicht wiederherstellbar sind; ein reiner Log-Eintrag wird leicht übersehen.
  Alternative, falls zu aufdringlich: nur Log plus Preflight-Warnung (F3).
- **F3 – Preflight-Absicherung:** Warnung, wenn im Modus „Cutten“ kein Schnitt-Layer aktiv ist?
  *Vorschlag:* Ja, als **Warnung**, nicht als Blocker (Gravieren mit M3 kann gewollt sein). Analoge
  Warnung für den Gravur-Modus nicht nötig.
- **F4 – Befund W1 (Fill-Modus wird bei „kein aktives Vektormotiv“ auf Kontur zurückgesetzt):** Im
  selben Fix mitbeheben?
  *Vorschlag:* Nein, eigene Folgeaufgabe mit eigenem Test, weil `LayerPanel` und alle drei Aufrufer
  in `window_job.py` betroffen sind und der Fehler nicht rasterspezifisch ist.
- **F5 – Befund W2 (gespeicherter G-Code wird beim Laden ungeprüft übernommen):** Soll beim Laden
  generell neu erzeugt werden, wenn das Projekt Motive enthält?
  *Vorschlag:* Im Fix nur bei Altdaten-Korrektur neu erzeugen; die generelle Frage als Folgeaufgabe
  klären (Auswirkung auf gespeicherte, von Hand bearbeitete G-Codes).
