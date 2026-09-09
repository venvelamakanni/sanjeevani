# SANJAYA — Software Specification (v0.1 starting point)

Part of **Project SANJEEVANI**. SANJAYA is the brain; **HANUMAN** is the pod it flies.

The autonomous "always knows where safe is" brain for the HANUMAN escape pod.
This is a **complete first-pass spec** to add to or cut from. Nothing here is fixed.

---

## 1. Mission of the software (one line)

From engine start to safe landing, **continuously know the single best reachable safe place** for the pilot — and after ejection, **fly the pod there and land it**, with no input required from the pilot.

---

## 2. The two operating modes

| Mode | When | What the software does |
|---|---|---|
| **ATTACHED (Advisor)** | Engine start → escape trigger | Runs silently in the background on the fighter. Continuously solves "where is safe right now" and keeps a ready-to-execute answer at every instant. Never touches flight controls. |
| **DETACHED (Pilot)** | Escape trigger → touchdown | Takes over the pod completely. Executes the escape route, flies to the chosen safe location, and lands autonomously. Pilot is a passenger. |

The key property: **the answer already exists before it's ever needed.** Detached mode doesn't start thinking — it starts *executing* a plan Attached mode has been refining the whole flight.

---

## 3. Functional modules (what the software is made of)

### 3.1 State Estimation — "Where am I, exactly?"
- Fuses multiple sensors into one trusted picture of position, velocity, altitude, attitude.
- Sensor sources: **INS/IMU** (self-contained, jam-proof), **GNSS/GPS**, **barometric + air-data**, **radar/laser altimeter**, **terrain-reference navigation**.
- Must keep working when **GPS is jammed or spoofed** — falls back to INS + terrain matching. (Assume a contested battlefield; GPS is *not* reliable.)

### 3.2 World Model — "What's around me?"
- Live, layered map the whole system reasons over:
  - **Terrain & elevation** (mountains, valleys, obstacles).
  - **Landing candidates:** friendly runways, air bases, highways/roads, flat open fields, water for ditching.
  - **Territory:** friendly / neutral / hostile zones, front lines.
  - **Threats:** known SAM rings, radar coverage, enemy positions.
  - **Weather:** wind, visibility, ceilings, icing, turbulence.
- Sources: pre-loaded mission maps + terrain databases, live datalink updates, onboard sensors.

### 3.3 Safe-Location Candidate Generator
- Produces the running list of every place the pilot *could* be put down safely.
- Each candidate carries: location, type, surface quality, elevation, weather-on-site, threat exposure, and distance.

### 3.4 Reachability / Energy Envelope Solver — the make-or-break math
- Answers, for each candidate: **"Can the pod actually get there with the energy it has?"**
- Computes the reachable footprint from current position, given:
  - Remaining propellant/battery + glide performance.
  - Current altitude and speed (altitude = stored energy).
  - Wind (huge effect on range).
- Discards anything outside the envelope. This is **deterministic physics math**, not guesswork.

### 3.5 Ranking / Cost Function — "Which safe place is *best*?"
- Scores every reachable candidate. Starting weights (all tunable):

| Factor | Why it matters |
|---|---|
| Reachability confidence | No point choosing a place you might not reach. |
| Friendly vs hostile territory | A runway in enemy hands is not "safe." |
| Threat exposure en route | Avoid flying through SAM/radar coverage. |
| Surface suitability | Runway > road > flat field > rough ground > water. |
| Weather on site + en route | Fog/crosswind/icing degrade landing. |
| Distance / time to safety | Faster recovery = better, all else equal. |
| Medical urgency | If pilot is injured/unconscious, bias toward *closest* survivable option. |
| Rescue reachability | Can friendly recovery teams actually get there? |

- Output: **one ranked list, top choice always live.**

### 3.6 Trajectory & Route Planner
- Builds the actual flight path to the chosen destination: waypoints, altitude profile, threat-avoidance dog-legs, descent, and approach.
- Re-plans continuously as inputs change (new threat, wind shift, motor underperforming).

### 3.7 Guidance, Navigation & Control (GNC) — the autopilot
- **Detached-mode only.** Physically flies the pod: manages boost, deceleration, wing deployment, cruise, descent, and landing.
- Handles the violent early moments: tumble arrest, stabilization, getting to controlled flight.
- Deterministic, verifiable control laws (this is flight-safety-critical — see §5).

### 3.8 Landing Manager
- Picks the landing method for the terrain: **runway rollout, field/airbag, retro-thrust, or water ditch.**
- Executes flare, touchdown, and post-landing safing.

### 3.9 Communications & Rescue Coordination
- On trigger, auto-broadcasts: **"Pilot ejected, pod inbound to [location], ETA [time], pilot status [x]."**
- Keeps a live position beacon so recovery is waiting on arrival.
- Encrypted, jam-resistant, with graceful "comms-denied" fallback (still flies the plan silently).

### 3.10 Pilot Physiological Monitor
- Tracks pilot vitals and consciousness.
- If pilot is unconscious/injured, biases the whole system toward **closest survivable landing + fastest rescue**, and can trigger escape autonomously if the aircraft is doomed and the pilot is incapacitated.

### 3.11 Pod Health Monitor
- Watches its own propellant, battery, actuators, structure, and sensors.
- Feeds real capability back into the reachability solver (a degraded motor shrinks the reachable footprint — the plan must know that).

### 3.12 Trigger / Decision Logic
- Decides **when** to escape:
  - Pilot-initiated (handle pull) — always honored.
  - Auto-initiated — aircraft unrecoverable *and* (pilot incapacitated **or** below safe-recovery threshold).
- Deliberately conservative; false ejection is catastrophic.

---

## 4. Inputs and outputs at a glance

**Inputs**
- Aircraft state (position, speed, altitude, attitude, heading)
- Onboard sensors (INS/IMU, GNSS, air data, altimeters, terrain sensors)
- Pre-loaded maps, terrain, base/airfield databases
- Live datalink: threats, friendly positions, weather, updated no-go zones
- Pilot vitals + consciousness
- Pod self-health (fuel, battery, actuators, structure)

**Outputs**
- **Attached mode:** the current best safe location + ready route (silent, standby)
- **Detached mode:** live flight control commands, descent/landing execution
- Rescue broadcast + position beacon
- Event/black-box log of every decision (for verification & post-incident review)

---

## 5. AI/ML vs deterministic — the honest split (read this one carefully)

Not everything should be "AI." Mixing them wrong makes the system unsafe *and* uncertifiable. Clean division:

| Use **deterministic, verifiable code** for | Use **ML / learned models** for |
|---|---|
| Reachability / energy envelope (physics) | Terrain classification from imagery ("is that field landable?") |
| Flight control laws (GNC) | Threat/radar-coverage prediction |
| Landing execution | Weather nowcasting between data updates |
| Trigger/eject logic | Pattern-based failure prediction (pod health) |
| The final ranking arithmetic | Estimating pilot state from noisy vitals |

**Rule of thumb:** ML *informs the map and the estimates*; deterministic code *makes the life-and-death decisions and flies the pod.* Anything that directly keeps the pilot alive must be testable, repeatable, and provable — not a black box. This is also what makes military certification even conceivable.

---

## 6. The hard problems (don't let these hide)

| Problem | Why it's hard | Direction |
|---|---|---|
| **GPS denied / spoofed** | Battlefields jam and fake GPS routinely | Lean on INS + terrain-reference nav; treat GNSS as optional |
| **Comms jammed** | Can't rely on the datalink | Must fly the whole plan fully offline; broadcast blindly |
| **No safe place in range** | Sometimes there is no good option | Fall back to *least-bad* survivable option (e.g., controlled water ditch) — never "give up" |
| **Over deep water / open ocean** | Nothing to land on | Ditch + flotation + strongest possible beacon |
| **Over hostile territory** | Nearest ≠ safest | Ranking must weight *friendly* heavily over *close* |
| **Pilot unconscious** | No human backup at all | Full autonomy end-to-end; medical-urgency biasing |
| **Night / fog / storm** | Sensors degrade | Sensor fusion + terrain nav; conservative landing choice |
| **Cyber attack / spoofed data** | Enemy feeds false maps/threats | Signed data, sanity-checking, trust-scoring of inputs |
| **False ejection** | Ejecting when not needed can kill | Conservative, multi-condition trigger logic |
| **Weight of the compute/sensors** | Everything added costs pod weight | Keep hardware minimal, rad/vibration-hardened, low-power |

---

## 7. Non-functional requirements

- **Real-time & deterministic** — hard timing guarantees; the answer must always be fresh.
- **Fault-tolerant** — degrades gracefully as sensors/comms drop; never a single point of failure.
- **Verifiable / certifiable** — every safety-critical path testable and provable.
- **Secure** — encrypted, anti-spoof, anti-jam; validates every external input.
- **Fully offline-capable** — must complete the entire mission with zero connectivity.
- **Logged** — black-box record of every decision and input.
- **Lightweight** — minimal, hardened compute and sensor set.

---

## 8. Architecture (layers)

```
┌─────────────────────────────────────────────┐
│  COMMS / RESCUE  (broadcast, beacon, datalink) │
├─────────────────────────────────────────────┤
│  DECISION & PLANNING                           │
│   trigger logic · candidate gen · reachability │
│   · ranking · route planner                    │
├─────────────────────────────────────────────┤
│  PERCEPTION / WORLD MODEL                      │
│   terrain · threats · weather · landing sites  │
│   · pilot state · pod health   (ML lives here) │
├─────────────────────────────────────────────┤
│  STATE ESTIMATION  (sensor fusion, nav)        │
├─────────────────────────────────────────────┤
│  CONTROL  (GNC, landing)  — detached mode only │
└─────────────────────────────────────────────┘
```
Data flows **up** (sensors → understanding → decisions) and commands flow **down** (decisions → control) once detached.

---

## 9. Prototype path — what you can build now, in pure software

You don't need hardware to prove the crown-jewel behavior. Build it as a simulation:

1. **MVP — the Advisor loop.** Given a flight path (lat/long/alt/speed over time) + a set of candidate safe sites + wind, output *in real time* the single best reachable site and a route to it. Watch the answer change as the jet moves.
2. **Add reachability physics.** Model glide + powered range vs altitude/energy/wind; show the shrinking/growing reachable footprint live.
3. **Add the ranking function.** Layer in territory, threats, weather, surface type; tune the weights.
4. **Add threat/terrain layers.** Feed synthetic SAM rings, no-go zones, terrain; watch routes dog-leg around them.
5. **Add detached simulation.** Simple flight model that "flies" the pod along the chosen route to a landing.
6. **Stress it.** Kill GPS, jam comms, remove all safe sites, put it over water — prove graceful degradation.

Everything above is buildable with a flight-sim environment, map/terrain data, and standard routing + estimation techniques — squarely in your AI/ML wheelhouse. The Advisor loop (step 1) is the highest-value, most-defensible demo of the entire invention.

---

## 10. What this software is deliberately NOT (scope boundary)

- Not a weapons system — it never fights, only escapes.
- Not dependent on the network — connectivity is a bonus, never a requirement.
- Not a black box making life/death calls — the critical decisions stay deterministic and provable.
- Not the pod's structure or propulsion — this is the *brain*; the airframe is a separate workstream.

---

*v0.1 — a starting scaffold. Add modules, delete modules, re-weight the ranking, redraw the boundary. The one piece worth protecting above all is the continuous Advisor loop in §3.5 + §4 + §9 — that's the invention.*
