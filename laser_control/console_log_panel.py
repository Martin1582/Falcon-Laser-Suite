from __future__ import annotations

from PySide6.QtWidgets import QGroupBox, QTextEdit, QVBoxLayout


class ConsoleLogPanel(QGroupBox):
    def __init__(self) -> None:
        super().__init__("Log")
        layout = QVBoxLayout(self)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(120)
        self.log_text.setMaximumHeight(180)
        self.log_text.setStyleSheet("font-family: Consolas, monospace; font-size: 10pt;")
        layout.addWidget(self.log_text)

    def append(self, message: str) -> None:
        self.log_text.append(message)

