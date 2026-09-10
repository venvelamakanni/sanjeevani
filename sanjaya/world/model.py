"""The digital twin as one queryable object.

WorldModel.query(p) answers, for any point in the sector: elevation, slope,
surface type, inside-India (with distance to the boundary), the nearest
airfields, and the nearest major road. This is the Phase 1 definition of done
and the world the later phases reason over.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sanjaya.config import SectorConfig
from sanjaya.core.geodesy import LatLon
from sanjaya.world import paths
from sanjaya.world.airfields import AirfieldFix, AirfieldLayer
from sanjaya.world.border_data import BorderLayer
from sanjaya.world.dem import DEMLayer
from sanjaya.world.landcover import LandCoverLayer, Surface
from sanjaya.world.projection import LocalProjection
from sanjaya.world.roads import RoadFix, RoadLayer


@dataclass(frozen=True, slots=True)
class PointInfo:
    pos: LatLon
    elevation_m: float | None          # None outside DEM coverage
    slope_deg: float | None
    surface: Surface
    inside_india: bool
    border_distance_m: float           # signed: + inside, - outside
    nearest_airfields: tuple[AirfieldFix, ...]
    nearest_road: RoadFix | None       # None when no road layer or none within range


class WorldModel:
    def __init__(self, sector: SectorConfig, dem: DEMLayer, landcover: LandCoverLayer,
                 border: BorderLayer, airfields: AirfieldLayer, roads: RoadLayer | None = None):
        self.sector = sector
        self.dem = dem
        self.landcover = landcover
        self.border = border
        self.airfields = airfields
        self.roads = roads

    @classmethod
    def load(cls, sector: SectorConfig, data_dir: Path | str | None = None, require_roads: bool = False) -> "WorldModel":
        d = Path(data_dir) if data_dir is not None else paths.sector_dir(sector.name)
        needed = [paths.DEM_FILE, paths.LANDCOVER_FILE, paths.BORDER_FILE, paths.AIRFIELDS_FILE]
        if require_roads:
            needed.append(paths.ROADS_FILE)
        missing = [n for n in needed if not (d / n).exists()]
        if missing:
            raise FileNotFoundError(
                f"world data for sector '{sector.name}' missing {missing} in {d}. "
                f"Run: python scripts/fetch_world_data.py"
            )
        proj = LocalProjection.for_bbox(sector.bbox)
        roads = RoadLayer.from_geojson(d / paths.ROADS_FILE, proj) if (d / paths.ROADS_FILE).exists() else None
        return cls(
            sector=sector,
            dem=DEMLayer(d / paths.DEM_FILE),
            landcover=LandCoverLayer(d / paths.LANDCOVER_FILE),
            border=BorderLayer.from_geojson(d / paths.BORDER_FILE, proj),
            airfields=AirfieldLayer.from_csv(d / paths.AIRFIELDS_FILE),
            roads=roads,
        )

    @property
    def provenance(self) -> dict[str, Any]:
        return {"border": self.border.provenance}

    def in_sector(self, p: LatLon) -> bool:
        b = self.sector.bbox
        return b.lat_min <= p.lat <= b.lat_max and b.lon_min <= p.lon <= b.lon_max

    def query(self, p: LatLon, k_airfields: int = 3) -> PointInfo:
        dem = self.dem.sample(p)
        road = self.roads.nearest(p, 1) if self.roads is not None else []
        return PointInfo(
            pos=p,
            elevation_m=None if dem is None else dem.elevation_m,
            slope_deg=None if dem is None else dem.slope_deg,
            surface=self.landcover.sample(p),
            inside_india=self.border.contains(p),
            border_distance_m=self.border.signed_distance_m(p),
            nearest_airfields=tuple(self.airfields.nearest(p, k_airfields)),
            nearest_road=road[0] if road else None,
        )

    def close(self) -> None:
        self.dem.close()
        self.landcover.close()
