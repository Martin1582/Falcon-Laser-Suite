import threading
import time

from laser_control.serial_executor import SerialExecutor, SerialPriority


class FakeSerial:
    is_open = True
    port = "COM1"

    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self._responses = [b"ok\n"]
        self._read_chunks: list[bytes] = []
        self.closed = False

    def reset_input_buffer(self) -> None:
        pass

    def write(self, value: bytes) -> None:
        self.writes.append(value)

    def flush(self) -> None:
        pass

    def readline(self) -> bytes:
        if self._responses:
            return self._responses.pop(0)
        return b""

    @property
    def in_waiting(self) -> int:
        if not self._read_chunks:
            return 0
        return len(self._read_chunks[0])

    def read(self, _size: int) -> bytes:
        if self._read_chunks:
            return self._read_chunks.pop(0)
        return b""

    def close(self) -> None:
        self.closed = True
        self.is_open = False


def test_serial_executor_runs_query_through_single_worker() -> None:
    fake = FakeSerial()
    executor = SerialExecutor()
    executor.open(lambda: fake)

    response = executor.query_line("G0 X1", wait_seconds=0.1)
    executor.shutdown()

    assert response == "ok"
    assert fake.writes == [b"G0 X1\n"]
    assert fake.closed


def test_serial_executor_prioritizes_realtime_command_during_read_wait() -> None:
    fake = FakeSerial()
    fake._responses = []
    executor = SerialExecutor()
    executor.open(lambda: fake)

    query_thread = threading.Thread(target=lambda: executor.query_line("G1 X10", wait_seconds=0.2))
    query_thread.start()
    time.sleep(0.05)

    executor.write_raw("!", priority=SerialPriority.PAUSE)
    query_thread.join(timeout=1.0)
    executor.shutdown()

    assert fake.writes[0] == b"G1 X10\n"
    assert b"!" in fake.writes


def test_serial_executor_close_interrupts_active_read_wait() -> None:
    fake = FakeSerial()
    fake._responses = []
    executor = SerialExecutor()
    executor.open(lambda: fake)

    query_thread = threading.Thread(target=lambda: executor.query_line("G1 X10", wait_seconds=0.3))
    query_thread.start()
    time.sleep(0.05)

    executor.close()
    query_thread.join(timeout=1.0)
    executor.shutdown()

    assert fake.closed


def test_serial_executor_clear_pending_aborts_queued_normal_command() -> None:
    fake = FakeSerial()
    fake._responses = []
    executor = SerialExecutor()
    executor.open(lambda: fake)
    errors: list[str] = []

    query_thread = threading.Thread(target=lambda: executor.query_line("G1 X10", wait_seconds=0.3))
    query_thread.start()
    time.sleep(0.05)

    def queued_write() -> None:
        try:
            executor.write_raw("G0 X0", priority=SerialPriority.MANUAL)
        except RuntimeError as exc:
            errors.append(str(exc))

    write_thread = threading.Thread(target=queued_write)
    write_thread.start()
    time.sleep(0.05)

    removed = executor.clear_pending(min_priority=SerialPriority.MANUAL)
    query_thread.join(timeout=1.0)
    write_thread.join(timeout=1.0)
    executor.shutdown()

    assert removed == 1
    assert errors


def test_status_query_reads_status_without_waiting_for_ok() -> None:
    fake = FakeSerial()
    fake._responses = [b"<Hold:0|MPos:1.000,2.000,0.000|FS:0,0>\n"]
    executor = SerialExecutor()
    executor.open(lambda: fake)

    response = executor.query_status_report("?", wait_seconds=0.1)
    executor.shutdown()

    assert response.startswith("<Hold")
    assert fake.writes == [b"?"]


def test_status_query_preserves_command_ok_for_active_reader() -> None:
    fake = FakeSerial()
    fake._responses = [b"ok\n", b"<Hold:0|MPos:0.000,0.000,0.000|FS:0,0>\n"]
    executor = SerialExecutor()
    executor.open(lambda: fake)

    status = executor.query_status_report("?", wait_seconds=0.1)
    response = executor.query_line("G90", wait_seconds=0.1)
    executor.shutdown()

    assert status.startswith("ok\n<Hold")
    assert response == "ok"
