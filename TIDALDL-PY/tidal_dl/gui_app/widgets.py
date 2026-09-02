"""Reusable building blocks for the Tidekeeper desktop GUI.

Everything here is presentation-only: no backend calls, no business rules.
``main_window.MainWindow`` composes these into the workspace and inspector.

Component rules
---------------
* ``button`` kinds: ``primary`` (one per panel), ``secondary`` (default),
  ``ghost`` (quiet/toggle), ``danger`` (destructive), ``icon`` (28px square),
  ``header`` (checkable inspector toggle in the title bar).
* ``Panel`` is the only bordered surface in the workspace. Its header and
  footer are 36px rows; content sits flush against them.
* ``FormSection`` is the only grouping used inside the inspector.
* Tables never carry their own border; the enclosing panel does.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .style import FONT_MONO, STATE_COLORS, TOKENS

PROGRESS_PERCENT_ROLE = Qt.UserRole + 1
PROGRESS_STATE_ROLE = Qt.UserRole + 2

CONTROL_HEIGHT = 30
ROW_HEIGHT = 30
BUTTON_KINDS = ("primary", "secondary", "ghost", "danger", "icon", "header")


# --------------------------------------------------------------------------- #
# Factories
# --------------------------------------------------------------------------- #

def button(text: str, kind: str = "secondary", *, tooltip: str = "", checkable: bool = False) -> QPushButton:
    """Create a styled push button. ``kind`` is one of :data:`BUTTON_KINDS`."""
    if kind not in BUTTON_KINDS:
        raise ValueError(f"unknown button kind: {kind}")
    widget = QPushButton(text)
    if kind == "primary":
        widget.setObjectName("Primary")
    elif kind == "ghost":
        widget.setObjectName("Ghost")
    elif kind == "danger":
        widget.setObjectName("Danger")
    elif kind == "icon":
        widget.setObjectName("IconButton")
    elif kind == "header":
        widget.setObjectName("HeaderToggle")
    widget.setCursor(Qt.PointingHandCursor)
    widget.setCheckable(checkable)
    widget.setFixedHeight(28 if kind in ("icon", "header") else CONTROL_HEIGHT)
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


def hint(text: str) -> QLabel:
    return label(text, "Hint", wrap=True)


def rule() -> QFrame:
    line = QFrame()
    line.setObjectName("Rule")
    line.setFrameShape(QFrame.NoFrame)
    return line


def dot_icon(color: str, size: int = 8) -> QIcon:
    """A filled circle icon used for status indicators on buttons."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(0, 0, size, size)
    painter.end()
    return QIcon(pixmap)


def log_view(placeholder: str) -> QTextEdit:
    view = QTextEdit()
    view.setObjectName("Log")
    view.setReadOnly(True)
    view.setPlaceholderText(placeholder)
    view.setLineWrapMode(QTextEdit.NoWrap)
    view.setFrameShape(QFrame.NoFrame)
    return view


def scroll_area(content: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setObjectName("Scroll")
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setFrameShape(QFrame.NoFrame)
    content.setObjectName("ScrollContent")
    scroll.setWidget(content)
    return scroll


def row(*widgets, spacing: int = 8, margins: tuple = (0, 0, 0, 0)) -> QHBoxLayout:
    """Pack widgets horizontally. Use ``None`` for a stretch, ``int`` for spacing."""
    layout = QHBoxLayout()
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    for widget in widgets:
        if widget is None:
            layout.addStretch(1)
        elif isinstance(widget, int):
            layout.addSpacing(widget)
        else:
            layout.addWidget(widget)
    return layout


def fix_height(*widgets: QWidget, height: int = CONTROL_HEIGHT) -> None:
    for widget in widgets:
        widget.setFixedHeight(height)


# --------------------------------------------------------------------------- #
# Brand
# --------------------------------------------------------------------------- #

class BrandMark(QWidget):
    """20px tide glyph: accent tile with two wave strokes."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(20, 20)

    def paintEvent(self, event):  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(TOKENS["accent"]))
        painter.drawRoundedRect(QRectF(0, 0, 20, 20), 5, 5)
        pen = QPen(QColor(TOKENS["on_accent"]))
        pen.setWidthF(1.8)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        for base in (7.5, 12.5):
            path = QPainterPath(QPointF(4, base + 1))
            path.cubicTo(QPointF(6, base - 1.5), QPointF(8, base - 1.5), QPointF(10, base + 1))
            path.cubicTo(QPointF(12, base + 3.5), QPointF(14, base + 3.5), QPointF(16, base + 1))
            painter.drawPath(path)
        painter.end()


# --------------------------------------------------------------------------- #
# Containers
# --------------------------------------------------------------------------- #

class Panel(QFrame):
    """Bordered workspace surface with optional header and footer rows.

    ``header`` and ``footer`` are horizontal layouts; ``body`` receives the
    main content flush against them.
    """

    BAR_HEIGHT = 36

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._header: Optional[QFrame] = None
        self._footer: Optional[QFrame] = None

    def _bar(self, name: str) -> QFrame:
        bar = QFrame(self)
        bar.setObjectName(name)
        bar.setFixedHeight(self.BAR_HEIGHT)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 0, 8, 0)
        layout.setSpacing(8)
        return bar

    @property
    def header(self) -> QHBoxLayout:
        if self._header is None:
            self._header = self._bar("PanelHeader")
            self._layout.insertWidget(0, self._header)
        return self._header.layout()

    @property
    def footer(self) -> QHBoxLayout:
        if self._footer is None:
            self._footer = self._bar("PanelFooter")
            self._layout.addWidget(self._footer)
        return self._footer.layout()

    def set_body(self, widget: QWidget, stretch: int = 1) -> None:
        index = 1 if self._header is not None else 0
        self._layout.insertWidget(index, widget, stretch)


class SegmentedControl(QFrame):
    """Horizontal exclusive toggle used to switch between related modes."""

    changed = Signal(int)

    def __init__(self, options: Sequence[str], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Segmented")
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.setFixedHeight(CONTROL_HEIGHT)
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


class FormSection(QWidget):
    """Inspector grouping: eyebrow title, rule, then rows of content."""

    LABEL_WIDTH = 96

    def __init__(self, title: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        head = row(label(title.upper(), "Eyebrow"), spacing=8)
        line = rule()
        head.addWidget(line, 1)
        self._layout.addLayout(head)

    def add_row(self, text: str, widget_or_layout) -> None:
        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(8)
        caption = label(text, "FieldLabel")
        caption.setFixedWidth(self.LABEL_WIDTH)
        line.addWidget(caption)
        if isinstance(widget_or_layout, QWidget):
            line.addWidget(widget_or_layout, 1)
        else:
            line.addLayout(widget_or_layout, 1)
        self._layout.addLayout(line)

    def add_stacked(self, text: str, widget_or_layout) -> None:
        self._layout.addWidget(label(text, "FieldLabel"))
        if isinstance(widget_or_layout, QWidget):
            self._layout.addWidget(widget_or_layout)
        else:
            self._layout.addLayout(widget_or_layout)

    def add_widget(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def add_layout(self, layout) -> None:
        self._layout.addLayout(layout)


class EmptyOverlay(QObject):
    """Centred muted message painted over a table viewport while it is empty."""

    def __init__(self, table: QTableWidget, text: str):
        super().__init__(table)
        self._table = table
        self._label = QLabel(text, table.viewport())
        self._label.setObjectName("EmptyOverlay")
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setWordWrap(True)
        self._label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        table.viewport().installEventFilter(self)
        self._reposition()

    def set_text(self, text: str) -> None:
        self._label.setText(text)

    def set_visible(self, visible: bool) -> None:
        self._label.setVisible(visible)
        if visible:
            self._reposition()

    def eventFilter(self, watched, event):  # noqa: N802 - Qt naming
        if event.type() == QEvent.Resize:
            self._reposition()
        return False

    def _reposition(self) -> None:
        viewport = self._table.viewport()
        width = max(200, min(viewport.width() - 48, 420))
        self._label.setFixedWidth(width)
        self._label.adjustSize()
        x = (viewport.width() - self._label.width()) // 2
        y = max(16, (viewport.height() - self._label.height()) // 2 - 8)
        self._label.move(x, y)


# --------------------------------------------------------------------------- #
# Table delegates
# --------------------------------------------------------------------------- #

def _selection_background(painter: QPainter, option) -> None:
    if option.state & QStyle.State_Selected:
        painter.fillRect(option.rect, QColor(TOKENS["accent_soft"]))
    elif option.features & QStyleOptionViewItem.Alternate:
        painter.fillRect(option.rect, QColor(TOKENS["surface_alt"]))


class StatusDelegate(QStyledItemDelegate):
    """Paints a state-coloured dot followed by the cell text."""

    DOT = 7

    def paint(self, painter: QPainter, option, index):
        state = str(index.data(PROGRESS_STATE_ROLE) or "queued")
        color = QColor(STATE_COLORS.get(state, TOKENS["muted"]))
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        _selection_background(painter, option)
        rect = option.rect.adjusted(8, 0, -8, 0)
        cy = rect.center().y()
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(rect.left(), cy - self.DOT // 2, self.DOT, self.DOT)
        text_rect = rect.adjusted(self.DOT + 8, 0, 0, 0)
        painter.setPen(QColor(TOKENS["text"] if state in ("active", "queued") else color))
        metrics = painter.fontMetrics()
        text = metrics.elidedText(str(index.data() or ""), Qt.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, text)
        painter.restore()


class QueueProgressDelegate(QStyledItemDelegate):
    """Paints a slim progress bar with the percentage to its right.

    Reads ``PROGRESS_PERCENT_ROLE`` (0-100) and ``PROGRESS_STATE_ROLE``
    (``"active"``, ``"done"``, ``"failed"``, ``"cancelled"`` or ``"queued"``).
    """

    TEXT_WIDTH = 36
    BAR_HEIGHT = 5

    def paint(self, painter: QPainter, option, index):
        try:
            percent = int(index.data(PROGRESS_PERCENT_ROLE))
        except (TypeError, ValueError):
            percent = 0
        percent = max(0, min(100, percent))
        state = str(index.data(PROGRESS_STATE_ROLE) or "queued")

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        _selection_background(painter, option)

        rect = option.rect.adjusted(8, 0, -8, 0)
        bar_width = rect.width() - self.TEXT_WIDTH - 6
        track = QRectF(rect.left(), rect.center().y() - self.BAR_HEIGHT / 2, bar_width, self.BAR_HEIGHT)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(TOKENS["border_strong"]))
        painter.drawRoundedRect(track, 2.5, 2.5)

        if percent > 0 and bar_width > 4:
            fill = QRectF(track)
            fill.setWidth(max(4.0, track.width() * percent / 100.0))
            painter.setBrush(QColor(STATE_COLORS.get(state, TOKENS["accent"])))
            painter.drawRoundedRect(fill, 2.5, 2.5)

        text = str(index.data() or "")
        if text:
            font = painter.font()
            font.setFamily(FONT_MONO.split(",")[0].strip('"'))
            font.setPointSizeF(max(7.5, font.pointSizeF() - 1))
            painter.setFont(font)
            painter.setPen(QColor(TOKENS["text_secondary"]))
            text_rect = rect.adjusted(rect.width() - self.TEXT_WIDTH, 0, 0, 0)
            painter.drawText(text_rect, Qt.AlignRight | Qt.AlignVCenter, text)
        painter.restore()


# --------------------------------------------------------------------------- #
# Table helpers
# --------------------------------------------------------------------------- #

def configure_table(table: QTableWidget, headers: Iterable[str], stretch_column: int = 1) -> None:
    """Apply the shared look and behaviour to a results/queue table."""
    headers = list(headers)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setSortingEnabled(True)
    table.setWordWrap(False)
    table.setFrameShape(QFrame.NoFrame)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setSelectionMode(QTableWidget.ExtendedSelection)
    table.setFocusPolicy(Qt.StrongFocus)
    table.setIconSize(QSize(8, 8))
    header = table.horizontalHeader()
    header.setHighlightSections(False)
    header.setStretchLastSection(False)
    header.setSectionResizeMode(QHeaderView.ResizeToContents)
    header.setSectionResizeMode(stretch_column, QHeaderView.Stretch)
    header.setFixedHeight(28)
    table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)


def fix_columns(table: QTableWidget, widths: dict) -> None:
    """Pin ``{column: width}`` pairs so they do not jitter on refresh."""
    header = table.horizontalHeader()
    for column, width in widths.items():
        header.setSectionResizeMode(column, QHeaderView.Fixed)
        table.setColumnWidth(column, width)
