# Maschinenprofile

Maschinenprofile beschreiben sicherheitsrelevantes Maschinenverhalten. Der Standard bleibt konservativ: Homing ist erforderlich.

Beispiel:

```json
{
  "profile_id": "creality-falcon-10w",
  "name": "Creality Falcon 10W",
  "machine_name": "Creality Falcon 10W",
  "controller_type": "GRBL ueber USB",
  "work_area_width": 400.0,
  "work_area_height": 415.0,
  "default_port": "",
  "baudrate": 115200,
  "homing_required": true,
  "max_speed": 10000,
  "max_power": 100,
  "notes": "",
  "allow_start_without_homing_warning": "Diese Maschine erlaubt Start ohne Homing. Die aktuelle Position kann ungenau sein.",
  "machine_has_limit_switches": true,
  "startup_requires_homing": true
}
```

## Speicherung

Die Profile werden als JSON gespeichert. Standardpfad ist `machine_profiles.json` im Arbeitsverzeichnis. Fuer Tests oder portable Setups kann `LASER_CONTROL_MACHINE_PROFILES` auf einen anderen Pfad zeigen.

Die Datei enthaelt mehrere Profile und die aktive Auswahl:

```json
{
  "version": 1,
  "active_profile_id": "creality-falcon-10w",
  "profiles": []
}
```

## Homing-Regel

- `homing_required: true`: Hardwarestarts werden blockiert, solange keine Referenzfahrt erkannt wurde.
- `homing_required: false`: Start ohne Homing ist nur nach sichtbarer Preflight-Warnung und bewusster Bestaetigung erlaubt.

Es gibt keine globale Option zum Ignorieren von Homing. Fehlende Felder werden konservativ behandelt.

## Fallback

Wenn keine Datei vorhanden ist, wird das sichere Defaultprofil verwendet. Wenn die JSON-Datei beschaedigt ist, wird nicht blind gestartet; die App faellt auf das Defaultprofil zurueck und protokolliert den Ladefehler.

## UI-Editor

Im Maschinenbereich kann die Profilliste geoeffnet und ein kleines Profilformular bearbeitet werden. Der Editor ist bewusst kompakt und unterstuetzt:

- bestehendes Profil auswaehlen
- neues Profil mit konservativen Defaults anlegen
- Profilname und Maschinenname bearbeiten
- Controller-Typ, Arbeitsbereich, Baudrate und optionalen Standard-Port setzen
- `homing_required`, maximale Geschwindigkeit, maximale Laserleistung und Notizen pflegen

Vor dem Speichern werden Pflichtfelder und plausible Grenzwerte validiert. Ungueltige Profile werden nicht gespeichert und nicht automatisch aktiviert.

## Validierung

- Profilname und Maschinenname duerfen nicht leer sein.
- Arbeitsbereich muss groesser als 0 mm sein.
- Baudrate muss im plausiblen Bereich liegen.
- Maximale Geschwindigkeit muss groesser als 0 sein.
- Maximale Laserleistung muss zwischen 1 und 100 Prozent liegen.
- `homing_required` bleibt bei neuen Profilen standardmaessig aktiv.
