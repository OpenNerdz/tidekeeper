from __future__ import annotations

import time
import webbrowser
from typing import Dict, List, Tuple

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QColor, QPalette, QPainter, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStyledItemDelegate,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..enums import AudioQuality, Type, VideoQuality
from ..settings import SETTINGS
from .backend import (
    SearchItem,
    TidekeeperBackend,
    format_queue_progress,
    parse_direct_inputs,
    queue_progress_percent,
    with_video_only,
)
from .style import APP_STYLESHEET, TABLE_TEXT_COLOR
from .workers import DownloadWorker, TaskWorker

PROGRESS_PERCENT_ROLE = Qt.UserRole + 1
