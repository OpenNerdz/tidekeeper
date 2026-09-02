"""Design tokens and the application stylesheet for the Tidekeeper desktop GUI.

Colours live in ``TOKENS`` so the stylesheet, painters, and palette all agree.
Object names referenced here (``Sidebar``, ``Card``, ``Primary`` ...) are set
by the helpers in :mod:`tidal_dl.gui_app.widgets`.
"""

TOKENS = {
    # Surfaces
    "bg": "#f4f6fa",
    "surface": "#ffffff",
    "surface_alt": "#f8fafc",
    "border": "#e3e8ef",
    "border_strong": "#cbd5e1",
    # Text
    "text": "#0f172a",
    "text_secondary": "#344054",
    "muted": "#64748b",
    "disabled": "#98a2b3",
    # Brand
    "accent": "#0f766e",
    "accent_hover": "#0d655e",
    "accent_soft": "#e6f4f1",
    "accent_bright": "#14b8a6",
    # Semantic
    "success": "#067647",
    "success_soft": "#e6f4ea",
    "warning": "#b54708",
    "warning_soft": "#fff4e5",
    "danger": "#b42318",
    "danger_soft": "#fdecea",
    "info": "#175cd3",
    "info_soft": "#eaf1fd",
    # Sidebar
    "sidebar": "#0f172a",
    "sidebar_hover": "#1e293b",
    "sidebar_text": "#cbd5e1",
    "sidebar_muted": "#94a3b8",
}

TABLE_TEXT_COLOR = TOKENS["text"]

APP_STYLESHEET = """
* {
    font-family: "Segoe UI", "Inter", "SF Pro Text", "Noto Sans", Arial, sans-serif;
    font-size: 13px;
}

QMainWindow, QWidget#Root, QWidget#Page {
    background: %(bg)s;
    color: %(text)s;
}

QToolTip {
    background: %(text)s;
    color: #ffffff;
    border: none;
    padding: 6px 8px;
    border-radius: 4px;
}

/* ---------------------------------------------------------------- sidebar */

QFrame#Sidebar {
    background: %(sidebar)s;
    border: none;
}

QLabel#Brand {
    color: #ffffff;
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 0.2px;
}

QLabel#BrandSub, QLabel#SidebarMuted {
    color: %(sidebar_muted)s;
    font-size: 12px;
}

QLabel#NavSection {
    color: %(sidebar_muted)s;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.8px;
    padding-left: 12px;
}

QPushButton#NavButton {
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 6px;
    color: %(sidebar_text)s;
    padding: 9px 12px 9px 13px;
    text-align: left;
    font-weight: 600;
}

QPushButton#NavButton:hover {
    background: %(sidebar_hover)s;
    color: #ffffff;
}

QPushButton#NavButton[active="true"] {
    background: %(sidebar_hover)s;
    border-left: 3px solid %(accent_bright)s;
    color: #ffffff;
}

QLabel#NavBadge {
    background: %(accent_bright)s;
    color: %(sidebar)s;
    border-radius: 9px;
    font-size: 11px;
    font-weight: 700;
    min-width: 18px;
    padding: 1px 6px;
}

QFrame#SessionCard {
    background: %(sidebar_hover)s;
    border: 1px solid #263243;
    border-radius: 8px;
}

QFrame#SessionCard:hover {
    border-color: %(accent_bright)s;
}

QLabel#SessionTitle {
    color: #ffffff;
    font-weight: 600;
}

/* ------------------------------------------------------------- page chrome */

QLabel#PageTitle {
    color: %(text)s;
    font-size: 22px;
    font-weight: 700;
}

QLabel#PageSubtitle {
    color: %(muted)s;
    font-size: 13px;
}

QLabel#CardTitle {
    color: %(text)s;
    font-size: 14px;
    font-weight: 700;
}

QLabel#CardDescription, QLabel#Hint {
    color: %(muted)s;
    font-size: 12px;
}

QLabel#FieldLabel {
    color: %(text_secondary)s;
    font-weight: 600;
}

QLabel#Muted {
    color: %(muted)s;
}

QLabel#Strong {
    color: %(text)s;
    font-weight: 700;
}

QLabel#Code {
    font-family: "Cascadia Mono", "JetBrains Mono", "Menlo", "Consolas", monospace;
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 2px;
    color: %(text)s;
    background: %(surface_alt)s;
    border: 1px dashed %(border_strong)s;
    border-radius: 6px;
    padding: 8px 14px;
}

QFrame#Card {
    background: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: 10px;
}

QFrame#Divider {
    background: %(border)s;
    max-height: 1px;
    min-height: 1px;
    border: none;
}

QScrollArea#PageScroll, QWidget#ScrollContent {
    background: transparent;
    border: none;
}

/* ------------------------------------------------------------------ chips */

QLabel#Chip, QLabel#ChipNeutral {
    background: %(surface_alt)s;
    border: 1px solid %(border)s;
    border-radius: 11px;
    color: %(text_secondary)s;
    font-size: 12px;
    font-weight: 600;
    padding: 3px 10px;
}

QLabel#ChipSuccess {
    background: %(success_soft)s;
    border: 1px solid %(success_soft)s;
    border-radius: 11px;
    color: %(success)s;
    font-size: 12px;
    font-weight: 600;
    padding: 3px 10px;
}

QLabel#ChipWarning {
    background: %(warning_soft)s;
    border: 1px solid %(warning_soft)s;
    border-radius: 11px;
    color: %(warning)s;
    font-size: 12px;
    font-weight: 600;
    padding: 3px 10px;
}

QLabel#ChipDanger {
    background: %(danger_soft)s;
    border: 1px solid %(danger_soft)s;
    border-radius: 11px;
    color: %(danger)s;
    font-size: 12px;
    font-weight: 600;
    padding: 3px 10px;
}

QLabel#ChipInfo {
    background: %(info_soft)s;
    border: 1px solid %(info_soft)s;
    border-radius: 11px;
    color: %(info)s;
    font-size: 12px;
    font-weight: 600;
    padding: 3px 10px;
}

QLabel#StatusPill {
    background: %(accent_soft)s;
    color: %(accent)s;
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 15px;
    font-weight: 700;
}

QLabel#StatusPill[state="in"] {
    background: %(success_soft)s;
    color: %(success)s;
}

QLabel#StatusPill[state="out"] {
    background: %(surface_alt)s;
    color: %(muted)s;
}

/* ----------------------------------------------------------------- inputs */

QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QAbstractSpinBox {
    background: %(surface)s;
    border: 1px solid %(border_strong)s;
    border-radius: 6px;
    color: %(text)s;
    placeholder-text-color: %(muted)s;
    min-height: 34px;
    padding: 5px 10px;
    selection-background-color: %(accent)s;
    selection-color: #ffffff;
}

QTextEdit, QPlainTextEdit {
    padding: 8px 10px;
}

QLineEdit:hover, QComboBox:hover, QTextEdit:hover, QAbstractSpinBox:hover {
    border-color: %(disabled)s;
}

QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus, QAbstractSpinBox:focus {
    border: 1px solid %(accent)s;
}

QLineEdit:read-only {
    background: %(surface_alt)s;
    color: %(text_secondary)s;
}

QLineEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled, QTextEdit:disabled {
    background: %(surface_alt)s;
    border-color: %(border)s;
    color: %(disabled)s;
}

QAbstractSpinBox {
    padding-top: 0px;
    padding-bottom: 0px;
}

QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
    background: transparent;
    border: none;
    width: 18px;
}

QTextEdit#Log, QPlainTextEdit#Log {
    background: %(surface_alt)s;
    border: 1px solid %(border)s;
    font-family: "Cascadia Mono", "JetBrains Mono", "Menlo", "Consolas", monospace;
    font-size: 12px;
    color: %(text_secondary)s;
}

QTextEdit#DirectInput {
    min-height: 72px;
    max-height: 96px;
}

QComboBox::drop-down {
    border: none;
    width: 28px;
}

QComboBox QAbstractItemView {
    background: %(surface)s;
    border: 1px solid %(border_strong)s;
    border-radius: 6px;
    color: %(text)s;
    outline: 0;
    padding: 4px;
    selection-background-color: %(accent_soft)s;
    selection-color: %(text)s;
}

QComboBox QAbstractItemView::item {
    min-height: 28px;
    padding: 5px 9px;
    border-radius: 4px;
    color: %(text)s;
}

QComboBox QAbstractItemView::item:hover,
QComboBox QAbstractItemView::item:selected {
    background: %(accent_soft)s;
    color: %(text)s;
}

QCheckBox {
    color: %(text)s;
    spacing: 8px;
    padding: 3px 0;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid %(border_strong)s;
    border-radius: 4px;
    background: %(surface)s;
}

QCheckBox::indicator:hover {
    border-color: %(accent)s;
}

QCheckBox::indicator:checked {
    background: %(accent)s;
    border-color: %(accent)s;
}

QCheckBox::indicator:disabled {
    background: %(surface_alt)s;
    border-color: %(border)s;
}

/* ---------------------------------------------------------------- buttons */

QPushButton {
    background: %(surface)s;
    border: 1px solid %(border_strong)s;
    border-radius: 6px;
    color: %(text)s;
    min-height: 34px;
    padding: 6px 14px;
    font-weight: 600;
}

QPushButton:hover {
    background: %(surface_alt)s;
    border-color: %(disabled)s;
}

QPushButton:pressed {
    background: %(border)s;
}

QPushButton#Primary {
    background: %(accent)s;
    border: 1px solid %(accent)s;
    color: #ffffff;
}

QPushButton#Primary:hover {
    background: %(accent_hover)s;
    border-color: %(accent_hover)s;
}

QPushButton#Danger {
    background: %(surface)s;
    border: 1px solid #f2b8b5;
    color: %(danger)s;
}

QPushButton#Danger:hover {
    background: %(danger_soft)s;
}

QPushButton#Ghost {
    background: transparent;
    border: 1px solid transparent;
    color: %(text_secondary)s;
}

QPushButton#Ghost:hover {
    background: %(surface_alt)s;
    border-color: %(border)s;
}

QPushButton:disabled {
    background: %(surface_alt)s;
    border-color: %(border)s;
    color: %(disabled)s;
}

QPushButton#Primary:disabled {
    background: #a7d3cd;
    border-color: #a7d3cd;
    color: #ffffff;
}

QPushButton#Ghost:disabled {
    background: transparent;
    border-color: transparent;
    color: %(disabled)s;
}

/* Segmented control ------------------------------------------------------ */

QFrame#Segmented {
    background: %(surface_alt)s;
    border: 1px solid %(border)s;
    border-radius: 8px;
}

QPushButton#Segment {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    color: %(muted)s;
    min-height: 28px;
    padding: 4px 14px;
    font-weight: 600;
}

QPushButton#Segment:hover {
    color: %(text)s;
}

QPushButton#Segment:checked {
    background: %(surface)s;
    border-color: %(border_strong)s;
    color: %(text)s;
}

/* ----------------------------------------------------------------- tables */

QTableWidget, QTableView {
    background: %(surface)s;
    alternate-background-color: %(surface_alt)s;
    border: 1px solid %(border)s;
    border-radius: 10px;
    gridline-color: transparent;
    color: %(text)s;
    selection-background-color: %(accent_soft)s;
    selection-color: %(text)s;
    outline: 0;
}

QTableWidget::item {
    background: transparent;
    border-bottom: 1px solid %(border)s;
    color: %(text)s;
    padding: 6px 10px;
}

QTableWidget::item:selected {
    background: %(accent_soft)s;
    color: %(text)s;
}

QTableWidget::item:disabled {
    color: %(disabled)s;
}

QHeaderView {
    background: transparent;
}

QHeaderView::section {
    background: %(surface_alt)s;
    border: none;
    border-bottom: 1px solid %(border)s;
    color: %(muted)s;
    font-size: 12px;
    font-weight: 700;
    padding: 9px 10px;
}

QTableCornerButton::section {
    background: %(surface_alt)s;
    border: none;
}

QLabel#EmptyState {
    color: %(muted)s;
    font-size: 14px;
    background: %(surface)s;
    border: 1px dashed %(border_strong)s;
    border-radius: 10px;
    padding: 40px;
}

/* -------------------------------------------------------------- scrolling */

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background: %(border_strong)s;
    border-radius: 4px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background: %(disabled)s;
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
    border-radius: 4px;
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
    height: 10px;
}

QSplitter::handle:hover {
    background: %(accent_soft)s;
}

/* ------------------------------------------------------------------- misc */

QMenu {
    background: %(surface)s;
    color: %(text)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    padding: 4px;
}

QMenu::item {
    padding: 6px 12px;
    border-radius: 4px;
}

QMenu::item:selected {
    background: %(accent_soft)s;
    color: %(text)s;
}
""" % TOKENS
