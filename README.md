# Observair

Spray-window planning for farmers and Pest Control Advisers (PCAs). Treatment has already been decided by pest scouting or a spray schedule. Observair answers: **given the target date, available equipment, local weather and neighboring fields, what is the earliest suitable opportunity to complete this job?**

It is decision support only. It does not diagnose pests, choose pesticides, recommend rates, predict exposure or drift distance, guarantee zero drift, or control equipment. **Go means no configured flags were detected, not guaranteed safety.**

Hack Arizona AgX prototype. All fields, growers, sensors, neighbors, readings and product constraints in the demo are **fictional or simulated** and are labeled that way in the UI.

## Run it

Requires Python 3.11+. Optional real-data and terrain features also need `herbie-data cfgrib eccodes xarray tifffile scikit-image` (see requirements.txt).

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt        # Windows (use .venv/bin/pip on macOS/Linux)
.venv/Scripts/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://127.0.0.1:8000. For a phone on the same network, open `http://<your-computer-LAN-IP>:8000`. The frontend uses same-origin `/api` routes, so no URL changes are needed. Allow port 8000 through the firewall if the phone can't connect.

- Data is stored in `data/observair.db` (SQLite). Set `OBSERVAIR_DB` to change it.
- **Replay demo** on the Today page resets requests, alerts and scenario events.
- MapLibre is vendored in `web/vendor`. Fonts, basemap tiles and terrain load from the internet. Offline, the map still draws the fictional overlays on a plain background. If WebGL is unavailable, a 2D SVG schematic is used.

Tests: `.venv/Scripts/python -m pytest -q` (93 tests). Presenter's guide: [docs/PRESENTATION.md](docs/PRESENTATION.md).

Optional AI-phrased explanations: `pip install anthropic`, configure Anthropic credentials (e.g. `ANTHROPIC_API_KEY`), then set `OBSERVAIR_AI=1`. Claude (`claude-opus-5-5`, server-side refusal fallback enabled) only rephrases the rule-based engine lines it is given. Any failure or refusal falls back to the rule-based text. The key stays on the server. **This path was not exercised during the build** (no credentials were configured); the rule-based path is what the demo uses and what was tested.

## What it does

| Area | Contents |
|---|---|
| **Today** | Next proposed job with depart/travel/setup times, deadlines and conflicts, unscheduled jobs with the reason, fields needing attention (including "ground-only would say Go" blind spots), treatment requests, and candidate weather windows for today and tomorrow, and an ML drift-flag outlook (hourly probability of a Stop-level flag for the next 12 h, likely window, turning-bad warning). |
| **Field map** | Desktop: fields and equipment on the left, map in the center, status and explanation on the right, time slider and replay at the bottom. Mobile: full-width map, status strip, bottom nav, and a draggable bottom sheet (Status / Setup / Time / Explain). Separate layers for decision status, inversion ΔT, interpolated temperature (5 ft or 30 ft), wind at both heights, sensitive areas and exclusions, and application passes. 2D/3D toggle with real DEM terrain at 1× scale. Mark sensitive areas or exclusions by clicking corners. |
| **Schedule** | Proposed order compared with the request order, a lane timeline (travel+setup, application, rain-free interval, deadline, suitable slots), a rain-probability strip, unscheduled jobs, and a request editor. |
| **Records** | Grouped alerts with operator acknowledgement, a filterable log (readings, triggered rules, equipment configs, schedule revisions, alerts, acks, areas, settings), CSV export, and an optional live regional context panel. |

### Map and visual layer
- Built on **MapLibre GL** (open-source fork of Mapbox GL, same 3D API, no account token needed).
- Opens in 3D: a camera fly-in, AWS terrarium DEM terrain at true 1× scale, hillshade, an atmospheric sky, and Esri satellite imagery (or CARTO dark streets).
- **Fields:** non-selected fields are 3D slabs colored by decision status. The selected field is flat so its passes stay visible.
- **Sensor masts:** 3D columns with rings at 5 ft and 30 ft colored by measured temperature, so an inversion shows as a warm upper ring. Mast height is drawn **4×** for visibility, as the legend states.
- **Wind flow:** animated particles from an inverse-distance blend of the two masts' wind vectors at 5 ft, 30 ft or both.
  - Particles exist only within 1.5 km of a mast; farther areas are unassessed and have no flow.
  - Particle speed is exaggerated **70×** for readability (labeled). Above 10 mph they turn red.
  - With reduced motion, static streamlines replace the animation.
- **Application replay:** a ground-aligned vehicle marker (tractor or drone) moves along the passes. The active pass shows as its swath-width strip.
- **HUD:** shows status, ΔT, wind at both heights, rain chance and data time, all bound to the viewed or replayed time.

### Field panel, equipment recommendation and prototype controls
- **Field picker:** a dropdown with each field's crop photo, crop type, acreage and status. The photos are representative Wikimedia Commons images credited in the UI with author and license (`app/photo_credits.json`). They are not photos of the fictional fields.
- **Recommended equipment** (`GET /api/recommend?field_id=`): re-runs the full sequence planner once per available rig, then ranks them:
  1. no blocking conflict;
  2. this job fits before its deadline;
  3. most priority-weighted jobs in the whole plan;
  4. earliest finish;
  5. shortest job.

  It shows a photo, key numbers, and the schedule each rig would get. **Use this equipment and replan** commits the choice. With the demo product, the boom is recommended. The drone stays blocked because a µm atomizer setting can't verify an ASABE droplet-class requirement.
- **Why it saves time and money:** under the recommendation the app shows the recommended rig's time on site (travel + setup + job), crew-hours, estimated cost and cost per acre, work rate (acres per hour), and the share of the job spent spraying. It then compares that against each alternative.
  - Cost = crew × hours on site × labor rate + machine hours × machine rate.
  - The rates ($24/person-hour, and $110 / $55 / $65 per hour for the boom / airblast / drone rigs) are **demo cost inputs** in `app/catalog.py`. Replace them with real rates.
  - A rig set up for the wrong crop (for example airblast in lettuce) is never used to claim a saving.
  - Rigs blocked by a fixable constraint, such as the drone's unverified droplet class, are shown as **reference only**.
  - When reordering jobs is what saves a deadline, a sequencing note says so.
- **Equipment photos** (self-propelled sprayer, spray drone, orchard/vineyard tower sprayer, ag aircraft) are Commons photos with the background removed and placed on white. This was done once, offline, with `rembg`, which is not a runtime dependency. Credits note the edit. Commons has no classic orchard airblast photo, so Rig 2 uses a vineyard/orchard tower sprayer and is labeled that way. All are representative, not the units in the plan.
- **Prototype controls** (top-bar button, or **Shift + P**) keep demo tools off the dashboard:
  - **View tab:** camera mode (Overview, Operator POV ride-along, Orbit), day/night, 2D/3D, basemap, thermal heat map (ironbow palette, interpolated, transparent where unassessed), wind flow, field coloring, layers, and **Hide demo badges**. Per-reading "Simulated" tags always stay visible.
  - **Simulation tab:** scenario clock, application replay, critical-change injection, rule thresholds, and demo reset.
- **Day and night modes:** follow the system setting until chosen; the map imagery and sky switch with the theme.

### Decision engine (`app/engine.py`)
- Paired readings at **5 ft and 30 ft** (simulated masts S1 and S2).
- ΔT = upper − lower, with combined sensor uncertainty ±√2·0.5 °F:
  - ΔT above the uncertainty band → **Stop** (inversion).
  - 0 < ΔT ≤ uncertainty → **Caution** (possible weak inversion).
  - Upper not warmer → no inversion flagged.
- Wind at 5 ft below 3 mph or above 10 mph → **Stop** (challenge defaults). Product wind limits are checked separately.
- Speed and direction shear are compared across heights with circular differences (350° vs 10° = 20°). Direction comparison is marked unreliable below 2 mph.
- Missing, stale (> 20 min), invalid or future-dated readings → **Insufficient data**, never Go.
- Sensitive areas are checked by geometry. "Wind from" is converted to "air moving toward" and compared with the bearing to each area inside an attention radius. A user-entered "hold while air moves toward" constraint blocks; otherwise the area is flagged for attention only.

### Scheduler (`app/scheduler.py`)
- Evaluates every job order (24 permutations for the four demo jobs).
- Each job is simulated per equipment unit, accounting for:
  - travel (straight line × 1.3 road factor) and setup;
  - crew shift;
  - earliest start and deadline;
  - every 15-min slot of the full job;
  - the product's rain-free interval after the last pass against the simulated forecast probability.
- Weather constraints are never relaxed. A job with no window shows *"No suitable window found before the requested deadline - review with your PCA."* plus the rejected causes.
- If the rain-free interval is unknown, the job can still be scheduled but is marked "rain check incomplete."

### Equipment (`app/equipment.py`)
- **Duration** = generated path length ÷ speed + headland turns + non-spray moves + refills. Drone refills include battery swaps.
- **Compatibility:**
  - equipment vs crop type;
  - nozzle family vs equipment (TeeJet tips are not offered for drone atomizers);
  - product method;
  - product droplet requirement vs the operator-entered ASABE class.
  - A drone's µm setting cannot verify an ASABE-class requirement, so the drone stays a candidate with a blocking conflict.
- **Product buffers** become exclusion strips that stay regardless of equipment.
- Equipment changes never clear a weather Stop.

## Measurement, terrain, nozzle and real-data additions

Each item below is marked **Implemented**, **Experimental**, **Simulated** or **Deferred**.

### Measurement model — Implemented (`app/measure.py`, `app/engine.py`)
- Every reading records its own metadata: installed height, reference surface (ground, canopy, spray surface or model ground), observation time, status, accuracy, averaging interval, gust interval and shielding. Temperature and wind heights are stored separately.
- **Three configurations, never treated as equivalent:**

  | Configuration | Heights | Source |
  |---|---|---|
  | Near-spray-surface | 6–12 in and 8–10 ft above the soil or closed canopy | NDSU AE-1705 |
  | Challenge tower | 5 ft and 30 ft above ground | Challenge example |
  | Model profile | Documented model levels | HRRR |

- Simulated mast S1 follows the tower configuration. Simulated mast S2 follows the near-surface method: 9 in and 9 ft above the canopy, with a single wind sensor at 2 m above ground.
- **A pair is invalid** (insufficient data, never Go) when:
  - the two readings are more than 5 min apart (prototype tolerance, configurable);
  - a required sensor height is undocumented;
  - the two temperatures use different reference surfaces.
- Shear is reported **Not assessed** on a mast with only one wind height.
- The temperature-difference trend needs at least three recent pairs.
- **Requirements register:** `/api/requirements`, shown in Records, lists 24 metrics, the decisions each one supports, and the behavior when it is missing.

### Conditions at the release height — Implemented, estimates labeled (`app/profile.py`)
This ports the useful part of the `backend-implementation` branch: multi-height and layer-by-layer analysis.
- **Release height** is computed per spray plan:
  - boom: inches above the target canopy;
  - drone: metres above the canopy;
  - airblast: manifold height above ground.
- **Temperature:** linear interpolation between installed sensors. It is **never extrapolated**; outside the measured range the panel says so.
- **Wind:** FAO-56 logarithmic profile (d = ⅔h, z₀m = 0.123h), fitted through the measured level or levels. It is flagged unreliable whenever an inversion is flagged, because the log law assumes neutral stability.
- These estimates are context only. Go/Stop still uses measured values.
- **Model profiles** (HRRR native levels at their real heights above model ground) get layer lapse rates, inverted layers, inversion top and regime. The panel states that the lowest level (~10 m) cannot resolve a 6 in–10 ft inversion.
- **Not taken from that branch:** the soil "skin" temperature (not air temperature), and EPA compliance wording. The ML forecaster was later rebuilt with measured, held-out skill (see *Calibrated ML drift-flag forecaster*).

### Nozzle candidates — Implemented, source-limited (`app/nozzles.py`)
- **Required flow per nozzle** = GPA × MPH × spacing (in) ÷ 5940, from the TeeJet guide (li-tj416, p. 94).
- **Transcribed data from the guide:**
  - p. 76: droplet class by tip size for XR110 at 30 psi and AIXR at 60 psi;
  - p. 94: the full AIXR11004 table (15–90 psi, XC → M, capacities 0.24–0.60 GPM).
- **Required pressure** comes from the nominal-rating convention (size code = GPM at 40 psi).
- **Droplet class** counts as documented only at a documented row, or between two rows that share the same class.
- **Each candidate card shows:**
  - required vs. expected flow, proposed pressure, droplet class and its source;
  - the compatibility checks it passed or failed;
  - why this family and why this size;
  - why the smaller and larger sizes were rejected;
  - which checks are missing.
- **Demo result:** 15 GPA, 8 mph and 20 in spacing give 0.404 GPM per nozzle. The AIXR11004 delivers that at 40.8 psi, which is Coarse, so it is recommended.
- If no candidate is fully documented, the answer is "no suitable candidate". A droplet class entered by the operator is used only as a labeled fallback.
- Airblast and drone atomizers use separate models; ground-boom formulas are never applied to them.

### Terrain — Implemented (`app/terrain.py`)
- **Source:** USGS 3DEP Bare Earth DEM (ImageServer exportImage plus the EPQS point service), NAVD88, metres. Cached rasters cover the demo district (~10 m display grid) and the study area (~60 m, including the Gila Mountains).
- **3D rendering** uses AWS Terrain Tiles, whose documented US source includes 3DEP.
- **Map controls:**
  - vertical exaggeration (1×/2×/3×/5×, labeled on the map; calculations always use true elevations);
  - hillshaded elevation colours with a legend;
  - contour lines;
  - click-to-sample elevation;
  - elevation profile along the first pass.
- **Per-field statistics:** the demo fields are genuinely flat (1.4–2.1 m relief, mean slope under 1°), and no relief is invented.
- **Acceptance check:** Prototype controls → "Fly to terrain check site (Gila Mountains)". A sampled raster value of 33.63 m matched EPQS at 33.64 m.

### Real-data pipeline — Experimental (`app/realdata.py`)
- **AZMET** Yuma Valley (az02), Yuma N.Gila (az14) and Yuma South (az36). Hourly observations come from the AZMET API. Location and sensor heights are parsed from each station's metadata page: temperature 1.5 m (Vaisala HMP60), wind 3.0 m (R. M. Young 03101/03301).
- **HRRR** via Herbie from the AWS archive:
  - `wrfsfc`: 2 m temperature, 10 m wind (rotated from grid-relative to earth-relative), surface height;
  - `wrfnat`: temperature and height on hybrid levels 1–10. Height above model ground = geopotential height − surface height.
- **NWS** hourly point forecast for the field.
- Data is subset to the study area and cached in `data/cache/` (not committed). Failures return explicit "unavailable"; the simulated demo is never substituted.
- **Fusion baseline (experimental):** HRRR 2 m plus an inverse-distance-weighted field of AZMET-minus-HRRR residuals. The 1.5 m vs 2 m height difference is a documented assumption. This is **not** kriging or regression kriging.
- **Data support panel**, at the selected field: contributing stations and model cell, distances, times, heights, resolution, status, assumptions, and whether a local paired sensor exists.
- **Validation (leave-one-station-out):** Nov 14, 2026 MST, every 2 h, HRRR analyses only (no future data), n = 33 station-hours.

  | Method | MAE °F | RMSE °F | Bias °F |
  |---|---|---|---|
  | Raw HRRR 2 m | 1.98 | 2.30 | +1.97 |
  | Nearest station | 0.89 | 1.22 | −0.13 |
  | IDW of stations | 0.97 | 1.29 | −0.05 |
  | Model + IDW residual | 0.98 | 1.28 | +0.03 |

  The correction removes HRRR's warm bias but does not beat the nearest station on this small sample. Three stations and one day establish nothing general, and surface-temperature skill says nothing about detecting shallow inversions.

### Other additions — Implemented
- **Night scene lighting:** Auto follows the scenario clock using the computed sun elevation for Yuma; Day and Night are manual. Night darkens the imagery and sky and adds tractor headlights. It is independent of the interface theme.
- **Spray liquid card:** product, carrier volume (not a dose), mix volume, tank loads, rain-free interval, and air-temperature range.
  - The temperature range is an optional, labeled product constraint, enforced every 15-minute slot.
  - Rain uses the rain-free interval after the last pass.
- **Proposed vs. accepted plan:** "Accept this plan" records who accepted it, and the Schedule page shows when the proposal has changed since acceptance.
- **Compare other equipment:** the rig options sit in a collapsed section under the recommendation.

### "Whether the Weather?" additions — Implemented (`app/engine.py`, `app/store.py`, `app/scheduler.py`)
- **One versioned decision.** Every assessment has a deterministic `decision_id` (a hash of the reading, time, field, product, thresholds, observations and rule version `cg-rules-0.4.0`).
  - The same ID appears in the status panel, the map HUD, the explanation, the monitoring result and the snapshot record.
  - Each scheduled job carries the decision ID at its planned start, matching what the status panel shows for that time. Both are covered by tests.
- **Persistence (prototype rules, editable thresholds).**
  - One clean reading after an inversion gives Caution, not Go. An inversion is treated as cleared only after 2 consecutive readings without it, and the scheduler applies the same rule to windows.
  - An active alert clears only after 2 consecutive non-critical monitoring checks. Any critical check resets the count, and new escalations are immediate.
  - Sunrise or an improved forecast never clears a measured inversion.
- **Developing or dissipating.**
  - Successive paired readings over 60 min are classified as strengthening, weakening, developing, mixing or uncertain. A change within the combined sensor uncertainty is "uncertain".
  - The lower-height wind trend is reported alongside.
  - A weakening trend does not clear the warning.
- **Field observations.**
  - Observers can record dust hanging, smoke layering, fog, dew, frost, cloud cover and local wind variability, plus observer, location, time and notes.
  - Every item starts as *not checked*.
  - Signs of stable air add a non-blocking Caution for 60 min. "No" or "not checked" never clears a flag.
  - Each observation is written to Records.
- **Height references.** The status panel lists every level's height above its installed reference, above ground, and above sea level (from the 3DEP field-mean elevation).
  - Levels shown: sensors, release height and canopy top.
  - It states that observed coverage is only between the installed sensors.
- **Rain and surface concerns, separate from drift.** Each scheduled job lists five concerns: airborne drift (checked every slot), rainfastness (product rain-free interval), runoff, dew or leaf wetness, and rain or irrigation for activation. Unknown product information stays *Unknown*.
- **Pre-application checks.** Each scheduled job has five checks:
  - fresh paired readings within 20 min;
  - wind direction toward sensitive areas;
  - an optional field observation;
  - re-reading the label;
  - re-checking the forecast.
- **Nozzles.** The TeeJet TTI table (product page, Catalog 52, saved with provenance in `app/data/teejet_tti.json`) joins XR and AIXR.
  - Prototype ranking: fully documented first, then no failed checks, then the least extra coarseness above the requirement (coarser is not assumed better), then pressure margin.
  - Release height is checked against TeeJet's documented 20 in for 110° tips at 20 in spacing.

### Scenario library — Implemented, simulated (`app/scenario.py`)

Adapted from the backend-implementation branch's scenario set. Switch under **Prototype controls → Simulation → Scenario**, or `POST /api/scenario/select {"id": ...}` (`GET /api/scenarios` lists them). Switching restores requests, alerts and thresholds, moves the clock to the scenario's start, recalculates the plan, and is logged to Records.

| ID | Starts | What it shows | Field A (mast S1) at start |
|---|---|---|---|
| `yuma-dawn-inversion` (default) | 05:30 | Inversion blind spot: 30 ft is +3.9 °F warmer than 5 ft, 5 ft wind inside the window | Stop; a single low station says Go |
| `katabatic-shear` | 05:30 | Cold drainage from the NW at 5 ft (~5 mph) under a 12-13 mph SW flow at 30 ft; no inversion | Caution for speed and direction shear; a single low station says Go |
| `evening-onset` | 17:00 | Mixed air and wind in the window now; an inversion forms after sunset | Go now; the ML outlook warns "likely to turn bad by 19:00" |
| `well-mixed` | 05:30 | Steady 5-8 mph breeze, upper air cooler all day | Go: the tool does not always say Stop |

Shear is visible only on mast S1, which has wind at both heights; S2 has one anemometer. All four scenarios are simulated keyframes, not recorded weather. Tests check each scenario's stated status at its start time.

### Product risk factors — Implemented, fictional products (`app/catalog.py`, `app/engine.py`)

Adapted from the backend-implementation branch's product taxonomy (systemic vs contact, category), plus volatility (a challenge stretch goal). Each fictional product now carries **category**, **mode of action**, **volatility** (low / moderate / high) and **off-target hazard**, each with its source. These properties only **tighten** the weather checks; a test confirms a volatile or high-hazard product is never less restrictive than a low-volatility one.

| Product (fictional) | Type | Volatility | Off-target hazard |
|---|---|---|---|
| Demo Insecticide R | Insecticide · contact | Low | Moderate |
| Demo Herbicide H | Herbicide · systemic | Moderate | High |
| Demo Growth-Regulator Herbicide G (new) | Herbicide · systemic | High | High |
| Operator product | Not entered | Not entered (Caution: adjustments not applied) | Not entered |

Rules (prototype assumptions; the temperature limits are adjustable thresholds in Prototype controls, and the label always wins):
- **Heat and volatility:** high volatility gives Caution from 80 °F and Stop from 90 °F air temperature at the lower sensor; moderate gives Caution from 90 °F. Volatility rises with temperature (EPA, *Reducing Pesticide Drift*).
- **Weak inversion:** with a moderate or high-volatility product, a possible inversion inside sensor uncertainty is raised from Caution to Stop, because vapor can stay in a stable layer and move after application.
- **Inversion developing:** with a volatile product, a developing or strengthening inversion trend adds Caution: spraying should finish well before the inversion forms.
- **Sensitive crops:** with a high off-target-hazard product, air moving toward a nearby sensitive crop is raised from Caution to Stop.

The scheduler uses the same checks, so the selected product changes the planned windows. Pick a product in **Schedule → request editor** (the list shows volatility). The field panel's *Spray liquid* card shows the product's type, volatility, hazard and the adjustments that apply. Example: in the *Warning before conditions turn bad* scenario at 18:00, Field A is Caution with Insecticide R (+0.3 °F, inside uncertainty) but Stop with Herbicide G. The November scenarios stay below 80 °F, so the heat rules are visible only by lowering the threshold or in tests.

### Calibrated ML drift-flag forecaster — Implemented, trained on simulated data (`app/forecast.py`)

Adapted from the backend-implementation branch's HistGradientBoosting forecaster, rebuilt so every skill number is measured rather than asserted.

- **Predicts** the probability that a Stop-level drift flag (inversion beyond combined sensor uncertainty, or lower wind outside the configured window, i.e. the engine's own thresholds) is present 1-12 h ahead at a paired-height mast.
- **Features** known at issue time only: current and 1-h-old ΔT and lower wind, upper-minus-lower wind (missing allowed), hour of day, lead time, target hour, flag now. A test confirms future scenario readings cannot change a forecast.
- **Training data:** a stochastic paired-height weather generator (per-day inversion strength, burn-off and onset times, daytime lapse, night wind, afternoon wind peak, AR(1) noise, gust bursts, sensor noise). 300 training days, 60 calibration days, 60 held-out test days. Trains in about 2 s at startup.
- **Model:** `HistGradientBoostingClassifier` + isotonic calibration on the calibration days.
- **Held-out skill:** Brier 0.144 vs 0.219 for conditional persistence and 0.182 for hourly climatology (34% and 21% better); mean calibration error about 1.6 percentage points. The reliability table is shown in the UI.
- **UI:** Today → "Drift-flag outlook": hourly bars per field, the next likely low-risk window, and a "turning bad within 3 h" warning. Each issued outlook is logged to Records (`forecast`).
- **API:** `GET /api/forecast?field_id=A[&time=...]`, `GET /api/forecast/model`.
- **Limits:** advisory only; it never changes the current Go/Caution/Stop status. Skill on real masts is unknown until validated on observed data. It does not know about products, neighbors or rain.

### Final checklist

| State | Items |
|---|---|
| **Implemented and tested** (63 automated tests plus a desktop and mobile browser check) | Paired-height inversion check with combined uncertainty; Go / Caution / Stop / Insufficient data, with stale or missing data never Go; 3–10 mph wind window; circular direction differences; speed and direction shear; neighbor attention checks; installed-height metadata and reference surfaces; versioned decision ID shared across screens; inversion persistence; alert-clearance persistence; trend classification; field observations (caution only); scheduler over all job orders with travel, setup, refills, shift, deadline, rain-free interval and persistence; rain and surface concerns kept separate; pre-application checks; nozzle sizing from TeeJet XR, AIXR and TTI tables; drone kept distinct from TeeJet nozzles; release-height interpolation (PCHIP, no extrapolation) and FAO-56 wind estimate; spray-plane ΔT; 3DEP terrain stats, profile and 3D relief; CSV records; EN/ES explanations |
| **Simulated** (labeled in the interface) | Sensor masts S1 and S2 and every local reading; the rain-probability forecast; fields, growers, neighbors and jobs; the demo products and their constraints; equipment costs; critical-change injection |
| **Awaiting data** | Real paired-height sensor feed; product label values (wind, temperature, rain-free, runoff, leaf wetness, activation, droplet class); manufacturer sensor accuracy and averaging; rainfall amount and intensity; leaf-wetness sensor; operator-verified sensor installation heights |
| **Experimental** (real data, not validated for decisions) | HRRR plus AZMET fusion with IDW residual correction (leave-one-out MAE 0.98 °F vs nearest station 0.89 °F, n = 33); HRRR native-level profile analysis; NWS hourly |
| **Deferred** | Kriging; PWM modelling; airblast airflow modelling; NBM, GOES, satellite and soil products; Synoptic/MesoWest and IEM; seeding from the lettuce report (attachment not available) |

### Deferred
- Geostatistical kriging (three stations cannot support a variogram).
- NBM, GOES, CDL, NLCD, Sentinel-2, Landsat, SMAP, SSURGO, ERA5, IGRA, CASES-99, BLLAST and MATERHORN.
- Synoptic/MesoWest and IEM.
- PWM modelling.
- Airblast airflow modelling.
- Seeding products from the lettuce report: that attachment was not available in this session.

## Three-minute demo script

1. **(0:00) Today.** "Four requests came in from the PCA and the spray program. Broccoli Field B must be done by 10:00." Point to the next proposed job (Field B, 06:15) and the line saying the request order would leave B unscheduled. In the side column, the **Drift-flag outlook** shows Field A's inversion likely persisting until about 08:30 and a likely window from 09:30; open *How good is this forecast?* for the held-out Brier scores against persistence and climatology.
2. **(0:30) Blind spot.** Under *Fields needing attention*, Field A shows Stop with "A 5 ft station alone would say Go." Click **Open map**, select Field A. The right panel shows *5 ft station only: Go* vs *Paired 5 ft + 30 ft: Stop*. The cross-section shows 30 ft is +3.9 °F warmer: an inversion lid.
3. **(1:00) Neighbors and wind.** Wind arrows point where air moves *to*. Air is moving south toward the fictional organic block (N1), which has a user-entered hold constraint. Show the Neighbors explanation, and note it is an attention check, not an exposure prediction.
4. **(1:30) Equipment.** In Setup, switch to **Agricultural spray drone**. A blocking conflict appears: the product's ASABE Medium-or-coarser requirement can't be verified from a µm atomizer setting. Switch back to the boom; the weather Stop is still there because equipment can't clear an inversion. Open *Compare nozzles*: candidates come from the TeeJet XR, AIXR and TTI tables with their sources, ranked by the stated prototype rule.
5. **(2:00) Reorder.** Open **Schedule**. Request order A → B → C leaves B unscheduled. Proposed B → A → C runs B at 06:15, then A after its inversion breaks (08:45–09:40), and C moves to tomorrow. Its blue bar is the 4 h rain-free interval that would overlap the simulated 15:00 showers today. Click **Why this order?** and toggle **ES**.
6. **(2:30) Monitoring and record.** On the map with Field A, open **Prototype controls → Simulation**, press **Simulate critical change** (it places a 13.5 mph wind surge inside Field A's planned 08:45–09:40 application and starts the replay; if the replay is already playing, the surge arrives 15 min after the replay time). The vehicle pauses, the active pass turns red, and one grouped alert appears. Enter a name and **Acknowledge**. After conditions improve, the alert stays active for one clean check and clears on the second. Record a field observation (e.g. dust hanging) in the status panel: it adds Caution and never clears a flag. Open **Schedule → Before each planned job** for the decision ID, rain and surface concerns, and pre-application checks. Open **Records**: the alert, acknowledgement, schedule revisions, rule version and *Simulated* flag are there. **Export CSV**.
7. **(If time) Other scenarios.** In **Prototype controls → Simulation → Scenario**, pick *Wind shear between heights*: Field A turns Caution for 5 ft vs 30 ft speed and direction differences while a single low station still says Go. Pick *Warning before conditions turn bad* (17:00): status is Go now, but the outlook warns an inversion is likely by 19:00.

## Sources and assumptions

| Item | Status |
|---|---|
| 3–10 mph wind window | Challenge default (labeled as such) |
| Upper-warmer-than-lower inversion flag, two-height measurement | Challenge requirement; concept per UC ANR *Surface inversions cause spray drift* |
| Sensor accuracy ±0.5 °F, shear thresholds (5 mph, 45°), calm threshold (2 mph), stale after 20 min, 45° downwind cone, 400 m attention radius, 40 % rain-probability threshold, 1.5 km sensor coverage | **Prototype assumptions, unsourced**. Labeled in the UI; configurable through `POST /api/settings/thresholds` |
| Broadcast calibration `gpm = GPA × mph × spacing / 5940`, tip code "04" = 0.4 gpm at 40 psi | Standard calibration convention; UI says to confirm against the manufacturer chart |
| TeeJet XR / AIXR / TTI, hollow cone, DJI AGRAS T50 atomizer | Listed with source links. **Pressure ranges, droplet tables and DJI specifications were not verified during this build.** Automated fetches of the manufacturer and extension pages failed, so those fields are `null` and the UI says "not verified." Droplet class is operator-entered from the manufacturer chart. |
| Drone configuration (40 L tank, 16 L/min, 9 m swath, etc.) | Demo operator inputs, **not** manufacturer-verified. Labeled "check ag.dji.com/t50" |
| Demo Insecticide R / Demo Herbicide H constraints (wind limit, droplet class, 4 h / 6 h rain-free, buffer) | **Fictional demo assumptions**. Replace with the actual product label |
| Products with no entered constraints | Shown as unknown; the rain check is reported as incomplete |
| Equipment illustrations | Generic drawings, not manufacturer photos |
| Basemap / terrain | Esri World Imagery, CARTO/OSM streets, AWS Terrain Tiles (terrarium DEM) at 1× exaggeration. Yuma Valley is nearly flat; no relief is invented. |
| Regional context | Open-Meteo forecast model at its native heights (temperature 2 m / 80 m, wind 10 m / 80 m). Labeled *model estimate*, never used for Go/Stop, and never shown as 5 ft / 30 ft. Failures return an explicit unavailable/stale state with retrieval time kept separate from source time. |
| AZMET and NWS APIs | **Not integrated.** AZMET station data is regional context at station height, not paired-height above a field. |

## Blueprint (CanopyGuard Pro) reuse report

**Reused:**
- the FastAPI app with an assessment endpoint;
- the paired-reading schema idea (lower/upper temperature, wind, direction);
- `angle_diff` circular direction difference;
- the ground-only vs multi-height comparison and "blind spot" concept;
- scripted scenario pattern (Yuma dawn inversion), later extended into a scenario library with the katabatic-shear and clean-window cases;
- SQLite logging with CSV export;
- Yuma-area setting;
- 20/40/60/80-acre parcel sizes.

**Corrected:**
- The hardcoded "38.4 % Brier improvement" and calibrated-probability claims were removed. The timeline is a labeled simulated scenario. A trained forecaster was later added with measured, held-out skill (`app/forecast.py`).
- `calculate_drift_distance` and the drift cone with its "EPA AgDRIFT" attribution were removed. No plume, drift distance or "protected" claim is drawn.
- Open-Meteo 2 m/80 m and 10 m/80 m values are no longer presented as 5 ft/30 ft tower readings. The required paired-height data comes from separately labeled simulated masts.
- Fabricated offline fallbacks and default values were replaced with explicit unavailable/stale/insufficient states.
- Radiant/Prefar temperature limits, buffers and nozzle mandates were replaced with fictional, labeled demo products. Unknown constraints stay unknown.
- Nozzle logic is now model- and family-specific, and drone atomizers are kept separate from tractor nozzles.
- "Official EPA Compliance Verdict," "EPA Log," "full regulatory compliance" and "immutable" wording became decision-support language. Records are stated to be not tamper-proof.
- The hardcoded neighboring-field name was replaced with geometry-based checks against labeled fictional areas.
- Hardcoded `127.0.0.1` frontend URLs became same-origin routes.
- Every reading carries its own observation timestamp, and staleness is evaluated against the viewed time. The scenario date is anchored to the server's Arizona date at startup, so restart the server on a new day.

**Omitted:**
- the HistGradientBoosting forecaster as written (hardcoded skill figure, no calibration); it was rebuilt in `app/forecast.py`;
- ntfy.sh push notifications;
- Pydantic response models (plain dicts are returned);

## Not implemented or not validated

- **No field validation.** Durations, travel times and thresholds are planning estimates from operator inputs and prototype assumptions.
- **Not verified:** manufacturer nozzle droplet tables and DJI T50 specifications (see above). No nozzle is recommended for that reason.
- No AZMET or NWS integration. No real sensor ingestion: the paired-height data is simulated.
- The ML drift-flag forecaster is trained and scored on simulated weather only. Its skill on real masts is unknown until it is validated against observed paired-height data.
- The optional Claude explanation path was not run (no credentials). Spanish UI covers explanations, status labels and a few headings, not every label.
- Not built: aircraft planning and chemigation (shown as unsupported), and airblast canopy/airflow modeling (links to the UC Airblast Spray Advisor).
- Records are append-only in the app's code paths, but SQLite itself is not tamper-proof.
- Jobs longer than one crew shift can't be split.
- Each job uses one equipment unit, and units work in parallel only across different unit IDs.
- Temperature interpolation uses two sensors and inverse-distance weighting. It is labeled interpolated, and areas beyond 1.2 km are left blank.
- Verified in headless Chromium at 1440×900 and 390×844. Not tested on physical phones, Safari or Firefox.
