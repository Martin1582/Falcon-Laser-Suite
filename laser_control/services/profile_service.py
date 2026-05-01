import json
from pathlib import Path

from laser_control.gcode import CUT_MODE, ENGRAVE_MODE
from laser_control.models import MaterialProfile
from laser_control.profiles import DEFAULT_CUT_PROFILES, DEFAULT_PROFILES
from laser_control.workflow import derive_cut_profile_from_engrave


class ProfileService:
    def __init__(self, base_profiles: list[MaterialProfile] | None = None) -> None:
        self.material_profiles = [
            MaterialProfile(item.name, item.power_percent, item.speed_mm_min, item.passes)
            for item in (base_profiles or DEFAULT_PROFILES)
        ]
        self.mode_profiles: dict[str, dict[str, MaterialProfile]] = {ENGRAVE_MODE: {}, CUT_MODE: {}}
        self._initialize_mode_profiles()

    def names(self) -> list[str]:
        return [profile.name for profile in self.material_profiles]

    def profile_for(self, profile_name: str, operation_mode: str) -> MaterialProfile:
        self.ensure_profile_modes(profile_name)
        profile = self.mode_profiles[operation_mode][profile_name]
        return MaterialProfile(profile.name, profile.power_percent, profile.speed_mm_min, profile.passes)

    def upsert_mode_profile(self, profile: MaterialProfile, operation_mode: str) -> None:
        self._upsert_base_profile(profile)
        self.ensure_profile_modes(profile.name)
        self.mode_profiles[operation_mode][profile.name] = MaterialProfile(
            profile.name,
            profile.power_percent,
            profile.speed_mm_min,
            profile.passes,
        )

    def export_profiles(self, path: str) -> None:
        data = {
            "version": 1,
            "profiles": {
                mode: [
                    {
                        "name": profile.name,
                        "power_percent": profile.power_percent,
                        "speed_mm_min": profile.speed_mm_min,
                        "passes": profile.passes,
                    }
                    for profile in profiles.values()
                ]
                for mode, profiles in self.mode_profiles.items()
            },
        }
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")

    def import_profiles(self, path: str) -> None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for mode, raw_profiles in data.get("profiles", {}).items():
            if mode not in self.mode_profiles:
                continue
            for raw_profile in raw_profiles:
                profile = MaterialProfile(
                    raw_profile["name"],
                    int(raw_profile["power_percent"]),
                    int(raw_profile["speed_mm_min"]),
                    int(raw_profile["passes"]),
                )
                self.upsert_mode_profile(profile, mode)

    def ensure_profile_modes(self, profile_name: str) -> None:
        if profile_name in self.mode_profiles[ENGRAVE_MODE] and profile_name in self.mode_profiles[CUT_MODE]:
            return
        base_profile = next((item for item in self.material_profiles if item.name == profile_name), None)
        if base_profile is None:
            base_profile = MaterialProfile(profile_name, 50, 1000, 1)
        self.mode_profiles[ENGRAVE_MODE][profile_name] = MaterialProfile(
            base_profile.name,
            base_profile.power_percent,
            base_profile.speed_mm_min,
            base_profile.passes,
        )
        cut_profile = DEFAULT_CUT_PROFILES.get(profile_name, derive_cut_profile_from_engrave(base_profile))
        self.mode_profiles[CUT_MODE][profile_name] = MaterialProfile(
            cut_profile.name,
            cut_profile.power_percent,
            cut_profile.speed_mm_min,
            cut_profile.passes,
        )

    def _initialize_mode_profiles(self) -> None:
        for profile in self.material_profiles:
            self.ensure_profile_modes(profile.name)

    def _upsert_base_profile(self, profile: MaterialProfile) -> None:
        for index, existing in enumerate(self.material_profiles):
            if existing.name == profile.name:
                self.material_profiles[index] = MaterialProfile(
                    profile.name,
                    profile.power_percent,
                    profile.speed_mm_min,
                    profile.passes,
                )
                break
        else:
            self.material_profiles.append(
                MaterialProfile(profile.name, profile.power_percent, profile.speed_mm_min, profile.passes)
            )
