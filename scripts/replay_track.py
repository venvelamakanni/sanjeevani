"""Phase 0 end-to-end: load a track, replay it at the sector's advisor rate,
log every state as an event, then read the log back and verify it.

Usage: python scripts/replay_track.py [track.csv] [run_id]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # run from a checkout without installing
from sanjaya.config import SectorConfig, load_default  # noqa: E402
from sanjaya.sim.runlog import RunLogger, read_run  # noqa: E402
from sanjaya.sim.track import load_track, replay  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    track_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/tracks/thar_sortie_01.csv"
    run_id = sys.argv[2] if len(sys.argv) > 2 else "phase0"
    sector = load_default(SectorConfig, "sector_thar.yaml")
    track = load_track(track_path)
    out = ROOT / "runs" / f"{run_id}.jsonl"

    n, first_hit = 0, None
    with RunLogger(out, run_id) as log:
        log.log(track[0].t, "run_start", {"sector": sector.name, "rate_hz": sector.advisor_rate_hz, "track": str(track_path)})
        for s in replay(track, sector.advisor_rate_hz):
            log.log(s.t, "aircraft_state", s)
            n += 1
            if first_hit is None and s.health.unrecoverable:
                first_hit = s.t
                log.log(s.t, "aircraft_unrecoverable", s.health)
        log.log(track[-1].t, "run_end", {"states": n})

    events = list(read_run(out))
    print(f"sector={sector.name} rate={sector.advisor_rate_hz} Hz")
    print(f"track: {len(track)} recorded points, {track[0].t:.0f}..{track[-1].t:.0f} s")
    print(f"replayed {n} states, first unrecoverable at t={first_hit}")
    print(f"log: {out}  events={len(events)}  sequence verified")


if __name__ == "__main__":
    main()
