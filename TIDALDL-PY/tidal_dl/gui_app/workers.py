from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()
    log = Signal(str)
    item_status = Signal(object, str)


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


class DownloadWorker(QRunnable):
    def __init__(self, backend, items):
        super().__init__()
        self.setAutoDelete(False)
        self.backend = backend
        self.items = items
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        failed = []
        try:
            for item in self.items:
                self.signals.item_status.emit(item, "Downloading")
                self.signals.log.emit(f"Starting {item.title}\n")
                try:
                    self.backend.download(item, self.signals.log.emit)
                except Exception as exc:
                    failed.append(item.title)
                    self.signals.item_status.emit(item, "Failed")
                    self.signals.log.emit(f"Failed {item.title}: {exc}\n")
                    continue
                self.signals.item_status.emit(item, "Done")
                self.signals.log.emit(f"Finished {item.title}\n")
            if failed:
                shown = ", ".join(failed[:5])
                more = f" (+{len(failed) - 5} more)" if len(failed) > 5 else ""
                self.signals.error.emit(
                    f"{len(failed)} download{'s' if len(failed) != 1 else ''} failed: {shown}{more}"
                )
            else:
                self.signals.result.emit(self.items)
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()
