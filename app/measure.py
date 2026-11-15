"""Measurement model: every weather value carries its own metadata.

A measurement is a dict with: variable, value, unit, source, source_id, lat, lon,
height_m, height_ref (ground | canopy | spray_surface | model_ground | msl),
status (observed | forecast | estimated | simulated | operator_entered | missing),
observed_at / valid_time / init_time / lead_h / retrieved_at, averaging, uncertainty,
instrument, missing_reason.

Height configurations are kept distinct; they are never treated as equivalent."""
from datetime import datetime

FT = 0.3048

# Documented temperature-pair configurations
CONFIGS = {
    "near_surface": {
        "name": "Near-spray-surface pair",
        "lower_ft": (0.5, 1.0), "upper_ft": (8.0, 10.0), "ref": "spray_surface", "refs": ("spray_surface", "canopy", "ground"),
        "source": "NDSU AE-1705 (2019): lower 6-12 in above the soil or a closed canopy, upper 8-10 ft above the surface to be sprayed",
        "url": "https://www.ndsu.edu/agriculture/sites/default/files/2023-12/AE-1705-%20Air%20Temp%20Inversions2019.pdf",
    },
    "challenge_tower": {
        "name": "Challenge tower example",
        "lower_ft": (5.0, 5.0), "upper_ft": (30.0, 30.0), "ref": "ground", "refs": ("ground",),
        "source": "Hack Arizona AgX challenge example (5 ft and 30 ft above ground)",
        "url": None,
    },
    "model_profile": {
        "name": "Model vertical profile",
        "lower_ft": None, "upper_ft": None, "ref": "model_ground",
        "source": "Model native levels at their documented heights", "url": "https://www.nco.ncep.noaa.gov/pmb/products/hrrr/",
    },
}


def classify_pair(lower_ft, upper_ft, ref):
    """Which documented configuration a temperature pair matches, if any."""
    for key, c in CONFIGS.items():
        if not c["lower_ft"] or ref not in c.get("refs", (c["ref"],)):
            continue
        lo, hi = c["lower_ft"], c["upper_ft"]
        if lo[0] - 1e-6 <= lower_ft <= lo[1] + 1e-6 and hi[0] - 1e-6 <= upper_ft <= hi[1] + 1e-6:
            return key
    return "other"


def m(variable, value, unit, *, source, status, height_ft=None, height_ref=None, observed_at=None, valid_time=None,
      init_time=None, lead_h=None, retrieved_at=None, averaging=None, uncertainty=None, instrument=None,
      lat=None, lon=None, source_id=None, missing_reason=None):
    if value is None and not missing_reason:
        missing_reason = "No value"
    return {"variable": variable, "value": value, "unit": unit, "source": source, "source_id": source_id,
            "lat": lat, "lon": lon, "height_ft": height_ft, "height_m": round(height_ft * FT, 3) if height_ft is not None else None,
            "height_ref": height_ref, "status": "missing" if value is None else status,
            "observed_at": observed_at, "valid_time": valid_time, "init_time": init_time, "lead_h": lead_h,
            "retrieved_at": retrieved_at, "averaging": averaging, "uncertainty": uncertainty, "instrument": instrument,
            "missing_reason": missing_reason}


def fmt_height(h_ft, ref):
    if h_ft is None:
        return "height not documented"
    txt = f"{h_ft * 12:.0f} in" if h_ft < 2 else f"{h_ft:g} ft"
    return f"{txt} above {ref.replace('_', ' ')}" if ref else txt


def age_min(at: datetime, iso):
    return None if not iso else (at - datetime.fromisoformat(iso)).total_seconds() / 60


# --------------------------------------------------------------------------
# Requirements register: which decisions need each metric, and what happens
# when it is unavailable. "essential" metrics block the affected decision;
# "optional" ones only reduce context.
REQUIREMENTS = [
    # weather
    {"metric": "Air temperature at two heights (same mast, aligned in time)", "group": "Weather", "essential": True,
     "decisions": ["Inversion check", "Go/Stop status", "Schedule windows"],
     "if_missing": "Status is Insufficient data; the slot is not schedulable."},
    {"metric": "Installed sensor heights and reference surface", "group": "Weather", "essential": True,
     "decisions": ["Inversion check", "Configuration label"],
     "if_missing": "The pair cannot be interpreted; treated as insufficient data."},
    {"metric": "Wind speed (sustained, with averaging interval)", "group": "Weather", "essential": True,
     "decisions": ["Wind window", "Product wind limit", "Schedule windows"],
     "if_missing": "Status is Insufficient data."},
    {"metric": "Wind direction (from)", "group": "Weather", "essential": True,
     "decisions": ["Sensitive-area attention", "User hold constraints"],
     "if_missing": "Status is Insufficient data (sensitive-area checks cannot run)."},
    {"metric": "Wind speed and direction at a second height", "group": "Weather", "essential": False,
     "decisions": ["Speed/direction change with height"],
     "if_missing": "Shear checks are reported as not assessable; other checks continue."},
    {"metric": "Gust value and gust interval", "group": "Weather", "essential": False,
     "decisions": ["Context only (gusts are not sustained wind)"], "if_missing": "Shown as unavailable."},
    {"metric": "Temperature trend (3+ recent paired observations)", "group": "Weather", "essential": False,
     "decisions": ["Context: inversion forming or breaking"], "if_missing": "Trend not shown."},
    {"metric": "Relative humidity", "group": "Weather", "essential": False, "decisions": ["Context"], "if_missing": "Shown as unavailable."},
    {"metric": "Rain forecast probability and timing", "group": "Weather", "essential": True,
     "decisions": ["Rain-free interval after last pass (when the product has one)"],
     "if_missing": "Rain check is reported incomplete; a window is not shown as rain-cleared."},
    {"metric": "Solar radiation / daylight", "group": "Weather", "essential": False, "decisions": ["Context; night scene lighting"],
     "if_missing": "Sunrise/sunset is computed from date and location."},
    {"metric": "Sensor accuracy, calibration, shielding", "group": "Weather", "essential": False,
     "decisions": ["Inversion uncertainty band"], "if_missing": "Prototype default accuracy is used and labeled."},
    # field
    {"metric": "Field boundary and calculated area", "group": "Field", "essential": True,
     "decisions": ["Passes, duration, volume"], "if_missing": "Job cannot be estimated or scheduled."},
    {"metric": "Crop and canopy height", "group": "Field", "essential": False,
     "decisions": ["Reference surface for near-surface sensors", "Equipment compatibility"], "if_missing": "Canopy reference unavailable; ground reference used and labeled."},
    {"metric": "Terrain elevation and slope (3DEP)", "group": "Field", "essential": False,
     "decisions": ["Context, profile, 3D view"], "if_missing": "Terrain shown as unavailable; no relief is invented."},
    {"metric": "Nearby sensitive areas and exclusions", "group": "Field", "essential": False,
     "decisions": ["Attention checks, user holds, excluded acres"], "if_missing": "No neighbor checks; stated in the panel."},
    {"metric": "Treatment deadline and earliest start", "group": "Field", "essential": True,
     "decisions": ["Scheduling"], "if_missing": "Request cannot be saved."},
    # application
    {"metric": "Equipment and spray-system model", "group": "Application", "essential": True,
     "decisions": ["Compatibility, duration, nozzle candidates"], "if_missing": "No equipment recommendation."},
    {"metric": "Carrier volume (GPA or L/ha, not dose)", "group": "Application", "essential": True,
     "decisions": ["Required flow, refills, nozzle size"], "if_missing": "Nozzle candidates blocked: required flow unknown."},
    {"metric": "Ground speed", "group": "Application", "essential": True,
     "decisions": ["Required flow, duration"], "if_missing": "Nozzle candidates and duration blocked."},
    {"metric": "Nozzle spacing or calibrated swath", "group": "Application", "essential": True,
     "decisions": ["Required flow per nozzle, passes"], "if_missing": "Nozzle candidates blocked."},
    {"metric": "Operating pressure limits (pump/controller)", "group": "Application", "essential": False,
     "decisions": ["Nozzle feasibility"], "if_missing": "Only the manufacturer's documented range is applied."},
    {"metric": "Release height", "group": "Application", "essential": False,
     "decisions": ["Context; vehicle display height"], "if_missing": "Shown as unavailable."},
    {"metric": "Product droplet-class requirement (verified or operator-entered)", "group": "Application", "essential": False,
     "decisions": ["Nozzle candidate check"], "if_missing": "Droplet check reported as missing; no nozzle is called compliant."},
    {"metric": "Product rain-free interval", "group": "Application", "essential": False,
     "decisions": ["Rain check after last pass"], "if_missing": "Rain check incomplete (stated on the schedule)."},
    {"metric": "Previous paired reading (15 min earlier)", "group": "Weather", "essential": False,
     "decisions": ["Inversion persistence: 2 consecutive clean readings before an inversion is treated as cleared"],
     "if_missing": "Persistence cannot be confirmed; only the current reading is used."},
    {"metric": "Successive paired readings (3 or more in 60 min)", "group": "Weather", "essential": False,
     "decisions": ["Trend class: strengthening / weakening / developing / mixing / uncertain"],
     "if_missing": "Trend shown as uncertain. A weakening trend never clears a warning."},
    {"metric": "Field observations (dust, smoke, fog, dew, frost, cloud, local wind)", "group": "Field", "essential": False,
     "decisions": ["Supporting caution only"], "if_missing": "Nothing is assumed. 'No' or 'not checked' never establishes safe conditions."},
    {"metric": "Product runoff, leaf-wetness and activation instructions", "group": "Application", "essential": False,
     "decisions": ["Rain and surface concerns, listed separately from drift"], "if_missing": "Shown as Unknown on the schedule."},
]
