"""Reusable building blocks for the Tidekeeper desktop GUI.

Everything here is presentation-only: no backend calls, no business rules.
``main_window.MainWindow`` composes these into pages and owns the behaviour.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .style import TOKENS

PROGRESS_PERCENT_ROLE = Qt.UserRole + 1
PROGRESS_STATE_ROLE = Qt.UserRole + 2

CHIP_TONES = ("neutral", "success", "warning", "danger", "info")


# --------------------------------------------------------------------------- #
# Small factories
# --------------------------------------------------------------------------- #

def button(
    text: str,
    *,
    primary: bool = False,
    danger: bool = False,
    ghost: bool = False,
    tooltip: str = "",
) -> QPushButton:
    """Create a styled push button. Exactly one of primary/danger/ghost may be set."""
    widget = QPushButton(text)
    if primary:
        widget.setObjectName("Primary")
    elif danger:
        widget.setObjectName("Danger")
    elif ghost:
        widget.setObjectName("Ghost")
    widget.setCursor(Qt.PointingHandCursor)
    if tooltip:
        widget.setToolTip(tooltip)
    return widget


def label(text: str, name: Optional[str] = None, *, wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    if wrap:
        widget.setWordWrap(True)
    return widget


def field_label(text: str) -> QLabel:
    return label(text, "FieldLabel")


def hint(text: str) -> QLabel:
    return label(text, "Hint", wrap=True)


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFrameShape(QFrame.NoFrame)
    return line


def hbox(*widgets, spacing: int = 8, stretch_index: Optional[int] = None) -> QHBoxLayout:
    """Pack widgets (or ``None`` for a stretch) horizontally."""
    layout = QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    for index, widget in enumerate(widgets):
        if widget is None:
            layout.addStretch(1)
        else:
            layout.addWidget(widget, 1 if index == stretch_index else 0)
    return layout


def log_view(placeholder: str) -> QTextEdit:
    view = QTextEdit()
    view.setObjectName("Log")
    view.setReadOnly(True)
    view.setPlaceholderText(placeholder)
    view.setLineWrapMode(QTextEdit.NoWrap)
    return view


def scroll_area(content: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setObjectName("PageScroll")
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setFrameShape(QFrame.NoFrame)
    content.setObjectName("ScrollContent")
    scroll.setWidget(content)
    return scroll


# --------------------------------------------------------------------------- #
# Composite widgets
# --------------------------------------------------------------------------- #

class Card(QFrame):
    """White rounded container with an optional title/description header.

    Use :meth:`body` to add content and :meth:`header_actions` to place
    buttons on the right of the title row.
    """

    def __init__(self, title: str = "", description: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(18, 16, 18, 18)
        self._layout.setSpacing(12)

        self._header_actions = QHBoxLayout()
        self._header_actions.setContentsMargins(0, 0, 0, 0)
        self._header_actions.setSpacing(8)

        if title or description:
            header = QHBoxLayout()
            header.setContentsMargins(0, 0, 0, 0)
            header.setSpacing(12)
            text_column = QVBoxLayout()
            text_column.setContentsMargins(0, 0, 0, 0)
            text_column.setSpacing(2)
            if title:
                text_column.addWidget(label(title, "CardTitle"))
            if description:
                text_column.addWidget(label(description, "CardDescription", wrap=True))
            header.addLayout(text_column, 1)
            header.addLayout(self._header_actions)
            self._layout.addLayout(header)

    @property
    def body(self) -> QVBoxLayout:
        return self._layout

    @property
    def header_actions(self) -> QHBoxLayout:
        return self._header_actions

    def add_layout(self, layout, stretch: int = 0) -> None:
        self._layout.addLayout(layout, stretch)

    def add_widget(self, widget: QWidget, stretch: int = 0) -> None:
        self._layout.addWidget(widget, stretch)


class Chip(QLabel):
    """Small rounded status label. ``tone`` is one of :data:`CHIP_TONES`."""

    def __init__(self, text: str = "", tone: str = "neutral", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        if tone not in CHIP_TONES:
            tone = "neutral"
        self.setObjectName("Chip" + tone.capitalize())
        self.style().unpolish(self)
        self.style().polish(self)


class SegmentedControl(QFrame):
    """Horizontal exclusive toggle used to switch between related views."""

    changed = Signal(int)

    def __init__(self, options: Sequence[str], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Segmented")
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: List[QPushButton] = []
        for index, text in enumerate(options):
            segment = QPushButton(text)
            segment.setObjectName("Segment")
            segment.setCheckable(True)
            segment.setCursor(Qt.PointingHandCursor)
            self._group.addButton(segment, index)
            self._buttons.append(segment)
            layout.addWidget(segment)
        if self._buttons:
            self._buttons[0].setChecked(True)
        self._group.idClicked.connect(self.changed.emit)

    def current_index(self) -> int:
        return self._group.checkedId()

    def set_current_index(self, index: int) -> None:
        if 0 <= index < len(self._buttons) and not self._buttons[index].isChecked():
            self._buttons[index].setChecked(True)
            self.changed.emit(index)


class TableStack(QStackedWidget):
    """Shows either a table or a centred empty-state message."""

    def __init__(self, table: QTableWidget, empty_text: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.table = table
        self.empty_label = label(empty_text, "EmptyState", wrap=True)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.addWidget(self.empty_label)
        self.addWidget(self.table)
        self.set_empty(True)

    def set_empty(self, empty: bool) -> None:
        self.setCurrentWidget(self.empty_label if empty else self.table)

    def set_empty_text(self, text: str) -> None:
        self.empty_label.setText(text)


class NavButton(QPushButton):
    """Sidebar navigation entry with an optional numeric badge."""

    def __init__(self, text: str, parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setObjectName("NavButton")
        self.setProperty("active", False)
        self.setCursor(Qt.PointingHandCursor)
        self.badge = QLabel("", self)
        self.badge.setObjectName("NavBadge")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.hide()

    def set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_badge(self, value: int) -> None:
        if value and value > 0:
            self.badge.setText(str(value) if value < 100 else "99+")
            self.badge.adjustSize()
            self.badge.show()
            self._place_badge()
        else:
            self.badge.hide()

    def resizeEvent(self, event):  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._place_badge()

    def _place_badge(self) -> None:
        if not self.badge.isVisible():
            return
        size = self.badge.sizeHint()
        x = self.width() - size.width() - 10
        y = (self.height() - size.height()) // 2
        self.badge.move(x, y)


class QueueProgressDelegate(QStyledItemDelegate):
    """Paints a rounded progress bar with percentage text in a table cell.

    Reads ``PROGRESS_PERCENT_ROLE`` (0-100) and ``PROGRESS_STATE_ROLE``
    (``"active"``, ``"done"``, ``"failed"`` or ``""``) from the index.
    """

    _FILL = {
        "done": TOKENS["success"],
        "failed": TOKENS["danger"],
        "active": TOKENS["accent"],
        "": TOKENS["accent"],
    }

    def paint(self, painter: QPainter, option, index):
        percent = index.data(PROGRESS_PERCENT_ROLE)
        try:
            percent = int(percent)
        except (TypeError, ValueError):
            percent = 0
        percent = max(0, min(100, percent))
        state = str(index.data(PROGRESS_STATE_ROLE) or "")

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor(TOKENS["accent_soft"]))

        track = option.rect.adjusted(10, 11, -10, -11)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(TOKENS["border"]))
        painter.drawRoundedRect(track, 4, 4)

        if percent > 0:
            fill = track.adjusted(0, 0, 0, 0)
            fill.setWidth(max(4, int(track.width() * percent / 100.0)))
            painter.setBrush(QColor(self._FILL.get(state, TOKENS["accent"])))
            painter.drawRoundedRect(fill, 4, 4)

        text = str(index.data() or "")
        if text:
            painter.setPen(QColor(TOKENS["text"]))
            font = painter.font()
            font.setBold(True)
            font.setPointSizeF(max(7.5, font.pointSizeF() - 1))
            painter.setFont(font)
            painter.drawText(option.rect, Qt.AlignCenter, text)
        painter.restore()


def configure_table(table: QTableWidget, headers: Iterable[str], stretch_column: int = 1) -> None:
    """Apply the shared look and behaviour to a results/queue table."""
    headers = list(headers)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(38)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setSortingEnabled(True)
    table.setWordWrap(False)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setSelectionMode(QTableWidget.ExtendedSelection)
    table.setFocusPolicy(Qt.StrongFocus)
    header = table.horizontalHeader()
    header.setHighlightSections(False)
    header.setStretchLastSection(False)
    header.setSectionResizeMode(QHeaderView.ResizeToContents)
    header.setSectionResizeMode(stretch_column, QHeaderView.Stretch)
    table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)


def fix_columns(table: QTableWidget, widths: dict) -> None:
    """Pin the given ``{column: width}`` pairs so they do not jitter on refresh."""
    header = table.horizontalHeader()
    for column, width in widths.items():
        header.setSectionResizeMode(column, QHeaderView.Fixed)
        table.setColumnWidth(column, width)
