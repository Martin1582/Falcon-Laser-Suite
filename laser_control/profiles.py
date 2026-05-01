from laser_control.models import MaterialProfile


# Starter presets based on Creality Falcon CR/Falcon 10W material tables.
# Always validate with a small test matrix on the actual material batch.
DEFAULT_PROFILES = [
    MaterialProfile("Lindenholz 2 mm", power_percent=40, speed_mm_min=3000, passes=1),
    MaterialProfile("Lindenholz 4 mm", power_percent=40, speed_mm_min=3000, passes=1),
    MaterialProfile("Bambus 5 mm", power_percent=40, speed_mm_min=3000, passes=1),
    MaterialProfile("Kraftpapier 0.2 mm", power_percent=25, speed_mm_min=3000, passes=1),
    MaterialProfile("Karton rot 0.2 mm", power_percent=25, speed_mm_min=3000, passes=1),
    MaterialProfile("Leder braun 0.65 mm", power_percent=20, speed_mm_min=3000, passes=1),
    MaterialProfile("Acryl schwarz 4.5 mm", power_percent=50, speed_mm_min=3000, passes=1),
    MaterialProfile("Eloxiertes Aluminium 3 mm", power_percent=100, speed_mm_min=200, passes=1),
    MaterialProfile("Edelstahl 2 mm", power_percent=100, speed_mm_min=500, passes=1),
    MaterialProfile("Keramikfliese schwarz lackiert 6 mm", power_percent=95, speed_mm_min=3800, passes=1),
]


DEFAULT_CUT_PROFILES = {
    "Lindenholz 2 mm": MaterialProfile("Lindenholz 2 mm", power_percent=100, speed_mm_min=350, passes=1),
    "Lindenholz 4 mm": MaterialProfile("Lindenholz 4 mm", power_percent=100, speed_mm_min=200, passes=1),
    "Bambus 5 mm": MaterialProfile("Bambus 5 mm", power_percent=100, speed_mm_min=230, passes=3),
    "Kraftpapier 0.2 mm": MaterialProfile("Kraftpapier 0.2 mm", power_percent=100, speed_mm_min=3500, passes=1),
    "Karton rot 0.2 mm": MaterialProfile("Karton rot 0.2 mm", power_percent=100, speed_mm_min=1500, passes=1),
    "Leder braun 0.65 mm": MaterialProfile("Leder braun 0.65 mm", power_percent=100, speed_mm_min=1500, passes=1),
    "Acryl schwarz 4.5 mm": MaterialProfile("Acryl schwarz 4.5 mm", power_percent=100, speed_mm_min=120, passes=2),
}
