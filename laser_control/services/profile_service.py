from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from laser_control.gcode import CUT_MODE, ENGRAVE_MODE
from laser_control.json_store import read_json_object, write_json_object
from laser_control.models import MaterialProfile
from laser_control.profiles import DEFAULT_CUT_PROFILES, DEFAULT_PROFILES
from laser_control.workflow import derive_cut_profile_from_engrave


LogFn = Callable[[str], None]


class ProfileService:
    def __init__(
        self,
        base_profiles: list[MaterialProfile] | None = None,
        storage_path: str | Path | None = None,
        log: LogFn | None = None,
        auto_load: bool = True,
    ) -> None:
        self.storage_path = Path(storage_path) if storage_path is not None else material_profile_store_path()
        self._log = log
        self.material_profiles = [_copy_profile(item) for item in (base_profiles or DEFAULT_PROFILES)]
        self.mode_profiles: dict[str, dict[str, MaterialProfile]] = {ENGRAVE_MODE: {}, CUT_MODE: {}}
        if auto_load:
            self._load_persisted_profiles()
        self._initialize_mode_profiles()

    def names(self) -> list[str]:
        return [profile.name for profile in self.material_profiles]

    def profile_for(self, profile_name: str, operation_mode: str) -> MaterialProfile:
        self.ensure_profile_modes(profile_name)
        profile = self.mode_profiles[operation_mode][profile_name]
        return _copy_profile(profile)

    def upsert_mode_profile(self, profile: MaterialProfile, operation_mode: str, persist: bool = True) -> None:
        self._upsert_base_profile(profile)
        self.ensure_profile_modes(profile.name)
        self.mode_profiles[operation_mode][profile.name] = _copy_profile(profile)
        if persist:
            self.save_profiles()

    def save_profiles(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        write_json_object(self.storage_path, self._profiles_to_data())
        self._emit(f"Materialprofile gespeichert: {self.storage_path}")

    def export_profiles(self, path: str) -> None:
        write_json_object(Path(path), self._profiles_to_data())

    def import_profiles(self, path: str) -> None:
        data = read_json_object(Path(path), {"profiles": {}})
        raw_modes = data.get("profiles", {})
        if not isinstance(raw_modes, dict):
            raise ValueError("Profil-Datei enthaelt keine gueltigen Profile.")
        for mode, raw_profiles in raw_modes.items():
            if mode not in self.mode_profiles:
                continue
            if not isinstance(raw_profiles, list):
                continue
            for raw_profile in raw_profiles:
                if not isinstance(raw_profile, dict):
                    continue
                profile = MaterialProfile(
                    str(raw_profile.get("name", "Unbenannt")).strip() or "Unbenannt",
                    max(0, min(100, _safe_int(raw_profile.get("power_percent"), 50))),
                    max(1, _safe_int(raw_profile.get("speed_mm_min"), 1000)),
                    max(1, _safe_int(raw_profile.get("passes"), 1)),
                    str(raw_profile.get("layer_type", "")),
                    str(raw_profile.get("notes", "")),
                    str(raw_profile.get("material_type", "")),
                    _optional_float(raw_profile.get("thickness_mm")),
                )
                self.upsert_mode_profile(profile, mode, persist=False)

    def ensure_profile_modes(self, profile_name: str) -> None:
        if profile_name in self.mode_profiles[ENGRAVE_MODE] and profile_name in self.mode_profiles[CUT_MODE]:
            return
        base_profile = next((item for item in self.material_profiles if item.name == profile_name), None)
        if base_profile is None:
            base_profile = MaterialProfile(profile_name, 50, 1000, 1)
        self.mode_profiles[ENGRAVE_MODE][profile_name] = _copy_profile(base_profile)
        cut_profile = DEFAULT_CUT_PROFILES.get(profile_name, derive_cut_profile_from_engrave(base_profile))
        self.mode_profiles[CUT_MODE][profile_name] = _copy_profile(cut_profile)

    def _initialize_mode_profiles(self) -> None:
        for profile in self.material_profiles:
            self.ensure_profile_modes(profile.name)

    def _upsert_base_profile(self, profile: MaterialProfile) -> None:
        clean = _copy_profile(profile)
        for index, existing in enumerate(self.material_profiles):
            if existing.name == clean.name:
                self.material_profiles[index] = clean
                break
        else:
            self.material_profiles.append(clean)

    def _load_persisted_profiles(self) -> None:
        if not self.storage_path.exists():
            self._emit(f"Materialprofile: keine User-Datei vorhanden, Defaults aktiv. Pfad: {self.storage_path}")
            return
        try:
            self.import_profiles(str(self.storage_path))
        except ValueError as exc:
            self._emit(f"Materialprofile konnten nicht geladen werden, Fallback auf Defaults: {exc}")
            return
        self._emit(f"Materialprofile geladen: {self.storage_path}")

    def _profiles_to_data(self) -> dict:
        return {
            "version": 1,
            "profiles": {
                mode: [_profile_to_dict(profile) for profile in profiles.values()]
                for mode, profiles in self.mode_profiles.items()
            },
        }

    def _emit(self, message: str) -> None:
        if self._log is not None:
            self._log(message)


def material_profile_store_path() -> Path:
    override = os.environ.get("LASER_CONTROL_PROFILE_DB")
    if override:
        return Path(override)
    material_db_override = os.environ.get("LASER_CONTROL_MATERIAL_DB")
    if material_db_override:
        return Path(material_db_override).with_name("material_profiles.json")
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Laser Control" / "material_profiles.json"
    return Path(__file__).resolve().parent.parent.parent / "material_profiles.json"


def _copy_profile(profile: MaterialProfile) -> MaterialProfile:
    return MaterialProfile(
        profile.name,
        profile.power_percent,
        profile.speed_mm_min,
        profile.passes,
        profile.layer_type,
        profile.notes,
        profile.material_type,
        profile.thickness_mm,
    )


def _profile_to_dict(profile: MaterialProfile) -> dict:
    return {
        "name": profile.name,
        "power_percent": profile.power_percent,
        "speed_mm_min": profile.speed_mm_min,
        "passes": profile.passes,
        "layer_type": profile.layer_type,
        "notes": profile.notes,
        "material_type": profile.material_type,
        "thickness_mm": profile.thickness_mm,
    }


def _safe_int(value: object, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _optional_float(value: object) -> float | None:
    if value in {None, ""}:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None
