"""Main application window for the Tidekeeper desktop GUI.

Layout
------
::

    +--------------------------------------------------------------+
    | Header: brand              [session toggle] [settings toggle] |
    +------------------------------------------------+-------------+
    | Find bar   [Search | Links]  type  query  [Go]  | Inspector   |
    | Results panel  (table, selection actions)       |  Settings   |
    | ------- splitter --------------------------     |  or         |
    | Queue panel    (table, transport, log)          |  Account    |
    +------------------------------------------------+-------------+

The inspector is hidden until a header toggle opens it. Presentation
helpers live in :mod:`tidal_dl.gui_app.widgets`; this module owns behaviour.
"""

from __future__ import annotations

import time
import webbrowser
from typing import List, Tuple

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QColor, QFont, QKeySequence, QPalette, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
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
from .style import APP_STYLESHEET, FONT_MONO, TOKENS
from .widgets import (
    PROGRESS_PERCENT_ROLE,
    PROGRESS_STATE_ROLE,
    BrandMark,
    EmptyOverlay,
    FormSection,
    Panel,
    QueueProgressDelegate,
    SegmentedControl,
    StatusDelegate,
    button,
    configure_table,
    dot_icon,
    fix_columns,
    fix_height,
    hint,
    label,
    log_view,
    row,
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

# "workspace" is the always-visible find/results/queue view; the other two
# name the inspector pages.
SCREEN_ORDER = ("workspace", "settings", "account")
INSPECTOR_WIDTH = 380
FIND_MODE_SEARCH, FIND_MODE_LINKS = 0, 1
LINKS_ROW_HEIGHT = 64 + 8 + 30  # paste box, gap, action row

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
    "{ArtistName} {AlbumArtistName} {AlbumTitle} {AlbumYear} {TrackNumber} "
    "{TrackTitle} {PlaylistName} {VideoTitle} {Quality} {Flag}"
)
RESULTS_EMPTY = (
    "Search the TIDAL catalog or paste links.\n"
    "Double-click an artist to browse their tracks."
)
QUEUE_EMPTY = "Nothing queued. Add results or links above."
QUEUE_STATE = {"Done": "done", "Failed": "failed", "Downloading": "active", "Cancelled": "cancelled"}


class MainWindow(QMainWindow):
    def __init__(self, backend: TidekeeperBackend):
        super().__init__()
        self.backend = backend
        self.thread_pool = QThreadPool.globalInstance()
        self.results: List[SearchItem] = []
        self.result_history: List[Tuple[List[SearchItem], str]] = []
        self.queue: List[SearchItem] = []
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

        self._mono_font = QFont()
        self._mono_font.setFamilies([name.strip().strip('"') for name in FONT_MONO.split(",")])
        self._mono_font.setPointSizeF(max(8.0, self._mono_font.pointSizeF() - 1))

        self.setWindowTitle("Tidekeeper")
        self.setMinimumSize(1024, 620)
        self.resize(1180, 760)
        self.setStyleSheet(APP_STYLESHEET)
        self._build()
        self._bind_shortcuts()
        self.version_label.setText(f"Version {self.backend.version()}")
        self.refresh_settings()
        self.refresh_auth_status()
        self.update_action_states()
        self.show_screen("workspace")

    # ------------------------------------------------------------------ build

    def _build(self):
        root = QWidget()
        root.setObjectName("Root")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        workspace = QWidget()
        workspace.setObjectName("Workspace")
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(12, 12, 12, 12)
        workspace_layout.setSpacing(10)
        workspace_layout.addWidget(self._build_find_bar())

        self.workspace_splitter = QSplitter(Qt.Vertical)
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.addWidget(self._build_results_panel())
        self.workspace_splitter.addWidget(self._build_queue_panel())
        self.workspace_splitter.setStretchFactor(0, 3)
        self.workspace_splitter.setStretchFactor(1, 2)
        self.workspace_splitter.setSizes([400, 280])
        workspace_layout.addWidget(self.workspace_splitter, 1)
        body.addWidget(workspace, 1)

        body.addWidget(self._build_inspector())
        root_layout.addLayout(body, 1)
        self.setCentralWidget(root)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(40)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(8)
        layout.addWidget(BrandMark())
        layout.addWidget(label("Tidekeeper", "Wordmark"))
        layout.addStretch(1)

        self.session_toggle = button("Signed out", "header", checkable=True)
        self.session_toggle.clicked.connect(lambda checked: self._toggle_inspector("account", checked))
        self.settings_toggle = button("Settings", "header", checkable=True, tooltip="Settings  (Ctrl+,)")
        self.settings_toggle.clicked.connect(lambda checked: self._toggle_inspector("settings", checked))
        layout.addWidget(self.session_toggle)
        layout.addWidget(self.settings_toggle)
        return header

    # --------------------------------------------------------------- find bar

    def _build_find_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.find_mode = SegmentedControl(["Search", "Links"])
        self.find_mode.changed.connect(self._set_find_mode)
        layout.addWidget(self.find_mode, 0, Qt.AlignTop)

        self.find_stack = QStackedWidget()
        self.find_stack.addWidget(self._build_search_row())
        self.find_stack.addWidget(self._build_links_row())
        layout.addWidget(self.find_stack, 1)
        self._set_find_mode(FIND_MODE_SEARCH)
        return bar

    def _build_search_row(self) -> QWidget:
        self.search_type = QComboBox()
        self.search_type.addItem("All", Type.Null)
        for item in (Type.Track, Type.Album, Type.Playlist, Type.Artist, Type.Video):
            self.search_type.addItem(item.name, item)
        self.search_type.setFixedWidth(112)
        self.search_type.setToolTip("Content type to search for.")
        self.search_text = QLineEdit()
        self.search_text.setPlaceholderText("Artist, album, track, playlist or a TIDAL URL   (Ctrl+F)")
        self.search_text.setClearButtonEnabled(True)
        self.search_button = button("Search", tooltip="Search TIDAL for the selected content type.")
        self.search_button.setMinimumWidth(88)
        self.search_button.clicked.connect(self.run_search)
        self.search_text.returnPressed.connect(self.run_search)
        self.search_text.textChanged.connect(self.update_search_action)
        fix_height(self.search_type, self.search_text)

        widget = QWidget()
        layout = row(self.search_type, self.search_text, self.search_button)
        layout.setStretch(1, 1)
        widget.setLayout(layout)
        return widget

    def _build_links_row(self) -> QWidget:
        self.direct_text = QTextEdit()
        self.direct_text.setObjectName("LinksInput")
        self.direct_text.setAcceptRichText(False)
        self.direct_text.setPlaceholderText(
            "One TIDAL URL or ID per line, comma-separated IDs, or the path to a .txt list"
        )
        self.direct_text.setFixedHeight(64)
        self.direct_video_only = QCheckBox("Videos only")
        self.direct_video_only.setToolTip("Skip audio for artist, album, playlist, mix or file downloads.")
        self.direct_browse_button = button("Choose file…", "ghost", tooltip="Pick a text file of TIDAL URLs.")
        self.direct_queue_button = button("Add to queue", "primary", tooltip="Queue every URL, ID or file line.")
        self.direct_download_button = button("Download now", tooltip="Queue and start every line.")
        self.direct_browse_button.clicked.connect(self.browse_direct_file)
        self.direct_queue_button.clicked.connect(self.add_direct_to_queue)
        self.direct_download_button.clicked.connect(self.download_direct)
        self.direct_text.textChanged.connect(self.update_direct_actions)

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.direct_text)
        layout.addLayout(
            row(
                self.direct_browse_button,
                self.direct_video_only,
                None,
                self.direct_queue_button,
                self.direct_download_button,
            )
        )
        return widget

    def _set_find_mode(self, index: int):
        self.find_stack.setCurrentIndex(index)
        self.find_stack.setFixedHeight(LINKS_ROW_HEIGHT if index == FIND_MODE_LINKS else 30)
        if self.find_mode.current_index() != index:
            self.find_mode.set_current_index(index)
        (self.direct_text if index == FIND_MODE_LINKS else self.search_text).setFocus()

    # ---------------------------------------------------------------- results

    def _build_results_panel(self) -> Panel:
        panel = Panel()
        self.back_results_button = button("← Back", "ghost", tooltip="Return to the previous result list.")
        self.back_results_button.clicked.connect(self.show_previous_results)
        self.search_status = label("", "Meta")
        self.artist_tracks_button = button("Tracks", "ghost", tooltip="Browse every track by the selected artist.")
        self.artist_videos_button = button("Videos", "ghost", tooltip="Browse videos by the selected artist.")
        self.artist_tracks_button.clicked.connect(self.view_selected_artist_tracks)
        self.artist_videos_button.clicked.connect(self.view_selected_artist_videos)
        header = panel.header
        header.addWidget(self.back_results_button)
        header.addWidget(label("Results", "PanelTitle"))
        header.addWidget(self.search_status, 1)
        header.addWidget(self.artist_tracks_button)
        header.addWidget(self.artist_videos_button)

        self.results_table = QTableWidget(0, 6)
        configure_table(self.results_table, ["Type", "Title", "Artists", "Quality", "Duration", "ID"])
        fix_columns(self.results_table, {0: 80, 3: 160, 4: 72, 5: 104})
        self.results_table.itemSelectionChanged.connect(self.update_result_actions)
        self.results_table.itemDoubleClicked.connect(self.open_result_item)
        self.results_empty = EmptyOverlay(self.results_table, RESULTS_EMPTY)
        panel.set_body(self.results_table)

        self.selection_label = label("", "Meta")
        self.result_video_only = QCheckBox("Videos only")
        self.result_video_only.setToolTip("Queue the selected rows in videos-only mode.")
        self.add_queue_button = button("Add to queue", "primary", tooltip="Add selected rows to the queue  (Enter)")
        self.download_now_button = button("Download now", tooltip="Add selected rows and start downloading.")
        self.add_queue_button.clicked.connect(self.add_selected_to_queue)
        self.download_now_button.clicked.connect(self.download_selected)
        footer = panel.footer
        footer.addWidget(self.selection_label, 1)
        footer.addWidget(self.result_video_only)
        footer.addWidget(self.add_queue_button)
        footer.addWidget(self.download_now_button)
        return panel

    # ------------------------------------------------------------------ queue

    def _build_queue_panel(self) -> Panel:
        panel = Panel()
        self.queue_status = label("", "Meta")
        self.queue_status.setTextFormat(Qt.RichText)
        self.queue_status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._queue_message = ""
        self.remove_queue_button = button("Remove", "ghost", tooltip="Remove selected rows  (Delete)")
        self.clear_queue_button = button("Clear", "ghost", tooltip="Clear the queue and log.")
        self.retry_failed_button = button("Retry failed", tooltip="Re-queue failed items and download them again.")
        self.log_toggle = button("Log", "ghost", checkable=True, tooltip="Show download output.")
        self.cancel_queue_button = button("Cancel", "danger", tooltip="Stop after the current item finishes.")
        self.start_queue_button = button("Start", "primary", tooltip="Download queued and failed items.")
        self.start_queue_button.setMinimumWidth(80)
        self.remove_queue_button.clicked.connect(self.remove_selected_queue_items)
        self.clear_queue_button.clicked.connect(self.clear_queue)
        self.retry_failed_button.clicked.connect(self.retry_failed_downloads)
        self.log_toggle.toggled.connect(self._set_log_visible)
        self.cancel_queue_button.clicked.connect(self.cancel_downloads)
        self.start_queue_button.clicked.connect(self.start_queue_download)
        header = panel.header
        header.addWidget(label("Queue", "PanelTitle"))
        header.addWidget(self.queue_status, 1)
        for widget in (
            self.remove_queue_button,
            self.clear_queue_button,
            self.retry_failed_button,
            self.log_toggle,
            self.cancel_queue_button,
            self.start_queue_button,
        ):
            header.addWidget(widget)

        self.queue_table = QTableWidget(0, 6)
        configure_table(self.queue_table, ["Type", "Title", "Artists", "Quality", "Status", "Progress"])
        fix_columns(self.queue_table, {0: 96, 3: 150, 4: 210, 5: 132})
        self.queue_table.setItemDelegateForColumn(4, StatusDelegate(self.queue_table))
        self.queue_table.setItemDelegateForColumn(5, QueueProgressDelegate(self.queue_table))
        self.queue_table.itemSelectionChanged.connect(self.update_queue_actions)
        self.queue_empty = EmptyOverlay(self.queue_table, QUEUE_EMPTY)

        self.download_log = log_view("Download output appears here while the queue runs.")
        self.download_log.setMinimumHeight(72)
        self.download_log.hide()

        self.queue_splitter = QSplitter(Qt.Vertical)
        self.queue_splitter.setChildrenCollapsible(False)
        self.queue_splitter.setHandleWidth(1)
        self.queue_splitter.addWidget(self.queue_table)
        self.queue_splitter.addWidget(self.download_log)
        self.queue_splitter.setStretchFactor(0, 3)
        self.queue_splitter.setStretchFactor(1, 1)
        panel.set_body(self.queue_splitter)
        return panel

    def _set_log_visible(self, visible: bool):
        self.download_log.setVisible(visible)
        if visible:
            total = max(1, self.queue_splitter.height())
            self.queue_splitter.setSizes([int(total * 0.65), int(total * 0.35)])

    # -------------------------------------------------------------- inspector

    def _build_inspector(self) -> QFrame:
        self.inspector = QFrame()
        self.inspector.setObjectName("Inspector")
        self.inspector.setFixedWidth(INSPECTOR_WIDTH)
        layout = QVBoxLayout(self.inspector)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("InspectorHeader")
        header.setFixedHeight(40)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 6, 0)
        header_layout.setSpacing(8)
        self.inspector_title = label("", "PanelTitle")
        close_button = button("×", "icon", tooltip="Close  (Esc)")
        close_button.clicked.connect(lambda: self.show_screen("workspace"))
        header_layout.addWidget(self.inspector_title, 1)
        header_layout.addWidget(close_button)
        layout.addWidget(header)

        self.inspector_stack = QStackedWidget()
        self.pages = {
            "settings": self._build_settings_page(),
            "account": self._build_account_page(),
        }
        for name in ("settings", "account"):
            self.inspector_stack.addWidget(self.pages[name])
        layout.addWidget(self.inspector_stack, 1)
        self.inspector.hide()
        return self.inspector

    def _inspector_content(self) -> tuple[QWidget, QVBoxLayout]:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)
        return content, layout

    # --------------------------------------------------------------- settings

    def _build_settings_page(self) -> QWidget:
        content, layout = self._inspector_content()

        storage = FormSection("Storage")
        self.download_path = QLineEdit()
        self.download_path.setPlaceholderText("Folder where downloads are written")
        browse = button("Browse…", tooltip="Choose a download folder.")
        open_folder = button("Open", "ghost", tooltip="Open the download folder.")
        browse.clicked.connect(self.browse_download_path)
        open_folder.clicked.connect(self.open_download_folder)
        fix_height(self.download_path)
        path_row = row(self.download_path, browse, open_folder)
        path_row.setStretch(0, 1)
        storage.add_stacked("Download folder", path_row)
        layout.addWidget(storage)

        quality = FormSection("Quality")
        self.audio_quality = QComboBox()
        for item in QUALITY_ORDER:
            self.audio_quality.addItem(item.name, item.name)
        self.priority_preset = QComboBox()
        self.priority_preset.setToolTip("Fallback order when the requested stream is blocked or unavailable.")
        for preset_label, order in PRIORITY_PRESETS:
            self.priority_preset.addItem(preset_label, order)
        self.video_quality = QComboBox()
        for item in VideoQuality:
            self.video_quality.addItem(item.name, item.name)
        for combo in (self.audio_quality, self.priority_preset, self.video_quality):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(12)
            combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            fix_height(combo)
        quality.add_row("Audio", self.audio_quality)
        quality.add_row("Fallback", self.priority_preset)
        quality.add_row("Video", self.video_quality)
        layout.addWidget(quality)

        self.checks = {}
        for key, text in (
            ("checkExist", "Skip files that already exist"),
            ("multiThread", "Download tracks in parallel"),
            ("downloadDelay", "Delay between requests"),
            ("adaptiveRateLimit", "Adapt the delay automatically"),
            ("saveCovers", "Save cover art"),
            ("lyricFile", "Save lyrics"),
            ("saveAlbumInfo", "Save album info"),
            ("saveAsFlac", "Save FLAC streams as .flac"),
            ("usePlaylistFolder", "Put playlists in their own folder"),
            ("includeEP", "Include EPs and singles"),
            ("downloadVideos", "Download videos with albums"),
            ("showProgress", "Log progress lines"),
            ("showTrackInfo", "Log track details"),
        ):
            self.checks[key] = QCheckBox(text)

        self.request_interval = QDoubleSpinBox()
        self.request_interval.setRange(0.0, 300.0)
        self.request_interval.setSingleStep(0.5)
        self.request_interval.setDecimals(1)
        self.request_interval.setSuffix(" s")
        self.request_interval.setFixedWidth(96)
        self.request_interval.setToolTip("Minimum delay between TIDAL playback API requests.")
        fix_height(self.request_interval)
        self.checks["downloadDelay"].toggled.connect(self._update_request_interval_enabled)

        downloads = FormSection("Downloads")
        downloads.add_widget(self.checks["checkExist"])
        downloads.add_widget(self.checks["multiThread"])
        delay_row = row(self.checks["downloadDelay"], None, self.request_interval)
        downloads.add_layout(delay_row)
        downloads.add_widget(self.checks["adaptiveRateLimit"])
        layout.addWidget(downloads)

        files = FormSection("Files")
        for key in ("saveCovers", "lyricFile", "saveAlbumInfo", "saveAsFlac", "usePlaylistFolder"):
            files.add_widget(self.checks[key])
        layout.addWidget(files)

        catalog = FormSection("Catalog")
        catalog.add_widget(self.checks["includeEP"])
        catalog.add_widget(self.checks["downloadVideos"])
        layout.addWidget(catalog)

        naming = FormSection("Naming")
        self.album_format = QLineEdit()
        self.playlist_format = QLineEdit()
        self.track_format = QLineEdit()
        self.video_format = QLineEdit()
        for text, widget in (
            ("Album folder", self.album_format),
            ("Playlist folder", self.playlist_format),
            ("Track file", self.track_format),
            ("Video file", self.video_format),
        ):
            widget.setObjectName("Mono")
            widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            fix_height(widget)
            naming.add_stacked(text, widget)
        naming.add_widget(hint(NAMING_HINT))
        layout.addWidget(naming)

        advanced = FormSection("Advanced")
        self.language = QComboBox()
        for index, name in self.backend.language_choices():
            self.language.addItem(name, index)
        self.api_client = QComboBox()
        for item in self.backend.api_clients():
            status = "OK" if item["valid"] else "old"
            self.api_client.addItem(f'{item["index"]} {status} · {item["platform"]}', item["index"])
            self.api_client.setItemData(
                self.api_client.count() - 1,
                f'{item["index"]} {status} · {item["platform"]} ({item["formats"]})',
                Qt.ToolTipRole,
            )
        for combo in (self.language, self.api_client):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(12)
            combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            fix_height(combo)
        advanced.add_row("Log language", self.language)
        advanced.add_row("TIDAL client", self.api_client)
        advanced.add_widget(hint("Changing the client signs you out; sign in again afterwards."))
        advanced.add_widget(self.checks["showProgress"])
        advanced.add_widget(self.checks["showTrackInfo"])
        layout.addWidget(advanced)
        layout.addStretch(1)

        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        page_layout.addWidget(scroll_area(content), 1)

        footer = QFrame()
        footer.setObjectName("PanelFooter")
        footer.setFixedHeight(44)
        self.settings_status = label("", "Meta")
        reload_button = button("Reload", "ghost", tooltip="Discard unsaved changes and reload from disk.")
        save_button = button("Save", "primary", tooltip="Write these settings to disk.")
        reload_button.clicked.connect(self.refresh_settings)
        save_button.clicked.connect(self.save_settings)
        footer.setLayout(row(self.settings_status, None, reload_button, save_button, margins=(12, 0, 12, 0)))
        page_layout.addWidget(footer)
        return page

    # ---------------------------------------------------------------- account

    def _build_account_page(self) -> QWidget:
        content, layout = self._inspector_content()

        session = FormSection("Session")
        self.auth_dot = label("")
        self.auth_dot.setFixedSize(10, 10)
        self.auth_label = label("Signed out")
        self.session_meta = label("", "Meta")
        self.refresh_login_button = button("Refresh", tooltip="Refresh the saved token if possible.")
        self.logout_button = button("Log out", "danger", tooltip="Remove the saved local login.")
        self.refresh_login_button.clicked.connect(self.refresh_saved_login)
        self.logout_button.clicked.connect(self.logout)
        session.add_layout(row(self.auth_dot, self.auth_label, None, spacing=8))
        session.add_widget(self.session_meta)
        session.add_layout(row(self.refresh_login_button, self.logout_button, None))
        layout.addWidget(session)

        device = FormSection("Device login")
        device.add_widget(hint("Sign in at tidal.com with a one-time code. Recommended."))
        self.device_login_button = button("Start device login", "primary", tooltip="Request a TIDAL device code.")
        self.device_login_button.clicked.connect(self.start_device_login)
        self.login_code_label = label("", "Code")
        self.login_code_label.setAlignment(Qt.AlignCenter)
        self.login_url = QLineEdit()
        self.login_url.setObjectName("Mono")
        self.login_url.setReadOnly(True)
        fix_height(self.login_url)
        self.open_login_button = button("Open in browser", tooltip="Open the device login URL.")
        self.open_login_button.clicked.connect(self.open_login_url)
        self.login_challenge = QWidget()
        challenge_layout = QVBoxLayout(self.login_challenge)
        challenge_layout.setContentsMargins(0, 0, 0, 0)
        challenge_layout.setSpacing(8)
        challenge_layout.addWidget(self.login_code_label)
        url_row = row(self.login_url, self.open_login_button)
        url_row.setStretch(0, 1)
        challenge_layout.addLayout(url_row)
        self.login_challenge.hide()
        device.add_layout(row(self.device_login_button, None))
        device.add_widget(self.login_challenge)
        layout.addWidget(device)

        token = FormSection("Manual token")
        self.access_token = QLineEdit()
        self.access_token.setEchoMode(QLineEdit.Password)
        self.access_token.setPlaceholderText("Access token")
        self.refresh_token = QLineEdit()
        self.refresh_token.setEchoMode(QLineEdit.Password)
        self.refresh_token.setPlaceholderText("Refresh token (optional)")
        fix_height(self.access_token, self.refresh_token)
        self.token_login_button = button("Save token", tooltip="Use tokens copied from another signed-in client.")
        self.token_login_button.clicked.connect(self.login_with_token)
        token.add_widget(self.access_token)
        token.add_widget(self.refresh_token)
        token.add_layout(row(self.token_login_button, None))
        layout.addWidget(token)

        maintenance = FormSection("Maintenance")
        self.version_label = label("", "Meta")
        self.doctor_button = button("Run doctor", tooltip="Check auth, download path, client and local tools.")
        self.update_button = button("Update", tooltip="Update the Tidekeeper install from PyPI.")
        self.doctor_button.clicked.connect(self.run_doctor)
        self.update_button.clicked.connect(lambda: self.update_tidekeeper(True))
        maintenance.add_layout(row(self.doctor_button, self.update_button, None, self.version_label))
        layout.addWidget(maintenance)
        layout.addStretch(1)

        self.account_log = log_view("Login, doctor and update output appears here.")
        self.account_log.setMinimumHeight(96)

        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)
        splitter.addWidget(scroll_area(content))
        splitter.addWidget(self.account_log)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([460, 220])
        return splitter

    # -------------------------------------------------------------- shortcuts

    def _bind_shortcuts(self):
        QShortcut(QKeySequence.Find, self, activated=self._focus_search)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=lambda: self._toggle_inspector("settings"))
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self._escape)
        for key in (Qt.Key_Return, Qt.Key_Enter):
            shortcut = QShortcut(QKeySequence(key), self.results_table, activated=self.add_selected_to_queue)
            shortcut.setContext(Qt.WidgetShortcut)
        remove = QShortcut(QKeySequence(Qt.Key_Delete), self.queue_table, activated=self.remove_selected_queue_items)
        remove.setContext(Qt.WidgetShortcut)

    def _focus_search(self):
        self._set_find_mode(FIND_MODE_SEARCH)
        self.search_text.selectAll()

    def _escape(self):
        if self.inspector.isVisible():
            self.show_screen("workspace")

    # ---------------------------------------------------------------- helpers

    def _table_cell(self, value, item=None, *, mono: bool = False, muted: bool = False) -> QTableWidgetItem:
        cell = QTableWidgetItem(str(value))
        if item is not None:
            cell.setData(Qt.UserRole, item)
        if mono:
            cell.setFont(self._mono_font)
        if muted:
            cell.setForeground(QColor(TOKENS["muted"]))
        return cell

    def _update_request_interval_enabled(self, enabled: bool):
        self.request_interval.setEnabled(enabled)

    def _row_item(self, table: QTableWidget, row_index: int):
        cell = table.item(row_index, 0)
        if cell is None:
            return None
        return cell.data(Qt.UserRole)

    @staticmethod
    def _plural(count: int, word: str) -> str:
        return f"{count} {word}{'' if count == 1 else 's'}"

    def show_screen(self, name: str):
        if name not in SCREEN_ORDER:
            return
        if name == "workspace":
            self.inspector.hide()
        else:
            self.inspector_stack.setCurrentWidget(self.pages[name])
            self.inspector_title.setText("Settings" if name == "settings" else "Account")
            self.inspector.show()
        self.settings_toggle.setChecked(name == "settings")
        self.session_toggle.setChecked(name == "account")

    def _toggle_inspector(self, name: str, checked: bool | None = None):
        if checked is None:
            checked = not (self.inspector.isVisible() and self.inspector_stack.currentWidget() is self.pages[name])
        self.show_screen(name if checked else "workspace")

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
        self.search_status.setText("Searching…")
        worker = TaskWorker(self.backend.search, text, kind)
        worker.signals.result.connect(self.set_search_results)
        worker.signals.error.connect(self.show_search_error)
        worker.signals.finished.connect(self._search_finished)
        self.start_worker(worker)

    def set_search_results(self, items: List[SearchItem], status_text: str | None = None):
        self.results = items
        self.results_table.setSortingEnabled(False)
        self.results_table.setRowCount(len(items))
        for row_index, item in enumerate(items):
            values = [item.kind.name, item.title, item.artists, item.quality, item.duration, item.identifier]
            for col, value in enumerate(values):
                cell = self._table_cell(value, item if col == 0 else None, mono=col == 5, muted=col in (0, 5))
                if col in (4, 5):
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.results_table.setItem(row_index, col, cell)
        self.results_table.setSortingEnabled(True)
        self.results_empty.set_text(RESULTS_EMPTY if not self.results_table.rowCount() and status_text is None
                                    else "No results. Try another term or content type.")
        self.results_empty.set_visible(not items)
        self.search_status.setText(status_text or f"{self._plural(len(items), 'result')}")
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
        self.search_status.setText(f"Loading {noun}s by {item.title}…")
        self.update_search_action()
        self.update_result_actions()
        worker = TaskWorker(loader, item)
        worker.signals.result.connect(
            lambda items, artist=item.title: self.set_search_results(
                items, f"{self._plural(len(items), noun)} by {artist}"
            )
        )
        worker.signals.error.connect(self.show_search_error)
        worker.signals.finished.connect(self._search_finished)
        self.start_worker(worker)

    def open_result_item(self, cell: QTableWidgetItem):
        item = self._row_item(self.results_table, cell.row())
        if item is None or self.search_in_progress:
            return
        if item.kind != Type.Artist:
            self.add_selected_to_queue()
            return
        self._load_artist_children(item, self.backend.artist_tracks, "track")

    def _selected_single_artist(self) -> SearchItem | None:
        items = self.selected_result_items()
        if len(items) == 1 and items[0].kind == Type.Artist:
            return items[0]
        self.search_status.setText("Select one artist row first.")
        return None

    def view_selected_artist_tracks(self):
        artist = self._selected_single_artist()
        if artist is not None and not self.search_in_progress:
            self._load_artist_children(artist, self.backend.artist_tracks, "track")

    def view_selected_artist_videos(self):
        artist = self._selected_single_artist()
        if artist is not None and not self.search_in_progress:
            self._load_artist_children(artist, self.backend.artist_videos, "video")

    def show_previous_results(self):
        if not self.result_history or self.search_in_progress:
            return
        items, status = self.result_history.pop()
        self.set_search_results(items, status)

    def selected_result_items(self) -> List[SearchItem]:
        rows = sorted({index.row() for index in self.results_table.selectionModel().selectedRows()})
        items = []
        for row_index in rows:
            item = self._row_item(self.results_table, row_index)
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
        self.search_status.setText(f"Added {self._plural(len(items), 'item')} to the queue")

    # ------------------------------------------------------------------ links

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
        tokens = parse_direct_inputs(self.direct_text.toPlainText())
        if not tokens:
            self._set_queue_message("Enter a URL, ID, mix ID, or .txt file.")
            return []
        video_only = self.direct_video_only.isChecked()
        return [with_video_only(self.backend.direct_item(token), video_only) for token in tokens]

    def add_direct_to_queue(self):
        items = self.direct_items_from_input()
        if not items:
            return
        self.queue.extend(items)
        self.refresh_queue_table()
        self._set_queue_message(f"Added {self._plural(len(items), 'link')}")

    def download_direct(self):
        if self.download_in_progress:
            self._set_queue_message("A download is already running.")
            return
        items = self.direct_items_from_input()
        if not items:
            return
        self.queue.extend(items)
        self.refresh_queue_table()
        self.start_downloads(items)

    def download_selected(self):
        if self.download_in_progress:
            self._set_queue_message("A download is already running.")
            return
        items = self.video_mode_items(self.selected_result_items(), self.result_video_only.isChecked())
        if not items:
            self.search_status.setText("Select one or more rows first.")
            return
        self.queue.extend(items)
        self.refresh_queue_table()
        self.start_downloads(items)

    # ------------------------------------------------------------------ queue

    def _queue_kind_label(self, item: SearchItem) -> str:
        kind = "Link" if item.kind == Type.Null else item.kind.name
        if item.video_only and item.kind != Type.Video:
            kind += " · videos"
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
        return QUEUE_STATE.get(item.status or "", "queued")

    def _set_queue_row(self, row_index: int, item: SearchItem):
        values = [
            self._queue_kind_label(item),
            item.title,
            item.artists,
            item.quality,
            self._queue_status_text(item),
            self._queue_progress_text(item),
        ]
        for col, value in enumerate(values):
            cell = self.queue_table.item(row_index, col)
            if cell is None:
                cell = self._table_cell(value, item if col == 0 else None, muted=col == 0)
                self.queue_table.setItem(row_index, col, cell)
            else:
                cell.setText(str(value))
                if col == 0:
                    cell.setData(Qt.UserRole, item)
        state = self._queue_progress_state(item)
        self.queue_table.item(row_index, 4).setData(PROGRESS_STATE_ROLE, state)
        progress_cell = self.queue_table.item(row_index, 5)
        progress_cell.setData(PROGRESS_STATE_ROLE, state)
        progress_cell.setData(PROGRESS_PERCENT_ROLE, 100 if item.status == "Done" else int(item.progress_percent or 0))

    def refresh_queue_table(self):
        self.queue_table.setSortingEnabled(False)
        self.queue_table.setRowCount(len(self.queue))
        for row_index, item in enumerate(self.queue):
            self._set_queue_row(row_index, item)
        self.queue_table.setSortingEnabled(True)
        self.queue_empty.set_visible(not self.queue)
        self._queue_message = ""
        self.update_queue_actions()

    def _refresh_queue_row(self, item: SearchItem):
        for row_index in range(self.queue_table.rowCount()):
            if self._row_item(self.queue_table, row_index) is item:
                self._set_queue_row(row_index, item)
                break
        self._update_queue_summary()

    def remove_selected_queue_items(self):
        rows = sorted({index.row() for index in self.queue_table.selectionModel().selectedRows()})
        selected_items = [self._row_item(self.queue_table, row_index) for row_index in rows]
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
            self._set_queue_message("A download is already running.")
            return
        items = self.pending_queue_items()
        if not items:
            self._set_queue_message("Nothing left to download.")
            return
        self.start_downloads(items)

    def retry_failed_downloads(self):
        if self.download_in_progress:
            self._set_queue_message("A download is already running.")
            return
        items = self.failed_queue_items()
        if not items:
            self._set_queue_message("No failed items to retry.")
            return
        for item in items:
            item.status = "Queued"
            item.progress_percent = 0
            item.progress_label = ""
        self.refresh_queue_table()
        self.start_downloads(items)

    def start_downloads(self, items: List[SearchItem]):
        if self.download_in_progress:
            self._set_queue_message("A download is already running.")
            return
        if not items:
            self._set_queue_message("Nothing left to download.")
            return
        # Honor the Settings panel even if the user did not click Save first.
        self.apply_settings_for_download()
        self.download_in_progress = True
        self._cancel_requested = False
        self.update_action_states()
        self._set_queue_message(f"Downloading {self._plural(len(items), 'item')}…")
        self.download_log.append("Starting downloads")
        worker = DownloadWorker(self.backend, items)
        self.download_worker = worker
        worker.signals.log.connect(self.append_download_log)
        worker.signals.item_status.connect(self._set_queue_item_status)
        worker.signals.item_progress.connect(self._set_queue_item_progress)
        worker.signals.result.connect(lambda _: self._set_queue_message("Downloads finished"))
        worker.signals.error.connect(self.show_download_error)
        worker.signals.finished.connect(self._download_finished)
        self.start_worker(worker)

    def _download_finished(self):
        self.download_in_progress = False
        self.download_worker = None
        if self._cancel_requested:
            self._cancel_requested = False
            self._set_queue_message("Downloads cancelled")
        self.update_action_states()

    def cancel_downloads(self):
        if self.download_worker is None:
            return
        self._cancel_requested = True
        self.download_worker.cancel()
        self.cancel_queue_button.setEnabled(False)
        self._set_queue_message("Cancelling after the current item…")

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
        self._set_queue_message(message)
        if not self.log_toggle.isChecked():
            self.log_toggle.setChecked(True)
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
        single_artist = len(selected) == 1 and selected[0].kind == Type.Artist
        self.back_results_button.setVisible(bool(self.result_history))
        self.back_results_button.setEnabled(bool(self.result_history) and not self.search_in_progress)
        for widget in (self.artist_tracks_button, self.artist_videos_button):
            widget.setVisible(single_artist)
            widget.setEnabled(single_artist and not self.search_in_progress)
        self.add_queue_button.setEnabled(has_selection)
        self.download_now_button.setEnabled(has_selection and not self.download_in_progress)
        self.selection_label.setText(f"{self._plural(len(selected), 'row')} selected" if has_selection else "")

    def video_mode_items(self, items: List[SearchItem], video_only: bool) -> List[SearchItem]:
        if not video_only:
            return items
        return [with_video_only(item, True) for item in items]

    def _set_queue_message(self, text: str):
        self._queue_message = text
        self._update_queue_summary()

    def _update_queue_summary(self):
        done = sum(1 for item in self.queue if item.status == "Done")
        failed = len(self.failed_queue_items())
        active = sum(1 for item in self.queue if item.status == "Downloading")
        pending = len(self.queue) - done - failed - active
        parts = []
        for count, word, color in (
            (active, "downloading", TOKENS["accent"]),
            (pending, "queued", None),
            (done, "done", TOKENS["success"]),
            (failed, "failed", TOKENS["danger"]),
        ):
            if count:
                text = f"{count} {word}"
                parts.append(f'<span style="color:{color}">{text}</span>' if color else text)
        if self._queue_message:
            parts.append(f'<span style="color:{TOKENS["text_secondary"]}">{self._queue_message}</span>')
        self.queue_status.setText("&nbsp;·&nbsp;".join(parts))

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
        self.settings_status.setText("Loaded from disk")

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
            self.settings_status.setText("Saved. Sign in again: the client changed.")
        else:
            self.settings_status.setText("Saved")

    # ---------------------------------------------------------------- account

    def refresh_auth_status(self):
        status = self.backend.auth_status()
        signed_in = bool(getattr(status, "has_token", False))
        color = TOKENS["success"] if signed_in else TOKENS["muted"]
        self.auth_dot.setPixmap(dot_icon(color, 10).pixmap(10, 10))
        self.auth_label.setText(status.label)
        meta = f"{status.country_code or 'Unknown region'} · expires in {status.expires_label}" if signed_in else ""
        self.session_meta.setText(meta)
        self.session_meta.setVisible(bool(meta))
        self.session_toggle.setIcon(dot_icon(color))
        self.session_toggle.setText(status.label)
        self.session_toggle.setToolTip(meta or "Sign in to search and download.")
        self.logout_button.setEnabled(signed_in)
        self.refresh_login_button.setEnabled(signed_in)

    def on_auth_result(self, status):
        """Refresh the account panel after a login/refresh worker succeeds."""
        self.refresh_auth_status()
        self.account_log.append(status.label)

    def refresh_saved_login(self):
        self.refresh_login_button.setEnabled(False)
        self.account_log.append("Refreshing saved login…")
        worker = TaskWorker(self.backend.refresh_saved_login)
        worker.signals.result.connect(self.on_auth_result)
        worker.signals.error.connect(self.account_log.append)
        worker.signals.finished.connect(lambda: self.refresh_login_button.setEnabled(True))
        self.start_worker(worker)

    def start_device_login(self):
        self.device_login_button.setEnabled(False)
        self.account_log.append("Requesting device login…")
        worker = TaskWorker(self.backend.start_device_login)
        worker.signals.result.connect(self._device_login_started)
        worker.signals.error.connect(self._device_login_error)
        self.start_worker(worker)

    def _show_login_challenge(self, url: str, code: str):
        self.login_url.setText(url)
        self.login_code_label.setText(code)
        self.login_code_label.setVisible(bool(code))
        self.login_challenge.setVisible(bool(url))

    def _device_login_started(self, challenge):
        code = getattr(challenge, "user_code", "") or ""
        self._show_login_challenge(challenge.url, code)
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
        self.login_challenge.hide()
        if message:
            self.account_log.append(message)

    def _device_login_error(self, message: str):
        self._stop_device_login(message)

    def _poll_device_login(self):
        if not self.login_polling or self.login_poll_inflight:
            return
        if self.login_deadline and time.time() >= self.login_deadline:
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
        self.account_log.append("Saving manual token…")
        worker = TaskWorker(self.backend.login_by_access_token, access_token, self.refresh_token.text())
        worker.signals.result.connect(self.on_auth_result)
        worker.signals.error.connect(self.account_log.append)
        worker.signals.finished.connect(lambda: self.token_login_button.setEnabled(True))
        self.start_worker(worker)

    def run_doctor(self):
        self.account_log.append("Running doctor…")
        worker = TaskWorker(self.backend.run_doctor)
        worker.signals.result.connect(lambda output: self.account_log.append(output.strip()))
        worker.signals.error.connect(self.account_log.append)
        self.start_worker(worker)

    def update_tidekeeper(self, include_gui: bool = True):
        self.account_log.append("Updating Tidekeeper…")
        self.update_button.setEnabled(False)
        worker = TaskWorker(self.backend.update_app, include_gui)
        worker.signals.result.connect(lambda output: self.account_log.append(output.strip()))
        worker.signals.error.connect(self.account_log.append)
        worker.signals.finished.connect(lambda: self.update_button.setEnabled(True))
        self.start_worker(worker)

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
                    item.progress_label = "7/16 · 2.1 MB/s · 12s"
                elif index == 4:
                    item.status = "Failed"
            self.refresh_queue_table()
            self.queue_table.selectRow(0)
            self.log_toggle.setChecked(True)
            self.download_log.setPlainText(
                "\n".join(f"Queued {item.title} - waiting for download slot" for item in self.queue) + "\n"
            )
        self._show_login_challenge("https://login.tidal.com/DEMO-CODE", "DEMO-CODE")
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
    palette.setColor(QPalette.Button, QColor(TOKENS["surface_alt"]))
    palette.setColor(QPalette.ButtonText, QColor(TOKENS["text"]))
    palette.setColor(QPalette.Light, QColor(TOKENS["surface_hover"]))
    palette.setColor(QPalette.Midlight, QColor(TOKENS["border_strong"]))
    palette.setColor(QPalette.Mid, QColor(TOKENS["border"]))
    palette.setColor(QPalette.Dark, QColor(TOKENS["bg"]))
    palette.setColor(QPalette.Shadow, QColor(TOKENS["bg"]))
    palette.setColor(QPalette.Highlight, QColor(TOKENS["accent"]))
    palette.setColor(QPalette.HighlightedText, QColor(TOKENS["on_accent"]))
    palette.setColor(QPalette.ToolTipBase, QColor(TOKENS["surface_hover"]))
    palette.setColor(QPalette.ToolTipText, QColor(TOKENS["text"]))
    palette.setColor(QPalette.PlaceholderText, QColor(TOKENS["muted"]))
    palette.setColor(QPalette.Link, QColor(TOKENS["accent"]))
    for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
        palette.setColor(QPalette.Disabled, role, QColor(TOKENS["disabled"]))
    app.setPalette(palette)
    hints = app.styleHints()
    if hasattr(hints, "setColorScheme"):
        hints.setColorScheme(Qt.ColorScheme.Dark)


def run_app(backend: TidekeeperBackend):
    app = QApplication.instance() or QApplication([])
    configure_application_theme(app)
    backend.initialize()
    window = MainWindow(backend)
    window.show()
    return app.exec()
