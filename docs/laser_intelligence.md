# Laser Intelligence Engine

Die Laser Intelligence Engine bewertet importierte SVG-, PNG- und JPG-Motive fuer den Creality CR Laser Falcon 10W. Sie ist eine beratende Schicht: Maschinenlogik, GRBL-Kommunikation und JobController bleiben unveraendert.

## Architektur

- `geometry_analyzer.py` sammelt Geometrie-, Bezier- und Rastermetriken.
- `svg_bezier_analysis.py` liest originale SVG-Path-Daten und bewertet Cubic-/Quadratic-Bezierkurven.
- `raster_analysis.py` bewertet DPI, Kontrast, Helligkeit, Transparenz, Detaildichte und Rastermodus.
- `material_recommendations.py` enthaelt Falcon-10W-Startwerte fuer ausgewaehlte Materialien.
- `geometry_optimizer.py` erzeugt nur interne Arbeitskopien.
- `intelligence_report.py` vergleicht Original und Arbeitskopie.
- `laser_intelligence_engine.py` buendelt Analyse, Klassifikation, Qualitaet, Maschinenempfehlung, Materialempfehlung und Report.

## Bezieranalyse

SVG-Kurven werden zusaetzlich zu den bereits geflatteten Liniensegmenten aus den originalen `path d`-Daten gelesen. Erfasst werden:

- Cubic Bezier
- Quadratic Bezier
- Anzahl Kurvensegmente
- geschaetzte Kurvenlaenge
- minimaler Kruemmungsradius
- stark gekruemmte Bereiche
- empfohlene Flattening-Toleranz

Die Analyse veraendert keine Form. Eine tatsaechliche Konturvereinfachung passiert nur, wenn der Benutzer die Optimierungsoption aktiviert.

## Rasteranalyse

Rasterquellen werden anhand der importierten Graustufendaten bewertet:

- Pixelgroesse und DPI
- berechnete Groesse in mm
- Kontrast und mittlere Helligkeit
- Farbmodus und Transparenz
- Detaildichte
- empfohlener Linienabstand
- empfohlener Modus `grayscale` oder `dithering`

Fehlende DPI wird als Hinweis gemeldet. Bei niedriger effektiver Aufloesung warnt die Engine, blockiert den Start aber nicht.

## Materialempfehlungen Falcon 10W

Die Tabelle enthaelt Startwerte fuer:

- Lindenholz 2 mm
- Kunstleder
- Schiefer
- Pappe/Karton
- Sperrholz 3 mm

Gespeichert sind Gravur-Speed, Gravur-Power, Durchgaenge, Fill-Abstand, Overscan-Default, M3/M4-Empfehlung und Hinweise. Schnittwerte sind nur dort hinterlegt, wo ein konservativer Startwert sinnvoll ist. Benutzer- und Layerwerte werden nicht automatisch ueberschrieben; Abweichungen erscheinen nur als Hinweis im Preflight.

## Original vs. Arbeitskopie

Der Report zeigt:

- Pfade, Segmente, Knoten
- geschaetzte GCode-Zeilen
- geschaetzte Laufzeit
- angewendete Optimierungen
- Segment-, GCode- und Laufzeitreduktion
- Detailverlust-Risiko

Originaldaten bleiben unveraendert. Die Arbeitskopie wird nur intern fuer Preview, Preflight und GCode genutzt, wenn die passende Optimierung aktiv ist.

## Grenzen

Alle Empfehlungen sind Startwerte fuer den Creality CR Laser Falcon 10W. Materialcharge, Fokus, Luftassist, Absaugung, Oberflaeche und GRBL-Konfiguration koennen das Ergebnis stark beeinflussen. Vor produktiven Jobs bleiben Frame, Dry Run und Materialtest Pflicht.
