"""Maschinenverbindung, Controller-Wahl, Worker-Threads und Statusanzeigen."""

import threading
from dataclasses import replace
from PySide6.QtWidgets import QDialog, QMessageBox
from laser_control.machine_profile_dialog import MachineProfileDialog
from laser_control.machine_log import MachineLogStatus
from laser_control.machine_profiles import MachineProfile
from laser_control.serial_autodetect import find_laser_port
from laser_control.serial_grbl import list_serial_ports, port_device


class MachineControlMixin:
    """Maschinenverbindung, Controller-Wahl, Worker-Threads und Statusanzeigen.

    Mixin fuer LaserControlWindow; nutzt dessen Widgets und Services ueber self.
    """

    def _switch_controller(self, *_args) -> None:
        self.controller = self.app_controller.switch_controller(self.connection_mode.currentText())
        self.active_connection_mode = self.connection_mode.currentText()
        self._sync_connection_indicator()

    def _current_controller(self):
        if self.active_connection_mode != self.connection_mode.currentText():
            self._switch_controller()
        self.controller = self.app_controller.current_controller(self.connection_mode.currentText())
        return self.controller

    def _refresh_ports(self) -> None:
        ports = list_serial_ports()
        self.serial_port.clear()
        self.serial_port.addItems(ports)
        if ports:
            default_port = getattr(self.machine_profile, "default_port", "")
            index = self._port_index(default_port)
            self.serial_port.setCurrentIndex(index if index >= 0 else 0)
        self.log(f"{len(ports)} COM-Port(s) gefunden." if ports else "Keine COM-Ports gefunden.")

    def _port_index(self, port: str) -> int:
        """Index of a port in the combo box; labels look like 'COM9 - USB Serial'."""
        wanted = port_device(port or "").upper()
        if not wanted:
            return -1
        for index in range(self.serial_port.count()):
            if port_device(self.serial_port.itemText(index)).upper() == wanted:
                return index
        return -1

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

    def _machine_profile_changed(self, profile_id: str) -> None:
        if not self._can_change_machine_profile(profile_id):
            self.machine_panel.set_machine_profiles(
                self.machine_profile_repository.profiles(),
                self.machine_profile_repository.active_profile_id(),
            )
            return
        previous = self.machine_profile
        self.machine_profile = self.machine_profile_repository.set_active_profile(profile_id)
        self._apply_machine_profile(self.machine_profile)
        self.log(f"Maschinenprofil gewechselt: {previous.name} -> {self.machine_profile.name}")
        self.workflow.record_action(
            "Maschinenprofil gewechselt",
            MachineLogStatus.INFO,
            (
                f"profil={self.machine_profile.profile_id}; "
                f"baudrate={self.machine_profile.baudrate}; "
                f"arbeitsbereich={self.machine_profile.work_area_width:.1f}x{self.machine_profile.work_area_height:.1f}; "
                f"homing_required={self.machine_profile.homing_required}"
            ),
        )

    def _edit_machine_profiles(self) -> None:
        raw_state = getattr(self.app_controller.controller, "state", None)
        if getattr(raw_state, "connected", False) or self.app_controller.machine_state.connected:
            self._block_machine_profile_change("__profile_editor__", self.app_controller.machine_state.phase.value)
            return
        dialog = MachineProfileDialog(
            self.machine_profile_repository.profiles(),
            self.machine_profile_repository.active_profile_id(),
            self._log_profile_validation_failed,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.saved_profile is None:
            return

        profile = dialog.saved_profile
        try:
            self.machine_profile_repository.upsert_profile(profile)
            self.machine_profile = self.machine_profile_repository.set_active_profile(profile.profile_id)
        except ValueError as exc:
            message = str(exc)
            self._log_profile_validation_failed(message)
            QMessageBox.warning(self, "Profil konnte nicht gespeichert werden", message)
            return

        self.machine_panel.set_machine_profiles(
            self.machine_profile_repository.profiles(),
            self.machine_profile_repository.active_profile_id(),
        )
        self._apply_machine_profile(self.machine_profile)
        action = "Maschinenprofil erstellt" if dialog.is_new_profile else "Maschinenprofil bearbeitet"
        self.log(f"{action}: {self.machine_profile.name}")
        self.workflow.record_action(
            action,
            MachineLogStatus.OK,
            (
                f"profil={self.machine_profile.profile_id}; "
                f"baudrate={self.machine_profile.baudrate}; "
                f"homing_required={self.machine_profile.homing_required}"
            ),
        )

    def _log_profile_validation_failed(self, message: str) -> None:
        self.log(f"Maschinenprofil ungueltig: {message}")
        self.workflow.record_action("Maschinenprofil ungueltig", MachineLogStatus.ERROR, message)

    def _can_change_machine_profile(self, requested_profile_id: str) -> bool:
        current_id = self.machine_profile_repository.active_profile_id()
        if requested_profile_id == current_id:
            return True
        raw_state = getattr(self.app_controller.controller, "state", None)
        if getattr(raw_state, "connected", False):
            return self._block_machine_profile_change(requested_profile_id, self.app_controller.machine_state.phase.value)
        self.app_controller.sync_from_controller()
        state = self.app_controller.machine_state
        if state.connected:
            return self._block_machine_profile_change(requested_profile_id, state.phase.value)
        return True

    def _block_machine_profile_change(self, requested_profile_id: str, phase: str) -> bool:
        message = (
            "Maschinenprofilwechsel ist nur im getrennten Zustand erlaubt. "
            "Bitte Verbindung trennen, Profil wechseln und neu verbinden."
        )
        self.log(message)
        self.workflow.record_action(
            "Maschinenprofilwechsel blockiert",
            MachineLogStatus.WARNING,
            f"profil={requested_profile_id}; zustand={phase}; ergebnis=blockiert",
        )
        QMessageBox.warning(self, "Profilwechsel blockiert", message)
        return False

    def _apply_machine_profile(self, profile: MachineProfile) -> None:
        self.app_controller.set_machine_profile(profile)
        if hasattr(self, "connection_mode"):
            self.connection_mode.setCurrentText(profile.controller_type)
        if hasattr(self, "work_width"):
            self.work_width.setValue(profile.work_area_width)
            self.work_height.setValue(profile.work_area_height)
        if profile.default_port and hasattr(self, "serial_port"):
            index = self._port_index(profile.default_port)
            if index >= 0:
                self.serial_port.setCurrentIndex(index)
        self._refresh_gcode()
        self._draw_preview()
        self._update_material_summary()
        self._update_workflow_status()

    def _query_status(self) -> None:
        controller = self._current_controller()
        self._run_worker(lambda: self.app_controller.get_status() if hasattr(controller, "get_status") else None)

    def _query_settings(self) -> None:
        controller = self._current_controller()
        if hasattr(controller, "query_settings"):
            self._run_worker(lambda: self.workflow.run_machine_action("GRBL Settings", self.app_controller.query_settings))
        else:
            self.log("GRBL Settings nur im USB-Modus verfuegbar.")

    def _trigger_machine_action(self, action_id: str, source: str = "UI") -> None:
        definition = self.machine_action_registry.get(action_id)
        details = f"action_id={definition.action_id}; quelle={source}"
        if definition.machine_action is not None and not self.app_controller.require_action(
            definition.machine_action,
            definition.label,
        ):
            self.workflow.record_action("Maschinenaktion blockiert", MachineLogStatus.WARNING, f"{details}; ergebnis=blockiert")
            QMessageBox.warning(self, "Aktion blockiert", f"'{definition.label}' ist im aktuellen Maschinenzustand nicht erlaubt.")
            self._sync_connection_indicator()
            return
        try:
            self._dispatch_machine_action(action_id)
            self.workflow.record_action("Maschinenaktion ausgefuehrt", MachineLogStatus.INFO, f"{details}; ergebnis=ausgefuehrt")
        except Exception as exc:  # noqa: BLE001 - user-facing action dispatch
            self.workflow.record_action("Maschinenaktion fehlgeschlagen", MachineLogStatus.ERROR, f"{details}; ergebnis=fehlgeschlagen", str(exc))
            raise

    def _dispatch_machine_action(self, action_id: str) -> None:
        if action_id == "connect":
            self._run_worker(lambda: self.workflow.run_machine_action("Verbindung herstellen", self.app_controller.connect))
        elif action_id == "disconnect":
            self._run_worker(
                lambda: self.workflow.run_machine_action("Verbindung trennen", self.app_controller.disconnect),
                allow_while_busy=True,
            )
        elif action_id == "refresh_ports":
            self._refresh_ports()
        elif action_id == "detect_laser":
            self._auto_detect_laser()
        elif action_id == "home":
            self._run_worker(lambda: self.workflow.run_machine_action("Homing", self.app_controller.home))
        elif action_id == "unlock_alarm":
            self._run_worker(lambda: self.workflow.run_machine_action("Alarm entsperren", self.app_controller.unlock_alarm))
        elif action_id == "status":
            self._query_status()
        elif action_id == "settings":
            self._query_settings()
        elif action_id == "toggle_alignment":
            target = bool(getattr(self, "alignment_button", None) and self.alignment_button.isChecked())
            self._run_worker(
                lambda: self.workflow.run_machine_action(
                    "Material ausrichten",
                    lambda: self.app_controller.toggle_alignment_mode(target),
                ),
                allow_while_busy=True,
            )
        elif action_id == "toggle_work_area_trace":
            target = bool(getattr(self, "work_area_trace_button", None) and self.work_area_trace_button.isChecked())
            self._run_worker(
                lambda: self.workflow.run_machine_action(
                    "Arbeitsflaeche abfahren",
                    lambda: self._toggle_work_area_trace_from_ui(target),
                ),
                allow_while_busy=True,
            )
        elif action_id == "jog_y_plus":
            self._run_worker(lambda: self.workflow.run_machine_action("Position setzen Y+", lambda: self.app_controller.jog(0, 10, "Position setzen Y+")))
        elif action_id == "jog_x_minus":
            self._run_worker(lambda: self.workflow.run_machine_action("Position setzen X-", lambda: self.app_controller.jog(-10, 0, "Position setzen X-")))
        elif action_id == "jog_x_plus":
            self._run_worker(lambda: self.workflow.run_machine_action("Position setzen X+", lambda: self.app_controller.jog(10, 0, "Position setzen X+")))
        elif action_id == "jog_y_minus":
            self._run_worker(lambda: self.workflow.run_machine_action("Position setzen Y-", lambda: self.app_controller.jog(0, -10, "Position setzen Y-")))
        elif action_id == "frame":
            self._frame_job()
        elif action_id == "dry_run":
            self._dry_run_job()
        elif action_id == "start_job":
            self._start_job()
        elif action_id == "pause":
            self._run_worker(lambda: self.workflow.run_machine_action("Job pausieren", self.app_controller.pause), allow_while_busy=True)
        elif action_id == "resume":
            self._run_worker(lambda: self.workflow.run_machine_action("Job fortsetzen", self.app_controller.resume), allow_while_busy=True)
        elif action_id == "stop":
            self._run_worker(
                lambda: self.workflow.run_machine_action("Job stoppen", self.app_controller.stop),
                allow_while_busy=True,
            )
        elif action_id == "emergency_stop":
            self._run_worker(
                lambda: self.workflow.run_machine_action("Sicherheitsstopp", self.app_controller.emergency_stop),
                allow_while_busy=True,
            )
        else:
            raise RuntimeError(f"Unbekannte Maschinenaktion: {action_id}")

    def _run_worker(self, action, allow_while_busy: bool = False) -> None:
        if self._closing:
            self.log("App wird beendet; keine neue Maschinenaktion gestartet.")
            return
        if self.worker_busy and not allow_while_busy:
            self.log("Bitte warten, bis die aktuelle Aktion abgeschlossen ist.")
            return
        counted_worker = not allow_while_busy
        if counted_worker:
            self.worker_busy = True
            # Projektaenderungen sofort sperren, nicht erst beim naechsten Phasenwechsel.
            if hasattr(self, "project_edit_actions"):
                self._sync_project_edit_actions()
            self._set_progress("Laeuft", 0, 1)

        def target() -> None:
            try:
                action()
            except Exception as exc:  # noqa: BLE001 - report worker failures to UI
                self.signals.error.emit(str(exc))
            finally:
                self.signals.finished.emit(counted_worker)

        thread = threading.Thread(target=target, daemon=True)
        self._worker_threads.append(thread)
        thread.start()

    def _threadsafe_log(self, message: str) -> None:
        self.signals.log.emit(message)

    def _threadsafe_progress(self, label: str, current: int, total: int) -> None:
        self.signals.progress.emit(label, current, total)

    def _show_worker_error(self, message: str) -> None:
        self.log(message)
        QMessageBox.critical(self, "Fehler", message)

    def _worker_finished(self, counted_worker: bool) -> None:
        if counted_worker:
            self.worker_busy = False
        self._worker_threads = [thread for thread in self._worker_threads if thread.is_alive()]
        self._sync_connection_indicator()

    def _sync_connection_indicator(self) -> None:
        if hasattr(self, "app_controller"):
            self.app_controller.sync_from_controller()
            if hasattr(self, "status_panel"):
                self.status_panel.update_machine_state(
                    self.app_controller.machine_state,
                    self.machine_profile.name if hasattr(self, "machine_profile") else "",
                    self.serial_port.currentText() if hasattr(self, "serial_port") else "",
                    self.app_controller.machine_state.message if self.app_controller.machine_state.phase.value in {"alarm", "error"} else "",
                    self.app_controller.job_controller.status,
                )
            self._sync_machine_action_buttons()
            if hasattr(self, "machine_panel"):
                self.machine_panel.update_state(self.app_controller.machine_state)
                self._update_workflow_status()
                self._update_assistant_panel()
                return
        state = getattr(self.controller, "state", None)
        self._set_connection_indicator(bool(state and state.connected))

    def _sync_machine_action_buttons(self) -> None:
        if not hasattr(self, "machine_action_registry"):
            return
        state = self.app_controller.machine_state
        has_motif = self._has_loaded_motif() if hasattr(self, "laser_project") else False
        for action_id, buttons in self.action_buttons.items():
            enabled = self.machine_action_registry.is_enabled(action_id, state)
            if action_id in {"frame", "dry_run", "start_job"} and not has_motif:
                enabled = False
            definition = self.machine_action_registry.get(action_id)
            for button in buttons:
                button.setEnabled(enabled)
                if action_id in {"frame", "dry_run", "start_job"} and not has_motif:
                    button.setToolTip(f"{definition.tooltip} Motiv importieren, bevor diese Aktion verfuegbar ist.")
                else:
                    button.setToolTip(definition.tooltip)
        self._sync_alignment_indicator()
        self._sync_work_area_trace_indicator()
        if hasattr(self, "project_edit_actions"):
            self._sync_project_edit_actions()

    def _alignment_power_changed(self, value: int) -> None:
        if not hasattr(self, "app_controller"):
            return
        if self.app_controller.is_alignment_mode_active():
            self._run_worker(lambda: self.app_controller.set_alignment_pointer_power(value), allow_while_busy=True)
        else:
            self.app_controller.set_alignment_pointer_power(value)
            self._sync_alignment_indicator()

    def _sync_alignment_indicator(self) -> None:
        if not hasattr(self, "alignment_status") or not hasattr(self, "app_controller"):
            return
        active = self.app_controller.is_alignment_mode_active()
        power = self.app_controller.alignment_controller.pointer_power_percent
        self.alignment_status.setText(
            f"Ausrichtmodus aktiv - Laserpunkt aktiv, niedrige Leistung {power}%."
            if active
            else "Ausrichtmodus aus"
        )
        self.alignment_status.setStyleSheet("color: #d93025; font-weight: 700;" if active else "color: #777777;")
        if hasattr(self, "alignment_button"):
            self.alignment_button.blockSignals(True)
            self.alignment_button.setChecked(active)
            self.alignment_button.setText("Ausrichtmodus ausschalten" if active else "Material ausrichten")
            self.alignment_button.blockSignals(False)
        if hasattr(self, "alignment_power") and self.alignment_power.value() != power:
            self.alignment_power.blockSignals(True)
            self.alignment_power.setValue(power)
            self.alignment_power.blockSignals(False)

    def _sync_work_area_trace_indicator(self) -> None:
        if not hasattr(self, "work_area_trace_status") or not hasattr(self, "app_controller"):
            return
        active = self.app_controller.is_work_area_trace_active()
        if hasattr(self, "workspace_scan_panel"):
            self.workspace_scan_panel.set_active(active)
            return
        if hasattr(self, "work_area_trace_button"):
            self.work_area_trace_button.blockSignals(True)
            self.work_area_trace_button.setChecked(active)
            self.work_area_trace_button.setText("Arbeitsflaeche stoppen" if active else "Arbeitsflaeche abfahren")
            self.work_area_trace_button.blockSignals(False)

    def _toggle_work_area_trace_from_ui(self, enabled: bool) -> None:
        self.app_controller.set_current_workspace(self.work_width.value(), self.work_height.value())
        self.app_controller.set_work_area_trace_power(5)
        self.app_controller.toggle_work_area_trace(enabled)

    def _test_alignment_pointer(self) -> None:
        if not hasattr(self, "app_controller"):
            return
        self._run_worker(
            lambda: self.workflow.run_machine_action(
                "Ausrichtlaser Testmodus",
                lambda: self.app_controller.test_alignment_pointer(self.alignment_power.value(), 2.0),
            ),
            allow_while_busy=True,
        )

    def _sync_position_indicator(self) -> None:
        controller_state = getattr(getattr(self, "app_controller", None).controller, "state", None)
        if controller_state is None or not hasattr(self, "status_panel"):
            return
        state = self.app_controller.machine_state
        self._sync_action_buttons_on_state_change(state)
        if getattr(controller_state, "position_source", ""):
            state.x_mm = getattr(controller_state, "x_mm", None)
            state.y_mm = getattr(controller_state, "y_mm", None)
            state.z_mm = getattr(controller_state, "z_mm", None)
            state.position_source = getattr(controller_state, "position_source", "")
            state.feed_rate = getattr(controller_state, "feed_rate", None)
            state.spindle_value = getattr(controller_state, "spindle_value", None)
        self.status_panel.update_machine_state(
            state,
            self.machine_profile.name if hasattr(self, "machine_profile") else "",
            self.serial_port.currentText() if hasattr(self, "serial_port") else "",
            job_state=self.app_controller.job_controller.status,
        )
        if hasattr(self, "preview"):
            self.preview.preview_model = replace(
                self.preview.preview_model,
                head_position=self._preview_head_position(),
                options=self._preview_options(),
            )
            self.preview.update()

    def _sync_action_buttons_on_state_change(self, state) -> None:
        """Refresh action buttons when a worker thread changed the machine state.

        Workers switch e.g. Idle -> Running while a job streams; without this, Pause/Stop would
        stay disabled until the worker finishes.
        """
        signature = (state.phase, state.alignment_mode_active, state.work_area_trace_active)
        if signature == getattr(self, "_last_action_button_state", None):
            return
        self._last_action_button_state = signature
        self._sync_machine_action_buttons()
        if hasattr(self, "machine_panel"):
            self.machine_panel.update_state(state)

    def _set_connection_indicator(self, connected: bool) -> None:
        self.connection_label.setText("Verbunden" if connected else "Nicht verbunden")
        color = "#188038" if connected else "#d93025"
        self.connection_label.setStyleSheet(f"color: {color}; font-weight: 600;")

    def _set_progress(self, label: str, current: int, total: int) -> None:
        self.status_panel.set_progress(label, current, total)
        if hasattr(self, "app_controller") and not self._closing:
            self._sync_position_indicator()
