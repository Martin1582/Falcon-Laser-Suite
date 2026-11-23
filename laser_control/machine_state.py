from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MachinePhase(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ALARM = "alarm"
    ERROR = "error"
    STOPPING = "stopping"


class MachineAction(StrEnum):
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    STATUS = "status"
    SETTINGS = "settings"
    HOME = "home"
    JOG = "jog"
    FRAME = "frame"
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"
    EMERGENCY_STOP = "emergency_stop"
    RESET = "reset"
    CAPTURE_POSITION = "capture_position"
    ALIGNMENT_MODE = "alignment_mode"
    WORK_AREA_TRACE = "work_area_trace"


class MachineEventType(StrEnum):
    STATUS = "status"
    STATE_CHANGED = "state_changed"
    ALARM = "alarm"
    ERROR = "error"
    CONNECTION_LOST = "connection_lost"
    JOB_PROGRESS = "job_progress"


@dataclass(frozen=True)
class MachineEvent:
    event_type: MachineEventType
    phase: MachinePhase
    message: str = ""
    raw: str = ""
    progress_current: int | None = None
    progress_total: int | None = None
    x_mm: float | None = None
    y_mm: float | None = None
    z_mm: float | None = None
    position_source: str = ""
    feed_rate: float | None = None
    spindle_value: float | None = None
    override_feed: int | None = None
    override_rapid: int | None = None
    override_spindle: int | None = None
    alignment_mode_active: bool = False
    pointer_power_percent: int = 1
    work_area_trace_active: bool = False


MachineStateChangedEvent = MachineEvent
GrblStatusEvent = MachineEvent
MachineAlarmEvent = MachineEvent
MachineErrorEvent = MachineEvent
ConnectionLostEvent = MachineEvent


ALLOWED_TRANSITIONS: dict[MachinePhase, set[MachinePhase]] = {
    MachinePhase.DISCONNECTED: {MachinePhase.CONNECTING, MachinePhase.IDLE, MachinePhase.ERROR},
    # ALARM: GRBL may report Alarm right after connecting (e.g. homing required after power-up).
    # PAUSED: a controller can still be in Hold when connecting; Resume/Stop must stay usable.
    MachinePhase.CONNECTING: {MachinePhase.IDLE, MachinePhase.ALARM, MachinePhase.PAUSED, MachinePhase.ERROR, MachinePhase.DISCONNECTED},
    MachinePhase.IDLE: {MachinePhase.RUNNING, MachinePhase.PAUSED, MachinePhase.STOPPING, MachinePhase.ALARM, MachinePhase.ERROR, MachinePhase.DISCONNECTED},
    MachinePhase.RUNNING: {MachinePhase.PAUSED, MachinePhase.STOPPING, MachinePhase.IDLE, MachinePhase.ALARM, MachinePhase.ERROR, MachinePhase.DISCONNECTED},
    MachinePhase.PAUSED: {MachinePhase.RUNNING, MachinePhase.STOPPING, MachinePhase.IDLE, MachinePhase.ALARM, MachinePhase.ERROR, MachinePhase.DISCONNECTED},
    # RUNNING: a homing cycle ($H) is the standard GRBL recovery from an alarm lock.
    MachinePhase.ALARM: {MachinePhase.RUNNING, MachinePhase.STOPPING, MachinePhase.ERROR, MachinePhase.DISCONNECTED, MachinePhase.IDLE},
    MachinePhase.ERROR: {MachinePhase.DISCONNECTED, MachinePhase.CONNECTING, MachinePhase.IDLE, MachinePhase.ALARM, MachinePhase.PAUSED},
    MachinePhase.STOPPING: {MachinePhase.IDLE, MachinePhase.DISCONNECTED, MachinePhase.ERROR, MachinePhase.ALARM},
}


ALLOWED_ACTIONS: dict[MachinePhase, set[MachineAction]] = {
    MachinePhase.DISCONNECTED: {MachineAction.CONNECT},
    MachinePhase.CONNECTING: {MachineAction.DISCONNECT},
    MachinePhase.IDLE: {
        MachineAction.DISCONNECT,
        MachineAction.STATUS,
        MachineAction.SETTINGS,
        MachineAction.HOME,
        MachineAction.JOG,
        MachineAction.FRAME,
        MachineAction.START,
        MachineAction.EMERGENCY_STOP,
        MachineAction.CAPTURE_POSITION,
        MachineAction.ALIGNMENT_MODE,
        MachineAction.WORK_AREA_TRACE,
    },
    MachinePhase.RUNNING: {
        MachineAction.DISCONNECT,
        MachineAction.PAUSE,
        MachineAction.STOP,
        MachineAction.EMERGENCY_STOP,
        MachineAction.STATUS,
    },
    MachinePhase.PAUSED: {
        MachineAction.DISCONNECT,
        MachineAction.RESUME,
        MachineAction.STOP,
        MachineAction.EMERGENCY_STOP,
        MachineAction.STATUS,
    },
    # Recovery: HOME ($H) for machines with homing switches, RESET ($X unlock) for the rest.
    MachinePhase.ALARM: {
        MachineAction.DISCONNECT,
        MachineAction.STATUS,
        MachineAction.EMERGENCY_STOP,
        MachineAction.HOME,
        MachineAction.RESET,
    },
    MachinePhase.ERROR: {MachineAction.CONNECT, MachineAction.DISCONNECT, MachineAction.STATUS, MachineAction.EMERGENCY_STOP, MachineAction.RESET},
    MachinePhase.STOPPING: {MachineAction.DISCONNECT, MachineAction.EMERGENCY_STOP, MachineAction.STATUS},
}


@dataclass
class MachineState:
    phase: MachinePhase = MachinePhase.DISCONNECTED
    message: str = "Nicht verbunden"
    x_mm: float | None = None
    y_mm: float | None = None
    z_mm: float | None = None
    position_source: str = ""
    feed_rate: float | None = None
    spindle_value: float | None = None
    override_feed: int | None = None
    override_rapid: int | None = None
    override_spindle: int | None = None
    alignment_mode_active: bool = False
    pointer_power_percent: int = 1
    work_area_trace_active: bool = False

    @property
    def connected(self) -> bool:
        return self.phase not in {MachinePhase.DISCONNECTED, MachinePhase.CONNECTING}

    @property
    def busy(self) -> bool:
        return self.phase in {MachinePhase.CONNECTING, MachinePhase.RUNNING, MachinePhase.STOPPING}

    def transition(self, next_phase: MachinePhase, message: str = "") -> None:
        if next_phase not in ALLOWED_TRANSITIONS[self.phase] and next_phase != self.phase:
            self.phase = MachinePhase.ERROR
            self.message = f"Ungueltiger Zustandswechsel nach {next_phase.value}."
            return
        self.phase = next_phase
        if message:
            self.message = message

    def can_perform(self, action: MachineAction) -> bool:
        if self.work_area_trace_active:
            return action in {
                MachineAction.WORK_AREA_TRACE,
                MachineAction.STOP,
                MachineAction.EMERGENCY_STOP,
                MachineAction.DISCONNECT,
                MachineAction.STATUS,
            }
        if self.alignment_mode_active:
            if action in {MachineAction.START, MachineAction.FRAME, MachineAction.HOME}:
                return False
            if action == MachineAction.STOP:
                return True
        return action in ALLOWED_ACTIONS[self.phase]

    def apply_event(self, event: MachineEvent) -> None:
        self.transition(event.phase, event.message)
        if event.phase == MachinePhase.DISCONNECTED:
            self.x_mm = None
            self.y_mm = None
            self.z_mm = None
            self.position_source = ""
            self.feed_rate = None
            self.spindle_value = None
            self.override_feed = None
            self.override_rapid = None
            self.override_spindle = None
            self.alignment_mode_active = False
            self.pointer_power_percent = 1
            self.work_area_trace_active = False
            return
        if event.x_mm is not None:
            self.x_mm = event.x_mm
            self.y_mm = event.y_mm
            self.z_mm = event.z_mm
            self.position_source = event.position_source
        if event.feed_rate is not None:
            self.feed_rate = event.feed_rate
        if event.spindle_value is not None:
            self.spindle_value = event.spindle_value
        if event.override_feed is not None:
            self.override_feed = event.override_feed
            self.override_rapid = event.override_rapid
            self.override_spindle = event.override_spindle
        self.alignment_mode_active = event.alignment_mode_active
        self.pointer_power_percent = event.pointer_power_percent
        self.work_area_trace_active = event.work_area_trace_active


def phase_from_controller_status(status: str, connected: bool = True, alarm: bool = False, paused: bool = False) -> MachinePhase:
    if not connected:
        return MachinePhase.DISCONNECTED
    if alarm:
        return MachinePhase.ALARM
    if paused:
        return MachinePhase.PAUSED
    normalized = status.strip().lower()
    if normalized.startswith("alarm"):
        return MachinePhase.ALARM
    if normalized.startswith("hold"):
        return MachinePhase.PAUSED
    if normalized.startswith("run") or normalized.startswith("jog") or normalized.startswith("home"):
        return MachinePhase.RUNNING
    if normalized.startswith("idle"):
        return MachinePhase.IDLE
    if normalized.startswith("error"):
        return MachinePhase.ERROR
    if normalized.startswith("door") or normalized.startswith("check"):
        return MachinePhase.ERROR
    return MachinePhase.IDLE


def machine_event_from_status(
    status: str,
    connected: bool = True,
    alarm: bool = False,
    paused: bool = False,
    raw: str = "",
    message: str = "",
    x_mm: float | None = None,
    y_mm: float | None = None,
    z_mm: float | None = None,
    position_source: str = "",
    feed_rate: float | None = None,
    spindle_value: float | None = None,
    override_feed: int | None = None,
    override_rapid: int | None = None,
    override_spindle: int | None = None,
    alignment_mode_active: bool = False,
    pointer_power_percent: int = 1,
    work_area_trace_active: bool = False,
) -> MachineEvent:
    phase = phase_from_controller_status(status, connected=connected, alarm=alarm, paused=paused)
    if phase == MachinePhase.DISCONNECTED:
        event_type = MachineEventType.CONNECTION_LOST
    elif phase == MachinePhase.ALARM:
        event_type = MachineEventType.ALARM
    elif phase == MachinePhase.ERROR:
        event_type = MachineEventType.ERROR
    else:
        event_type = MachineEventType.STATUS
    return MachineEvent(
        event_type=event_type,
        phase=phase,
        message=message or status or phase.value,
        raw=raw,
        x_mm=x_mm if position_source and phase != MachinePhase.DISCONNECTED else None,
        y_mm=y_mm if position_source and phase != MachinePhase.DISCONNECTED else None,
        z_mm=z_mm if position_source and phase != MachinePhase.DISCONNECTED else None,
        position_source=position_source if phase != MachinePhase.DISCONNECTED else "",
        feed_rate=feed_rate,
        spindle_value=spindle_value,
        override_feed=override_feed,
        override_rapid=override_rapid,
        override_spindle=override_spindle,
        alignment_mode_active=alignment_mode_active if phase != MachinePhase.DISCONNECTED else False,
        pointer_power_percent=pointer_power_percent,
        work_area_trace_active=work_area_trace_active if phase != MachinePhase.DISCONNECTED else False,
    )


def machine_event_from_state(state, raw: str = "") -> MachineEvent:
    connected = bool(getattr(state, "connected", False))
    alarm = bool(getattr(state, "alarm", False))
    paused = bool(getattr(state, "paused", False))
    status = str(getattr(state, "status", ""))
    return machine_event_from_status(
        status,
        connected=connected,
        alarm=alarm,
        paused=paused,
        raw=raw,
        message=status,
        x_mm=getattr(state, "x_mm", None) if getattr(state, "position_source", "") else None,
        y_mm=getattr(state, "y_mm", None) if getattr(state, "position_source", "") else None,
        z_mm=getattr(state, "z_mm", None) if getattr(state, "position_source", "") else None,
        position_source=str(getattr(state, "position_source", "")),
        feed_rate=getattr(state, "feed_rate", None),
        spindle_value=getattr(state, "spindle_value", None),
        override_feed=getattr(state, "override_feed", None),
        override_rapid=getattr(state, "override_rapid", None),
        override_spindle=getattr(state, "override_spindle", None),
        alignment_mode_active=bool(getattr(state, "alignment_mode_active", False)),
        pointer_power_percent=int(getattr(state, "pointer_power_percent", 1)),
        work_area_trace_active=bool(getattr(state, "work_area_trace_active", False)),
    )
