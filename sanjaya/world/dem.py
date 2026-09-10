"""Terrain elevation and slope from a geographic (lat/lon) DEM raster.

The DEM is a single GeoTIFF in EPSG:4326 covering the sector bbox. Queries do a
small windowed read around the point, so the file is never loaded whole and a
30 m product is as cheap to query as a 90 m one.

Elevation is bilinear between the four surrounding pixel centres. Slope is the
central-difference gradient at the nearest pixel, with pixel spacing converted
to metres at the point's latitude.

Copernicus DEM heights are orthometric (EGM2008), i.e. above mean sea level,
matching AircraftState.alt_m.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

from sanjaya.core.geodesy import LatLon, metres_per_degree


@dataclass(frozen=True, slots=True)
class DEMSample:
    elevation_m: float
    slope_deg: float | None   # None when a neighbour needed for the gradient is missing


class DEMLayer:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._ds = rasterio.open(self.path)
        if self._ds.crs is None or not self._ds.crs.is_geographic:
            raise ValueError(f"DEM must be in a geographic (lat/lon) CRS: {self.path}")
        self._nodata = self._ds.nodata if self._ds.nodata is not None else -32768.0
        self._xres = float(self._ds.transform.a)
        self._yres = float(-self._ds.transform.e)
        self._inv = ~self._ds.transform

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """(lon_min, lat_min, lon_max, lat_max)"""
        b = self._ds.bounds
        return (b.left, b.bottom, b.right, b.top)

    @property
    def resolution_deg(self) -> tuple[float, float]:
        return self._xres, self._yres

    def close(self) -> None:
        self._ds.close()

    def sample(self, p: LatLon) -> DEMSample | None:
        """Elevation and slope at p, or None if p is outside the raster or on nodata."""
        col_f, row_f = self._inv @ (p.lon, p.lat)
        w, h = self._ds.width, self._ds.height
        if not (0.0 <= col_f < w and 0.0 <= row_f < h):
            return None
        fx, fy = col_f - 0.5, row_f - 0.5           # pixel-centre coordinates
        ix, iy = math.floor(fx), math.floor(fy)
        u, v = fx - ix, fy - iy
        # Inside the raster but beyond the outermost pixel centres (a half-pixel band at
        # each edge): clamp to the edge pixel rather than read outside the grid.
        if ix < 0:
            ix, u = 0, 0.0
        elif ix > w - 2:
            ix, u = w - 2, 1.0
        if iy < 0:
            iy, v = 0, 0.0
        elif iy > h - 2:
            iy, v = h - 2, 1.0
        win = Window(ix - 1, iy - 1, 4, 4)
        a = self._ds.read(1, window=win, boundless=True, fill_value=self._nodata).astype(np.float64)
        valid = a != self._nodata

        q = a[1:3, 1:3]
        if not valid[1:3, 1:3].all():
            return None
        z =((1 - u) * (1 - v) * q[0, 0] + u * (1 - v) * q[0, 1]
             + (1 - u) * v * q[1, 0] + u * v * q[1, 1])

        jx, jy = 1 + int(round(u)), 1 + int(round(v))   # nearest pixel inside the 4x4 window
        slope: float | None = None
        if valid[jy, jx - 1] and valid[jy, jx + 1] and valid[jy - 1, jx] and valid[jy + 1, jx]:
            m_lat, m_lon = metres_per_degree(p.lat)
            dzdx = (a[jy, jx + 1] - a[jy, jx - 1]) / (2.0 * self._xres * m_lon)
            dzdy = (a[jy - 1, jx] - a[jy + 1, jx]) / (2.0 * self._yres * m_lat)
            slope = math.degrees(math.atan(math.hypot(dzdx, dzdy)))
        return DEMSample(elevation_m=float(z), slope_deg=slope)

    def elevation_m(self, p: LatLon) -> float | None:
        s = self.sample(p)
        return None if s is None else s.elevation_m

    def slope_deg(self, p: LatLon) -> float | None:
        s = self.sample(p)
        return None if s is None else s.slope_deg
