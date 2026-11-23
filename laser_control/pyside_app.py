"""Hauptfenster der Laser-Control-Oberflaeche (Aufbau, Layout, Vorschau).

Fachlogik liegt in den window_*-Mixins."""

import sys
import threading
from collections.abc import Callable
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from laser_control.application_controller import ApplicationController
from laser_control.artwork_import import ArtworkImportService, RasterImageSource
from laser_control.artwork_scaling import AutoFitResult, AutoFitService
from laser_control.artwork_transform import ArtworkTransform
from laser_control.console_log_panel import ConsoleLogPanel
from laser_control.diagnostic_log import DiagnosticLog
from laser_control.gcode import CUT_MODE, ENGRAVE_MODE
from laser_control.fill_toolpath import FillToolpath
from laser_control.job_history import load_job_history
from laser_control.laser_intelligence_engine import LaserIntelligenceEngine, LaserIntelligenceResult
from laser_control.machine_actions import MachineActionRegistry
from laser_control.machine_log import MachineActionLog
from laser_control.machine_panel import MachinePanel
from laser_control.machine_profiles import MachineProfileRepository
from laser_control.material_db import load_materials
from laser_control.profiles import DEFAULT_PROFILES
from laser_control.preview_model import (
    JobPreviewModel,
    PreviewHeadPosition,
    PreviewOptions,
    build_multi_item_preview_model,
    build_preview_model,
)
from laser_control.qt_panels import LayerPanel, WorkspaceScanPanel
from laser_control.project import LaserProject
from laser_control.services.assistant_service import AssistantService
from laser_control.services.job_service import JobService
from laser_control.services.profile_service import ProfileService
from laser_control.status_panel import StatusPanel
from laser_control.svg_optimization import SvgOptimizationResult, SvgVectorAnalysis
from laser_control.workflow_controller import WorkflowController
from laser_control.window_machine import MachineControlMixin
from laser_control.window_job import JobMixin
from laser_control.window_materials import MaterialMixin
from laser_control.window_artwork import ArtworkMixin
from laser_control.window_project import ProjectMixin
from laser_control.window_status import StatusSummaryMixin
from laser_control.window_theme import ThemeMixin
from laser_control.ui_common import WorkerSignals
from laser_control.work_area_preview import WorkAreaPreview
from laser_control.ui_common import AUTO_FIT_MARGIN_MM, JOB_ORIGIN_CENTER, JOB_ORIGIN_LOWER_LEFT, MATERIAL_SHAPE_CIRCLE, MATERIAL_SHAPE_RECTANGLE, WorkerSignals


class LaserControlWindow(
    MachineControlMixin,
    JobMixin,
    MaterialMixin,
    ArtworkMixin,
    ProjectMixin,
    StatusSummaryMixin,
    ThemeMixin,
    QMainWindow,
):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Laser Control")
        self.resize(1120, 720)
        self.setMinimumSize(980, 620)

        self.imported_paths = []
        self.original_imported_paths = []
        self.imported_file = None
        self.artwork_source = None
        self.artwork_transform: ArtworkTransform | None = None
        self.laser_project = LaserProject(300.0, 200.0)
        self.selected_artwork_item_id: str | None = None
        self._object_list_updating = False
        self._item_sources: dict[str, object] = {}
        self._item_vector_paths: dict[str, list] = {}
        self._item_optimized_vector_paths: dict[str, list] = {}
        self._item_svg_analyses: dict[str, SvgVectorAnalysis] = {}
        self._item_svg_optimization_results: dict[str, SvgOptimizationResult] = {}
        self._item_original_rasters: dict[str, RasterImageSource] = {}
        self._fill_toolpaths_by_item: dict[str, list[FillToolpath]] = {}
        self.svg_optimized_paths: list = []
        self.svg_analysis: SvgVectorAnalysis | None = None
        self.svg_optimization_result: SvgOptimizationResult | None = None
        self.laser_intelligence_engine = LaserIntelligenceEngine()
        self.laser_intelligence_result: LaserIntelligenceResult | None = None
        self._item_intelligence_results: dict[str, LaserIntelligenceResult] = {}
        self.raster_sources: list[RasterImageSource] = []
        self.original_raster_source: RasterImageSource | None = None
        self.autofit_result: AutoFitResult | None = None
        self.fill_toolpaths: list[FillToolpath] = []
        self.material_point_a = None
        self.material_point_b = None
        self.material_points = {1: None, 2: None, 3: None, 4: None}
        self.material_measurement = None
        self.current_project_path = None
        self.material_db_records = load_materials()
        self.profile_service = ProfileService()
        self.job_service = JobService()
        self.import_service = ArtworkImportService()
        self.autofit_service = AutoFitService()
        self.assistant_service = AssistantService()
        self.diagnostic_log = DiagnosticLog()
        self.machine_action_registry = MachineActionRegistry()
        self.action_buttons: dict[str, list[QPushButton]] = {}
        self.app_controller = ApplicationController(
            self._threadsafe_log,
            self._threadsafe_progress,
            lambda: self.serial_port.currentText() if hasattr(self, "serial_port") else "",
            self.diagnostic_log,
        )
        self.machine_action_log = MachineActionLog()
        self.workflow = WorkflowController(self.job_service, self.machine_action_log, self.log)
        self.machine_profile_repository = MachineProfileRepository()
        self.machine_profile = self.machine_profile_repository.active_profile()
        self.job_history = load_job_history()
        self.material_profiles = self.profile_service.material_profiles
        self.last_prepared_job = None
        self.dark_mode_enabled = True
        self.worker_busy = False
        self._parameter_source = "Materialprofil/Default"
        self._closing = False
        self._transform_ui_updating = False
        self._worker_threads: list[threading.Thread] = []

        self.signals = WorkerSignals()
        self.signals.log.connect(self.log)
        self.signals.progress.connect(self._set_progress)
        self.signals.error.connect(self._show_worker_error)
        self.signals.finished.connect(self._worker_finished)
        self.signals.port_detected.connect(self._apply_detected_port)
        self._machine_state_timer = QTimer(self)
        self._machine_state_timer.setInterval(250)
        self._machine_state_timer.timeout.connect(self._sync_position_indicator)
        self._machine_state_timer.start()

        self.controller = self.app_controller.controller
        self.active_connection_mode = "Simulator"

        self._build_layout()
        self.log(f"Materialprofile Speicherpfad: {self.profile_service.storage_path}")
        self.log(f"Materialprofile geladen: {len(self.profile_service.names())}")
        if self.machine_profile_repository.load_error:
            self.log(f"Maschinenprofile konnten nicht geladen werden, Default wird genutzt: {self.machine_profile_repository.load_error}")
        self._apply_machine_profile(self.machine_profile)
        self.log(f"Maschinenprofil geladen: {self.machine_profile.name}")
        self._refresh_material_db_combo()
        self._apply_mode_profile_to_controls()
        self._sync_layers_from_controls(preserve_states=False)
        self._refresh_ports()
        self._refresh_gcode()
        self._draw_preview()
        self._sync_connection_indicator()
        self.diagnostic_log.event("App gestartet.")
        self.diagnostic_log.event(f"Diagnose-Log: {self.diagnostic_log.path}")
        self.log(f"Diagnose-Log aktiv: {self.diagnostic_log.path}")

    def _build_layout(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 8)
        self.setCentralWidget(root)

        self._build_action_bar(root_layout)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        root_layout.addWidget(self.main_splitter, 1)

        self.left_sidebar = QWidget()
        self.left_sidebar.setObjectName("leftSidebar")
        self.left_sidebar.setMinimumWidth(300)
        self.left_sidebar.setMaximumWidth(340)
        left_layout = QVBoxLayout(self.left_sidebar)
        left_layout.setContentsMargins(0, 0, 6, 0)
        left_layout.setSpacing(0)
        self.sidebar_toolbox = QWidget()
        self.sidebar_toolbox.setObjectName("sidebarSections")
        self.sidebar_scroll = QScrollArea()
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar_scroll.setWidget(self.sidebar_toolbox)
        left_layout.addWidget(self.sidebar_scroll)
        self.main_splitter.addWidget(self.left_sidebar)
        self.sidebar_combos = []

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        self.main_splitter.addWidget(content)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 5)
        self.main_splitter.setSizes([320, 1380])

        self._build_sidebar(self.sidebar_toolbox)
        self._build_content(content_layout)
        self._build_status_bar(root_layout)

    def _build_action_bar(self, layout: QVBoxLayout) -> None:
        action_bar = QFrame()
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(0, 0, 0, 4)
        action_layout.setSpacing(8)
        self.workflow_hint = QLabel(
            "Maschine  >  Projekt & Material  >  Layer  >  Vorschau / Frame  >  Preflight / Start"
        )
        self.workflow_hint.setObjectName("workflowHint")
        self.workflow_hint.setWordWrap(True)
        self.workflow_hint.setMaximumHeight(42)
        action_layout.addWidget(self.workflow_hint, 1)
        action_layout.addStretch(1)
        self.theme_switch = QCheckBox("Dark")
        self.theme_switch.setChecked(True)
        self.theme_switch.toggled.connect(self._apply_theme)
        action_layout.addWidget(self.theme_switch)
        layout.addWidget(action_bar)

    def _add_sidebar_section(self, container_layout: QVBoxLayout, title: str, body: QWidget, expanded: bool) -> QGroupBox:
        section = QGroupBox(title)
        section.setObjectName("sidebarSection")
        section.setCheckable(True)
        section.setChecked(expanded)
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(8, 10, 8, 8)
        section_layout.setSpacing(6)
        section_layout.addWidget(body)
        body.setVisible(expanded)
        section.toggled.connect(body.setVisible)
        container_layout.addWidget(section)
        self.sidebar_sections[title] = section
        return section

    def _build_sidebar(self, toolbox: QWidget) -> None:
        sidebar_layout = QVBoxLayout(toolbox)
        sidebar_layout.setContentsMargins(6, 6, 6, 10)
        sidebar_layout.setSpacing(8)
        self.sidebar_sections: dict[str, QGroupBox] = {}

        machine_page = QWidget()
        machine_layout = QVBoxLayout(machine_page)
        machine_layout.setContentsMargins(0, 0, 0, 0)
        machine_layout.setSpacing(4)

        self.machine_panel = MachinePanel(self.machine_action_registry)
        self.connection_label = self.machine_panel.connection_label
        self.connection_mode = self.machine_panel.connection_mode
        self.serial_port = self.machine_panel.serial_port
        self._configure_sidebar_combo(self.connection_mode)
        self._configure_sidebar_combo(self.serial_port)
        self.machine_panel.mode_changed.connect(self._switch_controller)
        self.machine_panel.action_triggered.connect(self._trigger_machine_action)
        self.machine_panel.profile_changed.connect(self._machine_profile_changed)
        self.machine_panel.profile_editor_requested.connect(self._edit_machine_profiles)
        self.machine_panel.set_machine_profiles(
            self.machine_profile_repository.profiles(),
            self.machine_profile_repository.active_profile_id(),
        )
        for action_id, buttons in self.machine_panel.action_buttons.items():
            self.action_buttons.setdefault(action_id, []).extend(buttons)
        machine_layout.addWidget(self.machine_panel)
        self._add_sidebar_section(sidebar_layout, "Maschine", machine_page, True)

        position_page = QWidget()
        position_page_layout = QVBoxLayout(position_page)
        position_page_layout.setContentsMargins(0, 0, 0, 0)
        position_page_layout.setSpacing(6)
        jog_group = QGroupBox("Position / Jog")
        jog = QGridLayout(jog_group)
        jog.setContentsMargins(8, 8, 8, 8)
        jog.setHorizontalSpacing(8)
        jog.setVerticalSpacing(8)
        for column in range(3):
            jog.setColumnStretch(column, 1)
        jog.addWidget(self._machine_action_button("jog_y_plus", "Sidebar"), 0, 1)
        jog.addWidget(self._machine_action_button("jog_x_minus", "Sidebar"), 1, 0)
        jog.addWidget(self._machine_action_button("jog_x_plus", "Sidebar"), 1, 2)
        jog.addWidget(self._machine_action_button("jog_y_minus", "Sidebar"), 2, 1)
        position_page_layout.addWidget(jog_group)
        alignment_group = QGroupBox("Material ausrichten")
        alignment_layout = QVBoxLayout(alignment_group)
        alignment_layout.setContentsMargins(8, 8, 8, 8)
        alignment_layout.setSpacing(6)
        self.alignment_power = self._spin(1, 5, 1, suffix=" %")
        self.alignment_power.setToolTip("Sichere Pointer-Leistung, maximal 5%. Niemals Materialprofil-Power.")
        self.alignment_power.valueChanged.connect(self._alignment_power_changed)
        self.alignment_status = QLabel("Ausrichtmodus aus")
        self.alignment_status.setWordWrap(True)
        alignment_layout.addWidget(QLabel("Pointer-Leistung"))
        alignment_layout.addWidget(self.alignment_power)
        alignment_layout.addWidget(self._machine_action_button("toggle_alignment", "Sidebar"))
        alignment_layout.addWidget(self.alignment_status)
        self.workspace_scan_panel = WorkspaceScanPanel(
            self._machine_action_button("toggle_work_area_trace", "Sidebar"),
            self._button("Pointer 2s testen", self._test_alignment_pointer),
        )
        self.work_area_trace_status = self.workspace_scan_panel.status_label
        alignment_layout.addWidget(self.workspace_scan_panel)
        position_page_layout.addWidget(alignment_group)
        self._add_sidebar_section(sidebar_layout, "Positionierung", position_page, False)

        project_page = QWidget()
        project_page_layout = QVBoxLayout(project_page)
        project_page_layout.setContentsMargins(0, 0, 0, 0)
        project_page_layout.setSpacing(6)

        project = QGroupBox("Projekt")
        project_layout = QVBoxLayout(project)
        project_layout.setContentsMargins(8, 8, 8, 8)
        project_layout.setSpacing(6)
        project_layout.addWidget(self._button("Datei importieren", self._import_svg))
        self.object_table = QTableWidget(0, 4)
        self.object_table.setHorizontalHeaderLabels(["S", "A", "Name", "Typ"])
        self.object_table.verticalHeader().setVisible(False)
        self.object_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.object_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.object_table.setMinimumHeight(120)
        self.object_table.setMaximumHeight(180)
        self.object_table.setColumnWidth(0, 28)
        self.object_table.setColumnWidth(1, 28)
        self.object_table.setColumnWidth(3, 64)
        self.object_table.horizontalHeader().setStretchLastSection(False)
        self.object_table.horizontalHeader().setMinimumSectionSize(26)
        self.object_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.object_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.object_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.object_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.object_table.itemChanged.connect(self._object_table_item_changed)
        self.object_table.itemSelectionChanged.connect(self._object_table_selection_changed)
        project_layout.addWidget(self.object_table)
        self.project_empty_state = QLabel("Noch keine Motive vorhanden.\nJetzt erstes Motiv importieren.")
        self.project_empty_state.setObjectName("projectEmptyState")
        self.project_empty_state.setWordWrap(True)
        project_layout.addWidget(self.project_empty_state)
        project_layout.addWidget(self._button("Speichern", self._save_project))
        project_layout.addWidget(self._button("Laden", self._load_project))
        project_page_layout.addWidget(project)

        material = QGroupBox("Material")
        material_layout = QVBoxLayout(material)
        material_layout.setContentsMargins(8, 8, 8, 8)
        material_layout.setSpacing(6)
        self.material_measurement_label = QLabel("Nicht eingemessen")
        self.material_measurement_label.setWordWrap(True)
        material_layout.addWidget(self.material_measurement_label)
        material_layout.addWidget(self._button("Ecke 1 setzen", lambda: self._capture_material_point(1)))
        material_layout.addWidget(self._button("Ecke 2 setzen", lambda: self._capture_material_point(2)))
        material_layout.addWidget(self._button("Ecke 3 setzen", lambda: self._capture_material_point(3)))
        material_layout.addWidget(self._button("Ecke 4 setzen", lambda: self._capture_material_point(4)))
        material_layout.addWidget(self._button("Groesse uebernehmen", self._apply_material_measurement))
        self.material_db_name = QComboBox()
        self.material_db_name.setEditable(True)
        self._configure_sidebar_combo(self.material_db_name)
        material_layout.addWidget(QLabel("Name"))
        material_layout.addWidget(self.material_db_name)
        size_grid = QGridLayout()
        size_grid.setHorizontalSpacing(8)
        size_grid.setVerticalSpacing(4)
        self.material_db_width = self._double_spin(0, 2000, 0, " mm")
        self.material_db_height = self._double_spin(0, 2000, 0, " mm")
        size_grid.addWidget(QLabel("Breite"), 0, 0)
        size_grid.addWidget(self.material_db_width, 0, 1)
        size_grid.addWidget(QLabel("Hoehe"), 1, 0)
        size_grid.addWidget(self.material_db_height, 1, 1)
        size_grid.setColumnStretch(1, 1)
        material_layout.addLayout(size_grid)
        material_layout.addWidget(self._button("Material speichern", self._save_measured_material))
        self.material_db_selection = QComboBox()
        self._configure_sidebar_combo(self.material_db_selection)
        self.material_db_selection.currentTextChanged.connect(lambda _text: self._select_material_record())
        material_layout.addWidget(self.material_db_selection)
        material_layout.addWidget(self._button("Material laden", self._load_measured_material))
        material_layout.addWidget(self._button("Material loeschen", self._delete_measured_material))
        project_page_layout.addWidget(material)
        self._add_sidebar_section(sidebar_layout, "Projekt", project_page, False)

        job_page = QWidget()
        job_page_layout = QVBoxLayout(job_page)
        job_page_layout.setContentsMargins(0, 0, 0, 0)
        job_page_layout.setSpacing(4)
        job = QGroupBox("Job")
        job_layout = QVBoxLayout(job)
        job_layout.setContentsMargins(8, 8, 8, 8)
        job_layout.setSpacing(7)
        self.operation_mode = QComboBox()
        self.operation_mode.addItems([ENGRAVE_MODE, CUT_MODE])
        self._configure_sidebar_combo(self.operation_mode)
        self.operation_mode.currentTextChanged.connect(self._on_operation_mode_changed)
        job_layout.addWidget(QLabel("Modus"))
        job_layout.addWidget(self.operation_mode)
        job_layout.addWidget(QLabel("Job-Art"))
        self.job_kind = QComboBox()
        self.job_kind.addItems(["Einzelstueck"])
        self._configure_sidebar_combo(self.job_kind)
        job_layout.addWidget(self.job_kind)
        self.auto_home_after_job = QCheckBox("Auto-Home nach Einzelstueck")
        self.auto_home_after_job.setToolTip("Nach erfolgreichem Einzelstueck automatisch Home anfahren.")
        self.auto_home_after_job.setChecked(True)
        self.auto_home_after_job.toggled.connect(lambda _checked: self._settings_changed())
        job_layout.addWidget(self.auto_home_after_job)
        job_layout.addWidget(self._machine_action_button("frame", "Sidebar"))
        job_layout.addWidget(self._machine_action_button("dry_run", "Sidebar"))
        job_layout.addWidget(self._machine_action_button("start_job", "Sidebar"))
        pause_row = QHBoxLayout()
        pause_row.setSpacing(8)
        pause_row.addWidget(self._machine_action_button("pause", "Sidebar"))
        pause_row.addWidget(self._machine_action_button("resume", "Sidebar"))
        job_layout.addLayout(pause_row)
        job_layout.addWidget(self._machine_action_button("stop", "Sidebar"))
        job_layout.addWidget(self._machine_action_button("emergency_stop", "Sidebar"))
        job_layout.addWidget(self._machine_action_button("unlock_alarm", "Sidebar"))
        job_page_layout.addWidget(job)
        self._add_sidebar_section(sidebar_layout, "Job", job_page, True)

        diagnostics_page = QWidget()
        diagnostics_layout = QVBoxLayout(diagnostics_page)
        diagnostics_layout.setContentsMargins(0, 0, 0, 0)
        diagnostics_layout.setSpacing(6)
        machine_diagnostics = QGroupBox("Maschinendiagnose")
        machine_diagnostics_layout = QVBoxLayout(machine_diagnostics)
        machine_diagnostics_layout.setContentsMargins(8, 8, 8, 8)
        machine_diagnostics_layout.setSpacing(6)
        machine_diagnostics_layout.addWidget(self._machine_action_button("status", "Diagnose"))
        machine_diagnostics_layout.addWidget(self._machine_action_button("settings", "Diagnose"))
        machine_diagnostics_layout.addWidget(self._button("Diagnose exportieren", self._export_diagnostics))
        diagnostics_layout.addWidget(machine_diagnostics)

        svg_quality = QGroupBox("SVG-Optimierung")
        svg_quality_layout = QVBoxLayout(svg_quality)
        svg_quality_layout.setContentsMargins(8, 8, 8, 8)
        svg_quality_layout.setSpacing(6)
        self.svg_simplify_enabled = QCheckBox("Konturen vereinfachen")
        self.svg_simplify_enabled.setToolTip("Douglas-Peucker-Vereinfachung auf SVG-Pfadpunkte anwenden. Originaldatei bleibt unveraendert.")
        self.svg_simplify_enabled.toggled.connect(lambda _checked: self._svg_optimization_changed())
        self.svg_tolerance = QComboBox()
        for tolerance in (0.01, 0.02, 0.05, 0.10):
            self.svg_tolerance.addItem(f"{tolerance:.2f} mm", tolerance)
        self.svg_tolerance.setCurrentIndex(1)
        self.svg_tolerance.setToolTip("Empfehlung fuer feine Falcon-10W-Motive: 0.02 mm oder 0.05 mm.")
        self.svg_tolerance.currentIndexChanged.connect(lambda _index: self._svg_optimization_changed())
        self._configure_sidebar_combo(self.svg_tolerance)
        self.svg_remove_duplicates = QCheckBox("Doppelte Linien entfernen")
        self.svg_remove_duplicates.setToolTip("Nahezu identische Liniensegmente optional nur einmal gravieren.")
        self.svg_remove_duplicates.toggled.connect(lambda _checked: self._svg_optimization_changed())
        self.svg_show_analysis = QCheckBox("Analyse anzeigen")
        self.svg_show_analysis.setChecked(True)
        self.svg_show_analysis.toggled.connect(lambda _checked: self._update_import_summary())
        self.svg_analysis_label = QLabel("Keine SVG-Analyse")
        self.svg_analysis_label.setWordWrap(True)
        self.laser_intelligence_label = QLabel("Laser Intelligence: keine Analyse")
        self.laser_intelligence_label.setWordWrap(True)
        svg_quality_layout.addWidget(self.svg_simplify_enabled)
        svg_quality_layout.addWidget(QLabel("Toleranz"))
        svg_quality_layout.addWidget(self.svg_tolerance)
        svg_quality_layout.addWidget(self.svg_remove_duplicates)
        svg_quality_layout.addWidget(self.svg_show_analysis)
        svg_quality_layout.addWidget(self.svg_analysis_label)
        svg_quality_layout.addWidget(self.laser_intelligence_label)
        diagnostics_layout.addWidget(svg_quality)

        expert_tools = QGroupBox("Expertenfunktionen")
        expert_layout = QVBoxLayout(expert_tools)
        expert_layout.setContentsMargins(8, 8, 8, 8)
        expert_layout.setSpacing(6)
        expert_layout.addWidget(self._button("Profile exportieren", self._export_profiles))
        expert_layout.addWidget(self._button("Profile importieren", self._import_profiles))
        expert_layout.addWidget(self._button("Testmatrix erzeugen", self._generate_test_matrix))
        expert_layout.addWidget(self._button("Als gut speichern", lambda: self._record_job_result("good")))
        expert_layout.addWidget(self._button("Problem speichern", lambda: self._record_job_result("problem")))
        expert_layout.addWidget(self._button("Historie exportieren", self._export_history))
        expert_layout.addWidget(self._button("Historie importieren", self._import_history))
        diagnostics_layout.addWidget(expert_tools)
        self._add_sidebar_section(sidebar_layout, "Diagnose", diagnostics_page, False)
        sidebar_layout.addStretch(1)

    def _build_content(self, layout: QVBoxLayout) -> None:
        self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.workspace_splitter.setChildrenCollapsible(False)
        layout.addWidget(self.workspace_splitter, 1)

        main_panel = QWidget()
        main_layout = QVBoxLayout(main_panel)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.workspace_splitter.addWidget(main_panel)

        self.right_sidebar = QWidget()
        self.right_sidebar.setObjectName("rightSidebar")
        self.right_sidebar.setMinimumWidth(320)
        self.right_sidebar.setMaximumWidth(350)
        right_layout = QVBoxLayout(self.right_sidebar)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(8)
        self.workspace_splitter.addWidget(self.right_sidebar)
        self.workspace_splitter.setStretchFactor(0, 7)
        self.workspace_splitter.setStretchFactor(1, 2)
        self.workspace_splitter.setSizes([1120, 330])

        layout = main_layout

        workflow_group = QFrame()
        workflow_group.setObjectName("workflowStrip")
        workflow_layout = QVBoxLayout(workflow_group)
        workflow_layout.setContentsMargins(6, 4, 6, 4)
        self.workflow_status = QLabel("1 Maschine verbinden -> 2 Homing -> 3 Material -> 4 Datei -> 5 Layer -> 6 Vorschau -> 7 Frame -> 8 Preflight -> 9 Start")
        self.workflow_status.setObjectName("workflowStatus")
        self.workflow_status.setWordWrap(True)
        self.workflow_status.setMaximumHeight(58)
        workflow_layout.addWidget(self.workflow_status)
        layout.addWidget(workflow_group)

        settings = QFrame()
        settings_layout = QHBoxLayout(settings)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        self.work_width = self._double_spin(10, 2000, 300, " mm")
        self.work_height = self._double_spin(10, 2000, 200, " mm")
        self.material_shape = QComboBox()
        self.material_shape.addItems([MATERIAL_SHAPE_RECTANGLE, MATERIAL_SHAPE_CIRCLE])
        self.material_shape.currentTextChanged.connect(lambda _text: self._settings_changed())
        self.job_origin = QComboBox()
        self.job_origin.addItems([JOB_ORIGIN_LOWER_LEFT, JOB_ORIGIN_CENTER])
        self.job_origin.currentTextChanged.connect(lambda _text: self._settings_changed())
        self.profile_name = QComboBox()
        self.profile_name.addItems(self.profile_service.names())
        self.profile_name.currentTextChanged.connect(lambda _text: self._profile_selected())
        for widget in (self.work_width, self.work_height):
            widget.valueChanged.connect(self._settings_changed)
        settings_layout.addWidget(QLabel("Arbeitsbereich"))
        settings_layout.addWidget(self.work_width)
        settings_layout.addWidget(QLabel("x"))
        settings_layout.addWidget(self.work_height)
        settings_layout.addSpacing(8)
        settings_layout.addWidget(QLabel("Form"))
        settings_layout.addWidget(self.material_shape)
        settings_layout.addWidget(QLabel("Ursprung"))
        settings_layout.addWidget(self.job_origin)
        settings_layout.addSpacing(8)
        settings_layout.addSpacing(16)
        settings_layout.addWidget(QLabel("Material"))
        settings_layout.addWidget(self.profile_name, 1)
        self.add_material_button = self._button("Material hinzufuegen", self._open_add_material_dialog)
        settings_layout.addWidget(self.add_material_button)
        layout.addWidget(settings)

        material_settings = QFrame()
        material_layout = QHBoxLayout(material_settings)
        material_layout.setContentsMargins(0, 0, 0, 0)
        self.power_percent = self._spin(0, 100, DEFAULT_PROFILES[0].power_percent, suffix=" %")
        self.speed_mm_min = self._spin(50, 12000, DEFAULT_PROFILES[0].speed_mm_min, 50, " mm/min")
        self.passes = self._spin(1, 20, DEFAULT_PROFILES[0].passes, suffix=" x")
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

        self.material_summary = QLabel("Material: kein Profil gewaehlt")
        self.material_summary.setObjectName("materialSummary")
        self.material_summary.setWordWrap(True)
        self.material_summary.setMaximumHeight(48)
        layout.addWidget(self.material_summary)

        self.layer_panel = LayerPanel(on_changed=self._layer_changed)
        right_layout.addWidget(self.layer_panel)

        self.project_summary = QLabel("Projekt: Noch keine Motive vorhanden. Jetzt erstes Motiv importieren.")
        self.project_summary.setObjectName("projectSummary")
        self.project_summary.setWordWrap(True)
        self.project_summary.setMaximumHeight(48)
        layout.addWidget(self.project_summary)

        self.job_summary = QLabel("Naechster Schritt: Motiv importieren.")
        self.job_summary.setObjectName("jobSummary")
        self.job_summary.setWordWrap(True)
        self.job_summary.setMaximumHeight(48)
        layout.addWidget(self.job_summary)

        self.assistant_summary = QTextEdit()
        self.assistant_summary.setReadOnly(True)
        self.assistant_summary.setMinimumHeight(105)
        self.assistant_summary.setMaximumHeight(155)
        self.assistant_summary.setObjectName("assistantSummary")
        assistant_group = QGroupBox("Gefuehrter Check")
        assistant_layout = QVBoxLayout(assistant_group)
        assistant_layout.addWidget(self.assistant_summary)
        right_layout.addWidget(assistant_group)

        placement = QGroupBox("Motiv transformieren")
        placement.setVisible(False)
        placement_container_layout = QVBoxLayout(placement)
        placement_container_layout.setContentsMargins(6, 4, 6, 6)
        placement_body = QWidget()
        placement_layout = QGridLayout(placement_body)
        placement_container_layout.addWidget(placement_body)
        self.transform_group = placement
        self.transform_body = placement_body
        self.svg_auto = QRadioButton("Automatisch")
        self.svg_manual = QRadioButton("Manuell")
        self.svg_auto.setChecked(True)
        self.svg_auto.toggled.connect(lambda _checked: self._apply_svg_placement())
        self.svg_margin = self._double_spin(0, 50, AUTO_FIT_MARGIN_MM, " mm")
        self.svg_manual_width = self._double_spin(0.1, 2000, 50, " mm")
        self.artwork_height = self._double_spin(0.1, 2000, 50, " mm")
        self.artwork_scale_percent = self._double_spin(0.1, 1000, 100, " %")
        self.artwork_rotation = self._double_spin(-360, 360, 0, " deg")
        self.artwork_keep_aspect = QCheckBox("Seitenverhaeltnis sperren")
        self.artwork_keep_aspect.setChecked(True)
        self.svg_offset_x = self._double_spin(-2000, 2000, 0, " mm")
        self.svg_offset_y = self._double_spin(-2000, 2000, 0, " mm")
        self.svg_margin.valueChanged.connect(lambda _value: self._apply_svg_placement())
        self.svg_manual_width.valueChanged.connect(self._transform_width_changed)
        self.artwork_height.valueChanged.connect(self._transform_height_changed)
        self.artwork_scale_percent.valueChanged.connect(self._transform_scale_changed)
        self.artwork_rotation.valueChanged.connect(self._transform_rotation_changed)
        self.artwork_keep_aspect.toggled.connect(self._transform_aspect_changed)
        self.svg_offset_x.valueChanged.connect(lambda _value: self._transform_position_changed())
        self.svg_offset_y.valueChanged.connect(lambda _value: self._transform_position_changed())
        placement_layout.setContentsMargins(8, 8, 8, 8)
        placement_layout.setHorizontalSpacing(6)
        placement_layout.setVerticalSpacing(4)
        placement_layout.addWidget(self.svg_auto, 0, 0)
        placement_layout.addWidget(self.svg_manual, 0, 1)
        placement_layout.addWidget(QLabel("Rand"), 0, 2)
        placement_layout.addWidget(self.svg_margin, 0, 3)
        placement_layout.addWidget(self.artwork_keep_aspect, 0, 4, 1, 2)
        self.svg_size_label = QLabel("Motiv: keine SVG")
        self.svg_size_label.setWordWrap(False)
        self.svg_size_label.setMaximumHeight(22)

        compact_fields = (
            ("X", self.svg_offset_x),
            ("Y", self.svg_offset_y),
            ("Breite", self.svg_manual_width),
            ("Hoehe", self.artwork_height),
            ("Skalierung", self.artwork_scale_percent),
            ("Rotation", self.artwork_rotation),
        )
        for index, (label, widget) in enumerate(compact_fields):
            row = 1 + index // 3
            column = (index % 3) * 2
            placement_layout.addWidget(QLabel(label), row, column)
            placement_layout.addWidget(widget, row, column + 1)

        rotate_left = self._button("Links drehen", lambda: self._rotate_artwork(-90.0))
        rotate_right = self._button("Rechts drehen", lambda: self._rotate_artwork(90.0))
        placement_layout.addWidget(rotate_left, 3, 0)
        placement_layout.addWidget(rotate_right, 3, 1)
        placement_layout.addWidget(self._button("Zentrieren", self._center_artwork), 3, 2)
        placement_layout.addWidget(self._button("Links unten", self._place_artwork_lower_left), 3, 3)
        placement_layout.addWidget(self._button("Einpassen", self._fit_svg_to_material), 3, 4)
        placement_layout.addWidget(self._button("Originalgroesse", self._restore_artwork_original_size), 3, 5)
        placement_layout.addWidget(self.svg_size_label, 4, 0, 1, 6)
        placement_body.setVisible(False)
        self.transform_button = self._button("Motiv transformieren", self._open_transform_dialog)
        layout.addWidget(self.transform_button)

        self.preview = WorkAreaPreview()
        preview_group = QGroupBox("Vorschau")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_options = {
            "artwork": QCheckBox("Motiv"),
            "bounds": QCheckBox("Bounding Box"),
            "work_area": QCheckBox("Arbeitsbereich"),
            "head": QCheckBox("Kopfposition"),
            "gcode": QCheckBox("GCode-Pfad"),
            "overscan": QCheckBox("Overscan"),
            "snap": QCheckBox("Snap"),
        }
        option_row = QHBoxLayout()
        for key, checkbox in self.preview_options.items():
            checkbox.setChecked(key != "gcode")
            checkbox.toggled.connect(lambda _checked: self._draw_preview())
            option_row.addWidget(checkbox)
        option_row.addStretch(1)
        preview_layout.addLayout(option_row)
        self.import_summary_label = QLabel("Import: keine Datei geladen")
        self.import_summary_label.setObjectName("importSummary")
        self.import_summary_label.setWordWrap(False)
        self.import_summary_label.setMaximumHeight(22)
        preview_layout.addWidget(self.import_summary_label)
        self.preview_position_label = QLabel("Motivposition: --")
        self.preview_position_label.setObjectName("previewPosition")
        self.preview_position_label.setMaximumHeight(22)
        preview_layout.addWidget(self.preview_position_label)
        self.preview.artwork_position_requested.connect(self._move_artwork_from_preview)
        self.preview.artwork_selection_changed.connect(self._preview_selection_changed)
        self.preview.artwork_item_selected.connect(self._select_artwork_item)
        preview_layout.addWidget(self.preview)
        layout.addWidget(preview_group, 1)

        self.expert_tabs = QTabWidget()
        self.gcode_group = QGroupBox("G-Code")
        gcode_layout = QVBoxLayout(self.gcode_group)
        self.gcode_text = QTextEdit()
        self.gcode_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.gcode_text.setStyleSheet("font-family: Consolas, monospace; font-size: 10pt;")
        self.gcode_text.textChanged.connect(self._fit_gcode_panel_to_text)
        self.gcode_text.textChanged.connect(self._update_job_summary)
        self.gcode_text.textChanged.connect(self._update_assistant_panel)
        gcode_layout.addWidget(self.gcode_text)

        self.console_log_panel = ConsoleLogPanel()
        self.log_text = self.console_log_panel.log_text
        self.expert_tabs.addTab(self.gcode_group, "G-Code")
        self.expert_tabs.addTab(self.console_log_panel, "Log")
        self.diagnostics_group = QGroupBox("Diagnose / Expertenansicht")
        self.diagnostics_group.setCheckable(True)
        self.diagnostics_group.setChecked(False)
        diagnostics_layout = QVBoxLayout(self.diagnostics_group)
        diagnostics_layout.addWidget(self.expert_tabs)
        self.expert_tabs.setVisible(False)
        self.diagnostics_group.toggled.connect(self.expert_tabs.setVisible)
        right_layout.addWidget(self.diagnostics_group)
        right_layout.addStretch(1)

    def _build_status_bar(self, layout: QVBoxLayout) -> None:
        self.status_panel = StatusPanel()
        self.job_status = self.status_panel.job_status
        self.progress = self.status_panel.progress
        self.status = self.status_panel.status
        layout.addWidget(self.status_panel)
        self._apply_theme(self.dark_mode_enabled)

    def _button(self, text: str, handler: Callable) -> QPushButton:
        button = QPushButton(text)
        button.setToolTip(text)
        button.clicked.connect(handler)
        button.setMinimumHeight(32)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return button

    def _machine_action_button(self, action_id: str, source: str) -> QPushButton:
        definition = self.machine_action_registry.get(action_id)
        button = QPushButton(definition.label)
        button.setObjectName(f"machineAction_{action_id}")
        button.setToolTip(definition.tooltip)
        if action_id in {"toggle_alignment", "toggle_work_area_trace"}:
            button.setCheckable(True)
        if action_id == "toggle_alignment":
            self.alignment_button = button
        if action_id == "toggle_work_area_trace":
            self.work_area_trace_button = button
        button.clicked.connect(lambda _checked=False, item=action_id, origin=source: self._trigger_machine_action(item, origin))
        if action_id == "emergency_stop":
            button.setMinimumHeight(42)
        elif action_id in {"start_job", "stop", "frame", "dry_run"}:
            button.setMinimumHeight(36)
        else:
            button.setMinimumHeight(32)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.action_buttons.setdefault(action_id, []).append(button)
        return button

    def _configure_sidebar_combo(self, combo: QComboBox) -> None:
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        combo.setMinimumWidth(0)
        combo.view().setMinimumWidth(320)
        if hasattr(self, "sidebar_combos"):
            self.sidebar_combos.append(combo)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._sync_sidebar_popup_widths()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._closing = True
        try:
            self.app_controller.shutdown_controller()
            for thread in list(self._worker_threads):
                thread.join(timeout=1.0)
        finally:
            super().closeEvent(event)

    def _sync_sidebar_popup_widths(self) -> None:
        if not hasattr(self, "sidebar_combos"):
            return
        width = max(320, self.left_sidebar.width() - 24)
        for combo in self.sidebar_combos:
            combo.view().setMinimumWidth(width)

    def _spin(self, minimum: int, maximum: int, value: int, step: int = 1, suffix: str = "") -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setValue(value)
        if suffix:
            spin.setSuffix(suffix)
        return spin

    def _double_spin(self, minimum: float, maximum: float, value: float, suffix: str = "") -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(1)
        spin.setSingleStep(1.0)
        spin.setValue(value)
        if suffix:
            spin.setSuffix(suffix)
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
        if hasattr(self, "app_controller") and hasattr(self, "work_width") and hasattr(self, "work_height"):
            self.app_controller.set_current_workspace(self.work_width.value(), self.work_height.value())
        if self.original_imported_paths:
            self._apply_svg_placement()
        elif self.original_raster_source is not None:
            fitted_source = self._fit_raster_source(self.original_raster_source)
            self.raster_sources = [fitted_source]
            self.artwork_source = fitted_source
            self._set_svg_size_label(fitted_source.width_mm, fitted_source.height_mm, source_label=f"Raster: {fitted_source.file_name}")
            self._refresh_gcode()
            self._draw_preview()
        else:
            self._refresh_gcode()
            self._draw_preview()

    def _draw_preview(self) -> None:
        if hasattr(self, "preview"):
            self.preview.set_preview_model(
                self._build_preview_model(),
                self.material_shape.currentText() if hasattr(self, "material_shape") else MATERIAL_SHAPE_RECTANGLE,
                self.svg_margin.value() if hasattr(self, "svg_margin") else AUTO_FIT_MARGIN_MM,
                self.job_origin.currentText() if hasattr(self, "job_origin") else JOB_ORIGIN_LOWER_LEFT,
            )
            selected_item = self._selected_artwork_item()
            self.preview.set_artwork_interaction(
                selected_item.transform.bounds if selected_item is not None else (self.artwork_transform.bounds if self.artwork_transform is not None else None),
                bool(
                    self.preview_options.get("snap") is None
                    or self.preview_options["snap"].isChecked()
                ),
            )
        self._update_import_summary()

    def _build_preview_model(self) -> JobPreviewModel:
        estimated_runtime = None
        warnings: list[str] = []
        if hasattr(self, "gcode_text"):
            try:
                prepared = self.job_service.prepare_job(
                    self.gcode_text.toPlainText(),
                    self.work_width.value(),
                    self.work_height.value(),
                    self._effective_job_profile(),
                    self.operation_mode.currentText(),
                )
                estimated_runtime = prepared.analysis.estimated_runtime_seconds
                warnings.extend(prepared.warnings)
                gcode_segments = prepared.analysis.segments
            except ValueError as exc:
                warnings.append(str(exc))
                gcode_segments = []
        else:
            gcode_segments = []
        if self.autofit_result is not None:
            warnings.append(self.autofit_result.summary)
        # A generated job (test matrix) is shown as its G-code, not as the imported artwork.
        if self.laser_project.items and not getattr(self, "_generated_job_name", None):
            return build_multi_item_preview_model(
                self._visible_preview_items(),
                self._current_layers(),
                self.work_width.value(),
                self.work_height.value(),
                estimated_runtime,
                warnings,
                gcode_segments,
                self._preview_head_position(),
                self._preview_options(),
                self._fill_toolpaths_by_item,
            )
        preview_paths = self._effective_legacy_source_paths() if self.original_imported_paths and self.artwork_transform is not None else self.imported_paths
        return build_preview_model(
            preview_paths,
            self._current_layers(),
            self.work_width.value(),
            self.work_height.value(),
            estimated_runtime,
            warnings,
            self.raster_sources,
            self.artwork_transform if self.original_imported_paths else None,
            gcode_segments,
            self._preview_head_position(),
            self._preview_options(),
            self.fill_toolpaths,
        )

    def _preview_options(self) -> PreviewOptions:
        options = getattr(self, "preview_options", {})
        return PreviewOptions(
            show_artwork=bool(options.get("artwork") is None or options["artwork"].isChecked()),
            show_bounds=bool(options.get("bounds") is None or options["bounds"].isChecked()),
            show_work_area=bool(options.get("work_area") is None or options["work_area"].isChecked()),
            show_head_position=bool(options.get("head") is None or options["head"].isChecked()),
            show_gcode_path=bool(options.get("gcode") is not None and options["gcode"].isChecked()),
            show_overscan=bool(options.get("overscan") is None or options["overscan"].isChecked()),
        )

    def _preview_head_position(self) -> PreviewHeadPosition | None:
        state = getattr(self, "app_controller", None).machine_state if hasattr(self, "app_controller") else None
        if state is None or not state.position_source or state.x_mm is None or state.y_mm is None:
            return None
        if not state.position_source.startswith("WPos"):
            return None
        return PreviewHeadPosition(state.x_mm, state.y_mm, state.position_source)

    def log(self, message: str) -> None:
        self.status_panel.set_message(message)
        self.console_log_panel.append(message)
        self.diagnostic_log.app(message)


def run_app() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = LaserControlWindow()
    window.show()
    return app.exec()
