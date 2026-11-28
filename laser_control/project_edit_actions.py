"""Projektbearbeitung: Buttons, Bestaetigungsdialoge und Entf-Shortcut (ohne Fachlogik)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QPushButton, QSizePolicy, QWidget

NEW_PROJECT_TOOLTIP = "Aktuelles Projekt verwerfen und ein neues Projekt beginnen."
REMOVE_ARTWORK_TOOLTIP = "Ausgewaehltes Motiv aus dem Projekt entfernen (Taste: Entf)."
MATRIX_DISCARD_NOTE = "Die erzeugte Testmatrix wird dabei verworfen."


class ProjectEditActions(QWidget):
    """Zeile mit den Buttons "Neues Projekt" und "Motiv entfernen"."""

    new_project_requested = Signal()
    remove_artwork_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.new_project_button = self._make_button(
            "Neues Projekt", "projectNewButton", NEW_PROJECT_TOOLTIP
        )
        self.remove_artwork_button = self._make_button(
            "Motiv entfernen", "projectRemoveArtworkButton", REMOVE_ARTWORK_TOOLTIP
        )
        self.new_project_button.clicked.connect(self.new_project_requested)
        self.remove_artwork_button.clicked.connect(self.remove_artwork_requested)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.new_project_button)
        layout.addWidget(self.remove_artwork_button)
        self.setTabOrder(self.new_project_button, self.remove_artwork_button)

    def set_remove_state(self, enabled: bool, reason: str) -> None:
        self._apply_state(self.remove_artwork_button, enabled, reason, REMOVE_ARTWORK_TOOLTIP)

    def set_new_project_state(self, enabled: bool, reason: str) -> None:
        self._apply_state(self.new_project_button, enabled, reason, NEW_PROJECT_TOOLTIP)

    @staticmethod
    def _apply_state(button: QPushButton, enabled: bool, reason: str, default_tip: str) -> None:
        button.setEnabled(enabled)
        button.setToolTip(default_tip if enabled or not reason else reason)

    @staticmethod
    def _make_button(text: str, object_name: str, tooltip: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(object_name)
        button.setAccessibleName(text)
        button.setToolTip(tooltip)
        button.setMinimumHeight(32)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return button


def _ask_yes_no(parent: QWidget | None, title: str, text: str) -> bool:
    answer = QMessageBox.question(
        parent,
        title,
        text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


def confirm_remove_artwork(parent: QWidget | None, item_name: str, discards_generated_job: bool) -> bool:
    text = (
        f'Motiv "{item_name}" aus dem Projekt entfernen?\n\n'
        "Die Originaldatei bleibt erhalten. "
        "Dieser Schritt kann nicht rueckgaengig gemacht werden."
    )
    if discards_generated_job:
        text += f"\n{MATRIX_DISCARD_NOTE}"
    return _ask_yes_no(parent, "Motiv entfernen", text)


def confirm_new_project(parent: QWidget | None, item_count: int, discards_generated_job: bool) -> bool:
    text = "Aktuelles Projekt verwerfen und ein neues Projekt beginnen?\n\n"
    if item_count == 1:
        text += "1 Motiv wird aus der Arbeitsflaeche entfernt. "
    elif item_count > 1:
        text += f"{item_count} Motive werden aus der Arbeitsflaeche entfernt. "
    text += "Nicht gespeicherte Aenderungen gehen verloren."
    if discards_generated_job:
        text += f"\n{MATRIX_DISCARD_NOTE}"
    text += "\nMaschine, Material- und Maschinenprofile bleiben unveraendert."
    return _ask_yes_no(parent, "Neues Projekt", text)


def install_delete_shortcut(widget: QWidget, handler: Callable[[], None]) -> QShortcut:
    """Entf nur, solange `widget` den Fokus hat (nicht waehrend der Zellbearbeitung)."""
    shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Delete), widget)
    shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
    shortcut.activated.connect(handler)
    return shortcut
