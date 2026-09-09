# SANJAYA

The autonomous safe-location and escape-flight brain of **Project SANJEEVANI**.
SANJAYA is the brain. **HANUMAN** is the pod it flies.

From engine start to touchdown, SANJAYA continuously knows the single best reachable
safe place inside friendly territory, and after ejection flies the pod there.
First target sector: Thar / Rajasthan, India's north-west border.

## Status: Phase 0 complete

| Phase | State |
|---|---|
| 0. Foundations (geodesy, config, track replay, run log) | Done, 25 tests |
| 1. Thar digital twin (DEM, border, airfields, land cover, roads) | Next |
| 2. HANUMAN v0 energy model | |
| 3. Candidates + reachability + hard border | |
| 4. Ranking | |
| 5. Advisor loop (first demo) | |

Full plan: `docs/Sanjaya-Implementation-Plan.md`.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
python scripts/make_sample_track.py     # regenerate the synthetic Thar sortie
python scripts/replay_track.py          # Phase 0 end-to-end
```

## Layout

```
sanjaya/core/        deterministic core: pure, typed, no I/O, no randomness, no ML
sanjaya/config/      pod_v0.yaml, sector_thar.yaml, weights.yaml
sanjaya/sim/         track loader/replayer, append-only run log
sanjaya/world|pod|estimation|advisor|flight|adapters   (later phases)
data/tracks/         recorded and synthetic sorties
scripts/             runnable entry points
tests/               pytest + hypothesis property tests on the core
```

## Rules the code enforces

- `border_rule` may only be `hard`. Crossing the IB is prohibited, never penalised.
- Health flags are causal. A hit recorded at time t is invisible before t. No future leakage.
- Every run is an append-only JSONL log with an unbroken sequence; any run replays bit-for-bit.
- Configs reject unknown fields and out-of-range values at load time.

## Data caveat

The border geometry used in prototyping (OSM / Natural Earth) is **not authoritative**.
Before any real use the hard border rule must run on Survey of India / MoD geometry.
