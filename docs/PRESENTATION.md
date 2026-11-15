# Observair: presenter's guide

What you need to present Observair: the pitch, the stack, how it works, how to set up the demo, the three-minute walkthrough, and answers to likely questions.

For setup details and full feature notes, see [README.md](../README.md).

---

## 1. The pitch (30 seconds)

> Pesticide drift often happens at dawn and dusk, when a temperature inversion traps fine droplets near the ground and carries them sideways into neighboring fields. A weather station at one height can't see an inversion. It reads calm, mild air and says "go".
>
> Observair compares temperature at two heights on the same mast. It plans every spray job around the windows when the air is actually mixing. It answers one question for a farmer or Pest Control Adviser (PCA): **given the target date, the equipment, the local weather and the neighbors, what is the earliest suitable window to finish this job?**
>
> It never relaxes a weather rule to force a schedule, and every simulated number is labeled as simulated.

**Who it's for:** growers, PCAs and spray crews planning ground-boom, airblast, drone or aircraft applications.

**Our approach in one line:** a single-height sensor would say Go, and the paired-height mast says Stop. The demo is built around showing that difference.

---

## 2. Stack

| Layer | Technology | Why |
|---|---|---|
| Backend | Python 3.13, **FastAPI**, Uvicorn, Pydantic | Small, typed JSON API; the rules engine is plain Python and easy to test |
| Storage | **SQLite** (`data/observair.db`, set `OBSERVAIR_DB` to change it) | No setup. Holds jobs, alerts, observations, records and plan acceptance. Reads are serialized behind a lock. |
| Frontend | **Vanilla JavaScript ES modules**, no build step, hand-written CSS with design tokens | Loads instantly with nothing to compile, and works on a phone over the LAN |
| Map | **MapLibre GL 4.7.1** (vendored in `web/vendor`), Esri World Imagery basemap, AWS Terrarium terrain tiles | 3D map, wind particles, thermal layer, first-person view, day/night lighting. Falls back to a 2D SVG view without WebGL. |
| Terrain | **USGS 3DEP** (ImageServer exportImage and EPQS), scikit-image, tifffile, Pillow | Real field elevation, slope, relief, contours, click-to-get elevation, elevation profile along a pass |
| Real weather (experimental) | **HRRR** via Herbie, cfgrib, eccodes, xarray; **AZMET** stations; **NWS** hourly forecast | Regional context and validation only. It never replaces the local paired sensors. |
| AI (optional, off by default) | Anthropic SDK, `claude-opus-5-5` | Only rephrases explanations the rules engine already wrote. Turned on with `OBSERVAIR_AI=1` plus an API key. Not used in the demo. |
| Tests | **pytest** (63 tests), FastAPI TestClient; **Playwright** for browser checks | Covers the engine, scheduler, nozzles, measurement model, decisions and the API |

**API keys needed: none.** Every data source the demo uses is public. The optional AI path needs an Anthropic key, but the demo doesn't use it.

---

## 3. How it works

```
 Simulated masts S1/S2 ──┐                       ┌──> Field map (3D, wind, thermal, terrain)
 (paired heights)        │                       │
 Field / product / ──────┼──> Decision engine ───┼──> Status panel + checks + decision ID
 neighbors / equipment   │    (app/engine.py)    │
 Field observations ─────┘          │            ├──> Explanations (English/Spanish)
                                    ▼            │
                              Scheduler ─────────┼──> Schedule (all job orders, 15-min slots)
                          (app/scheduler.py)     │
                                    │            └──> Records + CSV export
 HRRR / AZMET / NWS / 3DEP ─> experimental regional context and terrain (labeled, never decisive)
```

### Key modules

| File | Role |
|---|---|
| `app/engine.py` | One assessment per field and time. Validates the reading, then runs the inversion, wind, shear, product, neighbor, persistence and observation checks. Returns a status and a **decision ID**. |
| `app/measure.py` | Measurement model: installed heights, reference surfaces (ground or canopy), accuracy, and the requirements register |
| `app/scheduler.py` | Tries every job order with 15-minute slots, travel, setup, refills, crew shift, deadline and rain-free interval. Also produces the equipment recommendation, rain and surface concerns, and pre-application checks. |
| `app/equipment.py`, `app/nozzles.py` | Equipment compatibility, job-time estimate, and TeeJet XR, AIXR and TTI nozzle sizing from the published tables (with sources) |
| `app/profile.py` | Temperature interpolated to the release height (PCHIP, no extrapolation), FAO-56 log-wind estimate, spray-plane temperature difference, model-profile analysis |
| `app/terrain.py` | 3DEP elevation cache, field stats, elevation profile, overlay |
| `app/realdata.py` | HRRR, AZMET and NWS fetch; a corrected estimate (experimental); leave-one-station-out validation |
| `app/store.py` | SQLite persistence: jobs, alerts with clear streaks, observations, records |
| `app/explain.py` | Rule-based explanations in English and Spanish, with optional Claude rephrasing |
| `web/js/*.js` | `today`, `mapview`, `schedule`, `records`, `panels`/`insight` (status and evidence), `sim` (prototype controls) |

### Decision rules to know

| Rule | Value | Source |
|---|---|---|
| Inversion | Upper minus lower temperature above the combined uncertainty (±0.71 °F with two ±0.5 °F sensors) → Stop | Paired-height method |
| Wind window | 3–10 mph | Common label range (editable) |
| Stale data | Older than 20 min → Insufficient data, **never Go** | Prototype rule |
| Pair alignment | Both readings within 5 min and 25 m of each other | Prototype rule |
| Direction difference | Measured as the shortest way around the circle (350° vs 10° = 20°), and unreliable under 2 mph | Geometry |
| Persistence | 2 clean readings before an inversion counts as cleared; 2 clean checks before an alert clears | Prototype rule |
| Field observations | Can add Caution for 60 min; can **never** clear a flag | Prototype rule |
| Rain | Probability ≥ 40 % inside the rain-free interval blocks the slot | Demo product constraint |

All thresholds can be edited live under **Prototype controls → Simulation**.

---

## 4. What's real and what's simulated

Say this plainly if judges ask; it's a strength.

| Real | Simulated (labeled in the UI) |
|---|---|
| Basemap imagery and USGS 3DEP terrain for the Yuma Valley | Sensor masts S1 and S2 and every local reading |
| TeeJet nozzle tables (XR and AIXR from the catalog with page numbers, TTI from the product page) | Fields, growers, neighbors and treatment requests |
| AZMET station data, HRRR model, NWS forecast (experimental panel) | Demo products and their constraints (fictional names) |
| NDSU and challenge-tower sensor heights used to configure the masts | Rain-probability forecast; equipment costs |
| Scheduling, physics and validation math | The "critical change" event used in monitoring |

**Validation result** (real data, n = 33, leave-one-station-out): raw HRRR error 1.98 °F; nearest AZMET station 0.89 °F; HRRR plus residual correction 0.98 °F. The correction doesn't beat the nearest station yet, so we label it experimental and don't use it for decisions.

---

## 5. Before you present (checklist)

- [ ] `git pull` the `canopyguard-app` branch.
- [ ] Install dependencies: `python -m venv .venv`, then `.venv/Scripts/pip install -r requirements.txt` (on macOS or Linux, use `.venv/bin/pip`).
- [ ] Run the tests: `.venv/Scripts/python -m pytest -q` should show **63 passed**.
- [ ] Start the server: `.venv/Scripts/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- [ ] Open http://127.0.0.1:8000 in Chrome or Edge with hardware acceleration on (WebGL is needed for the 3D map).
- [ ] Open **Prototype controls** (top bar) and click **Reset demo scenario**. This resets requests, alerts, observations and scenario events.
- [ ] Open the **Field map** once, so basemap tiles and terrain are cached before you go on stage.
- [ ] Optional: press **Load regional real data** once on the map so the HRRR and AZMET panel is cached. The first HRRR fetch can take 10–30 s.
- [ ] Phone demo: open `http://<laptop-LAN-IP>:8000` on the same Wi-Fi, and allow port 8000 through the firewall.
- [ ] **Prototype controls** (Shift+P) has a toggle that hides the "Simulated" badges for clean screenshots. **Turn them back on for the live demo.**
- [ ] Have the README open in a tab for the final checklist.

**If Wi-Fi fails:** the app still runs. The map draws the fictional overlays on a plain background, and the local scenario, schedule and records all work offline. Real-data panels show a clear "unavailable" state.

---

## 6. Three-minute demo script

Scenario clock: **Sunday 15 Nov 2026, 05:30 MST**, a simulated dawn inversion in the Yuma Valley.

| Time | Screen | Do | Say |
|---|---|---|---|
| 0:00 | **Today** | Point at the next proposed job: Field B (broccoli), 06:15. | "Four requests came in. Broccoli Field B must be done by 10:00. In the order they came in, B and D would get no window." |
| 0:25 | **Today → Field A** | Point to the Stop and the line "A single low station alone would say Go." Click **Open map**. | "This is the blind spot we built for." |
| 0:40 | **Field map**, Field A | Right panel: *Single low station only: Go* vs *Paired-height mast: Stop*. Point to the cross-section: 30 ft is **+3.9 °F** warmer than 5 ft. | "An inversion lid. Fine droplets would hang under it and drift." |
| 1:00 | Same | Point at the wind particles and the neighbor list. Click **Which neighbors need attention?** | "Arrows show where air moves *to*. Air is heading toward the organic block. That's an attention check, not a drift prediction." |
| 1:20 | Same, scroll | Show **Height references**, the **Trend** card and the **Decision ID**. | "Every number is tied to an installed height. This decision has an ID that follows it to the schedule and the record." |
| 1:40 | Left panel, **Setup** | Show the recommended rig with time and cost savings. Open **Compare other equipment** and pick the drone: a blocking conflict appears. | "The drone can't confirm the product's droplet-class requirement, so it's blocked. Equipment can't clear an inversion either." |
| 2:05 | **Schedule** | Request order vs proposed order: **B 06:15–06:50 → A 08:45–09:40 → C tomorrow 06:15–08:20**. D has no sensor, so it isn't scheduled. Scroll to **Before each planned job**. | "We try every order. Reordering fits B before its deadline, and A runs after its inversion breaks. Rain and surface concerns are listed separately, and anything the product label doesn't give us stays Unknown." |
| 2:30 | **Field map**, then **Prototype controls → Simulation** | Press **Play** on the map's playback bar, then **Simulate critical change** in Prototype controls. Acknowledge the alert with a name. | "Monitoring: one grouped alert. It only clears after two clean checks in a row." |
| 2:45 | **Records** | Show the alert, acknowledgement, decision ID and *Simulated* flag. Click **Export CSV**. Toggle **ES** on an explanation. | "A complete record in English or Spanish, with nothing fabricated." |

**Backup lines if something breaks:**
- *Map is blank:* "WebGL is off here. This is the 2D fallback, and the decisions are identical." Continue from the right panel.
- *Real data is slow:* "That's a live pull from NOAA's HRRR. It's context only, so the demo doesn't depend on it."

---

## 7. Likely judge questions

**Why two heights?**
One height can't tell you whether warmer air sits above colder air. That pattern, an inversion, is the main dawn and dusk drift risk. Pairing heights on the same mast shows it directly.

**How do you handle sensor error?**
Each sensor has an accuracy (±0.5 °F in the demo), and the two are combined (√(a² + b²) ≈ ±0.71 °F). A temperature difference inside that band isn't called an inversion, and a trend inside that band is reported as "no clear trend".

**What if data is missing or old?**
The status becomes Insufficient data, never Go. Field D has no paired sensor, so it's never scheduled; the plan says why.

**Is this EPA or label compliant?**
We make no compliance claims. Thresholds are labeled as prototype or demo values and can be edited. The app tells the operator to re-read the actual label before every job.

**Where's the AI?**
The decisions are deterministic rules, on purpose, so they can be checked and repeated. Claude is optional and only rephrases the engine's own explanation. It's off in the demo.

**How does scheduling work?**
For each job order, the scheduler walks 15-minute slots. A start time is accepted only if every slot of the job is suitable, the rain-free interval after the last pass is clear, and travel, setup, refills, crew shift and deadline all fit. It tries every permutation of up to 7 open jobs. It picks the order that schedules the most priority-weighted jobs, then the one that finishes them earliest (weighted by priority). Ties go to the order the requests came in.

**How accurate is the real-data estimate?**
Leave-one-station-out on 33 hours: 0.98 °F error after correction, versus 0.89 °F for the nearest station. It isn't better yet, which is why it's labeled experimental.

**Why isn't the nozzle "coarsest is best"?**
Coarser droplets drift less but cover worse. We rank fully documented options first, then the one that meets the requirement with the *least* extra coarseness, then pressure margin.

**Why does Field D show no nozzle candidates?**
Field D is a lemon orchard sprayed with an airblast rig. Airblast results depend on the canopy and the fan airflow, which we don't model, and the TeeJet boom tables don't apply to it. The panel lists exactly what a nozzle choice would need: what we have (tree height, row spacing, sprayer) and what's missing (skirt height, canopy diameter, missing trees, block weather). It links to the UC Airblast Spray Advisor. Drones and aircraft get the same kind of explanation.

**What would you need to go live?**
A real paired-height sensor feed, product label values, operator-verified sensor installation heights, and the manufacturer's sensor accuracy and averaging specs. See *Awaiting data* in the README checklist.

---

## 8. Numbers to remember

| | |
|---|---|
| Inversion in the demo | +3.9 °F (30 ft vs 5 ft, Field A) |
| Combined uncertainty | ±0.71 °F |
| Wind window | 3–10 mph |
| Schedule slot | 15 min |
| Proposed plan | B 06:15, A 08:45, C tomorrow 06:15; D needs a sensor |
| Field B recommended rig | Rig 1, 60 ft boom: 58 min on site, about $116, about 34 ac/h (demo cost inputs) |
| Real-data validation | n = 33; nearest station 0.89 °F, corrected model 0.98 °F, raw HRRR 1.98 °F |
| Tests | 63 automated tests plus browser checks at desktop and mobile widths |
| Rule version | `cg-rules-0.4.0` |

---

## 9. Not done yet (say it before they ask)

- **Kriging:** three AZMET stations can't support a variogram.
- **PWM nozzle modelling.**
- **Airblast airflow modelling:** the airblast unit is checked for input completeness only.
- **Satellite and soil products:** NBM, GOES and others.
- **Real sensor hardware:** both masts are simulated.
- **Optional Claude rephrasing:** never exercised with live credentials.
