"""Generate a synthetic Thar sortie for Phase 0 replay.

Profile: Jodhpur (AFS) take-off, climb to 6,000 m heading west-northwest toward
Jaisalmer, patrol leg toward the IB, 180 turn, return leg. A hydraulics hit is
injected on the return leg so later phases have a trigger to react to.
Sampled every 5 s so the 1 Hz replayer has to interpolate.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # run from a checkout without installing
from sanjaya.core.geodesy import LatLon, destination, wrap_deg  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "data" / "tracks" / "thar_sortie_01.csv"

JODHPUR = LatLon(26.2515, 73.0489)   # Jodhpur AFS, approx
DT = 5.0


def main() -> None:
    rows = []
    pos = JODHPUR
    t = 0.0
    alt, speed, fuel = 220.0, 0.0, 4000.0
    heading = 290.0

    def push(flags: dict[str, int] | None = None) -> None:
        f = {"engine_out": 0, "hydraulics_lost": 0, "controls_unresponsive": 0, "fire": 0, "structural_failure": 0}
        if flags:
            f.update(flags)
        rows.append({"t": round(t, 1), "lat": round(pos.lat, 6), "lon": round(pos.lon, 6), "alt_m": round(alt, 1),
                     "speed_mps": round(speed, 1), "heading_deg": round(heading, 1), "fuel_kg": round(fuel, 1), **f})

    push()
    # Take-off and climb: 0-300 s, accelerate to 250 m/s, climb to 6000 m
    for _ in range(60):
        t += DT
        speed = min(250.0, speed + 4.2 * DT)
        alt = min(6000.0, alt + 19.5 * DT)
        fuel -= 1.6 * DT
        pos = destination(pos, heading, speed * DT)
        push()
    # Outbound patrol leg: 300-780 s at 250 m/s -> ~120 km WNW, ends near Jaisalmer / IB approach
    for _ in range(96):
        t += DT
        fuel -= 1.1 * DT
        pos = destination(pos, heading, speed * DT)
        push()
    # 180 turn over 60 s
    for _ in range(12):
        t += DT
        heading = wrap_deg(heading - 15.0)
        fuel -= 1.1 * DT
        pos = destination(pos, heading, speed * DT)
        push()
    # Return leg: hydraulics hit at 1000 s, then controls degrade at 1100 s
    for _ in range(96):
        t += DT
        fuel -= 1.1 * DT
        pos = destination(pos, heading, speed * DT)
        flags = None
        if t >= 1100.0:
            flags = {"hydraulics_lost": 1, "controls_unresponsive": 1}
            alt -= 25.0 * DT
        elif t >= 1000.0:
            flags = {"hydraulics_lost": 1}
        push(flags)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUT}")
    print("start", rows[0]["lat"], rows[0]["lon"], "end", rows[-1]["lat"], rows[-1]["lon"], "t_end", rows[-1]["t"])


if __name__ == "__main__":
    main()
