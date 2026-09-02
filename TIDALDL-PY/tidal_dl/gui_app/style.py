"""Design tokens and the application stylesheet for the Tidekeeper desktop GUI.

Everything visual is derived from ``TOKENS`` so the stylesheet, delegates and
the application palette agree. Object names referenced here are set by the
helpers in :mod:`tidal_dl.gui_app.widgets`.

Scales
------
Type      11 eyebrow / 12 meta / 13 body / 14 panel title / 15 wordmark / 22 code
Spacing   4 / 8 / 12 / 16
Radius    4 controls / 6 panels
Controls  30px tall, table rows 30px, header 40px, inspector 380px
"""

TOKENS = {
    # Surfaces (deep water -> shallow)
    "bg": "#0c1219",
    "surface": "#121a24",
    "surface_alt": "#182230",
    "surface_hover": "#1e2a3a",
    "surface_pressed": "#243244",
    "border": "#223041",
    "border_strong": "#33455a",
    # Text
    "text": "#e7edf3",
    "text_secondary": "#b3c0cd",
    "muted": "#7d8da0",
    "disabled": "#506072",
    # Brand: tide teal
    "accent": "#37d2b8",
    "accent_hover": "#63dfca",
    "accent_pressed": "#23b39b",
    "accent_soft": "#17362f",
    "accent_dim": "#1f8f7d",
    "on_accent": "#06201b",
    # Semantic
    "success": "#4ccb8f",
    "success_soft": "#143327",
    "warning": "#f2b544",
    "warning_soft": "#3a2d12",
    "danger": "#f26d66",
    "danger_soft": "#3c1d1e",
    "info": "#7db2ff",
}

FONT_UI = '"Segoe UI", "Inter", "SF Pro Text", "Noto Sans", "Ubuntu", "Cantarell", sans-serif'
FONT_MONO = '"JetBrains Mono", "Cascadia Mono", "SF Mono", "Menlo", "Consolas", "DejaVu Sans Mono", monospace'

STATE_COLORS = {
    "queued": TOKENS["muted"],
    "active": TOKENS["accent"],
    "done": TOKENS["success"],
    "failed": TOKENS["danger"],
    "cancelled": TOKENS["warning"],
}

APP_STYLESHEET = """
* {
    font-family: %(font_ui)s;
    font-size: 13px;
}

QMainWindow, QWidget#Root, QWidget#Workspace {
    background: %(bg)s;
    color: %(text)s;
}

QToolTip {
    background: %(surface_hover)s;
    color: %(text)s;
    border: 1px solid %(border_strong)s;
    padding: 5px 8px;
    border-radius: 4px;
}

/* ----------------------------------------------------------------- header */

QFrame#Header {
    background: %(surface)s;
    border: none;
    border-bottom: 1px solid %(border)s;
}

QLabel#Wordmark {
    color: %(text)s;
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 0.3px;
}

QPushButton#HeaderToggle {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    color: %(text_secondary)s;
    min-height: 28px;
    padding: 0 10px;
    font-weight: 600;
}

QPushButton#HeaderToggle:hover {
    background: %(surface_hover)s;
    color: %(text)s;
}

QPushButton#HeaderToggle:checked {
    background: %(surface_alt)s;
    border-color: %(border_strong)s;
    color: %(text)s;
}

QPushButton#HeaderToggle:focus {
    border-color: %(accent)s;
}

/* ----------------------------------------------------------------- panels */

QFrame#Panel {
    background: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
}

QFrame#PanelHeader {
    background: transparent;
    border-bottom: 1px solid %(border)s;
}

QFrame#PanelFooter {
    background: transparent;
    border-top: 1px solid %(border)s;
}

QLabel#PanelTitle {
    color: %(text)s;
    font-size: 14px;
    font-weight: 600;
}

QLabel#Eyebrow {
    color: %(muted)s;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.9px;
}

QFrame#Rule {
    background: %(border)s;
    border: none;
    max-height: 1px;
    min-height: 1px;
}

QLabel#Meta, QLabel#Hint {
    color: %(muted)s;
    font-size: 12px;
}

QLabel#Muted {
    color: %(muted)s;
}

QLabel#FieldLabel {
    color: %(text_secondary)s;
}

QLabel#Mono {
    font-family: %(font_mono)s;
    font-size: 12px;
    color: %(text_secondary)s;
}

QLabel#Code {
    font-family: %(font_mono)s;
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 3px;
    color: %(accent)s;
    background: %(accent_soft)s;
    border: 1px solid %(accent_dim)s;
    border-radius: 4px;
    padding: 8px 12px;
}

QLabel#EmptyOverlay {
    color: %(muted)s;
    background: transparent;
    font-size: 13px;
}

/* -------------------------------------------------------------- inspector */

QFrame#Inspector {
    background: %(surface)s;
    border: none;
    border-left: 1px solid %(border)s;
}

QFrame#InspectorHeader {
    border-bottom: 1px solid %(border)s;
}

QScrollArea#Scroll, QWidget#ScrollContent {
    background: transparent;
    border: none;
}

/* ----------------------------------------------------------------- inputs */

QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QAbstractSpinBox {
    background: %(surface_alt)s;
    border: 1px solid %(border_strong)s;
    border-radius: 4px;
    color: %(text)s;
    placeholder-text-color: %(muted)s;
    min-height: 28px;
    padding: 0 8px;
    selection-background-color: %(accent_dim)s;
    selection-color: %(text)s;
}

QTextEdit, QPlainTextEdit {
    padding: 6px 8px;
}

QLineEdit:hover, QComboBox:hover, QTextEdit:hover, QAbstractSpinBox:hover {
    border-color: %(muted)s;
}

QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus, QAbstractSpinBox:focus {
    border-color: %(accent)s;
}

QLineEdit:read-only {
    color: %(text_secondary)s;
}

QLineEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled, QTextEdit:disabled {
    background: %(surface)s;
    border-color: %(border)s;
    color: %(disabled)s;
}

QLineEdit#Mono, QTextEdit#Mono {
    font-family: %(font_mono)s;
    font-size: 12px;
}

QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
    background: transparent;
    border: none;
    width: 16px;
}

QTextEdit#Log {
    background: %(bg)s;
    border: none;
    border-top: 1px solid %(border)s;
    border-radius: 0;
    font-family: %(font_mono)s;
    font-size: 12px;
    color: %(text_secondary)s;
}

QTextEdit#LinksInput {
    font-family: %(font_mono)s;
    font-size: 12px;
}

QComboBox::drop-down {
    border: none;
    width: 22px;
}

QComboBox QAbstractItemView {
    background: %(surface_alt)s;
    border: 1px solid %(border_strong)s;
    border-radius: 4px;
    color: %(text)s;
    outline: 0;
    padding: 4px;
    selection-background-color: %(accent_soft)s;
    selection-color: %(text)s;
}

QComboBox QAbstractItemView::item {
    min-height: 26px;
    padding: 4px 8px;
    border-radius: 3px;
}

QComboBox QAbstractItemView::item:hover,
QComboBox QAbstractItemView::item:selected {
    background: %(accent_soft)s;
    color: %(text)s;
}

QCheckBox {
    color: %(text)s;
    spacing: 8px;
    padding: 2px 0;
}

QCheckBox:disabled {
    color: %(disabled)s;
}

/* ---------------------------------------------------------------- buttons */

QPushButton {
    background: %(surface_alt)s;
    border: 1px solid %(border_strong)s;
    border-radius: 4px;
    color: %(text)s;
    min-height: 28px;
    padding: 0 12px;
    font-weight: 600;
}

QPushButton:hover {
    background: %(surface_hover)s;
    border-color: %(muted)s;
}

QPushButton:pressed {
    background: %(surface_pressed)s;
}

QPushButton:focus {
    border-color: %(accent)s;
}

QPushButton:disabled {
    background: %(surface)s;
    border-color: %(border)s;
    color: %(disabled)s;
}

QPushButton#Primary {
    background: %(accent)s;
    border-color: %(accent)s;
    color: %(on_accent)s;
}

QPushButton#Primary:hover {
    background: %(accent_hover)s;
    border-color: %(accent_hover)s;
}

QPushButton#Primary:pressed {
    background: %(accent_pressed)s;
    border-color: %(accent_pressed)s;
}

QPushButton#Primary:focus {
    border-color: %(text)s;
}

QPushButton#Primary:disabled {
    background: %(accent_soft)s;
    border-color: %(accent_soft)s;
    color: %(disabled)s;
}

QPushButton#Ghost {
    background: transparent;
    border-color: transparent;
    color: %(text_secondary)s;
}

QPushButton#Ghost:hover {
    background: %(surface_hover)s;
    border-color: transparent;
    color: %(text)s;
}

QPushButton#Ghost:checked {
    background: %(surface_alt)s;
    border-color: %(border_strong)s;
    color: %(text)s;
}

QPushButton#Ghost:focus {
    border-color: %(accent)s;
}

QPushButton#Ghost:disabled {
    background: transparent;
    border-color: transparent;
    color: %(disabled)s;
}

QPushButton#Danger {
    background: transparent;
    border-color: %(border_strong)s;
    color: %(danger)s;
}

QPushButton#Danger:hover {
    background: %(danger_soft)s;
    border-color: %(danger)s;
}

QPushButton#Danger:disabled {
    background: transparent;
    border-color: %(border)s;
    color: %(disabled)s;
}

QPushButton#IconButton {
    background: transparent;
    border-color: transparent;
    color: %(muted)s;
    min-width: 28px;
    max-width: 28px;
    padding: 0;
    font-size: 15px;
    font-weight: 400;
}

QPushButton#IconButton:hover {
    background: %(surface_hover)s;
    color: %(text)s;
}

QFrame#Segmented {
    background: %(surface_alt)s;
    border: 1px solid %(border_strong)s;
    border-radius: 4px;
}

QPushButton#Segment {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    color: %(muted)s;
    min-height: 22px;
    padding: 0 12px;
}

QPushButton#Segment:hover {
    color: %(text)s;
}

QPushButton#Segment:checked {
    background: %(surface_pressed)s;
    color: %(text)s;
}

QPushButton#Segment:focus {
    border-color: %(accent)s;
}

/* ----------------------------------------------------------------- tables */

QTableWidget {
    background: %(surface)s;
    alternate-background-color: %(surface_alt)s;
    border: none;
    gridline-color: transparent;
    color: %(text)s;
    selection-background-color: %(accent_soft)s;
    selection-color: %(text)s;
    outline: 0;
}

QTableWidget::item {
    background: transparent;
    color: %(text)s;
    padding: 0 8px;
    border: none;
}

QTableWidget::item:selected {
    background: %(accent_soft)s;
    color: %(text)s;
}

QHeaderView {
    background: transparent;
}

QHeaderView::section {
    background: %(surface)s;
    border: none;
    border-bottom: 1px solid %(border)s;
    color: %(muted)s;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
    padding: 6px 8px;
}

QHeaderView::section:hover {
    color: %(text_secondary)s;
}

QTableCornerButton::section {
    background: %(surface)s;
    border: none;
}

/* -------------------------------------------------------------- scrolling */

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background: %(border_strong)s;
    border-radius: 3px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background: %(muted)s;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
    height: 0;
}

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}

QScrollBar::handle:horizontal {
    background: %(border_strong)s;
    border-radius: 3px;
    min-width: 24px;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
    width: 0;
}

QSplitter::handle {
    background: transparent;
}

QSplitter::handle:vertical {
    height: 8px;
}

QSplitter::handle:hover {
    background: %(accent_soft)s;
}

/* ------------------------------------------------------------------- misc */

QMenu {
    background: %(surface_alt)s;
    color: %(text)s;
    border: 1px solid %(border_strong)s;
    border-radius: 4px;
    padding: 4px;
}

QMenu::item {
    padding: 5px 12px;
    border-radius: 3px;
}

QMenu::item:selected {
    background: %(accent_soft)s;
}

QMessageBox {
    background: %(surface)s;
}
""" % {**TOKENS, "font_ui": FONT_UI, "font_mono": FONT_MONO}
