from laser_control.models import MaterialProfile


DEFAULT_PROFILES = [
    MaterialProfile("Sperrholz 3 mm", power_percent=65, speed_mm_min=900, passes=1),
    MaterialProfile("Acryl dunkel", power_percent=45, speed_mm_min=1200, passes=1),
    MaterialProfile("Karton", power_percent=25, speed_mm_min=1800, passes=1),
    MaterialProfile("Edelstahl Markierung", power_percent=100, speed_mm_min=400, passes=2),
]
