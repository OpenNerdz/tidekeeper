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
import sys
import tempfile
import time
from threading import Lock, RLock

from filelock import FileLock, Timeout as FileLockTimeout

_output = contextvars.ContextVar('tidekeeper_output', default=None)
_cancel = contextvars.ContextVar('tidekeeper_cancel', default=None)
_warning = contextvars.ContextVar('tidekeeper_warning', default=None)
_output_locks = {}
_output_locks_guard = Lock()
_shared_lock_warnings = set()
# Tell the user why a download pauses when another one is writing the same file.
LOCK_NOTICE_SECONDS = 2.0
LOCK_SLOT_COUNT = 256
LEGACY_LOCK_GRACE_SECONDS = 24 * 60 * 60
_LEGACY_LOCK_NAME = re.compile(r'^[0-9a-f]{64}\.lock$')


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


def _preferred_lock_directory():
    if sys.platform == 'win32':
        base = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
        return os.path.join(base, 'Tidekeeper', 'locks')
    if sys.platform == 'darwin':
        return os.path.join(os.path.expanduser('~'), 'Library', 'Caches', 'Tidekeeper', 'locks')
    home = os.environ.get('HOME') or os.path.expanduser('~')
    state = os.environ.get('XDG_STATE_HOME') or os.path.join(home, '.local', 'state')
    return os.path.join(state, 'tidekeeper', 'locks')


def _temporary_lock_directory():
    identity = str(os.getuid()) if hasattr(os, 'getuid') else os.environ.get('USERNAME', 'user')
    identity = re.sub(r'[^A-Za-z0-9_.-]', '_', identity)
    return os.path.join(tempfile.gettempdir(), f'tidekeeper-{identity}', 'locks')


def _shared_lock_directory(path):
    """One bounded lock folder shared by hosts that share the download root."""
    try:
        from .paths import downloadRoot
        root = os.path.realpath(os.path.abspath(downloadRoot()))
        target = os.path.realpath(os.path.abspath(path))
        if os.path.commonpath((root, target)) != root:
            return None
    except (ImportError, OSError, ValueError):
        return None
    return os.path.join(root, '.tidekeeper-locks')


def _prepare_lock_directory(directory, mode):
    try:
        os.makedirs(directory, mode=mode, exist_ok=True)
        try:
            os.chmod(directory, mode)
        except OSError:
            pass
        with tempfile.NamedTemporaryFile(prefix='.probe-', dir=directory):
            pass
        return True
    except OSError:
        return False


def _cleanup_legacy_lock_directory(directory, remove_empty=False):
    """Best-effort removal of inactive per-destination locks from older releases."""
    try:
        names = os.listdir(directory)
    except OSError:
        return
    cutoff = time.time() - LEGACY_LOCK_GRACE_SECONDS
    for name in names:
        if not _LEGACY_LOCK_NAME.fullmatch(name):
            continue
        path = os.path.join(directory, name)
        try:
            if os.path.getmtime(path) > cutoff:
                continue
            stale_lock = FileLock(path, mode=0o600, preserve_lock_file=True, fallback_to_soft=False)
            stale_lock.acquire(timeout=0)
            stale_lock.release()
            os.unlink(path)
        except (FileLockTimeout, OSError):
            continue
    if remove_empty:
        try:
            os.rmdir(directory)
        except OSError:
            pass


def lock_directory(path=None):
    """Return a verified local lock folder without making downloads depend on HOME."""
    candidates = [(_preferred_lock_directory(), 0o700), (_temporary_lock_directory(), 0o700)]
    shared = _shared_lock_directory(path) if path else None
    if shared:
        candidates.append((shared, 0o1777))
    checked = set()
    for directory, mode in candidates:
        directory = os.path.abspath(directory)
        if directory in checked:
            continue
        checked.add(directory)
        if _prepare_lock_directory(directory, mode):
            _cleanup_legacy_lock_directory(directory)
            return directory
    raise PermissionError('No writable lock folder is available in app state, temporary storage, or downloads')


def _slot_path(directory, key):
    slot = int.from_bytes(hashlib.sha256(os.fsencode(key)).digest()[:8], 'big') % LOCK_SLOT_COUNT
    return os.path.join(directory, f'slot-{slot:03d}.lock')


def _shared_key(path):
    try:
        from .paths import downloadRoot
        root = os.path.realpath(os.path.abspath(downloadRoot()))
        target = os.path.realpath(os.path.abspath(path))
        return os.path.relpath(target, root).replace(os.sep, '/').casefold()
    except (ImportError, OSError, ValueError):
        return os.path.normcase(os.path.realpath(path))


def _warn_shared_lock(directory, error):
    with _output_locks_guard:
        if directory in _shared_lock_warnings:
            return
        _shared_lock_warnings.add(directory)
    report_warning(f'Shared download locking is unavailable at {directory}: {error}. '
                   'Downloads on this computer remain protected.')


@contextlib.contextmanager
def _cooperative_lock(lock_path, announce_wait, optional=False, shared=False):
    with _output_locks_guard:
        if lock_path not in _output_locks:
            _output_locks[lock_path] = (
                RLock(),
                FileLock(lock_path, mode=0o666 if shared else 0o600,
                         preserve_lock_file=True, fallback_to_soft=shared),
                0,
            )
        thread_lock, file_lock, users = _output_locks[lock_path]
        _output_locks[lock_path] = thread_lock, file_lock, users + 1
    acquired = file_acquired = False
    failure = None
    try:
        while not acquired:
            check_cancelled()
            acquired = thread_lock.acquire(timeout=0.1)
            if not acquired:
                announce_wait()
        check_cancelled()
        while not file_acquired:
            check_cancelled()
            try:
                file_lock.acquire(timeout=0)
                file_acquired = True
            except FileLockTimeout:
                announce_wait()
                sleep(0.1)
            except OSError as error:
                if not optional:
                    raise
                failure = error
                break
        if failure is not None:
            _warn_shared_lock(os.path.dirname(lock_path), failure)
        check_cancelled()
        yield file_acquired
    finally:
        try:
            if file_acquired:
                file_lock.release()
        finally:
            if acquired:
                thread_lock.release()
            with _output_locks_guard:
                remaining = _output_locks[lock_path][2] - 1
                if remaining:
                    _output_locks[lock_path] = thread_lock, file_lock, remaining
                else:
                    del _output_locks[lock_path]


@contextlib.contextmanager
def output_lock(path):
    """Serialize destination writers locally and, when supported, across hosts."""
    key = os.path.normcase(os.path.realpath(path))
    # Conservatively serialize filename case aliases, but keep distinct output
    # directories distinct on case-sensitive filesystems.
    key = os.path.join(os.path.dirname(key), os.path.basename(key).casefold())
    local_directory = lock_directory(path)
    shared_directory = _shared_lock_directory(path)
    local_is_shared = (
        shared_directory is not None
        and os.path.abspath(shared_directory) == os.path.abspath(local_directory)
    )
    local_path = _slot_path(local_directory, _shared_key(path) if local_is_shared else key)
    shared_path = None
    if shared_directory and not local_is_shared:
        if _prepare_lock_directory(shared_directory, 0o1777):
            _cleanup_legacy_lock_directory(shared_directory)
            shared_path = _slot_path(shared_directory, _shared_key(path))
        else:
            _warn_shared_lock(shared_directory, 'folder is not writable')
    old_directory = os.path.join(os.path.dirname(os.path.abspath(path)), '.tidekeeper-locks')
    if not shared_directory or os.path.abspath(old_directory) != os.path.abspath(shared_directory):
        _cleanup_legacy_lock_directory(old_directory, remove_empty=True)
    announced = False
    started = time.monotonic()

    def announce_wait():
        nonlocal announced
        if not announced and time.monotonic() - started >= LOCK_NOTICE_SECONDS:
            announced = True
            print(f'Waiting for another download to finish writing "{os.path.basename(path)}"...')

    with _cooperative_lock(local_path, announce_wait, shared=local_is_shared):
        if shared_path:
            with _cooperative_lock(shared_path, announce_wait, optional=True, shared=True):
                yield
        else:
            yield


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
