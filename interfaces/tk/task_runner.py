from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from typing import Any


class TkTaskRunner:
    """Run work on background threads; deliver callbacks on the Tk main thread."""

    def __init__(self, root: Any, *, poll_ms: int = 50) -> None:
        self._root = root
        self._poll_ms = max(10, int(poll_ms))
        self._completion_queue: queue.Queue[tuple[str, bool, Any]] = queue.Queue()
        self._active_keys: set[str] = set()
        self._suppressed_callbacks: set[str] = set()
        self._workers: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._shutdown = False
        self._poll_after_id: str | None = None
        self._start_polling()

    @property
    def shutdown(self) -> bool:
        with self._lock:
            return self._shutdown

    def is_active(self, key: str) -> bool:
        with self._lock:
            return key in self._active_keys

    def active_keys(self) -> frozenset[str]:
        with self._lock:
            return frozenset(self._active_keys)

    def has_in_flight_workers(self) -> bool:
        with self._lock:
            return bool(self._workers)

    def in_flight_worker_keys(self) -> frozenset[str]:
        with self._lock:
            return frozenset(self._workers)

    def submit(
        self,
        key: str,
        work: Callable[[], Any],
        *,
        on_success: Callable[[Any], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
    ) -> bool:
        thread: threading.Thread | None = None
        with self._lock:
            if self._shutdown:
                return False
            if key in self._active_keys:
                return False
            self._active_keys.add(key)
            self._suppressed_callbacks.discard(key)

            def _worker() -> None:
                try:
                    result = work()
                    self._completion_queue.put((key, True, (result, on_success)))
                except BaseException as exc:
                    self._completion_queue.put((key, False, (exc, on_error)))

            thread = threading.Thread(target=_worker, name=f"tk-task-{key}", daemon=False)
            self._workers[key] = thread
            try:
                thread.start()
            except Exception:
                self._active_keys.discard(key)
                self._workers.pop(key, None)
                return False
        return True

    def cancel_key(self, key: str) -> None:
        with self._lock:
            self._suppressed_callbacks.add(key)

    def shutdown_runner(self, *, join_timeout_s: float = 5.0) -> bool:
        with self._lock:
            self._shutdown = True
            self._suppressed_callbacks.update(self._active_keys)
            workers = list(self._workers.values())
        if self._poll_after_id is not None:
            try:
                self._root.after_cancel(self._poll_after_id)
            except Exception:
                pass
            self._poll_after_id = None
        finished = True
        deadline = time.monotonic() + max(0.1, float(join_timeout_s))
        for worker in workers:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                finished = False
                break
            worker.join(timeout=remaining)
            if worker.is_alive():
                finished = False
        with self._lock:
            if finished:
                self._active_keys.clear()
                self._workers.clear()
        return finished

    def _report_callback_exception(self, exc: BaseException) -> None:
        reporter = getattr(self._root, "report_callback_exception", None)
        if reporter is None:
            return
        try:
            reporter(type(exc), exc, exc.__traceback__)
        except Exception:
            pass

    def _start_polling(self) -> None:
        with self._lock:
            if self._shutdown:
                return
        self._poll_after_id = self._root.after(self._poll_ms, self._poll_completions)

    def _poll_completions(self) -> None:
        try:
            with self._lock:
                if self._shutdown:
                    return
            while True:
                try:
                    key, ok, payload = self._completion_queue.get_nowait()
                except queue.Empty:
                    break
                with self._lock:
                    self._active_keys.discard(key)
                    self._workers.pop(key, None)
                    suppressed = key in self._suppressed_callbacks
                    if suppressed:
                        self._suppressed_callbacks.discard(key)
                    shutting_down = self._shutdown
                if suppressed or shutting_down:
                    continue
                try:
                    if ok:
                        result, callback = payload
                        if callback is not None:
                            callback(result)
                    else:
                        exc, callback = payload
                        if callback is not None:
                            callback(exc)
                except BaseException as exc:
                    self._report_callback_exception(exc)
        finally:
            with self._lock:
                shutting_down = self._shutdown
            if not shutting_down:
                self._start_polling()
