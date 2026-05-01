import sys
import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QToolBox,
    QVBoxLayout,
    QWidget,
)

from laser_control.gcode import (
    CUT_MODE,
    ENGRAVE_MODE,
    build_polyline_gcode,
    build_rectangle_frame_gcode,
)
from laser_control.laser import SimulatedLaserController
from laser_control.job_history import (
    JobHistoryEntry,
    append_job_history,
    export_job_history,
    import_job_history,
    load_job_history,
    now_timestamp,
)
from laser_control.material_db import delete_material, find_material, load_materials, upsert_material
from laser_control.models import MaterialProfile
from laser_control.profiles import DEFAULT_PROFILES
from laser_control.project import load_project, project_to_dict, save_project
from laser_control.serial_autodetect import find_laser_port
from laser_control.serial_grbl import GrblSerialController, list_serial_ports
from laser_control.services.assistant_service import AssistantService
from laser_control.services.job_service import JobPreparation, JobService
from laser_control.services.profile_service import ProfileService
from laser_control.svg_import import fit_paths_to_area, import_svg, scale_paths_to_width


class WorkerSignals(QObject):
    log = Signal(str)
    progress = Signal(str, int, int)
    error = Signal(str)
    finished = Signal()
    port_detected = Signal(str)


class WorkAreaPreview(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(360, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.width_mm = 300.0
        self.height_mm = 200.0
        self.paths = []

    def set_preview(self, width_mm: float, height_mm: float, paths: list) -> None:
        self.width_mm = max(1.0, width_mm)
        self.height_mm = max(1.0, height_mm)
        self.paths = paths
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#f7f7f7"))

        margin = 18
        available_w = max(1, self.width() - margin * 2)
        available_h = max(1, self.height() - margin * 2)
        scale = min(available_w / self.width_mm, available_h / self.height_mm)
        area_w = self.width_mm * scale
        area_h = self.height_mm * scale
        origin_x = (self.width() - area_w) / 2
        origin_y = (self.height() - area_h) / 2

        painter.setPen(QPen(QColor("#9aa0a6"), 1))
        painter.drawRect(int(origin_x), int(origin_y), int(area_w), int(area_h))

        if self.paths:
            painter.setPen(QPen(QColor("#d93025"), 2))
            for polyline in self.paths:
                for index in range(1, len(polyline)):
                    x1, y1 = polyline[index - 1]
                    x2, y2 = polyline[index]
                    painter.drawLine(
                        int(origin_x + x1 * scale),
                        int(origin_y + y1 * scale),
                        int(origin_x + x2 * scale),
                        int(origin_y + y2 * scale),
                    )
        else:
            painter.setPen(QPen(QColor("#d93025"), 2))
            painter.drawRect(int(origin_x), int(origin_y), int(area_w), int(area_h))


class LaserControlWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Laser Control")
        self.resize(1120, 720)
        self.setMinimumSize(980, 620)

        self.imported_paths = []
        self.original_imported_paths = []
        self.imported_file = None
        self.material_point_a = None
        self.material_point_b = None
        self.material_measurement = None
        self.current_project_path = None
        self.material_db_records = load_materials()
        self.profile_service = ProfileService()
        self.job_service = JobService()
        self.assistant_service = AssistantService()
        self.job_history = load_job_history()
        self.material_profiles = self.profile_service.material_profiles
        self.last_prepared_job = None
        self.worker_busy = False

        self.signals = WorkerSignals()
        self.signals.log.connect(self.log)
        self.signals.progress.connect(self._set_progress)
        self.signals.error.connect(self._show_worker_error)
        self.signals.finished.connect(self._worker_finished)
        self.signals.port_detected.connect(self._apply_detected_port)

        self.controller = SimulatedLaserController(self._threadsafe_log, self._threadsafe_progress)
        self.active_connection_mode = "Simulator"

        self._build_layout()
        self._refresh_material_db_combo()
        self._apply_mode_profile_to_controls()
        self._refresh_ports()
        self._refresh_gcode()
        self._draw_preview()

    def _build_layout(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 8)
        self.setCentralWidget(root)

        self._build_action_bar(root_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root_layout.addWidget(splitter, 1)

        self.sidebar_toolbox = QToolBox()
        self.sidebar_toolbox.setMinimumWidth(280)
        self.sidebar_toolbox.setMaximumWidth(340)
        splitter.addWidget(self.sidebar_toolbox)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        splitter.addWidget(content)
        splitter.setStretchFactor(1, 1)

        self._build_sidebar(self.sidebar_toolbox)
        self._build_content(content_layout)
        self._build_status_bar(root_layout)

    def _build_action_bar(self, layout: QVBoxLayout) -> None:
        action_bar = QFrame()
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(0, 0, 0, 8)
        action_layout.setSpacing(8)
        action_layout.addWidget(self._button("Verbinden", lambda: self._run_controller_action(lambda c: c.connect())))
        action_layout.addWidget(self._button("Laser suchen", self._auto_detect_laser))
        action_layout.addWidget(self._button("Home", lambda: self._run_controller_action(lambda c: c.home())))
        action_layout.addWidget(self._button("Rahmen", self._frame_job))
        action_layout.addWidget(self._button("Dry Run", self._dry_run_job))
        start_button = self._button("Start", self._start_job)
        start_button.setObjectName("primaryStartButton")
        start_button.setStyleSheet("#primaryStartButton { font-weight: 700; }")
        action_layout.addWidget(start_button)
        action_layout.addWidget(self._button("Stop", lambda: self._run_controller_action(lambda c: c.stop(), True)))
        action_layout.addStretch(1)
        layout.addWidget(action_bar)

    def _build_sidebar(self, toolbox: QToolBox) -> None:
        machine_page = QWidget()
        machine_layout = QVBoxLayout(machine_page)
        machine_layout.setContentsMargins(8, 8, 8, 8)
        machine_layout.setSpacing(8)

        connection = QGroupBox("Verbindung")
        form = QVBoxLayout(connection)
        form.setSpacing(5)
        self.connection_label = QLabel("Nicht verbunden")
        form.addWidget(self.connection_label)
        self.connection_mode = QComboBox()
        self.connection_mode.addItems(["Simulator", "GRBL ueber USB"])
        self.connection_mode.currentTextChanged.connect(self._switch_controller)
        form.addWidget(self.connection_mode)
        self.serial_port = QComboBox()
        form.addWidget(self.serial_port)
        form.addWidget(self._button("Ports suchen", self._refresh_ports))
        form.addWidget(self._button("Laser automatisch finden", self._auto_detect_laser))
        form.addWidget(self._button("Verbinden", lambda: self._run_controller_action(lambda c: c.connect())))
        form.addWidget(self._button("Trennen", lambda: self._run_controller_action(lambda c: c.disconnect())))
        form.addWidget(self._button("Referenzfahrt", lambda: self._run_controller_action(lambda c: c.home())))
        form.addWidget(self._button("Status abfragen", self._query_status))
        form.addWidget(self._button("GRBL Settings", self._query_settings))
        machine_layout.addWidget(connection)

        jog_group = QGroupBox("Jog")
        jog = QGridLayout(jog_group)
        jog.setHorizontalSpacing(6)
        jog.setVerticalSpacing(6)
        jog.addWidget(self._button("Y+", lambda: self._run_controller_action(lambda c: c.jog(0, 10))), 0, 1)
        jog.addWidget(self._button("X-", lambda: self._run_controller_action(lambda c: c.jog(-10, 0))), 1, 0)
        jog.addWidget(self._button("X+", lambda: self._run_controller_action(lambda c: c.jog(10, 0))), 1, 2)
        jog.addWidget(self._button("Y-", lambda: self._run_controller_action(lambda c: c.jog(0, -10))), 2, 1)
        machine_layout.addWidget(jog_group)
        machine_layout.addStretch(1)
        toolbox.addItem(machine_page, "Maschine")

        material_page = QWidget()
        material_page_layout = QVBoxLayout(material_page)
        material_page_layout.setContentsMargins(8, 8, 8, 8)
        material_page_layout.setSpacing(8)
        material = QGroupBox("Material")
        material_layout = QVBoxLayout(material)
        material_layout.setSpacing(5)
        self.material_measurement_label = QLabel("Nicht eingemessen")
        self.material_measurement_label.setWordWrap(True)
        material_layout.addWidget(self.material_measurement_label)
        material_layout.addWidget(self._button("Ecke 1 setzen", lambda: self._capture_material_point(1)))
        material_layout.addWidget(self._button("Ecke 2 setzen", lambda: self._capture_material_point(2)))
        material_layout.addWidget(self._button("Groesse uebernehmen", self._apply_material_measurement))
        self.material_db_name = QComboBox()
        self.material_db_name.setEditable(True)
        material_layout.addWidget(QLabel("Name"))
        material_layout.addWidget(self.material_db_name)
        size_row = QHBoxLayout()
        self.material_db_width = self._double_spin(0, 2000, 0)
        self.material_db_height = self._double_spin(0, 2000, 0)
        size_row.addWidget(QLabel("B"))
        size_row.addWidget(self.material_db_width)
        size_row.addWidget(QLabel("H"))
        size_row.addWidget(self.material_db_height)
        material_layout.addLayout(size_row)
        material_layout.addWidget(self._button("Material speichern", self._save_measured_material))
        self.material_db_selection = QComboBox()
        self.material_db_selection.currentTextChanged.connect(lambda _text: self._select_material_record())
        material_layout.addWidget(self.material_db_selection)
        material_layout.addWidget(self._button("Material laden", self._load_measured_material))
        material_layout.addWidget(self._button("Material loeschen", self._delete_measured_material))
        material_page_layout.addWidget(material)
        material_page_layout.addStretch(1)
        toolbox.addItem(material_page, "Material")

        job_page = QWidget()
        job_page_layout = QVBoxLayout(job_page)
        job_page_layout.setContentsMargins(8, 8, 8, 8)
        job_page_layout.setSpacing(8)
        job = QGroupBox("Job")
        job_layout = QVBoxLayout(job)
        job_layout.setSpacing(5)
        self.operation_mode = QComboBox()
        self.operation_mode.addItems([ENGRAVE_MODE, CUT_MODE])
        self.operation_mode.currentTextChanged.connect(self._on_operation_mode_changed)
        job_layout.addWidget(QLabel("Modus"))
        job_layout.addWidget(self.operation_mode)
        job_layout.addWidget(self._button("Rahmen fahren", self._frame_job))
        job_layout.addWidget(self._button("Dry Run", self._dry_run_job))
        job_layout.addWidget(self._button("Start", self._start_job))
        job_layout.addWidget(self._button("Pause", lambda: self._run_controller_action(lambda c: c.pause(), True)))
        job_layout.addWidget(self._button("Fortsetzen", lambda: self._run_controller_action(lambda c: c.resume(), True)))
        job_layout.addWidget(self._button("Stop", lambda: self._run_controller_action(lambda c: c.stop(), True)))
        job_page_layout.addWidget(job)

        project = QGroupBox("Projekt")
        project_layout = QVBoxLayout(project)
        project_layout.setSpacing(5)
        project_layout.addWidget(self._button("SVG importieren", self._import_svg))
        project_layout.addWidget(self._button("Speichern", self._save_project))
        project_layout.addWidget(self._button("Laden", self._load_project))
        project_layout.addWidget(self._button("Profile exportieren", self._export_profiles))
        project_layout.addWidget(self._button("Profile importieren", self._import_profiles))
        job_page_layout.addWidget(project)

        intelligence = QGroupBox("Assistenz")
        intelligence_layout = QVBoxLayout(intelligence)
        intelligence_layout.setSpacing(5)
        intelligence_layout.addWidget(self._button("Analysieren", lambda: self._update_assistant_panel()))
        intelligence_layout.addWidget(self._button("Testmatrix erzeugen", self._generate_test_matrix))
        intelligence_layout.addWidget(self._button("Als gut speichern", lambda: self._record_job_result("good")))
        intelligence_layout.addWidget(self._button("Problem speichern", lambda: self._record_job_result("problem")))
        intelligence_layout.addWidget(self._button("Historie exportieren", self._export_history))
        intelligence_layout.addWidget(self._button("Historie importieren", self._import_history))
        job_page_layout.addWidget(intelligence)
        job_page_layout.addStretch(1)
        toolbox.addItem(job_page, "Job")

    def _build_content(self, layout: QVBoxLayout) -> None:
        settings = QFrame()
        settings_layout = QHBoxLayout(settings)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        self.work_width = self._double_spin(10, 2000, 300)
        self.work_height = self._double_spin(10, 2000, 200)
        self.profile_name = QComboBox()
        self.profile_name.addItems(self.profile_service.names())
        self.profile_name.currentTextChanged.connect(lambda _text: self._profile_selected())
        for widget in (self.work_width, self.work_height):
            widget.valueChanged.connect(self._settings_changed)
        settings_layout.addWidget(QLabel("Arbeitsbereich"))
        settings_layout.addWidget(self.work_width)
        settings_layout.addWidget(QLabel("x"))
        settings_layout.addWidget(self.work_height)
        settings_layout.addWidget(QLabel("mm"))
        settings_layout.addSpacing(16)
        settings_layout.addWidget(QLabel("Material"))
        settings_layout.addWidget(self.profile_name, 1)
        layout.addWidget(settings)

        material_settings = QFrame()
        material_layout = QHBoxLayout(material_settings)
        material_layout.setContentsMargins(0, 0, 0, 0)
        self.power_percent = self._spin(0, 100, DEFAULT_PROFILES[0].power_percent)
        self.speed_mm_min = self._spin(50, 12000, DEFAULT_PROFILES[0].speed_mm_min, 50)
        self.passes = self._spin(1, 20, DEFAULT_PROFILES[0].passes)
        for widget in (self.power_percent, self.speed_mm_min, self.passes):
            widget.valueChanged.connect(self._material_settings_changed)
        material_layout.addWidget(QLabel("Leistung %"))
        material_layout.addWidget(self.power_percent)
        material_layout.addWidget(QLabel("Geschwindigkeit"))
        material_layout.addWidget(self.speed_mm_min)
        material_layout.addWidget(QLabel("Durchgaenge"))
        material_layout.addWidget(self.passes)
        material_layout.addStretch(1)
        layout.addWidget(material_settings)

        self.job_summary = QLabel("Kein Job analysiert.")
        self.job_summary.setWordWrap(True)
        layout.addWidget(self.job_summary)

        self.assistant_summary = QTextEdit()
        self.assistant_summary.setReadOnly(True)
        self.assistant_summary.setMaximumHeight(120)
        self.assistant_summary.setStyleSheet("background: #fbfbfb;")
        layout.addWidget(self.assistant_summary)

        placement = QGroupBox("SVG Platzierung")
        placement_layout = QGridLayout(placement)
        self.svg_auto = QRadioButton("Automatisch")
        self.svg_manual = QRadioButton("Manuell")
        self.svg_auto.setChecked(True)
        self.svg_auto.toggled.connect(lambda _checked: self._apply_svg_placement())
        self.svg_margin = self._double_spin(0, 50, 5)
        self.svg_manual_width = self._double_spin(1, 400, 50)
        self.svg_offset_x = self._double_spin(0, 400, 0)
        self.svg_offset_y = self._double_spin(0, 415, 0)
        for widget in (self.svg_margin, self.svg_manual_width, self.svg_offset_x, self.svg_offset_y):
            widget.valueChanged.connect(lambda _value: self._apply_svg_placement())
        placement_layout.addWidget(self.svg_auto, 0, 0)
        placement_layout.addWidget(self.svg_manual, 0, 1)
        placement_layout.addWidget(QLabel("Rand"), 1, 0)
        placement_layout.addWidget(self.svg_margin, 1, 1)
        placement_layout.addWidget(QLabel("Breite"), 1, 2)
        placement_layout.addWidget(self.svg_manual_width, 1, 3)
        placement_layout.addWidget(QLabel("X"), 2, 0)
        placement_layout.addWidget(self.svg_offset_x, 2, 1)
        placement_layout.addWidget(QLabel("Y"), 2, 2)
        placement_layout.addWidget(self.svg_offset_y, 2, 3)
        layout.addWidget(placement)

        middle = QSplitter(Qt.Orientation.Horizontal)
        self.preview = WorkAreaPreview()
        preview_group = QGroupBox("Vorschau")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.addWidget(self.preview)
        middle.addWidget(preview_group)
        self.gcode_group = QGroupBox("G-Code")
        gcode_layout = QVBoxLayout(self.gcode_group)
        self.gcode_text = QTextEdit()
        self.gcode_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.gcode_text.setStyleSheet("font-family: Consolas, monospace; font-size: 10pt;")
        self.gcode_text.textChanged.connect(self._fit_gcode_panel_to_text)
        self.gcode_text.textChanged.connect(self._update_job_summary)
        self.gcode_text.textChanged.connect(self._update_assistant_panel)
        gcode_layout.addWidget(self.gcode_text)
        middle.addWidget(self.gcode_group)
        middle.setStretchFactor(0, 1)
        middle.setStretchFactor(1, 0)
        layout.addWidget(middle, 1)

        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(140)
        self.log_text.setStyleSheet("font-family: Consolas, monospace; font-size: 10pt;")
        log_layout.addWidget(self.log_text)
        layout.addWidget(log_group)

    def _build_status_bar(self, layout: QVBoxLayout) -> None:
        status = QFrame()
        status_layout = QGridLayout(status)
        status_layout.setContentsMargins(0, 4, 0, 0)
        self.job_status = QLabel("Bereit")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.status = QLabel("Simulator bereit.")
        status_layout.addWidget(self.job_status, 0, 0)
        status_layout.addWidget(self.progress, 0, 1)
        status_layout.addWidget(self.status, 1, 0, 1, 2)
        layout.addWidget(status)

    def _button(self, text: str, handler: Callable) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(handler)
        button.setMinimumHeight(28)
        return button

    def _spin(self, minimum: int, maximum: int, value: int, step: int = 1) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setValue(value)
        return spin

    def _double_spin(self, minimum: float, maximum: float, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(1)
        spin.setSingleStep(1.0)
        spin.setValue(value)
        return spin

    def _fit_gcode_panel_to_text(self) -> None:
        if not hasattr(self, "gcode_group"):
            return
        lines = self.gcode_text.toPlainText().splitlines() or [""]
        metrics = self.gcode_text.fontMetrics()
        longest_line_width = max(metrics.horizontalAdvance(line) for line in lines)
        scrollbar_width = self.gcode_text.verticalScrollBar().sizeHint().width()
        target_width = longest_line_width + scrollbar_width + 72
        target_width = max(360, min(620, target_width))
        self.gcode_group.setMinimumWidth(target_width)
        self.gcode_group.setMaximumWidth(target_width)

    def _settings_changed(self) -> None:
        self._refresh_gcode()
        self._draw_preview()

    def _profile_selected(self) -> None:
        self._ensure_profile_modes(self.profile_name.currentText())
        self._apply_mode_profile_to_controls()
        self._settings_changed()

    def _material_settings_changed(self) -> None:
        profile = self._selected_profile()
        self._upsert_profile(profile)
        self._settings_changed()

    def _switch_controller(self) -> None:
        try:
            self.controller.disconnect()
        except Exception as exc:  # noqa: BLE001 - UI logs controller errors
            self.log(str(exc))
        self._set_connection_indicator(False)
        if self.connection_mode.currentText() == "GRBL ueber USB":
            self.controller = GrblSerialController(self._threadsafe_log, lambda: self.serial_port.currentText(), self._threadsafe_progress)
        else:
            self.controller = SimulatedLaserController(self._threadsafe_log, self._threadsafe_progress)
        self.active_connection_mode = self.connection_mode.currentText()
        self.log(f"Modus gewechselt: {self.active_connection_mode}")

    def _current_controller(self):
        if self.active_connection_mode != self.connection_mode.currentText():
            self._switch_controller()
        return self.controller

    def _refresh_ports(self) -> None:
        ports = list_serial_ports()
        self.serial_port.clear()
        self.serial_port.addItems(ports)
        if ports:
            self.serial_port.setCurrentIndex(0)
        self.log(f"{len(ports)} COM-Port(s) gefunden." if ports else "Keine COM-Ports gefunden.")

    def _auto_detect_laser(self) -> None:
        self.log("Suche Laser an COM-Ports...")
        self._set_progress("Laser suchen", 0, 1)

        def detect() -> None:
            candidate = find_laser_port()
            if candidate is None:
                self.signals.error.emit("Kein passender Laser-Port gefunden.")
                return
            self.signals.log.emit(f"Laser-Port gefunden: {candidate.label} ({candidate.reason})")
            self.signals.port_detected.emit(candidate.label)
            self.signals.progress.emit("Bereit", 1, 1)

        self._run_worker(detect)

    def _apply_detected_port(self, port_label: str) -> None:
        self.connection_mode.setCurrentText("GRBL ueber USB")
        self._refresh_ports()
        index = self.serial_port.findText(port_label)
        if index < 0:
            self.serial_port.addItem(port_label)
            index = self.serial_port.findText(port_label)
        self.serial_port.setCurrentIndex(index)
        self.log(f"COM-Port automatisch ausgewaehlt: {port_label}")

    def _query_status(self) -> None:
        controller = self._current_controller()
        if hasattr(controller, "query_status"):
            self._run_worker(lambda: controller.query_status())
        else:
            self.log("Statusabfrage im Simulator nicht verfuegbar.")

    def _query_settings(self) -> None:
        controller = self._current_controller()
        if hasattr(controller, "query_settings"):
            self._run_worker(lambda: controller.query_settings())
        else:
            self.log("GRBL Settings nur im USB-Modus verfuegbar.")

    def _frame_job(self) -> None:
        controller = self._current_controller()
        width = self.work_width.value()
        height = self.work_height.value()

        def frame() -> None:
            try:
                controller.frame(width, height)
            except TypeError:
                controller.frame()

        self._run_worker(frame)

    def _start_job(self) -> None:
        controller = self._current_controller()
        width = self.work_width.value()
        height = self.work_height.value()
        profile = self._selected_profile()
        gcode = self.gcode_text.toPlainText().strip()
        try:
            prepared = self.job_service.prepare_job(gcode, width, height, profile, self.operation_mode.currentText())
        except ValueError as exc:
            self.log(str(exc))
            QMessageBox.critical(self, "G-Code ungueltig", str(exc))
            return

        controller_name = controller.__class__.__name__
        mode_label = self._operation_mode_label()
        mode_laser = "M3 konstant" if self.operation_mode.currentText() == CUT_MODE else "M4 dynamisch"
        self._show_job_analysis(prepared)
        self.last_prepared_job = prepared
        self._update_assistant_panel(prepared)

        if self.connection_mode.currentText() != "GRBL ueber USB":
            confirmed = QMessageBox.question(
                self,
                "Simulator-Modus",
                "Die App ist im Simulator-Modus.\n\n"
                "Der Job wird nicht an den Laser gesendet.\n"
                f"Auswahl: {mode_label}\n"
                f"Laser-Modus: {mode_laser}\n"
                f"Leistung: {profile.power_percent}%\n"
                f"Geschwindigkeit: {profile.speed_mm_min} mm/min\n"
                f"Durchgaenge: {profile.passes}\n"
                f"G-Code-Zeilen: {len(prepared.commands)}\n"
                f"Geschaetzte Laufzeit: {prepared.analysis.estimated_runtime_label}\n"
                "Soll die Simulation gestartet werden?",
            )
            if confirmed != QMessageBox.StandardButton.Yes:
                self.log("Simulation abgebrochen.")
                return
        else:
            if not self._hardware_preflight_ok(controller):
                return
            if prepared.warnings and not self._confirm_warnings(prepared.warnings):
                self.log("Jobstart wegen Preflight-Warnung abgebrochen.")
                return
            confirmed = QMessageBox.question(
                self,
                "Laserjob starten",
                "Laserjob wirklich starten?\n\n"
                "Modus: GRBL ueber USB\n"
                f"Operation: {mode_label}\n"
                f"Laser-Modus: {mode_laser}\n"
                f"Controller: {controller_name}\n"
                f"Port: {self.serial_port.currentText()}\n"
                f"Arbeitsbereich: {width:.0f} x {height:.0f} mm\n"
                f"Material: {profile.name}\n"
                f"Leistung: {profile.power_percent}%\n"
                f"Geschwindigkeit: {profile.speed_mm_min} mm/min\n"
                f"G-Code-Zeilen: {len(prepared.commands)}\n"
                f"Geschaetzte Laufzeit: {prepared.analysis.estimated_runtime_label}\n\n"
                "Schutzbrille tragen und Arbeitsbereich pruefen.",
            )
            if confirmed != QMessageBox.StandardButton.Yes:
                self.log("Jobstart abgebrochen.")
                return

        self.log(f"Start-Controller: {controller_name} ({mode_label})")

        def start() -> None:
            try:
                controller.start_job(gcode, width, height)
            except TypeError:
                controller.start_job(gcode)

        self._run_worker(start)

    def _dry_run_job(self) -> None:
        controller = self._current_controller()
        width = self.work_width.value()
        height = self.work_height.value()
        gcode = self.gcode_text.toPlainText().strip()
        try:
            dry_run_gcode = "\n".join(self.job_service.prepare_dry_run(gcode, width, height).commands)
        except ValueError as exc:
            self.log(str(exc))
            QMessageBox.critical(self, "Dry Run nicht moeglich", str(exc))
            return

        if self.connection_mode.currentText() == "GRBL ueber USB" and not self._hardware_preflight_ok(controller):
            return

        self.log(f"Dry Run Start-Controller: {controller.__class__.__name__} ({self._operation_mode_label()})")

        def start_dry_run() -> None:
            try:
                controller.start_job(dry_run_gcode, width, height)
            except TypeError:
                controller.start_job(dry_run_gcode)

        self._run_worker(start_dry_run)

    def _hardware_preflight_ok(self, controller) -> bool:
        warnings = self.job_service.hardware_preflight_warnings(controller, self.serial_port.currentText())
        if warnings:
            message = "\n".join(f"- {item}" for item in warnings)
            self.log(message)
            QMessageBox.critical(self, "Preflight fehlgeschlagen", message)
            return False
        return True

    def _confirm_warnings(self, warnings: list[str]) -> bool:
        warning_text = "\n".join(f"- {item}" for item in warnings)
        result = QMessageBox.question(
            self,
            "Preflight-Warnungen",
            "Bitte pruefe diese Punkte vor dem Start:\n\n"
            f"{warning_text}\n\n"
            "Nur fortsetzen, wenn Material, Fokus, Air Assist, Absaugung und Schutzbrille vorbereitet sind.",
        )
        return result == QMessageBox.StandardButton.Yes

    def _show_job_analysis(self, prepared: JobPreparation) -> None:
        analysis = prepared.analysis
        bounds = "keine Pfadgrenzen"
        if analysis.has_bounds:
            bounds = (
                f"X {analysis.min_x:.1f}..{analysis.max_x:.1f} mm, "
                f"Y {analysis.min_y:.1f}..{analysis.max_y:.1f} mm"
            )
        self.log(
            "Jobanalyse: "
            f"{len(prepared.commands)} Zeilen, "
            f"{analysis.movement_count} Bewegungen, "
            f"{analysis.laser_command_count} Laserbefehle, "
            f"{bounds}, "
            f"ca. {analysis.estimated_runtime_label}."
        )

    def _update_job_summary(self) -> None:
        if not hasattr(self, "job_summary"):
            return
        try:
            prepared = self.job_service.prepare_job(
                self.gcode_text.toPlainText(),
                self.work_width.value(),
                self.work_height.value(),
                self._selected_profile(),
                self.operation_mode.currentText(),
            )
        except ValueError as exc:
            self.job_summary.setText(f"G-Code: {exc}")
            return
        analysis = prepared.analysis
        warning_count = len(prepared.warnings)
        warning_text = f" | Warnungen: {warning_count}" if warning_count else ""
        bounds = ""
        if analysis.has_bounds:
            bounds = f" | Pfad: {analysis.width_mm:.1f} x {analysis.height_mm:.1f} mm"
        self.job_summary.setText(
            f"G-Code: {len(prepared.commands)} Zeilen | Bewegungen: {analysis.movement_count} "
            f"| Laufzeit ca. {analysis.estimated_runtime_label}{bounds}{warning_text}"
        )
        self.last_prepared_job = prepared

    def _update_assistant_panel(self, prepared: JobPreparation | None = None) -> None:
        if not hasattr(self, "assistant_summary"):
            return
        if prepared is None:
            try:
                prepared = self.job_service.prepare_job(
                    self.gcode_text.toPlainText(),
                    self.work_width.value(),
                    self.work_height.value(),
                    self._selected_profile(),
                    self.operation_mode.currentText(),
                )
            except ValueError as exc:
                self.assistant_summary.setPlainText(f"Assistenz: {exc}")
                return
        profile = self._selected_profile()
        advice = self.assistant_service.advise(
            profile.name,
            self.operation_mode.currentText(),
            profile,
            prepared.analysis,
            prepared.warnings,
            self.job_history,
        )
        lines = [f"Risiko: {advice.risk_label} ({advice.risk_score}/100)"]
        lines.extend(f"- {item}" for item in advice.recommendations)
        if advice.matching_successes:
            lines.append(f"Gespeicherte gute Treffer: {len(advice.matching_successes)}")
        self.assistant_summary.setPlainText("\n".join(lines))

    def _generate_test_matrix(self) -> None:
        profile = self._selected_profile()
        gcode = self.assistant_service.build_test_matrix_gcode(
            profile.name,
            self.operation_mode.currentText(),
            profile,
        )
        self.gcode_text.setPlainText(gcode)
        self.imported_paths = []
        self.original_imported_paths = []
        self._draw_preview()
        self.log("Testmatrix erzeugt. Bitte zuerst Dry Run und dann auf Restmaterial testen.")

    def _record_job_result(self, result: str) -> None:
        try:
            prepared = self.job_service.prepare_job(
                self.gcode_text.toPlainText(),
                self.work_width.value(),
                self.work_height.value(),
                self._selected_profile(),
                self.operation_mode.currentText(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Job-Historie", str(exc))
            return
        note, ok = QInputDialog.getText(self, "Job-Historie", "Notiz zum Ergebnis:")
        if not ok:
            return
        profile = self._selected_profile()
        entry = JobHistoryEntry(
            timestamp=now_timestamp(),
            material_name=profile.name,
            operation_mode=self.operation_mode.currentText(),
            power_percent=profile.power_percent,
            speed_mm_min=profile.speed_mm_min,
            passes=profile.passes,
            work_width_mm=self.work_width.value(),
            work_height_mm=self.work_height.value(),
            command_count=len(prepared.commands),
            movement_count=prepared.analysis.movement_count,
            estimated_runtime_seconds=prepared.analysis.estimated_runtime_seconds,
            warning_count=len(prepared.warnings),
            result=result,
            notes=note,
        )
        self.job_history = append_job_history(entry)
        self._update_assistant_panel(prepared)
        self.log(f"Job-Ergebnis gespeichert: {result}")

    def _refresh_gcode(self) -> None:
        if not hasattr(self, "gcode_text"):
            return
        profile = self._selected_profile()
        operation_mode = self.operation_mode.currentText()
        if self.imported_paths:
            code = build_polyline_gcode(self.imported_paths, profile, operation_mode)
        else:
            code = build_rectangle_frame_gcode(self.work_width.value(), self.work_height.value(), profile, operation_mode)
        if self.gcode_text.toPlainText() != code:
            self.gcode_text.setPlainText(code)
        self._update_job_summary()

    def _operation_mode_label(self) -> str:
        return "Cutten (M3 konstant)" if self.operation_mode.currentText() == CUT_MODE else "Gravieren (M4 dynamisch)"

    def _on_operation_mode_changed(self) -> None:
        self._apply_mode_profile_to_controls()
        self._settings_changed()

    def _ensure_profile_modes(self, profile_name: str) -> None:
        self.profile_service.ensure_profile_modes(profile_name)

    def _apply_mode_profile_to_controls(self) -> None:
        selected_name = self.profile_name.currentText()
        if not selected_name:
            return
        self._ensure_profile_modes(selected_name)
        mode_profile = self.profile_service.profile_for(selected_name, self.operation_mode.currentText())
        self.power_percent.blockSignals(True)
        self.speed_mm_min.blockSignals(True)
        self.passes.blockSignals(True)
        self.power_percent.setValue(mode_profile.power_percent)
        self.speed_mm_min.setValue(mode_profile.speed_mm_min)
        self.passes.setValue(mode_profile.passes)
        self.power_percent.blockSignals(False)
        self.speed_mm_min.blockSignals(False)
        self.passes.blockSignals(False)

    def _import_svg(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "SVG importieren", "", "SVG Dateien (*.svg);;Alle Dateien (*.*)")
        if not path:
            return
        try:
            result = import_svg(path)
        except Exception as exc:  # noqa: BLE001 - show file import errors to user
            QMessageBox.critical(self, "SVG Import", str(exc))
            return
        self.original_imported_paths = result.paths
        self.imported_file = path
        self.svg_manual_width.setValue(min(result.width_mm, self.work_width.value()))
        self._apply_svg_placement()
        self.log(f"SVG importiert: {path}")

    def _save_project(self) -> None:
        path = self.current_project_path
        if path is None:
            path, _filter = QFileDialog.getSaveFileName(self, "Projekt speichern", "", "Laser Projekt (*.laser.json)")
        if not path:
            return
        if not path.endswith(".laser.json"):
            path += ".laser.json"
        data = project_to_dict(
            self.work_width.value(),
            self.work_height.value(),
            self._selected_profile(),
            self.gcode_text.toPlainText(),
            self.imported_paths,
            self.imported_file,
            self.material_measurement,
            self._svg_placement_data(),
            self.operation_mode.currentText(),
        )
        save_project(path, data)
        self.current_project_path = path
        self.log(f"Projekt gespeichert: {path}")

    def _load_project(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Projekt laden", "", "Laser Projekt (*.laser.json);;Alle Dateien (*.*)")
        if not path:
            return
        try:
            data = load_project(path)
        except Exception as exc:  # noqa: BLE001 - show project load errors to user
            QMessageBox.critical(self, "Projekt laden", str(exc))
            return
        self.work_width.setValue(float(data["work_area"]["width_mm"]))
        self.work_height.setValue(float(data["work_area"]["height_mm"]))
        profile_data = data["material_profile"]
        profile = MaterialProfile(
            profile_data["name"],
            int(profile_data["power_percent"]),
            int(profile_data["speed_mm_min"]),
            int(profile_data["passes"]),
        )
        self._upsert_profile(profile)
        self.profile_name.setCurrentText(profile.name)
        self.power_percent.setValue(profile.power_percent)
        self.speed_mm_min.setValue(profile.speed_mm_min)
        self.passes.setValue(profile.passes)
        self.current_project_path = path
        self.imported_paths = data.get("imported_paths", [])
        self.original_imported_paths = self.imported_paths
        self.imported_file = data.get("imported_file")
        self.material_measurement = data.get("material_measurement")
        placement = data.get("svg_placement") or {}
        if data.get("operation_mode"):
            self.operation_mode.setCurrentText(data["operation_mode"])
        self.svg_auto.setChecked(placement.get("mode", "Automatisch") == "Automatisch")
        self.svg_manual_width.setValue(float(placement.get("manual_width", self.svg_manual_width.value())))
        self.svg_offset_x.setValue(float(placement.get("offset_x", 0)))
        self.svg_offset_y.setValue(float(placement.get("offset_y", 0)))
        self.svg_margin.setValue(float(placement.get("margin", 5)))
        self.gcode_text.setPlainText(data.get("gcode", ""))
        self._update_material_measurement_label()
        self._draw_preview()
        self.log(f"Projekt geladen: {path}")

    def _draw_preview(self) -> None:
        if hasattr(self, "preview"):
            self.preview.set_preview(self.work_width.value(), self.work_height.value(), self.imported_paths)

    def _selected_profile(self) -> MaterialProfile:
        return MaterialProfile(
            self.profile_name.currentText() or DEFAULT_PROFILES[0].name,
            self.power_percent.value() if hasattr(self, "power_percent") else DEFAULT_PROFILES[0].power_percent,
            self.speed_mm_min.value() if hasattr(self, "speed_mm_min") else DEFAULT_PROFILES[0].speed_mm_min,
            self.passes.value() if hasattr(self, "passes") else DEFAULT_PROFILES[0].passes,
        )

    def _upsert_profile(self, profile: MaterialProfile) -> None:
        self.profile_service.upsert_mode_profile(profile, self.operation_mode.currentText())
        self.profile_name.blockSignals(True)
        current = self.profile_name.currentText()
        self.profile_name.clear()
        self.profile_name.addItems(self.profile_service.names())
        self.profile_name.setCurrentText(current or profile.name)
        self.profile_name.blockSignals(False)

    def _capture_material_point(self, point_index: int) -> None:
        controller = self._current_controller()
        try:
            x, y = controller.current_position()
        except Exception as exc:  # noqa: BLE001 - user-facing hardware state
            self.log(str(exc))
            QMessageBox.critical(self, "Material einmessen", str(exc))
            return
        if point_index == 1:
            self.material_point_a = (x, y)
        else:
            self.material_point_b = (x, y)
        self._update_material_measurement_label()

    def _apply_material_measurement(self) -> None:
        if not self.material_point_a or not self.material_point_b:
            QMessageBox.warning(self, "Material einmessen", "Bitte zuerst beide Ecken setzen.")
            return
        ax, ay = self.material_point_a
        bx, by = self.material_point_b
        width = abs(bx - ax)
        height = abs(by - ay)
        self.work_width.setValue(width)
        self.work_height.setValue(height)
        self.material_db_width.setValue(width)
        self.material_db_height.setValue(height)
        self.material_measurement = {"point_a": self.material_point_a, "point_b": self.material_point_b}
        self._update_material_measurement_label()
        self._settings_changed()

    def _update_material_measurement_label(self) -> None:
        if not self.material_point_a and not self.material_point_b:
            self.material_measurement_label.setText("Nicht eingemessen")
            return
        self.material_measurement_label.setText(f"Ecke 1: {self.material_point_a or '-'}\nEcke 2: {self.material_point_b or '-'}")

    def _save_measured_material(self) -> None:
        name = self.material_db_name.currentText().strip()
        if not name:
            QMessageBox.warning(self, "Material speichern", "Bitte einen Materialnamen eingeben.")
            return
        record = {
            "name": name,
            "width_mm": self.material_db_width.value() or self.work_width.value(),
            "height_mm": self.material_db_height.value() or self.work_height.value(),
            "point_a": self.material_point_a,
            "point_b": self.material_point_b,
        }
        self.material_db_records = upsert_material(record)
        self._refresh_material_db_combo()
        self.log(f"Material gespeichert: {name}")

    def _select_material_record(self) -> None:
        record = find_material(self.material_db_selection.currentText())
        if record:
            self.material_db_name.setCurrentText(record.get("name", ""))
            self.material_db_width.setValue(float(record.get("width_mm", 0)))
            self.material_db_height.setValue(float(record.get("height_mm", 0)))

    def _load_measured_material(self) -> None:
        record = find_material(self.material_db_selection.currentText())
        if not record:
            return
        self.work_width.setValue(float(record.get("width_mm", self.work_width.value())))
        self.work_height.setValue(float(record.get("height_mm", self.work_height.value())))
        self.material_point_a = tuple(record["point_a"]) if record.get("point_a") else None
        self.material_point_b = tuple(record["point_b"]) if record.get("point_b") else None
        self.material_measurement = {"point_a": self.material_point_a, "point_b": self.material_point_b}
        self._update_material_measurement_label()
        self._settings_changed()
        self.log(f"Material geladen: {record.get('name', '')}")

    def _refresh_material_db_combo(self) -> None:
        names = [item.get("name", "") for item in self.material_db_records]
        self.material_db_selection.blockSignals(True)
        self.material_db_selection.clear()
        self.material_db_selection.addItems(names)
        self.material_db_selection.blockSignals(False)
        self.material_db_name.clear()
        self.material_db_name.addItems(names)

    def _delete_measured_material(self) -> None:
        name = self.material_db_selection.currentText()
        if not name:
            return
        self.material_db_records = delete_material(name)
        self._refresh_material_db_combo()
        self.log(f"Material geloescht: {name}")

    def _apply_svg_placement(self) -> None:
        if not self.original_imported_paths:
            return
        try:
            if self.svg_auto.isChecked():
                self.imported_paths, fitted_width, _fitted_height = fit_paths_to_area(
                    self.original_imported_paths,
                    self.work_width.value(),
                    self.work_height.value(),
                    self.svg_margin.value(),
                )
                self.svg_manual_width.blockSignals(True)
                self.svg_manual_width.setValue(fitted_width)
                self.svg_manual_width.blockSignals(False)
            else:
                self.imported_paths, _fitted_width, _fitted_height = scale_paths_to_width(
                    self.original_imported_paths,
                    self.svg_manual_width.value(),
                    self.svg_offset_x.value(),
                    self.svg_offset_y.value(),
                )
        except ValueError as exc:
            self.log(str(exc))
            return
        self._refresh_gcode()
        self._draw_preview()

    def _svg_placement_data(self) -> dict:
        return {
            "mode": "Automatisch" if self.svg_auto.isChecked() else "Manuell",
            "margin": self.svg_margin.value(),
            "manual_width": self.svg_manual_width.value(),
            "offset_x": self.svg_offset_x.value(),
            "offset_y": self.svg_offset_y.value(),
        }

    def _run_controller_action(self, action, allow_while_busy: bool = False) -> None:
        controller = self._current_controller()
        self._run_worker(lambda: action(controller), allow_while_busy=allow_while_busy)

    def _run_worker(self, action, allow_while_busy: bool = False) -> None:
        if self.worker_busy and not allow_while_busy:
            self.log("Bitte warten, bis die aktuelle Aktion abgeschlossen ist.")
            return
        self.worker_busy = True
        self._set_progress("Laeuft", 0, 1)

        def target() -> None:
            try:
                action()
            except Exception as exc:  # noqa: BLE001 - report worker failures to UI
                self.signals.error.emit(str(exc))
            finally:
                self.signals.finished.emit()

        thread = threading.Thread(target=target, daemon=True)
        thread.start()

    def _threadsafe_log(self, message: str) -> None:
        self.signals.log.emit(message)

    def _threadsafe_progress(self, label: str, current: int, total: int) -> None:
        self.signals.progress.emit(label, current, total)

    def _show_worker_error(self, message: str) -> None:
        self.log(message)
        QMessageBox.critical(self, "Fehler", message)

    def _worker_finished(self) -> None:
        self.worker_busy = False
        self._sync_connection_indicator()

    def _sync_connection_indicator(self) -> None:
        state = getattr(self.controller, "state", None)
        self._set_connection_indicator(bool(state and state.connected))

    def _set_connection_indicator(self, connected: bool) -> None:
        self.connection_label.setText("Verbunden" if connected else "Nicht verbunden")
        color = "#188038" if connected else "#d93025"
        self.connection_label.setStyleSheet(f"color: {color}; font-weight: 600;")

    def _set_progress(self, label: str, current: int, total: int) -> None:
        total = max(1, total)
        percent = int(current / total * 100)
        self.job_status.setText(label)
        self.progress.setValue(percent)

    def log(self, message: str) -> None:
        self.status.setText(message)
        self.log_text.append(message)

    def _export_profiles(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(self, "Profile exportieren", "", "JSON (*.json)")
        if not path:
            return
        if not path.endswith(".json"):
            path += ".json"
        self.profile_service.export_profiles(path)
        self.log(f"Profile exportiert: {path}")

    def _import_profiles(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Profile importieren", "", "JSON (*.json);;Alle Dateien (*.*)")
        if not path:
            return
        try:
            self.profile_service.import_profiles(path)
        except Exception as exc:  # noqa: BLE001 - user-facing import error
            QMessageBox.critical(self, "Profile importieren", str(exc))
            return
        self.profile_name.clear()
        self.profile_name.addItems(self.profile_service.names())
        self._apply_mode_profile_to_controls()
        self._settings_changed()
        self.log(f"Profile importiert: {path}")

    def _export_history(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(self, "Historie exportieren", "", "JSON (*.json)")
        if not path:
            return
        if not path.endswith(".json"):
            path += ".json"
        export_job_history(path)
        self.log(f"Historie exportiert: {path}")

    def _import_history(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Historie importieren", "", "JSON (*.json);;Alle Dateien (*.*)")
        if not path:
            return
        try:
            self.job_history = import_job_history(path)
        except Exception as exc:  # noqa: BLE001 - user-facing import error
            QMessageBox.critical(self, "Historie importieren", str(exc))
            return
        self._update_assistant_panel()
        self.log(f"Historie importiert: {path}")


def run_app() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = LaserControlWindow()
    window.show()
    return app.exec()
