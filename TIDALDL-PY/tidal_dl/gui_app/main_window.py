"""Main application window for the Tidekeeper desktop GUI.

Layout
------
A fixed dark sidebar on the left hosts navigation, a live session card and
the version label. A ``QStackedWidget`` on the right holds the four pages
(search, queue, settings, account). Presentation helpers live in
:mod:`tidal_dl.gui_app.widgets`; this module owns behaviour.

All public attribute names from the previous version are preserved so the
tests and ``scripts/gui_screenshots.py`` keep working.
"""

from __future__ import annotations

import time
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
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
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
from .style import APP_STYLESHEET, TABLE_TEXT_COLOR, TOKENS
from .widgets import (
    PROGRESS_PERCENT_ROLE,
    PROGRESS_STATE_ROLE,
    Card,
    Chip,
    NavButton,
    QueueProgressDelegate,
    TableStack,
    button,
    configure_table,
    field_label,
    fix_columns,
    hint,
    label,
    log_view,
    scroll_area,
)
from .workers import DownloadWorker, TaskWorker

__all__ = [
    "MainWindow",
    "SCREEN_ORDER",
    "QueueProgressDelegate",
    "PROGRESS_PERCENT_ROLE",
    "configure_application_theme",
    "run_app",
]

SCREEN_ORDER = ("search", "queue", "settings", "account")
NAV_SECTIONS = (
    ("Library", (("search", "Search"), ("queue", "Queue"))),
    ("System", (("settings", "Settings"), ("account", "Account"))),
)
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
NAMING_HINT = (
    "Placeholders: {ArtistName} {AlbumArtistName} {AlbumTitle} {AlbumYear} "
    "{TrackNumber} {TrackTitle} {PlaylistName} {VideoTitle} {Quality} {Flag}"
)
RESULTS_EMPTY = "Search the TIDAL catalog or paste a link above.\nResults appear here."
QUEUE_EMPTY = "The queue is empty.\nAdd items from Search or paste links into Direct download."


class MainWindow(QMainWindow):
    def __init__(self, backend: TidekeeperBackend):
        super().__init__()
        self.backend = backend
        self.thread_pool = QThreadPool.globalInstance()
        self.results: List[SearchItem] = []
        self.result_history: List[Tuple[List[SearchItem], str]] = []
        self.queue: List[SearchItem] = []
        self.nav_buttons: Dict[str, NavButton] = {}
        self.active_workers = set()
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_device_login)
        self.login_polling = False
        self.login_poll_inflight = False
        self.login_deadline = 0
        self.search_in_progress = False
        self.download_in_progress = False
        self.download_worker = None
        self._cancel_requested = False

        self.setWindowTitle("Tidekeeper")
        self.setMinimumSize(1040, 680)
        self.resize(1220, 820)
        self.setStyleSheet(APP_STYLESHEET)
        self._build()
        # Keep the interval spin box at its styled hint height even when the
        # settings page is squeezed vertically inside its scroll area.
        self.request_interval.ensurePolished()
        self.request_interval.setMinimumHeight(self.request_interval.sizeHint().height())
        self.version_label.setText(f"v{self.backend.version()}")
        self.refresh_settings()
        self.refresh_auth_status()
        self.update_action_states()
        self.show_screen("search")

    # ------------------------------------------------------------------ build

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
        sidebar.setFixedWidth(220)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 22, 14, 16)
        layout.setSpacing(4)

        brand_box = QVBoxLayout()
        brand_box.setContentsMargins(12, 0, 12, 0)
        brand_box.setSpacing(0)
        brand_box.addWidget(label("Tidekeeper", "Brand"))
        brand_box.addWidget(label("Desktop downloader", "BrandSub"))
        layout.addLayout(brand_box)
        layout.addSpacing(22)

        for section_title, entries in NAV_SECTIONS:
            layout.addWidget(label(section_title.upper(), "NavSection"))
            layout.addSpacing(2)
            for name, title in entries:
                nav = NavButton(title)
                nav.clicked.connect(lambda checked=False, screen=name: self.show_screen(screen))
                self.nav_buttons[name] = nav
                layout.addWidget(nav)
            layout.addSpacing(14)

        layout.addStretch(1)

        self.session_card = QFrame()
        self.session_card.setObjectName("SessionCard")
        self.session_card.setCursor(Qt.PointingHandCursor)
        self.session_card.setToolTip("Open the Account page.")
        self.session_card.mousePressEvent = lambda event: self.show_screen("account")
        card_layout = QVBoxLayout(self.session_card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(2)
        self.session_title = label("Signed out", "SessionTitle")
        self.session_detail = label("Sign in from Account", "SidebarMuted")
        card_layout.addWidget(self.session_title)
        card_layout.addWidget(self.session_detail)
        layout.addWidget(self.session_card)
        layout.addSpacing(8)

        self.version_label = label("Ready", "SidebarMuted")
        self.version_label.setContentsMargins(12, 0, 0, 0)
        layout.addWidget(self.version_label)
        return sidebar

    def _page(self, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout, QHBoxLayout]:
        page = QWidget()
        page.setObjectName("Page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(16)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(12)
        titles = QVBoxLayout()
        titles.setContentsMargins(0, 0, 0, 0)
        titles.setSpacing(2)
        titles.addWidget(label(title, "PageTitle"))
        if subtitle:
            titles.addWidget(label(subtitle, "PageSubtitle"))
        header.addLayout(titles, 1)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        header.addLayout(actions)
        layout.addLayout(header)
        return page, layout, actions

    # ----------------------------------------------------------------- search

    def _build_search_page(self) -> QWidget:
        page, layout, _ = self._page("Search", "Find music in the TIDAL catalog or download links directly")

        # -- Catalog search -------------------------------------------------
        search_card = Card("Catalog search", "Pick a content type, then type a name or paste a TIDAL URL.")
        self.search_type = QComboBox()
        self.search_type.addItem("All", Type.Null)
        for item in (Type.Track, Type.Album, Type.Playlist, Type.Artist, Type.Video):
            self.search_type.addItem(item.name, item)
        self.search_type.setFixedWidth(140)
        self.search_type.setToolTip("Content type to search for.")
        self.search_text = QLineEdit()
        self.search_text.setPlaceholderText("Artist, album, track, playlist or TIDAL URL")
        self.search_text.setClearButtonEnabled(True)
        self.search_button = button("Search", primary=True, tooltip="Search TIDAL for the selected content type.")
        self.search_button.setMinimumWidth(110)
        self.search_button.clicked.connect(self.run_search)
        self.search_text.returnPressed.connect(self.run_search)
        self.search_text.textChanged.connect(self.update_search_action)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.search_type)
        row.addWidget(self.search_text, 1)
        row.addWidget(self.search_button)
        search_card.add_layout(row)
        search_card.add_widget(hint("Tip: double-click an Artist row to browse their tracks, or use View Videos."))

        # -- Direct download ------------------------------------------------
        direct_card = Card(
            "Direct download",
            "One TIDAL URL or ID per line, comma-separated IDs, or the path to a .txt list.",
        )
        self.direct_text = QTextEdit()
        self.direct_text.setObjectName("DirectInput")
        self.direct_text.setAcceptRichText(False)
        self.direct_text.setPlaceholderText("https://tidal.com/browse/album/...  or  70973230, 70973231")
        self.direct_text.setFixedHeight(76)
        self.direct_video_only = QCheckBox("Videos only")
        self.direct_video_only.setToolTip(
            "Skip audio tracks for artist, album, playlist, mix, video, or file downloads."
        )
        self.direct_browse_button = button("Choose file...", tooltip="Pick a text file containing TIDAL URLs.")
        self.direct_queue_button = button("Add to Queue", tooltip="Add each pasted URL, ID, or file line to the queue.")
        self.direct_download_button = button(
            "Download", primary=True, tooltip="Queue and start every pasted URL, ID, or file line."
        )
        self.direct_browse_button.clicked.connect(self.browse_direct_file)
        self.direct_queue_button.clicked.connect(self.add_direct_to_queue)
        self.direct_download_button.clicked.connect(self.download_direct)
        self.direct_text.textChanged.connect(self.update_direct_actions)
        direct_card.add_widget(self.direct_text)
        direct_row = QHBoxLayout()
        direct_row.setSpacing(8)
        direct_row.addWidget(self.direct_browse_button)
        direct_row.addWidget(self.direct_video_only)
        direct_row.addStretch(1)
        direct_row.addWidget(self.direct_queue_button)
        direct_row.addWidget(self.direct_download_button)
        direct_card.add_layout(direct_row)

        top = QHBoxLayout()
        top.setSpacing(14)
        top.addWidget(search_card, 5)
        top.addWidget(direct_card, 4)
        layout.addLayout(top)

        # -- Results --------------------------------------------------------
        results_header = QHBoxLayout()
        results_header.setSpacing(10)
        results_header.addWidget(label("Results", "CardTitle"))
        self.results_count_chip = Chip("0 items", "neutral")
        results_header.addWidget(self.results_count_chip)
        self.search_status = label("No search run yet.", "Muted")
        results_header.addWidget(self.search_status, 1)
        self.back_results_button = button("Back", ghost=True, tooltip="Return to the previous result list.")
        self.artist_videos_button = button("View Videos", tooltip="Replace an Artist result with its videos.")
        self.back_results_button.clicked.connect(self.show_previous_results)
        self.artist_videos_button.clicked.connect(self.view_selected_artist_videos)
        results_header.addWidget(self.back_results_button)
        results_header.addWidget(self.artist_videos_button)
        layout.addLayout(results_header)

        self.results_table = QTableWidget(0, 6)
        configure_table(self.results_table, ["Type", "Title", "Artists", "Quality", "Duration", "ID"])
        fix_columns(self.results_table, {0: 90, 3: 140, 4: 90, 5: 120})
        self.results_table.itemSelectionChanged.connect(self.update_result_actions)
        self.results_table.itemDoubleClicked.connect(self.open_result_item)
        self.results_stack = TableStack(self.results_table, RESULTS_EMPTY)
        layout.addWidget(self.results_stack, 1)

        action_layout = QHBoxLayout()
        action_layout.setSpacing(8)
        self.selection_label = label("Nothing selected", "Muted")
        action_layout.addWidget(self.selection_label, 1)
        self.result_video_only = QCheckBox("Videos only")
        self.result_video_only.setToolTip("Queue or download selected rows in videos-only mode.")
        self.add_queue_button = button("Add to Queue", tooltip="Add selected rows to the queue.")
        self.download_now_button = button("Download Now", primary=True, tooltip="Add selected rows and start downloading.")
        self.add_queue_button.clicked.connect(self.add_selected_to_queue)
        self.download_now_button.clicked.connect(self.download_selected)
        action_layout.addWidget(self.result_video_only)
        action_layout.addWidget(self.add_queue_button)
        action_layout.addWidget(self.download_now_button)
        layout.addLayout(action_layout)
        return page

    # ------------------------------------------------------------------ queue

    def _build_queue_page(self) -> QWidget:
        page, layout, header_actions = self._page("Queue", "Everything waiting to download, in progress, or finished")

        self.remove_queue_button = button("Remove", ghost=True, tooltip="Remove selected queue rows.")
        self.clear_queue_button = button("Clear", ghost=True, tooltip="Clear the queue and output log.")
        self.retry_failed_button = button("Retry Failed", tooltip="Re-queue items that failed and download them again.")
        self.cancel_queue_button = button("Cancel", danger=True, tooltip="Stop after the current item finishes.")
        self.start_queue_button = button(
            "Start Queue", primary=True, tooltip="Download queued and failed items. Completed rows are skipped."
        )
        self.start_queue_button.setMinimumWidth(130)
        self.remove_queue_button.clicked.connect(self.remove_selected_queue_items)
        self.clear_queue_button.clicked.connect(self.clear_queue)
        self.retry_failed_button.clicked.connect(self.retry_failed_downloads)
        self.cancel_queue_button.clicked.connect(self.cancel_downloads)
        self.start_queue_button.clicked.connect(self.start_queue_download)
        for widget in (
            self.remove_queue_button,
            self.clear_queue_button,
            self.retry_failed_button,
            self.cancel_queue_button,
            self.start_queue_button,
        ):
            header_actions.addWidget(widget)

        summary = QHBoxLayout()
        summary.setSpacing(8)
        self.queue_chip_total = Chip("0 total", "neutral")
        self.queue_chip_pending = Chip("0 queued", "info")
        self.queue_chip_active = Chip("0 downloading", "warning")
        self.queue_chip_done = Chip("0 done", "success")
        self.queue_chip_failed = Chip("0 failed", "danger")
        for chip in (
            self.queue_chip_total,
            self.queue_chip_pending,
            self.queue_chip_active,
            self.queue_chip_done,
            self.queue_chip_failed,
        ):
            summary.addWidget(chip)
        self.queue_status = label("Queue is empty.", "Muted")
        summary.addWidget(self.queue_status, 1)
        layout.addLayout(summary)

        self.queue_table = QTableWidget(0, 6)
        configure_table(self.queue_table, ["Type", "Title", "Artists", "Quality", "Status", "Progress"])
        fix_columns(self.queue_table, {0: 110, 3: 140, 4: 240, 5: 140})
        self.queue_table.setItemDelegateForColumn(5, QueueProgressDelegate(self.queue_table))
        self.queue_table.itemSelectionChanged.connect(self.update_queue_actions)
        self.queue_stack = TableStack(self.queue_table, QUEUE_EMPTY)

        log_box = QWidget()
        log_layout = QVBoxLayout(log_box)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(6)
        log_layout.addWidget(label("Output", "CardTitle"))
        self.download_log = log_view("Download output appears here while the queue runs.")
        log_layout.addWidget(self.download_log, 1)

        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.queue_stack)
        splitter.addWidget(log_box)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([520, 190])
        layout.addWidget(splitter, 1)
        return page

    # --------------------------------------------------------------- settings

    def _build_settings_page(self) -> QWidget:
        page, layout, header_actions = self._page("Settings", "Storage, quality, library behaviour and file naming")

        self.settings_status = label("Settings loaded.", "Muted")
        reload_button = button("Reload", ghost=True, tooltip="Discard unsaved changes and reload from disk.")
        save_button = button("Save Settings", primary=True, tooltip="Write these settings to disk.")
        reload_button.clicked.connect(self.refresh_settings)
        save_button.clicked.connect(self.save_settings)
        header_actions.addWidget(self.settings_status)
        header_actions.addSpacing(6)
        header_actions.addWidget(reload_button)
        header_actions.addWidget(save_button)

        # Widgets ------------------------------------------------------------
        self.download_path = QLineEdit()
        self.download_path.setPlaceholderText("Folder where downloads are written")
        browse = button("Browse...", tooltip="Choose a download folder.")
        open_folder = button("Open", ghost=True, tooltip="Open the current download folder.")
        open_folder.clicked.connect(self.open_download_folder)
        browse.clicked.connect(self.browse_download_path)
        path_layout = QHBoxLayout()
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(8)
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
        for preset_label, order in PRIORITY_PRESETS:
            self.priority_preset.addItem(preset_label, order)
        self.priority_preset.setMinimumContentsLength(18)
        self.priority_preset.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.priority_preset.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.language = QComboBox()
        for index, name in self.backend.language_choices():
            self.language.addItem(name, index)
        self.api_client = QComboBox()
        for item in self.backend.api_clients():
            status = "OK" if item["valid"] else "old"
            self.api_client.addItem(f'{item["index"]} {status} - {item["platform"]}', item["index"])
            self.api_client.setItemData(
                self.api_client.count() - 1,
                f'{item["index"]} {status} - {item["platform"]} ({item["formats"]})',
                Qt.ToolTipRole,
            )
        self.api_client.setMinimumContentsLength(18)
        self.api_client.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.api_client.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

        self.checks = {}
        for key, text in (
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
            ("adaptiveRateLimit", "Automatically adapt request delay"),
            ("saveAsFlac", "Save FLAC as .flac files"),
            ("usePlaylistFolder", "Use playlist folders"),
        ):
            self.checks[key] = QCheckBox(text)

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

        # Layout -------------------------------------------------------------
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(14)
        top_layout.addWidget(self._build_storage_settings_panel(path_layout), 5)
        top_layout.addWidget(self._build_quality_settings_panel(), 4)
        content_layout.addLayout(top_layout)
        content_layout.addWidget(self._build_library_settings_panel())
        content_layout.addWidget(self._build_naming_settings_panel())
        content_layout.addStretch(1)
        layout.addWidget(scroll_area(content), 1)
        return page

    @staticmethod
    def _form_grid() -> QGridLayout:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        grid.setColumnMinimumWidth(0, 110)
        grid.setColumnStretch(1, 1)
        return grid

    def _build_storage_settings_panel(self, path_layout: QHBoxLayout) -> QFrame:
        card = Card("Storage & client", "Where files go and which TIDAL client Tidekeeper identifies as.")
        grid = self._form_grid()
        grid.addWidget(field_label("Download path"), 0, 0)
        grid.addLayout(path_layout, 0, 1)
        grid.addWidget(field_label("Language"), 1, 0)
        grid.addWidget(self.language, 1, 1)
        grid.addWidget(field_label("TIDAL client"), 2, 0)
        grid.addWidget(self.api_client, 2, 1)
        card.add_layout(grid)
        card.add_widget(hint("Changing the client requires signing in again."))
        return card

    def _build_quality_settings_panel(self) -> QFrame:
        card = Card("Quality", "Preferred stream quality and what to fall back to.")
        grid = self._form_grid()
        grid.setColumnMinimumWidth(0, 80)
        grid.addWidget(field_label("Audio"), 0, 0)
        grid.addWidget(self.audio_quality, 0, 1)
        grid.addWidget(field_label("Fallback"), 1, 0)
        grid.addWidget(self.priority_preset, 1, 1)
        grid.addWidget(field_label("Video"), 2, 0)
        grid.addWidget(self.video_quality, 2, 1)
        card.add_layout(grid)
        card.add_widget(hint("Fallback is used when the requested stream is blocked or unavailable."))
        return card

    def _build_library_settings_panel(self) -> QFrame:
        card = Card("Library behaviour", "What gets saved alongside the audio and how downloads run.")
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(4)
        groups = [
            ("Files", ["checkExist", "saveCovers", "lyricFile", "saveAlbumInfo", "usePlaylistFolder"]),
            ("Catalog", ["includeEP", "downloadVideos"]),
            ("Run behaviour", ["multiThread", "downloadDelay", "adaptiveRateLimit", "saveAsFlac"]),
            ("Console output", ["showProgress", "showTrackInfo"]),
        ]
        for column, (title, keys) in enumerate(groups):
            grid.addWidget(field_label(title), 0, column)
            for row, key in enumerate(keys, start=1):
                grid.addWidget(self.checks[key], row, column)
            grid.setColumnStretch(column, 1)
        interval_col = len(groups)
        grid.addWidget(field_label("Request interval"), 0, interval_col)
        grid.addWidget(self.request_interval, 1, interval_col)
        grid.addWidget(hint("Minimum gap between playback requests."), 2, interval_col, 1, 1)
        grid.setColumnStretch(interval_col, 1)
        card.add_layout(grid)
        return card

    def _build_naming_settings_panel(self) -> QFrame:
        card = Card("File naming", "Folder and file name templates.")
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)
        fields = (
            ("Album folder", self.album_format, 0, 0),
            ("Playlist folder", self.playlist_format, 0, 1),
            ("Track file", self.track_format, 2, 0),
            ("Video file", self.video_format, 2, 1),
        )
        for text, widget, row, column in fields:
            widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            grid.addWidget(field_label(text), row, column)
            grid.addWidget(widget, row + 1, column)
            grid.setColumnStretch(column, 1)
        card.add_layout(grid)
        card.add_widget(hint(NAMING_HINT))
        return card

    # ---------------------------------------------------------------- account

    def _build_account_page(self) -> QWidget:
        page, layout, _ = self._page("Account", "TIDAL session, sign-in and maintenance")

        content = QWidget()
        panels_layout = QVBoxLayout(content)
        panels_layout.setContentsMargins(0, 0, 0, 0)
        panels_layout.setSpacing(14)

        # Status ------------------------------------------------------------
        status_card = Card("Session")
        self.auth_label = label("Signed out", "StatusPill")
        self.auth_label.setProperty("state", "out")
        self.auth_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.country_label = label("Country: unknown", "Muted")
        self.expiry_label = label("Expires: unknown", "Muted")
        self.logout_button = button("Log Out", danger=True, tooltip="Remove the saved local login.")
        self.refresh_login_button = button("Refresh Saved Login", tooltip="Refresh the saved token if possible.")
        self.logout_button.clicked.connect(self.logout)
        self.refresh_login_button.clicked.connect(self.refresh_saved_login)
        status_row = QHBoxLayout()
        status_row.setSpacing(16)
        status_row.addWidget(self.auth_label)
        details = QVBoxLayout()
        details.setSpacing(2)
        details.addWidget(self.country_label)
        details.addWidget(self.expiry_label)
        status_row.addLayout(details, 1)
        status_row.addWidget(self.refresh_login_button)
        status_row.addWidget(self.logout_button)
        status_card.add_layout(status_row)
        panels_layout.addWidget(status_card)

        # Sign in -----------------------------------------------------------
        signin_row = QHBoxLayout()
        signin_row.setSpacing(14)

        login_card = Card("Device login", "Recommended. Sign in through tidal.com with a one-time code.")
        self.login_url = QLineEdit()
        self.login_url.setReadOnly(True)
        self.login_url.setPlaceholderText("Device login URL appears here")
        self.login_code_label = label("", "Code")
        self.login_code_label.setAlignment(Qt.AlignCenter)
        self.login_code_label.hide()
        self.device_login_button = button("Start Device Login", primary=True, tooltip="Start TIDAL device login.")
        self.open_login_button = button("Open in Browser", tooltip="Open the device login URL in your browser.")
        self.device_login_button.clicked.connect(self.start_device_login)
        self.open_login_button.clicked.connect(self.open_login_url)
        login_card.add_widget(self.login_url)
        login_card.add_widget(self.login_code_label)
        login_buttons = QHBoxLayout()
        login_buttons.setSpacing(8)
        login_buttons.addWidget(self.device_login_button)
        login_buttons.addWidget(self.open_login_button)
        login_buttons.addStretch(1)
        login_card.add_layout(login_buttons)
        signin_row.addWidget(login_card, 1)

        token_card = Card("Manual token", "Advanced. Paste tokens copied from another signed-in client.")
        self.access_token = QLineEdit()
        self.access_token.setEchoMode(QLineEdit.Password)
        self.access_token.setPlaceholderText("Access token")
        self.refresh_token = QLineEdit()
        self.refresh_token.setEchoMode(QLineEdit.Password)
        self.refresh_token.setPlaceholderText("Refresh token (optional)")
        self.token_login_button = button("Save Token", tooltip="Save a manually supplied TIDAL token.")
        self.token_login_button.clicked.connect(self.login_with_token)
        token_card.add_widget(self.access_token)
        token_card.add_widget(self.refresh_token)
        token_buttons = QHBoxLayout()
        token_buttons.addStretch(1)
        token_buttons.addWidget(self.token_login_button)
        token_card.add_layout(token_buttons)
        signin_row.addWidget(token_card, 1)
        panels_layout.addLayout(signin_row)

        # Maintenance -------------------------------------------------------
        maintenance_card = Card("Maintenance", "Diagnose the install or pull the latest version from GitHub.")
        self.doctor_button = button("Run Doctor", tooltip="Check auth, download path, client, and local tools.")
        self.update_terminal_button = button("Update Terminal", tooltip="Update the terminal install from GitHub.")
        self.update_gui_button = button(
            "Update Terminal + GUI", primary=True, tooltip="Update the terminal and GUI install from GitHub."
        )
        self.doctor_button.clicked.connect(self.run_doctor)
        self.update_terminal_button.clicked.connect(lambda: self.update_tidekeeper(False))
        self.update_gui_button.clicked.connect(lambda: self.update_tidekeeper(True))
        maintenance_row = QHBoxLayout()
        maintenance_row.setSpacing(8)
        maintenance_row.addWidget(self.doctor_button)
        maintenance_row.addStretch(1)
        maintenance_row.addWidget(self.update_terminal_button)
        maintenance_row.addWidget(self.update_gui_button)
        maintenance_card.add_layout(maintenance_row)
        panels_layout.addWidget(maintenance_card)

        log_box = QWidget()
        log_layout = QVBoxLayout(log_box)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(6)
        log_layout.addWidget(label("Output", "CardTitle"))
        self.account_log = log_view("Login, doctor and update output appears here.")
        log_layout.addWidget(self.account_log, 1)

        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(scroll_area(content))
        splitter.addWidget(log_box)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([460, 220])
        layout.addWidget(splitter, 1)
        return page

    # ---------------------------------------------------------------- helpers

    def _table_cell(self, value, item=None) -> QTableWidgetItem:
        cell = QTableWidgetItem(str(value))
        cell.setForeground(QColor(TABLE_TEXT_COLOR))
        if item is not None:
            cell.setData(Qt.UserRole, item)
        return cell

    def _update_request_interval_enabled(self, enabled: bool):
        self.request_interval.setEnabled(enabled)

    def _row_item(self, table: QTableWidget, row: int):
        cell = table.item(row, 0)
        if cell is None:
            return None
        return cell.data(Qt.UserRole)

    @staticmethod
    def _plural(count: int, word: str) -> str:
        return f"{count} {word}{'' if count == 1 else 's'}"

    def show_screen(self, name: str):
        if name not in self.pages:
            return
        self.stack.setCurrentWidget(self.pages[name])
        for key, nav in self.nav_buttons.items():
            nav.set_active(key == name)

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

    # ----------------------------------------------------------------- search

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
        self.results_stack.set_empty(not items)
        if not items:
            self.results_stack.set_empty_text("No results.\nTry another term or content type.")
        self.results_count_chip.setText(self._plural(len(items), "item"))
        self.search_status.setText(status_text or f"{self._plural(len(items), 'result')}.")
        self.update_result_actions()

    def _search_finished(self):
        self.search_in_progress = False
        self.update_search_action()
        self.update_result_actions()

    def show_search_error(self, message: str):
        self.search_status.setText(message)
        QMessageBox.warning(self, "Search failed", message)

    def _load_artist_children(self, item: SearchItem, loader, noun: str):
        self.result_history.append((list(self.results), self.search_status.text()))
        self.search_in_progress = True
        self.search_status.setText(f"Loading {noun}s by {item.title}...")
        self.update_search_action()
        self.update_result_actions()
        worker = TaskWorker(loader, item)
        worker.signals.result.connect(
            lambda items, artist=item.title: self.set_search_results(
                items, f"{self._plural(len(items), noun)} by {artist}."
            )
        )
        worker.signals.error.connect(self.show_search_error)
        worker.signals.finished.connect(self._search_finished)
        self.start_worker(worker)

    def open_result_item(self, cell: QTableWidgetItem):
        item = self._row_item(self.results_table, cell.row())
        if item is None:
            return
        if item.kind != Type.Artist:
            self.search_status.setText("Double-click Artist results to view tracks.")
            return
        if self.search_in_progress:
            return
        self._load_artist_children(item, self.backend.artist_tracks, "track")

    def view_selected_artist_videos(self):
        items = self.selected_result_items()
        if len(items) != 1 or items[0].kind != Type.Artist:
            self.search_status.setText("Select one artist row first.")
            return
        if self.search_in_progress:
            return
        self._load_artist_children(items[0], self.backend.artist_videos, "video")

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

    def add_selected_to_queue(self):
        items = self.video_mode_items(self.selected_result_items(), self.result_video_only.isChecked())
        if not items:
            self.search_status.setText("Select one or more rows first.")
            return
        self.queue.extend(items)
        self.refresh_queue_table()
        self.search_status.setText(f"Added {self._plural(len(items), 'item')} to queue.")

    # ----------------------------------------------------------------- direct

    def browse_direct_file(self):
        current = self.direct_text.toPlainText().strip().splitlines()
        start_dir = current[0] if current else ""
        path, _ = QFileDialog.getOpenFileName(self, "URL list", start_dir, "Text files (*.txt);;All files (*)")
        if path:
            self.direct_text.setPlainText(path)

    def direct_item_from_input(self):
        items = self.direct_items_from_input()
        return items[0] if items else None

    def direct_items_from_input(self) -> List[SearchItem]:
        text = self.direct_text.toPlainText()
        tokens = parse_direct_inputs(text)
        if not tokens:
            self.search_status.setText("Enter a URL, ID, mix ID, or .txt file.")
            return []
        video_only = self.direct_video_only.isChecked()
        return [with_video_only(self.backend.direct_item(token), video_only) for token in tokens]

    def add_direct_to_queue(self):
        items = self.direct_items_from_input()
        if not items:
            return
        self.queue.extend(items)
        self.refresh_queue_table()
        self.search_status.setText(f"Added {self._plural(len(items), 'direct item')} to queue.")

    def download_direct(self):
        if self.download_in_progress:
            self.search_status.setText("A download is already running.")
            return
        items = self.direct_items_from_input()
        if not items:
            return
        self.queue.extend(items)
        self.refresh_queue_table()
        self.show_screen("queue")
        self.start_downloads(items)

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

    # ------------------------------------------------------------------ queue

    def _queue_kind_label(self, item: SearchItem) -> str:
        kind = "Direct" if item.kind == Type.Null else item.kind.name
        if item.video_only and item.kind != Type.Video:
            kind += " videos"
        return kind

    def _queue_status_text(self, item: SearchItem) -> str:
        status = item.status or "Queued"
        if status == "Downloading" and item.progress_label:
            return f"Downloading {item.progress_label}"
        return status

    def _queue_progress_text(self, item: SearchItem) -> str:
        if item.status == "Done":
            return "100%"
        if item.progress_percent:
            return f"{item.progress_percent}%"
        if item.status == "Downloading":
            return "0%"
        return ""

    @staticmethod
    def _queue_progress_state(item: SearchItem) -> str:
        if item.status == "Done":
            return "done"
        if item.status == "Failed":
            return "failed"
        if item.status == "Downloading":
            return "active"
        return ""

    def _set_queue_row(self, row: int, item: SearchItem):
        values = [
            self._queue_kind_label(item),
            item.title,
            item.artists,
            item.quality,
            self._queue_status_text(item),
            self._queue_progress_text(item),
        ]
        for col, value in enumerate(values):
            cell = self.queue_table.item(row, col)
            if cell is None:
                cell = self._table_cell(value, item if col == 0 else None)
                self.queue_table.setItem(row, col, cell)
            else:
                cell.setText(str(value))
                if col == 0:
                    cell.setData(Qt.UserRole, item)
        status_cell = self.queue_table.item(row, 4)
        if status_cell is not None:
            colour = {
                "Done": TOKENS["success"],
                "Failed": TOKENS["danger"],
                "Downloading": TOKENS["accent"],
                "Cancelled": TOKENS["warning"],
            }.get(item.status or "", TABLE_TEXT_COLOR)
            status_cell.setForeground(QColor(colour))
        progress_cell = self.queue_table.item(row, 5)
        if progress_cell is not None:
            percent = 100 if item.status == "Done" else int(item.progress_percent or 0)
            progress_cell.setData(PROGRESS_PERCENT_ROLE, percent)
            progress_cell.setData(PROGRESS_STATE_ROLE, self._queue_progress_state(item))

    def refresh_queue_table(self):
        self.queue_table.setSortingEnabled(False)
        self.queue_table.setRowCount(len(self.queue))
        for row, item in enumerate(self.queue):
            self._set_queue_row(row, item)
        self.queue_table.setSortingEnabled(True)
        self.queue_stack.set_empty(not self.queue)
        self.queue_status.setText(
            "Queue is empty." if not self.queue else f"{self._plural(len(self.queue), 'item')} in queue."
        )
        self.update_queue_actions()

    def _refresh_queue_row(self, item: SearchItem):
        for row in range(self.queue_table.rowCount()):
            if self._row_item(self.queue_table, row) is item:
                self._set_queue_row(row, item)
                break
        self._update_queue_summary()

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

    def pending_queue_items(self) -> List[SearchItem]:
        return [item for item in self.queue if item.status not in ("Done", "Downloading")]

    def failed_queue_items(self) -> List[SearchItem]:
        return [item for item in self.queue if item.status == "Failed"]

    def start_queue_download(self):
        if self.download_in_progress:
            self.queue_status.setText("A download is already running.")
            return
        items = self.pending_queue_items()
        if not items:
            self.queue_status.setText("Nothing left to download.")
            return
        self.start_downloads(items)

    def retry_failed_downloads(self):
        if self.download_in_progress:
            self.queue_status.setText("A download is already running.")
            return
        items = self.failed_queue_items()
        if not items:
            self.queue_status.setText("No failed items to retry.")
            return
        for item in items:
            item.status = "Queued"
            item.progress_percent = 0
            item.progress_label = ""
        self.refresh_queue_table()
        self.start_downloads(items)

    def start_downloads(self, items: List[SearchItem]):
        if self.download_in_progress:
            self.queue_status.setText("A download is already running.")
            return
        if not items:
            self.queue_status.setText("Nothing left to download.")
            return
        # Honor the Settings screen even if the user did not click Save first.
        self.apply_settings_for_download()
        self.download_in_progress = True
        self._cancel_requested = False
        self.update_action_states()
        self.queue_status.setText(f"Downloading {self._plural(len(items), 'item')}...")
        self.download_log.append("Starting downloads")
        worker = DownloadWorker(self.backend, items)
        self.download_worker = worker
        worker.signals.log.connect(self.append_download_log)
        worker.signals.item_status.connect(self._set_queue_item_status)
        worker.signals.item_progress.connect(self._set_queue_item_progress)
        worker.signals.result.connect(lambda _: self.queue_status.setText("Downloads finished."))
        worker.signals.error.connect(self.show_download_error)
        worker.signals.finished.connect(self._download_finished)
        self.start_worker(worker)

    def _download_finished(self):
        self.download_in_progress = False
        self.download_worker = None
        if self._cancel_requested:
            self._cancel_requested = False
            self.queue_status.setText("Downloads cancelled.")
        self.update_action_states()

    def cancel_downloads(self):
        if self.download_worker is None:
            return
        self._cancel_requested = True
        self.download_worker.cancel()
        self.cancel_queue_button.setEnabled(False)
        self.queue_status.setText("Cancelling after the current item...")

    def _set_queue_item_status(self, item, status: str):
        item.status = status
        if status == "Done":
            item.progress_percent = 100
            item.progress_label = ""
        elif status in ("Failed", "Cancelled", "Queued"):
            item.progress_percent = 0
            item.progress_label = ""
        self._refresh_queue_row(item)

    def _set_queue_item_progress(self, item, snapshot: dict):
        item.progress_label = format_queue_progress(snapshot)
        item.progress_percent = queue_progress_percent(snapshot)
        if item.status == "Downloading":
            self._refresh_queue_row(item)

    def append_download_log(self, text: str):
        cursor = self.download_log.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.download_log.setTextCursor(cursor)
        self.download_log.ensureCursorVisible()

    def show_download_error(self, message: str):
        self.queue_status.setText(message)
        QMessageBox.warning(self, "Download failed", message)

    # ---------------------------------------------------------- action states

    def update_action_states(self):
        self.update_search_action()
        self.update_direct_actions()
        self.update_result_actions()
        self.update_queue_actions()

    def update_search_action(self):
        self.search_button.setEnabled(bool(self.search_text.text().strip()) and not self.search_in_progress)

    def update_direct_actions(self):
        has_input = bool(self.direct_text.toPlainText().strip())
        self.direct_queue_button.setEnabled(has_input)
        self.direct_download_button.setEnabled(has_input and not self.download_in_progress)

    def update_result_actions(self):
        selected = self.selected_result_items()
        has_selection = bool(selected)
        has_single_artist = len(selected) == 1 and selected[0].kind == Type.Artist
        self.back_results_button.setEnabled(bool(self.result_history) and not self.search_in_progress)
        self.back_results_button.setVisible(bool(self.result_history))
        self.artist_videos_button.setEnabled(has_single_artist and not self.search_in_progress)
        self.add_queue_button.setEnabled(has_selection)
        self.download_now_button.setEnabled(has_selection and not self.download_in_progress)
        self.selection_label.setText(
            f"{self._plural(len(selected), 'row')} selected" if has_selection else "Select rows to queue or download"
        )

    def video_mode_items(self, items: List[SearchItem], video_only: bool) -> List[SearchItem]:
        if not video_only:
            return items
        return [with_video_only(item, True) for item in items]

    def _update_queue_summary(self):
        total = len(self.queue)
        done = sum(1 for item in self.queue if item.status == "Done")
        failed = len(self.failed_queue_items())
        active = sum(1 for item in self.queue if item.status == "Downloading")
        pending = total - done - failed - active
        self.queue_chip_total.setText(self._plural(total, "item"))
        self.queue_chip_pending.setText(f"{pending} queued")
        self.queue_chip_active.setText(f"{active} downloading")
        self.queue_chip_done.setText(f"{done} done")
        self.queue_chip_failed.setText(f"{failed} failed")
        self.queue_chip_active.setVisible(active > 0)
        self.queue_chip_failed.setVisible(failed > 0)
        self.nav_buttons["queue"].set_badge(pending + active)

    def update_queue_actions(self):
        has_queue = bool(self.queue)
        has_selection = bool(self.queue_table.selectionModel().selectedRows())
        has_failed = bool(self.failed_queue_items())
        has_pending = bool(self.pending_queue_items())
        self.remove_queue_button.setEnabled(has_selection and not self.download_in_progress)
        self.clear_queue_button.setEnabled(has_queue and not self.download_in_progress)
        self.retry_failed_button.setEnabled(has_failed and not self.download_in_progress)
        self.retry_failed_button.setVisible(has_failed)
        self.cancel_queue_button.setEnabled(self.download_in_progress and not self._cancel_requested)
        self.cancel_queue_button.setVisible(self.download_in_progress)
        self.start_queue_button.setEnabled(has_pending and not self.download_in_progress)
        self._update_queue_summary()

    # --------------------------------------------------------------- settings

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
        self.request_interval.setValue(
            max(0.0, float(getattr(SETTINGS, "requestIntervalSeconds", 1.0) or 0.0))
        )
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

        text = "Custom saved: " + " > ".join(order)
        self.priority_preset.addItem(text, order)
        self.priority_preset.setCurrentIndex(self.priority_preset.count() - 1)

    def remove_custom_priority_preset(self):
        for index in range(self.priority_preset.count() - 1, -1, -1):
            if self.priority_preset.itemText(index).startswith("Custom saved: "):
                self.priority_preset.removeItem(index)

    def collect_settings_values(self) -> dict:
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
        return values

    def apply_settings_for_download(self):
        """Honor unsaved quality for this run without saving or logging out."""
        self.backend.apply_runtime_settings(self.collect_settings_values(), persist_client=False)

    def save_settings(self):
        result = self.backend.save_settings(self.collect_settings_values()) or {}
        if result.get("reauth_required"):
            self.refresh_auth_status()
            self.settings_status.setText("Settings saved. Sign in again: the TIDAL client changed.")
        else:
            self.settings_status.setText("Settings saved.")

    # ---------------------------------------------------------------- account

    def refresh_auth_status(self):
        status = self.backend.auth_status()
        signed_in = bool(getattr(status, "has_token", False))
        self.auth_label.setText(status.label)
        self.auth_label.setProperty("state", "in" if signed_in else "out")
        self.auth_label.style().unpolish(self.auth_label)
        self.auth_label.style().polish(self.auth_label)
        self.country_label.setText(f"Country: {status.country_code or 'unknown'}")
        self.expiry_label.setText(f"Expires: {status.expires_label}")
        self.session_title.setText(status.label)
        self.session_detail.setText(
            f"{status.country_code or 'Unknown region'} \u00b7 expires {status.expires_label}"
            if signed_in
            else "Sign in from Account"
        )
        self.logout_button.setEnabled(signed_in)
        self.refresh_login_button.setEnabled(signed_in)

    def on_auth_result(self, status):
        """Refresh the account panel after a login/refresh worker succeeds."""
        self.refresh_auth_status()
        self.account_log.append(status.label)

    def refresh_saved_login(self):
        self.refresh_login_button.setEnabled(False)
        self.account_log.append("Refreshing saved login...")
        worker = TaskWorker(self.backend.refresh_saved_login)
        worker.signals.result.connect(self.on_auth_result)
        worker.signals.error.connect(self.account_log.append)
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
        code = getattr(challenge, "user_code", "") or ""
        self.login_code_label.setText(code)
        self.login_code_label.setVisible(bool(code))
        self.account_log.append(f"Open {challenge.url}")
        self.account_log.append(f"Code: {challenge.user_code}")
        self.login_polling = True
        self.login_poll_inflight = False
        self.login_deadline = time.time() + max(1, int(challenge.expires_in or 0))
        self.poll_timer.start(max(1, challenge.interval) * 1000)

    def _stop_device_login(self, message: str):
        self.poll_timer.stop()
        self.login_polling = False
        self.login_poll_inflight = False
        self.login_deadline = 0
        self.device_login_button.setEnabled(True)
        self.login_code_label.hide()
        if message:
            self.account_log.append(message)

    def _device_login_error(self, message: str):
        self._stop_device_login(message)

    def _poll_device_login(self):
        if not self.login_polling or self.login_poll_inflight:
            return
        if getattr(self, "login_deadline", 0) and time.time() >= self.login_deadline:
            self._stop_device_login("Login code expired. Start login again.")
            return
        self.login_poll_inflight = True
        worker = TaskWorker(self.backend.poll_device_login)
        worker.signals.result.connect(self._device_login_polled)
        worker.signals.error.connect(self._device_login_poll_error)
        worker.signals.finished.connect(self._device_login_poll_finished)
        self.start_worker(worker)

    def _device_login_polled(self, status):
        self.refresh_auth_status()
        if getattr(status, "fresh_login", False):
            self._stop_device_login("Login complete.")

    def _device_login_poll_error(self, message: str):
        lowered = (message or "").lower()
        if "expired" in lowered or "denied" in lowered:
            self._stop_device_login(message)
            return
        self.account_log.append(message)

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
        worker = TaskWorker(self.backend.login_by_access_token, access_token, self.refresh_token.text())
        worker.signals.result.connect(self.on_auth_result)
        worker.signals.error.connect(self.account_log.append)
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

    # ------------------------------------------------------------------- demo

    def prepare_demo_state(self):
        self.search_text.setText("midnight")
        self.direct_text.setPlainText("https://tidal.com/browse/track/70973230")
        self.set_search_results(self.backend.search("midnight", Type.Track))
        if self.results:
            self.results_table.selectRow(0)
            self.queue = self.results[:28]
            for index, item in enumerate(self.queue):
                if index < 3:
                    item.status = "Done"
                    item.progress_percent = 100
                elif index == 3:
                    item.status = "Downloading"
                    item.progress_percent = 42
                    item.progress_label = "7/16 tracks"
                elif index == 4:
                    item.status = "Failed"
            self.refresh_queue_table()
            self.queue_table.selectRow(0)
            self.download_log.setPlainText(
                "\n".join(f"Queued {item.title} - waiting for download slot" for item in self.queue) + "\n"
            )
        self.login_url.setText("https://login.tidal.com/DEMO-CODE")
        self.login_code_label.setText("DEMO-CODE")
        self.login_code_label.show()
        self.account_log.setPlainText(
            self.backend.run_doctor()
            + "\n"
            + "\n".join(f"History {index + 1:02d}: token and client checks passed" for index in range(20))
        )


def configure_application_theme(app: QApplication):
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(TOKENS["bg"]))
    palette.setColor(QPalette.WindowText, QColor(TOKENS["text"]))
    palette.setColor(QPalette.Base, QColor(TOKENS["surface"]))
    palette.setColor(QPalette.AlternateBase, QColor(TOKENS["surface_alt"]))
    palette.setColor(QPalette.Text, QColor(TOKENS["text"]))
    palette.setColor(QPalette.Button, QColor(TOKENS["surface"]))
    palette.setColor(QPalette.ButtonText, QColor(TOKENS["text"]))
    palette.setColor(QPalette.Highlight, QColor(TOKENS["accent"]))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ToolTipBase, QColor(TOKENS["text"]))
    palette.setColor(QPalette.ToolTipText, QColor("#ffffff"))
    palette.setColor(QPalette.PlaceholderText, QColor(TOKENS["muted"]))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(TOKENS["disabled"]))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(TOKENS["disabled"]))
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
