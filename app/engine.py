"""Deterministic multi-height weather assessment.

Status meanings:
  GO                - no configured flag detected. NOT a guarantee of safety.
  CAUTION           - a non-blocking flag needs judgement.
  STOP              - a blocking flag is present.
  INSUFFICIENT_DATA - required readings are missing, stale or invalid; never Go.
"""
import math
from datetime import datetime
from app.config import RULE_VERSION, DEFAULT_THRESHOLDS, thresholds as _thr
from app.geo import angle_diff, bearing, centroid, poly_distance

GO, CAUTION, STOP, INSUFFICIENT = "GO", "CAUTION", "STOP", "INSUFFICIENT_DATA"
RANK = {GO: 0, CAUTION: 1, INSUFFICIENT: 2, STOP: 3}
LIMITS = {"temp_f": (-40, 140), "wind_mph": (0, 120), "dir_from_deg": (0, 360)}


def worst(*statuses):
    return max(statuses, key=lambda s: RANK[s]) if statuses else GO


def _src(key):
    return DEFAULT_THRESHOLDS[key]["source"]


def _check(id_, label, status, measured, threshold, source, reason, blocking=None):
    return {"id": id_, "label": label, "status": status, "measured": measured, "threshold": threshold,
            "threshold_source": source, "reason": reason,
            "blocking": blocking if blocking is not None else status in (STOP, INSUFFICIENT)}


def validate(reading: dict | None, at: datetime, t: dict):
    """Return (problems, age_min). Problems make the result INSUFFICIENT_DATA."""
    if reading is None:
        return ["No paired-height reading is available for this field and time."], None
    problems = []
    obs = datetime.fromisoformat(reading["observed_at"])
    age = (at - obs).total_seconds() / 60
    if age > t["stale_after_min"]:
        problems.append(f"Reading is {age:.0f} min old (stale after {t['stale_after_min']:.0f} min).")
    if age < -1:
        problems.append("Reading timestamp is in the future relative to the evaluation time.")
    for lvl in ("lower", "upper"):
        r = reading[lvl]
        for k in ("temp_f", "wind_mph", "dir_from_deg"):
            v = r.get(k)
            name = f"{r['height_ft']} ft {k.split('_')[0]}"
            if v is None:
                problems.append(f"{name} reading missing" + (f" ({r['missing_reason']})" if r.get("missing_reason") else "") + ".")
            elif not isinstance(v, (int, float)) or math.isnan(v) or not (LIMITS[k][0] <= v <= LIMITS[k][1]):
                problems.append(f"{name} reading invalid ({v}).")
    return problems, age


def ground_only(reading: dict | None, t: dict) -> dict:
    """What a single 5 ft station would conclude (wind window only)."""
    if not reading or reading["lower"].get("wind_mph") is None:
        return {"status": INSUFFICIENT, "reason": "No 5 ft wind reading."}
    w = reading["lower"]["wind_mph"]
    if w < t["wind_min_mph"]:
        return {"status": STOP, "reason": f"5 ft wind {w:.1f} mph is below {t['wind_min_mph']:.0f} mph."}
    if w > t["wind_max_mph"]:
        return {"status": STOP, "reason": f"5 ft wind {w:.1f} mph is above {t['wind_max_mph']:.0f} mph."}
    return {"status": GO, "reason": f"5 ft wind {w:.1f} mph is inside the {t['wind_min_mph']:.0f}-{t['wind_max_mph']:.0f} mph window. A single height cannot see an inversion."}


def neighbors(field: dict, areas: list, reading: dict | None, t: dict, product: dict | None = None):
    """Geometry-based context for nearby sensitive areas. This is an attention
    check on wind direction and distance - not an exposure or deposition model."""
    out = []
    fc = centroid(field["poly"])
    for a in areas:
        dist, near = poly_distance(field["poly"], a["poly"])
        if dist > t["attention_radius_m"]:
            continue
        brg = bearing(fc, near)
        item = {"area_id": a["id"], "name": a["name"], "kind": a["kind"], "distance_m": round(dist),
                "distance_ft": round(dist * 3.281), "bearing_deg": round(brg),
                "constraint": a.get("constraint"), "downwind": {}, "attention": False, "blocking": False,
                "direction_reliable": True, "notes": []}
        if reading:
            for lvl in ("lower", "upper"):
                r = reading[lvl]
                if r.get("dir_from_deg") is None or r.get("wind_mph") is None:
                    item["downwind"][lvl] = None
                    continue
                toward = (r["dir_from_deg"] + 180) % 360
                calm = r["wind_mph"] < t["calm_direction_mph"]
                hit = angle_diff(toward, brg) <= t["downwind_cone_deg"]
                item["downwind"][lvl] = {"height_ft": r["height_ft"], "from_deg": r["dir_from_deg"], "toward_deg": toward,
                                         "toward_area": hit, "calm": calm}
                if calm:
                    item["direction_reliable"] = False
                if hit or calm:
                    item["attention"] = True
        if not item["direction_reliable"]:
            item["notes"].append("Wind is near calm, so direction is unreliable - treat every nearby area as needing attention.")
        c = a.get("constraint") or {}
        if c.get("type") == "hold_when_toward" and item["attention"]:
            item["blocking"] = True
            item["notes"].append(f"Constraint ({c.get('source')}): hold application while air moves toward this area.")
        if product:
            bufs = product["constraints"]["buffers"]["value"]
            for b in bufs or []:
                if b["kind"] == a["kind"]:
                    item["buffer_ft"] = b["ft"]
                    item["buffer_source"] = product["constraints"]["buffers"]["source"]
                    item["notes"].append(f"Product buffer {b['ft']} ft from {a['kind'].replace('_', ' ')} ({item['buffer_source']}).")
        out.append(item)
    out.sort(key=lambda i: (not i["blocking"], not i["attention"], i["distance_m"]))
    return out


def assess(reading: dict | None, at: datetime, field: dict | None = None, areas: list = (),
           product: dict | None = None, overrides: dict | None = None) -> dict:
    t = _thr(overrides)
    checks = []
    problems, age = validate(reading, at, t)
    metrics = {"delta_t_f": None, "delta_t_uncertainty_f": round(math.sqrt(2) * t["sensor_temp_accuracy_f"], 2),
               "speed_diff_mph": None, "dir_diff_deg": None, "dir_comparison_reliable": None, "age_min": age}

    if problems:
        checks.append(_check("data", "Required paired-height data", INSUFFICIENT, "; ".join(problems),
                             "Both heights: temperature, wind speed and direction, fresh and in range",
                             _src("stale_after_min"),
                             "Missing, stale or invalid readings cannot produce Go."))
    else:
        lo, up = reading["lower"], reading["upper"]
        dT = round(up["temp_f"] - lo["temp_f"], 1)
        u = metrics["delta_t_uncertainty_f"]
        metrics["delta_t_f"] = dT
        # 1. Inversion (upper warmer than lower)
        if dT > u:
            checks.append(_check("inversion", "Temperature inversion", STOP,
                                 f"30 ft is {dT:+.1f} °F vs 5 ft", f"> +{u:.1f} °F (outside measurement uncertainty)",
                                 _src("sensor_temp_accuracy_f"),
                                 f"Air at 30 ft is {dT:.1f} °F warmer than at 5 ft. That is an inversion: fine droplets can stay suspended and move with the stable layer."))
        elif dT > 0:
            checks.append(_check("inversion", "Temperature inversion", CAUTION,
                                 f"30 ft is {dT:+.1f} °F vs 5 ft", f"0 to +{u:.1f} °F is within uncertainty",
                                 _src("sensor_temp_accuracy_f"),
                                 f"Upper air reads slightly warmer ({dT:+.1f} °F) but within the ±{u:.1f} °F combined sensor uncertainty. Possible weak inversion - recheck before starting."))
        else:
            note = " Difference is within sensor uncertainty, so mixing may be weak." if dT >= -u else ""
            checks.append(_check("inversion", "Temperature inversion", GO,
                                 f"30 ft is {dT:+.1f} °F vs 5 ft", "Upper not warmer than lower",
                                 _src("sensor_temp_accuracy_f"), "No inversion flagged: upper air is not warmer than lower air." + note))
        # 2. Wind speed window at 5 ft (challenge defaults)
        w = lo["wind_mph"]
        if w < t["wind_min_mph"]:
            checks.append(_check("wind_low", "Wind speed (5 ft)", STOP, f"{w:.1f} mph", f">= {t['wind_min_mph']:.0f} mph",
                                 _src("wind_min_mph"), "Near-calm air: droplets can hang and direction is unpredictable."))
        elif w > t["wind_max_mph"]:
            checks.append(_check("wind_high", "Wind speed (5 ft)", STOP, f"{w:.1f} mph", f"<= {t['wind_max_mph']:.0f} mph",
                                 _src("wind_max_mph"), f"Wind {w:.1f} mph exceeds the {t['wind_max_mph']:.0f} mph limit."))
        else:
            checks.append(_check("wind", "Wind speed (5 ft)", GO, f"{w:.1f} mph",
                                 f"{t['wind_min_mph']:.0f}-{t['wind_max_mph']:.0f} mph", _src("wind_max_mph"),
                                 "Wind is inside the configured window."))
        # 2b. Product wind limit (separate from challenge default)
        if product:
            pw = product["constraints"]["max_wind_mph"]
            if pw["value"] is None:
                checks.append(_check("product_wind", "Product wind limit", CAUTION, f"{w:.1f} mph", "Unknown",
                                     pw["source"], "Product wind limit not entered - only the default window was applied.", blocking=False))
            elif w > pw["value"]:
                checks.append(_check("product_wind", "Product wind limit", STOP, f"{w:.1f} mph", f"<= {pw['value']:.0f} mph",
                                     pw["source"], f"Exceeds the product limit of {pw['value']:.0f} mph."))
        # 3. Speed shear
        sd = round(abs(up["wind_mph"] - lo["wind_mph"]), 1)
        metrics["speed_diff_mph"] = sd
        if sd > t["speed_shear_caution_mph"]:
            checks.append(_check("speed_shear", "Speed change with height", CAUTION, f"{sd:.1f} mph difference",
                                 f"<= {t['speed_shear_caution_mph']:.0f} mph", _src("speed_shear_caution_mph"),
                                 f"Wind at 30 ft is {sd:.1f} mph different from 5 ft. Droplets released higher may travel differently.", blocking=False))
        # 4. Direction shear (circular), only when both heights are not calm
        reliable = lo["wind_mph"] >= t["calm_direction_mph"] and up["wind_mph"] >= t["calm_direction_mph"]
        metrics["dir_comparison_reliable"] = reliable
        dd = round(angle_diff(lo["dir_from_deg"], up["dir_from_deg"]))
        metrics["dir_diff_deg"] = dd
        if not reliable:
            checks.append(_check("dir_shear", "Direction change with height", CAUTION, f"{dd}° (calm - unreliable)",
                                 f"Both heights >= {t['calm_direction_mph']:.0f} mph", _src("calm_direction_mph"),
                                 "At least one height is near calm, so the direction comparison is not meaningful.", blocking=False))
        elif dd > t["dir_shear_caution_deg"]:
            checks.append(_check("dir_shear", "Direction change with height", CAUTION, f"{dd}° apart",
                                 f"<= {t['dir_shear_caution_deg']:.0f}°", _src("dir_shear_caution_deg"),
                                 f"Wind direction differs by {dd}° between 5 ft and 30 ft.", blocking=False))

    nb = neighbors(field, list(areas), None if problems else reading, t, product) if field else []
    for n in nb:
        if n["blocking"]:
            checks.append(_check(f"neighbor_{n['area_id']}", "Sensitive area constraint", STOP, n["name"],
                                 "Hold while air moves toward area", (n["constraint"] or {}).get("source", ""),
                                 f"Air is moving toward {n['name']} ({n['distance_ft']} ft away), and a constraint holds application in that case."))
        elif n["attention"]:
            checks.append(_check(f"neighbor_{n['area_id']}", "Nearby sensitive area", CAUTION, n["name"],
                                 "Attention only", _src("attention_radius_m"),
                                 f"{n['name']} is {n['distance_ft']} ft away and air is moving toward it (or wind is calm). Review before starting.", blocking=False))

    status = worst(*[c["status"] for c in checks]) if checks else INSUFFICIENT
    flagged = [c for c in checks if c["status"] == status and status != GO]
    reason = " ".join(c["reason"] for c in flagged) if flagged else \
        "No configured weather flags were detected. This is not a guarantee of safety - confirm conditions on site."
    g = ground_only(None if problems and reading is None else reading, t)
    headline = {GO: "Go - no configured flags", CAUTION: "Caution - review flags", STOP: "Stop - do not start",
                INSUFFICIENT: "Insufficient data - cannot assess"}[status]
    return {
        "time": at.isoformat(), "status": status, "headline": headline, "reason": reason,
        "checks": checks, "metrics": metrics, "reading": reading, "ground_only": g,
        "blind_spot": g["status"] == GO and status in (STOP, CAUTION) and any(
            c["id"] in ("inversion", "speed_shear", "dir_shear") and c["status"] != GO for c in checks),
        "neighbors": nb, "rule_version": RULE_VERSION, "thresholds": t,
        "provenance": {"source": reading["source"] if reading else None, "kind": reading["kind"] if reading else None,
                       "observed_at": reading["observed_at"] if reading else None, "evaluated_at": at.isoformat(),
                       "heights_ft": [5, 30], "timezone": "MST (UTC-7)"},
    }
