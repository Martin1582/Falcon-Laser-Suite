from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
)

from laser_control.layers import JobLayer, LayerMode, LayerType, OverscanMode
from laser_control.workflow_controller import PreflightResult


class LayerPanel(QGroupBox):
    def __init__(self, on_changed: Callable[[], None] | None = None) -> None:
        super().__init__("Layer / Operation")
        self._on_changed = on_changed
        self._layers: list[JobLayer] = []
        self._updating = False
        self._fill_available = False

        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Aktiv", "Sichtbar", "Name", "Modus", "Speed", "Power", "Passes"])
        self.table.verticalHeader().setVisible(False)
        self.table.itemChanged.connect(self._item_changed)
        self.table.currentCellChanged.connect(self._selected_row_changed)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setMinimumHeight(150)
        self.table.setMaximumHeight(230)
        layout.addWidget(self.table)
        self.empty_state = QLabel("Noch keine Layer vorhanden.\nLayer werden automatisch nach dem Import erzeugt.")
        self.empty_state.setObjectName("layerEmptyState")
        self.empty_state.setWordWrap(True)
        self.empty_state.setVisible(False)
        layout.addWidget(self.empty_state)

        self.detail_group = QGroupBox("Ausgewaehlter Layer")
        detail_layout = QGridLayout(self.detail_group)
        self.layer_detail_label = QLabel("Kein Layer ausgewaehlt")
        self.layer_detail_label.setWordWrap(True)
        self.fill_spacing = QComboBox()
        for spacing in (0.05, 0.08, 0.10, 0.15, 0.20):
            self.fill_spacing.addItem(f"{spacing:.2f} mm", spacing)
        self.fill_angle = QComboBox()
        for angle in (0, 45, 90):
            self.fill_angle.addItem(f"{angle} deg", angle)
        self.fill_spacing.currentIndexChanged.connect(self._detail_changed)
        self.fill_angle.currentIndexChanged.connect(self._detail_changed)
        self.overscan_enabled = QCheckBox("Overscan")
        self.overscan_enabled.setToolTip(
            "Fuegt bei Gravurlinien zusaetzlichen Fahrweg hinzu, damit der Falcon 10W gleichmaessiger beschleunigen kann."
        )
        self.overscan_mode = QComboBox()
        for mode in OverscanMode:
            self.overscan_mode.addItem(mode.value, mode.value)
        self.overscan_mode.setToolTip("Automatische oder manuelle Overscan-Laenge fuer Vektorgravur.")
        self.overscan_value = QDoubleSpinBox()
        self.overscan_value.setRange(0.1, 10.0)
        self.overscan_value.setDecimals(1)
        self.overscan_value.setSingleStep(0.5)
        self.overscan_value.setSuffix(" mm")
        self.overscan_value.setToolTip("Manuelle Overscan-Laenge in Millimetern.")
        self.overscan_enabled.toggled.connect(self._detail_changed)
        self.overscan_mode.currentIndexChanged.connect(self._detail_changed)
        self.overscan_value.valueChanged.connect(self._detail_changed)
        self.fill_info = QLabel("SVG-Flaechenfuellung ist nur fuer Vektordateien verfuegbar.")
        self.fill_info.setWordWrap(True)
        detail_layout.addWidget(self.layer_detail_label, 0, 0, 1, 4)
        detail_layout.addWidget(QLabel("Fuellabstand"), 1, 0)
        detail_layout.addWidget(self.fill_spacing, 1, 1)
        detail_layout.addWidget(QLabel("Winkel"), 1, 2)
        detail_layout.addWidget(self.fill_angle, 1, 3)
        detail_layout.addWidget(self.overscan_enabled, 2, 0)
        detail_layout.addWidget(self.overscan_mode, 2, 1)
        detail_layout.addWidget(self.overscan_value, 2, 2, 1, 2)
        detail_layout.addWidget(self.fill_info, 3, 0, 1, 4)
        layout.addWidget(self.detail_group)
        self._sync_detail_controls(-1)

    def set_layers(self, layers: list[JobLayer]) -> None:
        selected_row = self.table.currentRow()
        self._updating = True
        try:
            self._layers = [
                JobLayer(
                    layer.name,
                    layer.layer_type,
                    layer.visible,
                    layer.enabled,
                    layer.speed_mm_min,
                    layer.power_percent,
                    layer.order,
                    layer.passes,
                    layer.mode,
                    layer.fill_spacing_mm,
                    layer.fill_angle_deg,
                    layer.overscan_enabled,
                    layer.overscan_mode,
                    layer.overscan_mm,
                )
                for layer in layers
            ]
            self.table.setRowCount(len(self._layers))
            self.empty_state.setVisible(not self._layers)
            for row, layer in enumerate(self._layers):
                self._set_check_item(row, 0, layer.enabled)
                self._set_check_item(row, 1, layer.visible)
                self._set_text_item(row, 2, layer.name)
                self._set_mode_widget(row, layer.mode)
                self._set_number_item(row, 4, layer.speed_mm_min, " mm/min")
                self._set_number_item(row, 5, layer.power_percent, " %")
                self._set_number_item(row, 6, layer.passes, " x")
            self.table.resizeColumnsToContents()
            if self._layers:
                self.table.setCurrentCell(min(max(selected_row, 0), len(self._layers) - 1), 2)
        finally:
            self._updating = False
        self._sync_detail_controls(self.table.currentRow())

    def layers(self) -> list[JobLayer]:
        result: list[JobLayer] = []
        for row, layer in enumerate(self._layers):
            enabled = self.table.item(row, 0).checkState() == Qt.CheckState.Checked
            visible = self.table.item(row, 1).checkState() == Qt.CheckState.Checked
            speed = self._item_int(row, 4, layer.speed_mm_min)
            power = self._item_int(row, 5, layer.power_percent)
            passes = self._item_int(row, 6, layer.passes)
            mode_widget = self.table.cellWidget(row, 3)
            mode = LayerMode(mode_widget.currentData()) if isinstance(mode_widget, QComboBox) else layer.mode
            result.append(
                JobLayer(
                    name=layer.name,
                    layer_type=LayerType(layer.layer_type),
                    visible=visible,
                    enabled=enabled,
                    speed_mm_min=speed,
                    power_percent=power,
                    order=layer.order,
                    passes=passes,
                    mode=mode,
                    fill_spacing_mm=layer.fill_spacing_mm,
                    fill_angle_deg=layer.fill_angle_deg,
                    overscan_enabled=layer.overscan_enabled,
                    overscan_mode=layer.overscan_mode,
                    overscan_mm=layer.overscan_mm,
                )
            )
        return result

    def set_fill_available(self, available: bool, reason: str = "") -> None:
        self._fill_available = available
        self._updating = True
        try:
            for row, layer in enumerate(self._layers):
                combo = self.table.cellWidget(row, 3)
                if not isinstance(combo, QComboBox):
                    continue
                combo.setEnabled(available)
                if not available and layer.uses_fill:
                    layer.mode = LayerMode.OUTLINE
                    combo.setCurrentIndex(max(0, combo.findData(LayerMode.OUTLINE.value)))
        finally:
            self._updating = False
        self.fill_info.setStyleSheet("")
        self.fill_info.setText(
            reason
            or (
                "Geschlossene Vektorkonturen koennen gefuellt oder als Kontur + Fuellung ausgegeben werden."
                if available
                else "SVG-Flaechenfuellung ist nur fuer Vektordateien verfuegbar."
            )
        )
        self._sync_detail_controls(self.table.currentRow())

    def set_fill_warning(self, warning: str = "") -> None:
        if not warning:
            self.set_fill_available(self._fill_available)
            return
        self.fill_info.setText(warning)
        self.fill_info.setStyleSheet("color: #b06000; font-weight: 600;")

    def _set_check_item(self, row: int, column: int, checked: bool) -> None:
        item = QTableWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.table.setItem(row, column, item)

    def _set_text_item(self, row: int, column: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self.table.setItem(row, column, item)

    def _set_number_item(self, row: int, column: int, value: int, suffix: str = "") -> None:
        item = QTableWidgetItem(f"{value}{suffix}")
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, column, item)

    def _set_mode_widget(self, row: int, mode: LayerMode) -> None:
        combo = QComboBox()
        for item in LayerMode:
            combo.addItem(item.value, item.value)
        combo.setCurrentIndex(max(0, combo.findData(mode.value)))
        combo.setEnabled(self._fill_available)
        combo.setToolTip("Kontur, Fuellung oder Kontur + Fuellung")
        combo.currentIndexChanged.connect(lambda _value, current_row=row: self._mode_changed(current_row))
        self.table.setCellWidget(row, 3, combo)

    def _item_int(self, row: int, column: int, fallback: int) -> int:
        item = self.table.item(row, column)
        if item is None:
            return fallback
        raw = item.text().strip().split()[0].replace("%", "")
        try:
            return int(float(raw))
        except ValueError:
            return fallback

    def _item_changed(self, _item: QTableWidgetItem) -> None:
        if not self._updating and self._on_changed is not None:
            self._on_changed()

    def _widget_changed(self) -> None:
        if not self._updating and self._on_changed is not None:
            self._on_changed()

    def _mode_changed(self, row: int) -> None:
        if self._updating or not 0 <= row < len(self._layers):
            return
        combo = self.table.cellWidget(row, 3)
        if isinstance(combo, QComboBox):
            self._layers[row].mode = LayerMode(combo.currentData())
        if row == self.table.currentRow():
            self._sync_detail_controls(row)
        self._widget_changed()

    def _selected_row_changed(self, row: int, _column: int, _previous_row: int, _previous_column: int) -> None:
        self._sync_detail_controls(row)

    def _sync_detail_controls(self, row: int) -> None:
        self._updating = True
        try:
            valid = 0 <= row < len(self._layers)
            self.layer_detail_label.setText(
                f"{self._layers[row].name} | {self._layers[row].layer_type.value} | Reihenfolge {self._layers[row].order}"
                if valid
                else "Kein Layer ausgewaehlt"
            )
            if not valid:
                self.fill_spacing.setEnabled(False)
                self.fill_angle.setEnabled(False)
                self.overscan_enabled.setEnabled(False)
                self.overscan_mode.setEnabled(False)
                self.overscan_value.setEnabled(False)
                return
            layer = self._layers[row]
            spacing_index = self.fill_spacing.findData(layer.fill_spacing_mm)
            self.fill_spacing.setCurrentIndex(spacing_index if spacing_index >= 0 else self.fill_spacing.findData(0.08))
            self.fill_angle.setCurrentIndex(max(0, self.fill_angle.findData(layer.fill_angle_deg)))
            self.overscan_enabled.setChecked(layer.overscan_enabled)
            self.overscan_mode.setCurrentIndex(max(0, self.overscan_mode.findData(layer.overscan_mode.value)))
            self.overscan_value.setValue(layer.overscan_mm)
            enabled = self._fill_available and layer.uses_fill
            overscan_available = enabled and layer.layer_type == LayerType.ENGRAVE
            self.fill_spacing.setEnabled(enabled)
            self.fill_angle.setEnabled(enabled)
            self.overscan_enabled.setEnabled(overscan_available)
            self.overscan_mode.setEnabled(overscan_available and layer.overscan_enabled)
            self.overscan_value.setEnabled(
                overscan_available
                and layer.overscan_enabled
                and layer.overscan_mode == OverscanMode.MANUAL
            )
        finally:
            self._updating = False

    def _detail_changed(self, _value) -> None:
        if self._updating:
            return
        row = self.table.currentRow()
        if not 0 <= row < len(self._layers):
            return
        spacing = self.fill_spacing.currentData()
        angle = self.fill_angle.currentData()
        if spacing is not None:
            self._layers[row].fill_spacing_mm = float(spacing)
        if angle is not None:
            self._layers[row].fill_angle_deg = int(angle)
        self._layers[row].overscan_enabled = self.overscan_enabled.isChecked()
        mode = self.overscan_mode.currentData()
        if mode is not None:
            self._layers[row].overscan_mode = OverscanMode(mode)
        self._layers[row].overscan_mm = self.overscan_value.value()
        self._sync_detail_controls(row)
        self._widget_changed()


class WorkspaceScanPanel(QGroupBox):
    def __init__(self, trace_button: QPushButton, pointer_test_button: QPushButton) -> None:
        super().__init__("Arbeitsflaeche abfahren")
        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        self.trace_button = trace_button
        self.pointer_test_button = pointer_test_button
        self.status_label = QLabel("Arbeitsflaechenmodus aus")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.trace_button)
        layout.addWidget(self.pointer_test_button)
        layout.addWidget(self.status_label)
        self.set_active(False)

    def set_active(self, active: bool) -> None:
        self.status_label.setText(
            "Arbeitsflaechenmodus aktiv - Laser aus. Stop beendet nach dem aktuellen Segment; Sicherheitsstopp bricht sofort ab."
            if active
            else "Arbeitsflaechenmodus aus"
        )
        self.status_label.setStyleSheet("color: #b06000; font-weight: 700;" if active else "color: #777777;")
        self.trace_button.blockSignals(True)
        self.trace_button.setChecked(active)
        self.trace_button.setText("Arbeitsflaeche stoppen" if active else "Arbeitsflaeche abfahren")
        self.trace_button.blockSignals(False)


class PreflightDialog(QDialog):
    def __init__(self, preflight: PreflightResult, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preflight")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        heading = QLabel("Bitte pruefe den Job vor dem echten Start.")
        heading.setWordWrap(True)
        layout.addWidget(heading)

        self._preflight = preflight
        self.unhomed_confirmation: QCheckBox | None = None
        if preflight.requires_unhomed_confirmation:
            self.unhomed_confirmation = QCheckBox("Start ohne erkannte Referenzfahrt bewusst bestaetigen")
            self.unhomed_confirmation.setToolTip(preflight.context.homing_warning)
            self.unhomed_confirmation.stateChanged.connect(self._sync_start_button)
            layout.addWidget(self.unhomed_confirmation)

        summary = QTextEdit()
        summary.setReadOnly(True)
        summary.setPlainText("\n".join(preflight.summary_lines() + ["", "Startdiagnose:"] + preflight.start_condition_lines()))
        summary.setMinimumHeight(320)
        self.summary = summary
        layout.addWidget(summary)

        self.start_hint = QLabel("")
        self.start_hint.setWordWrap(True)
        layout.addWidget(self.start_hint)

        buttons = QDialogButtonBox()
        self.start_button = buttons.addButton("Start bestaetigen", QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel_button = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self._sync_start_button()
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _sync_start_button(self, *_args) -> None:
        confirmed_unhomed = self.unhomed_confirmation is None or self.unhomed_confirmation.isChecked()
        start_enabled = self._preflight.start_button_enabled(confirmed_unhomed)
        reasons = self._preflight.start_button_disabled_reasons(confirmed_unhomed)
        self.start_button.setEnabled(start_enabled)
        self.start_button.setToolTip("" if start_enabled else "\n".join(reasons))
        if start_enabled:
            self.start_hint.setText("Start ist freigegeben.")
            self.start_hint.setStyleSheet("color: #188038; font-weight: 700;")
        else:
            self.start_hint.setText("Start gesperrt: " + "; ".join(reasons))
            self.start_hint.setStyleSheet("color: #d93025; font-weight: 700;")
            parent_log = getattr(self.parent(), "log", None)
            if callable(parent_log):
                parent_log("Preflight Startbutton deaktiviert: " + "; ".join(reasons))
        if hasattr(self, "summary"):
            self.summary.setPlainText(
                "\n".join(
                    self._preflight.summary_lines()
                    + [""]
                    + ["Startdiagnose:"]
                    + self._preflight.start_condition_lines(confirmed_unhomed)
                )
            )
