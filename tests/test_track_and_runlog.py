import json
from pathlib import Path

import pytest

from sanjaya.core.geodesy import LatLon
from sanjaya.core.state import AircraftState, HealthFlags
from sanjaya.sim.runlog import RunLogger, read_run
from sanjaya.sim.track import interpolate, load_track, replay


def test_sample_track_loads_and_is_monotonic(sample_track_path):
    tr = load_track(sample_track_path)
    assert len(tr) > 100
    assert all(b.t > a.t for a, b in zip(tr, tr[1:]))
    assert tr[0].speed_mps == 0.0
    assert max(s.alt_m for s in tr) == pytest.approx(6000.0)


def test_sample_track_has_a_hit_on_return_leg(sample_track_path):
    tr = load_track(sample_track_path)
    first = next(s for s in tr if s.health.unrecoverable)
    assert first.t == 1100.0
    assert first.health.hydraulics_lost and first.health.controls_unresponsive


def test_replay_at_1hz_has_steady_clock(sample_track_path):
    tr = load_track(sample_track_path)
    states = list(replay(tr, rate_hz=1.0))
    ts = [s.t for s in states]
    assert ts[0] == tr[0].t and ts[-1] == tr[-1].t
    assert all(b - a == pytest.approx(1.0) for a, b in zip(ts, ts[1:]))
    assert len(states) == int(tr[-1].t - tr[0].t) + 1


def test_replay_matches_recorded_points_exactly(sample_track_path):
    tr = load_track(sample_track_path)
    by_t = {s.t: s for s in replay(tr, rate_hz=1.0)}
    for rec in tr:
        got = by_t[rec.t]
        assert got.pos.lat == pytest.approx(rec.pos.lat, abs=1e-9)
        assert got.alt_m == pytest.approx(rec.alt_m)
        assert got.health == rec.health


def test_interpolation_wraps_heading_correctly():
    a = AircraftState(0, LatLon(26, 72), 1000, 200, 350.0, 100)
    b = AircraftState(10, LatLon(26, 72), 1000, 200, 10.0, 100)
    mid = interpolate(a, b, 5)
    assert mid.heading_deg == pytest.approx(0.0, abs=1e-9)


def test_interpolation_flags_are_causal_no_future_leakage():
    a = AircraftState(0, LatLon(26, 72), 1000, 200, 0, 100)
    b = AircraftState(10, LatLon(26, 72), 1000, 200, 0, 100, HealthFlags(fire=True))
    assert interpolate(a, b, 1).health.fire is False      # hit at t=10 is invisible at t=1
    assert interpolate(a, b, 9.999).health.fire is False
    assert interpolate(a, b, 10).health.fire is True       # visible exactly when recorded


def test_track_rejects_non_monotonic_time(tmp_path: Path):
    p = tmp_path / "bad.csv"
    p.write_text("t,lat,lon,alt_m,speed_mps,heading_deg,fuel_kg\n0,26,72,100,0,0,10\n0,26,72,100,0,0,10\n")
    with pytest.raises(ValueError):
        load_track(p)


def test_runlog_roundtrip_and_sequence(tmp_path: Path, sample_track_path):
    tr = load_track(sample_track_path)
    log = tmp_path / "run.jsonl"
    with RunLogger(log, run_id="phase0-test") as rl:
        for s in replay(tr, 1.0):
            rl.log(s.t, "aircraft_state", s)
    events = list(read_run(log))
    assert len(events) == int(tr[-1].t - tr[0].t) + 1
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert events[0]["payload"]["pos"] == {"lat": tr[0].pos.lat, "lon": tr[0].pos.lon}


def test_runlog_detects_corruption(tmp_path: Path):
    log = tmp_path / "run.jsonl"
    with RunLogger(log, "x") as rl:
        rl.log(0, "a", {}); rl.log(1, "b", {}); rl.log(2, "c", {})
    lines = log.read_text().splitlines()
    log.write_text("\n".join([lines[0], lines[2]]) + "\n")   # drop seq 2
    with pytest.raises(ValueError):
        list(read_run(log))
