from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox, QTableWidget, QWidget

from laser_control import project_edit_actions as pea
from laser_control.project_edit_actions import (
    ProjectEditActions,
    confirm_new_project,
    confirm_remove_artwork,
    install_delete_shortcut,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _patch_question(monkeypatch, answer):
    calls = []

    def fake(parent, title, text, buttons, default):
        calls.append((title, text, buttons, default))
        return answer

    monkeypatch.setattr(pea.QMessageBox, "question", staticmethod(fake))
    return calls


def test_buttons_have_names_and_emit_signals():
    _app()
    panel = ProjectEditActions()
    panel.show()
    assert panel.new_project_button.objectName() == "projectNewButton"
    assert panel.remove_artwork_button.objectName() == "projectRemoveArtworkButton"
    assert panel.new_project_button.text() == "Neues Projekt"
    assert panel.remove_artwork_button.accessibleName() == "Motiv entfernen"
    assert panel.remove_artwork_button.minimumHeight() >= 32
    fired = []
    panel.new_project_requested.connect(lambda: fired.append("new"))
    panel.remove_artwork_requested.connect(lambda: fired.append("remove"))
    QTest.mouseClick(panel.new_project_button, Qt.MouseButton.LeftButton)
    QTest.mouseClick(panel.remove_artwork_button, Qt.MouseButton.LeftButton)
    assert fired == ["new", "remove"]


def test_remove_state_sets_enabled_and_tooltip():
    _app()
    panel = ProjectEditActions()
    default_tip = panel.remove_artwork_button.toolTip()
    assert "Entf" in default_tip
    panel.set_remove_state(False, "Zuerst ein Motiv auswaehlen.")
    assert not panel.remove_artwork_button.isEnabled()
    assert panel.remove_artwork_button.toolTip() == "Zuerst ein Motiv auswaehlen."
    panel.set_remove_state(True, "ignoriert")
    assert panel.remove_artwork_button.isEnabled()
    assert panel.remove_artwork_button.toolTip() == default_tip


def test_new_project_state_sets_enabled_and_tooltip():
    _app()
    panel = ProjectEditActions()
    default_tip = panel.new_project_button.toolTip()
    panel.set_new_project_state(False, "Job laeuft.")
    assert not panel.new_project_button.isEnabled()
    assert panel.new_project_button.toolTip() == "Job laeuft."
    panel.set_new_project_state(True, "")
    assert panel.new_project_button.isEnabled()
    assert panel.new_project_button.toolTip() == default_tip


def test_confirm_returns_answer_and_defaults_to_no(monkeypatch):
    _app()
    calls = _patch_question(monkeypatch, QMessageBox.StandardButton.Yes)
    assert confirm_remove_artwork(None, "logo.svg", False) is True
    assert confirm_new_project(None, 2, False) is True
    for _title, _text, buttons, default in calls:
        assert default == QMessageBox.StandardButton.No
        assert buttons == QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    _patch_question(monkeypatch, QMessageBox.StandardButton.No)
    assert confirm_remove_artwork(None, "logo.svg", False) is False
    assert confirm_new_project(None, 2, False) is False


def test_confirm_texts(monkeypatch):
    _app()
    calls = _patch_question(monkeypatch, QMessageBox.StandardButton.No)
    confirm_remove_artwork(None, "logo.svg", False)
    confirm_remove_artwork(None, "logo.svg", True)
    confirm_new_project(None, 1, False)
    confirm_new_project(None, 3, True)
    remove_plain, remove_matrix, new_one, new_many = calls
    assert remove_plain[0] == "Motiv entfernen"
    assert '"logo.svg"' in remove_plain[1]
    assert "Originaldatei bleibt erhalten" in remove_plain[1]
    assert "Testmatrix" not in remove_plain[1]
    assert "Testmatrix wird dabei verworfen" in remove_matrix[1]
    assert new_one[0] == "Neues Projekt"
    assert "1 Motiv wird" in new_one[1]
    assert "3 Motive werden" in new_many[1]
    assert "Testmatrix" not in new_one[1]
    assert "Testmatrix" in new_many[1]
    assert "bleiben unveraendert" in new_one[1]


def test_delete_shortcut_fires_only_on_target_widget():
    _app()
    host = QWidget()
    target = QTableWidget(1, 1, host)
    other = QLineEdit(host)
    host.show()
    calls = []
    shortcut = install_delete_shortcut(target, lambda: calls.append(1))
    assert shortcut.context() == Qt.ShortcutContext.WidgetShortcut

    other.setFocus()
    QApplication.processEvents()
    QTest.keyClick(other, Qt.Key.Key_Delete)
    QApplication.processEvents()
    assert calls == []

    target.setFocus()
    QApplication.processEvents()
    QTest.keyClick(target, Qt.Key.Key_Delete)
    QApplication.processEvents()
    assert calls == [1]
    host.close()
