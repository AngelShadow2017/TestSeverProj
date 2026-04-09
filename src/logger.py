import datetime
import os
import queue
import sys
import threading
import atexit
from pathlib import Path
from typing import TextIO


class Logger:
    def __init__(self, save_path: str):
        self.path = Path(save_path).expanduser().resolve()
        self.path.mkdir(parents=True, exist_ok=True)

        self._file_handle: TextIO | None = None
        self._current_day: datetime.date | None = None
        self._queue: queue.Queue[tuple[str, datetime.datetime] | object] = queue.Queue()
        self._sentinel = object()
        self._state_lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._closed = False

        self._previous_excepthook = sys.excepthook
        atexit.register(self.close)
        sys.excepthook = self._excepthook

    def file_name(self, now: datetime.datetime | None = None) -> str:
        current = now or datetime.datetime.now()
        return current.strftime("%Y.%m.%d") + ".log"

    def file_path(self, now: datetime.datetime | None = None) -> Path:
        return self.path / self.file_name(now)

    def ensure_file(self, now: datetime.datetime | None = None) -> Path:
        log_path = self.file_path(now)
        log_path.touch(exist_ok=True)
        return log_path

    def _start_worker_if_needed(self) -> None:
        with self._state_lock:
            if self._closed:
                return
            if self._worker is not None and self._worker.is_alive():
                return

            self._worker = threading.Thread(target=self._worker_loop, name="LoggerWriter")
            self._worker.start()

    def _worker_loop(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is self._sentinel:
                    break

                text, now = item
                self._rotate_if_needed(now)
                if self._file_handle is None:
                    continue

                self._file_handle.write(text)
                self._file_handle.flush()
                os.fsync(self._file_handle.fileno())
            finally:
                self._queue.task_done()

        self._close_file_handle()

    def _rotate_if_needed(self, now: datetime.datetime) -> None:
        target_day = now.date()
        if self._file_handle is not None and self._current_day == target_day:
            return

        self._close_file_handle()
        log_path = self.ensure_file(now)
        self._file_handle = log_path.open("a", encoding="utf-8")
        self._current_day = target_day

    def _close_file_handle(self) -> None:
        if self._file_handle is not None:
            self._file_handle.close()
            self._file_handle = None
            self._current_day = None

    def open(self, now: datetime.datetime | None = None) -> Path:
        current = now or datetime.datetime.now()
        self._start_worker_if_needed()
        return self.file_path(current)

    def write(self, text: str, now: datetime.datetime | None = None) -> None:
        if not text:
            return

        current = now or datetime.datetime.now()
        self._start_worker_if_needed()
        with self._state_lock:
            if self._closed:
                return
            self._queue.put_nowait((text, current))

    def write_line(self, text: str, now: datetime.datetime | None = None) -> None:
        self.write(text + "\n", now)

    def flush(self) -> None:
        worker = self._worker
        if worker is None:
            return
        self._queue.join()

    def close(self) -> None:
        worker: threading.Thread | None
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            worker = self._worker

            if worker is None:
                self._close_file_handle()
                return

            self._queue.put(self._sentinel)

        worker.join()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _excepthook(self, exc_type, exc, tb):
        # Best effort: drain queued logs before process exits on uncaught exception.
        try:
            self.close()
        finally:
            self._previous_excepthook(exc_type, exc, tb)

