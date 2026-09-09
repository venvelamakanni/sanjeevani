# SANJAYA — Implementation Plan (v0.1)

Part of **Project SANJEEVANI**. SANJAYA is the brain; **HANUMAN** is the pod it flies.

Scope: Python prototype of the Advisor loop and detached-flight logic, proven in simulation over a digital twin of the Thar/Rajasthan sector. Pod runs on the v0 placeholder until the OpenVSP aero table replaces it.

Locked decisions this plan is built on: border is a hard rule; auto-eject in scope behind an arming flag; Thar first, Ladakh second; Python-first with a small portable deterministic core; multiple metrics; fully Indian company, ITAR-free supply chain.

---

## 1. Engineering principles

1. **Deterministic core is sacred.** Energy, reachability, border check, ranking arithmetic, trigger logic: pure functions, fully typed, no randomness, no ML, no I/O. Same inputs always give the same plan. This is what gets ported to a certifiable language later.
2. **Everything is replayable.** Every run logs its full input stream and every decision. Any incident can be replayed bit-for-bit.
3. **Data-driven, not hard-coded.** Pod, weights, sector, threats, seasons all live in config files. Changing the pod is editing a file, not code.
4. **Adapters at every external boundary.** GNSS, IAF datalink, pilot vitals, weather, base status all sit behind interfaces with mock implementations. Real feeds plug in later without touching the core.
5. **Truth vs belief are separate.** The simulator knows the true pod position. The Brain only sees its estimated position and its uncertainty. The gap between them is where border-margin logic lives.

---

## 2. Project structure

```
sanjaya/
  core/            # deterministic core (pure, typed, no I/O)
    geodesy.py       lat/lon, ENU frames, geodesic distance
    energy.py        glide + powered range, density-altitude correction
    border.py        inside-India test with uncertainty margin (hard rule)
    reachability.py  reachable footprint, per-candidate feasibility
    ranking.py       cost function, weighted, friendly-filter first
    trigger.py       pilot-initiated + auto-eject conditions, arming flag
    plan.py          Plan and Candidate data types
  world/           # digital twin: data loading and world model
    dem.py           terrain elevation
    border_data.py   border polygon loader
    airfields.py     base and airfield database
    landcover.py     surface type (sand, cropland, built-up, water)
    roads.py         road segments as landing candidates
    threats.py       synthetic threat rings (config-driven)
    season.py        month-aware landability and weather
    weather.py       wind field (static, then time-varying)
  pod/
    model.py         loads pod config or aero table
    aero_table.py    reads OpenVSP/VSPAERO output
  estimation/
    truth.py         true state from simulator
    ins.py           INS drift model when GPS denied
    gnss.py          GPS + NavIC provider interface, jam/spoof modes
    fusion.py        estimated state + covariance
  advisor/
    loop.py          real-time cycle: state in, best plan out
  flight/
    route.py         waypoint planner with threat avoidance
    kinematics.py    3-DoF point-mass pod flight (JSBSim later)
    landing.py       landing mode selection and execution
    comms.py         rescue broadcast, jam-aware
  sim/
    scenario.py      scenario definition and randomization
    engine.py        runs one scenario end to end
    montecarlo.py    batch runner
    metrics.py       all four metric groups
    report.py        tables, heat maps, dead-zone maps
  adapters/          mocks for IAF datalink, vitals, base status
  config/
    pod_v0.yaml
    weights.yaml
    sector_thar.yaml
    threats_thar_synthetic.yaml
  tests/             unit + property-based tests on core/
```

---

## 3. Build order

Each phase has a definition of done. Do not start the next until the current one passes.

### Phase 0 — Foundations
- Repo, Python 3.11+, typed everywhere, `pytest` + `hypothesis`.
- `geodesy.py`: geodesic distance, bearing, local ENU frame.
- Config loading with `pydantic` validation.
- Run logger and replayer.
- **Done when:** a scripted aircraft track can be loaded, replayed, and every point's geodesy is unit-tested against known values.

### Phase 1 — Thar digital twin (data layer)
- Load DEM, border polygon, airfields, land cover, roads for the Thar bounding box.
- Build the world model as queryable layers: elevation at point, surface type at point, slope at point, nearest airfields, inside-India test.
- **Done when:** you can click any point in the sector and get elevation, surface, slope, inside-India, and nearest three airfields, and it matches independent sources.

### Phase 2 — Pod v0 energy model
- `pod_v0.yaml`: mass 300 kg, L/D 8, thrust 370 N, endurance 15 min, cruise 220 km/h.
- `energy.py`: glide range = altitude × L/D; powered range from endurance and speed; density-altitude correction; headwind/tailwind correction.
- `aero_table.py`: reader for the future OpenVSP table, tested against a synthetic table that reproduces L/D 8.
- **Done when:** given altitude, speed, wind, and pod config, the model returns a reach distance that hand calculation confirms.

### Phase 3 — Candidates + reachability + hard border
- Candidate generation: airfields, road segments, open flat patches (sand or bare, slope under threshold, away from built-up).
- `reachability.py`: which candidates are within reach given current energy and wind.
- `border.py`: **hard rule.** Any candidate outside India is deleted, not down-scored. Safe polygon shrinks by current position uncertainty.
- **Done when:** for a test aircraft state, the reachable set is correct, contains zero cross-border candidates, and shrinks correctly as uncertainty grows.

### Phase 4 — Ranking
- `ranking.py`: cost = weighted sum over reachability confidence, surface quality, distance, threat exposure en route, weather, medical urgency, rescue reachability. Weights in `weights.yaml`.
- Friendly filter runs **before** scoring (hard rule already applied).
- **Done when:** ranking is stable, weight changes move rankings in the expected direction, and property tests prove a closer safer site never ranks below a farther riskier one under equal other factors.

### Phase 5 — Advisor loop
- `loop.py`: consumes the aircraft state stream at 1 Hz (10 Hz later), emits best plan + ranked list every tick, logs everything.
- **Done when:** replaying a full Thar sortie produces a continuous plan timeline and the best candidate changes sensibly as the jet moves. **This is the first demo of the invention.**

### Phase 6 — Route planner
- `route.py`: waypoints from ejection point to candidate, routing around threat polygons (visibility graph or A* over a coarse grid), descent profile.
- **Done when:** routes never intersect threat rings, never cross the border, and respect the energy budget.

### Phase 7 — Estimation: truth vs belief
- `ins.py`: position drift grows with time when GPS is denied; `gnss.py`: GPS and NavIC providers with jam and spoof modes; `fusion.py`: estimated state + covariance.
- Border margin now driven by live covariance.
- **Done when:** in GPS-denied runs the Brain's belief drifts from truth realistically, and the border margin widens to match.

### Phase 8 — Detached flight
- `kinematics.py`: 3-DoF point-mass pod flies the route (JSBSim 6-DoF later, fed by the OpenVSP aero table).
- `landing.py`: runway / road / field / ditch selection and touchdown.
- Assume stable flight handed over at T+2 s after separation (separation itself is out of scope).
- **Done when:** the pod flies from ejection to touchdown in simulation and lands where the plan said.

### Phase 9 — Trigger logic
- `trigger.py`: pilot handle always honored. Auto-eject fires only when (arming flag on) AND (aircraft-unrecoverable flags) AND (pilot incapacitated OR below recovery threshold). All conditions logged.
- **Done when:** false-eject rate on healthy flights is zero across the test set and missed-eject is measured.

### Phase 10 — Scenario engine + Monte Carlo
- `scenario.py`: randomize hit location, altitude, speed, heading, wind, season, GPS-denied, comms-denied, pilot state, threat layout.
- `montecarlo.py`: run thousands of scenarios, parallelized.
- `metrics.py`: all four groups (below).
- **Done when:** a 10,000-run sweep completes, every metric is computed, and results are reproducible from a seed.

### Phase 11 — Reports and maps
- Reachability heat map of the sector, **dead-zone map**, per-candidate usage, metric tables. `folium` or `pydeck`.
- **Done when:** a non-engineer can read the report and see where a pilot is and is not safe.

### Later — SITL, HIL, Ladakh
- Swap `kinematics.py` for JSBSim 6-DoF using the OpenVSP aero table. Add PX4 SITL for real autopilot behaviour.
- HIL on a flight-controller board.
- Add `sector_ladakh.yaml`: thin-air corrections, terrain-referenced nav, LoC polygon.

---

## 4. Data sources for the Thar twin

| Layer | Prototype source | Production note |
|---|---|---|
| Terrain (DEM) | ISRO CartoSAT DEM via Bhoonidhi; Copernicus GLO-30 as easy fallback | Higher-res DRDO/SOI data later |
| **Border polygon** | OSM / Natural Earth admin boundary | **Not authoritative. A hard rule needs Survey of India / MoD geometry before any real use.** Flag this in every report. |
| Airfields | OurAirports open dataset, filtered to the sector | IAF base status feed via adapter |
| Land cover | ESA WorldCover 10 m (sand, bare, cropland, built-up, water) | Fine for Thar |
| Roads | OpenStreetMap | Filter to straight, paved segments |
| Weather / wind | Static seasonal wind profiles first, then IMD / ERA5 reanalysis | Live IMD feed via adapter |
| Season | Config: dust season, temperature, monsoon flags for Thar | Kutch flooding layer when that sector is added |
| Threats | **Synthetic**, config-driven rings and radar arcs | Real data is classified; enters via adapter only |
| Navigation | GPS + NavIC providers, simulated | Real receivers at HIL stage |

---

## 5. Stack

| Need | Choice |
|---|---|
| Language | Python 3.11+, fully typed |
| Geometry | `shapely`, `pyproj`, `geopandas` |
| Rasters | `rasterio`, `numpy` |
| Routing | `networkx` |
| Config / validation | `pydantic`, YAML |
| Tests | `pytest`, `hypothesis` (property-based tests on the deterministic core) |
| Maps / reports | `folium` or `pydeck`, `matplotlib` |
| Flight dynamics (later) | JSBSim (reads the OpenVSP aero table), PX4 SITL |
| Pod aero (your track) | OpenVSP + VSPAERO → aero table; SimScale for CFD |

---

## 6. Core data types (sketch)

```
AircraftState: t, lat, lon, alt, speed, heading, fuel, health_flags
EstimatedState: AircraftState + covariance (position uncertainty)
PodModel: mass, ld_ratio | aero_table, thrust, endurance, cruise_speed
Candidate: id, type(runway|road|field|ditch), lat, lon, surface, slope, inside_india
Plan: chosen Candidate, route waypoints, energy margin, eta, landing_mode, score
Scenario: seed, hit point, aircraft state, wind, season, gps_denied, comms_denied, pilot_state, threat_set
RunResult: Scenario + Plan timeline + touchdown point (truth) + peak_g + time_to_safety + flags
```

---

## 7. Metrics (computed by `metrics.py` from every Monte Carlo sweep)

| Group | Metric | Target |
|---|---|---|
| Safety | Territorial safety rate (landed inside India) | 100% of reachable cases; every miss investigated |
| Safety | Survival rate (peak g and landing loads within tolerance) | Maximize; report distribution |
| Safety | Injury severity histogram | Report |
| Safety | Time to safety (median, worst-case) | Minimize |
| Robustness | Success under GPS-denied / comms-denied / both | Reported separately |
| Robustness | Position uncertainty at landing vs border margin | Margin always held |
| Robustness | Re-plan success on mid-flight change | Maximize |
| Coverage | Reachability coverage (% of sector airspace with a safe site in reach) | Heat map; dead zones listed |
| Coverage | Landing-site quality mix | Report |
| Trigger | False auto-eject rate | **Zero** |
| Trigger | Missed-eject rate | Minimize |
| Trigger | Decision latency | Milliseconds |

---

## 8. Deterministic core boundary (what never gets ML)

`energy`, `reachability`, `border`, `ranking`, `trigger`, `plan`. Pure, typed, property-tested, replayable. ML is allowed later only in `world/` (land-cover classification, threat estimation) and `estimation/` (state estimation aids), and only as inputs to the core, never as decision-makers.

---

## 9. Rough effort (part-time, evenings and weekends)

| Phases | Effort |
|---|---|
| 0–2 | 2–3 weeks |
| 3–5 (first demo) | 3–4 weeks |
| 6–9 | 4–6 weeks |
| 10–11 | 2–3 weeks |
| **Total to full Monte Carlo report** | **~3–4 months** |

Phase 5 is the milestone that matters: a live map showing the best safe site updating as a jet crosses the Thar. That is the demo, the patent figure, and the iDEX pitch.

---

## 10. Handoff to the 3D track

The pod track owes the Brain exactly one artifact: an aero table (lift and drag coefficients vs angle of attack, at several speeds and altitudes) exported from VSPAERO. `aero_table.py` reads it. Swap the file, rerun the sweep, every footprint and every metric updates. Nothing else in the Brain changes.
