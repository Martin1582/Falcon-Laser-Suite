from laser_control.models import MaterialProfile


def derive_cut_profile_from_engrave(profile: MaterialProfile) -> MaterialProfile:
    return MaterialProfile(
        name=profile.name,
        power_percent=min(100, max(1, profile.power_percent + 20)),
        speed_mm_min=max(100, int(profile.speed_mm_min * 0.6)),
        passes=max(1, profile.passes + 1),
    )


def build_cut_mode_warnings(power_percent: int, speed_mm_min: int, passes: int) -> list[str]:
    warnings: list[str] = []
    if power_percent >= 90:
        warnings.append("Sehr hohe Leistung (>= 90%).")
    if speed_mm_min <= 300:
        warnings.append("Sehr niedrige Geschwindigkeit (<= 300 mm/min).")
    if passes >= 5:
        warnings.append("Viele Durchgaenge (>= 5).")
    return warnings
