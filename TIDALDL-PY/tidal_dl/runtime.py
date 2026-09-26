"""Per-job output and cancellation, without replacing process-wide streams."""
import builtins
import contextlib
import contextvars
import hashlib
import logging
import logging.handlers
import os
import re
import subprocess
import time
from threading import Lock, RLock

from filelock import FileLock, Timeout as FileLockTimeout

_output = contextvars.ContextVar('tidekeeper_output', default=None)
_cancel = contextvars.ContextVar('tidekeeper_cancel', default=None)
_warning = contextvars.ContextVar('tidekeeper_warning', default=None)
_output_locks = {}
_output_locks_guard = Lock()


class DownloadCancelled(Exception):
    pass


@contextlib.contextmanager
def job_context(output=None, cancel=None, warning=None):
    out_token = _output.set(output)
    cancel_token = _cancel.set(cancel)
    warning_token = _warning.set(warning)
    try:
        yield
    finally:
        _warning.reset(warning_token)
        _cancel.reset(cancel_token)
        _output.reset(out_token)


def check_cancelled():
    event = _cancel.get()
    if event is not None and event.is_set():
        raise DownloadCancelled('Download cancelled; partial transfers kept for retry.')


@contextlib.contextmanager
def output_lock(path):
    """Serialize destination writers across threads and cooperating processes."""
    key = os.path.normcase(os.path.realpath(path))
    directory = os.path.join(os.path.dirname(key), '.tidekeeper-locks')
    # Case-fold only the lock identity, not the actual output directory. This
    # also serializes case aliases on case-insensitive macOS filesystems.
    key = key.casefold()
    lock_path = os.path.join(directory, hashlib.sha256(os.fsencode(key)).hexdigest() + '.lock')
    with _output_locks_guard:
        if key not in _output_locks:
            _output_locks[key] = (RLock(), FileLock(lock_path, mode=0o600,
                                                  preserve_lock_file=True, fallback_to_soft=False), 0)
        lock, file_lock, users = _output_locks[key]
        _output_locks[key] = lock, file_lock, users + 1
    acquired = file_acquired = False
    try:
        while not acquired:
            check_cancelled()
            acquired = lock.acquire(timeout=0.1)
        check_cancelled()
        os.makedirs(directory, exist_ok=True)
        while not file_acquired:
            check_cancelled()
            try:
                file_lock.acquire(timeout=0)
                file_acquired = True
            except FileLockTimeout:
                sleep(0.1)
        check_cancelled()
        yield
    finally:
        try:
            if file_acquired:
                file_lock.release()
        finally:
            if acquired:
                lock.release()
            with _output_locks_guard:
                remaining = _output_locks[key][2] - 1
                if remaining:
                    _output_locks[key] = lock, file_lock, remaining
                else:
                    del _output_locks[key]


def sleep(seconds):
    event = _cancel.get()
    if event is None:
        time.sleep(seconds)
    elif event.wait(max(0.0, seconds)):
        check_cancelled()


def report_warning(message):
    logging.warning(message)
    callback = _warning.get()
    if callback is not None:
        callback(message)


def run_process(args, timeout=300, check=False, capture_output=False, **kwargs):
    """Run media processing with cancellation and bounded cleanup."""
    if _cancel.get() is None:
        return subprocess.run(args, timeout=timeout, check=check, capture_output=capture_output, **kwargs)
    check_cancelled()
    if capture_output:
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with subprocess.Popen(args, **kwargs) as process:
        started = time.monotonic()
        try:
            while True:
                check_cancelled()
                if time.monotonic() - started > timeout:
                    raise subprocess.TimeoutExpired(args, timeout)
                try:
                    stdout, stderr = process.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    continue
        except BaseException:
            process.kill()
            process.communicate()
            raise
        result = subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
        if check:
            result.check_returncode()
        return result


def print(*values, sep=' ', end='\n', **kwargs):
    callback = _output.get()
    message = redact((' ' if sep is None else sep).join(str(value) for value in values))
    if callback is None or kwargs.get('file') is not None:
        return builtins.print(message, end=end, **kwargs)
    callback(message + ('\n' if end is None else end))


def redact(message):
    message = re.sub(r'(?i)((?:bearer|basic)\s+)[^\s,;\"\x27]+', r'\1[redacted]', str(message))
    message = re.sub(r'(https?://)[^\s/@]+:[^\s/@]+@', r'\1[redacted]@', message)
    message = re.sub(r'(?i)((?:access_?token|refresh_?token|client_?secret)\b[\"\x27]?\s*[:=]\s*[\"\x27]?)[^\s\"\x27,}]+',
                     r'\1[redacted]', message)
    return re.sub(r'(https?://[^\s?]+)\?[^\s]+', r'\1?[redacted]', message)


class _SafeFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))


class _JobHandler(logging.Handler):
    def emit(self, record):
        callback = _output.get()
        if callback is not None:
            callback(redact(self.format(record)) + '\n')


def configure_logging(path):
    root = logging.getLogger()
    absolute = os.path.abspath(path)
    if any(getattr(handler, 'baseFilename', None) == absolute for handler in root.handlers):
        return
    os.makedirs(os.path.dirname(absolute), exist_ok=True)
    descriptor = os.open(absolute, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    os.close(descriptor)
    os.chmod(absolute, 0o600)
    handler = logging.handlers.RotatingFileHandler(absolute, maxBytes=2 * 1024 * 1024, backupCount=2, encoding='utf-8')
    handler.setFormatter(_SafeFormatter('%(asctime)s %(levelname)s %(message)s'))
    handler.setLevel(logging.INFO)
    root.addHandler(handler)
    if not any(isinstance(item, _JobHandler) for item in root.handlers):
        gui = _JobHandler()
        gui.setLevel(logging.WARNING)
        root.addHandler(gui)
    root.setLevel(logging.INFO)
