from __future__ import annotations

from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QProgressBar, QSizePolicy

from laser_control.machine_state import MachinePhase, MachineState


class StatusPanel(QFrame):
    def __init__(self) -> None:
        super().__init__()
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 3, 0, 0)
        layout.setHorizontalSpacing(8)
        self.job_status = QLabel("Bereit")
        self.job_status.setMaximumWidth(150)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setMaximumHeight(20)
        self.progress.setMaximumWidth(220)
        self.machine_state_label = QLabel("Maschine: disconnected")
        self.machine_state_label.setMinimumWidth(220)
        self.position_label = QLabel("Position: X: -- mm | Y: -- mm | Z: -- mm")
        self.position_label.setMinimumWidth(260)
        self.status = QLabel("Simulator bereit.")
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.status.setToolTip(self.status.text())
        layout.addWidget(self.machine_state_label, 0, 0)
        layout.addWidget(self.position_label, 0, 1)
        layout.addWidget(self.job_status, 0, 2)
        layout.addWidget(self.progress, 0, 3)
        layout.addWidget(self.status, 0, 4)
        layout.setColumnStretch(4, 1)
        self.setMaximumHeight(28)

    def set_progress(self, label: str, current: int, total: int) -> None:
        total = max(1, total)
        percent = int(current / total * 100)
        self.job_status.setText(label)
        self.progress.setValue(percent)

    def set_message(self, message: str) -> None:
        self.status.setToolTip(message)
        self.status.setText(message if len(message) <= 80 else f"{message[:77]}...")

    def update_machine_state(
        self,
        state: MachineState,
        machine: str = "",
        port: str = "",
        last_error: str = "",
        job_state: str = "",
    ) -> None:
        labels = {
            MachinePhase.DISCONNECTED: "getrennt",
            MachinePhase.CONNECTING: "verbinde",
            MachinePhase.IDLE: "bereit",
            MachinePhase.RUNNING: "laeuft",
            MachinePhase.PAUSED: "pausiert",
            MachinePhase.STOPPING: "stoppt",
            MachinePhase.ALARM: "Alarm",
            MachinePhase.ERROR: "Fehler",
        }
        colors = {
            MachinePhase.DISCONNECTED: "#777777",
            MachinePhase.CONNECTING: "#f29900",
            MachinePhase.IDLE: "#188038",
            MachinePhase.RUNNING: "#2563eb",
            MachinePhase.PAUSED: "#f29900",
            MachinePhase.STOPPING: "#d93025",
            MachinePhase.ALARM: "#d93025",
            MachinePhase.ERROR: "#d93025",
        }
        connection = "Verbunden" if state.connected else "Getrennt"
        parts = [connection, labels.get(state.phase, state.phase.value)]
        if machine:
            parts.append(machine)
        if port:
            parts.append(port)
        if job_state:
            parts.append(f"Job: {job_state}")
        if last_error:
            parts.append(f"Fehler: {last_error}")
        self.machine_state_label.setText(" | ".join(parts))
        self.machine_state_label.setStyleSheet(f"color: {colors.get(state.phase, '#777777')}; font-weight: 700;")
        self.position_label.setText(self._position_text(state))

    def _position_text(self, state: MachineState) -> str:
        if not state.connected or state.x_mm is None or state.y_mm is None:
            return "Position: X: -- mm | Y: -- mm | Z: -- mm"
        source = f" {state.position_source}" if state.position_source else ""
        z_value = state.z_mm if state.z_mm is not None else 0.0
        feed = f"  F {state.feed_rate:.0f}" if state.feed_rate is not None else ""
        return f"Position{source}: X: {state.x_mm:.2f} mm | Y: {state.y_mm:.2f} mm | Z: {z_value:.2f} mm{feed}"
