"""Offline tests of the digital-twin layers on synthetic data.

Every layer is exercised against a raster or polygon whose right answer is
known analytically, so these run without any downloaded data.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
import pytest
import rasterio
from hypothesis import given, settings
from hypothesis import strategies as st
from rasterio.transform import from_origin
from shapely.geometry import box

from sanjaya.config import BoundingBox, SectorConfig
from sanjaya.core.geodesy import LatLon, distance_m, metres_per_degree
from sanjaya.world import (AirfieldLayer, BorderLayer, DEMLayer, LandCoverLayer, LocalProjection, RoadLayer,
                           Surface, WorldModel)
from sanjaya.world import paths

# Synthetic world: 1 deg x 1 deg box, lat 25..26, lon 72..73
LAT0, LAT1, LON0, LON1 = 25.0, 26.0, 72.0, 73.0
RES = 0.01
A, B, C = 100.0, 1000.0, 500.0     # z = A + B*(lon-LON0) + C*(lat-LAT0)


def plane(lat: float, lon: float) -> float:
    return A + B * (lon - LON0) + C * (lat - LAT0)


def write_raster(path: Path, arr: np.ndarray, nodata: float | int | None) -> None:
    profile = {
        "driver": "GTiff", "dtype": arr.dtype.name, "count": 1, "nodata": nodata,
        "width": arr.shape[1], "height": arr.shape[0], "crs": "EPSG:4326",
        "transform": from_origin(LON0, LAT1, RES, RES),
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr, 1)


@pytest.fixture(scope="module")
def world_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("world")
    n = int(round((LAT1 - LAT0) / RES))
    # DEM: plane sampled at pixel centres, float32, one nodata hole at row 10, col 10
    rows = LAT1 - RES * (np.arange(n) + 0.5)
    cols = LON0 + RES * (np.arange(n) + 0.5)
    lat_g, lon_g = np.meshgrid(rows, cols, indexing="ij")
    dem = plane(lat_g, lon_g).astype(np.float32)
    dem[10, 10] = -32768
    write_raster(d / paths.DEM_FILE, dem, -32768)
    # Land cover: west half bare, east half built-up, a water pixel at row 5, col 5
    lc = np.full((n, n), Surface.BARE.value, dtype=np.uint8)
    lc[:, n // 2:] = Surface.BUILT_UP.value
    lc[5, 5] = Surface.WATER.value
    write_raster(d / paths.LANDCOVER_FILE, lc, 0)
    # Border: a square lat 25.2..25.8, lon 72.2..72.8
    feat = {"type": "Feature", "geometry": json.loads(json.dumps(box(72.2, 25.2, 72.8, 25.8).__geo_interface__)),
            "properties": {"source": "synthetic", "caveat": "test only"}}
    (d / paths.BORDER_FILE).write_text(json.dumps({"type": "FeatureCollection", "features": [feat]}))
    # Airfields
    with open(d / paths.AIRFIELDS_FILE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ident", "type", "name", "lat", "lon", "elevation_m", "iso_country",
                                          "municipality", "iata_code", "gps_code"])
        w.writeheader()
        w.writerow(dict(ident="AF1", type="large_airport", name="Centre", lat=25.5, lon=72.5, elevation_m=200,
                        iso_country="IN", municipality="", iata_code="", gps_code=""))
        w.writerow(dict(ident="AF2", type="small_airport", name="North", lat=25.9, lon=72.5, elevation_m="",
                        iso_country="IN", municipality="", iata_code="", gps_code=""))
        w.writerow(dict(ident="AF3", type="medium_airport", name="West", lat=25.5, lon=72.1, elevation_m=150,
                        iso_country="PK", municipality="", iata_code="", gps_code=""))
        w.writerow(dict(ident="AF4", type="small_airport", name="Far", lat=25.05, lon=72.95, elevation_m=100,
                        iso_country="IN", municipality="", iata_code="", gps_code=""))
    # Roads: a N-S road at lon 72.6 and an E-W road at lat 25.3
    roads = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[72.6, 25.0], [72.6, 26.0]]},
         "properties": {"osm_id": 1, "highway": "trunk", "ref": "NH 1", "lanes": "4"}},
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[72.0, 25.3], [73.0, 25.3]]},
         "properties": {"osm_id": 2, "highway": "primary", "ref": "SH 2", "lanes": ""}},
    ]}
    (d / paths.ROADS_FILE).write_text(json.dumps(roads))
    return d


@pytest.fixture(scope="module")
def sector() -> SectorConfig:
    return SectorConfig(name="synthetic", country="IN",
                        bbox=BoundingBox(lat_min=LAT0, lat_max=LAT1, lon_min=LON0, lon_max=LON1),
                        border_rule="hard", min_border_margin_m=1000, advisor_rate_hz=1)


@pytest.fixture(scope="module")
def proj(sector) -> LocalProjection:
    return LocalProjection.for_bbox(sector.bbox)


# ------------------------------------------------------------------ geodesy helper

def test_metres_per_degree_matches_geodesic():
    for lat in (0.0, 26.0, 45.0, 70.0):
        m_lat, m_lon = metres_per_degree(lat)
        assert math.isclose(m_lat, distance_m(LatLon(lat - 0.5, 10), LatLon(lat + 0.5, 10)), rel_tol=2e-5)
        if lat < 89:
            assert math.isclose(m_lon, distance_m(LatLon(lat, 9.5), LatLon(lat, 10.5)), rel_tol=2e-5)


# ------------------------------------------------------------------ DEM

def test_dem_bilinear_is_exact_on_a_plane(world_dir):
    dem = DEMLayer(world_dir / paths.DEM_FILE)
    for lat, lon in ((25.5, 72.5), (25.123, 72.987), (25.995, 72.005), (25.005, 72.995)):
        s = dem.sample(LatLon(lat, lon))
        assert s is not None
        assert math.isclose(s.elevation_m, plane(lat, lon), abs_tol=1e-3)


def test_dem_slope_matches_analytic_gradient(world_dir):
    dem = DEMLayer(world_dir / paths.DEM_FILE)
    p = LatLon(25.5, 72.5)
    s = dem.sample(p)
    assert s is not None and s.slope_deg is not None
    m_lat, m_lon = metres_per_degree(p.lat)
    expected = math.degrees(math.atan(math.hypot(B / m_lon, C / m_lat)))
    assert math.isclose(s.slope_deg, expected, rel_tol=2e-3)


def test_dem_outside_and_nodata_return_none(world_dir):
    dem = DEMLayer(world_dir / paths.DEM_FILE)
    assert dem.sample(LatLon(24.0, 72.5)) is None
    assert dem.sample(LatLon(25.5, 74.0)) is None
    # the hole at row 10, col 10 sits at lat 25.895, lon 72.105 (pixel centre)
    assert dem.elevation_m(LatLon(LAT1 - RES * 10.5, LON0 + RES * 10.5)) is None
    # slope next to the hole is None, elevation still fine
    s = dem.sample(LatLon(LAT1 - RES * 10.5, LON0 + RES * 11.6))
    assert s is not None and s.slope_deg is None


def test_dem_rejects_projected_crs(tmp_path):
    arr = np.zeros((4, 4), dtype=np.float32)
    with rasterio.open(tmp_path / "utm.tif", "w", driver="GTiff", dtype="float32", count=1, width=4, height=4,
                       crs="EPSG:32642", transform=from_origin(0, 0, 30, 30)) as dst:
        dst.write(arr, 1)
    with pytest.raises(ValueError):
        DEMLayer(tmp_path / "utm.tif")


# ------------------------------------------------------------------ land cover

def test_landcover_classes(world_dir):
    lc = LandCoverLayer(world_dir / paths.LANDCOVER_FILE)
    assert lc.sample(LatLon(25.5, 72.25)) is Surface.BARE
    assert lc.sample(LatLon(25.5, 72.75)) is Surface.BUILT_UP
    assert lc.sample(LatLon(LAT1 - RES * 5.5, LON0 + RES * 5.5)) is Surface.WATER
    assert lc.sample(LatLon(27.0, 72.5)) is Surface.UNKNOWN


def test_surface_from_unknown_code():
    assert Surface.from_code(42) is Surface.UNKNOWN
    assert Surface.from_code(60) is Surface.BARE


# ------------------------------------------------------------------ border

def test_border_contains_and_distance(world_dir, proj):
    b = BorderLayer.from_geojson(world_dir / paths.BORDER_FILE, proj)
    assert b.provenance["source"] == "synthetic"
    assert b.contains(LatLon(25.5, 72.5))
    assert not b.contains(LatLon(25.5, 72.9))
    # 0.1 deg of longitude inside the east edge at lat 25.5
    _, m_lon = metres_per_degree(25.5)
    d = b.signed_distance_m(LatLon(25.5, 72.7))
    assert math.isclose(d, 0.1 * m_lon, rel_tol=2e-3)
    assert math.isclose(b.signed_distance_m(LatLon(25.5, 72.9)), -0.1 * m_lon, rel_tol=2e-3)
    assert b.inside_with_margin(LatLon(25.5, 72.7), 5_000)
    assert not b.inside_with_margin(LatLon(25.5, 72.7), 20_000)
    assert not b.inside_with_margin(LatLon(25.5, 72.9), 0)
    with pytest.raises(ValueError):
        b.inside_with_margin(LatLon(25.5, 72.5), -1)


@settings(max_examples=200, deadline=None)
@given(lat=st.floats(25.0, 26.0), lon=st.floats(72.0, 73.0))
def test_border_sign_agrees_with_containment(world_dir, proj, lat, lon):
    b = BorderLayer.from_geojson(world_dir / paths.BORDER_FILE, proj)
    p = LatLon(lat, lon)
    d = b.signed_distance_m(p)
    if abs(d) > 1.0:
        assert (d > 0) == b.contains(p)


def test_border_rejects_non_polygon(proj):
    from shapely.geometry import LineString
    with pytest.raises(ValueError):
        BorderLayer(LineString([(0, 0), (1, 1)]), proj)


# ------------------------------------------------------------------ airfields

def test_airfields_nearest_ordering(world_dir):
    af = AirfieldLayer.from_csv(world_dir / paths.AIRFIELDS_FILE)
    assert len(af) == 4
    p = LatLon(25.5, 72.45)
    fixes = af.nearest(p, 3)
    assert [f.airfield.ident for f in fixes] == ["AF1", "AF3", "AF2"]
    assert all(a.distance_m <= b.distance_m for a, b in zip(fixes, fixes[1:]))
    assert math.isclose(fixes[0].distance_m, distance_m(p, af.by_ident("AF1").pos))
    assert 80 < fixes[0].bearing_deg < 100          # AF1 is due east
    assert af.by_ident("AF2").elevation_m is None
    assert af.nearest(p, 0) == []
    assert len(af.nearest(p, 10)) == 4


def test_airfields_duplicate_ident_rejected():
    from sanjaya.world.airfields import Airfield
    a = Airfield("X", "small_airport", "x", LatLon(0, 0), None, "IN")
    with pytest.raises(ValueError):
        AirfieldLayer([a, a])


# ------------------------------------------------------------------ roads

def test_roads_nearest(world_dir, proj):
    rl = RoadLayer.from_geojson(world_dir / paths.ROADS_FILE, proj)
    assert len(rl) == 2
    p = LatLon(25.5, 72.55)
    fixes = rl.nearest(p, 2)
    assert [f.road.osm_id for f in fixes] == [1, 2]
    _, m_lon = metres_per_degree(25.5)
    assert math.isclose(fixes[0].distance_m, 0.05 * m_lon, rel_tol=2e-3)
    assert math.isclose(fixes[0].nearest_point.lon, 72.6, abs_tol=1e-4)
    assert math.isclose(fixes[0].nearest_point.lat, 25.5, abs_tol=1e-3)
    assert fixes[0].road.lanes == 4 and fixes[1].road.lanes is None
    assert fixes[0].road.length_m > 100_000
    assert rl.nearest(p, 2, max_distance_m=1_000) == []


# ------------------------------------------------------------------ world model

def test_world_model_query(world_dir, sector):
    w = WorldModel.load(sector, data_dir=world_dir)
    p = LatLon(25.5, 72.7)
    info = w.query(p)
    assert math.isclose(info.elevation_m, plane(25.5, 72.7), abs_tol=1e-3)
    assert info.slope_deg is not None and info.slope_deg > 0
    assert info.surface is Surface.BUILT_UP
    assert info.inside_india and info.border_distance_m > 0
    assert [f.airfield.ident for f in info.nearest_airfields] == ["AF1", "AF2", "AF4"]
    assert info.nearest_road is not None and info.nearest_road.road.osm_id == 1
    assert w.in_sector(p) and not w.in_sector(LatLon(20, 72))
    outside = w.query(LatLon(25.5, 72.9), k_airfields=1)
    assert not outside.inside_india and outside.border_distance_m < 0
    assert len(outside.nearest_airfields) == 1
    w.close()


def test_world_model_load_reports_missing_files(sector, tmp_path):
    with pytest.raises(FileNotFoundError, match="fetch_world_data"):
        WorldModel.load(sector, data_dir=tmp_path)


def test_world_model_roads_optional(world_dir, sector, tmp_path):
    for n in (paths.DEM_FILE, paths.LANDCOVER_FILE, paths.BORDER_FILE, paths.AIRFIELDS_FILE):
        (tmp_path / n).write_bytes((world_dir / n).read_bytes())
    w = WorldModel.load(sector, data_dir=tmp_path)
    assert w.roads is None and w.query(LatLon(25.5, 72.5)).nearest_road is None
    with pytest.raises(FileNotFoundError):
        WorldModel.load(sector, data_dir=tmp_path, require_roads=True)
    w.close()
