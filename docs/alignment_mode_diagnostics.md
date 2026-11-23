# Material-Ausrichtmodus Diagnose

## Aktivierung

Der Ausrichtmodus verwendet `M3`, nicht `M4`.

Der S-Wert wird aus GRBL `$30` berechnet:

- `$30=1000`, 5 Prozent -> `S50`
- `$30=255`, 5 Prozent -> `S13`

Wenn `$30` noch nicht bekannt ist, fragt der Controller vor dem Aktivieren `$$` ab und speichert `$30`, `$31` und `$32`.

## Logging

Beim Aktivieren werden geloggt:

- `alignment mode requested`
- Maschinenstatus
- Pointer-Leistung in Prozent
- `$30` / S-Max
- `$31`, falls bekannt
- `$32`, falls bekannt
- berechneter S-Wert
- gesendeter Befehl, z. B. `M3 S50`
- ob ein Laser-Off-Befehl direkt gesendet wurde

Normales Aktivieren sendet kein direktes `M5` oder `S0`. `M5`/`S0` werden nur beim Deaktivieren, bei Safety-Pfaden oder im Testmodus-Ende gesendet.

## Sicherer Testmodus

Der Testmodus sendet bei idle Maschine:

1. `M3 S...`
2. wartet maximal 2 Sekunden
3. sendet automatisch `M5`
4. sendet automatisch `S0`

Der Testmodus ist keine Dauerfunktion und ersetzt nicht den normalen Ausrichtmodus.

## Wenn kein Punkt sichtbar ist

Einige GRBL-/Lasermodule zeigen `M3 S...` im Stillstand nicht sichtbar oder erst bei Bewegung. Dann:

1. Schutzbrille tragen, freie Flaeche sicherstellen.
2. `M3 S50` nur bei passendem `$30=1000` testen.
3. Optional minimale Bewegung testen, z. B. `G91`, `G1 X0.5 F100`, `G90`.
4. Danach immer `M5` und `S0` senden.

Bei `$31` groesser als berechneter S-Wert kann der Laserpunkt unsichtbar bleiben. Die App loggt diesen Fall, erhoeht die Leistung aber nicht automatisch.
