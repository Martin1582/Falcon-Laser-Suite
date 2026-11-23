from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from laser_control.json_store import read_json_object, write_json_object

SUPPORTED_CONTROLLER_TYPES = ("Simulator", "GRBL ueber USB")
MIN_BAUDRATE = 1200
MAX_BAUDRATE = 1000000
MAX_REASONABLE_SPEED = 200000
MAX_REASONABLE_POWER = 100


@dataclass(frozen=True)
class MachineProfile:
    profile_id: str = "creality-falcon-10w"
    name: str = "Creality Falcon 10W"
    machine_name: str = "Creality Falcon 10W"
    controller_type: str = "GRBL ueber USB"
    work_area_width: float = 400.0
    work_area_height: float = 415.0
    default_port: str = ""
    baudrate: int = 115200
    homing_required: bool = True
    max_speed: int = 10000
    max_power: int = 100
    notes: str = ""
    allow_start_without_homing_warning: str = (
        "Diese Maschine erlaubt Start ohne Homing. Die aktuelle Position kann ungenau sein."
    )
    machine_has_limit_switches: bool = True
    startup_requires_homing: bool = True


DEFAULT_MACHINE_PROFILE = MachineProfile(machine_name="Creality Falcon 10W", homing_required=True)


def machine_profile_from_dict(data: dict) -> MachineProfile:
    machine_name = str(data.get("machine_name", data.get("name", DEFAULT_MACHINE_PROFILE.machine_name)))
    profile_id = str(data.get("profile_id", _profile_id_from_name(machine_name)))
    controller_type = str(data.get("controller_type", DEFAULT_MACHINE_PROFILE.controller_type))
    if controller_type not in SUPPORTED_CONTROLLER_TYPES:
        controller_type = DEFAULT_MACHINE_PROFILE.controller_type
    return MachineProfile(
        profile_id=profile_id,
        name=str(data.get("name", machine_name)),
        machine_name=machine_name,
        controller_type=controller_type,
        work_area_width=_clamp_float(data.get("work_area_width", DEFAULT_MACHINE_PROFILE.work_area_width), 1.0, 5000.0),
        work_area_height=_clamp_float(data.get("work_area_height", DEFAULT_MACHINE_PROFILE.work_area_height), 1.0, 5000.0),
        default_port=str(data.get("default_port", "")),
        baudrate=_clamp_int(data.get("baudrate", DEFAULT_MACHINE_PROFILE.baudrate), MIN_BAUDRATE, MAX_BAUDRATE),
        homing_required=_bool_value(data.get("homing_required", True), True),
        max_speed=_clamp_int(data.get("max_speed", DEFAULT_MACHINE_PROFILE.max_speed), 1, MAX_REASONABLE_SPEED),
        max_power=_clamp_int(data.get("max_power", DEFAULT_MACHINE_PROFILE.max_power), 1, MAX_REASONABLE_POWER),
        notes=str(data.get("notes", "")),
        allow_start_without_homing_warning=str(
            data.get(
                "allow_start_without_homing_warning",
                DEFAULT_MACHINE_PROFILE.allow_start_without_homing_warning,
            )
        ),
        machine_has_limit_switches=_bool_value(data.get("machine_has_limit_switches", True), True),
        startup_requires_homing=_bool_value(data.get("startup_requires_homing", True), True),
    )


def machine_profile_to_dict(profile: MachineProfile) -> dict:
    return {
        "profile_id": profile.profile_id,
        "name": profile.name,
        "machine_name": profile.machine_name,
        "controller_type": profile.controller_type,
        "work_area_width": profile.work_area_width,
        "work_area_height": profile.work_area_height,
        "default_port": profile.default_port,
        "baudrate": profile.baudrate,
        "homing_required": profile.homing_required,
        "max_speed": profile.max_speed,
        "max_power": profile.max_power,
        "notes": profile.notes,
        "allow_start_without_homing_warning": profile.allow_start_without_homing_warning,
        "machine_has_limit_switches": profile.machine_has_limit_switches,
        "startup_requires_homing": profile.startup_requires_homing,
    }


def make_profile_id(name: str) -> str:
    return _profile_id_from_name(name)


def make_unique_profile_id(name: str, existing_ids: set[str]) -> str:
    base_id = _profile_id_from_name(name)
    if base_id not in existing_ids:
        return base_id
    counter = 2
    while f"{base_id}-{counter}" in existing_ids:
        counter += 1
    return f"{base_id}-{counter}"


def validate_machine_profile(
    profile: MachineProfile,
    existing_ids: set[str] | None = None,
    original_profile_id: str | None = None,
) -> list[str]:
    errors: list[str] = []
    existing_ids = existing_ids or set()

    if not profile.profile_id.strip():
        errors.append("Profil-ID fehlt.")
    elif profile.profile_id in existing_ids and profile.profile_id != original_profile_id:
        errors.append("Profil-ID ist bereits vorhanden.")
    if not profile.name.strip():
        errors.append("Profilname darf nicht leer sein.")
    if not profile.machine_name.strip():
        errors.append("Maschinenname darf nicht leer sein.")
    if profile.controller_type not in SUPPORTED_CONTROLLER_TYPES:
        errors.append("Controller-Typ ist ungueltig.")
    if profile.work_area_width <= 0 or profile.work_area_height <= 0:
        errors.append("Arbeitsbereich muss groesser als 0 mm sein.")
    if profile.baudrate < MIN_BAUDRATE or profile.baudrate > MAX_BAUDRATE:
        errors.append("Baudrate liegt ausserhalb des plausiblen Bereichs.")
    if profile.max_speed <= 0 or profile.max_speed > MAX_REASONABLE_SPEED:
        errors.append("Maximale Geschwindigkeit liegt ausserhalb des plausiblen Bereichs.")
    if profile.max_power <= 0 or profile.max_power > MAX_REASONABLE_POWER:
        errors.append("Maximale Laserleistung muss zwischen 1 und 100 Prozent liegen.")
    if not isinstance(profile.homing_required, bool):
        errors.append("Homing-Pflicht muss eindeutig gesetzt sein.")
    return errors


class MachineProfileRepository:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.environ.get("LASER_CONTROL_MACHINE_PROFILES", "machine_profiles.json"))
        self.load_error = ""
        self._profiles: dict[str, MachineProfile] = {DEFAULT_MACHINE_PROFILE.profile_id: DEFAULT_MACHINE_PROFILE}
        self._active_profile_id = DEFAULT_MACHINE_PROFILE.profile_id
        self._load()

    def profiles(self) -> list[MachineProfile]:
        return sorted(self._profiles.values(), key=lambda profile: profile.name.lower())

    def active_profile(self) -> MachineProfile:
        return self._profiles.get(self._active_profile_id, DEFAULT_MACHINE_PROFILE)

    def active_profile_id(self) -> str:
        return self.active_profile().profile_id

    def profile(self, profile_id: str) -> MachineProfile | None:
        return self._profiles.get(profile_id)

    def profile_ids(self) -> set[str]:
        return set(self._profiles)

    def set_active_profile(self, profile_id: str) -> MachineProfile:
        if profile_id not in self._profiles:
            self._active_profile_id = DEFAULT_MACHINE_PROFILE.profile_id
            self.save()
            return DEFAULT_MACHINE_PROFILE
        self._active_profile_id = profile_id
        self.save()
        return self.active_profile()

    def upsert_profile(self, profile: MachineProfile) -> None:
        errors = validate_machine_profile(profile, self.profile_ids(), profile.profile_id)
        if errors:
            raise ValueError("; ".join(errors))
        self._profiles[profile.profile_id] = profile
        if not self._active_profile_id:
            self._active_profile_id = profile.profile_id
        self.save()

    def save(self) -> None:
        write_json_object(
            self.path,
            {
                "version": 1,
                "active_profile_id": self._active_profile_id,
                "profiles": [machine_profile_to_dict(profile) for profile in self.profiles()],
            },
        )

    def _load(self) -> None:
        try:
            data = read_json_object(
                self.path,
                {
                    "version": 1,
                    "active_profile_id": DEFAULT_MACHINE_PROFILE.profile_id,
                    "profiles": [machine_profile_to_dict(DEFAULT_MACHINE_PROFILE)],
                },
            )
        except ValueError as exc:
            self.load_error = str(exc)
            return

        raw_profiles = data.get("profiles", [])
        profiles: dict[str, MachineProfile] = {}
        if isinstance(raw_profiles, list):
            for item in raw_profiles:
                if isinstance(item, dict):
                    profile = machine_profile_from_dict(item)
                    profiles[profile.profile_id] = profile
        profiles.setdefault(DEFAULT_MACHINE_PROFILE.profile_id, DEFAULT_MACHINE_PROFILE)
        self._profiles = profiles
        requested_active = str(data.get("active_profile_id", DEFAULT_MACHINE_PROFILE.profile_id))
        self._active_profile_id = requested_active if requested_active in self._profiles else DEFAULT_MACHINE_PROFILE.profile_id


def _profile_id_from_name(name: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in name.strip())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or DEFAULT_MACHINE_PROFILE.profile_id


def _clamp_float(value: object, minimum: float, maximum: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = minimum
    return min(maximum, max(minimum, numeric))


def _clamp_int(value: object, minimum: int, maximum: int) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = minimum
    return min(maximum, max(minimum, numeric))


def _bool_value(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "ja"}:
            return True
        if normalized in {"false", "0", "no", "nein"}:
            return False
    return default
