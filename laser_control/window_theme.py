"""Farb-Tokens und Qt-Stylesheet."""

from PySide6.QtGui import QColor


class ThemeMixin:
    """Farb-Tokens und Qt-Stylesheet.

    Mixin fuer LaserControlWindow; nutzt dessen Widgets und Services ueber self.
    """

    def _theme_tokens(self, dark: bool) -> dict[str, str]:
        if dark:
            return {
                "window": "#1b1c1f",
                "sidebar": "#202226",
                "workspace": "#1f2125",
                "panel": "#272a2f",
                "panel_alt": "#2d3036",
                "panel_border": "#464b54",
                "panel_highlight": "#383d45",
                "text": "#f2f3f5",
                "muted": "#aab0b8",
                "disabled_text": "#7d838c",
                "input": "#202329",
                "input_border": "#515762",
                "input_focus": "#6f9be8",
                "button": "#30343b",
                "button_hover": "#383d45",
                "button_pressed": "#262a30",
                "button_border": "#5a606a",
                "button_top": "#6a707a",
                "button_bottom": "#22252a",
                "blue": "#4d8dff",
                "green": "#188038",
                "green_dark": "#126a2e",
                "orange": "#d28a1d",
                "red": "#b3261e",
                "red_text": "#ffdad6",
                "table_grid": "#424750",
                "selection": "#294f82",
                "empty_border": "#5a606a",
            }
        return {
            "window": "#f3f5f8",
            "sidebar": "#e9edf2",
            "workspace": "#f7f8fa",
            "panel": "#ffffff",
            "panel_alt": "#f3f5f8",
            "panel_border": "#c5cbd4",
            "panel_highlight": "#ffffff",
            "text": "#202124",
            "muted": "#5f6670",
            "disabled_text": "#8a9099",
            "input": "#ffffff",
            "input_border": "#c3cad4",
            "input_focus": "#2563eb",
            "button": "#f8fafc",
            "button_hover": "#eef3fb",
            "button_pressed": "#e2e8f0",
            "button_border": "#b8c0cc",
            "button_top": "#ffffff",
            "button_bottom": "#cbd3de",
            "blue": "#2563eb",
            "green": "#188038",
            "green_dark": "#126a2e",
            "orange": "#b06000",
            "red": "#d93025",
            "red_text": "#8b1a10",
            "table_grid": "#d8dde3",
            "selection": "#dbeafe",
            "empty_border": "#c8cdd3",
        }

    def _build_stylesheet(self, tokens: dict[str, str]) -> str:
        return f"""
            QMainWindow {{
                background: {tokens["window"]};
                color: {tokens["text"]};
                font-size: 10pt;
            }}
            QWidget {{
                background: {tokens["workspace"]};
                color: {tokens["text"]};
                selection-background-color: {tokens["selection"]};
            }}
            QDialog {{
                background: {tokens["panel"]};
                border: 1px solid {tokens["panel_highlight"]};
                border-radius: 8px;
            }}
            QFrame#workflowStrip {{
                background: {tokens["panel"]};
                border: 1px solid {tokens["panel_border"]};
                border-top-color: {tokens["panel_highlight"]};
                border-bottom-color: {tokens["button_bottom"]};
                border-radius: 7px;
            }}
            QGroupBox {{
                background: {tokens["panel"]};
                border: 1px solid {tokens["panel_border"]};
                border-top-color: {tokens["panel_highlight"]};
                border-bottom-color: {tokens["button_bottom"]};
                border-radius: 7px;
                margin-top: 13px;
                padding: 12px 9px 9px 9px;
                font-weight: 650;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 11px;
                padding: 0 6px;
                color: {tokens["text"]};
                background: {tokens["workspace"]};
            }}
            QGroupBox#sidebarSection {{
                background: {tokens["panel_alt"]};
                border: 1px solid {tokens["panel_border"]};
                border-left: 2px solid {tokens["panel_highlight"]};
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 14px;
            }}
            QGroupBox#sidebarSection::title {{
                font-size: 13px;
                font-weight: 800;
                left: 10px;
                padding: 0 6px;
                background: {tokens["sidebar"]};
            }}
            QPushButton {{
                background: {tokens["button"]};
                color: {tokens["text"]};
                border: 1px solid {tokens["button_border"]};
                border-top-color: {tokens["button_top"]};
                border-bottom-color: {tokens["button_bottom"]};
                border-radius: 6px;
                padding: 7px 10px;
                min-height: 22px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {tokens["button_hover"]};
                border-color: {tokens["blue"]};
            }}
            QPushButton:pressed {{
                background: {tokens["button_pressed"]};
                border-top-color: {tokens["button_bottom"]};
                border-bottom-color: {tokens["button_top"]};
                padding-top: 8px;
                padding-bottom: 6px;
            }}
            QPushButton:disabled {{
                color: {tokens["disabled_text"]};
                background: {tokens["button_pressed"]};
                border-color: {tokens["panel_border"]};
            }}
            QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QTextEdit {{
                background: {tokens["input"]};
                color: {tokens["text"]};
                border: 1px solid {tokens["input_border"]};
                border-top-color: {tokens["button_bottom"]};
                border-bottom-color: {tokens["panel_highlight"]};
                border-radius: 5px;
                padding: 6px;
                selection-background-color: {tokens["selection"]};
            }}
            QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover, QTextEdit:hover {{
                border-color: {tokens["button_border"]};
            }}
            QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus, QTextEdit:focus {{
                border: 1px solid {tokens["input_focus"]};
            }}
            QComboBox::drop-down {{
                border-left: 1px solid {tokens["panel_border"]};
                width: 22px;
            }}
            QCheckBox {{
                spacing: 8px;
                min-height: 26px;
                color: {tokens["text"]};
            }}
            QCheckBox::indicator {{
                width: 15px;
                height: 15px;
                border: 1px solid {tokens["input_border"]};
                border-radius: 3px;
                background: {tokens["input"]};
            }}
            QCheckBox::indicator:hover {{
                border-color: {tokens["blue"]};
            }}
            QCheckBox::indicator:checked {{
                background: {tokens["blue"]};
                border-color: {tokens["blue"]};
            }}
            QTableWidget {{
                background: {tokens["input"]};
                alternate-background-color: {tokens["panel_alt"]};
                gridline-color: {tokens["table_grid"]};
                border: 1px solid {tokens["panel_border"]};
                border-radius: 6px;
            }}
            QTableWidget::item {{
                padding: 4px;
            }}
            QTableWidget::item:selected {{
                background: {tokens["selection"]};
                color: {tokens["text"]};
                border-left: 2px solid {tokens["blue"]};
            }}
            QHeaderView::section {{
                background: {tokens["panel_alt"]};
                color: {tokens["muted"]};
                border: 0;
                border-bottom: 1px solid {tokens["panel_border"]};
                padding: 5px;
                font-weight: 700;
            }}
            QTabWidget::pane {{
                border: 1px solid {tokens["panel_border"]};
                border-radius: 6px;
                background: {tokens["panel"]};
            }}
            QTabBar::tab {{
                background: {tokens["panel_alt"]};
                border: 1px solid {tokens["panel_border"]};
                padding: 6px 10px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }}
            QTabBar::tab:selected {{
                background: {tokens["panel"]};
                border-bottom-color: {tokens["panel"]};
                color: {tokens["blue"]};
            }}
            QScrollArea {{
                border: 0;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: {tokens["sidebar"]};
                width: 10px;
                margin: 2px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: {tokens["panel_border"]};
                min-height: 28px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {tokens["button_border"]};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QProgressBar {{
                background: {tokens["input"]};
                border: 1px solid {tokens["panel_border"]};
                border-radius: 5px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background: {tokens["blue"]};
                border-radius: 4px;
            }}
            QLabel#machineConnectionStatus {{
                font-size: 13px;
                font-weight: 800;
            }}
            #leftSidebar, #rightSidebar {{
                background: {tokens["sidebar"]};
                border: 1px solid {tokens["panel_border"]};
                border-top-color: {tokens["panel_highlight"]};
                border-radius: 8px;
            }}
            #leftSidebar {{
                border-right: 1px solid {tokens["button_bottom"]};
            }}
            #rightSidebar {{
                border-left: 1px solid {tokens["panel_highlight"]};
            }}
            #workflowHint {{
                color: {tokens["muted"]};
                font-weight: 700;
                letter-spacing: 0px;
            }}
            #workflowStatus, #projectSummary, #materialSummary, #previewPosition {{
                background: {tokens["panel"]};
                color: {tokens["muted"]};
                padding: 7px;
                border: 1px solid {tokens["panel_border"]};
                border-radius: 6px;
            }}
            #jobSummary {{
                background: {tokens["panel_alt"]};
                color: {tokens["text"]};
                font-weight: 700;
                padding: 7px;
                border: 1px solid {tokens["panel_border"]};
                border-left: 2px solid {tokens["blue"]};
                border-radius: 6px;
            }}
            #assistantSummary, #projectEmptyState, #layerEmptyState {{
                color: {tokens["muted"]};
                padding: 7px;
                border: 1px dashed {tokens["empty_border"]};
                border-radius: 6px;
                background: {tokens["panel_alt"]};
            }}
            #machineAction_frame {{
                border-color: {tokens["blue"]};
                font-weight: 700;
            }}
            #machineAction_start_job {{
                background: {tokens["green"]};
                color: #ffffff;
                border-color: {tokens["green_dark"]};
                border-top-color: #35a25b;
                border-bottom-color: #0f5524;
                font-weight: 800;
            }}
            #machineAction_start_job:hover {{
                background: #20924a;
            }}
            #machineAction_start_job:disabled {{
                background: {tokens["button_pressed"]};
                color: {tokens["disabled_text"]};
                border-color: {tokens["panel_border"]};
            }}
            #machineAction_stop {{
                border-color: {tokens["red"]};
                color: {tokens["red_text"]};
                font-weight: 800;
            }}
            #machineAction_emergency_stop {{
                background: {tokens["red"]};
                border-color: {tokens["red_text"]};
                border-bottom-color: #6f1712;
                color: #ffffff;
                font-weight: 900;
            }}
        """

    def _apply_theme(self, dark: bool) -> None:
        self.dark_mode_enabled = dark
        if hasattr(self, "theme_switch"):
            self.theme_switch.setText("Dark" if dark else "Light")
        tokens = self._theme_tokens(dark)
        self.setStyleSheet(self._build_stylesheet(tokens))
        if hasattr(self, "preview"):
            if dark:
                self.preview.background_color = QColor(tokens["window"])
                self.preview.material_surface_color = QColor("#262a30")
                self.preview.material_shadow_color = QColor("#14161a")
                self.preview.grid_color = QColor("#393e46")
                self.preview.border_color = QColor("#777e89")
                self.preview.path_color = QColor("#ff6b5f")
                self.preview.safe_area_color = QColor(tokens["blue"])
                self.preview.origin_color = QColor("#6dd47e")
                self.preview.head_color = QColor(tokens["red"])
                self.preview.head_ring_color = QColor("#f2f3f5")
            else:
                self.preview.background_color = QColor(tokens["workspace"])
                self.preview.material_surface_color = QColor("#ffffff")
                self.preview.material_shadow_color = QColor("#d4dae3")
                self.preview.grid_color = QColor("#dde2ea")
                self.preview.border_color = QColor("#9aa0a6")
                self.preview.path_color = QColor(tokens["red"])
                self.preview.safe_area_color = QColor(tokens["blue"])
                self.preview.origin_color = QColor(tokens["green"])
                self.preview.head_color = QColor(tokens["red"])
                self.preview.head_ring_color = QColor("#ffffff")
            self.preview.update()
