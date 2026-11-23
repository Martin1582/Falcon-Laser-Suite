# Importformate

## Unterstuetzte Quellen

- SVG: Vektorquelle fuer Pfad-/Schnitt- und Gravurjobs.
- PNG: Rasterquelle fuer spaetere Rastergravur.
- JPG/JPEG: Rasterquelle fuer spaetere Rastergravur.

## Raster vs. Vektor

SVG-Dateien werden als Vektordaten importiert. Unterstuetzte SVG-Geometrien werden in Pfade umgewandelt, in der Preview als Layerpfade angezeigt und koennen wie bisher G-Code erzeugen.

PNG- und JPG-Dateien werden als Rasterbilder importiert. Die App liest Pixelgroesse, DPI, eine sinnvolle Groesse in Millimetern und Graustufendaten. Rasterbilder werden in der Preview mit Bounding Box angezeigt und im Preflight als Rasterquelle aufgefuehrt.

Alle importierten Quellen laufen durch AutoFit. Groessere Motive werden proportional verkleinert und zentriert, kleinere Motive behalten ihre Originalgroesse. Details stehen in `docs/autofit.md`.

Positionierung und Skalierung laufen ueber ein gemeinsames Transform-Modell. Preview, Preflight und GCode duerfen keine eigenen, abweichenden Skalierungsdaten verwenden. Details stehen in `docs/artwork_positioning.md`.

## Aktuelle Einschraenkung

Rastergravur-GCode ist noch nicht implementiert. Deshalb blockiert der Preflight echte Hardwarestarts mit Rasterquellen eindeutig mit:

`Rastergravur-GCode noch nicht verfuegbar.`

Das verhindert, dass ein importiertes PNG/JPG faelschlich als startbereiter Job wirkt.

## Empfohlener Workflow

1. Fuer Schnitt- und Pfadarbeiten SVG verwenden.
2. PNG/JPG importieren, um Groesse, Preview, Layer und Preflight-Verhalten zu pruefen.
3. Hardwarestart mit Rasterquellen erst verwenden, wenn eine dedizierte Raster-GCode-Erzeugung implementiert und hardwarevalidiert ist.

## Fehlerbehandlung

Die Import-Pipeline meldet:

- nicht unterstuetzte Formate
- beschaedigte Rasterdateien
- SVG-Dateien ohne unterstuetzte Pfade
- fehlende DPI-Angaben als Warnung mit 96-DPI-Fallback
- sehr grosse Rasterbilder als Warnung
- Transparenz in Rasterbildern als Graustufen-Hinweis
