from __future__ import annotations

from collections.abc import Callable

from laser_control.machine_state import MachinePhase, MachineState


DEFAULT_POINTER_POWER_PERCENT = 1
MAX_POINTER_POWER_PERCENT = 5


class MaterialAlignmentController:
    def __init__(
        self,
        controller_getter: Callable[[], object],
        state_getter: Callable[[], MachineState],
        log: Callable[[str], None],
        default_power_percent: int = DEFAULT_POINTER_POWER_PERCENT,
    ) -> None:
        self._controller_getter = controller_getter
        self._state_getter = state_getter
        self._log = log
        self._pointer_power_percent = self._clamp_power(default_power_percent)

    @property
    def pointer_power_percent(self) -> int:
        return self._pointer_power_percent

    def is_alignment_mode_active(self) -> bool:
        state = getattr(self._controller_getter(), "state", None)
        return bool(getattr(state, "alignment_mode_active", False))

    def set_pointer_power(self, percent: int) -> int:
        clamped = self._clamp_power(percent)
        if clamped != percent:
            self._log(f"Ausrichtmodus: Pointer-Leistung auf {clamped}% begrenzt.")
        self._pointer_power_percent = clamped
        if self.is_alignment_mode_active():
            self._log(f"Ausrichtmodus: Pointer-Leistung wird auf {clamped}% gesetzt.")
            self._controller_getter().enable_alignment_pointer(clamped)
        return clamped

    def enable_alignment_mode(self) -> None:
        self._log("Ausrichtmodus angefordert.")
        state = self._state_getter()
        controller_state = getattr(self._controller_getter(), "state", None)
        if state.phase != MachinePhase.IDLE or not state.connected:
            self._log(f"Ausrichtmodus blockiert: Maschinenzustand {state.phase.value}.")
            raise RuntimeError("Ausrichtmodus ist nur bei verbundener, idle Maschine erlaubt.")
        if getattr(controller_state, "paused", False) or getattr(controller_state, "alarm", False):
            self._log("Ausrichtmodus blockiert: Controller ist pausiert oder meldet Alarm.")
            raise RuntimeError("Ausrichtmodus ist bei Pause/Alarm nicht erlaubt.")
        power = self._pointer_power_percent
        self._controller_getter().enable_alignment_pointer(power)
        self._log(f"Ausrichtmodus aktiviert. Laserpunkt aktiv mit {power}% Leistung.")

    def disable_alignment_mode(self, reason: str = "") -> None:
        active = self.is_alignment_mode_active()
        if reason:
            self._log(f"Ausrichtmodus deaktivieren: {reason}.")
        if active:
            self._log("Ausrichtmodus deaktiviert.")
        self.ensure_laser_off(reason or "Ausrichtmodus deaktiviert")

    def ensure_laser_off(self, reason: str = "") -> None:
        controller = self._controller_getter()
        shutdown = getattr(controller, "disable_alignment_pointer", None)
        if not callable(shutdown):
            return
        try:
            shutdown()
            self._log("Laserpunkt ausgeschaltet." + (f" Grund: {reason}." if reason else ""))
        except Exception as exc:  # noqa: BLE001 - shutdown path must report but not mask callers
            self._log(f"Fehler beim Ausschalten des Laserpunktes: {exc}")
            raise

    def _clamp_power(self, percent: int) -> int:
        return max(DEFAULT_POINTER_POWER_PERCENT, min(MAX_POINTER_POWER_PERCENT, int(percent)))
