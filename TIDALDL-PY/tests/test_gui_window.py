"""Desktop main window behavior."""

import copy
import os
import unittest

from tidal_dl.settings import SETTINGS

try:
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover - GUI extra not installed
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 is not installed")
class GuiDropAndDoctorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from tidal_dl.gui_app.backend import DemoBackend
        from tidal_dl.gui_app.main_window import FIND_MODE_LINKS, MainWindow

        self.saved = copy.deepcopy(SETTINGS.__dict__)
        backend = DemoBackend()
        backend.initialize()
        self.window = MainWindow(backend)
        self.links_mode = FIND_MODE_LINKS

    def tearDown(self):
        self.window.close()
        SETTINGS.__dict__.clear()
        SETTINGS.__dict__.update(self.saved)

    def test_dropped_urls_and_files_are_staged_in_links(self):
        from PySide6.QtCore import QMimeData, QUrl

        mime = QMimeData()
        mime.setUrls([QUrl("https://tidal.com/browse/album/1"), QUrl.fromLocalFile("/tmp/list.txt")])
        values = self.window.dropped_inputs(mime)
        self.assertEqual(values, ["https://tidal.com/browse/album/1", "/tmp/list.txt"])

        self.window.direct_text.setPlainText("123")
        self.window.append_direct_inputs(values)
        self.assertEqual(self.window.find_stack.currentIndex(), self.links_mode)
        self.assertEqual(self.window.direct_text.toPlainText().splitlines(),
                         ["123", "https://tidal.com/browse/album/1", "/tmp/list.txt"])
        self.assertEqual(self.window.queue, [])

    def test_dropped_plain_text_splits_lines_and_ignores_blank_payloads(self):
        from PySide6.QtCore import QMimeData

        mime = QMimeData()
        mime.setText(" 111 \n\n222\n")
        self.assertEqual(self.window.dropped_inputs(mime), ["111", "222"])
        self.assertEqual(self.window.dropped_inputs(QMimeData()), [])

    def test_doctor_button_is_disabled_until_the_check_finishes(self):
        started = []
        self.window.start_worker = lambda worker: started.append(worker)
        self.window.run_doctor()
        self.assertFalse(self.window.doctor_button.isEnabled())
        started[0].run()
        self.app.processEvents()
        self.assertTrue(self.window.doctor_button.isEnabled())

    def test_receipt_setting_round_trips_through_settings_page(self):
        receipts = self.window.checks["saveReceipts"]
        self.assertTrue(receipts.isChecked())
        SETTINGS.saveReceipts = False
        self.window.refresh_settings()
        self.assertFalse(receipts.isChecked())
        receipts.setChecked(True)
        self.assertTrue(self.window.collect_settings_values()["saveReceipts"])


@unittest.skipIf(QApplication is None, "PySide6 is not installed")
class BrandIconTests(unittest.TestCase):
    def test_brand_icon_renders_platform_sizes(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        QApplication.instance() or QApplication([])
        from tidal_dl.gui_app.widgets import brand_icon

        icon = brand_icon()
        self.assertFalse(icon.isNull())
        self.assertGreaterEqual(max(size.width() for size in icon.availableSizes()), 256)


if __name__ == "__main__":
    unittest.main()
