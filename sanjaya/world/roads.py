"""Road segments as landing candidates, with nearest-k queries.

Loaded from a GeoJSON FeatureCollection of LineStrings (OSM via Overpass,
written by scripts/fetch_world_data.py). Distances are measured in the
sector-local projection, in metres.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import LineString, Point, shape
from shapely.ops import nearest_points
from shapely.strtree import STRtree

from sanjaya.core.geodesy import LatLon
from sanjaya.world.projection import LocalProjection


@dataclass(frozen=True, slots=True)
class RoadSegment:
    osm_id: int
    highway: str                  # motorway | trunk | primary | ...
    ref: str = ""                 # e.g. "NH 62"
    name: str = ""
    surface: str = ""             # OSM surface= tag when present
    lanes: int | None = None
    length_m: float = 0.0


@dataclass(frozen=True, slots=True)
class RoadFix:
    """A road as seen from a query point."""
    road: RoadSegment
    distance_m: float
    nearest_point: LatLon         # closest point on the road to the query


class RoadLayer:
    def __init__(self, segments: list[RoadSegment], lines_lonlat: list[LineString], projection: LocalProjection):
        if len(segments) != len(lines_lonlat):
            raise ValueError("segments and geometries differ in length")
        self.segments = list(segments)
        self.projection = projection
        self._lines_xy = [projection.project(ln) for ln in lines_lonlat]
        self._tree = STRtree(self._lines_xy) if self._lines_xy else None

    @classmethod
    def from_geojson(cls, path: Path | str, projection: LocalProjection) -> "RoadLayer":
        with open(path, encoding="utf-8") as f:
            gj = json.load(f)
        segs: list[RoadSegment] = []
        lines: list[LineString] = []
        for feat in gj.get("features", []):
            geom = shape(feat["geometry"])
            if geom.geom_type != "LineString" or len(geom.coords) < 2:
                continue
            pr = feat.get("properties") or {}
            lanes_raw = str(pr.get("lanes", "") or "").strip()
            lanes = int(lanes_raw) if lanes_raw.isdigit() else None
            xy = projection.project(geom)
            segs.append(RoadSegment(
                osm_id=int(pr.get("osm_id", 0)), highway=str(pr.get("highway", "")),
                ref=str(pr.get("ref", "") or ""), name=str(pr.get("name", "") or ""),
                surface=str(pr.get("surface", "") or ""), lanes=lanes, length_m=float(xy.length),
            ))
            lines.append(geom)
        return cls(segs, lines, projection)

    def __len__(self) -> int:
        return len(self.segments)

    def nearest(self, p: LatLon, k: int = 1, max_distance_m: float = 200_000.0) -> list[RoadFix]:
        """The k nearest road segments within max_distance_m, nearest first."""
        if k <= 0 or self._tree is None:
            return []
        x, y = self.projection.to_xy(p)
        pt = Point(x, y)
        r = 2_000.0
        idx = self._tree.query(pt.buffer(r))
        while len(idx) < k and r < max_distance_m:
            r = min(r * 2.0, max_distance_m)
            idx = self._tree.query(pt.buffer(r))
        fixes: list[RoadFix] = []
        for i in idx:
            ln = self._lines_xy[i]
            d = float(ln.distance(pt))
            if d > max_distance_m:
                continue
            np_xy = nearest_points(ln, pt)[0]
            fixes.append(RoadFix(self.segments[i], d, self.projection.to_latlon(np_xy.x, np_xy.y)))
        fixes.sort(key=lambda f: (f.distance_m, f.road.osm_id))
        return fixes[:k]
