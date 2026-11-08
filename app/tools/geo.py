# distance
from math import asin, cos, radians, sin, sqrt

CITY_SPEED_KMPH = 25


def km_between(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    lat1, lng1, lat2, lng2 = map(radians, (lat1, lng1, lat2, lng2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 2 * 6371 * asin(sqrt(a))


def travel_minutes(km: float) -> int:
    return max(10, round(km / CITY_SPEED_KMPH * 60))
