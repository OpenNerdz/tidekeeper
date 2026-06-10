from __future__ import annotations

import webbrowser
from typing import Dict, List, Tuple

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QColor, QPalette, QTextCursor
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
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..enums import AudioQuality, Type, VideoQuality
from ..settings import SETTINGS
from .backend import SearchItem, TidekeeperBackend, with_video_only
from .style import APP_STYLESHEET, TABLE_TEXT_COLOR
from .workers import DownloadWorker, TaskWorker


SCREEN_ORDER = ("search", "queue", "settings", "account")
QUALITY_ORDER = [
    AudioQuality.Atmos,
    AudioQuality.Max,
    AudioQuality.Master,
    AudioQuality.HiFi,
    AudioQuality.High,
    AudioQuality.Normal,
]
PRIORITY_PRESETS = [
    ("Max > HiFi > High > Normal (default)", ["Max", "HiFi", "High", "Normal"]),
    ("Selected quality only", []),
    ("Selected quality, then lower", "__selected__"),
    ("Atmos > Max > Master > HiFi > High > Normal", [item.name for item in QUALITY_ORDER]),
    ("Max > Master > HiFi > High > Normal", ["Max", "Master", "HiFi", "High", "Normal"]),
    ("HiFi > High > Normal", ["HiFi", "High", "Normal"]),
]


def _button(text: str, primary: bool = False, danger: bool = False) -> QPushButton:
    button = QPushButton(text)
    if primary:
        button.setObjectName("Primary")
    if danger:
        button.setObjectName("Danger")
    button.setCursor(Qt.PointingHandCursor)
    return button


def _panel(layout) -> QFrame:
    frame = QFrame()
    frame.setObjectName("Panel")
    frame.setLayout(layout)
    return frame


def _label(text: str, name: str | None = None) -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    return label


def _panel_title(text: str) -> QLabel:
    return _label(text, "PanelTitle")


class MainWindow(QMainWindow):
    def __init__(self, backend: TidekeeperBackend):
        super().__init__()
        self.backend = backend
        self.thread_pool = QThreadPool.globalInstance()
        self.results: List[SearchItem] = []
        self.result_history: List[Tuple[List[SearchItem], str]] = []
        self.queue: List[SearchItem] = []
        self.nav_buttons: Dict[str, QPushButton] = {}
        self.active_workers = set()
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_device_login)
        self.login_polling = False
        self.login_poll_inflight = False
        self.search_in_progress = False
        self.download_in_progress = False

        self.setWindowTitle("Tidekeeper")
        self.setMinimumSize(1040, 680)
        self.resize(1180, 820)
        self.setStyleSheet(APP_STYLESHEET)
        self._build()
        self.version_label.setText(f"v{self.backend.version()}")
        self.refresh_settings()
        self.refresh_auth_status()
        self.update_action_states()
        self.show_screen("search")

    def _build(self):
        root = QWidget()
        root.setObjectName("Root")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        self.pages = {
            "search": self._build_search_page(),
            "queue": self._build_queue_page(),
            "settings": self._build_settings_page(),
            "account": self._build_account_page(),
        }
        for name in SCREEN_ORDER:
            self.stack.addWidget(self.pages[name])
        root_layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(210)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(10)

        brand = _label("Tidekeeper", "Brand")
        sub = _label("Desktop", "SubtleDark")
        layout.addWidget(brand)
        layout.addWidget(sub)
        layout.addSpacing(20)

        for name, title in (
            ("search", "Search"),
            ("queue", "Queue"),
            ("settings", "Settings"),
            ("account", "Account"),
        ):
            button = QPushButton(title)
            button.setObjectName("NavButton")
            button.setProperty("active", False)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda checked=False, screen=name: self.show_screen(screen))
            self.nav_buttons[name] = button
            layout.addWidget(button)

        layout.addStretch(1)
        self.version_label = _label("Ready", "SubtleDark")
        layout.addWidget(self.version_label)
        return sidebar

    def _page(self, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        layout.addWidget(_label(title, "PageTitle"))
        if subtitle:
            layout.addWidget(_label(subtitle, "Muted"))
        return page, layout

    def _build_search_page(self) -> QWidget:
        page, layout = self._page("Search", "TIDAL catalog")

        search_layout = QGridLayout()
        search_layout.setContentsMargins(16, 16, 16, 16)
        search_layout.setHorizontalSpacing(10)
        search_layout.setVerticalSpacing(10)
        self.search_type = QComboBox()
        self.search_type.addItem("All", Type.Null)
        for item in (Type.Track, Type.Album, Type.Playlist, Type.Artist, Type.Video):
            self.search_type.addItem(item.name, item)
        self.search_type.setFixedWidth(150)
        self.search_text = QLineEdit()
        self.search_text.setPlaceholderText("Search or paste URL")
        self.search_button = _button("Search", primary=True)
        self.search_button.setToolTip("Search TIDAL for the selected content type.")
        self.search_button.clicked.connect(self.run_search)
        self.search_text.returnPressed.connect(self.run_search)
        self.search_text.textChanged.connect(self.update_search_action)
        search_layout.addWidget(_panel_title("Catalog search"), 0, 0)
        search_layout.addWidget(self.search_type, 0, 1)
        search_layout.addWidget(self.search_text, 0, 2)
        search_layout.addWidget(self.search_button, 0, 3)
        search_layout.setColumnStretch(2, 1)
        layout.addWidget(_panel(search_layout))

        direct_layout = QGridLayout()
        direct_layout.setContentsMargins(16, 16, 16, 16)
        direct_layout.setHorizontalSpacing(10)
        direct_layout.setVerticalSpacing(10)
        self.direct_text = QLineEdit()
        self.direct_text.setPlaceholderText("Direct download: TIDAL URL, numeric ID, mix ID, or .txt file")
        self.direct_video_only = QCheckBox("Videos only")
        self.direct_browse_button = _button("File")
        self.direct_queue_button = _button("Add Direct")
        self.direct_download_button = _button("Download Direct", primary=True)
        self.direct_video_only.setToolTip("Skip audio tracks for artist, album, playlist, mix, video, or file downloads.")
        self.direct_browse_button.setToolTip("Pick a text file containing TIDAL URLs.")
        self.direct_queue_button.setToolTip("Add this URL, ID, or file to the queue.")
        self.direct_download_button.setToolTip("Start this direct download now.")
        self.direct_browse_button.clicked.connect(self.browse_direct_file)
        self.direct_queue_button.clicked.connect(self.add_direct_to_queue)
        self.direct_download_button.clicked.connect(self.download_direct)
        self.direct_text.textChanged.connect(self.update_direct_actions)
        direct_layout.addWidget(_panel_title("Direct input"), 0, 0)
        direct_layout.addWidget(self.direct_text, 0, 1, 1, 4)
        direct_layout.addWidget(self.direct_browse_button, 0, 5)
        direct_layout.addWidget(self.direct_video_only, 1, 1)
        direct_layout.addWidget(self.direct_queue_button, 1, 4)
        direct_layout.addWidget(self.direct_download_button, 1, 5)
        direct_layout.setColumnStretch(1, 1)
        layout.addWidget(_panel(direct_layout))

        self.results_table = QTableWidget(0, 6)
        self._setup_table(self.results_table, ["Type", "Title", "Artists", "Quality", "Duration", "ID"])
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.results_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.results_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.results_table.setColumnWidth(3, 150)
        self.results_table.setColumnWidth(4, 90)
        self.results_table.setColumnWidth(5, 120)
        self.results_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.results_table.itemSelectionChanged.connect(self.update_result_actions)
        self.results_table.itemDoubleClicked.connect(self.open_result_item)
        layout.addWidget(self.results_table, 1)

        action_layout = QHBoxLayout()
        self.search_status = _label("No search run yet.", "Muted")
        action_layout.addWidget(self.search_status, 1)
        self.back_results_button = _button("Back")
        self.artist_videos_button = _button("View Videos")
        self.result_video_only = QCheckBox("Videos only")
        self.add_queue_button = _button("Add to Queue")
        self.download_now_button = _button("Download Now", primary=True)
        self.back_results_button.setToolTip("Return to the previous result list.")
        self.artist_videos_button.setToolTip("Replace an Artist result with its videos.")
        self.result_video_only.setToolTip("Queue or download selected rows in videos-only mode.")
        self.add_queue_button.setToolTip("Add selected rows to the queue.")
        self.download_now_button.setToolTip("Add selected rows and start downloading.")
        self.back_results_button.clicked.connect(self.show_previous_results)
        self.artist_videos_button.clicked.connect(self.view_selected_artist_videos)
        self.add_queue_button.clicked.connect(self.add_selected_to_queue)
        self.download_now_button.clicked.connect(self.download_selected)
        action_layout.addWidget(self.back_results_button)
        action_layout.addWidget(self.artist_videos_button)
        action_layout.addWidget(self.result_video_only)
        action_layout.addWidget(self.add_queue_button)
        action_layout.addWidget(self.download_now_button)
        layout.addLayout(action_layout)
        return page

    def _build_queue_page(self) -> QWidget:
        page, layout = self._page("Queue", "Download list")

        self.queue_table = QTableWidget(0, 5)
        self._setup_table(self.queue_table, ["Type", "Title", "Artists", "Quality", "Status"])
        self.queue_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.queue_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.queue_table.setColumnWidth(3, 150)
        self.queue_table.setColumnWidth(4, 120)
        self.queue_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.queue_table.itemSelectionChanged.connect(self.update_queue_actions)
        layout.addWidget(self.queue_table, 1)

        action_layout = QHBoxLayout()
        self.queue_status = _label("Queue is empty.", "Muted")
        action_layout.addWidget(self.queue_status, 1)
        self.remove_queue_button = _button("Remove")
        self.clear_queue_button = _button("Clear")
        self.start_queue_button = _button("Start Queue", primary=True)
        self.remove_queue_button.setToolTip("Remove selected queue rows.")
        self.clear_queue_button.setToolTip("Clear the queue and output log.")
        self.start_queue_button.setToolTip("Download every queued item.")
        self.remove_queue_button.clicked.connect(self.remove_selected_queue_items)
        self.clear_queue_button.clicked.connect(self.clear_queue)
        self.start_queue_button.clicked.connect(self.start_queue_download)
        action_layout.addWidget(self.remove_queue_button)
        action_layout.addWidget(self.clear_queue_button)
        action_layout.addWidget(self.start_queue_button)
        layout.addLayout(action_layout)

        self.download_log = QTextEdit()
        self.download_log.setReadOnly(True)
        self.download_log.setPlaceholderText("Download output")
        layout.addWidget(_label("Output", "SectionTitle"))
        layout.addWidget(self.download_log)
        return page

    def _build_settings_page(self) -> QWidget:
        page, layout = self._page("Settings", "Preferences")

        self.download_path = QLineEdit()
        browse = _button("Browse")
        open_folder = _button("Open")
        open_folder.setToolTip("Open the current download folder.")
        open_folder.clicked.connect(self.open_download_folder)
        browse.clicked.connect(self.browse_download_path)
        path_layout = QHBoxLayout()
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.addWidget(self.download_path, 1)
        path_layout.addWidget(open_folder)
        path_layout.addWidget(browse)

        self.audio_quality = QComboBox()
        for item in QUALITY_ORDER:
            self.audio_quality.addItem(item.name, item.name)
        self.video_quality = QComboBox()
        for item in VideoQuality:
            self.video_quality.addItem(item.name, item.name)
        self.priority_preset = QComboBox()
        self.priority_preset.setToolTip("Fallback order used when the requested stream is blocked or unavailable.")
        for label, order in PRIORITY_PRESETS:
            self.priority_preset.addItem(label, order)
        self.priority_preset.setMinimumContentsLength(18)
        self.priority_preset.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.priority_preset.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.language = QComboBox()
        for index, name in self.backend.language_choices():
            self.language.addItem(name, index)
        self.api_client = QComboBox()
        for item in self.backend.api_clients():
            status = "OK" if item["valid"] else "old"
            self.api_client.addItem(
                f'{item["index"]} {status} - {item["platform"]} ({item["formats"]})',
                item["index"],
            )
        self.api_client.setMinimumContentsLength(18)
        self.api_client.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.api_client.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

        self.checks = {}
        for key, label in (
            ("checkExist", "Skip existing files"),
            ("showProgress", "Show progress"),
            ("showTrackInfo", "Show track info"),
            ("includeEP", "Include EPs and singles"),
            ("saveCovers", "Save covers"),
            ("lyricFile", "Save lyrics"),
            ("saveAlbumInfo", "Save album info"),
            ("downloadVideos", "Download videos"),
            ("multiThread", "Parallel downloads"),
            ("downloadDelay", "Use request delay"),
            ("saveAsFlac", "Save FLAC as .flac files"),
            ("usePlaylistFolder", "Use playlist folders"),
        ):
            self.checks[key] = QCheckBox(label)

        self.request_interval = QDoubleSpinBox()
        self.request_interval.setRange(0.0, 300.0)
        self.request_interval.setSingleStep(0.5)
        self.request_interval.setDecimals(1)
        self.request_interval.setSuffix(" s")
        self.request_interval.setToolTip("Minimum delay between TIDAL playback API requests.")
        self.checks["downloadDelay"].toggled.connect(self._update_request_interval_enabled)

        self.album_format = QLineEdit()
        self.playlist_format = QLineEdit()
        self.track_format = QLineEdit()
        self.video_format = QLineEdit()

        content = QWidget()
        content.setObjectName("ScrollContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(10)
        top_layout.addWidget(self._build_storage_settings_panel(path_layout), 3)
        top_layout.addWidget(self._build_quality_settings_panel(), 2)
        content_layout.addLayout(top_layout)
        content_layout.addWidget(self._build_library_settings_panel())
        content_layout.addWidget(self._build_naming_settings_panel())
        content_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setObjectName("PageScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        action_layout = QHBoxLayout()
        self.settings_status = _label("Settings loaded.", "Muted")
        action_layout.addWidget(self.settings_status, 1)
        reset = _button("Reload")
        save = _button("Save Settings", primary=True)
        reset.clicked.connect(self.refresh_settings)
        save.clicked.connect(self.save_settings)
        action_layout.addWidget(reset)
        action_layout.addWidget(save)
        layout.addLayout(action_layout)
        return page

    def _build_storage_settings_panel(self, path_layout: QHBoxLayout) -> QFrame:
        grid = QGridLayout()
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.addWidget(_panel_title("Storage"), 0, 0, 1, 2)
        grid.addWidget(_label("Download path", "SectionTitle"), 1, 0)
        grid.addLayout(path_layout, 1, 1)
        grid.addWidget(_label("Language", "SectionTitle"), 2, 0)
        grid.addWidget(self.language, 2, 1)
        grid.addWidget(_label("TIDAL client", "SectionTitle"), 3, 0)
        grid.addWidget(self.api_client, 3, 1)
        grid.setColumnStretch(1, 1)
        return _panel(grid)

    def _build_quality_settings_panel(self) -> QFrame:
        grid = QGridLayout()
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.addWidget(_panel_title("Quality"), 0, 0, 1, 2)
        grid.addWidget(_label("Audio", "SectionTitle"), 1, 0)
        grid.addWidget(self.audio_quality, 1, 1)
        grid.addWidget(_label("Fallback", "SectionTitle"), 2, 0)
        grid.addWidget(self.priority_preset, 2, 1)
        grid.addWidget(_label("Video", "SectionTitle"), 3, 0)
        grid.addWidget(self.video_quality, 3, 1)
        grid.setColumnStretch(1, 1)
        return _panel(grid)

    def _build_library_settings_panel(self) -> QFrame:
        grid = QGridLayout()
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)
        groups = [
            ("Files", ["checkExist", "saveCovers", "lyricFile", "saveAlbumInfo", "usePlaylistFolder"]),
            ("Catalog", ["includeEP", "downloadVideos"]),
            ("Run behavior", ["multiThread", "downloadDelay", "saveAsFlac", "showProgress", "showTrackInfo"]),
        ]
        for column, (title, keys) in enumerate(groups):
            grid.addWidget(_label(title, "SectionTitle"), 0, column)
            for row, key in enumerate(keys, start=1):
                grid.addWidget(self.checks[key], row, column)
            grid.setColumnStretch(column, 1)
        grid.addWidget(_label("Request interval", "SectionTitle"), 0, len(groups))
        grid.addWidget(self.request_interval, 1, len(groups))
        grid.setColumnStretch(len(groups), 1)
        return _panel(grid)

    def _build_naming_settings_panel(self) -> QFrame:
        grid = QGridLayout()
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)
        grid.addWidget(_panel_title("Naming"), 0, 0, 1, 2)
        fields = (
            ("Album folder", self.album_format, 1, 0),
            ("Playlist folder", self.playlist_format, 1, 1),
            ("Track file", self.track_format, 3, 0),
            ("Video file", self.video_format, 3, 1),
        )
        for label, widget, row, column in fields:
            widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            grid.addWidget(_label(label, "SectionTitle"), row, column)
            grid.addWidget(widget, row + 1, column)
            grid.setColumnStretch(column, 1)
        return _panel(grid)

    def _build_account_page(self) -> QWidget:
        page, layout = self._page("Account", "Session")

        status_layout = QGridLayout()
        status_layout.setContentsMargins(16, 16, 16, 16)
        status_layout.setVerticalSpacing(12)
        self.auth_label = _label("Signed out", "StatusPill")
        self.country_label = _label("Country: unknown", "Muted")
        self.expiry_label = _label("Expires: unknown", "Muted")
        status_layout.addWidget(self.auth_label, 0, 0, 1, 2)
        status_layout.addWidget(self.country_label, 1, 0)
        status_layout.addWidget(self.expiry_label, 1, 1)
        layout.addWidget(_panel(status_layout))

        login_layout = QGridLayout()
        login_layout.setContentsMargins(16, 16, 16, 16)
        login_layout.setVerticalSpacing(12)
        self.login_url = QLineEdit()
        self.login_url.setReadOnly(True)
        self.login_url.setPlaceholderText("Device login URL")
        self.device_login_button = _button("Start Device Login", primary=True)
        self.open_login_button = _button("Open Login")
        self.refresh_login_button = _button("Refresh Saved Login")
        self.logout_button = _button("Log Out", danger=True)
        self.device_login_button.setToolTip("Start TIDAL device login.")
        self.open_login_button.setToolTip("Open the device login URL in your browser.")
        self.refresh_login_button.setToolTip("Refresh the saved token if possible.")
        self.logout_button.setToolTip("Remove the saved local login.")
        self.device_login_button.clicked.connect(self.start_device_login)
        self.open_login_button.clicked.connect(self.open_login_url)
        self.refresh_login_button.clicked.connect(self.refresh_saved_login)
        self.logout_button.clicked.connect(self.logout)
        login_layout.addWidget(_label("Device login", "SectionTitle"), 0, 0)
        login_layout.addWidget(self.login_url, 0, 1, 1, 3)
        login_layout.addWidget(self.device_login_button, 1, 0)
        login_layout.addWidget(self.open_login_button, 1, 1)
        login_layout.addWidget(self.refresh_login_button, 1, 2)
        login_layout.addWidget(self.logout_button, 1, 3)
        layout.addWidget(_panel(login_layout))

        token_layout = QGridLayout()
        token_layout.setContentsMargins(16, 16, 16, 16)
        token_layout.setVerticalSpacing(12)
        self.access_token = QLineEdit()
        self.access_token.setEchoMode(QLineEdit.Password)
        self.access_token.setPlaceholderText("Access token")
        self.refresh_token = QLineEdit()
        self.refresh_token.setEchoMode(QLineEdit.Password)
        self.refresh_token.setPlaceholderText("Refresh token, optional")
        self.token_login_button = _button("Save Token", primary=True)
        self.token_login_button.setToolTip("Save a manually supplied TIDAL token.")
        self.token_login_button.clicked.connect(self.login_with_token)
        token_layout.addWidget(_label("Manual token", "SectionTitle"), 0, 0)
        token_layout.addWidget(self.access_token, 0, 1)
        token_layout.addWidget(self.refresh_token, 1, 1)
        token_layout.addWidget(self.token_login_button, 1, 2)
        layout.addWidget(_panel(token_layout))

        maintenance_layout = QGridLayout()
        maintenance_layout.setContentsMargins(16, 16, 16, 16)
        maintenance_layout.setVerticalSpacing(12)
        self.doctor_button = _button("Run Doctor")
        self.update_terminal_button = _button("Update Terminal")
        self.update_gui_button = _button("Update GUI", primary=True)
        self.doctor_button.setToolTip("Check auth, download path, client, and local tools.")
        self.update_terminal_button.setToolTip("Update the terminal install from GitHub.")
        self.update_gui_button.setToolTip("Update the terminal and GUI install from GitHub.")
        self.doctor_button.clicked.connect(self.run_doctor)
        self.update_terminal_button.clicked.connect(lambda: self.update_tidekeeper(False))
        self.update_gui_button.clicked.connect(lambda: self.update_tidekeeper(True))
        maintenance_layout.addWidget(_label("Maintenance", "SectionTitle"), 0, 0)
        maintenance_layout.addWidget(self.doctor_button, 0, 1)
        maintenance_layout.addWidget(self.update_terminal_button, 0, 2)
        maintenance_layout.addWidget(self.update_gui_button, 0, 3)
        layout.addWidget(_panel(maintenance_layout))

        self.account_log = QTextEdit()
        self.account_log.setReadOnly(True)
        self.account_log.setPlaceholderText("Account output")
        layout.addWidget(_label("Output", "SectionTitle"))
        layout.addWidget(self.account_log, 1)
        return page

    def _table_cell(self, value, item=None) -> QTableWidgetItem:
        cell = QTableWidgetItem(str(value))
        cell.setForeground(QColor(TABLE_TEXT_COLOR))
        if item is not None:
            cell.setData(Qt.UserRole, item)
        return cell

    def _update_request_interval_enabled(self, enabled: bool):
        self.request_interval.setEnabled(enabled)

    def _setup_table(self, table: QTableWidget, headers: List[str]):
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setSortingEnabled(True)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def show_screen(self, name: str):
        if name not in self.pages:
            return
        self.stack.setCurrentWidget(self.pages[name])
        for key, button in self.nav_buttons.items():
            button.setProperty("active", key == name)
            button.style().unpolish(button)
            button.style().polish(button)

    def start_worker(self, worker):
        self.active_workers.add(worker)

        def cleanup():
            self.active_workers.discard(worker)
            try:
                worker.signals.finished.disconnect(cleanup)
            except (RuntimeError, TypeError):
                pass

        worker.signals.finished.connect(cleanup)
        self.thread_pool.start(worker)

    def run_search(self):
        text = self.search_text.text().strip()
        kind = self.search_type.currentData()
        if not text:
            self.search_status.setText("Enter a search term or TIDAL URL.")
            return
        if self.search_in_progress:
            return
        self.result_history = []
        self.search_in_progress = True
        self.update_search_action()
        self.update_result_actions()
        self.search_status.setText("Searching...")
        worker = TaskWorker(self.backend.search, text, kind)
        worker.signals.result.connect(self.set_search_results)
        worker.signals.error.connect(self.show_search_error)
        worker.signals.finished.connect(self._search_finished)
        self.start_worker(worker)

    def set_search_results(self, items: List[SearchItem], status_text: str | None = None):
        self.results = items
        self.results_table.setSortingEnabled(False)
        self.results_table.setRowCount(len(items))
        for row, item in enumerate(items):
            values = [item.kind.name, item.title, item.artists, item.quality, item.duration, item.identifier]
            for col, value in enumerate(values):
                cell = self._table_cell(value, item if col == 0 else None)
                if col == 5:
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.results_table.setItem(row, col, cell)
        self.results_table.setSortingEnabled(True)
        self.search_status.setText(status_text or f"{len(items)} result{'s' if len(items) != 1 else ''}.")
        self.update_result_actions()

    def _search_finished(self):
        self.search_in_progress = False
        self.update_search_action()
        self.update_result_actions()

    def show_search_error(self, message: str):
        self.search_status.setText(message)
        QMessageBox.warning(self, "Search failed", message)

    def open_result_item(self, cell: QTableWidgetItem):
        item = self._row_item(self.results_table, cell.row())
        if item is None:
            return
        if item.kind != Type.Artist:
            self.search_status.setText("Double-click Artist results to view tracks.")
            return
        if self.search_in_progress:
            return

        self.result_history.append((list(self.results), self.search_status.text()))
        self.search_in_progress = True
        self.search_status.setText(f"Loading tracks by {item.title}...")
        self.update_search_action()
        self.update_result_actions()
        worker = TaskWorker(self.backend.artist_tracks, item)
        worker.signals.result.connect(
            lambda items, artist=item.title: self.set_search_results(
                items,
                f"{len(items)} track{'s' if len(items) != 1 else ''} by {artist}.",
            )
        )
        worker.signals.error.connect(self.show_search_error)
        worker.signals.finished.connect(self._search_finished)
        self.start_worker(worker)

    def view_selected_artist_videos(self):
        items = self.selected_result_items()
        if len(items) != 1 or items[0].kind != Type.Artist:
            self.search_status.setText("Select one artist row first.")
            return
        if self.search_in_progress:
            return

        item = items[0]
        self.result_history.append((list(self.results), self.search_status.text()))
        self.search_in_progress = True
        self.search_status.setText(f"Loading videos by {item.title}...")
        self.update_search_action()
        self.update_result_actions()
        worker = TaskWorker(self.backend.artist_videos, item)
        worker.signals.result.connect(
            lambda videos, artist=item.title: self.set_search_results(
                videos,
                f"{len(videos)} video{'s' if len(videos) != 1 else ''} by {artist}.",
            )
        )
        worker.signals.error.connect(self.show_search_error)
        worker.signals.finished.connect(self._search_finished)
        self.start_worker(worker)

    def show_previous_results(self):
        if not self.result_history or self.search_in_progress:
            return
        items, status = self.result_history.pop()
        self.set_search_results(items, status)

    def selected_result_items(self) -> List[SearchItem]:
        rows = sorted({index.row() for index in self.results_table.selectionModel().selectedRows()})
        items = []
        for row in rows:
            item = self._row_item(self.results_table, row)
            if item is not None:
                items.append(item)
        return items

    def _row_item(self, table: QTableWidget, row: int):
        cell = table.item(row, 0)
        if cell is None:
            return None
        return cell.data(Qt.UserRole)

    def add_selected_to_queue(self):
        items = self.video_mode_items(self.selected_result_items(), self.result_video_only.isChecked())
        if not items:
            self.search_status.setText("Select one or more rows first.")
            return
        self.queue.extend(items)
        self.refresh_queue_table()
        self.search_status.setText(f"Added {len(items)} item{'s' if len(items) != 1 else ''} to queue.")

    def browse_direct_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "URL list", self.direct_text.text(), "Text files (*.txt);;All files (*)")
        if path:
            self.direct_text.setText(path)

    def direct_item_from_input(self):
        text = self.direct_text.text().strip()
        if not text:
            self.search_status.setText("Enter a URL, ID, mix ID, or .txt file.")
            return None
        return with_video_only(self.backend.direct_item(text), self.direct_video_only.isChecked())

    def add_direct_to_queue(self):
        item = self.direct_item_from_input()
        if item is None:
            return
        self.queue.append(item)
        self.refresh_queue_table()
        self.search_status.setText("Direct item added to queue.")

    def download_direct(self):
        if self.download_in_progress:
            self.search_status.setText("A download is already running.")
            return
        item = self.direct_item_from_input()
        if item is None:
            return
        self.queue.append(item)
        self.refresh_queue_table()
        self.show_screen("queue")
        self.start_downloads([item])

    def download_selected(self):
        if self.download_in_progress:
            self.search_status.setText("A download is already running.")
            return
        items = self.video_mode_items(self.selected_result_items(), self.result_video_only.isChecked())
        if not items:
            self.search_status.setText("Select one or more rows first.")
            return
        self.queue.extend(items)
        self.refresh_queue_table()
        self.show_screen("queue")
        self.start_downloads(items)

    def refresh_queue_table(self):
        self.queue_table.setSortingEnabled(False)
        self.queue_table.setRowCount(len(self.queue))
        for row, item in enumerate(self.queue):
            kind = "Direct" if item.kind == Type.Null else item.kind.name
            if item.video_only and item.kind != Type.Video:
                kind += " videos"
            values = [kind, item.title, item.artists, item.quality, "Queued"]
            for col, value in enumerate(values):
                self.queue_table.setItem(row, col, self._table_cell(value, item if col == 0 else None))
        self.queue_table.setSortingEnabled(True)
        self.queue_status.setText(f"{len(self.queue)} item{'s' if len(self.queue) != 1 else ''} in queue.")
        self.update_queue_actions()

    def remove_selected_queue_items(self):
        rows = sorted({index.row() for index in self.queue_table.selectionModel().selectedRows()})
        selected_items = [self._row_item(self.queue_table, row) for row in rows]
        for selected in selected_items:
            if selected is None:
                continue
            for index, queued in enumerate(self.queue):
                if queued is selected:
                    self.queue.pop(index)
                    break
        self.refresh_queue_table()

    def clear_queue(self):
        self.queue = []
        self.refresh_queue_table()
        self.download_log.clear()

    def start_queue_download(self):
        if self.download_in_progress:
            self.queue_status.setText("A download is already running.")
            return
        if not self.queue:
            self.queue_status.setText("Queue is empty.")
            return
        self.start_downloads(list(self.queue))

    def start_downloads(self, items: List[SearchItem]):
        if self.download_in_progress:
            self.queue_status.setText("A download is already running.")
            return
        self.download_in_progress = True
        self.update_action_states()
        self.download_log.append("Starting downloads")
        worker = DownloadWorker(self.backend, items)
        worker.signals.log.connect(self.append_download_log)
        worker.signals.item_status.connect(self._set_queue_item_status)
        worker.signals.result.connect(lambda _: self.queue_status.setText("Downloads finished."))
        worker.signals.error.connect(self.show_download_error)
        worker.signals.finished.connect(self._download_finished)
        self.start_worker(worker)

    def _download_finished(self):
        self.download_in_progress = False
        self.update_action_states()

    def _set_queue_item_status(self, item, status: str):
        for row in range(self.queue_table.rowCount()):
            if self._row_item(self.queue_table, row) is item:
                cell = self.queue_table.item(row, 4)
                if cell is not None:
                    cell.setText(status)
                break

    def update_action_states(self):
        self.update_search_action()
        self.update_direct_actions()
        self.update_result_actions()
        self.update_queue_actions()

    def update_search_action(self):
        self.search_button.setEnabled(bool(self.search_text.text().strip()) and not self.search_in_progress)

    def update_direct_actions(self):
        has_input = bool(self.direct_text.text().strip())
        self.direct_queue_button.setEnabled(has_input)
        self.direct_download_button.setEnabled(has_input and not self.download_in_progress)

    def update_result_actions(self):
        selected = self.selected_result_items()
        has_selection = bool(selected)
        has_single_artist = len(selected) == 1 and selected[0].kind == Type.Artist
        self.back_results_button.setEnabled(bool(self.result_history) and not self.search_in_progress)
        self.artist_videos_button.setEnabled(has_single_artist and not self.search_in_progress)
        self.add_queue_button.setEnabled(has_selection)
        self.download_now_button.setEnabled(has_selection and not self.download_in_progress)

    def video_mode_items(self, items: List[SearchItem], video_only: bool) -> List[SearchItem]:
        if not video_only:
            return items
        return [with_video_only(item, True) for item in items]

    def update_queue_actions(self):
        has_queue = bool(self.queue)
        has_selection = bool(self.queue_table.selectionModel().selectedRows())
        self.remove_queue_button.setEnabled(has_selection and not self.download_in_progress)
        self.clear_queue_button.setEnabled(has_queue and not self.download_in_progress)
        self.start_queue_button.setEnabled(has_queue and not self.download_in_progress)

    def append_download_log(self, text: str):
        cursor = self.download_log.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.download_log.setTextCursor(cursor)
        self.download_log.ensureCursorVisible()

    def show_download_error(self, message: str):
        self.queue_status.setText(message)
        QMessageBox.warning(self, "Download failed", message)

    def refresh_settings(self):
        self.download_path.setText(SETTINGS.downloadPath)
        self.audio_quality.setCurrentText(SETTINGS.audioQuality.name)
        self.video_quality.setCurrentText(SETTINGS.videoQuality.name)
        priority = SETTINGS.getAudioQualityPriority(SETTINGS.audioQualityPriority)
        self.set_priority_preset([item.name for item in priority])
        index = self.language.findData(SETTINGS.language)
        self.language.setCurrentIndex(index if index >= 0 else 0)
        client_index = self.api_client.findData(SETTINGS.apiKeyIndex)
        self.api_client.setCurrentIndex(client_index if client_index >= 0 else 0)
        for key, checkbox in self.checks.items():
            checkbox.setChecked(bool(getattr(SETTINGS, key)))
        self.request_interval.setValue(max(0.0, float(getattr(SETTINGS, 'requestIntervalSeconds', 1.0) or 0.0)))
        self._update_request_interval_enabled(self.checks["downloadDelay"].isChecked())
        self.album_format.setText(SETTINGS.albumFolderFormat)
        self.playlist_format.setText(SETTINGS.playlistFolderFormat)
        self.track_format.setText(SETTINGS.trackFileFormat)
        self.video_format.setText(SETTINGS.videoFileFormat)
        self.settings_status.setText("Settings loaded.")

    def browse_download_path(self):
        path = QFileDialog.getExistingDirectory(self, "Download folder", self.download_path.text())
        if path:
            self.download_path.setText(path)

    def open_download_folder(self):
        path = self.download_path.text().strip() or SETTINGS.downloadPath
        try:
            opened = self.backend.open_download_folder(path)
        except OSError as exc:
            self.settings_status.setText(str(exc))
            QMessageBox.warning(self, "Open folder failed", str(exc))
            return
        self.settings_status.setText(f"Opened {opened}")

    def selected_priority_order(self) -> List[str]:
        data = self.priority_preset.currentData()
        if data == "__selected__":
            return self.selected_quality_then_lower()
        if isinstance(data, list):
            return list(data)
        return []

    def selected_quality_then_lower(self) -> List[str]:
        selected = AudioQuality[self.audio_quality.currentData()]
        names = [item.name for item in QUALITY_ORDER]
        start = names.index(selected.name)
        return names[start:]

    def set_priority_preset(self, order: List[str]):
        self.remove_custom_priority_preset()
        if not order:
            for index in range(self.priority_preset.count()):
                if self.priority_preset.itemData(index) == []:
                    self.priority_preset.setCurrentIndex(index)
                    return
            self.priority_preset.setCurrentIndex(0)
            return

        selected_order = self.selected_quality_then_lower()
        for index in range(self.priority_preset.count()):
            data = self.priority_preset.itemData(index)
            if data == order or (data == "__selected__" and selected_order == order):
                self.priority_preset.setCurrentIndex(index)
                return

        label = "Custom saved: " + " > ".join(order)
        self.priority_preset.addItem(label, order)
        self.priority_preset.setCurrentIndex(self.priority_preset.count() - 1)

    def remove_custom_priority_preset(self):
        for index in range(self.priority_preset.count() - 1, -1, -1):
            if self.priority_preset.itemText(index).startswith("Custom saved: "):
                self.priority_preset.removeItem(index)

    def save_settings(self):
        values = {
            "downloadPath": self.download_path.text().strip(),
            "audioQuality": self.audio_quality.currentData(),
            "videoQuality": self.video_quality.currentData(),
            "audioQualityPriority": self.selected_priority_order(),
            "albumFolderFormat": self.album_format.text(),
            "playlistFolderFormat": self.playlist_format.text(),
            "trackFileFormat": self.track_format.text(),
            "videoFileFormat": self.video_format.text(),
            "language": self.language.currentData(),
            "apiKeyIndex": self.api_client.currentData(),
        }
        values.update({key: checkbox.isChecked() for key, checkbox in self.checks.items()})
        values["requestIntervalSeconds"] = float(self.request_interval.value())
        self.backend.save_settings(values)
        self.settings_status.setText("Settings saved.")

    def refresh_auth_status(self):
        status = self.backend.auth_status()
        self.auth_label.setText(status.label)
        self.country_label.setText(f"Country: {status.country_code or 'unknown'}")
        self.expiry_label.setText(f"Expires: {status.expires_label}")

    def refresh_saved_login(self):
        self.refresh_login_button.setEnabled(False)
        self.account_log.append("Refreshing saved login...")
        worker = TaskWorker(self.backend.refresh_saved_login)
        worker.signals.result.connect(lambda status: (self.refresh_auth_status(), self.account_log.append(status.label)))
        worker.signals.error.connect(lambda message: self.account_log.append(message))
        worker.signals.finished.connect(lambda: self.refresh_login_button.setEnabled(True))
        self.start_worker(worker)

    def start_device_login(self):
        self.device_login_button.setEnabled(False)
        self.account_log.append("Requesting device login...")
        worker = TaskWorker(self.backend.start_device_login)
        worker.signals.result.connect(self._device_login_started)
        worker.signals.error.connect(self._device_login_error)
        self.start_worker(worker)

    def _device_login_started(self, challenge):
        self.login_url.setText(challenge.url)
        self.account_log.append(f"Open {challenge.url}")
        self.account_log.append(f"Code: {challenge.user_code}")
        self.login_polling = True
        self.login_poll_inflight = False
        self.poll_timer.start(max(1, challenge.interval) * 1000)

    def _device_login_error(self, message: str):
        self.device_login_button.setEnabled(True)
        self.account_log.append(message)

    def _poll_device_login(self):
        if not self.login_polling or self.login_poll_inflight:
            return
        self.login_poll_inflight = True
        worker = TaskWorker(self.backend.poll_device_login)
        worker.signals.result.connect(self._device_login_polled)
        worker.signals.error.connect(lambda message: self.account_log.append(message))
        worker.signals.finished.connect(self._device_login_poll_finished)
        self.start_worker(worker)

    def _device_login_polled(self, status):
        self.refresh_auth_status()
        if status.has_token:
            self.poll_timer.stop()
            self.login_polling = False
            self.device_login_button.setEnabled(True)
            self.account_log.append("Login complete.")

    def _device_login_poll_finished(self):
        self.login_poll_inflight = False

    def open_login_url(self):
        if self.login_url.text():
            webbrowser.open(self.login_url.text())

    def logout(self):
        self.backend.logout()
        self.refresh_auth_status()
        self.account_log.append("Logged out.")

    def login_with_token(self):
        access_token = self.access_token.text().strip()
        if not access_token:
            self.account_log.append("Enter an access token first.")
            return
        self.token_login_button.setEnabled(False)
        self.account_log.append("Saving manual token...")
        worker = TaskWorker(
            self.backend.login_by_access_token,
            access_token,
            self.refresh_token.text(),
        )
        worker.signals.result.connect(lambda status: (self.refresh_auth_status(), self.account_log.append(status.label)))
        worker.signals.error.connect(lambda message: self.account_log.append(message))
        worker.signals.finished.connect(lambda: self.token_login_button.setEnabled(True))
        self.start_worker(worker)

    def run_doctor(self):
        self.account_log.append("Running doctor...")
        worker = TaskWorker(self.backend.run_doctor)
        worker.signals.result.connect(lambda output: self.account_log.append(output.strip()))
        worker.signals.error.connect(lambda message: self.account_log.append(message))
        self.start_worker(worker)

    def update_tidekeeper(self, include_gui: bool):
        target = "terminal and GUI" if include_gui else "terminal"
        self.account_log.append(f"Updating {target} install...")
        self.update_terminal_button.setEnabled(False)
        self.update_gui_button.setEnabled(False)
        worker = TaskWorker(self.backend.update_app, include_gui)
        worker.signals.result.connect(lambda output: self.account_log.append(output.strip()))
        worker.signals.error.connect(lambda message: self.account_log.append(message))
        worker.signals.finished.connect(self._update_finished)
        self.start_worker(worker)

    def _update_finished(self):
        self.update_terminal_button.setEnabled(True)
        self.update_gui_button.setEnabled(True)

    def prepare_demo_state(self):
        self.search_text.setText("midnight")
        self.direct_text.setText("https://tidal.com/browse/track/70973230")
        self.set_search_results(self.backend.search("midnight", Type.Track))
        if self.results:
            self.results_table.selectRow(0)
            self.queue = self.results[:28]
            self.refresh_queue_table()
            self.queue_table.selectRow(0)
            self.download_log.setPlainText(
                "\n".join(
                    f"Queued {item.title} - waiting for download slot"
                    for item in self.queue
                )
                + "\n"
            )
        self.login_url.setText("https://login.tidal.com/DEMO-CODE")
        self.account_log.setPlainText(
            self.backend.run_doctor()
            + "\n"
            + "\n".join(f"History {index + 1:02d}: token and client checks passed" for index in range(20))
        )


def configure_application_theme(app: QApplication):
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#f5f7fb"))
    palette.setColor(QPalette.WindowText, QColor("#172033"))
    palette.setColor(QPalette.Base, QColor("#ffffff"))
    palette.setColor(QPalette.AlternateBase, QColor("#f8fafc"))
    palette.setColor(QPalette.Text, QColor("#172033"))
    palette.setColor(QPalette.Button, QColor("#ffffff"))
    palette.setColor(QPalette.ButtonText, QColor("#172033"))
    palette.setColor(QPalette.Highlight, QColor("#0f766e"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
    palette.setColor(QPalette.ToolTipText, QColor("#172033"))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#98a2b3"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#98a2b3"))
    app.setPalette(palette)
    hints = app.styleHints()
    if hasattr(hints, "setColorScheme"):
        hints.setColorScheme(Qt.ColorScheme.Light)


def run_app(backend: TidekeeperBackend):
    app = QApplication.instance() or QApplication([])
    configure_application_theme(app)
    backend.initialize()
    window = MainWindow(backend)
    window.show()
    return app.exec()
