"""Phase 1 end-to-end: "click" any point in the sector and see what the twin knows.

Usage: python scripts/query_point.py LAT LON [--sector sector_thar.yaml] [-k 3]
       python scripts/query_point.py 26.2515 73.0489
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # run from a checkout without installing
from sanjaya.config import SectorConfig, load_default, load_yaml  # noqa: E402
from sanjaya.core.geodesy import LatLon  # noqa: E402
from sanjaya.world import WorldModel  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lat", type=float)
    ap.add_argument("lon", type=float)
    ap.add_argument("--sector", default="sector_thar.yaml")
    ap.add_argument("-k", type=int, default=3, help="nearest airfields to list")
    args = ap.parse_args()

    sp = Path(args.sector)
    sector = load_yaml(sp, SectorConfig) if sp.exists() else load_default(SectorConfig, args.sector)
    world = WorldModel.load(sector)
    p = LatLon(lat=args.lat, lon=args.lon)
    info = world.query(p, k_airfields=args.k)

    print(f"point        {p.lat:.5f}, {p.lon:.5f}   in sector bbox: {world.in_sector(p)}")
    print(f"elevation    {'n/a' if info.elevation_m is None else f'{info.elevation_m:.1f} m AMSL'}")
    print(f"slope        {'n/a' if info.slope_deg is None else f'{info.slope_deg:.2f} deg'}")
    print(f"surface      {info.surface.name.lower()} (WorldCover {info.surface.value})")
    side = "INSIDE" if info.inside_india else "OUTSIDE"
    print(f"territory    {side} India, {abs(info.border_distance_m) / 1000:.1f} km from the boundary")
    print(f"airfields    nearest {args.k}:")
    for f in info.nearest_airfields:
        a = f.airfield
        elev = "" if a.elevation_m is None else f" elev {a.elevation_m:.0f} m"
        print(f"    {f.distance_m / 1000:7.1f} km  brg {f.bearing_deg:5.1f}  {a.ident:6s} {a.type:14s} {a.name} [{a.iso_country}]{elev}")
    if info.nearest_road is not None:
        r = info.nearest_road.road
        label = " ".join(x for x in (r.highway, r.ref, r.name) if x)
        print(f"road         {info.nearest_road.distance_m / 1000:.1f} km to {label} (osm way {r.osm_id})")
    else:
        print("road         no road layer loaded")
    prov = world.provenance["border"]
    print(f"\nCAVEAT: border from {prov.get('source', '?')}. {prov.get('caveat', '')}")
    world.close()


if __name__ == "__main__":
    main()
