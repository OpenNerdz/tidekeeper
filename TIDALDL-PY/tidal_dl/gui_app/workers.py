from __future__ import annotations

import time
from threading import Lock

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()
    log = Signal(str)
    item_status = Signal(object, str)
    item_progress = Signal(object, dict)


class TaskWorker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.setAutoDelete(False)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(result)
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()


class ItemProgressReporter:
    """Thread-safe download progress adapter for one queue row."""

    def __init__(self, item, emit):
        self.item = item
        self._emit = emit
        self._lock = Lock()
        self.completed = 0
        self.count = 0
        self.current = 0
        self.bytes = 0
        self.bytes_total = 0
        self._started = None
        self._last_emit = 0.0

    def snapshot(self) -> dict:
        speed, eta = self._speed_eta()
        return {
            "completed": self.completed,
            "count": self.count,
            "current": self.current,
            "bytes": self.bytes,
            "bytes_total": self.bytes_total,
            "speed": speed,
            "eta": eta,
        }

    def _speed_eta(self):
        if self._started is None:
            return 0.0, None
        elapsed = time.monotonic() - self._started
        if elapsed <= 0.05:
            return 0.0, None
        if self.bytes_total > 0 and self.bytes > 0:
            speed = self.bytes / elapsed
            remain = max(self.bytes_total - self.bytes, 0)
            eta = remain / speed if speed > 0 else None
            return speed, eta
        if self.count > 1 and self.completed > 0:
            item_speed = self.completed / elapsed
            remain = max(self.count - self.completed, 0)
            eta = remain / item_speed if item_speed > 0 else None
            return 0.0, eta
        return 0.0, None

    def _push(self, force=False):
        now = time.monotonic()
        if not force and now - self._last_emit < 0.1:
            return
        self._last_emit = now
        self._emit(self.item, self.snapshot())

    def begin_collection(self, total):
        extra = max(int(total or 0), 0)
        if extra <= 0:
            return
        with self._lock:
            # Nested collections (album audio then videos) add to the total
            # instead of resetting the bar back to 0%.
            if self.count == 0:
                self.count = extra
                self.completed = 0
                self.current = 0
                self.bytes = 0
                self.bytes_total = 0
                if self._started is None:
                    self._started = time.monotonic()
            else:
                self.count += extra
        self._push(force=True)

    def _adopt_entry_total(self, total):
        extra = int(total or 0)
        if extra <= 0:
            return extra
        # Nested begin_entry/finish_entry pass the inner collection size
        # (for example video count after album tracks). Never shrink the
        # combined total or the bar jumps to 100%.
        if self.count <= 0 or extra > self.count:
            self.count = extra
        return extra

    def begin_entry(self, index, total, title=""):
        with self._lock:
            inner = self._adopt_entry_total(total)
            if inner > 0 and self.count > inner and self.completed > 0:
                self.current = min(self.completed + 1, self.count)
            else:
                self.current = int(index or 0)
            self.bytes = 0
            self.bytes_total = 0
            self._started = time.monotonic()
        self._push(force=True)

    def finish_entry(self, index, total, ok=True):
        with self._lock:
            inner = self._adopt_entry_total(total)
            self.completed = min(self.completed + 1, self.count or self.completed + 1)
            if inner > 0 and self.count > inner:
                self.current = min(self.completed, self.count)
            else:
                self.current = int(index or self.current)
            self.bytes = 0
            self.bytes_total = 0
        self._push(force=True)

    def setMaxNum(self, size):
        with self._lock:
            self.bytes_total = int(size or 0)
            if self._started is None:
                self._started = time.monotonic()
        self._push(force=True)

    def addCurNum(self, size):
        with self._lock:
            self.bytes += int(size or 0)
            if self._started is None:
                self._started = time.monotonic()
        self._push()

    def updateStream(self, stream):
        return


class DownloadWorker(QRunnable):
    def __init__(self, backend, items):
        super().__init__()
        self.setAutoDelete(False)
        self.backend = backend
        self.items = items
        self.signals = WorkerSignals()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    @Slot()
    def run(self):
        failed = []
        cancelled = False
        try:
            for item in self.items:
                if self._cancelled:
                    cancelled = True
                    self.signals.item_status.emit(item, "Cancelled")
                    continue
                self.signals.item_status.emit(item, "Downloading")
                self.signals.log.emit(f"Starting {item.title}\n")
                reporter = ItemProgressReporter(item, self.signals.item_progress.emit)
                try:
                    self.backend.download(item, self.signals.log.emit, progress=reporter)
                except Exception as exc:
                    failed.append(item.title)
                    self.signals.item_status.emit(item, "Failed")
                    self.signals.log.emit(f"Failed {item.title}: {exc}\n")
                    continue
                self.signals.item_status.emit(item, "Done")
                self.signals.log.emit(f"Finished {item.title}\n")
            if cancelled:
                self.signals.log.emit("Remaining downloads cancelled.\n")
            if failed:
                shown = ", ".join(failed[:5])
                more = f" (+{len(failed) - 5} more)" if len(failed) > 5 else ""
                self.signals.error.emit(
                    f"{len(failed)} download{'s' if len(failed) != 1 else ''} failed: {shown}{more}"
                )
            elif not cancelled:
                self.signals.result.emit(self.items)
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()
