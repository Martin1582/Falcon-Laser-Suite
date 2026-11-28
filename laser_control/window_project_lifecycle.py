"""Motiv entfernen und Neues Projekt: Verdrahtung im Hauptfenster.

Die Projektdaten aendert ausschliesslich der ProjectWorkspace; dieses Mixin sorgt dafuer,
dass Auswahl, Vorschau, G-Code, Preflight und Buttons danach zueinander passen.
"""

from laser_control.machine_state import MachinePhase
from laser_control.project_edit_actions import (
    ProjectEditActions,
    confirm_new_project,
    confirm_remove_artwork,
    install_delete_shortcut,
)

# Waehrend dieser Phasen beschreiben Vorschau, Frame und Job-Ergebnis den laufenden Job;
# eine Projektaenderung wuerde sie von dem trennen, was die Maschine gerade ausfuehrt.
LOCKED_PHASES = frozenset({MachinePhase.RUNNING, MachinePhase.PAUSED, MachinePhase.STOPPING})
NO_SELECTION_REASON = "Zuerst ein Motiv in der Objektliste auswaehlen."
LOCKED_REASON = "Waehrend ein Job oder eine Maschinenaktion laeuft nicht moeglich."
DEFAULT_PARAMETER_SOURCE = "Materialprofil/Default"


class ProjectLifecycleMixin:
    """Mixin fuer LaserControlWindow: Motiv entfernen und Neues Projekt anlegen."""

    def _build_project_edit_controls(self, layout) -> None:
        self.project_edit_actions = ProjectEditActions()
        self.project_edit_actions.remove_artwork_requested.connect(self._remove_selected_artwork)
        self.project_edit_actions.new_project_requested.connect(self._new_project)
        self._delete_artwork_shortcut = install_delete_shortcut(self.object_table, self._remove_selected_artwork)
        layout.addWidget(self.project_edit_actions)
        self._sync_project_edit_actions()

    def _project_edit_locked(self) -> bool:
        if getattr(self, "worker_busy", False):
            return True
        controller = getattr(self, "app_controller", None)
        return controller is not None and controller.machine_state.phase in LOCKED_PHASES

    def _sync_project_edit_actions(self) -> None:
        actions = getattr(self, "project_edit_actions", None)
        if actions is None:
            return
        locked = self._project_edit_locked()
        has_selection = self._selected_artwork_item() is not None
        actions.set_remove_state(has_selection and not locked, LOCKED_REASON if locked else NO_SELECTION_REASON)
        actions.set_new_project_state(not locked, LOCKED_REASON)

    def _clear_selected_artwork_state(self) -> None:
        """Setzt den kompletten Zustand des gewaehlten Motivs zurueck (Projekt bleibt)."""
        self.selected_artwork_item_id = None
        self.artwork_source = None
        self.artwork_transform = None
        self.imported_file = None
        self.imported_paths = []
        self.original_imported_paths = []
        self.raster_sources = []
        self.original_raster_source = None
        self.autofit_result = None
        self.fill_toolpaths = []
        self.svg_analysis = None
        self.svg_optimization_result = None
        self.svg_optimized_paths = []
        self.laser_intelligence_result = None

    def _show_empty_selection_labels(self) -> None:
        if hasattr(self, "svg_size_label"):
            self.svg_size_label.setText("Motiv: keine Datei")
        if hasattr(self, "preview_position_label"):
            self.preview_position_label.setText("Motivposition: --")

    def _remove_selected_artwork(self) -> None:
        item = self._selected_artwork_item()
        if item is None:
            return
        if self._project_edit_locked():
            self.log("Motiv entfernen ist waehrend eines Jobs oder einer Maschinenaktion nicht moeglich.")
            return
        # Q3: wie beim Aktiv-Haekchen erzeugt das Entfernen den G-Code neu und verwirft die Matrix.
        discards_matrix = bool(getattr(self, "_generated_job_name", None))
        if not confirm_remove_artwork(self, item.name, discards_matrix):
            return
        removal = self.project_workspace.remove_item(item.item_id)
        self._select_artwork_item(removal.next_selected_id)
        self._refresh_after_project_change()
        self.log(f"Motiv entfernt: {item.name} ({len(self.laser_project.items)} Motive im Projekt)")
        if discards_matrix:
            self.log("Testmatrix verworfen.")

    def _new_project(self) -> None:
        if self._project_edit_locked():
            self.log("Neues Projekt ist waehrend eines Jobs oder einer Maschinenaktion nicht moeglich.")
            return
        if self._has_loaded_motif():
            discards_matrix = bool(getattr(self, "_generated_job_name", None))
            if not confirm_new_project(self, len(self.laser_project.items), discards_matrix):
                return
        # Q1: Arbeitsbereich, Material, Leistung/Speed/Passes und Modus bleiben (Arbeitsumgebung).
        self.project_workspace.reset(self.work_width.value(), self.work_height.value(), self.profile_name.currentText())
        self._clear_selected_artwork_state()
        self._show_empty_selection_labels()
        self._reset_project_side_state()
        self._restore_svg_placement(self._new_project_placement())
        self._sync_layers_from_controls(preserve_states=False)
        self._refresh_object_table()
        self._refresh_after_project_change()
        self.log("Neues Projekt angelegt.")

    def _new_project_placement(self) -> dict:
        """Startwerte der Platzierung; Materialform und Job-Ursprung bleiben (Q1)."""
        return {
            **self._default_svg_placement,
            "material_shape": self.material_shape.currentText(),
            "job_origin": self.job_origin.currentText(),
        }

    def _reset_project_side_state(self) -> None:
        """Projektzustand ausserhalb des LaserProject: Pfad, Einmessung (Q2), Parameterquelle."""
        self.current_project_path = None
        self.material_measurement = None
        self.material_points = {1: None, 2: None, 3: None, 4: None}
        self.material_point_a = None
        self.material_point_b = None
        self._update_material_measurement_label()
        self._parameter_source = DEFAULT_PARAMETER_SOURCE
        self.last_prepared_job = None

    def _refresh_after_project_change(self) -> None:
        # _refresh_gcode setzt auch _generated_job_name zurueck (Testmatrix verworfen).
        self._refresh_gcode()
        self._draw_preview()
        self._update_assistant_panel()
        self._sync_machine_action_buttons()
