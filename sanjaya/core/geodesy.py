"""Geodesy on the WGS84 ellipsoid.

Deterministic core. All functions are pure. Angles in degrees, distances in metres.
Latitude is positive north, longitude positive east, matching every data source in
the Thar sector (DEM, borders, airfields).

The local frame used throughout SANJAYA is ENU (East, North, Up) about an origin.
It is exact enough for the distances a pod can fly (tens of km); we do not need
an ECEF round trip at this scale.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from pyproj import Geod

_WGS84 = Geod(ellps="WGS84")


@dataclass(frozen=True, slots=True)
class LatLon:
    lat: float
    lon: float

    def __post_init__(self) -> None:
        if not -90.0 <= self.lat <= 90.0:
            raise ValueError(f"latitude out of range: {self.lat}")
        if not -180.0 <= self.lon <= 180.0:
            raise ValueError(f"longitude out of range: {self.lon}")


@dataclass(frozen=True, slots=True)
class ENU:
    east: float
    north: float
    up: float = 0.0


def distance_m(a: LatLon, b: LatLon) -> float:
    """Geodesic (ellipsoidal) surface distance in metres."""
    _, _, d = _WGS84.inv(a.lon, a.lat, b.lon, b.lat)
    return float(d)


def bearing_deg(a: LatLon, b: LatLon) -> float:
    """Initial forward azimuth from a to b, in [0, 360)."""
    az, _, _ = _WGS84.inv(a.lon, a.lat, b.lon, b.lat)
    return float(az) % 360.0


def destination(origin: LatLon, bearing: float, dist_m: float) -> LatLon:
    """Point reached travelling dist_m along the geodesic at the given initial bearing."""
    lon, lat, _ = _WGS84.fwd(origin.lon, origin.lat, bearing, dist_m)
    return LatLon(lat=float(lat), lon=float(lon))


def to_enu(origin: LatLon, p: LatLon, up: float = 0.0) -> ENU:
    """Local ENU offset of p relative to origin, metres.

    Uses the geodesic distance and bearing, so it is exact along the great circle and
    accurate to well under a metre over the tens of km relevant to a pod.
    """
    d = distance_m(origin, p)
    az = math.radians(bearing_deg(origin, p))
    return ENU(east=d * math.sin(az), north=d * math.cos(az), up=up)


def from_enu(origin: LatLon, e: ENU) -> LatLon:
    """Inverse of to_enu (ignores up)."""
    d = math.hypot(e.east, e.north)
    if d == 0.0:
        return origin
    az = math.degrees(math.atan2(e.east, e.north)) % 360.0
    return destination(origin, az, d)


def wrap_deg(x: float) -> float:
    """Wrap an angle to [0, 360)."""
    return x % 360.0


def angle_diff_deg(a: float, b: float) -> float:
    """Signed smallest difference b - a, in (-180, 180]."""
    d = (b - a + 180.0) % 360.0 - 180.0
    return 180.0 if d == -180.0 else d
