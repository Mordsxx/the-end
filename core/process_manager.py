"""Subprocess handling (no console windows), cancellation, and background tasks for the GUI."""
import queue
import subprocess
import sys
import threading
import traceback
from typing import Callable

from .errors import CancelledError

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def popen(cmd, **kwargs) -> subprocess.Popen:
    kwargs.setdefault("creationflags", CREATE_NO_WINDOW)
    return subprocess.Popen([str(c) for c in cmd], **kwargs)


def run(cmd, timeout: float | None = None, **kwargs) -> subprocess.CompletedProcess:
    kwargs.setdefault("creationflags", CREATE_NO_WINDOW)
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("encoding", "utf-8")
    kwargs.setdefault("errors", "replace")
    return subprocess.run([str(c) for c in cmd], timeout=timeout, **kwargs)


class CancelToken:
    """Cooperative cancellation. Registered child processes are killed on cancel()."""

    def __init__(self):
        self._event = threading.Event()
        self._procs: list[subprocess.Popen] = []
        self._lock = threading.Lock()

    @property
    def is_set(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self._event.is_set():
            raise CancelledError("Operation cancelled.")

    def register(self, proc: subprocess.Popen) -> subprocess.Popen:
        with self._lock:
            self._procs.append(proc)
        if self._event.is_set():
            self._kill(proc)
        return proc

    def cancel(self) -> None:
        self._event.set()
        with self._lock:
            for p in self._procs:
                self._kill(p)

    @staticmethod
    def _kill(proc: subprocess.Popen) -> None:
        try:
            if proc.poll() is None:
                proc.kill()
        except OSError:
            pass


class BackgroundTask:
    """Runs fn(progress=..., cancel=...) in a thread; the GUI polls .poll() from its own thread."""

    def __init__(self, fn: Callable):
        self._fn = fn
        self.cancel_token = CancelToken()
        self._q: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self.running = False

    def start(self, **kwargs) -> None:
        self.running = True
        self._thread = threading.Thread(target=self._main, kwargs=kwargs, daemon=True)
        self._thread.start()

    def _main(self, **kwargs):
        try:
            result = self._fn(progress=self._progress, cancel=self.cancel_token, **kwargs)
            self._q.put(("done", result))
        except CancelledError as e:
            self._q.put(("cancelled", e))
        except Exception as e:  # reported to the user, never swallowed
            self._q.put(("error", e, traceback.format_exc()))

    def _progress(self, fraction: float, text: str = "", **extra):
        self._q.put(("progress", max(0.0, min(1.0, fraction)), text, extra))

    def cancel(self) -> None:
        self.cancel_token.cancel()

    def poll(self) -> list:
        msgs = []
        while True:
            try:
                msgs.append(self._q.get_nowait())
            except queue.Empty:
                break
        if any(m[0] in ("done", "error", "cancelled") for m in msgs):
            self.running = False
        return msgs
