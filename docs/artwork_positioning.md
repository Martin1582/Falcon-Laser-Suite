# Positionierung und Skalierung importierter Motive

## Zentrale Transform-Daten

Importierte Motive verwenden eine gemeinsame Transform-Basis:

- `x_mm`: linke Motivposition im Arbeitsbereich
- `y_mm`: untere Motivposition im Arbeitsbereich
- `scale` / `uniform_scale`: proportionaler Skalierungsfaktor
- `scale_x` / `scale_y`: positive Achsenskalierung; negative Werte und damit versehentliche Spiegelungen sind ungueltig
- `rotation_deg`: bewusste Benutzerdrehung, Standard `0 Grad`
- `keep_aspect_ratio`: standardmaessig aktiv
- `origin_mode`: aktuell `lower_left`
- `original_width_mm` / `original_height_mm`: importierte Originalgroesse
- `current_width_mm` / `current_height_mm`: Groesse nach AutoFit oder manueller Skalierung

Preview, Preflight und Vektor-GCode verwenden dieselben Transformdaten. Originalpfade bleiben in lokalen Motivkoordinaten erhalten; Arbeitsbereichskoordinaten werden daraus abgeleitet.

## AutoFit

AutoFit passt groessere Motive proportional in den Arbeitsbereich ein. Das Seitenverhaeltnis bleibt erhalten, es wird nicht verzerrt und nicht beschnitten.

Kleinere Motive werden nicht automatisch vergroessert. Sie behalten `scale = 1.0` und werden zentriert.

Bei kreisfoermigem Material wird in die zentrierte Kreis-Bounding-Box eingepasst. Eine gesetzte Rotation wird bei der Groessen- und Boundsberechnung beruecksichtigt.

## Manuelle Positionierung

X, Y, Breite, Hoehe, Skalierung und Rotation schreiben in `ArtworkTransform`. Bei gesperrtem Seitenverhaeltnis aktualisiert eine Breiten- oder Hoehenanpassung die jeweils andere Dimension proportional.
Zusaetzlich stehen Zentrieren, links unten platzieren, Einpassen und Originalgroesse zur Verfuegung.

## Direkte Preview-Positionierung

Ein Motiv kann in der Preview ausgewählt und mit gedrueckter linker Maustaste verschoben werden. Die Bedienung bewegt ausschliesslich das importierte Motiv; es werden keine Maschinenbewegungen oder GRBL-Kommandos ausgeloest.

Die Preview berechnet die neue Position in Millimetern und schreibt sie ueber denselben Commit-Pfad wie die numerischen X-/Y-Felder in `ArtworkTransform.x_mm` und `ArtworkTransform.y_mm`. Die Ursprungsdatei bleibt unveraendert.

Snap ist standardmaessig aktiv und kann in den Preview-Optionen deaktiviert werden. Unterstuetzt werden:

- linke, rechte, obere und untere Arbeitsbereichskante
- horizontale und vertikale Arbeitsbereichsmitte
- vollstaendige Zentrierung

Beim Einrasten werden Hilfslinien angezeigt. Das Motiv darf fuer vorbereitende Positionierung ausserhalb des Arbeitsbereichs liegen; die Bounding Box wird dann als ungueltig dargestellt und der Preflight blockiert den Start.

Bei ausgewaehltem Motiv stehen Pfeiltasten fuer Feinkorrekturen zur Verfuegung:

- Pfeiltaste: 1 mm
- Shift + Pfeiltaste: 10 mm
- Ctrl + Pfeiltaste: 0.1 mm

Die Interaktionsschicht verwaltet aktuell eine einzelne Auswahl. Auswahlrahmen und Hit-Test sind getrennt von der Transformlogik, sodass spaetere Resize-/Rotationsgriffe oder Mehrfachauswahl ergaenzt werden koennen, ohne den GCode-Datenfluss zu duplizieren.

## Koordinatensystem

Die App verwendet Millimeter und absolute GRBL-Arbeitskoordinaten mit Ursprung links unten. Das entspricht der Arbeitsflaechen-Preview und dem Standardprofil der Creality CR Laser Falcon 10W mit maximal 400 x 415 mm.

SVG verwendet dagegen einen Ursprung links oben und eine nach unten laufende Y-Achse. Beim Import erfolgt deshalb genau eine Koordinatenkonvertierung nach links unten/Y nach oben. Das ist keine Benutzerspiegelung, sondern bewahrt zusammen mit dem Qt-Screen-Mapping die sichtbare Orientierung der Ursprungsdatei.

Rasterpixel werden in ihrer gespeicherten Reihenfolge beibehalten. Die Ursprungsdatei und ihre Pixel-/Vektordaten werden nicht veraendert.

## Transform-Reihenfolge

1. Originalmotiv laden und unveraendert speichern
2. SVG-Koordinaten einmalig in das GRBL-Koordinatensystem konvertieren
3. positive X-/Y-Skalierung anwenden
4. um den lokalen Motivursprung drehen
5. gedrehte Bounding Box auf ihre lokale linke untere Ecke normalisieren
6. mit X/Y im Arbeitsbereich positionieren
7. Arbeitsbereich pruefen
8. dieselben Punkte fuer Preview, Preflight und Vektor-GCode verwenden

Die Qt-Preview konvertiert diese Maschinenkoordinaten erst beim Zeichnen in Bildschirmkoordinaten. Im GCode findet keine weitere Y-Invertierung oder Rotation statt.

## Arbeitsbereichspruefung

Die Bounding Box des transformierten Motivs wird gegen den Arbeitsbereich geprueft. Liegt das Motiv ausserhalb, blockiert der Preflight den Start mit einer verstaendlichen Meldung.

## Einschraenkungen

- Raster-GCode ist weiterhin nicht implementiert und bleibt fuer Hardwarestarts blockiert.
- Freie Rotation ist moeglich; bei Rasterbildern wird die gedrehte Bitmap nur in der Preview dargestellt, da Raster-GCode noch fehlt.
- Es gibt bewusst keine automatische Spiegelung und keine negativen Skalierungswerte.
- Click-to-Move und CAM-Simulation sind nicht Bestandteil dieser Funktion.
