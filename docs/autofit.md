# AutoFit / AutoScale

## Verhalten

Importierte Motive werden automatisch proportional in den verfuegbaren Arbeitsbereich eingepasst.

Unterstuetzt:

- SVG / Vektorquellen
- PNG / JPG / JPEG Rasterquellen

## Regeln

- Das Seitenverhaeltnis bleibt immer erhalten.
- Es wird nicht beschnitten.
- Es wird nicht verzerrt.
- Kleinere Motive werden nicht automatisch vergroessert.
- Groessere Motive werden proportional verkleinert.
- Die Standardposition ist zentriert.
- Das Ergebnis wird als `ArtworkTransform` gespeichert und nicht nur in Preview- oder GCode-Pfaden versteckt.

Beispiel:

- Arbeitsbereich: `400 x 415 mm`
- Motiv: `600 x 800 mm`
- Ergebnis: `311.2 x 415.0 mm`
- Skalierung: `51.9 %`
- Position: `zentriert`

## Preflight

Der Preflight zeigt bei importierten Quellen:

- Quelle und Typ
- Originalgroesse
- aktuelle Groesse
- Position X/Y
- Skalierungsfaktor
- Arbeitsbereich OK / ueberschritten

Wenn keine Skalierung noetig war, zeigt der Preflight, dass das Motiv vollstaendig in den Arbeitsbereich passt.

## Einschraenkungen

Rasterbilder bleiben aktuell Preview-/Preflight-faehig, echter Hardwarestart bleibt aber blockiert, bis Rastergravur-GCode implementiert ist.

Weitere Details stehen in `docs/artwork_positioning.md`.
