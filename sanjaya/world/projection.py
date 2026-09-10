"""Sector-local planar projection for metre-accurate vector queries.

Border distance and road distance need metres, not degrees. An azimuthal
equidistant projection centred on the sector gives exact distances from the
centre and well under 0.1% scale error at the edges of a ~700 km box, far
below the margins the system reasons with.
"""
from __future__ import annotations

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry.base import BaseGeometry

from sanjaya.config import BoundingBox
from sanjaya.core.geodesy import LatLon


class LocalProjection:
    def __init__(self, lat0: float, lon0: float):
        self.lat0 = lat0
        self.lon0 = lon0
        crs = f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m +no_defs"
        self._fwd = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        self._inv = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

    @classmethod
    def for_bbox(cls, bbox: BoundingBox) -> "LocalProjection":
        return cls((bbox.lat_min + bbox.lat_max) / 2.0, (bbox.lon_min + bbox.lon_max) / 2.0)

    def to_xy(self, p: LatLon) -> tuple[float, float]:
        x, y = self._fwd.transform(p.lon, p.lat)
        return float(x), float(y)

    def to_latlon(self, x: float, y: float) -> LatLon:
        lon, lat = self._inv.transform(x, y)
        return LatLon(lat=float(lat), lon=float(lon))

    def project(self, geom: BaseGeometry) -> BaseGeometry:
        """Project a lon/lat shapely geometry into local metres."""
        def _f(coords: np.ndarray) -> np.ndarray:
            x, y = self._fwd.transform(coords[:, 0], coords[:, 1])
            return np.column_stack([x, y])
        return shapely.transform(geom, _f)
