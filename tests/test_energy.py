"""Reach model checked against hand calculation and closed-form results.

Expected values are computed here with plain arithmetic, independent of the
atmosphere and energy modules, so the tests confirm the model rather than
restate it.
"""
import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from sanjaya.config import PodConfig, load_default
from sanjaya.core.atmosphere import Atmosphere
from sanjaya.core.energy import CALM, DescentProfile, PodPerformance, Wind, footprint, ground_speed_mps, reach
from sanjaya.pod.model import performance_from_config

G = 9.80665
T0, L, EXP = 288.15, 0.0065, 5.255877     # ISA troposphere, g/(R L)
R0 = 6_356_766.0                           # standard-atmosphere earth radius


@pytest.fixture(scope="module")
def pod() -> PodPerformance:
    return performance_from_config(load_default(PodConfig, "pod_v0.yaml"))


def sigma_isa(h: float) -> float:
    hgp = R0 * h / (R0 + h)                # geometric -> geopotential
    return (1 - L * hgp / T0) ** (EXP - 1)


# ------------------------------------------------------------------ the pod itself

def test_pod_v0_numbers(pod):
    assert pod.glide_ld == 8 and pod.cruise_eas_mps == 61 and pod.endurance_s == 900
    assert pod.cruise_drag_n == pytest.approx(300 * G / 8)          # 367.75 N
    assert pod.cruises_level                                       # 370 N >= 367.75 N
    assert pod.powered_angle_rad == 0.0


# ------------------------------------------------------------------ hand checks

def test_hand_glide_3000m_times_ld(pod):
    r = reach(pod, 3200, 200, track_deg=45, endurance_s=0)
    assert r.distance_m == pytest.approx(3000 * 8, rel=1e-9)
    assert r.powered_m == 0 and r.holds_track


def test_hand_powered_at_sea_level(pod):
    r = reach(pod, 0, 0, track_deg=0)
    assert r.distance_m == pytest.approx(61 * 900, rel=1e-9)
    assert r.time_s == pytest.approx(900)


def test_hand_powered_hot_day(pod):
    # Same pressure, air 20 C hotter: sigma = 288.15/308.15, TAS = 61*sqrt(308.15/288.15)
    r = reach(pod, 0, 0, track_deg=0, atm=Atmosphere(isa_offset_c=20))
    assert r.distance_m == pytest.approx(61 * math.sqrt(308.15 / 288.15) * 900, rel=1e-9)


def test_hand_full_mission_from_3200m(pod):
    tas = 61 / math.sqrt(sigma_isa(3200))                          # ~71.5 m/s at 3200 m
    expected = tas * 900 + 3000 * 8                                 # ~88.4 km
    r = reach(pod, 3200, 200, track_deg=270)
    assert r.distance_m == pytest.approx(expected, rel=1e-6)
    assert r.powered_m == pytest.approx(tas * 900, rel=1e-6)
    assert r.glide_m == pytest.approx(24_000, rel=1e-9)


@pytest.mark.parametrize("from_deg,expected_gs", [
    (180.0, 61 + 10),                    # flying north, wind from the south: tailwind
    (0.0, 61 - 10),                      # headwind
    (90.0, math.sqrt(61 ** 2 - 10 ** 2)),  # pure crosswind: crab, lose a little
])
def test_hand_wind_on_powered_leg(pod, from_deg, expected_gs):
    r = reach(pod, 0, 0, track_deg=0, wind=Wind(10, from_deg))
    assert r.distance_m == pytest.approx(expected_gs * 900, rel=1e-9)


def test_glide_with_tailwind_matches_closed_form(pod):
    # Time aloft gliding at constant EAS from H to 0 in ISA:
    #   t = (1 / (EAS sin g)) * integral_0^H sqrt(sigma) dh,  sqrt(sigma) = theta^a, a = (EXP-1)/2
    #   integral = (T0/L) * (1 - theta_H^(a+1)) / (a+1)
    # The closed form ignores the geometric/geopotential difference, worth ~1e-4 at 6 km.
    H, W = 6000.0, 15.0
    a = (EXP - 1) / 2
    integral = (T0 / L) * (1 - (1 - L * H / T0) ** (a + 1)) / (a + 1)
    t = integral / (61 * math.sin(math.atan(1 / 8)))
    r = reach(pod, H, 0, track_deg=90, wind=Wind(W, 270), endurance_s=0)
    assert r.time_s == pytest.approx(t, rel=3e-4)
    assert r.distance_m == pytest.approx(H * 8 + W * t, rel=3e-4)


# ------------------------------------------------------------------ edge cases

def test_site_above_release_is_unreachable(pod):
    r = reach(pod, 500, 800, track_deg=0)
    assert r.distance_m == 0 and r.time_s == 0


def test_crosswind_stronger_than_airspeed_cannot_hold_track(pod):
    r = reach(pod, 0, 0, track_deg=0, wind=Wind(70, 90))
    assert not r.holds_track and r.distance_m == 0
    assert ground_speed_mps(61, Wind(70, 90), 0) is None


def test_headwind_stronger_than_airspeed_gives_zero_not_negative(pod):
    assert reach(pod, 0, 0, track_deg=0, wind=Wind(80, 0)).distance_m == 0


def test_no_thrust_powered_phase_is_just_a_glide():
    p = PodPerformance(300, 8, 61, 8, 61, thrust_n=0, endurance_s=600)
    assert p.powered_angle_rad == pytest.approx(math.atan(1 / 8))
    assert reach(p, 2000, 0, 0).distance_m == pytest.approx(16_000, rel=1e-9)


def test_weak_thrust_flattens_the_descent():
    p = PodPerformance(300, 8, 61, 8, 61, thrust_n=200, endurance_s=100_000)
    g, W = p.powered_angle_rad, p.weight_n
    assert W * math.cos(g) / 8 - 200 == pytest.approx(W * math.sin(g), rel=1e-9)   # force balance
    assert reach(p, 2000, 0, 0).distance_m == pytest.approx(2000 / math.tan(g), rel=1e-6)


def test_kinetic_energy_credit_and_debit(pod):
    fast = PodPerformance(300, 8, 61, 8, 61, 370, 900, kinetic_energy_recovery=0.5)
    dh = 0.5 * (250 ** 2 - 61 ** 2) / (2 * G)
    assert reach(fast, 0, 0, 0, endurance_s=0, initial_tas_mps=250).distance_m == pytest.approx(dh * 8, rel=1e-9)
    # default pod credits nothing
    assert reach(pod, 1000, 0, 0, endurance_s=0, initial_tas_mps=250).distance_m == pytest.approx(8000, rel=1e-9)
    # too slow: must dive to gain speed, full debit
    v_t = 61 / math.sqrt(sigma_isa(1000))  # target TAS at 1000 m, ~64 m/s
    debit = (v_t ** 2 - 30 ** 2) / (2 * G)
    assert reach(pod, 1000, 0, 0, endurance_s=0, initial_tas_mps=30).distance_m == pytest.approx((1000 - debit) * 8, rel=1e-6)


def test_profile_reuse_matches_fresh_build(pod):
    prof = DescentProfile.build(pod, 8000, floor_m=0)
    w = Wind(12, 300)
    for site in (0.0, 180.0, 1234.5, 5000.0):
        for trk in (0.0, 123.0, 300.0):
            a = prof.reach(trk, w, site).distance_m
            b = reach(pod, 8000, site, trk, wind=w).distance_m
            assert a == pytest.approx(b, rel=1e-4)
    with pytest.raises(ValueError):
        prof.reach(0, w, -10)


def test_input_validation(pod):
    with pytest.raises(ValueError):
        Wind(-1, 0)
    with pytest.raises(ValueError):
        Wind(5, 360)
    with pytest.raises(ValueError):
        PodPerformance(300, 8, 61, 8, 61, 370, 900, kinetic_energy_recovery=1.5)
    with pytest.raises(ValueError):
        DescentProfile.build(pod, 1000, endurance_s=-1)
    with pytest.raises(ValueError):
        footprint(pod, 1000, 0, n_bearings=0)


# ------------------------------------------------------------------ properties

alts = st.floats(0.0, 15_000.0)
trk = st.floats(0.0, 359.99)
wind = st.builds(Wind, st.floats(0.0, 40.0), st.floats(0.0, 359.99))


@settings(max_examples=150, deadline=None)
@given(alt=alts, t=trk, w=wind)
def test_reach_is_non_negative_and_deterministic(pod, alt, t, w):
    a = reach(pod, alt, 0, t, wind=w)
    assert a.distance_m >= 0
    assert a == reach(pod, alt, 0, t, wind=w)


@settings(max_examples=100, deadline=None)
@given(a1=alts, a2=alts, t=trk, w=wind)
def test_more_altitude_never_less_reach(pod, a1, a2, t, w):
    lo, hi = sorted((a1, a2))
    assert reach(pod, hi, 0, t, wind=w).distance_m >= reach(pod, lo, 0, t, wind=w).distance_m - 1e-6


@settings(max_examples=100, deadline=None)
@given(alt=alts, spd=st.floats(1.0, 40.0), frm=st.floats(0.0, 359.99))
def test_tailwind_beats_calm_beats_headwind(pod, alt, spd, frm):
    downwind = (frm + 180.0) % 360.0
    w = Wind(spd, frm)
    tail = reach(pod, alt, 0, downwind, wind=w).distance_m
    calm = reach(pod, alt, 0, downwind).distance_m
    head = reach(pod, alt, 0, frm, wind=w).distance_m
    assert tail > calm > head


@settings(max_examples=60, deadline=None)
@given(alt=alts, w=wind, d=st.floats(0.0, 180.0))
def test_footprint_is_symmetric_about_the_wind_axis(pod, alt, w, d):
    down = (w.from_deg + 180.0) % 360.0
    left = reach(pod, alt, 0, (down - d) % 360.0, wind=w).distance_m
    right = reach(pod, alt, 0, (down + d) % 360.0, wind=w).distance_m
    assert left == pytest.approx(right, rel=1e-9, abs=1e-6)


def test_calm_footprint_is_a_circle(pod):
    fp = footprint(pod, 5000, 200, n_bearings=24)
    assert len(fp) == 24 and fp[6].track_deg == 90.0
    assert max(r.distance_m for r in fp) == pytest.approx(min(r.distance_m for r in fp), rel=1e-12)


def test_ground_speed_calm():
    assert ground_speed_mps(61, CALM, 123) == 61
