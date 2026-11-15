"""Rule configuration. Every threshold carries its source so the UI can show
whether it is a challenge default, a product entry, or a prototype assumption."""
from datetime import timezone, timedelta

RULE_VERSION = "cg-rules-0.3.0"
# Arizona does not observe DST, so a fixed UTC-7 offset is correct year-round.
MST = timezone(timedelta(hours=-7), "MST")
SLOT_MIN = 15  # scenario + scheduling resolution, minutes

CHALLENGE = "Hack Arizona AgX challenge default"
PROTOTYPE = "Prototype assumption (unsourced, adjustable)"

DEFAULT_THRESHOLDS = {
    "wind_min_mph": {"value": 3.0, "source": CHALLENGE},
    "wind_max_mph": {"value": 10.0, "source": CHALLENGE},
    "sensor_temp_accuracy_f": {"value": 0.5, "source": PROTOTYPE + " - per-sensor accuracy; replace with sensor spec"},
    "speed_shear_caution_mph": {"value": 5.0, "source": PROTOTYPE},
    "dir_shear_caution_deg": {"value": 45.0, "source": PROTOTYPE},
    "calm_direction_mph": {"value": 2.0, "source": PROTOTYPE + " - below this, direction comparisons are unreliable"},
    "stale_after_min": {"value": 20.0, "source": PROTOTYPE},
    "downwind_cone_deg": {"value": 45.0, "source": PROTOTYPE + " - half-angle for 'air moving toward' attention check"},
    "attention_radius_m": {"value": 400.0, "source": PROTOTYPE + " - attention radius, NOT a safe distance"},
    "rain_prob_block_pct": {"value": 40.0, "source": PROTOTYPE + " - forecast probability treated as conflicting with a rain-free interval"},
    "sensor_coverage_m": {"value": 1500.0, "source": PROTOTYPE + " - max distance for a field to use a paired-height sensor"},
}


def thresholds(overrides: dict | None = None) -> dict:
    t = {k: v["value"] for k, v in DEFAULT_THRESHOLDS.items()}
    for k, v in (overrides or {}).items():
        if k in t and v is not None:
            t[k] = float(v)
    return t
