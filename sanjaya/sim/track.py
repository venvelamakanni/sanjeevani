"""Aircraft track loading and replay.

A track is a recorded sortie: one AircraftState per row, time-ordered.
The replayer streams it to the advisor loop at a fixed rate, interpolating
between recorded points so the advisor sees a steady clock regardless of how
the track was sampled.
"""
from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

from sanjaya.core.geodesy import LatLon, angle_diff_deg, wrap_deg
from sanjaya.core.state import AircraftState, HealthFlags

_COLUMNS = ("t", "lat", "lon", "alt_m", "speed_mps", "heading_deg", "fuel_kg")
_FLAGS = ("engine_out", "hydraulics_lost", "controls_unresponsive", "fire", "structural_failure")


def _row_to_state(row: dict[str, str]) -> AircraftState:
    flags = HealthFlags(**{k: row.get(k, "0").strip() in ("1", "true", "True") for k in _FLAGS})
    return AircraftState(
        t=float(row["t"]),
        pos=LatLon(lat=float(row["lat"]), lon=float(row["lon"])),
        alt_m=float(row["alt_m"]),
        speed_mps=float(row["speed_mps"]),
        heading_deg=wrap_deg(float(row["heading_deg"])),
        fuel_kg=float(row["fuel_kg"]),
        health=flags,
    )


def load_track(path: Path | str) -> list[AircraftState]:
    """Load a CSV track. Rows must be strictly increasing in t."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in _COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"track missing columns: {missing}")
        states = [_row_to_state(r) for r in reader]
    if not states:
        raise ValueError("track is empty")
    for a, b in zip(states, states[1:]):
        if b.t <= a.t:
            raise ValueError(f"track time not strictly increasing at t={b.t}")
    return states


def _lerp(a: float, b: float, u: float) -> float:
    return a + (b - a) * u


def interpolate(a: AircraftState, b: AircraftState, t: float) -> AircraftState:
    """Linear interpolation between two states at time t in [a.t, b.t].

    Health flags are causal step functions (zero-order hold): between samples the
    flags keep the value of the EARLIER sample. A hit recorded at b.t must not be
    visible before b.t, or decision-latency and trigger metrics would be measured
    against knowledge the system could not have had. No future leakage, ever.
    """
    if not a.t <= t <= b.t:
        raise ValueError("t outside [a.t, b.t]")
    u = 0.0 if b.t == a.t else (t - a.t) / (b.t - a.t)
    heading = wrap_deg(a.heading_deg + angle_diff_deg(a.heading_deg, b.heading_deg) * u)
    health = a.health if t < b.t else b.health
    return AircraftState(
        t=t,
        pos=LatLon(lat=_lerp(a.pos.lat, b.pos.lat, u), lon=_lerp(a.pos.lon, b.pos.lon, u)),
        alt_m=_lerp(a.alt_m, b.alt_m, u),
        speed_mps=_lerp(a.speed_mps, b.speed_mps, u),
        heading_deg=heading,
        fuel_kg=_lerp(a.fuel_kg, b.fuel_kg, u),
        health=health,
    )


def replay(track: list[AircraftState], rate_hz: float) -> Iterator[AircraftState]:
    """Stream the track at a fixed rate from track[0].t to track[-1].t inclusive."""
    if rate_hz <= 0:
        raise ValueError("rate_hz must be > 0")
    dt = 1.0 / rate_hz
    i = 0
    n_steps = int(round((track[-1].t - track[0].t) * rate_hz))
    for k in range(n_steps + 1):
        t = track[0].t + k * dt
        if t > track[-1].t:
            t = track[-1].t
        while i + 1 < len(track) - 1 and track[i + 1].t <= t:
            i += 1
        yield interpolate(track[i], track[i + 1], t) if len(track) > 1 else track[0]
