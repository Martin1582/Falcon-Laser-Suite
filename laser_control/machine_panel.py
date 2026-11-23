from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QGridLayout, QGroupBox, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from laser_control.machine_actions import MachineActionRegistry
from laser_control.machine_state import MachinePhase, MachineState


class MachinePanel(QWidget):
    action_triggered = Signal(str, str)
    mode_changed = Signal(str)
    profile_changed = Signal(str)
    profile_editor_requested = Signal()

    def __init__(self, action_registry: MachineActionRegistry | None = None) -> None:
        super().__init__()
        self._action_registry = action_registry or MachineActionRegistry()
        self.action_buttons: dict[str, list[QPushButton]] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        connection = QGroupBox("Verbindung")
        form = QVBoxLayout(connection)
        form.setContentsMargins(8, 8, 8, 8)
        form.setSpacing(6)
        self.connection_label = QLabel("Nicht verbunden")
        self.connection_label.setObjectName("machineConnectionStatus")
        self.connection_label.setMinimumHeight(24)
        form.addWidget(self.connection_label)
        form.addWidget(QLabel("Maschinenprofil"))
        self.profile_select = QComboBox()
        self.profile_select.currentIndexChanged.connect(self._profile_index_changed)
        form.addWidget(self.profile_select)
        self.connection_mode = QComboBox()
        self.connection_mode.addItems(["Simulator", "GRBL ueber USB"])
        self.connection_mode.currentTextChanged.connect(self.mode_changed.emit)
        form.addWidget(self.connection_mode)
        form.addWidget(QLabel("Port"))
        self.serial_port = QComboBox()
        form.addWidget(self.serial_port)
        self.refresh_button = self._action_button("refresh_ports")
        self.detect_button = self._action_button("detect_laser")
        self.connect_button = self._action_button("connect")
        self.disconnect_button = self._action_button("disconnect")
        self.home_button = self._action_button("home")
        primary_grid = QGridLayout()
        primary_grid.setHorizontalSpacing(8)
        primary_grid.setVerticalSpacing(8)
        primary_grid.addWidget(self.connect_button, 0, 0)
        primary_grid.addWidget(self.disconnect_button, 0, 1)
        primary_grid.addWidget(self.home_button, 1, 0, 1, 2)
        form.addLayout(primary_grid)

        advanced = QGroupBox("Weitere")
        advanced.setCheckable(True)
        advanced.setChecked(False)
        advanced_layout = QVBoxLayout(advanced)
        advanced_layout.setContentsMargins(8, 8, 8, 8)
        advanced_layout.setSpacing(6)
        self.profile_edit_button = QPushButton("Profile bearbeiten")
        self.profile_edit_button.setToolTip("Maschinenprofile bearbeiten.")
        self.profile_edit_button.setMinimumHeight(30)
        self.profile_edit_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.profile_edit_button.clicked.connect(self.profile_editor_requested.emit)
        advanced_layout.addWidget(self.refresh_button)
        advanced_layout.addWidget(self.detect_button)
        advanced_layout.addWidget(self.profile_edit_button)
        advanced.toggled.connect(self._sync_advanced_visibility)
        form.addWidget(advanced)
        self.advanced_group = advanced
        layout.addWidget(connection)
        self.update_state(MachineState())
        self._sync_advanced_visibility(False)

    def set_machine_profiles(self, profiles, active_profile_id: str) -> None:
        self.profile_select.blockSignals(True)
        self.profile_select.clear()
        for profile in profiles:
            self.profile_select.addItem(profile.name, profile.profile_id)
        index = self.profile_select.findData(active_profile_id)
        self.profile_select.setCurrentIndex(max(0, index))
        self.profile_select.blockSignals(False)

    def update_state(self, state: MachineState) -> None:
        labels = {
            MachinePhase.DISCONNECTED: "Nicht verbunden",
            MachinePhase.CONNECTING: "Verbinde",
            MachinePhase.IDLE: "Verbunden",
            MachinePhase.RUNNING: "Laeuft",
            MachinePhase.PAUSED: "Pausiert",
            MachinePhase.ALARM: "Alarm",
            MachinePhase.ERROR: "Fehler",
            MachinePhase.STOPPING: "Stoppt",
        }
        self.connection_label.setText(labels.get(state.phase, state.message))
        color = "#188038" if state.connected else "#d93025"
        if state.phase in {MachinePhase.ALARM, MachinePhase.ERROR}:
            color = "#d93025"
        elif state.phase in {MachinePhase.CONNECTING, MachinePhase.RUNNING, MachinePhase.STOPPING}:
            color = "#f29900"
        self.connection_label.setStyleSheet(f"color: {color}; font-weight: 600;")
        for action_id, buttons in self.action_buttons.items():
            enabled = self._action_registry.is_enabled(action_id, state)
            for button in buttons:
                button.setEnabled(enabled)

    def _action_button(self, action_id: str) -> QPushButton:
        definition = self._action_registry.get(action_id)
        button = QPushButton(definition.label)
        button.setObjectName(f"machineAction_{action_id}")
        button.setToolTip(definition.tooltip)
        button.clicked.connect(lambda _checked=False, item=action_id: self.action_triggered.emit(item, "Sidebar"))
        button.setMinimumHeight(32 if action_id in {"connect", "disconnect", "home"} else 30)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.action_buttons.setdefault(action_id, []).append(button)
        return button

    def _profile_index_changed(self, index: int) -> None:
        profile_id = self.profile_select.itemData(index)
        if profile_id:
            self.profile_changed.emit(str(profile_id))

    def _sync_advanced_visibility(self, checked: bool) -> None:
        for widget in (self.refresh_button, self.detect_button, self.profile_edit_button):
            widget.setVisible(checked)
