# -*- coding: utf-8 -*-
"""Einheitliches SkyTycoon Dark-Theme — nur Graustufen, keine Gold/Blau/Grün-Akzente."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

# Hintergrund / Rahmen / Text
_SKY_BG = "#121214"
_SKY_BG_ALT = "#1a1a1e"
_SKY_BG_INPUT = "#161618"
_SKY_BORDER = "#3a3a42"
_SKY_BORDER_FOCUS = "#5a5a62"
_SKY_TEXT = "#e8e8ec"
_SKY_TEXT_MUTED = "#a8a8b0"
_SKY_SEL = "#2c2c32"

SKYTYCOON_UNIFIED_DARK_STYLE = f"""
QWidget {{
    background-color: {_SKY_BG};
    color: {_SKY_TEXT};
    selection-background-color: {_SKY_SEL};
    selection-color: {_SKY_TEXT};
}}
QMainWindow, QDialog, QMessageBox {{
    background-color: {_SKY_BG};
    color: {_SKY_TEXT};
}}
QFrame, QGroupBox, QScrollArea, QSplitter, QStackedWidget {{
    background-color: {_SKY_BG_ALT};
    color: {_SKY_TEXT};
    border: 1px solid {_SKY_BORDER};
    border-radius: 6px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 6px;
    color: {_SKY_TEXT_MUTED};
}}
QLabel {{
    color: {_SKY_TEXT};
    background: transparent;
}}
QPushButton {{
    background-color: {_SKY_BG_INPUT};
    color: {_SKY_TEXT};
    border: 1px solid {_SKY_BORDER};
    border-radius: 6px;
    padding: 8px 14px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {_SKY_SEL};
    border-color: {_SKY_BORDER_FOCUS};
}}
QPushButton:pressed {{
    background-color: {_SKY_BG};
}}
QPushButton:disabled {{
    background-color: {_SKY_BG_ALT};
    color: #66666e;
    border-color: #2a2a30;
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit {{
    background-color: {_SKY_BG_INPUT};
    color: {_SKY_TEXT};
    border: 1px solid {_SKY_BORDER};
    border-radius: 4px;
    padding: 5px 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {_SKY_BG_ALT};
    color: {_SKY_TEXT};
    border: 1px solid {_SKY_BORDER};
    selection-background-color: {_SKY_SEL};
}}
QTableView, QTableWidget {{
    background-color: {_SKY_BG};
    alternate-background-color: {_SKY_BG_ALT};
    color: {_SKY_TEXT};
    gridline-color: #2a2a30;
    border: 1px solid {_SKY_BORDER};
}}
QHeaderView::section {{
    background-color: {_SKY_BG_ALT};
    color: {_SKY_TEXT_MUTED};
    border: 1px solid {_SKY_BORDER};
    padding: 6px;
    font-weight: 700;
}}
QTreeView, QListView, QListWidget, QTreeWidget {{
    background-color: {_SKY_BG};
    color: {_SKY_TEXT};
    border: 1px solid {_SKY_BORDER};
    alternate-background-color: {_SKY_BG_ALT};
}}
QTabWidget::pane {{
    border: 1px solid {_SKY_BORDER};
    background: {_SKY_BG};
    top: -1px;
}}
QTabBar::tab {{
    background: {_SKY_BG_ALT};
    color: {_SKY_TEXT_MUTED};
    padding: 8px 16px;
    border: 1px solid {_SKY_BORDER};
    margin: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{
    background: {_SKY_BG};
    color: {_SKY_TEXT};
    border-color: {_SKY_BORDER_FOCUS};
    font-weight: 700;
}}
QTabBar::tab:hover {{
    color: {_SKY_TEXT};
}}
QMenuBar, QStatusBar, QToolBar {{
    background: {_SKY_BG};
    color: {_SKY_TEXT};
    border: none;
}}
QMenu {{
    background: {_SKY_BG_ALT};
    color: {_SKY_TEXT};
    border: 1px solid {_SKY_BORDER};
}}
QMenu::item:selected {{
    background: {_SKY_SEL};
}}
QToolTip {{
    background: {_SKY_BG_ALT};
    color: {_SKY_TEXT};
    border: 1px solid {_SKY_BORDER};
}}
QTextEdit, QPlainTextEdit {{
    background-color: {_SKY_BG_INPUT};
    color: {_SKY_TEXT};
    border: 1px solid {_SKY_BORDER};
}}
QProgressBar {{
    background: {_SKY_BG};
    border: 1px solid {_SKY_BORDER};
    border-radius: 4px;
    text-align: center;
    color: {_SKY_TEXT};
}}
QProgressBar::chunk {{
    background: #6a6a72;
}}
QCheckBox, QRadioButton {{
    color: {_SKY_TEXT};
    spacing: 8px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {_SKY_BORDER};
    background: {_SKY_BG_INPUT};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: #6a6a72;
    border-color: {_SKY_BORDER_FOCUS};
}}
QScrollBar:vertical {{
    background: {_SKY_BG};
    width: 12px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #4a4a52;
    min-height: 24px;
    border-radius: 4px;
}}
QScrollBar:horizontal {{
    background: {_SKY_BG};
    height: 12px;
}}
QScrollBar::handle:horizontal {{
    background: #4a4a52;
    min-width: 24px;
    border-radius: 4px;
}}
"""

MONO_TILE_STYLE = (
    "QFrame#platinTile { background:#1a1a1e; border:1px solid #3a3a42; "
    "border-radius:8px; padding:10px; }"
    "QPushButton#platinBtn { background:#161618; color:#e8e8ec; border:1px solid #3a3a42; "
    "font-weight:600; padding:12px 16px; border-radius:6px; min-height:48px; }"
    "QPushButton#platinBtn:hover { background:#2c2c32; }"
    "QLabel#platinHdr { color:#a8a8b0; font-weight:700; font-size:14px; }"
)

SKY_DARK_SCROLL_CSS = (
    "QScrollArea { background:#121214; border:1px solid #3a3a42; border-radius:6px; }"
)

SKY_DARK_PANEL_STYLE = SKYTYCOON_UNIFIED_DARK_STYLE


def apply_skytycoon_dark_theme(app: QApplication) -> None:
    """Fusion + neutrale Palette + globales Stylesheet für die ganze App."""
    app.setStyle(QStyleFactory.create("Fusion"))
    bg = QColor(18, 18, 20)
    bg_alt = QColor(26, 26, 30)
    fg = QColor(232, 232, 236)
    disabled = QColor(120, 120, 128)
    highlight = QColor(44, 44, 50)
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, bg)
    pal.setColor(QPalette.ColorRole.WindowText, fg)
    pal.setColor(QPalette.ColorRole.Base, QColor(22, 22, 24))
    pal.setColor(QPalette.ColorRole.AlternateBase, bg_alt)
    pal.setColor(QPalette.ColorRole.ToolTipBase, bg_alt)
    pal.setColor(QPalette.ColorRole.ToolTipText, fg)
    pal.setColor(QPalette.ColorRole.Text, fg)
    pal.setColor(QPalette.ColorRole.Button, bg_alt)
    pal.setColor(QPalette.ColorRole.ButtonText, fg)
    pal.setColor(QPalette.ColorRole.BrightText, fg)
    pal.setColor(QPalette.ColorRole.Link, QColor(168, 168, 176))
    pal.setColor(QPalette.ColorRole.Highlight, highlight)
    pal.setColor(QPalette.ColorRole.HighlightedText, fg)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled)
    app.setPalette(pal)
    app.setStyleSheet(SKYTYCOON_UNIFIED_DARK_STYLE)


def apply_skytycoon_dark_theme_to_widget(widget: object) -> None:
    if widget is None:
        return
    try:
        widget.setStyleSheet(SKYTYCOON_UNIFIED_DARK_STYLE)  # type: ignore[attr-defined]
    except (AttributeError, RuntimeError):
        pass
