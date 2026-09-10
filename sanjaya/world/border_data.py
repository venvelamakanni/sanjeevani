"""Friendly-territory polygon and the inside-India test.

This is the *data* half of the hard border rule. The rule itself (delete any
candidate outside the polygon shrunk by position uncertainty) lives in the
deterministic core in Phase 3; this module only answers "is p inside?" and
"how far is p from the boundary?".

Containment is tested on the lon/lat polygon directly (topologically exact).
Distance to the boundary is measured in a sector-local projection in metres.
The boundary includes the coastline, so "distance to boundary" means distance
to leaving Indian land, which is what a landing site cares about.

DATA CAVEAT: the prototype polygon is Natural Earth / OSM. It is NOT
authoritative. The hard rule must run on Survey of India / MoD geometry before
any real use. Provenance is carried on the layer so every report can say so.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import shapely
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry

from sanjaya.core.geodesy import LatLon
from sanjaya.world.projection import LocalProjection


class BorderLayer:
    def __init__(self, geometry: BaseGeometry, projection: LocalProjection, provenance: dict[str, Any] | None = None):
        if geometry.geom_type not in ("Polygon", "MultiPolygon"):
            raise ValueError(f"border geometry must be polygonal, got {geometry.geom_type}")
        if not geometry.is_valid:
            geometry = shapely.make_valid(geometry)
        self.geometry = geometry
        self.projection = projection
        self.provenance = dict(provenance or {})
        shapely.prepare(self.geometry)
        self._boundary_xy = projection.project(geometry).boundary
        shapely.prepare(self._boundary_xy)

    @classmethod
    def from_geojson(cls, path: Path | str, projection: LocalProjection) -> "BorderLayer":
        with open(path, encoding="utf-8") as f:
            gj = json.load(f)
        if gj.get("type") == "FeatureCollection":
            feats = gj["features"]
            if len(feats) != 1:
                raise ValueError(f"border file must hold exactly one feature, got {len(feats)}")
            feat = feats[0]
        elif gj.get("type") == "Feature":
            feat = gj
        else:
            raise ValueError("border file must be a GeoJSON Feature or FeatureCollection")
        return cls(shape(feat["geometry"]), projection, feat.get("properties") or {})

    def contains(self, p: LatLon) -> bool:
        return bool(shapely.contains_xy(self.geometry, p.lon, p.lat))

    def distance_to_boundary_m(self, p: LatLon) -> float:
        x, y = self.projection.to_xy(p)
        return float(self._boundary_xy.distance(Point(x, y)))

    def signed_distance_m(self, p: LatLon) -> float:
        """Positive inside friendly territory, negative outside; magnitude = metres to the boundary."""
        d = self.distance_to_boundary_m(p)
        return d if self.contains(p) else -d

    def inside_with_margin(self, p: LatLon, margin_m: float) -> bool:
        """Inside, and at least margin_m from the boundary. The building block of the hard rule."""
        if margin_m < 0:
            raise ValueError("margin must be >= 0")
        return self.contains(p) and self.distance_to_boundary_m(p) >= margin_m
