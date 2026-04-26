# Creality CR-Laser Falcon Verbindung

Stand: 2026-04-26

## Ziel

Unser Tool soll den Creality CR-Laser Falcon unter Windows zuerst sicher erkennen,
ein GRBL-Handshake ausfuehren und spaeter G-Code zeilenweise senden.

## Anschluss

- Verbindung: USB-C Datenkabel vom PC zum Laser.
- Windows-Port: COM-Port unter "Anschluesse (COM & LPT)" im Geraetemanager.
- Controller-Typ in Laser-Software: GRBL.
- Baudrate: 115200.
- Arbeitsbereich aus LightBurn-Profilen: 400 x 415 mm.
- Laserleistungsskala: `S0` bis `S1000`.
- Laser-Modus fuer dynamische Leistung: `M4`.

## Windows-Treiber

Je nach Board/Revision kann Windows unterschiedliche USB-IDs und Treiber zeigen:

- ESP32-S2: oft als generisches "USB Serial Device (COMx)".
- Silicon Labs CP210x: "Silicon Labs CP210x USB to UART Bridge (COMx)".
- WCH CH340/CH341: "USB-SERIAL CH340 (COMx)".

Unser Tool sollte deshalb nicht auf einen festen Treibernamen vertrauen, sondern
alle COM-Ports anzeigen und nach dem Verbinden per GRBL-Handshake pruefen.

## GRBL-Handshake

Geplantes Verhalten:

1. COM-Port mit 115200 Baud oeffnen.
2. Kurz warten, Input-Puffer lesen.
3. `\r\n\r\n` oder `?` senden, um den Controller zu wecken bzw. Status zu lesen.
4. Optional `$I` senden, um Build-Info auszulesen.
5. Optional `$$` senden, um Settings auszulesen.
6. Nur als verbunden markieren, wenn eine GRBL-Antwort, `ok`, Statusreport oder
   eine plausible Fehlerantwort kommt.

Typische erwartete Konsole:

```text
Grbl 1.1f ['$' for help]
ok
```

Beobachtung am angeschlossenen Falcon auf `COM3`:

```text
> $I
< ok
< <Idle|MPos:0.000,0.000,0.000|FS:0,0|Ov:100,100,100|A:S>
```

Der Controller liefert beim Build-Info-Test nicht zwingend ein sichtbares
`Grbl ...` Banner. Unser Handshake akzeptiert deshalb auch `ok` plus einen
plausiblen Statusreport als erfolgreiche GRBL-Verbindung.

## G-Code-Richtlinien

- Einheiten: `G21`
- Absolute Koordinaten: `G90`
- Laser aus: `M5`
- Dynamischer Laser-Modus: `M4`
- Leistung: `S0` bis `S1000`
- Vorschub: `F...` in mm/min
- Homing: `$H`, wenn vom Controller unterstuetzt und mechanisch sicher.
- Statusabfrage: `?`
- Hold/Resume/Reset spaeter getrennt behandeln, weil das Echtzeit-Kommandos sind.

## Sicherheit fuer unser Projekt

- Echte Hardware-Kommunikation bleibt zunaechst hinter einem "Hardware aktivieren"
  Schalter.
- Kein automatischer Start nach dem Verbinden.
- Vor Jobstart: Arbeitsbereich pruefen, Laserleistung anzeigen, Materialprofil
  bestaetigen lassen.
- "Stop" muss immer sichtbar sein und `M5` senden.
- Framing nur mit sehr niedriger Leistung oder ohne Laser, soweit die Firmware das
  erlaubt.

## Naechste Implementierung

Erledigt:

1. Python-Abhaengigkeit `pyserial` in `requirements.txt` aufgenommen.
2. Modul `laser_control/serial_grbl.py` angelegt.
3. COM-Port-Erkennung in die UI eingebaut.
4. Neben "Simulator" den Modus "GRBL ueber USB" eingebaut.
5. Verbinden, `$I`, `$$`, `?`, `M5`, `$H`, Jog, Feed-Hold und Stop vorbereitet.
6. Sichere Rahmenfahrt ohne Laserleistung eingebaut.
7. Kontrollierten Jobstart mit Sicherheitsdialog und zeilenweiser `ok/error`
   Pruefung eingebaut.
8. Hintergrund-Worker fuer laengere Aktionen eingebaut, damit die UI bedienbar
   bleibt.
9. Status- und Fortschrittsanzeige fuer laufende Aktionen eingebaut.
10. Projekt speichern/laden als `.laser.json` und editierbare Materialwerte
    eingebaut.
11. SVG-Dateiimport fuer einfache Vektorformen eingebaut.
12. Material-Einmessung ueber zwei aktuelle Laserpositionen eingebaut.
13. Proportionale SVG-Platzierung mit Automatik- und Manuell-Modus eingebaut.
14. Linke Steuerleiste scrollbar gemacht, damit alle Funktionen auf FHD sichtbar
    bleiben.
15. SVG-Import um Transform-Unterstuetzung und Kurvenapproximation erweitert.
16. Lokale Materialdatenbank fuer eingemessene Materialien eingebaut.

Noch offen:

1. Jobversand spaeter mit echter Queue/Cancellation-Logik verfeinern.
2. Fortschrittsanzeige um Restzeit/Zeilenzahl im Hauptfenster erweitern.

## Sichere Rahmenfahrt

Die Rahmenfahrt ist fuer echte Hardware nur erlaubt, wenn:

- der Controller verbunden ist
- eine Referenzfahrt ausgefuehrt wurde
- der Arbeitsbereich innerhalb `400 x 415 mm` liegt

Der erzeugte G-Code verwendet nur `G0` Bewegungen und setzt vor und nach der
Fahrt `M5`. Es wird keine Laserleistung (`S...`) gesendet.

Beim Test am echten Falcon wurde bestaetigt:

- 300 x 200 mm Rahmenfahrt wurde ohne Laserleistung angenommen.
- GRBL sendet `ok`, sobald Befehle angenommen sind, nicht erst nach Bewegungsende.
- Der Controller wartet deshalb nach der Rahmenfahrt aktiv auf `<Idle...>`.
- Der Falcon kann beim Homing interne ESP/GPIO-Meldungen ausgeben; diese werden
  fuer die App-Anzeige von ANSI-Farbsequenzen bereinigt.

## Kontrollierter Jobstart

Der echte Jobstart ist freigeschaltet, aber nur mit Sicherheitsdialog in der App.
Vor dem Senden wird geprueft:

- Arbeitsbereich liegt innerhalb `400 x 415 mm`
- G-Code enthaelt Bewegungsbefehle
- finale Laser-Aus-Sequenz `M5` ist vorhanden oder wird ergaenzt
- Dialog zeigt Material, Leistung, Geschwindigkeit, Arbeitsbereich und Anzahl
  der G-Code-Zeilen

Der GRBL-Controller sendet jede Zeile einzeln und wartet auf `ok` oder `error`.
Bei Fehlern wird `M5` gesendet und der Fehler an die UI weitergegeben.

## Hintergrund-Worker

Laengere Aktionen laufen jetzt ausserhalb des Tkinter-Hauptthreads:

- Verbinden
- Trennen
- Referenzfahrt
- Status/Settings-Abfrage
- Jog
- Rahmenfahrt
- Jobstart

Logausgaben werden per UI-Queue zurueck in den Hauptthread gereicht. `Pause`,
`Fortsetzen` und `Stop` duerfen auch waehrend einer laufenden Aktion gestartet
werden.

Tkinter-Variablen duerfen nicht aus Worker-Threads gelesen werden. Werte wie der
ausgewaehlte COM-Port werden deshalb vor dem Workerstart in normale Python-Werte
kopiert.

## Status und Fortschritt

Die App zeigt unten einen Zustandstext, einen Prozentbalken und eine
Prozentanzeige. Der GRBL-Controller meldet Fortschritt fuer:

- Verbinden
- Referenzfahrt
- Rahmenfahrt
- Jobstart pro gesendeter G-Code-Zeile
- Pause, Fortsetzen, Stop/Reset

## Projektdateien und Materialwerte

Projektdateien werden als JSON mit der Endung `.laser.json` gespeichert. Aktuell
enthalten sie:

- Arbeitsbereich
- aktuelles Materialprofil mit Leistung, Geschwindigkeit und Durchgaengen
- sichtbaren G-Code

Materialwerte koennen in der App direkt angepasst werden. Die Werte gelten fuer
das aktuell ausgewaehlte Profil und werden beim Projekt-Speichern mit abgelegt.

## SVG-Import

Der Dateiimport unterstuetzt aktuell:

- `rect`
- `line`
- `polyline`
- `polygon`
- `circle`
- `ellipse`
- einfache `path`-Befehle: `M`, `L`, `H`, `V`, `Z`, `C`, `S`, `Q`, `T`, `A`
  sowie relative Varianten
- Gruppen-/Element-Transforms: `translate`, `scale`, `rotate`, `matrix`

Kurven werden in Polylinien angenaehert. Arc-Befehle (`A`) werden aktuell als
Linie bis zum Endpunkt angenaehert und koennen spaeter noch genauer umgesetzt
werden. Importierte Geometrie wird als Polylinien in der Vorschau angezeigt und
in G-Code mit `G0`/`G1` umgewandelt.

### SVG-Platzierung

SVG-Geometrie kann proportional platziert werden:

- Automatisch: Einpassen in den aktuellen Arbeitsbereich bzw. die eingemessene
  Materialgroesse, mit einstellbarem Rand und Zentrierung.
- Manuell: Zielbreite, X-Offset und Y-Offset setzen. Die Hoehe wird proportional
  berechnet.

Die Platzierung wird beim Projekt-Speichern mit abgelegt.

## Material-Einmessung

Die App kann die Materialgroesse aus zwei Laserpositionen berechnen:

1. Laser an eine Materialecke joggen.
2. `Ecke 1 setzen` klicken.
3. Laser an die gegenueberliegende Materialecke joggen.
4. `Ecke 2 setzen` klicken.
5. `Groesse uebernehmen` setzt den Arbeitsbereich auf die gemessene Breite und
   Hoehe.

Die Position wird aus dem GRBL-Statusreport `MPos`/`WPos` gelesen. Die Messung
wird beim Projekt-Speichern mit abgelegt.

Eingemessene oder manuell eingetragene Materialien koennen zusaetzlich in einer
lokalen Datei `materials.json` gespeichert, bearbeitet, geladen und geloescht
werden.

## Quellen

- Creality Download Center: https://www.creality.com/download/cr-laser-falcon-laser-engraver-10w
- CR-Laser Falcon Handbuch via ManualsLib: https://www.manualslib.com/manual/3405017/Creality-Cr-Laser-Falcon.html
- Creality/LaserGRBL Kurzanleitung via device.report: https://device.report/m/acdf6b6cab72ead0c2dc8dd6bba9aab9ab34b1b1755eb8e1a9ee301c5f482309
- CR-Laser Falcon LightBurn-Profil: https://gist.github.com/marcdurham/4168878f2a5f7b0a0b5ea121fa01094f
- LightBurn-Forum Treiber/COM-Port Hinweise: https://forum.lightburnsoftware.com/t/lightburn-2-0-04-not-communicating-with-controller/184872
