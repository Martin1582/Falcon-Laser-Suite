# LaserWeb-inspirierte Workflow-Konzepte

Diese App uebernimmt nur einfache, robuste Konzepte:

- Arbeitsbereich mit Grid und Job-Bounds
- Import-Zusammenfassung
- Sichtbarkeitsschalter fuer Preview-Ebenen
- echte GRBL-Kopfposition, wenn bekannt
- Preflight als Sicherheits- und Verstaendlichkeitsstufe
- vorbereitete GCode-Pfadanzeige aus analysierbaren Bewegungssegmenten

Nicht uebernommen werden:

- vollstaendige CAM-Operationen
- komplexe Simulation
- Kamera, Rotary, Autofokus oder Click-to-Move
- eine dominante Experten-/Terminaloberflaeche

## Vereinfachte Pipeline

Die App trennt die Daten gedanklich so:

`Importiertes Objekt -> Job-Layer / Operation -> PreviewModel -> PreparedJob -> StreamingJob`

Importiertes Objekt und `ArtworkTransform` bilden die gemeinsame Basis fuer Position und Skalierung. Preview, Preflight und GCode duerfen keine abweichenden Transformdaten verwenden.

## Preview-Schalter

Die Sichtbarkeitsschalter beeinflussen nur die Darstellung:

- Motiv
- Bounding Box
- Arbeitsbereich
- Kopfposition
- GCode-Pfad

Sie veraendern keine Jobdaten, keine Transformwerte und keinen GCode.

## Kopfposition

Die Kopfposition wird nur aus echten Maschinenstatusdaten angezeigt. `WPos` wird bevorzugt, `MPos` ist Fallback, sofern der GRBL-Statusparser diese Werte liefert. Wenn keine Position bekannt ist, wird kein Marker gezeichnet.

## GCode-Overlay

Das Overlay verwendet Bewegungssegmente aus der bestehenden GCode-Analyse. Es ist keine Simulation und erzeugt keine Sollposition. Rapid-Bewegungen und Arbeitsbewegungen koennen unterschiedlich dargestellt werden.
