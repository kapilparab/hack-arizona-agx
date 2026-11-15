"""Deterministic multi-height weather assessment.

Status meanings:
  GO                - no configured flag detected. NOT a guarantee of safety.
  CAUTION           - a non-blocking flag needs judgement.
  STOP              - a blocking flag is present.
  INSUFFICIENT_DATA - required readings are missing, stale, invalid or misaligned; never Go.
  NOT_ASSESSED      - (checks only) the optional input for this check is not installed/available.

Heights come from each reading's metadata (see app/measure.py); configurations
such as the near-surface pair and the 5 ft / 30 ft tower are never treated as equivalent.
"""
import math
from datetime import datetime
from app.config import RULE_VERSION, DEFAULT_THRESHOLDS, thresholds as _thr
from app.geo import angle_diff, bearing, centroid, poly_distance
from app.measure import CONFIGS, classify_pair, fmt_height

GO, CAUTION, STOP, INSUFFICIENT, NA = "GO", "CAUTION", "STOP", "INSUFFICIENT_DATA", "NOT_ASSESSED"
RANK = {NA: 0, GO: 0, CAUTION: 1, INSUFFICIENT: 2, STOP: 3}
LIMITS = {"temp_f": (-40, 140), "wind_mph": (0, 120), "dir_from_deg": (0, 360)}


def worst(*statuses):
    return max(statuses, key=lambda s: RANK[s]) if statuses else GO


def _src(key):
    return DEFAULT_THRESHOLDS[key]["source"]


def _check(id_, label, status, measured, threshold, source, reason, blocking=None):
    return {"id": id_, "label": label, "status": status, "measured": measured, "threshold": threshold,
            "threshold_source": source, "reason": reason,
            "blocking": blocking if blocking is not None else status in (STOP, INSUFFICIENT)}


def _num_ok(v, k):
    return isinstance(v, (int, float)) and not math.isnan(v) and LIMITS[k][0] <= v <= LIMITS[k][1]


def temp_label(lv):
    return fmt_height(lv.get("height_ft"), lv.get("ref"))


def wind_label(lv):
    return fmt_height(lv.get("wind_height_ft", lv.get("height_ft")), lv.get("wind_ref", lv.get("ref")))


def wind_levels(reading):
    """Installed wind levels, lowest first."""
    out = []
    for name in ("lower", "upper"):
        lv = reading[name]
        if lv.get("wind_installed", True):
            out.append((name, lv))
    return sorted(out, key=lambda x: x[1].get("wind_height_ft", x[1].get("height_ft")) or 0)


def validate(reading: dict | None, at: datetime, t: dict):
    """Return (problems, age_min). Problems make the result INSUFFICIENT_DATA."""
    if reading is None:
        return ["No paired-height reading is available for this field and time."], None
    problems = []
    lo, up = reading["lower"], reading["upper"]
    for name, lv in (("lower", lo), ("upper", up)):
        if lv.get("height_ft") is None or not lv.get("ref"):
            problems.append(f"{name} temperature sensor height or reference surface not documented.")
    obs = datetime.fromisoformat(reading["observed_at"])
    age = (at - obs).total_seconds() / 60
    if age > t["stale_after_min"]:
        problems.append(f"Reading is {age:.0f} min old (stale after {t['stale_after_min']:.0f} min).")
    if age < -1:
        problems.append("Reading timestamp is in the future relative to the evaluation time.")
    # pair alignment: both temperatures must be from (nearly) the same time
    ta, tb = lo.get("temp_observed_at"), up.get("temp_observed_at")
    if ta and tb:
        dt = abs((datetime.fromisoformat(ta) - datetime.fromisoformat(tb)).total_seconds()) / 60
        if dt > t["pair_time_tolerance_min"]:
            problems.append(f"Lower and upper temperatures are {dt:.0f} min apart (pair tolerance {t['pair_time_tolerance_min']:.0f} min).")
    for name, lv in (("lower", lo), ("upper", up)):
        v = lv.get("temp_f")
        lab = f"{temp_label(lv)} temperature"
        if v is None:
            problems.append(f"{lab} missing" + (f" ({lv['missing_reason']})" if lv.get("missing_reason") else "") + ".")
        elif not _num_ok(v, "temp_f"):
            problems.append(f"{lab} invalid ({v}).")
    winds = wind_levels(reading)
    if not winds:
        problems.append("No wind sensor is installed.")
    for name, lv in winds:
        for k in ("wind_mph", "dir_from_deg"):
            v = lv.get(k)
            lab = f"{wind_label(lv)} wind {'speed' if k == 'wind_mph' else 'direction'}"
            if v is None:
                problems.append(f"{lab} missing" + (f" ({lv['missing_reason']})" if lv.get("missing_reason") else "") + ".")
            elif not _num_ok(v, k):
                problems.append(f"{lab} invalid ({v}).")
    return problems, age


def ground_only(reading: dict | None, t: dict) -> dict:
    """What a single low station would conclude (lowest wind window only, no temperature pair)."""
    if not reading:
        return {"status": INSUFFICIENT, "reason": "No reading."}
    winds = wind_levels(reading)
    if not winds or winds[0][1].get("wind_mph") is None:
        return {"status": INSUFFICIENT, "reason": "No low wind reading."}
    lv = winds[0][1]
    w = lv["wind_mph"]
    lab = wind_label(lv)
    if w < t["wind_min_mph"]:
        return {"status": STOP, "reason": f"Wind at {lab} is {w:.1f} mph, below {t['wind_min_mph']:.0f} mph."}
    if w > t["wind_max_mph"]:
        return {"status": STOP, "reason": f"Wind at {lab} is {w:.1f} mph, above {t['wind_max_mph']:.0f} mph."}
    return {"status": GO, "reason": f"Wind at {lab} is {w:.1f} mph, inside the {t['wind_min_mph']:.0f}-{t['wind_max_mph']:.0f} mph window. A single height cannot see an inversion."}


def neighbors(field: dict, areas: list, reading: dict | None, t: dict, product: dict | None = None):
    """Geometry-based context for nearby sensitive areas. An attention check on wind
    direction and distance - not an exposure or deposition model."""
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
            for lvl, r in wind_levels(reading):
                if r.get("dir_from_deg") is None or r.get("wind_mph") is None:
                    item["downwind"][lvl] = None
                    continue
                toward = (r["dir_from_deg"] + 180) % 360
                calm = r["wind_mph"] < t["calm_direction_mph"]
                hit = angle_diff(toward, brg) <= t["downwind_cone_deg"]
                item["downwind"][lvl] = {"height_ft": r.get("wind_height_ft", r.get("height_ft")), "height_label": wind_label(r),
                                         "from_deg": r["dir_from_deg"], "toward_deg": toward, "toward_area": hit, "calm": calm}
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
            for b in product["constraints"]["buffers"]["value"] or []:
                if b["kind"] == a["kind"]:
                    item["buffer_ft"] = b["ft"]
                    item["buffer_source"] = product["constraints"]["buffers"]["source"]
                    item["notes"].append(f"Product buffer {b['ft']} ft from {a['kind'].replace('_', ' ')} ({item['buffer_source']}).")
        out.append(item)
    out.sort(key=lambda i: (not i["blocking"], not i["attention"], i["distance_m"]))
    return out


def assess(reading: dict | None, at: datetime, field: dict | None = None, areas: list = (),
           product: dict | None = None, overrides: dict | None = None, trend: dict | None = None) -> dict:
    t = _thr(overrides)
    checks = []
    problems, age = validate(reading, at, t)
    pair = None
    metrics = {"delta_t_f": None, "delta_t_uncertainty_f": None, "speed_diff_mph": None, "dir_diff_deg": None,
               "dir_comparison_reliable": None, "age_min": age, "trend": trend, "pair_label": None, "config": None,
               "config_name": None, "config_source": None}
    if reading:
        lo, up = reading["lower"], reading["upper"]
        acc_l = lo.get("temp_accuracy_f", t["sensor_temp_accuracy_f"])
        acc_u = up.get("temp_accuracy_f", t["sensor_temp_accuracy_f"])
        metrics["delta_t_uncertainty_f"] = round(math.sqrt(acc_l ** 2 + acc_u ** 2), 2)
        if lo.get("height_ft") is not None and up.get("height_ft") is not None and lo.get("ref") == up.get("ref"):
            cfg = classify_pair(lo["height_ft"], up["height_ft"], lo["ref"])
            pair = f"{temp_label(up)} minus {temp_label(lo)}"
            metrics.update(pair_label=pair, config=cfg, config_name=CONFIGS.get(cfg, {}).get("name", "Other installed pair"),
                           config_source=CONFIGS.get(cfg, {}).get("source", "Installed heights as recorded"))
        elif lo.get("ref") != up.get("ref"):
            problems.append("Lower and upper temperatures use different reference surfaces; they are not a valid pair.")

    if problems:
        checks.append(_check("data", "Required paired-height data", INSUFFICIENT, "; ".join(problems),
                             "Two temperatures on one mast (aligned in time, documented heights) and at least one wind sensor",
                             _src("stale_after_min"), "Missing, stale, invalid or misaligned readings cannot produce Go."))
    else:
        lo, up = reading["lower"], reading["upper"]
        dT = round(up["temp_f"] - lo["temp_f"], 1)
        u = metrics["delta_t_uncertainty_f"]
        metrics["delta_t_f"] = dT
        unc_src = reading.get("accuracy_note") or _src("sensor_temp_accuracy_f")
        if dT > u:
            checks.append(_check("inversion", "Temperature inversion", STOP, f"{dT:+.1f} °F ({pair})",
                                 f"> +{u:.1f} °F (outside combined sensor uncertainty)", unc_src,
                                 f"Air {temp_label(up)} is {dT:.1f} °F warmer than {temp_label(lo)}. That is an inversion: fine droplets can stay suspended and move with the stable layer."))
        elif dT > 0:
            checks.append(_check("inversion", "Temperature inversion", CAUTION, f"{dT:+.1f} °F ({pair})",
                                 f"0 to +{u:.1f} °F is within uncertainty", unc_src,
                                 f"Upper air reads slightly warmer ({dT:+.1f} °F) but within the ±{u:.1f} °F combined uncertainty. Possible weak inversion - recheck before starting."))
        else:
            note = " Difference is within sensor uncertainty, so mixing may be weak." if dT >= -u else ""
            checks.append(_check("inversion", "Temperature inversion", GO, f"{dT:+.1f} °F ({pair})", "Upper not warmer than lower",
                                 unc_src, "No inversion flagged: upper air is not warmer than lower air." + note))
        winds = wind_levels(reading)
        wl = winds[0][1]
        w = wl["wind_mph"]
        wlab = wind_label(wl)
        avg = reading.get("averaging") or "averaging not documented"
        if w < t["wind_min_mph"]:
            checks.append(_check("wind_low", f"Wind speed ({wlab})", STOP, f"{w:.1f} mph ({avg})", f">= {t['wind_min_mph']:.0f} mph",
                                 _src("wind_min_mph"), "Near-calm air: droplets can hang and direction is unpredictable."))
        elif w > t["wind_max_mph"]:
            checks.append(_check("wind_high", f"Wind speed ({wlab})", STOP, f"{w:.1f} mph ({avg})", f"<= {t['wind_max_mph']:.0f} mph",
                                 _src("wind_max_mph"), f"Sustained wind {w:.1f} mph exceeds the {t['wind_max_mph']:.0f} mph limit."))
        else:
            checks.append(_check("wind", f"Wind speed ({wlab})", GO, f"{w:.1f} mph ({avg})", f"{t['wind_min_mph']:.0f}-{t['wind_max_mph']:.0f} mph",
                                 _src("wind_max_mph"), "Sustained wind is inside the configured window. A single reading does not establish steady or laminar flow."))
        if product:
            pc = product["constraints"]
            pw = pc["max_wind_mph"]
            if pw["value"] is None:
                checks.append(_check("product_wind", "Product wind limit", CAUTION, f"{w:.1f} mph", "Unknown",
                                     pw["source"], "Product wind limit not entered - only the default window was applied.", blocking=False))
            elif w > pw["value"]:
                checks.append(_check("product_wind", "Product wind limit", STOP, f"{w:.1f} mph", f"<= {pw['value']:.0f} mph",
                                     pw["source"], f"Exceeds the product limit of {pw['value']:.0f} mph."))
            tr = pc.get("temp_range_f", {"value": None, "source": "Not entered"})
            if tr["value"]:
                lo_f, hi_f = tr["value"]
                T = lo["temp_f"]
                if (lo_f is not None and T < lo_f) or (hi_f is not None and T > hi_f):
                    checks.append(_check("product_temp", "Product temperature range", STOP, f"{T:.1f} °F at {temp_label(lo)}",
                                         f"{lo_f if lo_f is not None else '-'} to {hi_f if hi_f is not None else '-'} °F", tr["source"],
                                         "Air temperature is outside the product's entered application range."))
                else:
                    checks.append(_check("product_temp", "Product temperature range", GO, f"{T:.1f} °F at {temp_label(lo)}",
                                         f"{lo_f if lo_f is not None else '-'} to {hi_f if hi_f is not None else '-'} °F", tr["source"],
                                         "Air temperature is inside the product's entered range."))
        if len(winds) >= 2:
            a, b = winds[0][1], winds[1][1]
            sd = round(abs(b["wind_mph"] - a["wind_mph"]), 1)
            metrics["speed_diff_mph"] = sd
            if sd > t["speed_shear_caution_mph"]:
                checks.append(_check("speed_shear", "Speed change with height", CAUTION, f"{sd:.1f} mph ({wind_label(b)} vs {wind_label(a)})",
                                     f"<= {t['speed_shear_caution_mph']:.0f} mph", _src("speed_shear_caution_mph"),
                                     f"Wind {wind_label(b)} differs by {sd:.1f} mph from {wind_label(a)}. Droplets released higher may travel differently.", blocking=False))
            reliable = a["wind_mph"] >= t["calm_direction_mph"] and b["wind_mph"] >= t["calm_direction_mph"]
            metrics["dir_comparison_reliable"] = reliable
            dd = round(angle_diff(a["dir_from_deg"], b["dir_from_deg"]))
            metrics["dir_diff_deg"] = dd
            if not reliable:
                checks.append(_check("dir_shear", "Direction change with height", CAUTION, f"{dd}° (calm - unreliable)",
                                     f"Both heights >= {t['calm_direction_mph']:.0f} mph", _src("calm_direction_mph"),
                                     "At least one height is near calm, so the direction comparison is not meaningful.", blocking=False))
            elif dd > t["dir_shear_caution_deg"]:
                checks.append(_check("dir_shear", "Direction change with height", CAUTION, f"{dd}° apart",
                                     f"<= {t['dir_shear_caution_deg']:.0f}°", _src("dir_shear_caution_deg"),
                                     f"Wind direction differs by {dd}° between heights (circular difference).", blocking=False))
        else:
            checks.append(_check("shear", "Wind change with height", NA, "One wind height installed", "Needs wind at two heights",
                                 "Requirements register", "Speed and direction shear cannot be assessed on this mast; other checks continue.", blocking=False))

    nb = neighbors(field, list(areas), None if problems else reading, t, product) if field else []
    for n in nb:
        if n["blocking"]:
            checks.append(_check(f"neighbor_{n['area_id']}", "Sensitive area constraint", STOP, n["name"],
                                 "Hold while air moves toward area", (n["constraint"] or {}).get("source", ""),
                                 f"Air is moving toward {n['name']} ({n['distance_ft']} ft away), and a constraint holds application in that case."))
        elif n["attention"]:
            checks.append(_check(f"neighbor_{n['area_id']}", "Nearby sensitive area", CAUTION, n["name"], "Attention only",
                                 _src("attention_radius_m"),
                                 f"{n['name']} is {n['distance_ft']} ft away and air is moving toward it (or wind is calm). Review before starting.", blocking=False))

    status = worst(*[c["status"] for c in checks]) if checks else INSUFFICIENT
    flagged = [c for c in checks if c["status"] == status and status != GO]
    reason = " ".join(c["reason"] for c in flagged) if flagged else \
        "No configured weather flags were detected. This is not a guarantee of safety - confirm conditions on site."
    g = ground_only(reading, t)
    headline = {GO: "Go - no configured flags", CAUTION: "Caution - review flags", STOP: "Stop - do not start",
                INSUFFICIENT: "Insufficient data - cannot assess"}[status]
    return {
        "time": at.isoformat(), "status": status, "headline": headline, "reason": reason,
        "checks": checks, "metrics": metrics, "reading": reading, "ground_only": g,
        "blind_spot": g["status"] == GO and status in (STOP, CAUTION) and any(
            c["id"] in ("inversion", "speed_shear", "dir_shear") and c["status"] in (STOP, CAUTION) for c in checks),
        "neighbors": nb, "rule_version": RULE_VERSION, "thresholds": t,
        "provenance": {"source": reading["source"] if reading else None, "kind": reading["kind"] if reading else None,
                       "observed_at": reading["observed_at"] if reading else None, "evaluated_at": at.isoformat(),
                       "config": metrics["config"], "pair_label": metrics["pair_label"],
                       "averaging": (reading or {}).get("averaging"), "gust_interval": (reading or {}).get("gust_interval"),
                       "shielding": (reading or {}).get("shielding"), "timezone": "MST (UTC-7)"},
    }
