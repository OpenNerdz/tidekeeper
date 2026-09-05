from __future__ import annotations

import time
from threading import RLock, Event

from ..runtime import DownloadCancelled

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


class EntryProgress:
    """Byte counters owned by a single file, including its segment workers."""
    def __init__(self, parent, key):
        self.parent = parent
        self.key = key
        self.cancel_event = parent.cancel_event

    def setMaxNum(self, size):
        self.parent._update(self.key, total=max(0, int(size or 0)))

    def addCurNum(self, size):
        self.parent._update(self.key, delta=int(size or 0))

    def updateStream(self, stream):
        self.parent.updateStream(stream)

    def note_warning(self, message):
        self.parent.note_warning(message)


class ItemProgressReporter:
    """Aggregate completed entries and independent active transfer counters."""
    def __init__(self, item, emit, cancel_event=None):
        self.item = item
        self._emit = emit
        self._lock = RLock()
        self.cancel_event = cancel_event
        self.completed = 0
        self.count = 0
        self.current = 0
        self._offset = 0
        self._allocated = 0
        self._entries = {}
        self._finished = set()
        self._started = time.monotonic()
        self._last_emit = 0.0
        self._transferred = 0
        self._qualities = set()
        self.warnings = []

    def snapshot(self):
        with self._lock:
            active = [value for key, value in self._entries.items() if key not in self._finished]
            current = sum(value['bytes'] for value in active)
            total = sum(value['total'] for value in active)
            fraction = sum(min(value['bytes'] / value['total'], 1) for value in active if value['total'] > 0)
            elapsed = max(time.monotonic() - self._started, 0.05)
            return {'completed': self.completed, 'count': self.count, 'current': self.current,
                    'bytes': current, 'bytes_total': total, 'file_fraction': fraction,
                    'speed': self._transferred / elapsed, 'eta': None,
                    'actual_quality': ', '.join(sorted(self._qualities)),
                    'active': bool(active) or self.completed < self.count}

    def _push(self, force=False):
        with self._lock:
            now = time.monotonic()
            if not force and now - self._last_emit < 0.1:
                return
            self._last_emit = now
            self._emit(self.item, self.snapshot())

    def begin_collection(self, total):
        with self._lock:
            self._offset = self._allocated
            self._allocated += max(0, int(total or 0))
            self.count = max(self.count, self._allocated)
        self._push(True)

    def plan_collection(self, total):
        with self._lock:
            self.count = max(self.count, self._allocated + total)
        self._push(True)

    def begin_entry(self, index, total, title=''):
        with self._lock:
            if not self.count:
                self.count = int(total or 1)
            self.current = self._offset + int(index or 1)
            self._entries[self.current] = {'bytes': 0, 'total': 0}
        self._push(True)

    def for_entry(self, index):
        return EntryProgress(self, self._offset + index)

    def finish_entry(self, index, total, ok=True):
        with self._lock:
            key = self._offset + index
            self._finished.add(key)
            self.completed = len(self._finished)
        self._push(True)

    def _update(self, key, total=None, delta=0):
        with self._lock:
            value = self._entries.setdefault(key, {'bytes': 0, 'total': 0})
            if total is not None:
                value['total'] = total
            value['bytes'] += delta
            self._transferred += max(0, delta)
        self._push(total is not None)

    def setMaxNum(self, size):
        self._update(self.current, total=max(0, int(size or 0)))

    def addCurNum(self, size):
        self._update(self.current, delta=int(size or 0))

    def updateStream(self, stream):
        label = getattr(stream, 'soundQuality', '') or getattr(stream, 'resolution', '')
        codec = getattr(stream, 'codec', '')
        with self._lock:
            if label:
                self._qualities.add(f'{label} ({codec})' if codec else label)
        self._push(True)

    def note_warning(self, message):
        with self._lock:
            self.warnings.append(message)


class DownloadWorker(QRunnable):
    def __init__(self, backend, items, more_items=None):
        super().__init__()
        self.setAutoDelete(False)
        self.backend = backend
        self.items = items
        self.more_items = more_items
        self.signals = WorkerSignals()
        self._cancelled = Event()

    def cancel(self):
        self._cancelled.set()

    def _next_items(self, processed):
        extra = self.more_items() if self.more_items else []
        return [item for item in extra if id(item) not in processed]

    @Slot()
    def run(self):
        failed = []
        cancelled = False
        processed = set()
        try:
            items = list(self.items)
            idx = 0
            while True:
                while idx < len(items):
                    item = items[idx]
                    idx += 1
                    if id(item) in processed:
                        continue
                    processed.add(id(item))
                    if self._cancelled.is_set():
                        cancelled = True
                        self.signals.item_status.emit(item, "Cancelled")
                        continue
                    self.signals.item_status.emit(item, "Downloading")
                    self.signals.log.emit(f"Starting {item.title}\n")
                    reporter = ItemProgressReporter(item, self.signals.item_progress.emit, self._cancelled)
                    try:
                        self.backend.download(item, self.signals.log.emit, progress=reporter)
                    except DownloadCancelled:
                        cancelled = True
                        self._cancelled.set()
                        self.signals.item_status.emit(item, "Cancelled")
                        continue
                    except Exception as exc:
                        failed.append(item.title)
                        self.signals.item_status.emit(item, "Failed")
                        self.signals.log.emit(f"Failed {item.title}: {exc}\n")
                        continue
                    self.signals.item_status.emit(item, "Partial" if reporter.warnings else "Done")
                    self.signals.log.emit(f"Finished {item.title}\n")
                if cancelled:
                    break
                extra = self._next_items(processed)
                if not extra:
                    break
                items.extend(extra)
            if cancelled:
                self.signals.log.emit("Remaining downloads cancelled.\n")
            if failed:
                shown = ", ".join(failed[:5])
                more = f" (+{len(failed) - 5} more)" if len(failed) > 5 else ""
                self.signals.error.emit(
                    f"{len(failed)} download{'s' if len(failed) != 1 else ''} failed: {shown}{more}"
                )
            elif not cancelled:
                self.signals.result.emit(items)
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()
