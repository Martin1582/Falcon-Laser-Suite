# SVG-Flaechenfuellung

## Datenfluss

SVG-Geometrie wird importiert und ueber `ArtworkTransform` in Arbeitsbereichskoordinaten gebracht.
Erst danach erzeugt `FillToolpath` die Fuellsegmente. Preview, Preflight und GCode verwenden dieselben
gespeicherten Segmente.

Die Ursprungsdatei wird nicht veraendert.

## Layer-Modi

Jeder Ausgabelayer besitzt einen eigenen Modus:

- `Kontur`
- `Fuellung`
- `Kontur + Fuellung`

Standard ist `Kontur`. Eine Fuellung wird niemals automatisch aktiviert.

Pro Layer werden Fuellabstand und Winkel gespeichert. Unterstuetzte Winkel sind `0`, `45` und
`90 Grad`; Standardabstand ist `0.08 mm`.

## Hatch-Algorithmus

1. Geschlossene Konturen erkennen.
2. Polygon fuer den gewaehlten Winkel in Scanraum drehen.
3. Parallele horizontale Scanlinien mit dem Layerabstand erzeugen.
4. Schnittpunkte mit den Polygonkanten sortieren.
5. Je zwei Schnittpunkte als inneres Segment speichern.
6. Segmente in Arbeitsbereichskoordinaten zurueckdrehen.
7. Fahrtrichtung pro Segment wechseln, um Serpentine-Fahrten zu erhalten.

Offene Pfade werden nicht gefuellt und blockieren den Preflight, sobald Fuellung aktiv ist.

## Kurzfristige Sicherheitsgrenze

SVG-Fuellung ist aktuell nur fuer einfache, einzelne geschlossene Flaechen ohne Loecher oder
verschachtelte Innenkonturen freigegeben. Sobald der Import offene Konturen oder verschachtelte
geschlossene Konturen erkennt, wird kein FillToolpath erzeugt. Preview und G-Code zeigen dann keine
Fuelllinien, und der Preflight blockiert den Start mit einer klaren Sicherheitsmeldung:

`SVG-Fuellung bei verschachtelten oder offenen Konturen aktuell nicht sicher unterstuetzt.`

Konturmodus bleibt fuer dieselbe SVG-Geometrie erlaubt. `Kontur + Fuellung` ist nur startfaehig,
wenn die Fuellung sicher erzeugt werden kann.

## Creality CR Laser Falcon 10W

Fuell-GCode nutzt die vorhandenen Layerwerte fuer Geschwindigkeit, Leistung und Durchgaenge.
Im Gravurmodus wird wie bei bestehenden Gravurpfaden `M4` verwendet. Die Arbeitsbereichspruefung
bleibt auf die aktuell eingestellte App-Arbeitsflaeche sowie das Falcon-Maximum 400 x 415 mm bezogen.

## Einschraenkungen und Roadmap

- Keine Rastergravur und keine PNG-/JPG-Fuellung.
- Loecher und verschachtelte Polygone werden kurzfristig blockiert, damit keine falsche Gravur entsteht.
- Selbstueberschneidende oder ungueltige Polygone koennen unerwartete Innenintervalle ergeben.
- Kreuzfuellung ist architektonisch als mehrere `FillToolpath`-Ebenen moeglich, aber noch nicht aktiv.
- Sehr kleine Abstaende erzeugen viele GCode-Zeilen und lange Laufzeiten.
- Langfristige Loesung: robuste Polygon-Differenz mit Even-Odd- oder Non-Zero-Fill-Rule, damit
  Innenkonturen als echte Aussparungen behandelt werden.
# Overscan

SVG-Fuellungen koennen pro Layer mit Overscan ausgegeben werden. Kontur-, Schnitt-, Markierungs-, Frame- und Arbeitsflaechenpfade bleiben unveraendert.

Der `FillToolpath` speichert fuer jede Hatch-Linie getrennt:

- Anfahrpunkt mit ausgeschaltetem Laser
- eigentlichen Gravurstart
- eigentliches Gravurende
- Auslaufpunkt mit ausgeschaltetem Laser

Im automatischen Modus wird der Falcon-10W-Ausgangswert aus der Gravurgeschwindigkeit berechnet:

`overscan_mm = clamp(speed_mm_min / 500, 2, 10)`

Zusaetzlich wird der physikalische Bremsweg bei einer konservativen Beschleunigungsannahme von 500 mm/s^2 als Untergrenze beruecksichtigt. Der Wert wird an jeder Linie auf die eingestellte App-Arbeitsflaeche begrenzt.

Der Laser wird erst am eigentlichen Gravurstart mit Leistung gefahren und vor dem Auslauf wieder mit `M5` abgeschaltet. Preview, Preflight und GCode verwenden dasselbe `FillToolpath`-Objekt.

Fuer eine spaetere Rasterpipeline soll dieselbe Overscan-Berechnung wiederverwendet werden. Rasterzeilen muessen ebenfalls Anfahrt, aktiven Bildbereich und Auslauf getrennt modellieren; eine zweite, unabhaengige Berechnung im Rasterrenderer ist zu vermeiden.
