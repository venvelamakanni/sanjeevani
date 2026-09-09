"""Geodesy is tested against independently known values, not against pyproj itself."""
import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from sanjaya.core.geodesy import ENU, LatLon, angle_diff_deg, bearing_deg, destination, distance_m, from_enu, to_enu

# Textbook WGS84 values
METRES_PER_DEG_LAT_AT_EQUATOR = 110_574.0
METRES_PER_DEG_LON_AT_EQUATOR = 111_320.0
MERIDIONAL_QUARTER_M = 10_001_965.7   # equator to pole along a meridian


def test_one_degree_latitude_at_equator():
    d = distance_m(LatLon(0, 0), LatLon(1, 0))
    assert d == pytest.approx(METRES_PER_DEG_LAT_AT_EQUATOR, rel=1e-4)


def test_one_degree_longitude_at_equator():
    d = distance_m(LatLon(0, 0), LatLon(0, 1))
    assert d == pytest.approx(METRES_PER_DEG_LON_AT_EQUATOR, rel=1e-4)


def test_equator_to_pole():
    d = distance_m(LatLon(0, 0), LatLon(90, 0))
    assert d == pytest.approx(MERIDIONAL_QUARTER_M, rel=1e-6)


def test_bearing_cardinals():
    o = LatLon(26.0, 72.0)
    assert bearing_deg(o, LatLon(27.0, 72.0)) == pytest.approx(0.0, abs=1e-6)
    assert bearing_deg(o, LatLon(25.0, 72.0)) == pytest.approx(180.0, abs=1e-6)
    assert bearing_deg(o, LatLon(26.0, 73.0)) == pytest.approx(90.0, abs=0.3)   # meridian convergence
    assert bearing_deg(o, LatLon(26.0, 71.0)) == pytest.approx(270.0, abs=0.3)


def test_jodhpur_jaisalmer_leg_is_wnw_and_about_224km():
    # Independent check: published road/great-circle distance is ~220-225 km
    jd, js = LatLon(26.2389, 73.0243), LatLon(26.9157, 70.9083)
    assert 220_000 < distance_m(jd, js) < 226_000
    assert 285 < bearing_deg(jd, js) < 295


def test_latlon_rejects_out_of_range():
    with pytest.raises(ValueError):
        LatLon(91, 0)
    with pytest.raises(ValueError):
        LatLon(0, 181)


def test_angle_diff():
    assert angle_diff_deg(350, 10) == 20
    assert angle_diff_deg(10, 350) == -20
    assert angle_diff_deg(0, 180) == 180


# Property-based tests: the deterministic core must obey these for ANY input.
lat = st.floats(min_value=-89.0, max_value=89.0)
lon = st.floats(min_value=-179.0, max_value=179.0)
points = st.builds(LatLon, lat=lat, lon=lon)
thar_points = st.builds(LatLon, lat=st.floats(24.0, 30.5), lon=st.floats(68.5, 75.5))


@given(a=points, b=points)
def test_distance_symmetric_and_nonnegative(a, b):
    assert distance_m(a, b) >= 0
    assert distance_m(a, b) == pytest.approx(distance_m(b, a), rel=1e-9, abs=1e-6)


@given(a=points)
def test_distance_identity(a):
    assert distance_m(a, a) == pytest.approx(0.0, abs=1e-6)


@given(o=thar_points, bearing=st.floats(0, 360, exclude_max=True), d=st.floats(0, 200_000))
@settings(max_examples=200)
def test_destination_then_distance_roundtrip(o, bearing, d):
    p = destination(o, bearing, d)
    assert distance_m(o, p) == pytest.approx(d, rel=1e-6, abs=1e-3)


@given(o=thar_points, p=thar_points)
@settings(max_examples=200)
def test_enu_roundtrip(o, p):
    q = from_enu(o, to_enu(o, p))
    assert distance_m(p, q) < 1e-3   # sub-millimetre


@given(o=thar_points, p=thar_points)
def test_enu_magnitude_matches_distance(o, p):
    e = to_enu(o, p)
    assert math.hypot(e.east, e.north) == pytest.approx(distance_m(o, p), rel=1e-9, abs=1e-6)
