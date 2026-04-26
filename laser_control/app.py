import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from laser_control.gcode import (
    CUT_MODE,
    ENGRAVE_MODE,
    build_dry_run_gcode,
    build_polyline_gcode,
    build_rectangle_frame_gcode,
    prepare_job_gcode,
)
from laser_control.laser import SimulatedLaserController
from laser_control.material_db import delete_material, find_material, load_materials, upsert_material
from laser_control.models import MaterialProfile
from laser_control.profiles import DEFAULT_PROFILES
from laser_control.project import load_project, project_to_dict, save_project
from laser_control.serial_grbl import GrblSerialController, list_serial_ports, serial_support_available
from laser_control.svg_import import fit_paths_to_area, import_svg, scale_paths_to_width


class LaserControlApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title("Laser Control")
        self.geometry("1120x720")
        self.minsize(980, 620)

        self.work_width = tk.DoubleVar(value=300.0)
        self.work_height = tk.DoubleVar(value=200.0)
        self.profile_name = tk.StringVar(value=DEFAULT_PROFILES[0].name)
        self.power_percent = tk.IntVar(value=DEFAULT_PROFILES[0].power_percent)
        self.speed_mm_min = tk.IntVar(value=DEFAULT_PROFILES[0].speed_mm_min)
        self.passes = tk.IntVar(value=DEFAULT_PROFILES[0].passes)
        self.operation_mode = tk.StringVar(value=ENGRAVE_MODE)
        self.connection_mode = tk.StringVar(value="Simulator")
        self.serial_port = tk.StringVar()
        self.selected_serial_port = ""
        self.status = tk.StringVar(value="Simulator bereit.")
        self.job_status = tk.StringVar(value="Bereit")
        self.progress_text = tk.StringVar(value="0%")
        self.progress_value = tk.DoubleVar(value=0.0)
        self.gcode = tk.StringVar()
        self.imported_paths = []
        self.original_imported_paths = []
        self.imported_file = None
        self.svg_placement_mode = tk.StringVar(value="Automatisch")
        self.svg_margin = tk.DoubleVar(value=5.0)
        self.svg_manual_width = tk.DoubleVar(value=50.0)
        self.svg_offset_x = tk.DoubleVar(value=0.0)
        self.svg_offset_y = tk.DoubleVar(value=0.0)
        self.material_point_a = None
        self.material_point_b = None
        self.material_measurement = None
        self.material_measurement_label = tk.StringVar(value="Nicht eingemessen")
        self.material_db_name = tk.StringVar(value="")
        self.material_db_width = tk.DoubleVar(value=0.0)
        self.material_db_height = tk.DoubleVar(value=0.0)
        self.material_db_selection = tk.StringVar(value="")
        self.material_db_records = load_materials()
        self.material_profiles = [MaterialProfile(item.name, item.power_percent, item.speed_mm_min, item.passes) for item in DEFAULT_PROFILES]
        self.current_project_path = None
        self.ui_queue = queue.Queue()
        self.worker_busy = False

        self.controller = SimulatedLaserController(self._threadsafe_log, self._threadsafe_progress)
        self.active_connection_mode = self.connection_mode.get()

        self._build_layout()
        self._refresh_gcode()
        self._draw_preview()
        self.after(100, self._poll_worker_events)

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)

        sidebar = self._build_scrollable_sidebar()
        sidebar.grid(row=0, column=0, sticky="ns")

        content = ttk.Frame(self, padding=(0, 16, 16, 16))
        content.grid(row=0, column=1, sticky="nsew")
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=2)
        content.rowconfigure(1, weight=1)

        self._build_sidebar(self.sidebar_content)
        self._build_content(content)

        status_bar = ttk.Frame(self, padding=(16, 8))
        status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        status_bar.columnconfigure(1, weight=1)
        ttk.Label(status_bar, textvariable=self.job_status, width=18).grid(row=0, column=0, sticky="w")
        ttk.Progressbar(status_bar, variable=self.progress_value, maximum=100).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Label(status_bar, textvariable=self.progress_text, width=6).grid(row=0, column=2, sticky="e")
        ttk.Label(status_bar, textvariable=self.status).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

    def _build_scrollable_sidebar(self) -> ttk.Frame:
        outer = ttk.Frame(self)
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        self.sidebar_canvas = tk.Canvas(outer, width=178, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=self.sidebar_canvas.yview)
        self.sidebar_canvas.configure(yscrollcommand=scrollbar.set)
        self.sidebar_canvas.grid(row=0, column=0, sticky="ns")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.sidebar_content = ttk.Frame(self.sidebar_canvas, padding=8)
        self.sidebar_window = self.sidebar_canvas.create_window((0, 0), window=self.sidebar_content, anchor="nw")
        self.sidebar_content.bind("<Configure>", self._update_sidebar_scroll_region)
        self.sidebar_canvas.bind("<Configure>", self._resize_sidebar_content)
        self.sidebar_canvas.bind("<MouseWheel>", self._scroll_sidebar)
        self.sidebar_content.bind("<MouseWheel>", self._scroll_sidebar)
        return outer

    def _update_sidebar_scroll_region(self, _event=None) -> None:
        self.sidebar_canvas.configure(scrollregion=self.sidebar_canvas.bbox("all"))

    def _resize_sidebar_content(self, event) -> None:
        self.sidebar_canvas.itemconfigure(self.sidebar_window, width=event.width)

    def _scroll_sidebar(self, event) -> None:
        self.sidebar_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Verbindung", font=("Segoe UI", 12, "bold")).pack(anchor="w")

        status_row = ttk.Frame(parent)
        status_row.pack(fill="x", pady=(8, 4))
        self.connection_indicator = tk.Canvas(status_row, width=18, height=18, highlightthickness=0)
        self.connection_indicator.pack(side="left")
        self.connection_label = ttk.Label(status_row, text="Nicht verbunden")
        self.connection_label.pack(side="left", padx=(8, 0))
        self._set_connection_indicator(False)

        mode = ttk.Combobox(parent, textvariable=self.connection_mode, values=["Simulator", "GRBL ueber USB"], state="readonly", width=22)
        mode.pack(fill="x", pady=(4, 4))
        mode.bind("<<ComboboxSelected>>", lambda _: self._switch_controller())

        self.port_select = ttk.Combobox(parent, textvariable=self.serial_port, values=[], width=22)
        self.port_select.pack(fill="x", pady=4)
        ttk.Button(parent, text="Ports suchen", command=self._refresh_ports).pack(fill="x", pady=4)

        ttk.Button(parent, text="Verbinden", command=lambda: self._run_controller_action(lambda controller: controller.connect())).pack(fill="x", pady=(8, 4))
        ttk.Button(parent, text="Trennen", command=lambda: self._run_controller_action(lambda controller: controller.disconnect())).pack(fill="x", pady=4)
        ttk.Button(parent, text="Referenzfahrt", command=lambda: self._run_controller_action(lambda controller: controller.home())).pack(fill="x", pady=(4, 16))

        ttk.Button(parent, text="Status abfragen", command=self._query_status).pack(fill="x", pady=(0, 4))
        ttk.Button(parent, text="GRBL Settings", command=self._query_settings).pack(fill="x", pady=(0, 16))

        ttk.Label(parent, text="Jog", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        jog = ttk.Frame(parent)
        jog.pack(pady=8)
        ttk.Button(jog, text="Y+", width=7, command=lambda: self._run_controller_action(lambda controller: controller.jog(0, 10))).grid(row=0, column=1)
        ttk.Button(jog, text="X-", width=7, command=lambda: self._run_controller_action(lambda controller: controller.jog(-10, 0))).grid(row=1, column=0)
        ttk.Button(jog, text="X+", width=7, command=lambda: self._run_controller_action(lambda controller: controller.jog(10, 0))).grid(row=1, column=2)
        ttk.Button(jog, text="Y-", width=7, command=lambda: self._run_controller_action(lambda controller: controller.jog(0, -10))).grid(row=2, column=1)

        ttk.Separator(parent).pack(fill="x", pady=16)

        ttk.Label(parent, text="Material", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(parent, textvariable=self.material_measurement_label, wraplength=150).pack(anchor="w", pady=(6, 4))
        ttk.Button(parent, text="Ecke 1 setzen", command=lambda: self._capture_material_point(1)).pack(fill="x", pady=4)
        ttk.Button(parent, text="Ecke 2 setzen", command=lambda: self._capture_material_point(2)).pack(fill="x", pady=4)
        ttk.Button(parent, text="Groesse uebernehmen", command=self._apply_material_measurement).pack(fill="x", pady=(4, 12))
        ttk.Label(parent, text="Name").pack(anchor="w")
        ttk.Entry(parent, textvariable=self.material_db_name).pack(fill="x", pady=(0, 4))
        material_size = ttk.Frame(parent)
        material_size.pack(fill="x", pady=(0, 4))
        ttk.Label(material_size, text="B").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(material_size, from_=1, to=2000, increment=1, textvariable=self.material_db_width, width=6).grid(row=0, column=1, padx=(4, 8))
        ttk.Label(material_size, text="H").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(material_size, from_=1, to=2000, increment=1, textvariable=self.material_db_height, width=6).grid(row=0, column=3, padx=(4, 0))
        ttk.Button(parent, text="Material speichern", command=self._save_measured_material).pack(fill="x", pady=4)
        self.material_db_combo = ttk.Combobox(
            parent,
            textvariable=self.material_db_selection,
            values=[item.get("name", "") for item in self.material_db_records],
            state="readonly",
        )
        self.material_db_combo.pack(fill="x", pady=4)
        self.material_db_combo.bind("<<ComboboxSelected>>", lambda _: self._select_material_record())
        ttk.Button(parent, text="Material laden", command=self._load_measured_material).pack(fill="x", pady=(4, 12))
        ttk.Button(parent, text="Material loeschen", command=self._delete_measured_material).pack(fill="x", pady=(0, 12))

        ttk.Separator(parent).pack(fill="x", pady=16)

        ttk.Label(parent, text="Job", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(parent, text="Modus").pack(anchor="w", pady=(8, 0))
        mode_select = ttk.Combobox(
            parent,
            textvariable=self.operation_mode,
            values=[ENGRAVE_MODE, CUT_MODE],
            state="readonly",
            width=22,
        )
        mode_select.pack(fill="x", pady=(4, 4))
        mode_select.bind("<<ComboboxSelected>>", lambda _: self._settings_changed())
        ttk.Button(parent, text="Rahmen fahren", command=self._frame_job).pack(fill="x", pady=(8, 4))
        ttk.Button(parent, text="Dry Run", command=self._dry_run_job).pack(fill="x", pady=4)
        ttk.Button(parent, text="Start", command=self._start_job).pack(fill="x", pady=4)
        ttk.Button(parent, text="Pause", command=lambda: self._run_controller_action(lambda controller: controller.pause(), allow_while_busy=True)).pack(fill="x", pady=4)
        ttk.Button(parent, text="Fortsetzen", command=lambda: self._run_controller_action(lambda controller: controller.resume(), allow_while_busy=True)).pack(fill="x", pady=4)
        ttk.Button(parent, text="Stop", command=lambda: self._run_controller_action(lambda controller: controller.stop(), allow_while_busy=True)).pack(fill="x", pady=4)
        ttk.Separator(parent).pack(fill="x", pady=16)

        ttk.Label(parent, text="Projekt", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Button(parent, text="SVG importieren", command=self._import_svg).pack(fill="x", pady=(8, 4))
        ttk.Button(parent, text="Speichern", command=self._save_project).pack(fill="x", pady=(8, 4))
        ttk.Button(parent, text="Laden", command=self._load_project).pack(fill="x", pady=4)
        self._refresh_ports()

    def _build_content(self, parent: ttk.Frame) -> None:
        settings = ttk.Frame(parent)
        settings.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        settings.columnconfigure(5, weight=1)

        ttk.Label(settings, text="Arbeitsbereich").grid(row=0, column=0, sticky="w")
        width = ttk.Spinbox(settings, from_=10, to=2000, increment=10, textvariable=self.work_width, width=8, command=self._settings_changed)
        width.grid(row=0, column=1, padx=(8, 4))
        ttk.Label(settings, text="x").grid(row=0, column=2)
        height = ttk.Spinbox(settings, from_=10, to=2000, increment=10, textvariable=self.work_height, width=8, command=self._settings_changed)
        height.grid(row=0, column=3, padx=4)
        ttk.Label(settings, text="mm").grid(row=0, column=4, padx=(0, 16))

        ttk.Label(settings, text="Material").grid(row=0, column=6, sticky="e")
        self.profile_combo = ttk.Combobox(settings, textvariable=self.profile_name, values=[item.name for item in self.material_profiles], state="readonly", width=24)
        self.profile_combo.grid(row=0, column=7, padx=(8, 0))
        self.profile_combo.bind("<<ComboboxSelected>>", lambda _: self._profile_selected())
        width.bind("<KeyRelease>", lambda _: self._settings_changed())
        height.bind("<KeyRelease>", lambda _: self._settings_changed())

        material_settings = ttk.Frame(parent)
        material_settings.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Label(material_settings, text="Leistung %").grid(row=0, column=0, sticky="w")
        power = ttk.Spinbox(material_settings, from_=0, to=100, increment=1, textvariable=self.power_percent, width=6, command=self._material_settings_changed)
        power.grid(row=0, column=1, padx=(8, 16))
        ttk.Label(material_settings, text="Geschwindigkeit").grid(row=0, column=2, sticky="w")
        speed = ttk.Spinbox(material_settings, from_=50, to=12000, increment=50, textvariable=self.speed_mm_min, width=8, command=self._material_settings_changed)
        speed.grid(row=0, column=3, padx=(8, 16))
        ttk.Label(material_settings, text="Durchgaenge").grid(row=0, column=4, sticky="w")
        passes = ttk.Spinbox(material_settings, from_=1, to=20, increment=1, textvariable=self.passes, width=5, command=self._material_settings_changed)
        passes.grid(row=0, column=5, padx=(8, 0))
        power.bind("<KeyRelease>", lambda _: self._material_settings_changed())
        speed.bind("<KeyRelease>", lambda _: self._material_settings_changed())
        passes.bind("<KeyRelease>", lambda _: self._material_settings_changed())

        placement = ttk.LabelFrame(parent, text="SVG Platzierung", padding=8)
        placement.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Radiobutton(placement, text="Automatisch", value="Automatisch", variable=self.svg_placement_mode, command=self._apply_svg_placement).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(placement, text="Manuell", value="Manuell", variable=self.svg_placement_mode, command=self._apply_svg_placement).grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Label(placement, text="Rand").grid(row=1, column=0, sticky="w", pady=(8, 0))
        margin = ttk.Spinbox(placement, from_=0, to=50, increment=1, textvariable=self.svg_margin, width=6, command=self._apply_svg_placement)
        margin.grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Label(placement, text="Breite").grid(row=1, column=2, sticky="w", padx=(12, 0), pady=(8, 0))
        manual_width = ttk.Spinbox(placement, from_=1, to=400, increment=1, textvariable=self.svg_manual_width, width=7, command=self._apply_svg_placement)
        manual_width.grid(row=1, column=3, sticky="w", pady=(8, 0))
        ttk.Label(placement, text="X").grid(row=2, column=0, sticky="w", pady=(8, 0))
        offset_x = ttk.Spinbox(placement, from_=0, to=400, increment=1, textvariable=self.svg_offset_x, width=6, command=self._apply_svg_placement)
        offset_x.grid(row=2, column=1, sticky="w", pady=(8, 0))
        ttk.Label(placement, text="Y").grid(row=2, column=2, sticky="w", padx=(12, 0), pady=(8, 0))
        offset_y = ttk.Spinbox(placement, from_=0, to=415, increment=1, textvariable=self.svg_offset_y, width=6, command=self._apply_svg_placement)
        offset_y.grid(row=2, column=3, sticky="w", pady=(8, 0))
        for field in (margin, manual_width, offset_x, offset_y):
            field.bind("<KeyRelease>", lambda _: self._apply_svg_placement())

        preview_group = ttk.LabelFrame(parent, text="Vorschau", padding=12)
        preview_group.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        preview_group.columnconfigure(0, weight=1)
        preview_group.rowconfigure(0, weight=1)

        self.preview = tk.Canvas(preview_group, bg="#f7f7f7", highlightthickness=1, highlightbackground="#c8c8c8")
        self.preview.grid(row=0, column=0, sticky="nsew")
        self.preview.bind("<Configure>", lambda _: self._draw_preview())

        gcode_group = ttk.LabelFrame(parent, text="G-Code", padding=12)
        gcode_group.grid(row=1, column=1, sticky="nsew")
        gcode_group.columnconfigure(0, weight=1)
        gcode_group.rowconfigure(0, weight=1)

        self.gcode_text = tk.Text(gcode_group, wrap="none", height=10, font=("Consolas", 10))
        self.gcode_text.grid(row=0, column=0, sticky="nsew")

        log_group = ttk.LabelFrame(parent, text="Log", padding=12)
        log_group.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        log_group.columnconfigure(0, weight=1)

        self.log_text = tk.Text(log_group, height=6, wrap="word", font=("Consolas", 10))
        self.log_text.grid(row=0, column=0, sticky="ew")

    def _settings_changed(self) -> None:
        self._refresh_gcode()
        self._draw_preview()

    def _profile_selected(self) -> None:
        profile = self._selected_profile()
        self.power_percent.set(profile.power_percent)
        self.speed_mm_min.set(profile.speed_mm_min)
        self.passes.set(profile.passes)
        self._settings_changed()

    def _material_settings_changed(self) -> None:
        profile = self._selected_profile()
        profile.power_percent = self._int_value(self.power_percent, profile.power_percent)
        profile.speed_mm_min = self._int_value(self.speed_mm_min, profile.speed_mm_min)
        profile.passes = self._int_value(self.passes, profile.passes)
        self._settings_changed()

    def _switch_controller(self) -> None:
        try:
            self.controller.disconnect()
        except Exception as exc:
            self.log(str(exc))
        self._set_connection_indicator(False)

        if self.connection_mode.get() == "GRBL ueber USB":
            self.selected_serial_port = self.serial_port.get()
            self.controller = GrblSerialController(self._threadsafe_log, lambda: self.selected_serial_port, self._threadsafe_progress)
            self.active_connection_mode = "GRBL ueber USB"
            self._refresh_ports()
            self.status.set("GRBL/USB bereit. Bitte COM-Port waehlen.")
        else:
            self.controller = SimulatedLaserController(self._threadsafe_log, self._threadsafe_progress)
            self.active_connection_mode = "Simulator"
            self.status.set("Simulator bereit.")

    def _current_controller(self):
        if self.active_connection_mode != self.connection_mode.get():
            self._switch_controller()
        return self.controller

    def _refresh_ports(self) -> None:
        if self.connection_mode.get() == "GRBL ueber USB" and self.active_connection_mode != "GRBL ueber USB":
            self._switch_controller()
            return

        ports = list_serial_ports()
        if hasattr(self, "port_select"):
            self.port_select.configure(values=ports)
        if ports and not self.serial_port.get():
            self.serial_port.set(ports[0])
            self.selected_serial_port = ports[0]
            self.log(f"COM-Port gefunden: {ports[0]}")
        elif ports:
            self.selected_serial_port = self.serial_port.get()
            self.log(f"{len(ports)} COM-Port(s) gefunden.")
        elif not serial_support_available():
            self.log("pyserial ist nicht installiert. Bitte requirements installieren.")
        if not ports:
            self.log("Keine COM-Ports gefunden.")

    def _query_status(self) -> None:
        controller = self._current_controller()
        query_status = getattr(controller, "query_status", None)
        if query_status is None:
            self.log("Statusabfrage gibt es nur im GRBL/USB-Modus.")
            return
        self._run_worker(query_status)

    def _query_settings(self) -> None:
        controller = self._current_controller()
        query_settings = getattr(controller, "query_settings", None)
        if query_settings is None:
            self.log("GRBL Settings gibt es nur im GRBL/USB-Modus.")
            return
        self._run_worker(query_settings)

    def _frame_job(self) -> None:
        controller = self._current_controller()
        width = self._dimension(self.work_width)
        height = self._dimension(self.work_height)

        def frame() -> None:
            try:
                controller.frame(width, height)
            except TypeError:
                controller.frame()

        self._run_worker(frame)

    def _start_job(self) -> None:
        controller = self._current_controller()
        width = self._dimension(self.work_width)
        height = self._dimension(self.work_height)
        profile = self._selected_profile()
        if hasattr(self, "gcode_text"):
            gcode = self.gcode_text.get("1.0", "end").strip()
            self.gcode.set(gcode)
        else:
            gcode = self.gcode.get()
        commands = prepare_job_gcode(gcode, width, height)
        controller_name = controller.__class__.__name__
        mode_label = self._operation_mode_label()

        if self.connection_mode.get() != "GRBL ueber USB":
            confirmed = messagebox.askyesno(
                "Simulator-Modus",
                "Die App ist im Simulator-Modus.\n\n"
                "Der Job wird nicht an den Laser gesendet.\n"
                f"Auswahl: {mode_label}\n"
                "Soll die Simulation gestartet werden?",
            )
            if not confirmed:
                self.log("Simulation abgebrochen.")
                return
        else:
            if not self._hardware_preflight_ok(controller):
                return
            confirmed = messagebox.askyesno(
                "Laserjob starten",
                "Laserjob wirklich starten?\n\n"
                "Modus: GRBL ueber USB\n"
                f"Operation: {mode_label}\n"
                f"Controller: {controller_name}\n"
                f"Port: {self.serial_port.get()}\n"
                f"Arbeitsbereich: {width:.0f} x {height:.0f} mm\n"
                f"Material: {profile.name}\n"
                f"Leistung: {profile.power_percent}%\n"
                f"Geschwindigkeit: {profile.speed_mm_min} mm/min\n"
                f"G-Code-Zeilen: {len(commands)}\n\n"
                "Schutzbrille tragen und Arbeitsbereich pruefen.",
            )
            if not confirmed:
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
        width = self._dimension(self.work_width)
        height = self._dimension(self.work_height)
        if hasattr(self, "gcode_text"):
            gcode = self.gcode_text.get("1.0", "end").strip()
            self.gcode.set(gcode)
        else:
            gcode = self.gcode.get()
        dry_run_gcode = build_dry_run_gcode(gcode, width, height)
        command_count = len(dry_run_gcode.splitlines())
        controller_name = controller.__class__.__name__
        mode_label = self._operation_mode_label()

        if self.connection_mode.get() != "GRBL ueber USB":
            confirmed = messagebox.askyesno(
                "Simulator Dry Run",
                "Dry Run startet im Simulator.\n\n"
                "Es wird nur Bewegung simuliert, ohne Laser.\n"
                f"Auswahl: {mode_label}\n"
                "Soll die Simulation gestartet werden?",
            )
            if not confirmed:
                self.log("Dry Run abgebrochen.")
                return
        else:
            if not self._hardware_preflight_ok(controller):
                return
            confirmed = messagebox.askyesno(
                "Dry Run starten",
                "Dry Run wirklich starten?\n\n"
                "Modus: GRBL ueber USB\n"
                f"Operation: {mode_label}\n"
                f"Controller: {controller_name}\n"
                f"Port: {self.serial_port.get()}\n"
                f"Arbeitsbereich: {width:.0f} x {height:.0f} mm\n"
                f"Dry-Run-Zeilen: {command_count}\n\n"
                "Laser bleibt aus (M5 erzwungen).",
            )
            if not confirmed:
                self.log("Dry Run abgebrochen.")
                return

        self.log(f"Dry Run Start-Controller: {controller_name} ({mode_label})")

        def start_dry_run() -> None:
            try:
                controller.start_job(dry_run_gcode, width, height)
            except TypeError:
                controller.start_job(dry_run_gcode)

        self._run_worker(start_dry_run)

    def _hardware_preflight_ok(self, controller) -> bool:
        if not serial_support_available():
            message = "pyserial ist nicht installiert. Bitte requirements installieren."
            self.log(message)
            messagebox.showerror("Preflight fehlgeschlagen", message)
            return False

        port = self.serial_port.get().strip()
        if not port:
            message = "Kein COM-Port ausgewaehlt. Bitte zuerst einen Port waehlen."
            self.log(message)
            messagebox.showerror("Preflight fehlgeschlagen", message)
            return False

        state = getattr(controller, "state", None)
        if not state or not getattr(state, "connected", False):
            message = "Controller ist nicht verbunden. Bitte zuerst auf 'Verbinden' klicken."
            self.log(message)
            messagebox.showerror("Preflight fehlgeschlagen", message)
            return False

        if not getattr(state, "homed", False):
            message = "Keine Referenzfahrt erkannt. Bitte zuerst 'Referenzfahrt' ausfuehren."
            self.log(message)
            messagebox.showerror("Preflight fehlgeschlagen", message)
            return False

        return True

    def _refresh_gcode(self) -> None:
        profile = self._selected_profile()
        operation_mode = self.operation_mode.get()
        if self.imported_paths:
            code = build_polyline_gcode(self.imported_paths, profile, operation_mode)
        else:
            code = build_rectangle_frame_gcode(
                self._dimension(self.work_width),
                self._dimension(self.work_height),
                profile,
                operation_mode,
            )
        self.gcode.set(code)
        if hasattr(self, "gcode_text"):
            self.gcode_text.delete("1.0", "end")
            self.gcode_text.insert("1.0", code)

    def _operation_mode_label(self) -> str:
        return "Cutten (M3 konstant)" if self.operation_mode.get() == CUT_MODE else "Gravieren (M4 dynamisch)"

    def _import_svg(self) -> None:
        path = filedialog.askopenfilename(
            title="SVG importieren",
            filetypes=[("SVG", "*.svg"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return

        result = import_svg(path)
        self.original_imported_paths = result.paths
        self.imported_paths = result.paths
        self.imported_file = path
        if not self.material_measurement:
            self.work_width.set(round(result.width_mm, 2))
            self.work_height.set(round(result.height_mm, 2))
        self._apply_svg_placement(refresh=False)
        self._refresh_gcode()
        self._draw_preview()
        point_count = sum(len(polyline) for polyline in self.imported_paths)
        self.log(f"SVG importiert: {path} ({len(self.imported_paths)} Pfade, {point_count} Punkte)")

    def _save_project(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Projekt speichern",
            defaultextension=".laser.json",
            filetypes=[("Laser Control Projekt", "*.laser.json"), ("JSON", "*.json"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return

        data = project_to_dict(
            self._dimension(self.work_width),
            self._dimension(self.work_height),
            self._selected_profile(),
            self.gcode_text.get("1.0", "end").strip() if hasattr(self, "gcode_text") else self.gcode.get(),
            self.imported_paths,
            self.imported_file,
            self.material_measurement,
            self._svg_placement_data(),
        )
        save_project(path, data)
        self.current_project_path = path
        self.log(f"Projekt gespeichert: {path}")

    def _load_project(self) -> None:
        path = filedialog.askopenfilename(
            title="Projekt laden",
            filetypes=[("Laser Control Projekt", "*.laser.json"), ("JSON", "*.json"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return

        data = load_project(path)
        work_area = data["work_area"]
        material = data["material_profile"]
        profile = MaterialProfile(
            material["name"],
            int(material["power_percent"]),
            int(material["speed_mm_min"]),
            int(material["passes"]),
        )
        self._upsert_profile(profile)

        self.work_width.set(float(work_area["width_mm"]))
        self.work_height.set(float(work_area["height_mm"]))
        self.profile_name.set(profile.name)
        self.power_percent.set(profile.power_percent)
        self.speed_mm_min.set(profile.speed_mm_min)
        self.passes.set(profile.passes)
        self.current_project_path = path

        loaded_gcode = data.get("gcode", "")
        self.imported_paths = data.get("imported_paths", [])
        self.original_imported_paths = self.imported_paths
        self.imported_file = data.get("imported_file")
        self.material_measurement = data.get("material_measurement")
        if self.material_measurement:
            self.material_point_a = tuple(self.material_measurement["point_a"])
            self.material_point_b = tuple(self.material_measurement["point_b"])
            self._update_material_measurement_label()
        svg_placement = data.get("svg_placement")
        if svg_placement:
            self.svg_placement_mode.set(svg_placement.get("mode", "Automatisch"))
            self.svg_margin.set(float(svg_placement.get("margin", 5.0)))
            self.svg_manual_width.set(float(svg_placement.get("manual_width", 50.0)))
            self.svg_offset_x.set(float(svg_placement.get("offset_x", 0.0)))
            self.svg_offset_y.set(float(svg_placement.get("offset_y", 0.0)))
        self.gcode.set(loaded_gcode)
        if hasattr(self, "gcode_text"):
            self.gcode_text.delete("1.0", "end")
            self.gcode_text.insert("1.0", loaded_gcode)
        self._draw_preview()
        self.log(f"Projekt geladen: {path}")

    def _draw_preview(self) -> None:
        if not hasattr(self, "preview"):
            return

        self.preview.delete("all")
        canvas_width = max(1, self.preview.winfo_width())
        canvas_height = max(1, self.preview.winfo_height())
        margin = 32
        width_mm = max(1.0, self._dimension(self.work_width))
        height_mm = max(1.0, self._dimension(self.work_height))
        scale = min((canvas_width - margin * 2) / width_mm, (canvas_height - margin * 2) / height_mm)
        draw_width = width_mm * scale
        draw_height = height_mm * scale
        left = (canvas_width - draw_width) / 2
        top = (canvas_height - draw_height) / 2
        right = left + draw_width
        bottom = top + draw_height

        self.preview.create_rectangle(left, top, right, bottom, outline="#1f6feb", width=2)
        if self.material_measurement:
            self.preview.create_rectangle(left, top, right, bottom, outline="#1f9d55", width=3)
        if self.imported_paths:
            for polyline in self.imported_paths:
                if len(polyline) < 2:
                    continue
                coords = []
                for x, y in polyline:
                    coords.extend([left + x * scale, top + y * scale])
                self.preview.create_line(*coords, fill="#d93025", width=2)
        self.preview.create_line(left, bottom, right, bottom, fill="#333333")
        self.preview.create_line(left, top, left, bottom, fill="#333333")
        self.preview.create_text(left, bottom + 16, anchor="w", text="X0 Y0")
        self.preview.create_text(right, top - 12, anchor="e", text=f"{width_mm:.0f} x {height_mm:.0f} mm")

    def _selected_profile(self) -> MaterialProfile:
        selected = self.profile_name.get()
        return next(profile for profile in self.material_profiles if profile.name == selected)

    def _upsert_profile(self, profile: MaterialProfile) -> None:
        for index, existing in enumerate(self.material_profiles):
            if existing.name == profile.name:
                self.material_profiles[index] = profile
                break
        else:
            self.material_profiles.append(profile)
        if hasattr(self, "profile_combo"):
            self.profile_combo.configure(values=[item.name for item in self.material_profiles])

    def _dimension(self, value: tk.DoubleVar) -> float:
        try:
            return value.get()
        except tk.TclError:
            return 1.0

    def _int_value(self, value: tk.IntVar, fallback: int) -> int:
        try:
            return value.get()
        except tk.TclError:
            return fallback

    def _capture_material_point(self, point_index: int) -> None:
        controller = self._current_controller()

        def capture() -> None:
            x, y = controller.current_position()
            self.ui_queue.put(("material_point", point_index, x, y))

        self._run_worker(capture)

    def _apply_material_measurement(self) -> None:
        if self.material_point_a is None or self.material_point_b is None:
            self.log("Bitte zuerst Ecke 1 und Ecke 2 setzen.")
            return

        ax, ay = self.material_point_a
        bx, by = self.material_point_b
        width = abs(bx - ax)
        height = abs(by - ay)
        if width <= 0 or height <= 0:
            self.log("Einmessung ungueltig: Breite und Hoehe muessen groesser als 0 sein.")
            return

        self.work_width.set(round(width, 2))
        self.work_height.set(round(height, 2))
        self.material_measurement = {
            "point_a": [ax, ay],
            "point_b": [bx, by],
            "width_mm": width,
            "height_mm": height,
        }
        self.material_db_width.set(round(width, 2))
        self.material_db_height.set(round(height, 2))
        self._update_material_measurement_label()
        self._apply_svg_placement(refresh=False)
        self._settings_changed()
        self.log(f"Materialgroesse uebernommen: {width:.1f} x {height:.1f} mm.")

    def _update_material_measurement_label(self) -> None:
        if not self.material_measurement:
            self.material_measurement_label.set("Nicht eingemessen")
            return
        self.material_measurement_label.set(
            f"{self.material_measurement['width_mm']:.1f} x {self.material_measurement['height_mm']:.1f} mm"
        )

    def _save_measured_material(self) -> None:
        name = self.material_db_name.get().strip()
        if not name:
            self.log("Bitte einen Namen fuer das Material eingeben.")
            return
        width = self._dimension(self.material_db_width)
        height = self._dimension(self.material_db_height)
        if width <= 0 or height <= 0:
            self.log("Bitte gueltige Materialmasse eingeben.")
            return

        point_a = self.material_measurement["point_a"] if self.material_measurement else [0.0, 0.0]
        point_b = self.material_measurement["point_b"] if self.material_measurement else [width, height]

        record = {
            "name": name,
            "width_mm": width,
            "height_mm": height,
            "point_a": point_a,
            "point_b": point_b,
        }
        self.material_db_records = upsert_material(record)
        self.material_measurement = {
            "point_a": point_a,
            "point_b": point_b,
            "width_mm": width,
            "height_mm": height,
        }
        self._refresh_material_db_combo()
        self.material_db_selection.set(name)
        self._update_material_measurement_label()
        self.log(f"Material gespeichert: {name}")

    def _select_material_record(self) -> None:
        record = find_material(self.material_db_selection.get().strip())
        if not record:
            return
        self.material_db_name.set(record.get("name", ""))
        self.material_db_width.set(round(float(record.get("width_mm", 0.0)), 2))
        self.material_db_height.set(round(float(record.get("height_mm", 0.0)), 2))

    def _load_measured_material(self) -> None:
        name = self.material_db_selection.get().strip()
        if not name:
            self.log("Bitte ein gespeichertes Material auswaehlen.")
            return
        record = find_material(name)
        if not record:
            self.log(f"Material nicht gefunden: {name}")
            return

        self.material_measurement = {
            "point_a": record.get("point_a", [0.0, 0.0]),
            "point_b": record.get("point_b", [record["width_mm"], record["height_mm"]]),
            "width_mm": float(record["width_mm"]),
            "height_mm": float(record["height_mm"]),
        }
        self.material_point_a = tuple(self.material_measurement["point_a"])
        self.material_point_b = tuple(self.material_measurement["point_b"])
        self.work_width.set(round(self.material_measurement["width_mm"], 2))
        self.work_height.set(round(self.material_measurement["height_mm"], 2))
        self.material_db_name.set(name)
        self.material_db_width.set(round(self.material_measurement["width_mm"], 2))
        self.material_db_height.set(round(self.material_measurement["height_mm"], 2))
        self._update_material_measurement_label()
        self._apply_svg_placement(refresh=False)
        self._settings_changed()
        self.log(f"Material geladen: {name}")

    def _refresh_material_db_combo(self) -> None:
        if hasattr(self, "material_db_combo"):
            self.material_db_combo.configure(values=[item.get("name", "") for item in self.material_db_records])

    def _delete_measured_material(self) -> None:
        name = self.material_db_selection.get().strip() or self.material_db_name.get().strip()
        if not name:
            self.log("Bitte ein Material zum Loeschen auswaehlen.")
            return
        if not messagebox.askyesno("Material loeschen", f"Material '{name}' wirklich loeschen?"):
            return
        self.material_db_records = delete_material(name)
        self._refresh_material_db_combo()
        self.material_db_selection.set("")
        self.material_db_name.set("")
        self.material_db_width.set(0.0)
        self.material_db_height.set(0.0)
        self.log(f"Material geloescht: {name}")

    def _apply_svg_placement(self, refresh: bool = True) -> None:
        if not self.original_imported_paths:
            return

        mode = self.svg_placement_mode.get()
        if mode == "Automatisch":
            paths, fitted_width, fitted_height = fit_paths_to_area(
                self.original_imported_paths,
                self._dimension(self.work_width),
                self._dimension(self.work_height),
                self._dimension(self.svg_margin),
            )
            self.imported_paths = paths
            self.svg_manual_width.set(round(fitted_width, 2))
            self.log(f"SVG automatisch eingepasst: {fitted_width:.1f} x {fitted_height:.1f} mm.")
        else:
            paths, fitted_width, fitted_height = scale_paths_to_width(
                self.original_imported_paths,
                max(1.0, self._dimension(self.svg_manual_width)),
                max(0.0, self._dimension(self.svg_offset_x)),
                max(0.0, self._dimension(self.svg_offset_y)),
            )
            self.imported_paths = paths
            self.log(f"SVG manuell platziert: {fitted_width:.1f} x {fitted_height:.1f} mm.")

        if refresh:
            self._settings_changed()

    def _svg_placement_data(self) -> dict:
        return {
            "mode": self.svg_placement_mode.get(),
            "margin": self._dimension(self.svg_margin),
            "manual_width": self._dimension(self.svg_manual_width),
            "offset_x": self._dimension(self.svg_offset_x),
            "offset_y": self._dimension(self.svg_offset_y),
        }

    def _run_controller_action(self, action, allow_while_busy: bool = False) -> None:
        controller = self._current_controller()
        self.selected_serial_port = self.serial_port.get()
        self._run_worker(lambda: action(controller), allow_while_busy=allow_while_busy)

    def _run_worker(self, action, allow_while_busy: bool = False) -> None:
        if self.worker_busy and not allow_while_busy:
            self.log("Bitte warten: Es laeuft bereits eine Aktion.")
            return

        if not allow_while_busy:
            self.worker_busy = True
            self._set_progress("Aktion laeuft", 0, 1)

        def worker() -> None:
            try:
                action()
            except Exception as exc:
                self._threadsafe_log(str(exc))
            finally:
                self.ui_queue.put(("done", allow_while_busy))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _threadsafe_log(self, message: str) -> None:
        self.ui_queue.put(("log", message))

    def _threadsafe_progress(self, label: str, current: int, total: int) -> None:
        self.ui_queue.put(("progress", label, current, total))

    def _poll_worker_events(self) -> None:
        try:
            while True:
                event = self.ui_queue.get_nowait()
                if event[0] == "log":
                    self.log(event[1])
                elif event[0] == "progress":
                    self._set_progress(event[1], event[2], event[3])
                elif event[0] == "material_point":
                    point_index, x, y = event[1], event[2], event[3]
                    if point_index == 1:
                        self.material_point_a = (x, y)
                        self.log(f"Material Ecke 1 gesetzt: X{x:.1f} Y{y:.1f}.")
                    else:
                        self.material_point_b = (x, y)
                        self.log(f"Material Ecke 2 gesetzt: X{x:.1f} Y{y:.1f}.")
                    if self.material_point_a is not None and self.material_point_b is not None:
                        ax, ay = self.material_point_a
                        bx, by = self.material_point_b
                        self.material_measurement = {
                            "point_a": [ax, ay],
                            "point_b": [bx, by],
                            "width_mm": abs(bx - ax),
                            "height_mm": abs(by - ay),
                        }
                        self._update_material_measurement_label()
                elif event[0] == "done":
                    allow_while_busy = event[1]
                    if not allow_while_busy:
                        self.worker_busy = False
                        if self.job_status.get() == "Aktion laeuft":
                            self._set_progress("Bereit", 1, 1)
                    self._sync_connection_indicator()
        except queue.Empty:
            pass
        self.after(100, self._poll_worker_events)

    def _safe(self, action):
        def wrapped() -> None:
            try:
                action()
                self._sync_connection_indicator()
            except Exception as exc:
                self._set_connection_indicator(False)
                self.log(str(exc))

        return wrapped

    def _sync_connection_indicator(self) -> None:
        state = getattr(self.controller, "state", None)
        connected = bool(state and state.connected)
        self._set_connection_indicator(connected)

    def _set_connection_indicator(self, connected: bool) -> None:
        if not hasattr(self, "connection_indicator"):
            return

        color = "#1f9d55" if connected else "#d93025"
        label = "Verbunden" if connected else "Nicht verbunden"
        self.connection_indicator.delete("all")
        self.connection_indicator.create_oval(3, 3, 15, 15, fill=color, outline=color)
        self.connection_label.configure(text=label)

    def _set_progress(self, label: str, current: int, total: int) -> None:
        total = max(1, total)
        percent = max(0.0, min(100.0, current / total * 100))
        self.job_status.set(label)
        self.progress_value.set(percent)
        self.progress_text.set(f"{percent:.0f}%")

    def log(self, message: str) -> None:
        self.status.set(message)
        if hasattr(self, "log_text"):
            self.log_text.insert("end", message + "\n")
            self.log_text.see("end")
