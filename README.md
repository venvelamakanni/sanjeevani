# SANJAYA

The autonomous safe-location and escape-flight brain of **Project SANJEEVANI**.
SANJAYA is the brain. **HANUMAN** is the pod it flies.

From engine start to touchdown, SANJAYA continuously knows the single best reachable
safe place inside friendly territory, and after ejection flies the pod there.
First target sector: Thar / Rajasthan, India's north-west border.

## Status: Phase 1 complete

| Phase | State |
|---|---|
| 0. Foundations (geodesy, config, track replay, run log) | Done |
| 1. Thar digital twin (DEM, border, airfields, land cover, roads) | Done |
| 2. HANUMAN v0 energy model | Next |
| 3. Candidates + reachability + hard border | |
| 4. Ranking | |
| 5. Advisor loop (first demo) | |

Full plan: `docs/Sanjaya-Implementation-Plan.md`.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]" --config-settings editable_mode=compat
pytest                                   # offline tests; Thar data tests skip until fetched
python scripts/fetch_world_data.py       # ~300 MB: DEM tiles, land cover, roads (once)
pytest                                   # now also checks the twin against known places
python scripts/query_point.py 26.2515 73.0489   # Phase 1 end-to-end: "click" a point
python scripts/replay_track.py           # Phase 0 end-to-end
```

`editable_mode=compat` writes a plain path entry instead of an import hook. Python 3.14
on macOS ignores `.pth` files that carry the hidden flag, which the default hook trips
over inside `~/Documents`; the scripts also add the repo root to `sys.path` themselves.

## Layout

```
sanjaya/core/        deterministic core: pure, typed, no I/O, no randomness, no ML
sanjaya/world/       digital twin: DEM, land cover, border, airfields, roads, WorldModel facade
sanjaya/config/      pod_v0.yaml, sector_thar.yaml, weights.yaml
sanjaya/sim/         track loader/replayer, append-only run log
sanjaya/pod|estimation|advisor|flight|adapters   (later phases)
data/world/          per-sector twin data (see data/world/README.md for sources and licences)
data/tracks/         recorded and synthetic sorties
scripts/             runnable entry points
tests/               pytest + hypothesis; synthetic-world tests plus real-Thar checks
```

## The twin in one call

```python
from sanjaya.config import SectorConfig, load_default
from sanjaya.core.geodesy import LatLon
from sanjaya.world import WorldModel

world = WorldModel.load(load_default(SectorConfig, "sector_thar.yaml"))
info = world.query(LatLon(26.2515, 73.0489))
# info.elevation_m, info.slope_deg, info.surface, info.inside_india,
# info.border_distance_m (signed), info.nearest_airfields, info.nearest_road
```

## Rules the code enforces

- `border_rule` may only be `hard`. Crossing the IB is prohibited, never penalised.
- Health flags are causal. A hit recorded at time t is invisible before t. No future leakage.
- Every run is an append-only JSONL log with an unbroken sequence; any run replays bit-for-bit.
- Configs reject unknown fields and out-of-range values at load time.
- The world layers describe the world as it is, across the border too. Only the border rule decides what is allowed.

## Data caveat

The border geometry used in prototyping (Natural Earth) is **not authoritative** and the
layer says so in its provenance. Before any real use the hard border rule must run on
Survey of India / MoD geometry.
