from __future__ import annotations

import threading
from collections.abc import Callable

from laser_control.alignment import MaterialAlignmentController
from laser_control.controller_interface import LaserController
from laser_control.diagnostic_log import DiagnosticLog
from laser_control.job_controller import JobController, JobState, PreparedMachineJob
from laser_control.laser import SimulatedLaserController
from laser_control.machine_profiles import DEFAULT_MACHINE_PROFILE, MachineProfile
from laser_control.machine_state import MachineAction, MachineEvent, MachineEventType, MachinePhase, MachineState, machine_event_from_state
from laser_control.models import LaserState
from laser_control.serial_grbl import GrblSerialController


LogFn = Callable[[str], None]
ProgressFn = Callable[[str, int, int], None]
PortGetter = Callable[[], str]
WORK_AREA_TRACE_POINTER_POWER_PERCENT = 5


class ApplicationController:
    """UI-independent coordinator for the active machine controller."""

    def __init__(
        self,
        log: LogFn,
        progress: ProgressFn | None,
        port_getter: PortGetter,
        diagnostic_log: DiagnosticLog | None = None,
    ) -> None:
        self._log = log
        self._progress = progress
        self._port_getter = port_getter
        self._diagnostic_log = diagnostic_log
        self.machine_state = MachineState()
        self.connection_mode = "Simulator"
        self.machine_profile = DEFAULT_MACHINE_PROFILE
        self.current_workspace_width = float(DEFAULT_MACHINE_PROFILE.work_area_width)
        self.current_workspace_height = float(DEFAULT_MACHINE_PROFILE.work_area_height)
        self.work_area_trace_power_percent = WORK_AREA_TRACE_POINTER_POWER_PERCENT
        self.controller: LaserController = SimulatedLaserController(log, progress)
        self.job_controller = JobController(self._on_job_state_changed)
        self._work_area_trace_stop = threading.Event()
        self._work_area_trace_thread: threading.Thread | None = None
        self.alignment_controller = MaterialAlignmentController(
            lambda: self.controller,
            lambda: self.machine_state,
            self._log,
        )

    def switch_controller(self, connection_mode: str) -> LaserController:
        self.shutdown_controller()
        if connection_mode == "GRBL ueber USB":
            self.controller = GrblSerialController(
                self._log,
                self._port_getter,
                self._progress,
                baudrate=self.machine_profile.baudrate,
                diagnostic_log=self._diagnostic_log,
            )
        else:
            self.controller = SimulatedLaserController(self._log, self._progress)
        self.connection_mode = connection_mode
        self.machine_state.transition(MachinePhase.DISCONNECTED, "Nicht verbunden")
        self._log(f"Modus gewechselt: {self.connection_mode}")
        return self.controller

    def set_machine_profile(self, profile: MachineProfile) -> None:
        self.disable_work_area_trace("Maschinenprofilwechsel")
        self.ensure_alignment_laser_off("Maschinenprofilwechsel")
        self.machine_profile = profile
        self.set_current_workspace(profile.work_area_width, profile.work_area_height)
        self._log(
            "Maschinenprofil aktiv: "
            f"{profile.name} ({profile.machine_name}), "
            f"Baud {profile.baudrate}, "
            f"Arbeitsbereich {profile.work_area_width:.1f} x {profile.work_area_height:.1f} mm, "
            f"Homing erforderlich: {'ja' if profile.homing_required else 'nein'}."
        )

    def set_current_workspace(self, width_mm: float, height_mm: float) -> None:
        self.current_workspace_width = max(1.0, float(width_mm))
        self.current_workspace_height = max(1.0, float(height_mm))

    def set_work_area_trace_power(self, percent: int) -> int:
        self.work_area_trace_power_percent = max(0, min(5, int(percent)))
        return self.work_area_trace_power_percent

    def current_controller(self, connection_mode: str | None = None) -> LaserController:
        if connection_mode is not None and connection_mode != self.connection_mode:
            return self.switch_controller(connection_mode)
        return self.controller

    def run_machine_action(
        self,
        action_name: str,
        action: Callable[[LaserController], None],
        machine_action: MachineAction | None = None,
    ) -> None:
        machine_action = machine_action or self._action_from_name(action_name)
        if not self.require_action(machine_action, action_name):
            raise RuntimeError(f"Aktion im Zustand '{self.machine_state.phase.value}' nicht erlaubt: {action_name}")
        try:
            self._mark_action_start(machine_action, action_name)
            action(self.controller)
            self.sync_from_controller()
        except Exception as exc:
            if "alarm" in str(exc).lower():
                self.machine_state.transition(MachinePhase.ALARM, str(exc))
            else:
                self.machine_state.transition(MachinePhase.ERROR, str(exc))
            raise

    def connect(self) -> None:
        if not self.require_action(MachineAction.CONNECT, "Verbindung herstellen"):
            raise RuntimeError("Verbinden ist im aktuellen Maschinenzustand nicht erlaubt.")
        self.machine_state.transition(MachinePhase.CONNECTING, "Verbinde")
        try:
            self.controller.connect()
            self.sync_from_controller()
        except Exception as exc:
            self.machine_state.transition(MachinePhase.ERROR, str(exc))
            raise

    def disconnect(self) -> None:
        if not self.require_action(MachineAction.DISCONNECT, "Verbindung trennen"):
            raise RuntimeError("Trennen ist im aktuellen Maschinenzustand nicht erlaubt.")
        try:
            try:
                self.disable_work_area_trace("Disconnect")
                self.ensure_alignment_laser_off("Disconnect")
            except Exception as exc:  # noqa: BLE001 - still close the controller path
                self._log(f"Fehler bei Ausrichtmodus-Abschaltung vor Disconnect: {exc}")
            self.controller.disconnect()
        except Exception as exc:
            self.machine_state.transition(MachinePhase.ERROR, str(exc))
            raise
        else:
            self.machine_state.transition(MachinePhase.DISCONNECTED, "Nicht verbunden")

    def get_status(self) -> LaserState:
        if not self.require_action(MachineAction.STATUS, "Status abfragen"):
            raise RuntimeError("Statusabfrage ist im aktuellen Maschinenzustand nicht erlaubt.")
        try:
            status = self.controller.get_status()
            self.sync_from_controller()
            return status
        except Exception as exc:
            self.machine_state.transition(MachinePhase.ERROR, str(exc))
            raise

    def query_settings(self) -> object:
        def action(controller: LaserController) -> object:
            query = getattr(controller, "query_settings", None)
            if not callable(query):
                raise RuntimeError("GRBL Settings sind fuer diesen Controller nicht verfuegbar.")
            return query()

        return self._run_machine_action_with_result("GRBL Settings", action, MachineAction.SETTINGS)

    def home(self) -> None:
        self.run_machine_action("Homing", lambda controller: controller.home(), MachineAction.HOME)

    def jog(self, dx_mm: float, dy_mm: float, label: str = "Jog") -> None:
        self.run_machine_action(label, lambda controller: controller.jog(dx_mm, dy_mm), MachineAction.JOG)

    def frame_job(self, width_mm: float, height_mm: float, x_mm: float = 0.0, y_mm: float = 0.0) -> None:
        self.disable_work_area_trace("Frame-Start")
        self.ensure_alignment_laser_off("Frame-Start")
        self._log(
            "Frame-Bounds verwendet: "
            f"X{x_mm:.2f} Y{y_mm:.2f} bis X{x_mm + width_mm:.2f} Y{y_mm + height_mm:.2f} "
            f"({width_mm:.2f} x {height_mm:.2f} mm)."
        )
        self.run_machine_action(
            "Frame gestartet",
            lambda controller: self.job_controller.frame(controller, width_mm, height_mm, x_mm, y_mm),
            MachineAction.FRAME,
        )

    def start_job(
        self,
        gcode: str,
        width_mm: float,
        height_mm: float,
        label: str = "Job",
        preflight_confirmed: bool = False,
        auto_home_after_success: bool = False,
        job_kind: str = "Einzelstueck",
    ) -> None:
        self.disable_work_area_trace(f"{label} Start")
        self.ensure_alignment_laser_off(f"{label} Start")
        if self.connection_mode == "GRBL ueber USB" and not preflight_confirmed:
            self._log("Blockierter Hardwarestart: Preflight wurde nicht bestaetigt.")
            self.job_controller.require_preflight()
            raise RuntimeError("Hardwarestart ist nur nach bestaetigtem Preflight erlaubt.")
        if not self.require_action(MachineAction.START, f"{label} gestartet"):
            raise RuntimeError(f"Aktion im Zustand '{self.machine_state.phase.value}' nicht erlaubt: {label} gestartet")
        self.job_controller.prepare()
        self.job_controller.mark_ready()
        job = PreparedMachineJob(gcode=gcode, width_mm=width_mm, height_mm=height_mm, label=label)
        self.run_machine_action(
            f"{label} gestartet",
            lambda controller: self.job_controller.start(controller, job),
            MachineAction.START,
        )
        self._handle_auto_home_after_job(auto_home_after_success, job_kind, label)

    def pause(self) -> None:
        self.run_machine_action("Job pausieren", self.job_controller.pause, MachineAction.PAUSE)

    def resume(self) -> None:
        self.run_machine_action("Job fortsetzen", self.job_controller.resume, MachineAction.RESUME)

    def stop(self) -> None:
        if self.is_work_area_trace_active():
            self.disable_work_area_trace("Stop")
            return
        if self.is_alignment_mode_active() and self.machine_state.phase == MachinePhase.IDLE:
            self.disable_alignment_mode("Stop")
            self.sync_from_controller()
            return
        self.run_machine_action("Job stoppen", self.job_controller.stop, MachineAction.STOP)

    def emergency_stop(self) -> None:
        if not self.require_action(MachineAction.EMERGENCY_STOP, "Sicherheitsstopp"):
            raise RuntimeError("Sicherheitsstopp ist im aktuellen Maschinenzustand nicht erlaubt.")
        self.machine_state.transition(MachinePhase.STOPPING, "Sicherheitsstopp")
        try:
            try:
                self.disable_work_area_trace("Sicherheitsstopp")
                self.ensure_alignment_laser_off("Sicherheitsstopp")
            except Exception as exc:  # noqa: BLE001 - emergency stop must still be sent
                self._log(f"Fehler bei Ausrichtmodus-Abschaltung vor Sicherheitsstopp: {exc}")
            self.job_controller.emergency_stop(self.controller)
            self.handle_machine_event(
                MachineEvent(
                    MachineEventType.ALARM,
                    MachinePhase.ALARM,
                    "Sicherheitsstopp ausgeloest. Reset/Unlock/Re-Homing erforderlich.",
                )
            )
        except Exception as exc:
            self.machine_state.transition(MachinePhase.ERROR, str(exc))
            self.job_controller.transition(JobState.FAILED, str(exc))
            raise

    def current_position(self) -> tuple[float, float]:
        return self._run_machine_action_with_result(
            "Position erfassen",
            lambda controller: controller.current_position(),
            MachineAction.CAPTURE_POSITION,
        )

    def set_alignment_pointer_power(self, percent: int) -> int:
        power = self.alignment_controller.set_pointer_power(percent)
        self.sync_from_controller()
        return power

    def test_alignment_pointer(self, percent: int = 5, duration_seconds: float = 2.0) -> None:
        if not self.require_action(MachineAction.ALIGNMENT_MODE, "Ausrichtlaser Testmodus"):
            raise RuntimeError("Ausrichtlaser-Test ist im aktuellen Maschinenzustand nicht erlaubt.")
        if self.machine_state.phase != MachinePhase.IDLE:
            raise RuntimeError("Ausrichtlaser-Test ist nur bei idle Maschine erlaubt.")
        test = getattr(self.controller, "test_alignment_pointer", None)
        if callable(test):
            self._log(
                "alignment pointer test requested: "
                f"machine_state={self.machine_state.phase.value}; "
                f"pointer_power_percent={percent}; duration_seconds={duration_seconds:.1f}"
            )
            test(percent, duration_seconds)
        else:
            self._log(
                "alignment pointer test requested: Simulator/Controller ohne Hardware-Testmodus; "
                f"pointer_power_percent={percent}; duration_seconds={duration_seconds:.1f}"
            )
            self.controller.enable_alignment_pointer(percent)
            self.controller.disable_alignment_pointer()
        self.sync_from_controller()

    def enable_work_area_trace(self) -> None:
        if self.is_work_area_trace_active():
            self._log("Arbeitsflaechenmodus ist bereits aktiv.")
            return
        if self.machine_state.phase != MachinePhase.IDLE or not self.machine_state.connected:
            self._log(f"Arbeitsflaechenmodus blockiert: Maschinenzustand {self.machine_state.phase.value}.")
            raise RuntimeError("Arbeitsflaechenmodus ist nur bei verbundener, idle Maschine erlaubt.")
        if not self.require_action(MachineAction.WORK_AREA_TRACE, "Arbeitsflaeche abfahren"):
            raise RuntimeError("Arbeitsflaeche abfahren ist im aktuellen Maschinenzustand nicht erlaubt.")
        width = float(self.current_workspace_width)
        height = float(self.current_workspace_height)
        feed = self._work_area_trace_feed()
        power = self.work_area_trace_power_percent
        self._log(
            "Arbeitsflaechenmodus aktiviert: "
            f"Profil={self.machine_profile.name}; App-Arbeitsflaeche X{width:.1f} Y{height:.1f}; "
            f"Geschwindigkeit={feed} mm/min; Laserpunkt={power}%."
        )
        self._work_area_trace_stop.clear()
        self.machine_state.work_area_trace_active = True
        state = getattr(self.controller, "state", None)
        if state is not None:
            setattr(state, "work_area_trace_active", True)
        self._work_area_trace_thread = threading.Thread(
            target=self._run_work_area_trace,
            args=(width, height, feed, power),
            daemon=True,
            name="WorkAreaTraceMode",
        )
        self._work_area_trace_thread.start()

    def disable_work_area_trace(self, reason: str = "") -> None:
        if not self.is_work_area_trace_active() and not (self._work_area_trace_thread and self._work_area_trace_thread.is_alive()):
            return
        self._log(f"Arbeitsflaechenmodus deaktivieren: {reason or 'Benutzer'}.")
        self._work_area_trace_stop.set()
        stop_trace = getattr(self.controller, "stop_work_area_trace", None)
        if callable(stop_trace):
            try:
                stop_trace()
            except Exception as exc:  # noqa: BLE001 - continue with laser-off cleanup
                self._log(f"Arbeitsflaechenmodus Stop-Warnung: {exc}")
        self._set_work_area_trace_active(False)
        self.ensure_alignment_laser_off("Arbeitsflaechenmodus deaktiviert")
        self._sync_after_work_area_trace_cleanup()
        home_allowed = self.machine_state.can_perform(MachineAction.HOME)
        if (reason or "").lower() == "stop":
            self._log(
                "Arbeitsflaechenmodus gestoppt - Laser aus - "
                f"Home {'wieder moeglich' if home_allowed else 'noch blockiert, bis Maschine Idle meldet'}."
            )
        self._log(
            "Arbeitsflaechenmodus deaktiviert. Laser aus bestaetigt. "
            f"MachineState={self.machine_state.phase.value}; Home wieder erlaubt: {'ja' if home_allowed else 'nein'}."
        )

    def toggle_work_area_trace(self, enabled: bool) -> None:
        if enabled:
            self.enable_work_area_trace()
        else:
            self.disable_work_area_trace("Benutzer")

    def is_work_area_trace_active(self) -> bool:
        return bool(self.machine_state.work_area_trace_active)

    def enable_alignment_mode(self) -> None:
        if not self.require_action(MachineAction.ALIGNMENT_MODE, "Material ausrichten"):
            raise RuntimeError("Ausrichtmodus ist im aktuellen Maschinenzustand nicht erlaubt.")
        self.alignment_controller.enable_alignment_mode()
        self.sync_from_controller()

    def disable_alignment_mode(self, reason: str = "") -> None:
        self.alignment_controller.disable_alignment_mode(reason)
        self.sync_from_controller()

    def toggle_alignment_mode(self, enabled: bool) -> None:
        if enabled:
            self.enable_alignment_mode()
        else:
            self.disable_alignment_mode("Benutzer")

    def is_alignment_mode_active(self) -> bool:
        return self.alignment_controller.is_alignment_mode_active()

    def ensure_alignment_laser_off(self, reason: str = "") -> None:
        if self.is_alignment_mode_active():
            self._log(f"Automatische Sicherheitsabschaltung Ausrichtmodus: {reason}.")
        self.alignment_controller.ensure_laser_off(reason)
        state = getattr(self.controller, "state", None)
        if state is not None:
            self.machine_state.alignment_mode_active = bool(getattr(state, "alignment_mode_active", False))
            self.machine_state.pointer_power_percent = int(getattr(state, "pointer_power_percent", 1))

    def require_action(self, action: MachineAction, label: str) -> bool:
        if self.machine_state.can_perform(action):
            return True
        self._log(f"Blockierte Maschinenaktion: {label} im Zustand {self.machine_state.phase.value}.")
        return False

    def _handle_auto_home_after_job(self, enabled: bool, job_kind: str, label: str) -> None:
        self._log(
            "Auto-Home Entscheidung: "
            f"aktiv={'ja' if enabled else 'nein'}; job_art={job_kind}; job={label}."
        )
        reason = self._auto_home_skip_reason(enabled, job_kind)
        if reason:
            self._log(f"Auto-Home uebersprungen: {reason}.")
            return
        self._log("Job abgeschlossen - fahre Home an.")
        self._log("Auto-Home Sicherheitspruefung bestanden.")
        try:
            self._send_laser_off_before_auto_home()
            self._log("Auto-Home: M5/S0 gesendet.")
            self._log("Auto-Home: Home angefordert.")
            self.run_machine_action("Auto-Home", lambda controller: controller.home(), MachineAction.HOME)
        except Exception as exc:  # noqa: BLE001 - job is complete; report homing failure separately
            if "alarm" in str(exc).lower():
                self.machine_state.transition(MachinePhase.ALARM, str(exc))
            else:
                self.machine_state.transition(MachinePhase.ERROR, str(exc))
            self._log(f"Auto-Home fehlgeschlagen: {exc}")
            return
        self._log("Home abgeschlossen - bereit.")

    def _auto_home_skip_reason(self, enabled: bool, job_kind: str) -> str:
        if not enabled:
            return "Option deaktiviert"
        if job_kind != "Einzelstueck":
            return f"Job-Art ist {job_kind}, Auto-Home nur fuer Einzelstueck"
        if self.job_controller.state != JobState.COMPLETED:
            return f"JobState ist {self.job_controller.state.value}"
        if self.machine_state.phase != MachinePhase.IDLE:
            return f"MachineState ist {self.machine_state.phase.value}"
        state = getattr(self.controller, "state", None)
        if state is None:
            return "kein Controllerstatus"
        if not getattr(state, "connected", False):
            return "Maschine nicht verbunden"
        status = str(getattr(state, "status", ""))
        if getattr(state, "alarm", False) or status.lower().startswith("alarm"):
            return "Alarm aktiv"
        if status.lower().startswith("error"):
            return "Controller meldet Error"
        if getattr(state, "paused", False):
            return "Maschine pausiert"
        if self.machine_state.phase in {MachinePhase.RUNNING, MachinePhase.PAUSED, MachinePhase.STOPPING}:
            return f"Maschine nicht idle ({self.machine_state.phase.value})"
        if not self.machine_profile.homing_required or not self.machine_profile.machine_has_limit_switches:
            return "Homing im aktiven Profil nicht unterstuetzt oder deaktiviert"
        if not self._is_falcon_10w_profile_active():
            return "aktives Profil ist nicht Creality CR Laser Falcon 10W"
        queue_empty = getattr(self.controller, "serial_queue_empty", True)
        if callable(queue_empty):
            queue_empty = queue_empty()
        if not bool(queue_empty):
            return "Serial-Queue nicht leer"
        return ""

    def _send_laser_off_before_auto_home(self) -> None:
        laser_off = getattr(self.controller, "workspace_trace_laser_off", None)
        if callable(laser_off):
            laser_off()
            return
        self.controller.disable_alignment_pointer()

    def _is_falcon_10w_profile_active(self) -> bool:
        profile = self.machine_profile
        values = " ".join(
            [
                profile.profile_id,
                profile.name,
                profile.machine_name,
            ]
        ).lower()
        return "falcon" in values and "10w" in values

    def shutdown_controller(self) -> None:
        try:
            self.disable_work_area_trace("App-Schliessen")
            self.ensure_alignment_laser_off("App-Schliessen")
            if getattr(self.controller, "state", None) and self.controller.state.connected:
                self.controller.disconnect()
        except Exception as exc:  # noqa: BLE001 - shutdown should continue
            self._log(f"Fehler beim Trennen: {exc}")
        try:
            shutdown = getattr(self.controller, "shutdown", None)
            if callable(shutdown):
                shutdown()
        except Exception as exc:  # noqa: BLE001 - shutdown should continue
            self._log(f"Fehler beim Controller-Shutdown: {exc}")
        self.machine_state.transition(MachinePhase.DISCONNECTED, "Nicht verbunden")

    def _run_machine_action_with_result(
        self,
        action_name: str,
        action: Callable[[LaserController], object],
        machine_action: MachineAction,
    ) -> object:
        if not self.require_action(machine_action, action_name):
            raise RuntimeError(f"Aktion im Zustand '{self.machine_state.phase.value}' nicht erlaubt: {action_name}")
        try:
            self._mark_action_start(machine_action, action_name)
            result = action(self.controller)
            self.sync_from_controller()
            return result
        except Exception as exc:
            if "alarm" in str(exc).lower():
                self.machine_state.transition(MachinePhase.ALARM, str(exc))
            else:
                self.machine_state.transition(MachinePhase.ERROR, str(exc))
            raise

    def sync_from_controller(self) -> MachineState:
        state = getattr(self.controller, "state", None)
        if state is None:
            self.handle_machine_event(MachineEvent(MachineEventType.CONNECTION_LOST, MachinePhase.DISCONNECTED, "Nicht verbunden"))
            return self.machine_state
        self.handle_machine_event(machine_event_from_state(state))
        return self.machine_state

    def handle_machine_event(self, event: MachineEvent) -> MachineState:
        previous = self.machine_state.phase
        self.machine_state.apply_event(event)
        if self.machine_state.phase != previous:
            self._log(
                f"MachineState: {previous.value} -> {self.machine_state.phase.value} "
                f"[{event.event_type.value}] ({event.message})."
            )
        elif event.event_type in {MachineEventType.ALARM, MachineEventType.ERROR, MachineEventType.CONNECTION_LOST}:
            self._log(f"MachineEvent: {event.event_type.value} im Zustand {self.machine_state.phase.value} ({event.message}).")
        self.job_controller.handle_machine_event(event)
        if self.machine_state.phase in {MachinePhase.ALARM, MachinePhase.ERROR, MachinePhase.DISCONNECTED}:
            try:
                self.disable_work_area_trace(f"State {self.machine_state.phase.value}")
                self.ensure_alignment_laser_off(f"State {self.machine_state.phase.value}")
            except Exception:
                pass
        return self.machine_state

    def _on_job_state_changed(self, previous: JobState, current: JobState, reason: str) -> None:
        suffix = f" ({reason})" if reason else ""
        self._log(f"JobState: {previous.value} -> {current.value}{suffix}.")

    def _mark_action_start(self, action: MachineAction, action_name: str) -> None:
        if action in {MachineAction.STOP, MachineAction.EMERGENCY_STOP}:
            self.machine_state.transition(MachinePhase.STOPPING, action_name)
        elif action == MachineAction.CONNECT:
            self.machine_state.transition(MachinePhase.CONNECTING, action_name)
        elif action == MachineAction.DISCONNECT:
            self.machine_state.transition(MachinePhase.DISCONNECTED, action_name)
        elif action in {MachineAction.START, MachineAction.FRAME, MachineAction.JOG, MachineAction.HOME}:
            self.machine_state.transition(MachinePhase.RUNNING, action_name)

    def _action_from_name(self, action_name: str) -> MachineAction:
        lowered = action_name.lower()
        if "verbindung herstellen" in lowered:
            return MachineAction.CONNECT
        if "trennen" in lowered:
            return MachineAction.DISCONNECT
        if "status" in lowered:
            return MachineAction.STATUS
        if "settings" in lowered:
            return MachineAction.SETTINGS
        if "homing" in lowered or "referenz" in lowered:
            return MachineAction.HOME
        if "jog" in lowered or "position setzen" in lowered:
            return MachineAction.JOG
        if "frame" in lowered or "rahmen" in lowered:
            return MachineAction.FRAME
        if "pause" in lowered:
            return MachineAction.PAUSE
        if "fortsetzen" in lowered:
            return MachineAction.RESUME
        if "stop" in lowered or "sicherheits" in lowered:
            return MachineAction.EMERGENCY_STOP
        if "position erfassen" in lowered:
            return MachineAction.CAPTURE_POSITION
        if "ausrichten" in lowered:
            return MachineAction.ALIGNMENT_MODE
        if "arbeitsflaeche" in lowered or "arbeitsfläche" in lowered:
            return MachineAction.WORK_AREA_TRACE
        return MachineAction.START

    def _run_work_area_trace(self, width_mm: float, height_mm: float, feed_mm_min: int, power_percent: int) -> None:
        round_index = 0
        try:
            trace_once = getattr(self.controller, "trace_work_area_once", None)
            if not callable(trace_once):
                raise RuntimeError("Controller unterstuetzt Arbeitsflaechenmodus nicht.")
            self._log("Arbeitsflaechenmodus: Laser aus wird gesendet (M5/S0).")
            trace_off = getattr(self.controller, "workspace_trace_laser_off", None)
            if callable(trace_off):
                trace_off()
            else:
                self.controller.disable_alignment_pointer()
            self._log("Arbeitsflaechenmodus: Laser aus bestaetigt.")
            while not self._work_area_trace_stop.is_set():
                round_index += 1
                self._log(f"Arbeitsflaechenmodus: Runde {round_index} gestartet.")
                trace_once(width_mm, height_mm, feed_mm_min, self._work_area_trace_stop, power_percent)
                self._log(f"Arbeitsflaechenmodus: Runde {round_index} beendet.")
        except Exception as exc:  # noqa: BLE001 - background worker reports and stops mode
            self._log(f"Arbeitsflaechenmodus beendet durch Fehler: {exc}")
            self.machine_state.transition(MachinePhase.ERROR, str(exc))
        finally:
            self._work_area_trace_stop.set()
            try:
                off = getattr(self.controller, "workspace_trace_laser_off", None)
                if callable(off):
                    off()
                else:
                    self.controller.disable_alignment_pointer()
            except Exception as exc:  # noqa: BLE001 - report final safety issue
                self._log(f"Arbeitsflaechenmodus Laser-Aus fehlgeschlagen: {exc}")
            self._set_work_area_trace_active(False)
            self._sync_after_work_area_trace_cleanup()

    def _set_work_area_trace_active(self, active: bool) -> None:
        self.machine_state.work_area_trace_active = active
        state = getattr(self.controller, "state", None)
        if state is not None:
            setattr(state, "work_area_trace_active", active)

    def _sync_after_work_area_trace_cleanup(self) -> None:
        if self.machine_state.phase in {MachinePhase.ALARM, MachinePhase.ERROR, MachinePhase.DISCONNECTED}:
            return
        try:
            get_status = getattr(self.controller, "get_status", None)
            if callable(get_status):
                get_status()
            self.sync_from_controller()
        except Exception as exc:  # noqa: BLE001 - keep Home blocked until a later valid status
            self._log(f"Arbeitsflaechenmodus Status-Synchronisierung fehlgeschlagen: {exc}")
            self.machine_state.transition(MachinePhase.STOPPING, "Warte auf GRBL Idle")
            return
        if self.machine_state.phase == MachinePhase.IDLE:
            self.machine_state.message = "Arbeitsflaechenmodus beendet"
        else:
            self._log(
                "Arbeitsflaechenmodus beendet, Home noch blockiert: "
                f"GRBL meldet {self.machine_state.phase.value}."
            )

    def _work_area_trace_feed(self) -> int:
        max_speed = int(getattr(self.machine_profile, "max_speed", 2000) or 2000)
        return max(1000, min(2000, max_speed))
