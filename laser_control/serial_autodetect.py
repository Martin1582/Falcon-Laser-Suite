import time
from dataclasses import dataclass

from laser_control.serial_executor import SerialExecutor, SerialPriority

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover - depends on local installation
    serial = None
    list_ports = None


LASER_PORT_KEYWORDS = (
    "usb serial",
    "ch340",
    "ch341",
    "cp210",
    "silicon labs",
    "usb-sERIAL",
    "uart",
    "wch",
)


@dataclass
class PortCandidate:
    device: str
    label: str
    score: int
    reason: str
    grbl_response: str = ""


def find_laser_port(baudrate: int = 115200, probe: bool = True) -> PortCandidate | None:
    candidates = list_port_candidates()
    if probe:
        for candidate in candidates:
            response = probe_grbl_port(candidate.device, baudrate=baudrate)
            if looks_like_grbl(response):
                candidate.score += 100
                candidate.reason = f"GRBL-Antwort erkannt: {candidate.reason}"
                candidate.grbl_response = response
                return candidate
    return candidates[0] if candidates else None


def list_port_candidates() -> list[PortCandidate]:
    if list_ports is None:
        return []
    candidates = []
    for port in list_ports.comports():
        label = port.device
        description = getattr(port, "description", "") or ""
        hwid = getattr(port, "hwid", "") or ""
        if description:
            label = f"{port.device} - {description}"
        text = f"{description} {hwid}".lower()
        score = 10
        reasons = []
        for keyword in LASER_PORT_KEYWORDS:
            if keyword.lower() in text:
                score += 20
                reasons.append(keyword)
        candidates.append(
            PortCandidate(
                device=port.device,
                label=label,
                score=score,
                reason=", ".join(reasons) if reasons else "COM-Port ohne Laser-Hinweis",
            )
        )
    return sorted(candidates, key=lambda item: item.score, reverse=True)


def probe_grbl_port(device: str, baudrate: int = 115200, timeout: float = 0.35) -> str:
    if serial is None:
        return ""
    executor = SerialExecutor()
    try:
        executor.open_serial(serial, port=device, baudrate=baudrate, timeout=timeout, write_timeout=timeout)
        time.sleep(1.2)
        executor.reset_input_buffer()
        chunks = [
            executor.read_available_after_write("\r\n\r\n", wait_seconds=0.2, priority=SerialPriority.CONNECTION),
            executor.query_line("$I", wait_seconds=1.0, priority=SerialPriority.CONNECTION),
            executor.read_available_after_write("?", wait_seconds=0.2, priority=SerialPriority.STATUS),
        ]
        return "\n".join(chunk for chunk in chunks if chunk).strip()
    except Exception:
        return ""
    finally:
        executor.shutdown()


def looks_like_grbl(response: str) -> bool:
    lowered = response.lower()
    return (
        "grbl" in lowered
        or "[ver:" in lowered
        or "[opt:" in lowered
        or ("<" in response and ">" in response and ("mpos:" in lowered or "wpos:" in lowered))
        or any(line.strip().lower() == "ok" for line in response.splitlines())
    )
