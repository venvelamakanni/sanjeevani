"""Phase 1 definition of done, on the real Thar data: click any point and the
answer matches independent sources.

Skipped when the data has not been fetched (python scripts/fetch_world_data.py).
"""
from __future__ import annotations

import math

import pytest

from sanjaya.config import SectorConfig, load_default
from sanjaya.core.geodesy import LatLon
from sanjaya.world import Surface, WorldModel, paths

SECTOR = load_default(SectorConfig, "sector_thar.yaml")
DATA = paths.sector_dir(SECTOR.name)
HAVE_DATA = all((DATA / n).exists() for n in (paths.DEM_FILE, paths.LANDCOVER_FILE, paths.BORDER_FILE, paths.AIRFIELDS_FILE))

pytestmark = pytest.mark.skipif(not HAVE_DATA, reason="Thar world data not fetched")

JODHPUR_AIRPORT = LatLon(26.2515, 73.0489)      # VIJO, the sortie start point. Elevation 219 m per OurAirports.
GURU_SHIKHAR = LatLon(24.6497, 72.7794)         # highest point of the Aravallis, 1722 m
OPEN_DESERT = LatLon(26.90, 70.20)              # dunes west of Jaisalmer, 100% bare in WorldCover
JODHPUR_OLD_CITY = LatLon(26.2960, 73.0180)     # dense built-up
SINDH_INTERIOR = LatLon(25.50, 68.80)           # Pakistan, well inside the bbox
LONGEWALA = LatLon(26.98, 70.14)                # Indian border post; Natural Earth puts the IB ~44 km away (reality ~16 km)
MUNABAO = LatLon(25.76, 70.28)                  # rail border crossing, a few km inside the IB
SAMBHAR_LAKE = LatLon(26.95, 75.08)             # India's largest inland salt lake


@pytest.fixture(scope="module")
def world() -> WorldModel:
    w = WorldModel.load(SECTOR)
    yield w
    w.close()


def test_jodhpur_airport(world):
    info = world.query(JODHPUR_AIRPORT)
    assert info.elevation_m is not None and 200 <= info.elevation_m <= 245
    assert info.slope_deg is not None and info.slope_deg < 3
    assert info.inside_india and info.border_distance_m > 150_000
    assert info.nearest_airfields[0].airfield.ident == "VIJO"
    assert info.nearest_airfields[0].distance_m < 2_000
    assert [f.airfield.iso_country for f in info.nearest_airfields].count("IN") == 3


def test_aravalli_summit_is_high_and_steep(world):
    info = world.query(GURU_SHIKHAR)
    assert info.elevation_m is not None and info.elevation_m > 1500
    assert info.slope_deg is not None and info.slope_deg > 8


def test_desert_surface(world):
    info = world.query(OPEN_DESERT)
    assert info.surface is Surface.BARE
    assert info.slope_deg is not None and info.slope_deg < 5
    assert info.inside_india


def test_city_is_built_up(world):
    assert world.query(JODHPUR_OLD_CITY).surface is Surface.BUILT_UP


def test_salt_lake_is_water(world):
    assert world.query(SAMBHAR_LAKE).surface is Surface.WATER


def test_border_sides(world):
    pk = world.query(SINDH_INTERIOR)
    assert not pk.inside_india and pk.border_distance_m < -30_000
    lw = world.query(LONGEWALA)
    assert lw.inside_india and 0 < lw.border_distance_m < 60_000
    mb = world.query(MUNABAO)
    assert mb.inside_india and 0 < mb.border_distance_m < 15_000


def test_border_provenance_is_flagged_non_authoritative(world):
    prov = world.provenance["border"]
    assert prov["authoritative"] is False
    assert "authoritative" in prov["caveat"].lower()


def test_dem_agrees_with_ourairports_elevations(world):
    """Independent cross-check: DEM at each Indian airport vs the OurAirports elevation."""
    checked, agree = 0, 0
    for a in world.airfields.airfields:
        if a.iso_country != "IN" or a.elevation_m is None or a.type == "small_airport":
            continue
        z = world.dem.elevation_m(a.pos)
        if z is None:
            continue
        checked += 1
        if abs(z - a.elevation_m) <= 40:
            agree += 1
    assert checked >= 5
    assert agree / checked >= 0.8, f"{agree}/{checked} airports within 40 m"


def test_query_speed(world):
    """The advisor will query thousands of points per tick; a query must be well under a millisecond-ish."""
    import time
    t0 = time.perf_counter()
    n = 300
    for i in range(n):
        world.query(LatLon(25.0 + 5.0 * (i / n), 69.0 + 6.0 * ((i * 7) % n) / n))
    per = (time.perf_counter() - t0) / n
    assert per < 0.02, f"{per * 1000:.1f} ms per query"


def test_sector_coverage(world):
    lo, la = SECTOR.bbox, SECTOR.bbox
    assert world.dem.bounds[0] <= lo.lon_min and world.dem.bounds[2] >= lo.lon_max
    assert world.dem.bounds[1] <= la.lat_min and world.dem.bounds[3] >= la.lat_max
    assert math.isclose(world.landcover.bounds[0], lo.lon_min, abs_tol=1e-6)
