# CanopyGuard

Spray-window planning for farmers and Pest Control Advisers (PCAs). Treatment has already been decided by pest scouting or a spray schedule. CanopyGuard answers: **given the target date, available equipment, local weather and neighboring fields, what is the earliest suitable opportunity to complete this job?**

It is decision support only. It does not diagnose pests, choose pesticides, recommend rates, predict exposure or drift distance, guarantee zero drift, or control equipment. **Go means no configured flags were detected, not guaranteed safety.**

Hack Arizona AgX prototype. All fields, growers, sensors, neighbors, readings and product constraints in the demo are **fictional or simulated** and are labeled that way in the UI.

## Run it

Requires Python 3.11+.

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt        # Windows (use .venv/bin/pip on macOS/Linux)
.venv/Scripts/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://127.0.0.1:8000. For a phone on the same network, open `http://<your-computer-LAN-IP>:8000`. The frontend uses same-origin `/api` routes, so no URL changes are needed. Allow port 8000 through the firewall if the phone can't connect.

- Data is stored in `data/canopyguard.db` (SQLite). Set `CANOPYGUARD_DB` to change it.
- **Replay demo** on the Today page resets requests, alerts and scenario events.
- MapLibre is vendored in `web/vendor`. Fonts, basemap tiles and terrain load from the internet. Offline, the map still draws the fictional overlays on a plain background. If WebGL is unavailable, a 2D SVG schematic is used.

Tests: `.venv/Scripts/python -m pytest -q` (38 tests).

Optional AI-phrased explanations: `pip install anthropic`, configure Anthropic credentials (e.g. `ANTHROPIC_API_KEY`), then set `CANOPYGUARD_AI=1`. Claude (`claude-opus-5-5`, server-side refusal fallback enabled) only rephrases the rule-based engine lines it is given. Any failure or refusal falls back to the rule-based text. The key stays on the server. **This path was not exercised during the build** (no credentials were configured); the rule-based path is what the demo uses and what was tested.

## What it does

| Area | Contents |
|---|---|
| **Today** | Next proposed job with depart/travel/setup times, deadlines and conflicts, unscheduled jobs with the reason, fields needing attention (including "ground-only would say Go" blind spots), treatment requests, and candidate weather windows for today and tomorrow. |
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

## Three-minute demo script

1. **(0:00) Today.** "Four requests came in from the PCA and the spray program. Broccoli Field B must be done by 10:00." Point to the next proposed job (Field B, 06:15) and the line saying the request order would leave B unscheduled.
2. **(0:30) Blind spot.** Under *Fields needing attention*, Field A shows Stop with "A 5 ft station alone would say Go." Click **Open map**, select Field A. The right panel shows *5 ft station only: Go* vs *Paired 5 ft + 30 ft: Stop*. The cross-section shows 30 ft is +3.9 °F warmer: an inversion lid.
3. **(1:00) Neighbors and wind.** Wind arrows point where air moves *to*. Air is moving south toward the fictional organic block (N1), which has a user-entered hold constraint. Show the Neighbors explanation, and note it is an attention check, not an exposure prediction.
4. **(1:30) Equipment.** In Setup, switch to **Agricultural spray drone**. A blocking conflict appears: the product's ASABE Medium-or-coarser requirement can't be verified from a µm atomizer setting. Switch back to the boom; the weather Stop is still there because equipment can't clear an inversion. Open *Compare nozzles*: no recommendation, because verified droplet charts aren't loaded.
5. **(2:00) Reorder.** Open **Schedule**. Request order A → B → C leaves B unscheduled. Proposed B → A → C runs B at 06:15, then A after its inversion breaks (08:45–09:40), and C moves to tomorrow. Its blue bar is the 4 h rain-free interval that would overlap the simulated 15:00 showers today. Click **Why this order?** and toggle **ES**.
6. **(2:30) Monitoring and record.** On the map with Field A, open **Prototype controls → Simulation**, press **Play**, then **Simulate critical change**. The vehicle pauses, the active pass turns red, and one grouped alert appears. Enter a name and **Acknowledge**. Open **Records**: the alert, acknowledgement, schedule revisions, rule version and *Simulated* flag are there. **Export CSV**.

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
- scripted scenario pattern (Yuma dawn inversion);
- SQLite logging with CSV export;
- Yuma-area setting;
- 20/40/60/80-acre parcel sizes.

**Corrected:**
- The hardcoded "38.4 % Brier improvement" and calibrated-probability claims were removed. The timeline is a labeled simulated scenario; there is no trained model.
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
- the HistGradientBoosting forecaster;
- ntfy.sh push notifications;
- Pydantic response models (plain dicts are returned);
- the Marana katabatic scenario.

## Not implemented or not validated

- **No field validation.** Durations, travel times and thresholds are planning estimates from operator inputs and prototype assumptions.
- **Not verified:** manufacturer nozzle droplet tables and DJI T50 specifications (see above). No nozzle is recommended for that reason.
- No AZMET or NWS integration. No real sensor ingestion: the paired-height data is simulated.
- The optional Claude explanation path was not run (no credentials). Spanish UI covers explanations, status labels and a few headings, not every label.
- Not built: aircraft planning and chemigation (shown as unsupported), and airblast canopy/airflow modeling (links to the UC Airblast Spray Advisor).
- Records are append-only in the app's code paths, but SQLite itself is not tamper-proof.
- Jobs longer than one crew shift can't be split.
- Each job uses one equipment unit, and units work in parallel only across different unit IDs.
- Temperature interpolation uses two sensors and inverse-distance weighting. It is labeled interpolated, and areas beyond 1.2 km are left blank.
- Verified in headless Chromium at 1440×900 and 390×844. Not tested on physical phones, Safari or Firefox.
