from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from laser_control.controller_interface import LaserController
from laser_control.machine_state import MachineEvent, MachineEventType, MachinePhase


@dataclass(frozen=True)
class PreparedMachineJob:
    """Controller-ready job payload.

    This is intentionally small: preflight, G-code creation and UI prompts stay
    outside this class, while the actual controller call is kept out of widgets.
    """

    gcode: str
    width_mm: float
    height_mm: float
    label: str = "Job"


class JobState(StrEnum):
    IDLE = "idle"
    PREPARING = "preparing"
    PREFLIGHT_REQUIRED = "preflight_required"
    READY = "ready"
    STREAMING = "streaming"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


JOB_TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.IDLE: {
        JobState.PREPARING,
        JobState.PREFLIGHT_REQUIRED,
        JobState.READY,
        JobState.STREAMING,
        JobState.STOPPING,
        JobState.FAILED,
        JobState.ABORTED,
    },
    JobState.PREPARING: {JobState.PREFLIGHT_REQUIRED, JobState.READY, JobState.STREAMING, JobState.FAILED, JobState.ABORTED},
    JobState.PREFLIGHT_REQUIRED: {JobState.READY, JobState.IDLE, JobState.FAILED, JobState.ABORTED},
    JobState.READY: {JobState.STREAMING, JobState.IDLE, JobState.FAILED, JobState.ABORTED},
    JobState.STREAMING: {JobState.PAUSED, JobState.STOPPING, JobState.COMPLETED, JobState.FAILED, JobState.ABORTED},
    JobState.PAUSED: {JobState.STREAMING, JobState.STOPPING, JobState.FAILED, JobState.ABORTED},
    JobState.STOPPING: {JobState.STOPPED, JobState.ABORTED, JobState.FAILED},
    JobState.STOPPED: {JobState.IDLE, JobState.PREPARING, JobState.STREAMING},
    JobState.COMPLETED: {JobState.IDLE, JobState.PREPARING, JobState.PREFLIGHT_REQUIRED, JobState.READY, JobState.STREAMING},
    JobState.FAILED: {JobState.IDLE, JobState.PREPARING, JobState.PREFLIGHT_REQUIRED, JobState.READY, JobState.STREAMING},
    JobState.ABORTED: {JobState.IDLE, JobState.PREPARING, JobState.PREFLIGHT_REQUIRED, JobState.READY, JobState.STREAMING},
}


class JobController:
    """UI-independent coordinator for frame runs and job streaming entrypoints."""

    def __init__(self, on_state_changed=None) -> None:
        self.state = JobState.IDLE
        self._on_state_changed = on_state_changed

    @property
    def status(self) -> str:
        return self.state.value

    def transition(self, next_state: JobState, reason: str = "") -> None:
        if next_state not in JOB_TRANSITIONS[self.state] and next_state != self.state:
            previous = self.state
            next_state = JobState.FAILED
            reason = reason or "Ungueltiger JobState-Uebergang."
            if next_state == previous:
                return
        if next_state == self.state:
            return
        previous = self.state
        self.state = next_state
        if self._on_state_changed is not None:
            self._on_state_changed(previous, next_state, reason)

    def prepare(self) -> None:
        self.transition(JobState.PREPARING, "Jobvorbereitung gestartet.")

    def require_preflight(self) -> None:
        self.transition(JobState.PREFLIGHT_REQUIRED, "Preflight erforderlich.")

    def mark_ready(self) -> None:
        self.transition(JobState.READY, "Job ist startbereit.")

    def frame(self, controller: LaserController, width_mm: float, height_mm: float, x_mm: float = 0.0, y_mm: float = 0.0) -> None:
        controller.frame(width_mm, height_mm, x_mm, y_mm)

    def start(self, controller: LaserController, job: PreparedMachineJob) -> None:
        if not job.gcode.strip():
            raise RuntimeError("Job enthaelt keinen G-Code.")
        if self.state not in {JobState.READY, JobState.STREAMING}:
            self.transition(JobState.PREPARING, f"{job.label} wird vorbereitet.")
            self.transition(JobState.READY, f"{job.label} ist startbereit.")
        self.transition(JobState.STREAMING, f"{job.label} Streaming gestartet.")
        try:
            controller.start_job(job.gcode, job.width_mm, job.height_mm)
        except Exception as exc:
            if "stop" in str(exc).lower() or "abgebrochen" in str(exc).lower():
                self.transition(JobState.ABORTED, str(exc))
            else:
                self.transition(JobState.FAILED, str(exc))
            raise
        else:
            self.transition(JobState.COMPLETED, f"{job.label} abgeschlossen.")

    def pause(self, controller: LaserController) -> None:
        controller.pause()
        self.transition(JobState.PAUSED, "GRBL Hold/Pause erkannt.")

    def resume(self, controller: LaserController) -> None:
        controller.resume()
        self.transition(JobState.STREAMING, "Job fortgesetzt.")

    def stop(self, controller: LaserController) -> None:
        self.transition(JobState.STOPPING, "Kontrollierter Jobstop angefordert.")
        controller.stop()
        self.transition(JobState.STOPPED, "Job kontrolliert gestoppt.")

    def emergency_stop(self, controller: LaserController) -> None:
        self.transition(JobState.STOPPING, "Sicherheitsstopp angefordert.")
        controller.emergency_stop()
        self.transition(JobState.ABORTED, "Job durch Sicherheitsstopp abgebrochen.")

    def handle_machine_event(self, event: MachineEvent) -> None:
        if event.event_type == MachineEventType.STATUS:
            if event.phase == MachinePhase.PAUSED and self.state in {JobState.READY, JobState.STREAMING}:
                self.transition(JobState.PAUSED, event.message or "Maschine meldet Hold.")
            elif event.phase == MachinePhase.RUNNING and self.state == JobState.PAUSED:
                self.transition(JobState.STREAMING, event.message or "Maschine meldet Run.")
            elif event.phase == MachinePhase.IDLE and self.state == JobState.STREAMING:
                self.transition(JobState.COMPLETED, event.message or "Maschine meldet Idle nach Streaming.")
            elif event.phase == MachinePhase.IDLE and self.state == JobState.STOPPING:
                self.transition(JobState.STOPPED, event.message or "Maschine meldet Idle nach Stop.")
            elif event.phase == MachinePhase.IDLE and self.state == JobState.PAUSED:
                self.transition(JobState.STOPPED, event.message or "Maschine meldet Idle aus Hold.")
        elif event.event_type == MachineEventType.ALARM:
            if self.state != JobState.ABORTED:
                self.transition(JobState.FAILED, event.message or "Maschinenalarm.")
        elif event.event_type in {MachineEventType.ERROR, MachineEventType.CONNECTION_LOST}:
            if self.state in {JobState.PREPARING, JobState.READY, JobState.STREAMING, JobState.PAUSED, JobState.STOPPING}:
                if event.event_type == MachineEventType.ERROR:
                    self.transition(JobState.FAILED, event.message or "Maschinenfehler.")
                else:
                    self.transition(JobState.ABORTED, event.message or "Verbindungsverlust.")
