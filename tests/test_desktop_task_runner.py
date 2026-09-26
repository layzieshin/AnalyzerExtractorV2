from __future__ import annotations

import threading
import time
from collections.abc import Callable
from unittest.mock import patch

from interfaces.tk.task_runner import TkTaskRunner


class _FakeRoot:
    def __init__(self) -> None:
        self._callbacks: list[tuple[int, Callable[[], None]]] = []
        self._counter = 0
        self.reported: list[str] = []

    def after(self, delay_ms: int, callback: Callable[[], None]) -> str:
        self._counter += 1
        handle = f"after-{self._counter}"
        self._callbacks.append((delay_ms, callback))
        return handle

    def after_cancel(self, handle: str) -> None:
        return None

    def report_callback_exception(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self.reported.append(str(exc))

    def drain_pending(self, *, max_rounds: int = 20) -> None:
        for _ in range(max_rounds):
            if not self._callbacks:
                return
            pending = list(self._callbacks)
            self._callbacks.clear()
            for _delay, callback in pending:
                callback()


def test_submit_rejects_duplicate_keys_until_complete() -> None:
    root = _FakeRoot()
    runner = TkTaskRunner(root, poll_ms=1)
    started = threading.Event()
    release = threading.Event()

    def work() -> str:
        started.set()
        release.wait(timeout=2.0)
        return "ok"

    assert runner.submit("refresh", work) is True
    assert runner.submit("refresh", work) is False
    started.wait(timeout=2.0)
    release.set()
    time.sleep(0.02)
    root.drain_pending()
    assert runner.is_active("refresh") is False
    assert runner.submit("refresh", work) is True
    release.set()
    time.sleep(0.02)
    root.drain_pending()
    runner.shutdown_runner()


def test_worker_runs_off_main_thread_and_callback_on_poll_thread() -> None:
    root = _FakeRoot()
    runner = TkTaskRunner(root, poll_ms=5)
    worker_threads: list[int] = []
    callback_threads: list[int] = []
    main_thread = threading.get_ident()

    def work() -> int:
        worker_threads.append(threading.get_ident())
        return 7

    def on_success(value: int) -> None:
        callback_threads.append(threading.get_ident())
        assert value == 7

    assert runner.submit("task", work, on_success=on_success) is True
    time.sleep(0.05)
    root.drain_pending()
    assert worker_threads
    assert worker_threads[0] != main_thread
    assert callback_threads
    assert callback_threads[0] == main_thread
    runner.shutdown_runner()


def test_callback_exception_is_reported_and_next_completion_still_runs() -> None:
    root = _FakeRoot()
    runner = TkTaskRunner(root, poll_ms=5)
    seen: list[str] = []

    def boom(_value: int) -> None:
        raise RuntimeError("boom")

    def ok(value: int) -> None:
        seen.append(f"ok:{value}")

    assert runner.submit("first", lambda: 1, on_success=boom) is True
    time.sleep(0.03)
    root.drain_pending()
    assert root.reported == ["boom"]
    assert runner.submit("second", lambda: 2, on_success=ok) is True
    time.sleep(0.03)
    root.drain_pending()
    assert seen == ["ok:2"]
    runner.shutdown_runner()


def test_cancel_key_suppresses_callback_but_keeps_key_reserved_until_done() -> None:
    root = _FakeRoot()
    runner = TkTaskRunner(root, poll_ms=1)
    started = threading.Event()
    release = threading.Event()
    seen: list[str] = []

    def work() -> str:
        started.set()
        release.wait(timeout=2.0)
        return "done"

    assert runner.submit("refresh", work, on_success=lambda _v: seen.append("called")) is True
    started.wait(timeout=2.0)
    runner.cancel_key("refresh")
    assert runner.is_active("refresh") is True
    assert runner.submit("refresh", work) is False
    release.set()
    time.sleep(0.02)
    root.drain_pending()
    assert seen == []
    assert runner.is_active("refresh") is False
    runner.shutdown_runner()


def test_shutdown_waits_for_in_flight_worker_and_blocks_new_submit() -> None:
    root = _FakeRoot()
    runner = TkTaskRunner(root, poll_ms=1)
    release = threading.Event()

    def work() -> str:
        release.wait(timeout=2.0)
        return "ok"

    assert runner.submit("processing", work) is True
    finished = runner.shutdown_runner(join_timeout_s=1.0)
    assert finished is False
    assert runner.submit("processing", work) is False
    release.set()
    finished = runner.shutdown_runner(join_timeout_s=2.0)
    assert finished is True
    assert runner.submit("processing", work) is False


def test_submit_after_shutdown_returns_false() -> None:
    root = _FakeRoot()
    runner = TkTaskRunner(root, poll_ms=1)
    runner.shutdown_runner()
    assert runner.submit("task", lambda: None) is False
    assert runner.shutdown is True


def test_thread_start_failure_rolls_back_active_key() -> None:
    root = _FakeRoot()
    runner = TkTaskRunner(root, poll_ms=1)

    with patch.object(threading.Thread, "start", side_effect=RuntimeError("start failed")):
        assert runner.submit("task", lambda: None) is False
    assert runner.is_active("task") is False
    assert runner.submit("task", lambda: "ok") is True
    time.sleep(0.02)
    root.drain_pending()
    runner.shutdown_runner()


def test_submit_vs_shutdown_race_rejects_late_submit() -> None:
    root = _FakeRoot()
    runner = TkTaskRunner(root, poll_ms=1)
    release = threading.Event()

    def work() -> str:
        release.wait(timeout=2.0)
        return "ok"

    assert runner.submit("processing", work) is True
    runner.shutdown_runner(join_timeout_s=0.2)
    assert runner.submit("processing", work) is False
    release.set()
    runner.shutdown_runner(join_timeout_s=2.0)
