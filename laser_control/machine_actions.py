from __future__ import annotations

from dataclasses import dataclass

from laser_control.machine_state import MachineAction, MachineState


@dataclass(frozen=True)
class MachineActionDefinition:
    action_id: str
    label: str
    tooltip: str
    machine_action: MachineAction | None = None
    icon_name: str = ""
    safety_critical: bool = False
    shortcut: str = ""
    allow_while_busy: bool = False


class MachineActionRegistry:
    def __init__(self, definitions: list[MachineActionDefinition] | None = None) -> None:
        self._definitions = {definition.action_id: definition for definition in (definitions or default_machine_actions())}

    def get(self, action_id: str) -> MachineActionDefinition:
        return self._definitions[action_id]

    def all(self) -> list[MachineActionDefinition]:
        return list(self._definitions.values())

    def is_enabled(self, action_id: str, state: MachineState) -> bool:
        definition = self.get(action_id)
        if definition.machine_action is None:
            return not state.busy
        return state.can_perform(definition.machine_action)


def default_machine_actions() -> list[MachineActionDefinition]:
    return [
        MachineActionDefinition("connect", "Verbinden", "Verbindung zur ausgewaehlten Maschine herstellen.", MachineAction.CONNECT),
        MachineActionDefinition("disconnect", "Trennen", "Aktive Maschinenverbindung sauber trennen.", MachineAction.DISCONNECT, allow_while_busy=True),
        MachineActionDefinition("refresh_ports", "Ports suchen", "Verfuegbare serielle Ports neu laden."),
        MachineActionDefinition("detect_laser", "Laser suchen", "COM-Ports auf eine GRBL-Lasersteuerung pruefen."),
        MachineActionDefinition("home", "Home", "Referenzfahrt ausfuehren. Hebt auch einen GRBL-Alarm auf.", MachineAction.HOME),
        MachineActionDefinition(
            "unlock_alarm",
            "Alarm entsperren",
            "GRBL-Alarm ohne Referenzfahrt aufheben ($X). Die Position ist danach nicht referenziert.",
            MachineAction.RESET,
            safety_critical=True,
        ),
        MachineActionDefinition("status", "Status", "Aktuellen Maschinenstatus abfragen.", MachineAction.STATUS),
        MachineActionDefinition("settings", "GRBL Settings", "GRBL-Konfiguration vom Controller abfragen.", MachineAction.SETTINGS),
        MachineActionDefinition("jog_y_plus", "Y+", "Y-Achse positiv bewegen.", MachineAction.JOG),
        MachineActionDefinition("jog_x_minus", "X-", "X-Achse negativ bewegen.", MachineAction.JOG),
        MachineActionDefinition("jog_x_plus", "X+", "X-Achse positiv bewegen.", MachineAction.JOG),
        MachineActionDefinition("jog_y_minus", "Y-", "Y-Achse negativ bewegen.", MachineAction.JOG),
        MachineActionDefinition("toggle_alignment", "Material ausrichten", "Schwachen Laserpunkt fuer Materialausrichtung sicher ein-/ausschalten.", MachineAction.ALIGNMENT_MODE, safety_critical=True),
        MachineActionDefinition(
            "toggle_work_area_trace",
            "Arbeitsflaeche abfahren",
            "Konfigurierte App-Arbeitsflaeche wiederholt abfahren. Stop beendet nach dem aktuellen Segment, schaltet M5/S0 und gibt Home nach Idle wieder frei; Sicherheitsstopp bricht sofort ab.",
            MachineAction.WORK_AREA_TRACE,
            safety_critical=True,
            allow_while_busy=True,
        ),
        MachineActionDefinition("frame", "Rahmen", "Jobrahmen ohne aktiven Laser abfahren.", MachineAction.FRAME),
        MachineActionDefinition("dry_run", "Dry Run", "Jobbewegungen mit deaktiviertem Laser testen.", MachineAction.START),
        MachineActionDefinition("start_job", "Start", "Vorbereiteten Job starten.", MachineAction.START, safety_critical=True),
        MachineActionDefinition("pause", "Pause", "Laufenden Job pausieren.", MachineAction.PAUSE, allow_while_busy=True),
        MachineActionDefinition("resume", "Fortsetzen", "Pausierten Job fortsetzen.", MachineAction.RESUME, allow_while_busy=True),
        MachineActionDefinition("stop", "Stop", "Laufenden Job kontrolliert stoppen. Im Arbeitsflaechenmodus: keine neuen Scanbewegungen, M5/S0, Home nach GRBL Idle wieder moeglich.", MachineAction.STOP, safety_critical=True, allow_while_busy=True),
        MachineActionDefinition("emergency_stop", "Sicherheitsstopp", "Sofortigen Sicherheitsabbruch ausloesen; Reset/Unlock/Re-Homing kann erforderlich sein.", MachineAction.EMERGENCY_STOP, safety_critical=True, allow_while_busy=True),
    ]
