# Hardware Test Plan

Alle Tests sind als Trockenlauf geplant. Laserleistung muss deaktiviert bleiben: `M5`, `S0`, niedrige Testdaten oder abgestecktes/deaktiviertes Lasermodul verwenden. Schutzbrille und freie Arbeitsflaeche bleiben trotzdem Pflicht.

Versionierte Ergebnislaeufe werden in `docs/hardware_test_results.md` dokumentiert. Ein Test gilt erst als bestanden, wenn dort Datum, App-Version/Commit, Maschine, Controller, Profil, Baudrate, Sicherheitsstatus, tatsaechliches Ergebnis und Log/Beobachtung eingetragen sind.

## Pflichtcheck vor echter Gravur

- Creality-CR-Laser-Falcon-10W-Profil aktiv.
- Arbeitsflaeche entspricht Material und liegt innerhalb 400 x 415 mm.
- GRBL Settings dokumentiert: insbesondere `$30` und `$32`.
- Homing durchgefuehrt und Status `Idle`.
- `M5` und `S0` vor Start im Log bestaetigt.
- Motiv, Bounding Box, Nullpunkt und Kopfmarker stimmen in WPos-Arbeitskoordinaten ueberein.
- Preflight ohne Blocker; Warnungen bewertet.
- Frame oder Dry Run ohne Laser erfolgreich.
- Stop und Sicherheitsstopp sind erreichbar.
- Nach jedem Test erneut Laser-Aus (`M5`/`S0`) senden oder bestaetigen.

## Verbindungstest

- Vorbereitung: Maschine per USB anschliessen, Laser deaktivieren, korrekten COM-Port auswaehlen.
- Schritte: Verbinden ausloesen, Statusanzeige und Maschinenlog beobachten, danach sauber trennen.
- Erwartetes Verhalten: Verbindung wird hergestellt, Status wechselt auf `idle` oder eine klare Alarm-/Fehlermeldung, Trennen schliesst den Port.
- Akzeptanzkriterium: Kein UI-Freeze, kein haengender Port nach Disconnect.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Homing-Regel im Maschinenprofil

- Vorbereitung: Maschinenprofil mit `homing_required=true` verwenden, Maschine verbunden aber nicht gehomed.
- Schritte: Hardwarestart mit Testjob und `M5`/`S0` ausloesen.
- Erwartetes Verhalten: Preflight blockiert den Start wegen fehlender Referenzfahrt.
- Akzeptanzkriterium: Kein G-Code wird gesendet, Log nennt Homing erforderlich.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Auto-Home nach erfolgreichem Einzelstueck - Dry Run

- Datum:
- App-Version/Commit:
- Maschine: Creality CR Laser Falcon 10W
- Profil: Creality CR Laser Falcon 10W
- `$22` Homing:
- `$30`:
- `$32`:
- Vorbereitung: Maschine verbinden, homen, Laser sicher deaktivieren, Job-Art `Einzelstueck`, Option `Nach erfolgreichem Einzelstueck automatisch Home anfahren` aktivieren.
- Schritte: Kurzen Dry Run starten und bis zum normalen Abschluss laufen lassen.
- Erwartetes Verhalten: Job endet `completed`, App loggt Auto-Home aktiv, Sicherheitspruefung bestanden, `M5`, `S0`, danach `$H`.
- Akzeptanzkriterium: Keine Laserleistung beim Home, Maschine faehrt nach Jobende in Home-Position, Status danach `idle/bereit`.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Auto-Home nach erfolgreichem Einzelstueck - echter kurzer Job

- Datum:
- App-Version/Commit:
- Maschine: Creality CR Laser Falcon 10W
- Profil: Creality CR Laser Falcon 10W
- Material:
- `$22` Homing:
- `$30`:
- `$32`:
- Vorbereitung: Geeignetes Restmaterial, Schutzbrille/Absaugung, sehr kurzer beaufsichtigter Gravurjob, Auto-Home aktiv.
- Schritte: Job starten, bis zum normalen Abschluss laufen lassen, Home-Fahrt beobachten.
- Erwartetes Verhalten: Nach erfolgreicher Gravur wird zuerst Laser-Aus (`M5/S0`) geloggt und gesendet, danach Homing (`$H`).
- Akzeptanzkriterium: Keine Bewegung ausserhalb erwarteter Homing-Sequenz, kein Alarm, Status danach bereit.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Auto-Home Negativtests

- Datum:
- App-Version/Commit:
- Maschine: Creality CR Laser Falcon 10W
- Profil: Creality CR Laser Falcon 10W
- `$22` Homing:
- `$30`:
- `$32`:
- Vorbereitung: Langer Dry Run ohne Laser, Auto-Home aktiv.
- Faelle:
  - Stop waehrend Job -> kein Auto-Home.
  - Emergency Stop -> kein Auto-Home.
  - Alarm/Error erzeugen -> kein Auto-Home.
  - Disconnect waehrend Job -> kein Auto-Home.
- Erwartetes Verhalten: In jedem Fall Laser-Aus/Stop-Logik bleibt aktiv, Auto-Home wird mit Grund uebersprungen, kein `$H` nach Abbruch/Fehler.
- Akzeptanzkriterium: Log enthaelt `Auto-Home uebersprungen` mit Grund; Queue/Port bleiben recoverbar oder verlangen klaren Reset/Re-Homing.
- Ergebnis Stop: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:
- Ergebnis Emergency Stop: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:
- Ergebnis Alarm/Error: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:
- Ergebnis Disconnect: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Optionales Homing bewusst bestaetigen

- Vorbereitung: Separates Testprofil mit `homing_required=false`, Maschine verbunden aber nicht gehomed, Laser aus.
- Schritte: Hardwarestart ausloesen, Preflight-Warnung lesen, Start ohne Homing bewusst bestaetigen.
- Erwartetes Verhalten: Startbutton wird erst nach bewusster Bestaetigung aktiv; Log dokumentiert Start ohne Homing.
- Akzeptanzkriterium: Keine globale Deaktivierung von Homing, Entscheidung gilt nur fuer diesen Preflight.
- Risiko/Hinweis: Nur mit sehr kleinem `M5`/`S0`-Dry-Run und freier Arbeitsflaeche testen.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Maschinenprofil wechseln

- Vorbereitung: Mindestens zwei Profile im Profil-Editor anlegen, Laser deaktivieren.
- Schritte: Profil A auswaehlen, Arbeitsbereich/Port/Baudrate pruefen; Profil B auswaehlen und dieselben Anzeigen pruefen.
- Erwartetes Verhalten: Aktives Profil wird gespeichert und nach App-Neustart wieder geladen.
- Akzeptanzkriterium: Preflight und Maschinenstatus verwenden das sichtbare aktive Profil.
- Risiko/Hinweis: Vor einem echten Hardwarestart immer COM-Port und Arbeitsbereich gegen die reale Maschine pruefen.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Zwei-Profil-Smoke-Test

- Vorbereitung: Profil A mit Standardbaudrate und normalem Arbeitsbereich anlegen/auswaehlen. Profil B mit abweichender Baudrate oder kleinerem Arbeitsbereich anlegen. Laser deaktivieren (`M5`, `S0`).
- Schritte: App starten, Profil A auswaehlen, Ports aktualisieren, verbinden, Status abfragen, Preflight fuer kleinen Testjob oeffnen, Frame ohne Laser pruefen, trennen. Danach Profil B auswaehlen und dieselben Schritte wiederholen.
- Erwartetes Verhalten: Aktive Profilanzeige, Arbeitsbereich, Baudrate, Homing-Regel und Preflight-Werte entsprechen jeweils dem ausgewaehlten Profil.
- Akzeptanzkriterium: Verbindung nutzt die Profil-Baudrate; Frame/Preflight/Startvalidierung verwenden den aktiven Profil-Arbeitsbereich; Maschinenlog nennt Profil und Homing-Regel.
- Risiko/Hinweis: Profilwechsel nur im getrennten Zustand durchfuehren. Bei abweichender Baudrate ist eine fehlgeschlagene Verbindung akzeptiert, solange die App nicht einfriert und sauber getrennt bleibt.
- Ergebnis Profil A: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:
- Ergebnis Profil B: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Profilwechsel waehrend aktiver Verbindung

- Vorbereitung: Maschine verbunden, Laser deaktiviert, mindestens zwei Profile vorhanden.
- Schritte: Bei aktiver Verbindung ein anderes Profil auswaehlen oder den Profil-Editor oeffnen.
- Erwartetes Verhalten: Profilwechsel wird blockiert; bestehende Verbindung bleibt unveraendert; Nutzerhinweis und Maschinenlog nennen den blockierten Wechsel.
- Akzeptanzkriterium: Aktives Profil, Baudrate und Arbeitsbereich bleiben unveraendert. Kein Reconnect/Hot-Reload erfolgt automatisch.
- Risiko/Hinweis: Dieses konservative Verhalten verhindert, dass Serial-Konfiguration und UI-Profil auseinanderlaufen.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Profilwechsel waehrend laufendem Job

- Vorbereitung: Langer Dry-Run-Job ohne Laser laeuft, mindestens zwei Profile vorhanden.
- Schritte: Waehrend `running` ein anderes Profil auswaehlen oder den Profil-Editor oeffnen.
- Erwartetes Verhalten: Profilwechsel wird blockiert; Jobstreaming laeuft unveraendert weiter oder kann normal gestoppt werden.
- Akzeptanzkriterium: Kein weiterer Profilwert wird uebernommen, keine UI-Blockade, Maschinenlog dokumentiert die Blockierung.
- Risiko/Hinweis: Nicht mit aktivem Laser testen; nur Dry-Run mit `M5`/`S0`.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Profil mit anderer Baudrate

- Vorbereitung: Testprofil mit abweichender Baudrate anlegen, passenden Controller ohne Laserleistung verbinden.
- Schritte: Profil auswaehlen, verbinden, Status abfragen, danach trennen.
- Erwartetes Verhalten: Controller-Verbindung nutzt die Baudrate des aktiven Profils.
- Akzeptanzkriterium: Verbindung ist stabil oder liefert eine klare Fehlermeldung ohne UI-Freeze.
- Risiko/Hinweis: Falsche Baudrate ist ein erwarteter Negativtest und darf nicht zu haengenden Threads fuehren.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Falsche Baudrate im Profil

- Vorbereitung: Testprofil mit absichtlich falscher Baudrate anlegen, Laser deaktivieren.
- Schritte: Profil auswaehlen, verbinden, Statusabfrage abwarten, danach trennen oder Reconnect auf korrektes Profil pruefen.
- Erwartetes Verhalten: Verbindung schlaegt verstaendlich fehl oder Status bleibt ungueltig; App bleibt bedienbar.
- Akzeptanzkriterium: Kein UI-Freeze, Port wird nach Disconnect wieder freigegeben, Log nennt Profil/Baudrate.
- Akzeptiertes Fehlverhalten: Controller antwortet nicht oder liefert Timeout; das ist bei falscher Baudrate erwartbar.
- Recovery: Trennen, korrektes Profil auswaehlen, neu verbinden.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Profil mit anderem Arbeitsbereich

- Vorbereitung: Testprofil mit kleinerem Arbeitsbereich anlegen, Testjob ohne Laser vorbereiten.
- Schritte: Profil auswaehlen, Preview und Preflight pruefen, Job ausserhalb des Arbeitsbereichs vorbereiten.
- Erwartetes Verhalten: Arbeitsbereich wird aus dem aktiven Profil uebernommen, Preflight blockiert Ueberschreitungen.
- Akzeptanzkriterium: Kein G-Code wird bei ueberschrittenem Arbeitsbereich gesendet.
- Risiko/Hinweis: Nur mit deaktiviertem Laser und kleiner Testgeometrie pruefen.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Ungueltiger Arbeitsbereich im Profil

- Vorbereitung: Profil-JSON manuell mit fehlendem oder ungueltigem Arbeitsbereich vorbereiten, Backup der Datei behalten.
- Schritte: App starten, Profil laden lassen, Preflight mit Testjob oeffnen.
- Erwartetes Verhalten: Fehlende Felder werden konservativ ergaenzt, unplausible Werte werden begrenzt oder Startvalidierung blockiert.
- Akzeptanzkriterium: Kein blinder Hardwarestart mit ungueltigem Arbeitsbereich.
- Akzeptiertes Fehlverhalten: Profil faellt auf Defaultwerte zurueck, wenn die Datei nicht sinnvoll reparierbar ist.
- Recovery: Profil im Editor korrigieren oder JSON-Backup wiederherstellen.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Beschaedigtes Profil-JSON

- Vorbereitung: Kopie von `machine_profiles.json` sichern, danach JSON absichtlich syntaktisch beschaedigen.
- Schritte: App starten.
- Erwartetes Verhalten: App faellt auf Defaultprofil zurueck und loggt den Ladefehler.
- Akzeptanzkriterium: Kein Crash, kein Hardwarestart ohne gueltiges Profil, korrupte Datei bleibt als `.corrupt` nachvollziehbar.
- Akzeptiertes Fehlverhalten: Individuelle Profile sind bis zur Reparatur nicht verfuegbar.
- Recovery: Backup der JSON-Datei zurueckspielen oder Profile neu anlegen.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Fehlende Profilfelder

- Vorbereitung: Profil-JSON mit altem/minimalem Profil ohne neue Felder vorbereiten.
- Schritte: App starten, Profil auswaehlen, Preflight oeffnen.
- Erwartetes Verhalten: Fehlende Felder erhalten sichere Defaults, insbesondere `homing_required=true`.
- Akzeptanzkriterium: Preflight und Startvalidierung nutzen Defaultwerte sichtbar und nachvollziehbar.
- Recovery: Profil im Editor einmal speichern, um die Felder vollstaendig zu schreiben.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Zurueck auf Defaultprofil wechseln

- Vorbereitung: Alternatives Testprofil ist aktiv, Maschine getrennt.
- Schritte: Defaultprofil auswaehlen, App neu starten, Preflight mit Testjob oeffnen.
- Erwartetes Verhalten: Defaultprofil bleibt aktiv gespeichert; konservative Homing-Regel ist wieder aktiv.
- Akzeptanzkriterium: Arbeitsbereich, Baudrate und Homing-Regel entsprechen dem Defaultprofil.
- Recovery: Falls nicht aktiv, Profil erneut auswaehlen und App neu starten.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Profil mit Portwechsel

- Vorbereitung: Profil mit `default_port` anlegen, Maschine an diesem Port verfuegbar machen.
- Schritte: Ports aktualisieren, Profil auswaehlen, Portauswahl pruefen, verbinden.
- Erwartetes Verhalten: Vorhandener Default-Port wird vorausgewaehlt; fehlender Port erzeugt keine Ausnahme.
- Akzeptanzkriterium: App bleibt bedienbar und loggt die Port-/Profilwahl nachvollziehbar.
- Risiko/Hinweis: Vor Bewegungstest Port und Maschinenname manuell gegenpruefen.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Emergency Stop waehrend Hold

- Vorbereitung: Dry-Run-Job ist per Feed Hold pausiert, Laser aus (`M5`/`S0`).
- Schritte: Emergency Stop/Sicherheitsstopp ausloesen.
- Erwartetes Verhalten: Ctrl-X wird sofort priorisiert gesendet, Queue wird geleert, Job wird als abgebrochen markiert.
- Akzeptanzkriterium: Keine weitere normale G-Code-Zeile nach Emergency Stop, UI bleibt bedienbar, Reconnect/Reset moeglich.
- Risiko/Hinweis: Controller verliert Homing-Referenz; danach zuerst Status pruefen und erneut homen.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Mehrfach Pause -> Stop

- Vorbereitung: Langer Dry-Run-Job ohne Laser laeuft.
- Schritte: Pause ausloesen, Hold bestaetigen, Resume, erneut Pause, danach Stop.
- Erwartetes Verhalten: Wiederholte Hold-Zustaende bleiben stabil; Stop beendet Streaming sofort.
- Akzeptanzkriterium: Kein Timeout, kein weiterer Jobstream nach Stop, Port bleibt reconnect-faehig.
- Risiko/Hinweis: Bewegungen nur in freiem Arbeitsbereich ausfuehren.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Mehrfach Pause -> Emergency Stop

- Vorbereitung: Langer Dry-Run-Job ohne Laser laeuft.
- Schritte: Pause ausloesen, Hold bestaetigen, Resume, erneut Pause, danach Emergency Stop.
- Erwartetes Verhalten: Emergency Stop unterbricht priorisiert und setzt Jobstatus auf abgebrochen.
- Akzeptanzkriterium: Kein UI-Freeze, keine weitere Jobzeile, Controller danach definiert resetten/reconnecten.
- Risiko/Hinweis: Nach Emergency Stop mechanische Lage und Homing neu pruefen.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## USB-Trennung waehrend Hold

- Vorbereitung: Dry-Run-Job ist per Feed Hold pausiert, Laser aus (`M5`/`S0`).
- Schritte: USB-Kabel ziehen oder Controller stromlos machen.
- Erwartetes Verhalten: Serial-Fehler wird geloggt, Job endet im Fehler-/Disconnect-Zustand, UI bleibt bedienbar.
- Akzeptanzkriterium: Kein haengender Thread, erneute Verbindung erst nach bewusstem Reconnect.
- Risiko/Hinweis: Nur ohne aktiven Laser und mit sicherer Maschinenposition testen.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Statuspolling

- Vorbereitung: Maschine verbunden und idle, Laser deaktiviert.
- Schritte: Mehrfach Status abfragen, optional waehrend kurzer manueller Bewegung erneut abfragen.
- Erwartetes Verhalten: Statusantworten werden geloggt, Positions-/Alarmstatus bleibt nachvollziehbar.
- Akzeptanzkriterium: Keine blockierende UI und keine unbehandelte Timeout-Exception.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Positionsanzeige bei Idle

- Vorbereitung: Maschine verbunden und idle, Laser deaktiviert (`M5`, `S0`).
- Schritte: Status abfragen und Positionsanzeige in der Statusleiste beobachten.
- Erwartetes Verhalten: X/Y/Z werden aus `MPos` oder `WPos` angezeigt; bei fehlender Position bleibt die Anzeige auf `--`.
- Akzeptanzkriterium: Keine normale `ok`-Pflicht fuer `?`, kein Timeout, UI bleibt bedienbar.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Positionsanzeige beim Jogging

- Vorbereitung: Maschine verbunden, gehomed, Laser deaktiviert, kleine Jog-Schritte verwenden.
- Schritte: X+/Y+ joggen und danach Status/Positionsanzeige beobachten.
- Erwartetes Verhalten: Positionswerte aendern sich nachvollziehbar passend zur Bewegung.
- Akzeptanzkriterium: Jogging bleibt nur in `idle` moeglich; Positionsanzeige aktualisiert ohne Logspam.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Positionsanzeige waehrend langem Dry Run

- Vorbereitung: Langer Dry-Run-Job mit `M5`/`S0`, freie Arbeitsflaeche.
- Schritte: Dry Run starten und Positionsanzeige waehrend `running` beobachten.
- Erwartetes Verhalten: Position wird moderat aktualisiert; Job-Streaming, Feed Hold, Resume und Stop bleiben bedienbar.
- Akzeptanzkriterium: Keine Statusquery-Timeouts, kein spuerbarer Streaming-Stau durch Positionspolling.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Positionsanzeige waehrend Gravurjob

- Vorbereitung: Kleiner Gravurjob als sicherer Testlauf, Laser sicher deaktiviert (`M5`, `S0`) oder Lasermodul getrennt, freie Arbeitsflaeche.
- Schritte: Gravurjob starten und Positionsanzeige in Statusleiste/Maschinenpanel waehrend `running` beobachten.
- Erwartetes Verhalten: X/Y/Z werden fortlaufend aus `<Run|MPos:...>` oder `<Run|WPos:...>` aktualisiert; `WPos` wird bevorzugt angezeigt.
- Akzeptanzkriterium: `?` erzeugt keine normale `ok`-Pflicht, Statuszeilen stoeren keine G-Code-`ok`-Zuordnung, Pause/Resume/Stop bleiben bedienbar.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Positionsanzeige waehrend Hold und nach Resume

- Vorbereitung: Langer Dry Run laeuft, Laser deaktiviert.
- Schritte: Pause/Feed Hold ausloesen, Positionsanzeige im Hold beobachten, Resume ausloesen.
- Erwartetes Verhalten: Position bleibt im Hold sichtbar; nach Resume aktualisiert sie weiter.
- Akzeptanzkriterium: `!`, `~` und `?` erwarten weiterhin keine normale `ok`-Antwort; kein UI-Freeze.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Positionsanzeige nach Disconnect

- Vorbereitung: Maschine verbunden, Position sichtbar.
- Schritte: Verbindung trennen.
- Erwartetes Verhalten: Positionsanzeige wechselt kontrolliert auf `--` oder unbekannt.
- Akzeptanzkriterium: Kein veralteter Positionswert wird als aktive Verbindung angezeigt.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Preview-Kopfposition und Arbeitsnullpunkt

- Vorbereitung: Maschine verbunden, gehomed, Laser aus (`M5`, `S0`), Arbeitsbereich frei.
- Schritte: Nach Homing Status abfragen und Log auf `MPos`, `WPos` oder `WCO` pruefen. Danach Arbeitsnullpunkt setzen, Status erneut abfragen und Preview beobachten.
- Erwartetes Verhalten: Der Kopfmarker nutzt `WPos`; falls nur `MPos` und `WCO` gemeldet werden, wird `WPos = MPos - WCO` verwendet. Reines `MPos` dient nur Diagnose und soll den Arbeitsbereichsmarker nicht verschieben.
- Akzeptanzkriterium: Bei `WPos X0 Y0` liegt der Marker exakt auf dem Preview-Nullpunkt links unten.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Preview-Kopfposition beim Jogging

- Vorbereitung: Maschine verbunden, Arbeitsnullpunkt gesetzt, Laser aus (`M5`, `S0`).
- Schritte: Von `WPos X0 Y0` aus klein X+ joggen, danach klein Y+ joggen. Preview und Log beobachten.
- Erwartetes Verhalten: X+ bewegt den Marker nach rechts; Y+ bewegt den Marker in der Preview nach oben. Keine doppelte Y-Invertierung.
- Akzeptanzkriterium: Position X0/Y0 faehrt optisch zum Nullpunkt; `MPos`/`WPos` beziehungsweise `WCO` werden im Log dokumentiert.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Jogging

- Vorbereitung: Maschine verbunden, gehomed, freie Arbeitsflaeche, Laser deaktiviert.
- Schritte: Kleine Jog-Bewegungen X+/X-/Y+/Y- ausloesen.
- Erwartetes Verhalten: Jogging ist nur in `idle` aktiv, Bewegungen bleiben klein und kontrolliert.
- Akzeptanzkriterium: Keine Aktion ausserhalb `idle`, Maschinenlog nennt ausgefuehrte/blockierte Jogs.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Frame ohne Laser

- Vorbereitung: Testjob mit bekannter Groesse vorbereiten, Maschine verbunden und gehomed, Laser deaktiviert.
- Schritte: Frame ausloesen und G-Code/Log auf `M5`/`S0` pruefen.
- Erwartetes Verhalten: Rahmen nutzt Jobgrenzen, Laserleistung bleibt sicher aus.
- Akzeptanzkriterium: Keine Materialbearbeitung, keine `S`-Leistung > 0 waehrend Frame.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Arbeitsflaeche abfahren

- Vorbereitung: Maschine verbunden und idle, Creality CR Laser Falcon 10W Profil aktiv, reale Maschinenflaeche 400 x 415 mm bekannt, App-Arbeitsbereich bewusst kleiner einstellen, z. B. 110 x 110 mm. Freie Arbeitsflaeche herstellen.
- Schritte: Toggle `Arbeitsflaeche abfahren` aktivieren und Maschinenbewegung/Log beobachten.
- Erwartetes Verhalten: Maschine faehrt ausschliesslich die aktuell in der App eingestellte Arbeitsflaeche ab: X0/Y0 -> X110/Y0 -> X110/Y110 -> X0/Y110 -> X0/Y0. Das Profil 400 x 415 mm darf diesen Scan nicht direkt vergroessern.
- Akzeptanzkriterium: Log nennt App-Arbeitsflaeche, Geschwindigkeit, `$30`, Pointer-Prozent, berechnetes `S`, `M3` und Bewegungsmodus `G1`. Bei `$30=1000` und 5% wird `M3 S50` gesendet; die Rahmenbewegungen sind `G1`, nicht `G0`; am Ende stehen `M5` und `S0`.
- Sicherheit: Test zuerst ohne Material, danach mit sichtbarem schwachem Laserpunkt pruefen. Stop ist jederzeit erreichbar; nach Ende muss `M5`/`S0` im Log stehen.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Arbeitsflaeche abfahren - Preview gegen Maschine

- Vorbereitung: App-Arbeitsbereich auf 110 x 110 mm setzen, Preview pruefen, Laser/Material sicher vorbereiten.
- Schritte: Arbeitsflaechenmodus starten und gefahrene Koordinaten im Log mit der Preview vergleichen. Danach mit 200 x 50 mm wiederholen.
- Erwartetes Verhalten: Preview-Arbeitsbereich, Bounding Box und Scanpfad verwenden dieselben Werte. 110 x 110 faehrt 110 x 110; 200 x 50 faehrt 200 x 50.
- Akzeptanzkriterium: Keine Koordinate aus `machine_profile.work_area_width=400` oder `work_area_height=415` wird fuer den Scan verwendet, solange die App-Arbeitsflaeche kleiner eingestellt ist.
- Ergebnis 110 x 110: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:
- Ergebnis 200 x 50: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Arbeitsflaeche abfahren - Laser 5 Prozent

- Vorbereitung: Creality CR Laser Falcon 10W verbunden und idle, Schutzbrille/Gehaeuse aktiv, App-Arbeitsflaeche klein setzen, z. B. 110 x 110 mm, `$30` und `$32` im Log pruefen.
- Schritte: Arbeitsflaechenmodus aktivieren und waehrend der `G1`-Bewegung den schwachen Laserpunkt beobachten.
- Erwartetes Verhalten: Vor Start wird `M5`/`S0` gesendet, dann `M3 S50` bei `$30=1000`, danach `G1`-Rahmenbewegungen, beim Beenden `M5`/`S0`.
- Akzeptanzkriterium: Laser ist waehrend `G1` sichtbar, aber schwach; bei `G0` darf kein Rahmenpfad im Scanlog erscheinen.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Arbeitsflaeche abfahren - Stop

- Vorbereitung: Arbeitsflaechenmodus aktiv, Maschine bewegt sich, Laser aus (`M5`, `S0`).
- Schritte: `Stop` waehrend einer Bewegung ausloesen.
- Erwartetes Verhalten: Modus wird deaktiviert, keine neue Runde wird gestartet, Queue wird geleert beziehungsweise keine weiteren Trace-Befehle werden nachgelegt. Ein bereits von GRBL akzeptiertes einzelnes `G1`-Segment kann bis zum Segmentende auslaufen; danach synchronisiert die App auf `Idle`.
- Akzeptanzkriterium: Log nennt automatische Sicherheitsabschaltung/Stop; Laser-Aus wird erneut gesendet oder bestaetigt; UI zeigt Modus aus; MachineState ist wieder `idle`, `Home` ist wieder freigegeben.
- UI-Hinweis: Statusmeldung erwartet: `Arbeitsflaechenmodus gestoppt - Laser aus - Home wieder moeglich`, sobald die Maschine `Idle` meldet. Falls Home blockiert bleibt, muss der Blockierungsgrund in Log/Status sichtbar sein.
- Risiko/Hinweis: Fuer sofortigen harten Abbruch `Sicherheitsstopp` verwenden; danach koennen Reset/Unlock/Re-Homing erforderlich sein.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Arbeitsflaeche abfahren - Emergency Stop

- Vorbereitung: Arbeitsflaechenmodus aktiv, Maschine bewegt sich, Laser aus (`M5`, `S0`).
- Schritte: `Sicherheitsstopp` ausloesen.
- Erwartetes Verhalten: Ctrl-X/Emergency-Pfad wird priorisiert, Modus endet, kein weiterer Trace-Befehl wird gesendet.
- Akzeptanzkriterium: Maschine stoppt definiert, UI zeigt Alarm/Sicherheitsstopp, erneutes Homing/Reset wird verlangt.
- Risiko/Hinweis: Sicherheitsstopp ist ein anderer Recovery-Pfad als normaler Stop. Danach mechanische Lage pruefen, ggf. Unlock/Reset ausfuehren und vor weiterer Bewegung neu homen.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Arbeitsflaeche abfahren - Deaktivieren

- Vorbereitung: Arbeitsflaechenmodus aktiv, Laser aus (`M5`, `S0`).
- Schritte: Toggle nach der ersten vollstaendigen Runde deaktivieren; danach erneut aktivieren und waehrend einer Bewegung deaktivieren.
- Erwartetes Verhalten: Nach Deaktivierung werden keine neuen Runden gestartet; UI und Log zeigen Modus aus und Laser aus.
- Akzeptanzkriterium: Keine Endlosschleife im UI-Thread, keine blockierte Bedienung, kein weiterer Trace-Start nach Toggle aus.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Arbeitsflaeche abfahren - kleineres Profil

- Vorbereitung: Testprofil mit kleinerem Arbeitsbereich anlegen, Maschine verbunden und idle, Laser aus (`M5`, `S0`).
- Schritte: Kleineres Profil aktivieren, Modus starten und Bewegungsgrenzen beobachten.
- Erwartetes Verhalten: Rahmen nutzt ausschliesslich X/Y-Werte des aktiven Profils, nicht die Defaultmaschine.
- Akzeptanzkriterium: Log und reale Bewegung entsprechen dem kleineren Profil; Profilwechsel waehrend aktivem Modus beendet/blockiert den Modus sicher.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Langer Job ohne Laser

- Vorbereitung: Maschine verbinden und homen, Test-G-Code mit vielen Bewegungen und `M5`/`S0` vorbereiten.
- Schritte: Dry Run starten und bis zum Ende laufen lassen.
- Erwartetes Verhalten: UI bleibt bedienbar, Fortschritt/Log laufen weiter, Job endet mit Laser aus.
- Akzeptanzkriterium: Kein Hänger, kein Alarm, Abschlussmeldung sichtbar.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Pause während langem Job

- Vorbereitung: Langer Dry-Run-Job läuft.
- Schritte: Während Job-Streaming Pause/Feed Hold auslösen.
- Erwartetes Verhalten: Pause wird priorisiert, Queue blockiert nicht, UI zeigt pausierten Zustand.
- Akzeptanzkriterium: Bewegung stoppt kontrolliert und Status wird `paused`/Hold.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Resume nach Pause

- Vorbereitung: Job ist pausiert.
- Schritte: Resume/Fortsetzen auslösen.
- Erwartetes Verhalten: Resume wird priorisiert, Job läuft weiter oder Controller meldet klaren Fehler.
- Akzeptanzkriterium: Kein UI-Freeze, Status wechselt aus `paused`.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Stop während Job-Streaming

- Vorbereitung: Langer Dry-Run-Job läuft.
- Schritte: Stop auslösen.
- Erwartetes Verhalten: Soft Reset/Emergency-Priorität, wartende normale Befehle werden verworfen, Laser bleibt aus.
- Akzeptanzkriterium: Jobzustand beendet definiert, erneutes Homing wird verlangt.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Emergency Stop während Job

- Vorbereitung: Langer Dry-Run-Job läuft.
- Schritte: Sicherheitsstopp auslösen.
- Erwartetes Verhalten: Emergency Stop wartet nicht hinter G-Code, Queue wird definiert beendet.
- Akzeptanzkriterium: Bewegung stoppt, UI friert nicht ein, Status/Log nennen Stopp.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## USB-Kabel ziehen während Idle

- Vorbereitung: Maschine verbunden und idle.
- Schritte: USB-Kabel ziehen, danach Status abfragen oder trennen.
- Erwartetes Verhalten: Fehler wird geloggt, UI wechselt in Fehler oder getrennt.
- Akzeptanzkriterium: Keine unbehandelte Exception, App bleibt bedienbar.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## USB-Kabel ziehen während Job

- Vorbereitung: Langer Dry-Run-Job läuft.
- Schritte: USB-Kabel ziehen.
- Erwartetes Verhalten: Serial-Fehler wird erkannt, Job endet im Fehlerzustand, UI bleibt bedienbar.
- Akzeptanzkriterium: Kein Freeze, keine weitere Jobausführung ohne erneute Verbindung.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Controller-Reset während Statuspolling

- Vorbereitung: Maschine verbunden, Statusabfragen möglich.
- Schritte: Statusabfrage starten und Controller resetten.
- Erwartetes Verhalten: Fehlende/unerwartete Antwort wird geloggt, Zustand wird nachvollziehbar.
- Akzeptanzkriterium: App bleibt stabil und verlangt bei Bedarf erneute Verbindung/Homing.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Ungültigen G-Code senden

- Vorbereitung: Testprojekt mit bewusst ungültigem oder nicht bewegendem G-Code.
- Schritte: Preflight/Start auslösen.
- Erwartetes Verhalten: Preflight oder GRBL-Fehler blockiert den Job, Laser bleibt aus.
- Akzeptanzkriterium: Nutzerhinweis ist verständlich, keine Queue hängt.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Disconnect während aktiver Queue

- Vorbereitung: Langer Dry-Run-Job oder lange Status-/Query-Aktion läuft.
- Schritte: Verbindung trennen.
- Erwartetes Verhalten: Wartende normale Befehle werden verworfen, Port wird geschlossen.
- Akzeptanzkriterium: UI geht definiert auf getrennt/Fehler, keine hängenden Threads.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## App schließen während Verbindung aktiv ist

- Vorbereitung: Maschine verbunden, kein aktiver Laser.
- Schritte: App-Fenster schließen.
- Erwartetes Verhalten: Controller wird getrennt, SerialExecutor stoppt, keine Exception beim Schließen.
- Akzeptanzkriterium: Prozess beendet sauber, Port ist danach wieder verfügbar.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Mehrfach Pause/Resume ohne Laser

- Vorbereitung: Langer Dry-Run-Job mit `M5`/`S0` laeuft.
- Schritte: Pause ausloesen, Hold-Status abwarten, Resume ausloesen; Sequenz mindestens dreimal wiederholen.
- Erwartetes Verhalten: `!` und `~` werden als Realtime-Kommandos gesendet, Status wechselt zwischen `Hold` und `Run`/`Idle`.
- Akzeptanzkriterium: Keine normale `ok`-Pflicht fuer Realtime-Kommandos, kein SerialExecutor-Timeout.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Statuspolling waehrend Hold

- Vorbereitung: Dry-Run-Job laeuft und wurde per Feed Hold pausiert.
- Schritte: Mehrfach Status abfragen, waehrend der Controller im Hold-Zustand bleibt.
- Erwartetes Verhalten: Statusabfragen senden `?`, erwarten Statuszeilen wie `<Hold|...>` und blockieren die Queue nicht.
- Akzeptanzkriterium: Kein Timeout, UI zeigt paused/Hold nachvollziehbar.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Material-Ausrichtmodus mit Laserpunkt

- Vorbereitung: Maschine verbunden und idle, Schutzbrille/Gehaeuse aktiv, kein brennbares Material beim ersten Test, Pointer Power 1-3% einstellen, maximal 5%.
- Schritte: GRBL Settings abfragen oder beim Aktivieren Log pruefen. Danach `Material ausrichten` aktivieren, Statusanzeige beobachten, Laserpunkt visuell pruefen.
- Erwartetes Verhalten: Laserpunkt ist sichtbar, aber schwach; UI zeigt `Ausrichtmodus aktiv`; Log nennt Pointer Power, `$30`, `$31`, `$32`, berechneten S-Wert und `M3 S...`.
- Akzeptanzkriterium: Bei `$30=1000` und 5% wird `M3 S50` gesendet; bei `$30=255` und 5% ca. `M3 S13`. Direkt nach Aktivierung wird kein `M5`/`S0` gesendet.
- Sicherheit: Nach dem Test `M5`/`S0` im Log oder per Status/Controller pruefen.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Material-Ausrichtmodus Testmodus 2 Sekunden

- Vorbereitung: Maschine verbunden und idle, Schutzbrille/Gehaeuse aktiv, freie Arbeitsflaeche, Pointer Power maximal 5%.
- Schritte: `Pointer 2s testen` ausloesen.
- Erwartetes Verhalten: Log meldet Testmodus, sendet `M3 S...`, wartet ca. 2 Sekunden und sendet danach automatisch `M5` und `S0`.
- Akzeptanzkriterium: Laserpunkt erscheint nur kurz; danach ist der Laser sicher aus und Ausrichtmodus nicht aktiv.
- Sicherheit: Es wird kein Gravurjob gestartet; Leistung bleibt auf Pointer-Limit begrenzt; kein Materialabtrag.
- Hinweis: Falls `M3 S...` im Stand nicht sichtbar ist, optional mit minimaler Bewegung testen: `G91`, `G1 X0.5 F100`, `G90`; danach immer `M5` und `S0`.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Jogging im Material-Ausrichtmodus

- Vorbereitung: Ausrichtmodus aktiv, freie Arbeitsflaeche, Pointer Power 1-3%.
- Schritte: Kleine Jog-Schritte X/Y ausloesen.
- Erwartetes Verhalten: Jogging laeuft nur ueber die bestehenden Jog-Aktionen; Laserpunkt bleibt schwach sichtbar und folgt der Position.
- Akzeptanzkriterium: Keine Job-/Frame-Aktion startet, solange der Laserpunkt aktiv ist; UI bleibt bedienbar.
- Sicherheit: Nach Jogging Ausrichtmodus deaktivieren und `M5`/`S0` pruefen.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Ausrichtmodus Sicherheitsabschaltungen

- Vorbereitung: Ausrichtmodus aktiv, Maschine idle, Pointer Power 1-3%.
- Schritte: Nacheinander deaktivieren, Disconnect, Stop, Emergency Stop und Jobstart/Preflight testen. Zwischen den Tests neu verbinden/idle herstellen.
- Erwartetes Verhalten: Jeder Pfad schaltet den Laserpunkt vorher oder sofort aus; Log nennt automatische Sicherheitsabschaltung.
- Akzeptanzkriterium: Nach jedem Pfad ist der Laser aus (`M5`/`S0`), Ausrichtmodus in der UI aus, kein unbeabsichtigter aktiver Laserpunkt.
- Sicherheit: Emergency Stop/Reset kann Homing verlieren; danach zuerst Status pruefen und ggf. neu homen.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Ausrichtmodus bei Alarm/Error blockiert

- Vorbereitung: Controller gezielt in Alarm/Error oder simulierten Fehlerzustand bringen, Laser aus.
- Schritte: `Material ausrichten` aktivieren versuchen.
- Erwartetes Verhalten: Aktivierung wird blockiert, kein `M3/M4` wird gesendet, UI zeigt verstaendliche Meldung.
- Akzeptanzkriterium: Laser bleibt aus; Log nennt blockierten Ausrichtmodus.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Stop waehrend Hold

- Vorbereitung: Dry-Run-Job ist per Feed Hold pausiert.
- Schritte: Stop ausloesen.
- Erwartetes Verhalten: Stop/Reset wird priorisiert, Queue wird definiert beendet, Laser bleibt aus.
- Akzeptanzkriterium: Controller ist danach in definiertem Idle/Reset-Zustand oder verlangt klares Re-Homing.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Disconnect waehrend Hold

- Vorbereitung: Dry-Run-Job ist per Feed Hold pausiert.
- Schritte: Verbindung trennen.
- Erwartetes Verhalten: Port wird geschlossen, wartende Jobbefehle werden verworfen, UI wechselt getrennt/definiert.
- Akzeptanzkriterium: Kein haengender Thread, Port ist danach wieder verbindbar.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## Controller-Reset waehrend Hold

- Vorbereitung: Dry-Run-Job ist per Feed Hold pausiert.
- Schritte: Controller manuell resetten oder Soft Reset ausloesen.
- Erwartetes Verhalten: Startup-/Reset-Meldungen werden geloggt, Job wird nicht fortgesetzt, Zustand wird klar.
- Akzeptanzkriterium: Kein UI-Freeze, erneutes Verbinden/Homing ist moeglich.
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

## SVG Hatch-Fill - Creality CR Laser Falcon 10W

- Datum:
- App-Version/Commit:
- Maschine: Creality CR Laser Falcon 10W
- Profil: Falcon 10W, maximal 400 x 415 mm
- Arbeitsflaeche:
- `$30`:
- `$32`:
- Sicherheit: Zuerst ausschliesslich als Dry Run mit `M5`/`S0`; danach nur auf Restmaterial mit Schutzbrille und beaufsichtigter Maschine.

### Testobjekte

- Rechteck
- Kreis
- geschlossener Schriftzug/Textpfad
- Logo mit mehreren geschlossenen Konturen

### Testmatrix

Fuer jedes Testobjekt nacheinander pruefen:

1. Layer-Modus `Kontur`
2. Layer-Modus `Fuellung`
3. Layer-Modus `Kontur + Fuellung`

Dokumentieren:

- Leistung in Prozent und resultierender S-Wert
- Geschwindigkeit in mm/min
- Fuellabstand: 0.05 / 0.08 / 0.10 / 0.15 / 0.20 mm
- Fuellwinkel: 0 / 45 / 90 Grad
- geschaetzte und tatsaechliche Laufzeit
- Gravurergebnis, Gleichmaessigkeit und sichtbare Linien
- Ergebnis: [ ] Bestanden / [ ] Fehlgeschlagen / Notizen:

### Akzeptanzkriterien

- Konturmodus erzeugt keine Hatch-Linien.
- Fuellmodus graviert nur die erzeugten Innenlinien.
- Kontur + Fuellung erzeugt beide getrennten Toolpath-Arten.
- Preview, Preflight und gesendeter GCode zeigen dieselbe Linienanzahl und Geometrie.
- Offene Konturen erzeugen eine Warnung und keine Fuellung.
- Serpentine-Richtung wechselt je Scanlinie; keine unnoetige Rueckfahrt zum linken Startpunkt.
- Job bleibt innerhalb der eingestellten App-Arbeitsflaeche und des Falcon-Limits.
- Stop, Pause/Resume und Statuspolling bleiben waehrend eines Fill-Jobs bedienbar.

## Falcon 10W Produktionsnahe Integrationsmatrix

Fuer jede Gruppe dokumentieren:

- Datum, App-Version und Commit
- Profil: Creality CR Laser Falcon 10W
- eingestellte App-Arbeitsflaeche
- Material oder `Dry Run`
- Laserleistung, Geschwindigkeit und Durchgaenge
- `$30`, `$32`
- erwartetes und tatsaechliches Verhalten
- Ergebnis: bestanden / fehlgeschlagen / offen
- Logauszug und Folgeaufgabe

### 1. Arbeitsflaechenmodus

- Mit App-Arbeitsflaeche 110 x 110 mm starten; Profilmaximum bleibt 400 x 415 mm.
- Normalen Stop waehrend eines Segments ausloesen.
- Pruefen: keine neue Runde, Queue bereinigt, `M5/S0`, Modus inaktiv.
- Home muss blockiert bleiben, solange GRBL noch `Run` meldet, und nach echtem `Idle` wieder moeglich sein.
- Disconnect und Sicherheitsstopp separat pruefen; Sicherheitsstopp darf Re-Homing verlangen.

### 2. Kopfposition und Preview

- Nach Homing MPos, WCO und abgeleitete/echte WPos dokumentieren.
- Arbeitsnullpunkt setzen und WPos 0/0 mit Preview-Nullpunkt vergleichen.
- Jog X+ muss Marker nach rechts bewegen; Jog Y+ muss Marker in der Preview nach oben bewegen.
- Bounding Box, Motiv, Nullpunkt und Kopfmarker muessen denselben Workspace-Maßstab verwenden.

### 3. SVG-Fuellung

- Rechteck, Kreis, Polygon und geschlossene Textpfade testen.
- Abstaende 0.05 bis 0.20 mm und Winkel 0/45/90 Grad pruefen.
- Zuerst Dry Run mit `M5/S0`, danach beaufsichtigter Materialtest.
- Offene Konturen muessen gewarnt und ohne Fuell-GCode behandelt werden.

### 4. Kontur + Fuellung

- Preview muss Fill und Kontur unterschiedlich darstellen.
- GCode-Reihenfolge pruefen: `toolpath fill` vor `toolpath outline`.
- Linienanzahl in Toolpath, Preview und Preflight vergleichen.
- Kontur muss erst nach abgeschlossener Fuellung gefahren werden.

### 5. Live-Maschinenposition

- Position in Idle, Jog, Run, Hold, Resume, Dry Run und Arbeitsflaechenmodus beobachten.
- Pollingintervall und Log auf Timeouts oder Streaming-Stoerungen pruefen.
- Preview-Marker darf nur WPos oder `WPos (MPos-WCO)` verwenden.
- Disconnect muss Statusanzeige und Marker auf unbekannt zuruecksetzen.

## Falcon 10W Overscan-Vergleich

Alle Versuche zuerst als Dry Run mit `M5` und `S0` pruefen. Materialtests nur beaufsichtigt, mit Schutzbrille, Absaugung und geeignetem Restmaterial durchfuehren.

### Testdaten dokumentieren

- Datum, App-Version und Commit
- Maschine: Creality CR Laser Falcon 10W
- eingestellte App-Arbeitsflaeche
- Material und Materialstaerke
- Geschwindigkeit und Leistung
- Fuellabstand und Fuellwinkel
- Overscan-Modus und berechneter/manueller Wert
- geschaetzte und tatsaechliche Laufzeit
- tatsaechlicher minimaler/maximaler Fahrweg

### Vergleich ohne und mit Overscan

1. Geschlossenes Rechteck mit mindestens 30 mm Breite importieren.
2. Layer auf `Fuellung`, Fuellwinkel 0 Grad stellen.
3. Einen Durchlauf mit deaktiviertem Overscan gravieren.
4. Einen Durchlauf mit automatischem Overscan bei gleicher Leistung, Geschwindigkeit und Linienlage gravieren.
5. Fuer 1000, 2000, 3000 und 5000 mm/min wiederholen.
6. Randqualitaet, dunkle Endbereiche und Gleichmaessigkeit fotografisch dokumentieren.
7. Laufzeit und zusaetzliche Fahrstrecke aus Preflight mit dem beobachteten Ablauf vergleichen.

### Serpentine und Arbeitsbereich

- Pruefen, dass aufeinanderfolgende Linien ihre Richtung wechseln.
- Auf beiden Seiten muss der Laser im Overscan-Bereich aus bleiben.
- Motiv nahe X0 testen: linker Overscan muss auf X0 begrenzt werden.
- Motiv nahe X-Max testen: rechter Overscan muss auf die eingestellte App-Arbeitsflaeche begrenzt werden.
- Dasselbe mit Fuellwinkel 45 und 90 Grad wiederholen.
- Preview, Preflight und GCode muessen denselben Overscan-Wert und dieselben Grenzen zeigen.

### Akzeptanzkriterien

- Keine sichtbare Markierung ausserhalb der eigentlichen Fuellflaeche.
- Weniger dunkle Linienenden als beim Vergleich ohne Overscan.
- Kein Fahrweg ausserhalb der eingestellten App-Arbeitsflaeche oder des Falcon-Profils.
- Kontur-, Schnitt-, Frame- und Arbeitsflaechenmodus bleiben unveraendert.
- Stop und Pause/Resume funktionieren weiterhin waehrend eines Fill-Jobs.

## Falcon 10W Motivpositionierung per Preview

Die Mausbedienung veraendert nur das Motivmodell. Vor einem Hardwaretest GCode, Preflight und Frame kontrollieren; ein Klick in die Preview darf niemals unmittelbar eine Maschinenbewegung ausloesen.

### Testablauf

1. Falcon-10W-Profil und eine kleine App-Arbeitsflaeche waehlen.
2. Geschlossenes SVG importieren und in der Preview anklicken.
3. Motiv per Maus nacheinander links unten, mittig und rechts oben positionieren.
4. X/Y-Anzeige und numerische Transformfelder nach jeder Bewegung dokumentieren.
5. Snap an allen vier Kanten sowie horizontaler und vertikaler Mitte pruefen.
6. Snap deaktivieren und eine freie Position einstellen.
7. Mit Pfeiltasten 1 mm, mit Shift 10 mm und mit Ctrl 0.1 mm korrigieren.
8. Motiv absichtlich teilweise ausserhalb platzieren und blockierenden Preflight pruefen.
9. Motiv wieder innerhalb positionieren und Frame mit ausgeschaltetem Laser (`M5`, `S0`) ausfuehren.
10. Preview-Bounds, GCode-Koordinaten und realen Frame-Weg vergleichen.

### Akzeptanzkriterien

- Mausklick und Drag senden keine GRBL-Bewegung.
- Frame beginnt an der in Preview und Transformfeldern angezeigten Position.
- Pfeil-Nudging aktualisiert Preview, Preflight und GCode gemeinsam.
- Snap-Hilfslinien erscheinen nur innerhalb der Toleranz.
- Ausserhalb liegende Motive bleiben verschiebbar, der Jobstart ist jedoch blockiert.
- Die Gravur startet nach bestaetigtem Preflight an der erwarteten WPos.

## Falcon 10W Mehrmotiv-Schluesselband 100 x 30 mm

Dieser Test validiert die Mehrmotiv-Funktion fuer einen praxisnahen Kunstleder-Schluesselband-Job. Zuerst als Frame und Dry Run mit sicher deaktiviertem Laser ausfuehren. Eine echte Testgravur nur beaufsichtigt, mit Schutzbrille, Absaugung und geeignetem Restmaterial starten.

### Testdaten dokumentieren

- Datum:
- App-Version/Commit:
- Maschine: Creality CR Laser Falcon 10W
- Profil: Creality CR Laser Falcon 10W
- Material: Kunstleder-Schluesselband
- Materialgroesse: 100 x 30 mm
- `$30`:
- `$32`:
- Speed:
- Power:
- Passes:
- Ergebnis/Abweichungen:

### Schritte

1. Material/Arbeitsbereich auf 100 x 30 mm einstellen.
2. Logo-SVG importieren; Objektliste muss ein aktives und sichtbares Motiv zeigen.
3. Text-SVG importieren; Logo bleibt erhalten, Text wird automatisch ausgewaehlt.
4. Logo links positionieren, z. B. X 5 mm, Y 5 mm.
5. Text rechts positionieren, z. B. X 45 mm, Y 8 mm.
6. Preview pruefen: beide Motive sichtbar, beide Bounding Boxes korrekt, ausgewaehltes Motiv hervorgehoben.
7. Frame fahren; der Frame muss die Gesamt-Bounding-Box beider aktiver Motive abfahren.
8. Dry Run starten; Log/GCode muss beide Motive enthalten.
9. Preflight ausfuehren; alle aktiven Motive muessen innerhalb 100 x 30 mm liegen.
10. Optional echte Testgravur mit dokumentierten Parametern ausfuehren.

### Akzeptanzkriterien

- Mehrfachimport ersetzt kein vorhandenes Motiv.
- Nur das ausgewaehlte Motiv reagiert auf Transformfelder und Drag & Drop.
- Inaktive Motive werden nicht graviert.
- Unsichtbare Motive werden nicht angezeigt; aktive unsichtbare Motive sind fuer den Job bewusst zu pruefen.
- Preview, Preflight, Frame und GCode nutzen dieselben Item-Transforms.
- Ein ausserhalb liegendes aktives Motiv blockiert den Start.
- GCode enthaelt nachvollziehbare Abschnitte fuer Logo und Text.

## Falcon 10W SVG-Optimierung fuer komplexe Linienmotive

Dieser Test vergleicht ein komplexes Wolf-SVG mit einem einfachen Schriftzug. Ziel ist, gleiche Laserparameter beizubehalten und nur die zuschaltbare SVG-Geometrieoptimierung zu bewerten. Originaldateien bleiben unveraendert.

### Testdaten dokumentieren

- Datum:
- App-Version/Commit:
- Maschine: Creality CR Laser Falcon 10W
- Profil: Creality CR Laser Falcon 10W
- Material:
- Speed:
- Power:
- Passes:
- `$30`:
- `$32`:
- Testmotiv komplex: Wolf-SVG
- Vergleichsmotiv: einfacher Schriftzug

### Varianten

1. Original ohne Optimierung
2. Konturvereinfachung 0.02 mm
3. Konturvereinfachung 0.05 mm
4. Doppelte Linien entfernen
5. Konturvereinfachung plus doppelte Linien entfernen

### Pro Variante dokumentieren

- Segmentanzahl vorher:
- Segmentanzahl nachher:
- Geschaetzte GCode-Zeilen vorher/nachher:
- Preflight-Warnungen:
- Gravurzeit geschaetzt/tatsaechlich:
- Sichtbare Linienqualitaet:
- Dichte/dunkle Mehrfachlinien:
- Detailverlust ja/nein:
- Abweichungen:

### Ablauf

1. Wolf-SVG importieren und Analysewerte notieren.
2. Preview ohne Optimierung pruefen und GCode-Zeilen dokumentieren.
3. Variante aktivieren, Preview und GCode erneut vergleichen.
4. Frame und Dry Run mit deaktiviertem Laser durchfuehren.
5. Optional echte Gravur mit identischen Materialparametern ausfuehren.
6. Denselben Ablauf mit einfachem Schriftzug wiederholen.

### Akzeptanzkriterien

- Preview, Preflight und GCode verwenden dieselbe optimierte Geometrie.
- ArtworkTransform bleibt unveraendert; keine Rotation, Spiegelung oder Verschiebung entsteht.
- Offene Pfade bleiben offen; geschlossene Pfade bleiben geschlossen.
- Bei 0.02 mm bleibt die Motivform sichtbar unveraendert.
- Bei 0.05 mm darf die Gravurzeit sinken, Detailverlust muss dokumentiert werden.
- Doppelte Linien werden nur bei aktivierter Option entfernt.
- Ein einfacher Schriftzug darf durch deaktivierte Standardoptionen nicht beeinflusst werden.

## Falcon 10W Laser Intelligence Analyse

Dieser Test prueft die neue Analyse- und Empfehlungsschicht fuer SVG, PNG und JPG. Die Engine darf keine Originaldatei veraendern und darf Optimierungen nur auf einer internen Arbeitskopie anwenden, wenn die zugehoerige UI-Option aktiv ist.

### Testdaten dokumentieren

- Datum:
- App-Version/Commit:
- Maschine: Creality CR Laser Falcon 10W
- Profil: Creality CR Laser Falcon 10W
- Material:
- Speed:
- Power:
- Passes:
- `$30`:
- `$32`:
- Motiv 1: komplexes Linien-SVG
- Motiv 2: Logo/Text-SVG
- Motiv 3: PNG/JPG-Foto

### Ablauf

1. Jedes Motiv importieren und Laser-Intelligence-Anzeige dokumentieren.
2. Klassifikation, Qualitaetswert, Empfehlungen und Falcon-10W-Parameter notieren.
3. Preview, Preflight-Warnungen und GCode-Erzeugung ohne Optimierung vergleichen.
4. Konturvereinfachung und doppelte-Linien-Entfernung bewusst aktivieren.
5. Preview, Preflight und GCode erneut vergleichen.
6. Frame und Dry Run mit deaktiviertem Laser (`M5`/`S0`) ausfuehren.
7. Optional echte Gravur auf Restmaterial mit identischen Materialparametern ausfuehren.

### Akzeptanzkriterien

- Originaldateien bleiben unveraendert.
- Die Anzeige nennt nachvollziehbar Qualitaet, Motivklasse, Strategie und Falcon-10W-Empfehlung.
- Preflight enthaelt die gleiche Analyseklasse und Qualitaetseinschaetzung wie die Sidebar.
- GCode nutzt nur dann optimierte Pfade, wenn die Option bewusst aktiv ist.
- Rastermotive werden als Raster/Foto klassifiziert und nicht als SVG-Konturen behandelt.
- Komplexe SVGs erhalten Warnungen zu Segmentdichte, kleinen Details oder doppelten Linien, sofern vorhanden.
- Keine Maschinen-, Serial-, GRBL- oder JobController-Logik wird durch die Analyse veraendert.

### Phase 2: Bezier, Raster und Materialstartwerte

1. SVG mit Cubic- und Quadratic-Bezier importieren.
2. Pruefen: Kurvenanzahl, empfohlene Flattening-Toleranz und Warnungen erscheinen in Analyse/Preflight.
3. PNG/JPG mit DPI importieren, danach dasselbe Motiv ohne DPI importieren.
4. Pruefen: DPI-Hinweis, Kontrastbewertung, Rastermodus und empfohlener Linienabstand sind nachvollziehbar.
5. Materialprofil nacheinander auf Lindenholz 2 mm, Kunstleder, Schiefer, Pappe/Karton und Sperrholz 3 mm setzen.
6. Pruefen: Falcon-10W-Startwerte erscheinen als Hinweise, ueberschreiben aber keine Layerwerte.
7. SVG-Optimierung aktivieren und Original-vs-Arbeitskopie-Report dokumentieren.

Akzeptanzkriterien:

- Bezieranalyse veraendert die importierte Form nicht.
- Rasteranalyse blockiert den Start nicht nur wegen niedriger Qualitaet.
- Materialempfehlungen sind als Startwerte markiert.
- Preflight blockiert weiterhin nur bei echten Sicherheits-/Jobblockern.
