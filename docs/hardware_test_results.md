# Hardwaretest-Ergebnisse

Diese Datei dokumentiert nachvollziehbare Hardwaretests. Offene Tests sind bewusst als `offen / nicht validiert` markiert. Ohne realen Dry-Run mit deaktiviertem Laser wird kein Test als bestanden gewertet.

## Lauf HT-2026-05-26-001

- Datum: 2026-05-26
- App-Version / Commit: Arbeitsbaum lokal, Commit nicht festgelegt
- Maschine: offen
- Controller: offen
- Firmware: offen
- Profil: offen
- Baudrate: offen
- Tester: offen
- Sicherheitsstatus: M5/S0 muss vor Testbeginn bestaetigt werden
- Gesamtergebnis: offen / nicht validiert

### Testfall

- ID: HT-CONNECT-001
- Name: Verbindungstest
- Vorbereitung: Maschine per USB anschliessen, Laser deaktivieren, korrektes Profil und COM-Port auswaehlen.
- Schritte: Verbinden, Status abfragen, trennen.
- Erwartetes Ergebnis: Verbindung wird hergestellt oder liefert klare Fehlermeldung; Disconnect gibt Port frei.
- Tatsaechliches Ergebnis: offen / nicht validiert
- Ergebnis: offen
- Beobachtungen:
- Logauszug:
- Folgeaufgaben: Mit echter Maschine ausfuehren.

### Testfall

- ID: HT-HOMING-001
- Name: Homing und Profilregel
- Vorbereitung: Profil mit `homing_required=true`, Maschine verbunden, Laser deaktiviert.
- Schritte: Start ohne Homing versuchen, danach Homing ausfuehren und Preflight erneut pruefen.
- Erwartetes Ergebnis: Start ohne Homing wird blockiert; nach Homing ist Preflight nicht wegen Homing blockiert.
- Tatsaechliches Ergebnis: offen / nicht validiert
- Ergebnis: offen
- Beobachtungen:
- Logauszug:
- Folgeaufgaben: Mit echter Maschine ausfuehren.

### Testfall

- ID: HT-FRAME-001
- Name: Frame ohne Laser
- Vorbereitung: GCode/Testjob mit bekannten Grenzen, Laser aus (`M5`, `S0`).
- Schritte: Frame ausloesen, Bewegung und Log beobachten.
- Erwartetes Ergebnis: Rahmenfahrt nutzt Job-/Arbeitsbereichsgrenzen; keine Laserleistung > 0.
- Tatsaechliches Ergebnis: offen / nicht validiert
- Ergebnis: offen
- Beobachtungen:
- Logauszug:
- Folgeaufgaben: Mit echter Maschine ausfuehren.

### Testfall

- ID: HT-DRYRUN-001
- Name: Langer Dry Run
- Vorbereitung: Langer Testjob mit `M5`/`S0`, freie Arbeitsflaeche.
- Schritte: Dry Run starten und bis Ende laufen lassen.
- Erwartetes Ergebnis: UI bleibt bedienbar, JobState endet `completed`, MachineState wird wieder `idle`.
- Tatsaechliches Ergebnis: offen / nicht validiert
- Ergebnis: offen
- Beobachtungen:
- Logauszug:
- Folgeaufgaben: Mit echter Maschine ausfuehren.

### Testfall

- ID: HT-PAUSE-RESUME-001
- Name: Pause/Resume waehrend Job
- Vorbereitung: Langer Dry Run laeuft.
- Schritte: Pause ausloesen, Hold abwarten, Resume ausloesen.
- Erwartetes Ergebnis: `!` und `~` werden als Realtime-Kommandos ohne `ok`-Pflicht gesendet; JobState wechselt `streaming -> paused -> streaming`.
- Tatsaechliches Ergebnis: offen / nicht validiert
- Ergebnis: offen
- Beobachtungen:
- Logauszug:
- Folgeaufgaben: Mit echter Maschine ausfuehren.

### Testfall

- ID: HT-STOP-RUN-001
- Name: Stop waehrend Running
- Vorbereitung: Langer Dry Run laeuft.
- Schritte: Stop ausloesen.
- Erwartetes Ergebnis: Kontrollierter Stop leert Queue, sendet Reset priorisiert, JobState wird `stopped` oder `aborted`, keine weitere GCode-Zeile wird gesendet.
- Tatsaechliches Ergebnis: offen / nicht validiert
- Ergebnis: offen
- Beobachtungen:
- Logauszug:
- Folgeaufgaben: Mit echter Maschine ausfuehren.

### Testfall

- ID: HT-STOP-HOLD-001
- Name: Stop waehrend Hold
- Vorbereitung: Langer Dry Run ist per Feed Hold pausiert.
- Schritte: Stop ausloesen.
- Erwartetes Ergebnis: Kontrollierter Stop beendet Jobstreaming, Queue wird geleert, UI bleibt bedienbar, Re-Homing wird verlangt.
- Tatsaechliches Ergebnis: offen / nicht validiert
- Ergebnis: offen
- Beobachtungen:
- Logauszug:
- Folgeaufgaben: Mit echter Maschine ausfuehren.

### Testfall

- ID: HT-ESTOP-RUN-001
- Name: Emergency Stop waehrend Running
- Vorbereitung: Langer Dry Run laeuft.
- Schritte: Sicherheitsstopp ausloesen.
- Erwartetes Ergebnis: Emergency Stop wird priorisiert gesendet, JobState wird `aborted`, MachineState geht in Alarm/Error-Recovery-Pfad.
- Tatsaechliches Ergebnis: offen / nicht validiert
- Ergebnis: offen
- Beobachtungen:
- Logauszug:
- Folgeaufgaben: Mit echter Maschine ausfuehren.

### Testfall

- ID: HT-ESTOP-HOLD-001
- Name: Emergency Stop waehrend Hold
- Vorbereitung: Langer Dry Run ist per Feed Hold pausiert.
- Schritte: Sicherheitsstopp ausloesen.
- Erwartetes Ergebnis: Emergency Stop wartet nicht hinter GCode, Queue wird sofort geleert, JobState `aborted`, bewusster Reset/Unlock/Re-Homing erforderlich.
- Tatsaechliches Ergebnis: offen / nicht validiert
- Ergebnis: offen
- Beobachtungen:
- Logauszug:
- Folgeaufgaben: Mit echter Maschine ausfuehren.

### Testfall

- ID: HT-DISCONNECT-JOB-001
- Name: Disconnect waehrend Job
- Vorbereitung: Langer Dry Run laeuft.
- Schritte: Disconnect ausloesen.
- Erwartetes Ergebnis: Job wird abgebrochen, Queue wird verworfen, Port wird geschlossen, UI bleibt bedienbar.
- Tatsaechliches Ergebnis: offen / nicht validiert
- Ergebnis: offen
- Beobachtungen:
- Logauszug:
- Folgeaufgaben: Mit echter Maschine ausfuehren.

### Testfall

- ID: HT-PROFILE-001
- Name: Profilwechsel / zwei Profile
- Vorbereitung: Profil A Standardbaudrate/normaler Arbeitsbereich, Profil B falsche Baudrate oder kleinerer Arbeitsbereich.
- Schritte: Profil A testen, trennen, Profil B testen, zurueck auf Defaultprofil wechseln.
- Erwartetes Ergebnis: Profilwerte beeinflussen Baudrate, Arbeitsbereich, Homing-Regel und Preflight; Profilwechsel bei aktiver Verbindung wird blockiert.
- Tatsaechliches Ergebnis: offen / nicht validiert
- Ergebnis: offen
- Beobachtungen:
- Logauszug:
- Folgeaufgaben: Mit echter Maschine ausfuehren.

### Testfall

- ID: HT-PROFILE-CORRUPT-001
- Name: Beschaedigtes Profil
- Vorbereitung: Backup von `machine_profiles.json`, danach Testdatei absichtlich beschaedigen.
- Schritte: App starten.
- Erwartetes Ergebnis: App nutzt Defaultprofil, loggt Ladefehler, kein Hardwarestart ohne gueltiges Profil.
- Tatsaechliches Ergebnis: offen / nicht validiert
- Ergebnis: offen
- Beobachtungen:
- Logauszug:
- Folgeaufgaben: In separater Testumgebung ausfuehren.

## Hardwaretest Arbeitsflaechen-Abtastmodus Falcon 10W

- Datum: 2026-06-05
- App-Version/Commit: `8c3b095` auf Branch `master`, Arbeitsstand mit lokalen Fixes
- Maschine: Creality CR Laser Falcon 10W
- Port/Baudrate: COM3 / 115200
- Profil: Creality CR Laser Falcon 10W
- Profil-Arbeitsbereich: 400.0 x 415.0 mm
- Eingestellte App-Arbeitsflaeche: 110.0 x 110.0 mm
- Laserleistung: 5 Prozent
- GRBL-Parameter: `$30=1000.0`, `$32=1.0`, `$130=400.0`, `$131=415.0`, `$20=0.0`, `$22=1.0`
- Logdatei: `hardware_falcon_work_area_scan_test.log`

### Ergebnis

- Ergebnis: bestanden
- Arbeitsflaechenquelle: bestanden. Der Scan nutzte `X110.000`/`Y110.000`; im Testlog erschienen keine Scanbefehle mit `X400.000` oder `Y415.000`.
- Laser 5 Prozent: bestanden. Gesendet wurde `M3 S50`; waehrend der Bewegung meldete GRBL `FS:1000,50`.
- Bewegungsmodus: bestanden. Scanbewegungen wurden als `G1` gesendet, nicht als `G0`.
- Stop-Verhalten: bestanden. Stop deaktivierte den Modus, es wurden keine weiteren Scansegmente nachgelegt, `M5`/`S0` wurde gesendet.
- Home nach Stop: bestanden. Nach Stop meldete GRBL `Idle`, `Home` war erlaubt und `$H` wurde erfolgreich ausgefuehrt.

### Gesendete relevante Befehle

```gcode
$$
G21
G90
M5
S0
M3 S50
G1 X0.000 Y0.000 F1000
G1 X110.000 Y0.000 F1000
G1 X110.000 Y110.000 F1000
M5
S0
$H
```

### Beobachtungen

- Stop wurde waehrend der zweiten Kante angefordert. Die bereits vom Controller akzeptierte `G1`-Bewegung lief bis zum Segmentende; danach wurden keine weiteren Scansegmente mehr gesendet.
- Final nach Stop: `MachineState=idle`, `JobState=idle`, `Home wieder erlaubt: ja`.
- Homing nach Stop endete mit `Idle|MPos:3.000,3.000,0.000|FS:0,0`.
- Der Controller gab waehrend `$H` wiederholt ESP/GPIO-Hinweise aus, quittierte aber mit `ok`; Homing wurde erfolgreich abgeschlossen.

## Falcon 10W Hardwaretest-Abarbeitungsstand

- Datum: 2026-06-05
- App-Version/Commit: lokaler Arbeitsstand, automatisierte Tests bestanden
- Maschine: Creality CR Laser Falcon 10W
- Profil: Creality CR Laser Falcon 10W, 400.0 x 415.0 mm
- Referenzlog: `hardware_falcon_work_area_scan_test.log`

### Validiert

- Arbeitsflaechenmodus mit App-Arbeitsflaeche 110.0 x 110.0 mm statt Profilmaximum 400.0 x 415.0 mm.
- 5-Prozent-Laserpunkt im Arbeitsflaechenmodus: `$30=1000`, `M3 S50`, `FS:1000,50`.
- Stop waehrend Arbeitsflaechenmodus: keine neue Runde, `M5`/`S0`, danach `MachineState=idle`.
- Home nach Stop: `$H` erfolgreich, final `Idle|MPos:3.000,3.000,0.000|FS:0,0`.

### Offen / noch nicht erneut hardwarevalidiert

- Pause/Resume waehrend langem Dry Run: Feed Hold, Resume, Statuspolling und JobState/MachineState ueber mehrere Minuten pruefen.
- Disconnect waehrend Idle, Hold und Dry Run: Queue-Ende, UI-Bedienbarkeit und Reconnect pruefen.
- Lange Dry Runs: Positionsupdates, kein UI-Freeze, Stop und Abschlusszustand pruefen.
- Fehlerzustaende: ungueltiger GCode, Alarm/Error, Controller-Reset und USB-Trennung mit Recovery dokumentieren.
- Live-Position waehrend Running/Hold: WPos/MPos/WCO im Log mit Preview-Marker vergleichen.

## Falcon 10W Idle-/Disconnect-Nachtest

- Datum: 2026-06-13
- App-Version/Commit: `8c3b095`, Branch `master`, lokaler Arbeitsstand
- Maschine: Creality CR Laser Falcon 10W
- Port/Baudrate: COM3 / 115200
- Profil-Arbeitsbereich: 400.0 x 415.0 mm
- Testart: Nicht bewegender Sicherheitstest, kein Laserjob
- GRBL-Parameter: `$30=1000.0`, `$31=0.0`, `$32=1.0`

### Testschritte

1. Mit COM3 verbinden und GRBL-Handshake ausfuehren.
2. Status und `$$` lesen.
3. Laser sicher mit `M5` und `S0` ausschalten.
4. Status erneut abfragen.
5. Im Idle trennen.

### Ergebnis

- Ergebnis: bestanden
- Tatsaechliches Verhalten: GRBL meldete `Idle|MPos:3.000,3.000,0.000|FS:0,0`.
- `M5` und `S0` wurden jeweils mit `ok` quittiert.
- Positionsquelle war `MPos`; Position X3.000/Y3.000/Z0.000 wurde gespeichert.
- Disconnect im Idle schloss COM3 sauber; Endzustand `connected=False`, `status=Disconnected`.
- Keine Bewegung, kein Reset, kein Homing und keine Laserleistung wurden ausgeloest.

### Relevanter Logauszug

```text
GRBL verbunden.
< <Idle|MPos:3.000,3.000,0.000|FS:0,0>
GRBL-Parameter gelesen: $30=1000.0, $31=0.0, $32=1.0.
> M5
< ok
> S0
< ok
Serial: Port geschlossen: COM3
GRBL getrennt.
```

### Folgeaufgaben

- Disconnect waehrend Hold/Dry Run, Pause/Resume und langer Dry Run benoetigen eine bestaetigte freie Arbeitsflaeche.
- USB-Abzug, Controller-Reset und Alarm-Recovery nur als beaufsichtigte Hardwaretests ausfuehren.

## Falcon 10W Hardware-Matrix Fortschreibung 2026-06-28

- Datum: 2026-06-28
- App-Version / Commit: lokaler Arbeitsstand, nicht committet
- Maschine: Creality CR Laser Falcon 10W
- Profil: Creality Falcon 10W, 400.0 x 415.0 mm
- Arbeitsflaeche: je Test explizit einzustellen, Startwert 110.0 x 110.0 mm empfohlen
- `$30`: vor Test per `GRBL Settings` dokumentieren
- `$32`: vor Test per `GRBL Settings` dokumentieren
- Sicherheitsstatus: Nur Dry Runs mit `M5`/`S0`; Laserleistung nur bei explizitem Niedrigleistungstest; kein brennbares Material bei Diagnosefahrten.
- Gesamtergebnis: offen / Hardware nicht in dieser Sitzung angesteuert

### Testgruppe langer Dry Run

- Erwartetes Verhalten: G-Code enthaelt keine Laserleistung, UI bleibt bedienbar, Statuspolling laeuft, Abschlusszustand `Idle`.
- Tatsaechliches Verhalten: offen
- Ergebnis: offen
- Logauszug: offen
- Folgeaufgabe: Mit freier Arbeitsflaeche und `M5`/`S0` ausfuehren.

### Testgruppe Pause / Resume

- Erwartetes Verhalten: `!` und `~` werden priorisiert gesendet, Status wechselt `Run -> Hold -> Run/Idle`, Position bleibt sichtbar.
- Tatsaechliches Verhalten: offen
- Ergebnis: offen
- Logauszug: offen
- Folgeaufgabe: WPos in Run und Hold mit Preview-Kopfmarker vergleichen.

### Testgruppe Stop / Home nach Stop

- Erwartetes Verhalten: Stop leert wartende Queue, sendet Reset/Abbruch priorisiert, Laser aus, Homing erst nach definiertem Zustand erneut erlauben.
- Tatsaechliches Verhalten: Arbeitsflaechenmodus 110 x 110 bereits am 2026-06-05 bestanden; langer Dry-Run-Stop noch offen.
- Ergebnis: teilweise validiert / offen
- Logauszug: siehe `hardware_falcon_work_area_scan_test.log`
- Folgeaufgabe: Stop waehrend langem Dry Run wiederholen und Home danach dokumentieren.

### Testgruppe Disconnect

- Erwartetes Verhalten: Disconnect bricht aktive Queue ab, sendet Laser-Aus soweit moeglich, Port wird freigegeben, UI bleibt bedienbar.
- Tatsaechliches Verhalten: Idle-Disconnect am 2026-06-13 bestanden; Disconnect waehrend Hold/Dry Run offen.
- Ergebnis: teilweise validiert / offen
- Logauszug: siehe Idle-/Disconnect-Nachtest
- Folgeaufgabe: Disconnect waehrend Hold und waehrend Dry Run getrennt testen.

### Testgruppe Live-WPos Run / Hold

- Erwartetes Verhalten: Preview-Kopfmarker nutzt echte `WPos`; wenn nur `MPos` + `WCO` geliefert werden, nutzt die App `WPos (MPos-WCO)`. Reines `MPos` bleibt Diagnose und verschiebt den Arbeitsbereichsmarker nicht.
- Tatsaechliches Verhalten: automatisiert abgesichert; Hardwarevergleich offen.
- Ergebnis: offen
- Logauszug: offen
- Folgeaufgabe: Statuszeilen mit `WPos`, `MPos` und `WCO` im Log dokumentieren.

### Testgruppe Frame / Dry Run / Fehlerzustaende

- Erwartetes Verhalten: Frame faehrt ohne Laser (`M5`/`S0`), Dry Run entfernt Laserbefehle, ungueltiger G-Code wird vor Hardwarestart blockiert.
- Tatsaechliches Verhalten: automatisiert abgesichert; Hardwarematrix offen.
- Ergebnis: offen
- Logauszug: offen
- Folgeaufgabe: Ungueltigen G-Code, Alarm/Error und Controller-Reset nur beaufsichtigt testen.
