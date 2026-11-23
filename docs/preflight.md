# Preflight

Vor jedem echten Hardwarestart muss der Preflight bestaetigt werden. Der Start ist nur erlaubt, wenn keine blockierenden Fehler vorliegen.

Geprueft werden unter anderem:

- Maschine verbunden
- Maschinenzustand `idle`
- kein `paused`, `running`, `stopping`, `alarm` oder `error`
- G-Code vorhanden
- aktive Layer vorhanden
- Arbeitsbereich eingehalten
- Laserleistung und Geschwindigkeit plausibel
- Homing gemaess Maschinenprofil
- Arbeitsbereich, Port und Baudrate aus aktivem Maschinenprofil
- sichere SVG-Fuellung: offene oder verschachtelte Konturen blockieren Fill-Jobs

Wenn ein Maschinenprofil Homing optional erlaubt und keine Referenzfahrt erkannt wurde, muss der Nutzer im Preflight bewusst bestaetigen, dass ohne Homing gestartet werden soll. Diese Entscheidung wird nicht global gespeichert.

Das aktive Maschinenprofil wird im Preflight angezeigt, damit nachvollziehbar bleibt, welche Homing-Regel, Arbeitsflaeche und Kommunikationsparameter verwendet werden.

## Gravur-Sicherheitscheck Falcon 10W

Vor echter Gravur auf dem Creality CR Laser Falcon 10W muss die folgende Kette bewusst geprueft
werden:

1. Falcon-10W-Profil aktiv, Arbeitsflaeche plausibel und COM-Port korrekt.
2. Maschine verbunden, Status `Idle`, keine Alarm-/Hold-/Error-Meldung.
3. Homing durchgefuehrt; bei optionalem Homing nur nach bewusster Preflight-Bestaetigung starten.
4. `M5` und `S0` vor Bewegung/Jobstart im Log bestaetigt.
5. Motivposition, Bounding Box, Nullpunkt und Kopfmarker in WPos-Arbeitskoordinaten plausibel.
6. Layerwerte fuer Leistung, Geschwindigkeit und Durchgaenge gegen Material pruefen.
7. Preflight ohne Blocker; Warnungen bewusst bewerten.
8. Frame oder Dry Run ohne Laser ausfuehren.
9. Stop und Sicherheitsstopp erreichbar halten.
10. Nach jedem Diagnose- oder Niedrigleistungstest erneut `M5`/`S0` senden oder bestaetigen.
