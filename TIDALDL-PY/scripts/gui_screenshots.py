#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _is_nonblank(image) -> bool:
    width = image.width()
    height = image.height()
    if width < 800 or height < 500:
        return False

    first = image.pixelColor(0, 0).rgba()
    step_x = max(1, width // 20)
    step_y = max(1, height // 20)
    distinct = set()
    for x in range(0, width, step_x):
        for y in range(0, height, step_y):
            color = image.pixelColor(x, y).rgba()
            distinct.add(color)
            if color != first and len(distinct) >= 8:
                return True
    return False


def _validate_interactions(window) -> list[str]:
    failures = []
    preset = window.priority_preset.currentText()
    if "Max" not in preset or "HiFi" not in preset or "High" not in preset:
        failures.append("settings: saved fallback priority is not reflected")

    selected_then_lower = window.priority_preset.findText("Selected quality, then lower")
    if selected_then_lower >= 0:
        window.audio_quality.setCurrentText("HiFi")
        window.priority_preset.setCurrentIndex(selected_then_lower)
        if window.selected_priority_order() != ["HiFi", "High", "Normal"]:
            failures.append("settings: selected fallback priority resolves the wrong order")

    window.search_text.clear()
    if window.search_button.isEnabled():
        failures.append("search: search button is enabled without input")
    window.search_text.setText("midnight")
    if not window.search_button.isEnabled():
        failures.append("search: search button is disabled with input")

    window.direct_text.clear()
    if window.direct_queue_button.isEnabled() or window.direct_download_button.isEnabled():
        failures.append("links: direct actions are enabled without input")
    window.direct_text.setText("https://tidal.com/browse/track/70973230")
    if not window.direct_queue_button.isEnabled() or not window.direct_download_button.isEnabled():
        failures.append("links: direct actions are disabled with input")
    window.direct_video_only.setChecked(True)
    direct_item = window.direct_item_from_input()
    if direct_item is None or not direct_item.video_only:
        failures.append("links: direct videos-only checkbox is not applied")
    window.direct_video_only.setChecked(False)

    window.show_screen("settings")
    if not window.inspector.isVisible() or not window.settings_toggle.isChecked():
        failures.append("inspector: settings toggle does not open the inspector")
    window.show_screen("workspace")
    if window.inspector.isVisible() or window.settings_toggle.isChecked() or window.session_toggle.isChecked():
        failures.append("inspector: workspace does not close the inspector")

    if window.results:
        window.results_table.clearSelection()
        if window.add_queue_button.isEnabled() or window.download_now_button.isEnabled():
            failures.append("search: row actions are enabled without a selected result")
        window.results_table.sortItems(1)
        window.results_table.selectRow(0)
        if not window.add_queue_button.isEnabled() or not window.download_now_button.isEnabled():
            failures.append("search: row actions are disabled with a selected result")
        selected = window.selected_result_items()
        row_item = window._row_item(window.results_table, 0)
        if not selected or selected[0] is not row_item:
            failures.append("search: sorted selection resolves the wrong item")
        window.result_video_only.setChecked(True)
        video_only_items = window.video_mode_items(selected, True)
        if not video_only_items or not video_only_items[0].video_only:
            failures.append("search: selected videos-only checkbox is not applied")
        window.result_video_only.setChecked(False)

    if window.queue:
        window.queue_table.clearSelection()
        if window.remove_queue_button.isEnabled():
            failures.append("queue: remove is enabled without a selected item")
        window.queue_table.sortItems(1)
        window.queue_table.selectRow(0)
        if not window.remove_queue_button.isEnabled():
            failures.append("queue: remove is disabled with a selected item")
        row_item = window._row_item(window.queue_table, 0)
        before = len(window.queue)
        window.remove_selected_queue_items()
        if row_item is None or any(item is row_item for item in window.queue) or len(window.queue) != before - 1:
            failures.append("queue: sorted removal resolves the wrong item")
        if row_item is not None:
            window.queue.append(row_item)
        window.refresh_queue_table()
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture and validate Tidekeeper GUI screens.")
    parser.add_argument(
        "--output",
        default=str(ROOT / "gui-screenshots"),
        help="Directory for generated PNG screenshots.",
    )
    parser.add_argument(
        "--platform",
        default=os.environ.get("QT_QPA_PLATFORM", "offscreen"),
        help="Qt platform plugin to use for capture.",
    )
    args = parser.parse_args()

    os.environ.setdefault("QT_QPA_PLATFORM", args.platform)
    os.environ["TIDEKEEPER_GUI_DEMO"] = "1"

    try:
        from PySide6.QtWidgets import QApplication
        from tidal_dl.gui_app.backend import DemoBackend
        from tidal_dl.gui_app.main_window import MainWindow, SCREEN_ORDER
    except ImportError as exc:
        print(f"Missing GUI dependency: {exc}", file=sys.stderr)
        return 2

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication([])
    backend = DemoBackend()
    backend.initialize()
    window = MainWindow(backend)
    window.prepare_demo_state()
    window.show()
    app.processEvents()

    failures = _validate_interactions(window)
    window.refresh_settings()
    window.prepare_demo_state()
    app.processEvents()
    for screen in SCREEN_ORDER:
        window.show_screen(screen)
        app.processEvents()
        pixmap = window.grab()
        image = pixmap.toImage()
        target = output / f"{screen}.png"
        if not pixmap.save(str(target), "PNG"):
            failures.append(f"{screen}: failed to save")
            continue
        if not _is_nonblank(image):
            failures.append(f"{screen}: screenshot looks blank or undersized")

    window.close()
    app.quit()

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1

    print(f"Captured {len(SCREEN_ORDER)} screens in {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
