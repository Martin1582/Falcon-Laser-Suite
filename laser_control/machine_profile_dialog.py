from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from laser_control.machine_profiles import (
    DEFAULT_MACHINE_PROFILE,
    MachineProfile,
    SUPPORTED_CONTROLLER_TYPES,
    make_unique_profile_id,
    validate_machine_profile,
)


class MachineProfileDialog(QDialog):
    def __init__(
        self,
        profiles: list[MachineProfile],
        active_profile_id: str,
        validation_failed: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Maschinenprofile")
        self.setMinimumWidth(440)
        self._profiles = {profile.profile_id: profile for profile in profiles}
        self._validation_failed = validation_failed
        self.saved_profile: MachineProfile | None = None
        self.saved_existing_profile = active_profile_id in self._profiles
        self._current_profile_id = active_profile_id if active_profile_id in self._profiles else DEFAULT_MACHINE_PROFILE.profile_id
        self._is_new_profile = False

        layout = QVBoxLayout(self)
        profile_row = QHBoxLayout()
        self.profile_select = QComboBox()
        self.profile_select.currentIndexChanged.connect(self._profile_selection_changed)
        self.new_button = QPushButton("Neu")
        self.new_button.clicked.connect(self._create_new_profile)
        profile_row.addWidget(QLabel("Profil"))
        profile_row.addWidget(self.profile_select, 1)
        profile_row.addWidget(self.new_button)
        layout.addLayout(profile_row)

        form = QFormLayout()
        self.profile_name = QLineEdit()
        self.machine_name = QLineEdit()
        self.controller_type = QComboBox()
        self.controller_type.addItems(SUPPORTED_CONTROLLER_TYPES)
        self.work_area_width = self._double_spin(1.0, 5000.0, " mm")
        self.work_area_height = self._double_spin(1.0, 5000.0, " mm")
        self.default_port = QLineEdit()
        self.baudrate = QSpinBox()
        self.baudrate.setRange(1200, 1000000)
        self.baudrate.setSingleStep(9600)
        self.homing_required = QCheckBox("Homing vor Hardwarestart verlangen")
        self.max_speed = QSpinBox()
        self.max_speed.setRange(1, 200000)
        self.max_speed.setSuffix(" mm/min")
        self.max_power = QSpinBox()
        self.max_power.setRange(1, 100)
        self.max_power.setSuffix(" %")
        self.notes = QTextEdit()
        self.notes.setFixedHeight(72)

        form.addRow("Profilname", self.profile_name)
        form.addRow("Maschinenname", self.machine_name)
        form.addRow("Controller", self.controller_type)
        form.addRow("Arbeitsbereich Breite", self.work_area_width)
        form.addRow("Arbeitsbereich Hoehe", self.work_area_height)
        form.addRow("Standard-Port", self.default_port)
        form.addRow("Baudrate", self.baudrate)
        form.addRow("Homing", self.homing_required)
        form.addRow("Max. Geschwindigkeit", self.max_speed)
        form.addRow("Max. Laserleistung", self.max_power)
        form.addRow("Notizen", self.notes)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save_profile)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh_profile_select(self._current_profile_id)

    @property
    def is_new_profile(self) -> bool:
        return not self.saved_existing_profile

    def _double_spin(self, minimum: float, maximum: float, suffix: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(1)
        spin.setSuffix(suffix)
        return spin

    def _refresh_profile_select(self, selected_profile_id: str) -> None:
        self.profile_select.blockSignals(True)
        self.profile_select.clear()
        for profile in sorted(self._profiles.values(), key=lambda item: item.name.lower()):
            self.profile_select.addItem(profile.name, profile.profile_id)
        index = self.profile_select.findData(selected_profile_id)
        self.profile_select.setCurrentIndex(max(0, index))
        self.profile_select.blockSignals(False)
        self._load_profile_from_id(str(self.profile_select.currentData() or selected_profile_id))

    def _profile_selection_changed(self, index: int) -> None:
        profile_id = self.profile_select.itemData(index)
        if profile_id:
            self._load_profile_from_id(str(profile_id))

    def _load_profile_from_id(self, profile_id: str) -> None:
        profile = self._profiles.get(profile_id, DEFAULT_MACHINE_PROFILE)
        self._current_profile_id = profile.profile_id
        self._is_new_profile = False
        self.profile_name.setText(profile.name)
        self.machine_name.setText(profile.machine_name)
        index = self.controller_type.findText(profile.controller_type)
        self.controller_type.setCurrentIndex(max(0, index))
        self.work_area_width.setValue(profile.work_area_width)
        self.work_area_height.setValue(profile.work_area_height)
        self.default_port.setText(profile.default_port)
        self.baudrate.setValue(profile.baudrate)
        self.homing_required.setChecked(profile.homing_required)
        self.max_speed.setValue(profile.max_speed)
        self.max_power.setValue(profile.max_power)
        self.notes.setPlainText(profile.notes)

    def _create_new_profile(self) -> None:
        base = DEFAULT_MACHINE_PROFILE
        existing_ids = set(self._profiles)
        profile_id = make_unique_profile_id("Neues Maschinenprofil", existing_ids)
        profile = replace(
            base,
            profile_id=profile_id,
            name="Neues Maschinenprofil",
            machine_name="Neue GRBL-Maschine",
            default_port="",
            homing_required=True,
            notes="",
        )
        self._profiles[profile.profile_id] = profile
        self._refresh_profile_select(profile.profile_id)
        self._is_new_profile = True

    def _save_profile(self) -> None:
        original_id = self._current_profile_id
        profile_id = original_id
        if self._is_new_profile:
            profile_id = make_unique_profile_id(self.profile_name.text(), set(self._profiles) - {original_id})
        profile = MachineProfile(
            profile_id=profile_id,
            name=self.profile_name.text().strip(),
            machine_name=self.machine_name.text().strip(),
            controller_type=self.controller_type.currentText(),
            work_area_width=self.work_area_width.value(),
            work_area_height=self.work_area_height.value(),
            default_port=self.default_port.text().strip(),
            baudrate=self.baudrate.value(),
            homing_required=self.homing_required.isChecked(),
            max_speed=self.max_speed.value(),
            max_power=self.max_power.value(),
            notes=self.notes.toPlainText().strip(),
        )
        errors = validate_machine_profile(profile, set(self._profiles) - {original_id}, original_id)
        if errors:
            message = "\n".join(errors)
            if self._validation_failed is not None:
                self._validation_failed(message)
            QMessageBox.warning(self, "Profil ungueltig", message)
            return
        self.saved_existing_profile = not self._is_new_profile
        self.saved_profile = profile
        self.accept()
