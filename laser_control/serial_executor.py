import itertools
import heapq
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum


LogFn = Callable[[str], None]


class SerialPriority(IntEnum):
    EMERGENCY = 0
    PAUSE = 1
    RESUME = 2
    STATUS = 3
    MANUAL = 4
    JOB = 5
    CONNECTION = 6


@dataclass
class SerialCommandResult:
    value: object = None
    error: BaseException | None = None


class SerialCommandHandle:
    def __init__(self) -> None:
        self._done = threading.Event()
        self._result = SerialCommandResult()

    def set_result(self, value: object) -> None:
        self._result = SerialCommandResult(value=value)
        self._done.set()

    def set_error(self, error: BaseException) -> None:
        self._result = SerialCommandResult(error=error)
        self._done.set()

    def result(self, timeout: float | None = None):
        if not self._done.wait(timeout):
            raise TimeoutError("SerialExecutor Timeout beim Warten auf Befehlsabschluss.")
        if self._result.error is not None:
            raise self._result.error
        return self._result.value


class SerialExecutor:
    def __init__(self, log: LogFn | None = None) -> None:
        self._log = log
        self._serial = None
        self._line_buffer: list[str] = []
        self._queue: queue.PriorityQueue[tuple[int, int, Callable[[], object], SerialCommandHandle]] = queue.PriorityQueue()
        self._counter = itertools.count()
        self._stop_event = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True, name="SerialExecutor")
        self._worker.start()

    @property
    def connection(self):
        return self._serial

    @property
    def is_open(self) -> bool:
        return bool(self._serial is not None and getattr(self._serial, "is_open", False))

    @property
    def port(self) -> str:
        return str(getattr(self._serial, "port", ""))

    @property
    def is_queue_empty(self) -> bool:
        return self._queue.empty()

    def submit(
        self,
        operation: Callable[[], object],
        priority: SerialPriority = SerialPriority.MANUAL,
        timeout: float | None = None,
    ):
        if self._stop_event.is_set():
            raise RuntimeError("SerialExecutor wurde gestoppt.")
        handle = SerialCommandHandle()
        self._queue.put((int(priority), next(self._counter), operation, handle))
        return handle.result(timeout)

    def open(self, serial_factory: Callable[[], object], timeout: float = 5.0) -> None:
        def operation() -> None:
            self._close_current()
            self._serial = serial_factory()
            self._log_event(f"Port geoeffnet: {self.port or '<unbekannt>'}")

        self.submit(operation, SerialPriority.CONNECTION, timeout=timeout)

    def open_serial(
        self,
        serial_module,
        port: str,
        baudrate: int,
        timeout: float,
        write_timeout: float,
        open_timeout: float = 5.0,
    ) -> None:
        self.open(
            lambda: serial_module.Serial(
                port=port,
                baudrate=baudrate,
                timeout=timeout,
                write_timeout=write_timeout,
            ),
            timeout=open_timeout,
        )

    def close(self, timeout: float = 5.0) -> None:
        self.clear_pending(min_priority=SerialPriority.STATUS)
        self.submit(self._close_current, SerialPriority.EMERGENCY, timeout=timeout)

    def clear_pending(self, min_priority: SerialPriority = SerialPriority.MANUAL) -> int:
        removed = 0
        with self._queue.mutex:
            kept = []
            while self._queue.queue:
                item = heapq.heappop(self._queue.queue)
                priority, _index, _operation, handle = item
                if priority >= int(min_priority):
                    handle.set_error(RuntimeError("Serial-Befehl durch Echtzeitkommando abgebrochen."))
                    removed += 1
                else:
                    kept.append(item)
            for item in kept:
                heapq.heappush(self._queue.queue, item)
            self._queue.unfinished_tasks = max(0, self._queue.unfinished_tasks - removed)
            self._queue.not_full.notify_all()
        if removed:
            self._log_event(f"{removed} wartende Serial-Befehl(e) verworfen.")
        return removed

    def write_raw(self, value: str, priority: SerialPriority = SerialPriority.MANUAL, timeout: float = 2.0) -> None:
        self.submit(lambda: self._write_raw_locked(value), priority, timeout=timeout)

    def query_line(
        self,
        command: str,
        wait_seconds: float,
        priority: SerialPriority = SerialPriority.MANUAL,
    ) -> str:
        return self.submit(lambda: self._query_line_locked(command, wait_seconds), priority, timeout=wait_seconds + 1.0)

    def read_available_after_write(
        self,
        value: str,
        wait_seconds: float,
        priority: SerialPriority = SerialPriority.STATUS,
    ) -> str:
        return self.submit(
            lambda: self._read_available_after_write_locked(value, wait_seconds),
            priority,
            timeout=wait_seconds + 1.0,
        )

    def query_status_report(
        self,
        value: str = "?",
        wait_seconds: float = 0.6,
        priority: SerialPriority = SerialPriority.STATUS,
    ) -> str:
        return self.submit(
            lambda: self._query_status_report_locked(value, wait_seconds),
            priority,
            timeout=wait_seconds + 1.0,
        )

    def read_available(self, wait_seconds: float, priority: SerialPriority = SerialPriority.MANUAL) -> str:
        return self.submit(lambda: self._read_available_locked(wait_seconds), priority, timeout=wait_seconds + 1.0)

    def reset_input_buffer(self, timeout: float = 2.0) -> None:
        self.submit(self._reset_input_buffer_locked, SerialPriority.CONNECTION, timeout=timeout)

    def shutdown(self) -> None:
        if self._stop_event.is_set():
            return
        self.clear_pending(min_priority=SerialPriority.PAUSE)
        try:
            self.close(timeout=2.0)
        except Exception as exc:  # noqa: BLE001 - shutdown must continue
            self._log_event(f"Fehler beim Schliessen des Ports: {exc}")
        self._stop_event.set()
        self._queue.put((int(SerialPriority.EMERGENCY), next(self._counter), lambda: None, SerialCommandHandle()))
        self._worker.join(timeout=2.0)
        self._log_event("SerialExecutor gestoppt.")

    def _run(self) -> None:
        while True:
            _priority, _index, operation, handle = self._queue.get()
            if self._stop_event.is_set():
                handle.set_result(None)
                self._queue.task_done()
                break
            try:
                handle.set_result(operation())
            except Exception as exc:  # noqa: BLE001 - return failures to caller
                handle.set_error(exc)
                self._log_event(f"Serial-Fehler: {exc}")
            finally:
                self._queue.task_done()

    def _close_current(self) -> None:
        if self._serial is not None:
            try:
                if getattr(self._serial, "is_open", False):
                    self._serial.close()
                    self._log_event(f"Port geschlossen: {getattr(self._serial, 'port', '<unbekannt>')}")
            finally:
                self._serial = None

    def _require_open(self):
        if self._serial is None or not getattr(self._serial, "is_open", False):
            raise RuntimeError("Nicht verbunden.")
        return self._serial

    def _reset_input_buffer_locked(self) -> None:
        connection = self._require_open()
        connection.reset_input_buffer()

    def _write_raw_locked(self, value: str) -> None:
        connection = self._require_open()
        try:
            connection.write(value.encode("ascii"))
            connection.flush()
        except Exception:
            self._serial = None
            raise

    def _query_line_locked(self, command: str, wait_seconds: float) -> str:
        self._write_raw_locked(command.strip() + "\n")
        return self._read_until_ok_or_error_locked(wait_seconds)

    def _read_available_after_write_locked(self, value: str, wait_seconds: float) -> str:
        self._write_raw_locked(value)
        return self._read_available_locked(wait_seconds)

    def _read_until_ok_or_error_locked(self, wait_seconds: float) -> str:
        connection = self._require_open()
        end_time = time.monotonic() + wait_seconds
        lines = []
        while time.monotonic() < end_time:
            self._run_priority_interrupts(SerialPriority.STATUS)
            try:
                line = self._readline_locked(connection).strip()
            except Exception:
                self._serial = None
                raise
            if not line:
                time.sleep(0.01)
                continue
            lines.append(line)
            lowered = line.lower()
            if lowered == "ok" or lowered.startswith("error:"):
                break
        return "\n".join(lines)

    def _read_available_locked(self, wait_seconds: float) -> str:
        connection = self._require_open()
        end_time = time.monotonic() + wait_seconds
        chunks = []
        while time.monotonic() < end_time:
            self._run_priority_interrupts(SerialPriority.RESUME)
            try:
                waiting = connection.in_waiting
                if waiting:
                    chunks.append(connection.read(waiting).decode("ascii", errors="replace"))
                else:
                    time.sleep(0.05)
            except Exception:
                self._serial = None
                raise
        return "".join(chunks).strip()

    def _query_status_report_locked(self, value: str, wait_seconds: float) -> str:
        self._write_raw_locked(value)
        return self._read_until_status_report_locked(wait_seconds)

    def _read_until_status_report_locked(self, wait_seconds: float) -> str:
        connection = self._require_open()
        end_time = time.monotonic() + wait_seconds
        lines: list[str] = []
        deferred_command_lines: list[str] = []
        while time.monotonic() < end_time:
            try:
                line = self._readline_locked(connection).strip()
            except Exception:
                self._serial = None
                raise
            if not line:
                time.sleep(0.01)
                continue
            lines.append(line)
            lowered = line.lower()
            if lowered == "ok" or lowered.startswith("error:"):
                deferred_command_lines.append(line)
                continue
            if line.startswith("<") and ">" in line:
                self._push_front_lines(deferred_command_lines)
                return "\n".join(lines)
            if lowered.startswith("alarm:"):
                self._push_front_lines(deferred_command_lines)
                return "\n".join(lines)
        self._push_front_lines(deferred_command_lines)
        return "\n".join(lines)

    def _readline_locked(self, connection) -> str:
        if self._line_buffer:
            return self._line_buffer.pop(0)
        return connection.readline().decode("ascii", errors="replace")

    def _push_front_lines(self, lines: list[str]) -> None:
        if not lines:
            return
        self._line_buffer = lines + self._line_buffer

    def _log_event(self, message: str) -> None:
        if self._log is not None:
            self._log(message)

    def _run_priority_interrupts(self, max_priority: SerialPriority) -> None:
        while True:
            with self._queue.mutex:
                if not self._queue.queue or self._queue.queue[0][0] > int(max_priority):
                    return
                _priority, _index, operation, handle = heapq.heappop(self._queue.queue)
                self._queue.not_full.notify()
            try:
                handle.set_result(operation())
            except Exception as exc:  # noqa: BLE001 - return failures to caller
                handle.set_error(exc)
                self._log_event(f"Serial-Fehler: {exc}")
            finally:
                self._queue.task_done()
