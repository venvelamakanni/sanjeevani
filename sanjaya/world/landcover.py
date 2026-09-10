"""Surface type at a point from an ESA WorldCover raster (EPSG:4326, uint8).

Class codes are WorldCover's own so the raster can be swapped for a finer or
newer product without touching this module.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path

import rasterio
from rasterio.windows import Window

from sanjaya.core.geodesy import LatLon


class Surface(Enum):
    UNKNOWN = 0
    TREE = 10
    SHRUB = 20
    GRASS = 30
    CROPLAND = 40
    BUILT_UP = 50
    BARE = 60          # bare / sparse vegetation: sand, rock. Most of the Thar.
    SNOW = 70
    WATER = 80
    WETLAND = 90
    MANGROVE = 95
    MOSS = 100

    @classmethod
    def from_code(cls, code: int) -> "Surface":
        try:
            return cls(int(code))
        except ValueError:
            return cls.UNKNOWN


class LandCoverLayer:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._ds = rasterio.open(self.path)
        if self._ds.crs is None or not self._ds.crs.is_geographic:
            raise ValueError(f"land cover must be in a geographic (lat/lon) CRS: {self.path}")
        self._inv = ~self._ds.transform

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        b = self._ds.bounds
        return (b.left, b.bottom, b.right, b.top)

    def close(self) -> None:
        self._ds.close()

    def sample(self, p: LatLon) -> Surface:
        """Nearest-pixel surface class; UNKNOWN outside the raster or on nodata."""
        col_f, row_f = self._inv @ (p.lon, p.lat)
        col, row = int(col_f), int(row_f)
        if col_f < 0 or row_f < 0 or col >= self._ds.width or row >= self._ds.height:
            return Surface.UNKNOWN
        v = self._ds.read(1, window=Window(col, row, 1, 1))[0, 0]
        return Surface.from_code(int(v))
