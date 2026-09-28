"""Phase 2 end-to-end: how far can HANUMAN get?

Prints the pod's performance, a reach table over altitude, day temperature and
wind, and the reach footprint at the moment the sample sortie takes its hit,
with the ground elevation under it read from the Thar DEM when available.

Usage: python scripts/reach_demo.py [--wind SPEED_MPS FROM_DEG] [--isa-offset C]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sanjaya.config import PodConfig, SectorConfig, load_default  # noqa: E402
from sanjaya.core.atmosphere import Atmosphere  # noqa: E402
from sanjaya.core.energy import CALM, Wind, footprint, reach  # noqa: E402
from sanjaya.pod.model import performance_from_config  # noqa: E402
from sanjaya.sim.track import load_track  # noqa: E402

COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wind", nargs=2, type=float, default=(10.0, 240.0), metavar=("SPEED_MPS", "FROM_DEG"))
    ap.add_argument("--isa-offset", type=float, default=20.0, help="day temperature above ISA, C (Thar summer ~+20)")
    args = ap.parse_args()

    pod = performance_from_config(load_default(PodConfig, "pod_v0.yaml"))
    print(f"pod        {pod.source}: {pod.mass_kg:g} kg, glide L/D {pod.glide_ld:g} at {pod.glide_eas_mps:g} m/s EAS,")
    print(f"           thrust {pod.thrust_n:g} N vs cruise drag {pod.cruise_drag_n:.1f} N "
          f"({'holds level' if pod.cruises_level else 'powered descent'}), endurance {pod.endurance_s:g} s")

    hot = Atmosphere(args.isa_offset)
    w = Wind(args.wind[0], args.wind[1] % 360.0)
    down, up = (w.from_deg + 180.0) % 360.0, w.from_deg
    print(f"\nreach to a sea-level site, km (powered + glide).  wind {w.speed_mps:g} m/s from {w.from_deg:g} deg")
    print(f"{'release alt':>12} {'calm ISA':>10} {'calm ISA+' + format(args.isa_offset, 'g'):>12} "
          f"{'downwind':>10} {'upwind':>10} {'glide only':>11}")
    for alt in (500, 1000, 3000, 6000, 9000, 12000):
        c = reach(pod, alt, 0, 0).distance_m
        ch = reach(pod, alt, 0, 0, atm=hot).distance_m
        dn = reach(pod, alt, 0, down, wind=w, atm=hot).distance_m
        dup = reach(pod, alt, 0, up, wind=w, atm=hot).distance_m
        g = reach(pod, alt, 0, 0, endurance_s=0).distance_m
        print(f"{alt:>10} m {c / 1e3:>10.1f} {ch / 1e3:>12.1f} {dn / 1e3:>10.1f} {dup / 1e3:>10.1f} {g / 1e3:>11.1f}")

    track = load_track(ROOT / "data" / "tracks" / "thar_sortie_01.csv")
    hit = next((s for s in track if s.health.unrecoverable), track[-1])
    ground = 0.0
    try:
        from sanjaya.world import WorldModel
        world = WorldModel.load(load_default(SectorConfig, "sector_thar.yaml"))
        z = world.dem.elevation_m(hit.pos)
        ground = z if z is not None else 0.0
        src = "Thar DEM"
        world.close()
    except FileNotFoundError:
        src = "no DEM, sea level assumed"
    print(f"\nsortie hit at t={hit.t:g} s: {hit.pos.lat:.4f}, {hit.pos.lon:.4f}, {hit.alt_m:.0f} m AMSL, "
          f"{hit.speed_mps:.0f} m/s, ground {ground:.0f} m ({src})")
    fp = footprint(pod, hit.alt_m, ground, wind=w, atm=hot, n_bearings=8, initial_tas_mps=hit.speed_mps)
    calm = footprint(pod, hit.alt_m, ground, wind=CALM, atm=hot, n_bearings=8)
    print("reach to level ground at that elevation, km:")
    print("   " + "".join(f"{c:>8}" for c in COMPASS))
    print("   " + "".join(f"{r.distance_m / 1e3:>8.1f}" for r in fp) + "   with wind")
    print("   " + "".join(f"{r.distance_m / 1e3:>8.1f}" for r in calm) + "   calm")
    print(f"time aloft {fp[0].time_s / 60:.1f} min. Terrain between here and there is Phase 3/6's problem.")


if __name__ == "__main__":
    main()
