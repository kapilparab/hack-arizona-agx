"""Earliest suitable full-job windows and job sequencing.

Windows are conditional planning estimates from a SIMULATED scenario. Every
start still requires a fresh local check. Weather constraints are never
relaxed to force a schedule; jobs without a window stay unscheduled."""
import itertools
import math
from datetime import datetime, timedelta
from app import catalog, demo_data, engine, equipment
from app.config import MST, SLOT_MIN, RULE_VERSION, thresholds as _thr
from app.geo import centroid

PRIORITY_W = {"high": 4, "medium": 2, "normal": 1, "low": 0.5}
NO_WINDOW = "No suitable window found before the requested deadline - review with your PCA."
WEATHER_IDS = {"inversion", "speed_shear", "dir_shear", "inversion_persistence"}
CAUSE_LABEL = {
    "inversion": "temperature inversion", "wind_low": "wind below minimum", "wind_high": "wind above maximum",
    "product_wind": "product wind limit", "data": "missing or insufficient sensor data", "speed_shear": "wind-speed change with height",
    "dir_shear": "wind-direction change with height", "neighbor": "sensitive-area constraint", "rain": "rain-free interval conflicts with forecast rain",
    "shift": "outside crew shift", "deadline": "would finish after the deadline", "horizon": "beyond the scenario horizon",
}


def _ceil_slot(t: datetime) -> datetime:
    t = t.astimezone(MST).replace(second=0, microsecond=0)
    r = t.minute % SLOT_MIN
    return t if r == 0 else t + timedelta(minutes=SLOT_MIN - r)


def slot_status(scn, field, product, areas, t, overrides=None):
    """Return (suitable, cause_id, assessment) for the slot starting at t."""
    sid = field["sensor_id"]
    rd = scn.reading(sid, t) if sid else None
    prev = scn.reading(sid, t - timedelta(minutes=SLOT_MIN)) if sid else None
    a = engine.assess(rd, t, field, areas, product, overrides, prev_reading=prev)
    for c in a["checks"]:
        if c["status"] in (engine.STOP, engine.INSUFFICIENT):
            return False, ("neighbor" if c["id"].startswith("neighbor_") else c["id"]), a
    for c in a["checks"]:
        if c["id"] in WEATHER_IDS and c["status"] == engine.CAUTION:
            return False, c["id"], a
    return True, None, a


class Context:
    def __init__(self, scn, jobs, user_areas=(), user_exclusions=(), overrides=None):
        self.scn, self.jobs = scn, jobs
        self.areas = list(demo_data.SENSITIVE) + list(user_areas)
        self.user_exclusions = list(user_exclusions)
        self.overrides = overrides or {}
        self.t = _thr(overrides)
        self._suit = {}
        self._dec = {}  # decision ID of each assessed slot (same ID the map/status/records show for that time)
        self.evals = {}
        for j in jobs:
            f = demo_data.field(j["field_id"])
            prod = catalog.PRODUCTS.get(j.get("product_id"))
            ev = equipment.evaluate(f, j["unit_id"], j.get("config_override"), prod, j.get("orientation_deg", 0),
                                    self.user_exclusions, user_areas)
            self.evals[j["id"]] = ev

    def suit(self, field, product_id, t):
        key = (field["id"], product_id, t)
        if key not in self._suit:
            ok, cause, a = slot_status(self.scn, field, catalog.PRODUCTS.get(product_id), self.areas, t, self.overrides)
            self._suit[key] = (ok, cause, a["status"])
            self._dec[key] = a["decision_id"]
        return self._suit[key]

    def rain_ok(self, end: datetime, hours):
        if hours is None:
            return None, "Rain-free requirement not entered for this product - rain check incomplete."
        thr = self.t["rain_prob_block_pct"]
        t = end
        stop = end + timedelta(hours=hours)
        worst = 0
        while t < stop:
            p = self.scn.rain_prob(t)
            if p is None:
                return False, f"Forecast does not cover the full {hours:g} h rain-free interval."
            worst = max(worst, p)
            if p >= thr:
                return False, (f"Simulated forecast shows {p:.0f}% rain probability at {t.strftime('%H:%M')}, inside the "
                               f"{hours:g} h rain-free interval after the last pass (threshold {thr:.0f}%).")
            t += timedelta(minutes=SLOT_MIN)
        return True, f"Highest simulated rain probability in the {hours:g} h after the last pass: {worst:.0f}% (below {thr:.0f}%)."


def _shift_bounds(unit, day_dt):
    s0 = datetime.strptime(unit["shift"][0], "%H:%M").time()
    s1 = datetime.strptime(unit["shift"][1], "%H:%M").time()
    d = day_dt.date()
    return datetime.combine(d, s0, MST), datetime.combine(d, s1, MST)


def find_window(ctx: Context, job, ready: datetime, collect=False):
    """Earliest start >= ready where the full job fits every constraint."""
    f = demo_data.field(job["field_id"])
    ev = ctx.evals[job["id"]]
    unit = catalog.unit(job["unit_id"])
    dur = job.get("duration_override_min") or ev["estimate"]["total_min"]
    deadline = datetime.fromisoformat(job["latest_completion"])
    rain_h = (catalog.PRODUCTS.get(job.get("product_id")) or {}).get("constraints", {}).get("rainfast_h", {}).get("value")
    causes = {}
    s = _ceil_slot(max(ready, datetime.fromisoformat(job["earliest_start"])))
    while True:
        end = s + timedelta(minutes=dur)
        if end > deadline:
            causes.setdefault("deadline", 0)
            causes["deadline"] += 1
            break
        if end > ctx.scn.end:
            causes["horizon"] = causes.get("horizon", 0) + 1
            break
        sh0, sh1 = _shift_bounds(unit, s)
        if s < sh0 or end > sh1:
            causes["shift"] = causes.get("shift", 0) + 1
            s = sh0 if s < sh0 else _shift_bounds(unit, s + timedelta(days=1))[0]
            s = _ceil_slot(s)
            continue
        bad = None
        t = s
        while t < end:
            ok, cause, _ = ctx.suit(f, job.get("product_id"), t)
            if not ok:
                bad = (t, cause)
                break
            t += timedelta(minutes=SLOT_MIN)
        if bad:
            causes[bad[1]] = causes.get(bad[1], 0) + 1
            s = bad[0] + timedelta(minutes=SLOT_MIN)
            continue
        rok, rmsg = ctx.rain_ok(end, rain_h)
        if rok is False:
            causes["rain"] = causes.get("rain", 0) + 1
            s += timedelta(minutes=SLOT_MIN)
            continue
        return {"start": s, "end": end, "duration_min": dur, "rain_ok": rok, "rain_note": rmsg, "causes": causes}
    return {"start": None, "causes": causes, "duration_min": dur}


def _travel_min(unit, frm_xy, to_xy):
    d = math.dist(frm_xy, to_xy) * 1.3  # straight line x 1.3 road factor (prototype assumption)
    return int(math.ceil(d / (unit["travel_mph"] * 0.44704) / 60))


def simulate(ctx: Context, order):
    now = ctx.scn.now
    state = {u["id"]: {"free": now, "xy": demo_data.YARD["xy"], "loc": demo_data.YARD["name"]} for u in catalog.EQUIPMENT_UNITS}
    results = []
    for jid in order:
        job = next(j for j in ctx.jobs if j["id"] == jid)
        ev = ctx.evals[jid]
        f = demo_data.field(job["field_id"])
        unit = catalog.unit(job["unit_id"])
        if not ev.get("compatible"):
            blocks = [i["message"] for i in ev["issues"] if i["severity"] == "block"]
            results.append({"job_id": jid, "scheduled": False, "reason_code": "equipment_conflict",
                            "message": NO_WINDOW, "details": blocks, "unit_id": unit["id"]})
            continue
        st = state[unit["id"]]
        fxy = centroid(f["poly"])
        travel = _travel_min(unit, st["xy"], fxy)
        setup = ev["config"].get("setup_min", 20)
        ready = st["free"] + timedelta(minutes=travel + setup)
        pre = []
        if not f["sensor_id"]:
            pre.append(("data", "No paired-height sensor covers this field, so inversions cannot be assessed"))
        dur = job.get("duration_override_min") or ev["estimate"]["total_min"]
        sh0, sh1 = _shift_bounds(unit, now)
        if dur > (sh1 - sh0).total_seconds() / 60:
            pre.append(("shift", f"Estimated job duration {dur // 60} h {dur % 60} min exceeds one {unit['shift'][0]}-{unit['shift'][1]} crew shift (split jobs are not supported)"))
        w = {"start": None, "causes": {}} if pre else find_window(ctx, job, ready)
        if w["start"] is None:
            top = sorted(w["causes"].items(), key=lambda kv: -kv[1])
            details = [m for _, m in pre] + [f"{CAUSE_LABEL.get(c, c)} ({n} candidate start{'s' if n != 1 else ''} rejected)" for c, n in top]
            results.append({"job_id": jid, "scheduled": False,
                            "reason_code": pre[0][0] if pre else (top[0][0] if top else "unknown"),
                            "message": NO_WINDOW, "unit_id": unit["id"], "details": details,
                            "earliest_ready": ready.isoformat()})
            continue
        depart = w["start"] - timedelta(minutes=travel + setup)
        depart = max(depart, st["free"])
        results.append({"job_id": jid, "scheduled": True, "unit_id": unit["id"], "from": st["loc"],
                        "depart": depart.isoformat(), "travel_min": travel, "setup_min": setup,
                        "start": w["start"].isoformat(), "end": w["end"].isoformat(), "duration_min": w["duration_min"],
                        "wait_min": int((w["start"] - ready).total_seconds() // 60),
                        "rain_ok": w["rain_ok"], "rain_note": w["rain_note"],
                        "rejected_causes": {CAUSE_LABEL.get(k, k): v for k, v in w["causes"].items()}})
        results[-1]["surface"] = surface_checks(job, results[-1])
        results[-1]["pre_checks"] = PRE_CHECKS
        results[-1]["start_decision_id"] = ctx._dec.get((f["id"], job.get("product_id"), w["start"]))
        st.update(free=w["end"], xy=fxy, loc=f["name"])
    return results


def score(ctx, results):
    now = ctx.scn.now
    w_sched = sum(PRIORITY_W[next(j for j in ctx.jobs if j["id"] == r["job_id"])["priority"]] for r in results if r["scheduled"])
    lateness = sum(PRIORITY_W[next(j for j in ctx.jobs if j["id"] == r["job_id"])["priority"]] *
                   (datetime.fromisoformat(r["end"]) - now).total_seconds() / 60 for r in results if r["scheduled"])
    return (-w_sched, round(lateness))


def plan(scn, jobs, user_areas=(), user_exclusions=(), overrides=None):
    jobs = [j for j in jobs if j.get("status", "open") == "open"]
    ctx = Context(scn, jobs, user_areas, user_exclusions, overrides)
    default = [j["id"] for j in jobs]
    perms = list(itertools.permutations(default)) if len(default) <= 7 else [tuple(default)]
    scored = []
    for p in perms:
        res = simulate(ctx, p)
        scored.append((score(ctx, res), 0 if list(p) == default else 1, p, res))
    scored.sort(key=lambda x: (x[0], x[1]))
    best = scored[0]
    dflt = next(s for s in scored if list(s[2]) == default)
    alts, seen = [], set()
    for s in scored[1:]:
        key = tuple(r["job_id"] for r in s[3] if r["scheduled"])
        if key in seen or s[0] == best[0]:
            continue
        seen.add(key)
        alts.append(_summary(ctx, s))
        if len(alts) == 3:
            break
    out = {
        "generated_at": datetime.now(MST).isoformat(), "scenario_now": scn.now.isoformat(),
        "rule_version": RULE_VERSION, "simulated": True, "sequences_evaluated": len(perms),
        "order": list(best[2]), "jobs": best[3], "chosen": _summary(ctx, best), "default": _summary(ctx, dflt),
        "alternatives": alts, "equipment": {jid: _slim_eval(e) for jid, e in ctx.evals.items()},
        "objective": "Schedule the most priority-weighted jobs before their deadlines, then finish higher-priority work earliest.",
        "conditional_note": "Candidate windows are conditional planning estimates from simulated data. Confirm fresh local readings before starting each job.",
    }
    return out


def _slim_eval(e):
    return {k: e.get(k) for k in ("unit", "status", "compatible", "issues", "estimate", "buffers")}


def _summary(ctx, s):
    sc, _, order, res = s
    sched = [r for r in res if r["scheduled"]]
    return {"order": list(order), "scheduled": [r["job_id"] for r in sched],
            "unscheduled": [r["job_id"] for r in res if not r["scheduled"]],
            "weighted_scheduled": -sc[0], "weighted_finish_min": sc[1],
            "last_end": max((r["end"] for r in sched), default=None),
            "jobs": {r["job_id"]: ({"start": r["start"], "end": r["end"]} if r["scheduled"] else {"reason": r["reason_code"]}) for r in res}}


def field_timeline(scn, field, product_id=None, user_areas=(), overrides=None):
    areas = list(demo_data.SENSITIVE) + list(user_areas)
    prod = catalog.PRODUCTS.get(product_id) if product_id else None
    out = []
    for t in scn.slots():
        ok, cause, a = slot_status(scn, field, prod, areas, t, overrides)
        m = a["metrics"]
        rd = a["reading"]
        out.append({"time": t.isoformat(), "status": a["status"], "suitable": ok, "cause": cause,
                    "kind": scn.kind_at(t), "delta_t_f": m["delta_t_f"],
                    "wind_lower_mph": rd["lower"]["wind_mph"] if rd else None,
                    "wind_upper_mph": rd["upper"]["wind_mph"] if rd else None,
                    "rain_prob_pct": scn.rain_prob(t), "ground_only": a["ground_only"]["status"]})
    return out


def recommend(scn, jobs, field_id, user_areas=(), user_exclusions=(), overrides=None):
    """Rank every available equipment unit for the open job on `field_id`.

    For each unit the full sequence planner is re-run with this job assigned to
    that unit, so the recommendation accounts for compatibility, product
    constraints, job duration, travel/setup, weather windows, the rain-free
    interval, the deadline, and knock-on effects on the other jobs.
    Order of preference: no blocking conflict > this job fits before its deadline
    > more priority-weighted jobs scheduled overall > earlier finish > shorter job.
    Faster or coarser is never assumed better on its own."""
    import copy
    open_jobs = [j for j in jobs if j.get("status", "open") == "open"]
    job = next((j for j in open_jobs if j["field_id"] == field_id), None)
    if not job:
        return {"field_id": field_id, "job_id": None, "options": [], "recommended_unit": None,
                "message": "No open treatment request for this field."}
    options = []
    for u in catalog.EQUIPMENT_UNITS:
        js = copy.deepcopy(open_jobs)
        me = next(j for j in js if j["id"] == job["id"])
        if me["unit_id"] != u["id"]:
            me["unit_id"] = u["id"]
            me.pop("config_override", None)
        p = plan(scn, js, user_areas, user_exclusions, overrides)
        r = next(x for x in p["jobs"] if x["job_id"] == job["id"])
        ev = p["equipment"][job["id"]]
        blocks = [i["message"] for i in ev["issues"] if i["severity"] == "block"]
        est = ev.get("estimate") or {}
        others = [x for x in p["jobs"] if x["job_id"] != job["id"]]
        options.append({
            "unit_id": u["id"], "unit_name": u["name"], "type": u["type"], "crew": u["crew"],
            "block_codes": [i["code"] for i in ev["issues"] if i["severity"] == "block"],
            "economics": _economics(u, est, r),
            "compatible": not blocks, "blocking": blocks,
            "warnings": [i["message"] for i in ev["issues"] if i["severity"] == "warn"],
            "estimate": {k: est.get(k) for k in ("total_min", "spray_min", "turn_min", "reload_min", "loads", "volume", "setup_min", "speed_m_s", "swath_m", "treated_acres")} if est else None,
            "scheduled": r["scheduled"],
            "schedule": {k: r.get(k) for k in ("depart", "start", "end", "travel_min", "setup_min", "wait_min", "rain_ok", "rain_note")} if r["scheduled"] else None,
            "unscheduled_reason": None if r["scheduled"] else "; ".join(r.get("details") or [r.get("reason_code", "")]),
            "plan_order": p["order"], "plan_weighted": p["chosen"]["weighted_scheduled"],
            "others_scheduled": sum(1 for x in others if x["scheduled"]), "others_total": len(others),
        })

    def key(o):
        end = o["schedule"]["end"] if o["schedule"] else "9999"
        return (not o["compatible"], not o["scheduled"], -o["plan_weighted"], end, (o["estimate"] or {}).get("total_min") or 1e9)

    options.sort(key=key)
    best = options[0] if options and options[0]["compatible"] and options[0]["scheduled"] else None
    for i, o in enumerate(options):
        if not o["compatible"]:
            o["why"] = "Blocked: " + o["blocking"][0]
        elif not o["scheduled"]:
            o["why"] = "Compatible, but no suitable window before the deadline: " + (o["unscheduled_reason"] or "")
        elif o is best:
            o["why"] = (f"Finishes {o['schedule']['end'][11:16]} with no blocking conflicts, and the full plan still fits "
                        f"{o['others_scheduled']} of {o['others_total']} other jobs.")
        else:
            b = best["schedule"]["end"][11:16] if best else "-"
            o["why"] = f"Workable, but finishes {o['schedule']['end'][11:16]} (recommended finishes {b}) or fits fewer jobs overall."
    savings = _savings(best, options) if best else []
    seq = None
    if best:
        p0 = plan(scn, open_jobs, user_areas, user_exclusions, overrides)
        d_ = p0["default"]["jobs"].get(job["id"], {}); c_ = p0["chosen"]["jobs"].get(job["id"], {})
        if "reason" in d_ and "start" in c_:
            seq = (f"Sequencing: in the request order ({' → '.join(p0['default']['order'])}) this job would get no window "
                   f"({CAUSE_LABEL.get(d_['reason'], d_['reason'])}). The proposed order ({' → '.join(p0['chosen']['order'])}) fits it before its deadline.")
        elif "start" in d_ and "start" in c_ and d_["end"] != c_["end"]:
            diff = int((datetime.fromisoformat(d_["end"]) - datetime.fromisoformat(c_["end"])).total_seconds() // 60)
            seq = f"Sequencing: the proposed order finishes this job {abs(diff)} min {'earlier' if diff > 0 else 'later'} than the request order, to fit higher-priority work."
    return {"field_id": field_id, "job_id": job["id"], "recommended_unit": best["unit_id"] if best else None,
            "savings": savings, "sequencing": seq,
            "cost_basis": {"labor_usd_per_person_h": catalog.LABOR_USD_PER_PERSON_H, "source": catalog.COST_SOURCE,
                           "machine_usd_per_h": {u["id"]: u["machine_usd_per_h"] for u in catalog.EQUIPMENT_UNITS}},
            "options": options,
            "message": None if best else "No equipment option gives a suitable window before the requested deadline - review with your PCA.",
            "basis": "Ranks units by: no blocking conflict, fits before the deadline, most priority-weighted jobs in the full plan, earliest finish, then shortest job. "
                     "Uses simulated weather and operator-entered equipment inputs; it is a planning candidate, not a guarantee."}


# Comparisons only for alternatives that could do this job with a fixable change;
# a wrong-crop or unsupported unit is never used to claim a saving.
_NOT_COMPARABLE = {"crop_mismatch", "unsupported", "nozzle_incompatible"}


def _economics(unit, est, r):
    """Time, cost and efficiency for one unit. Cost = crew x on-site hours x labor rate
    + machine hours (travel + job) x machine rate, using DEMO cost inputs."""
    if not est:
        return None
    travel = r.get("travel_min") or 0
    setup = est.get("setup_min") or 0
    job = est["total_min"]
    on_site = travel + setup + job
    labor = unit["crew_size"] * on_site / 60 * catalog.LABOR_USD_PER_PERSON_H
    machine = (travel + job) / 60 * unit["machine_usd_per_h"]
    acres = est.get("treated_acres") or 0
    return {"on_site_min": on_site, "job_min": job, "travel_min": travel, "setup_min": setup,
            "crew_hours": round(unit["crew_size"] * on_site / 60, 1),
            "labor_usd": round(labor), "machine_usd": round(machine), "total_usd": round(labor + machine),
            "usd_per_acre": round((labor + machine) / acres, 2) if acres else None,
            "acres_per_hour": round(acres / (job / 60), 1) if job else None,
            "spray_share_pct": round(100 * est["spray_min"] / job) if job else None,
            "treated_acres": acres, "travel_estimated": not r.get("travel_min")}


def _savings(best, options):
    b = best["economics"]
    out = []
    for o in options:
        if o is best or not o.get("economics") or set(o["block_codes"]) & _NOT_COMPARABLE:
            continue
        e = o["economics"]
        out.append({"unit_id": o["unit_id"], "unit_name": o["unit_name"],
                    "minutes_saved": e["on_site_min"] - b["on_site_min"], "usd_saved": e["total_usd"] - b["total_usd"],
                    "crew_hours_saved": round(e["crew_hours"] - b["crew_hours"], 1),
                    "reference_only": not (o["compatible"] and o["scheduled"]),
                    "note": None if (o["compatible"] and o["scheduled"]) else
                            ("Reference only: this unit is currently blocked - " + (o["blocking"][0] if o["blocking"] else "no window") )})
    return out



PRE_CHECKS = [
    "Take fresh paired-height readings at the field (both heights, same mast) within 20 min of starting; the window is a simulated, conditional estimate.",
    "Confirm wind direction relative to every marked sensitive area at both installed heights.",
    "Optional field observation: dust hanging, smoke layering, fog/dew/frost, cloud, local wind variability. Absence of signs does not establish safe conditions.",
    "Re-read the product label for wind, temperature, rain-free, buffer and activation instructions; demo constraints are not label values.",
    "Re-check the forecast for rain timing and probability; forecast improvement does not clear a measured inversion.",
]


def surface_checks(job, r):
    """Five separate rain/surface concerns; unknown product information stays explicit."""
    prod = catalog.PRODUCTS.get(job.get("product_id")) or {}
    c = prod.get("constraints", {})
    rf = c.get("rainfast_h", {"value": None, "source": "Not entered"})
    act = c.get("activation", {"value": None, "source": "Not entered"})
    run = c.get("runoff", {"value": None, "source": "Not entered"})
    lw = c.get("leaf_wetness", {"value": None, "source": "Not entered"})
    return [
        {"id": "drift", "label": "Airborne drift", "status": "checked",
         "text": "Paired-height inversion, wind window, shear and sensitive-area checks were applied to every 15-min slot of the job."},
        {"id": "rainfast", "label": "Rainfastness / effectiveness", "status": "checked" if rf["value"] is not None else "unknown",
         "text": (r.get("rain_note") or "") if rf["value"] is not None else "Rain-free interval not entered for this product - not checked.", "source": rf["source"]},
        {"id": "runoff", "label": "Runoff", "status": "checked" if run["value"] else "unknown",
         "text": run["value"] or "No product runoff instruction entered, and the simulated forecast has probability only (no rainfall amount or intensity).", "source": run["source"]},
        {"id": "wetness", "label": "Dew / leaf wetness", "status": "checked" if lw["value"] else "unknown",
         "text": lw["value"] or "No leaf-wetness requirement entered. Dew can be recorded as a field observation; no leaf-wetness sensor is in the demo.", "source": lw["source"]},
        {"id": "activation", "label": "Rain or irrigation for activation", "status": "noted" if act["value"] else "unknown",
         "text": act["value"] or "Not entered for this product.", "source": act["source"]},
    ]
