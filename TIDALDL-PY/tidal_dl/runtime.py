"""Per-job output and cancellation, without replacing process-wide streams."""
import builtins
import contextlib
import contextvars
import logging
import logging.handlers
import os
import re
import subprocess
import time

_output = contextvars.ContextVar('tidekeeper_output', default=None)
_cancel = contextvars.ContextVar('tidekeeper_cancel', default=None)
_warning = contextvars.ContextVar('tidekeeper_warning', default=None)


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
    if callback is None or kwargs.get('file') is not None:
        return builtins.print(*values, sep=sep, end=end, **kwargs)
    callback(redact(sep.join(str(value) for value in values) + end))


def redact(message):
    message = re.sub(r'(?i)(bearer\s+)[^\s,;]+', r'\1[redacted]', str(message))
    message = re.sub(r'(?i)((?:access_?token|refresh_?token|client_?secret)[\s\"\x27:=]+)[^\s\"\x27,}]+',
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
