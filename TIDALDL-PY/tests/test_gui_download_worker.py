import sys
import unittest
from types import ModuleType, SimpleNamespace


def _install_pyside_stub():
    if "PySide6.QtCore" in sys.modules:
        return
    qtcore = ModuleType("PySide6.QtCore")

    class _Signal:
        def __init__(self, *args, **kwargs):
            self._slots = []

        def emit(self, *args, **kwargs):
            for slot in self._slots:
                slot(*args, **kwargs)

        def connect(self, slot, *args, **kwargs):
            self._slots.append(slot)

    class _QObject:
        pass

    class _QRunnable:
        def setAutoDelete(self, *args, **kwargs):
            pass

    def _Slot(*args, **kwargs):
        def decorator(fn):
            return fn

        return decorator

    qtcore.QObject = _QObject
    qtcore.QRunnable = _QRunnable
    qtcore.Signal = _Signal
    qtcore.Slot = _Slot
    pyside = ModuleType("PySide6")
    pyside.QtCore = qtcore
    sys.modules["PySide6"] = pyside
    sys.modules["PySide6.QtCore"] = qtcore


class RecordingBackend:
    def __init__(self, on_download=None):
        self.downloaded = []
        self._on_download = on_download

    def download(self, item, log, progress=None):
        self.downloaded.append(item.title)
        if self._on_download:
            self._on_download(item)


class DownloadWorkerQueueTests(unittest.TestCase):
    def setUp(self):
        _install_pyside_stub()
        from tidal_dl.gui_app.workers import DownloadWorker

        self.DownloadWorker = DownloadWorker

    def test_worker_picks_up_items_added_during_run(self):
        first = SimpleNamespace(title="Album One")
        second = SimpleNamespace(title="Album Two")
        extra = []

        def on_download(item):
            if item.title == "Album One":
                extra.append(second)

        backend = RecordingBackend(on_download)
        worker = self.DownloadWorker(backend, [first])
        worker.more_items = lambda: list(extra)
        worker.run()

        self.assertEqual(backend.downloaded, ["Album One", "Album Two"])

    def test_worker_cancel_does_not_start_items_added_during_run(self):
        first = SimpleNamespace(title="Album One")
        second = SimpleNamespace(title="Album Two")
        extra = []
        worker_holder = {}

        def on_download(item):
            worker_holder["worker"].cancel()
            extra.append(second)

        backend = RecordingBackend(on_download)
        worker = self.DownloadWorker(backend, [first])
        worker.more_items = lambda: list(extra)
        worker_holder["worker"] = worker
        worker.run()

        self.assertEqual(backend.downloaded, ["Album One"])

    def test_worker_without_more_items_keeps_original_snapshot(self):
        first = SimpleNamespace(title="Album One")
        backend = RecordingBackend()
        worker = self.DownloadWorker(backend, [first])
        worker.run()
        self.assertEqual(backend.downloaded, ["Album One"])

    def test_worker_does_not_redownload_item_still_listed_as_queued(self):
        first = SimpleNamespace(title="Album One")
        backend = RecordingBackend()
        worker = self.DownloadWorker(backend, [first])
        worker.more_items = lambda: [first]
        worker.run()
        self.assertEqual(backend.downloaded, ["Album One"])


if __name__ == "__main__":
    unittest.main()
