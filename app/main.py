"""CanopyGuard API + static web app (same origin, so it works from phones on the LAN)."""
import os
import uuid
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles

from app import catalog, demo_data, engine, equipment, explain, regional, scheduler, store
from app.config import DEFAULT_THRESHOLDS, MST, RULE_VERSION, thresholds
from app.geo import to_xy
from app.scenario import SCENARIO

app = FastAPI(title="CanopyGuard - spray-window decision support (prototype)", version=RULE_VERSION)
WEB = os.path.join(os.path.dirname(__file__), "..", "web")
STATE = {"overrides": {}, "plan": None}

store.seed(SCENARIO)


# ----------------------------------------------------------------- helpers
def _t(iso: str | None) -> datetime:
    if not iso:
        return SCENARIO.now
    try:
        t = datetime.fromisoformat(iso)
    except ValueError:
        raise HTTPException(400, f"Invalid time: {iso}")
    return t if t.tzinfo else t.replace(tzinfo=MST)


def _field(fid):
    f = demo_data.field(fid)
    if not f:
        raise HTTPException(404, f"Unknown field {fid}")
    return f


def _user_areas():
    return [a for a in store.list_areas() if a.get("_type") == "sensitive"]


def _user_excl():
    return [a for a in store.list_areas() if a.get("_type") == "exclusion"]


def _areas():
    return list(demo_data.SENSITIVE) + _user_areas()


def _assess(fid, at, product_id=None):
    f = _field(fid)
    rd = SCENARIO.reading(f["sensor_id"], at) if f["sensor_id"] else None
    prod = catalog.PRODUCTS.get(product_id) if product_id else None
    a = engine.assess(rd, at, f, _areas(), prod, STATE["overrides"])
    a["field_id"] = fid
    if not f["sensor_id"]:
        a["reason"] = "No paired-height sensor covers this field. Inversions cannot be detected here, so it cannot be assessed."
    return a


def _job_for_field(fid):
    return next((j for j in store.list_jobs() if j["field_id"] == fid and j.get("status", "open") == "open"), None)


def _plan(record_reason=None):
    p = scheduler.plan(SCENARIO, store.list_jobs(), _user_areas(), _user_excl(), STATE["overrides"])
    STATE["plan"] = p
    if record_reason:
        store.record("schedule", f"Plan revised ({record_reason}): order {' → '.join(p['order'])}; "
                                 f"{len(p['chosen']['scheduled'])} scheduled, {len(p['chosen']['unscheduled'])} unscheduled",
                     {"order": p["order"], "jobs": p["jobs"], "default": p["default"]}, scenario_time=SCENARIO.now.isoformat())
    return p


# -------------------------------------------------------------------- meta
@app.get("/api/meta")
def meta():
    return {"rule_version": RULE_VERSION, "scenario": SCENARIO.meta(), "ai_enabled": explain.ai_available(),
            "thresholds": {k: {**v, "value": thresholds(STATE["overrides"])[k]} for k, v in DEFAULT_THRESHOLDS.items()},
            "disclaimer": "Decision support only. Go means no configured flags were detected, not guaranteed safety. "
                          "Does not diagnose pests, choose pesticides, predict exposure, or control equipment."}


@app.get("/api/fields")
def fields():
    return demo_data.fields_payload(_user_areas(), _user_excl())


@app.get("/api/catalog")
def get_catalog():
    return catalog.catalog_payload()


# -------------------------------------------------------------- assessment
@app.get("/api/assess")
def assess(field_id: str, time: str | None = None, product_id: str | None = None):
    at = _t(time)
    j = _job_for_field(field_id)
    return _assess(field_id, at, product_id or (j or {}).get("product_id"))


@app.get("/api/assess/all")
def assess_all(time: str | None = None):
    at = _t(time)
    out = []
    for f in demo_data.FIELDS:
        j = _job_for_field(f["id"])
        a = _assess(f["id"], at, (j or {}).get("product_id"))
        out.append({k: a[k] for k in ("field_id", "status", "headline", "reason", "metrics", "ground_only", "blind_spot", "provenance")}
                   | {"neighbors_attention": [n["name"] for n in a["neighbors"] if n["attention"]],
                      "neighbors_blocking": [n["name"] for n in a["neighbors"] if n["blocking"]],
                      "reading": a["reading"], "checks": a["checks"]})
    return {"time": at.isoformat(), "fields": out, "sensors": [
        {"id": s["id"], "reading": SCENARIO.reading(s["id"], at)} for s in demo_data.SENSORS]}


@app.get("/api/timeline")
def timeline(field_id: str):
    f = _field(field_id)
    j = _job_for_field(field_id)
    return {"field_id": field_id, "slots": scheduler.field_timeline(SCENARIO, f, (j or {}).get("product_id"), _user_areas(), STATE["overrides"]),
            "rain": SCENARIO.rain_series(), "now": SCENARIO.now.isoformat()}


@app.post("/api/settings/thresholds")
def set_thresholds(body: dict = Body(...)):
    clean = {k: float(v) for k, v in body.items() if k in DEFAULT_THRESHOLDS and v is not None}
    STATE["overrides"] = clean
    store.record("config", f"Thresholds changed: {clean or 'reset to defaults'}", clean, scenario_time=SCENARIO.now.isoformat(), simulated=False)
    return meta()


# --------------------------------------------------------------- equipment
@app.post("/api/equipment/evaluate")
def evaluate(body: dict = Body(...)):
    f = _field(body.get("field_id"))
    prod = catalog.PRODUCTS.get(body.get("product_id"))
    ev = equipment.evaluate(f, body.get("unit_id", "U1"), body.get("config") or {}, prod, float(body.get("orientation_deg", 0)),
                            _user_excl(), _user_areas())
    if "error" in ev:
        raise HTTPException(400, ev["error"])
    at = _t(body.get("time"))
    a = _assess(f["id"], at, body.get("product_id"))
    ev["weather_status"] = {"status": a["status"], "reason": a["reason"], "time": at.isoformat()}
    if body.get("record"):
        store.record("equipment", f"Equipment evaluated for {f['name']}: {ev['unit']['name']} -> {ev['status']}",
                     {"config": ev["config"], "issues": ev["issues"], "estimate": ev["estimate"]}, field_id=f["id"],
                     job_id=body.get("job_id"), status=ev["status"], scenario_time=SCENARIO.now.isoformat())
    return ev


# -------------------------------------------------------------------- jobs
REQUIRED = ("field_id", "earliest_start", "latest_completion", "priority", "unit_id")


@app.get("/api/jobs")
def jobs():
    return store.list_jobs()


@app.post("/api/jobs")
def save_job(job: dict = Body(...)):
    missing = [k for k in REQUIRED if not job.get(k)]
    if missing:
        raise HTTPException(422, f"Missing required fields: {', '.join(missing)}")
    _field(job["field_id"])
    if job["priority"] not in scheduler.PRIORITY_W:
        raise HTTPException(422, "Priority must be high, medium, normal or low")
    if not catalog.unit(job["unit_id"]):
        raise HTTPException(422, "Unknown equipment unit")
    if _t(job["latest_completion"]) <= _t(job["earliest_start"]):
        raise HTTPException(422, "Latest completion must be after the earliest start")
    job.setdefault("id", "J-" + uuid.uuid4().hex[:4].upper())
    job.setdefault("status", "open")
    job.setdefault("product_id", "unknown")
    new = store.get_job(job["id"]) is None
    store.upsert_job(job)
    store.record("request", f"Treatment request {'created' if new else 'updated'}: {job['id']} on field {job['field_id']}",
                 job, field_id=job["field_id"], job_id=job["id"], scenario_time=SCENARIO.now.isoformat(), simulated=False)
    return job


@app.delete("/api/jobs/{jid}")
def remove_job(jid: str):
    if not store.get_job(jid):
        raise HTTPException(404, "Unknown job")
    store.delete_job(jid)
    store.record("request", f"Treatment request removed: {jid}", None, job_id=jid, scenario_time=SCENARIO.now.isoformat(), simulated=False)
    return {"ok": True}


# ---------------------------------------------------------------- schedule
@app.get("/api/schedule")
def get_schedule():
    return STATE["plan"] or _plan("initial")


@app.post("/api/schedule")
def run_schedule(body: dict = Body(default={})):
    return _plan(body.get("reason", "operator request"))


# ----------------------------------------------------------------- explain
@app.get("/api/explain")
def get_explain(topic: str, field_id: str | None = None, job_id: str | None = None, time: str | None = None, lang: str = "en"):
    lang = "es" if lang == "es" else "en"
    at = _t(time)
    plan = STATE["plan"] or _plan("initial")
    jobs_ = store.list_jobs()
    job = store.get_job(job_id) if job_id else (_job_for_field(field_id) if field_id else None)
    if job and not field_id:
        field_id = job["field_id"]
    if topic == "order":
        res = explain.order(plan, jobs_, lang)
    elif topic in ("hold", "neighbors", "missing"):
        if not field_id:
            raise HTTPException(400, "field_id required")
        f = _field(field_id)
        a = _assess(field_id, at, (job or {}).get("product_id"))
        if topic == "hold":
            tl = scheduler.field_timeline(SCENARIO, f, (job or {}).get("product_id"), _user_areas(), STATE["overrides"])
            res = explain.hold(a, f, tl, lang)
        elif topic == "neighbors":
            res = explain.neighbors(a, f, lang)
        else:
            ev = plan["equipment"].get(job["id"]) if job else None
            res = explain.missing(a, f, ev, job, lang)
    elif topic in ("rain", "equipment"):
        if not job:
            raise HTTPException(400, "job_id or field_id with an open job required")
        if topic == "rain":
            res = explain.rain(plan, job, lang)
        else:
            f = _field(job["field_id"])
            ev = equipment.evaluate(f, job["unit_id"], job.get("config_override"), catalog.PRODUCTS.get(job.get("product_id")),
                                    job.get("orientation_deg", 0), _user_excl(), _user_areas())
            res = explain.equipment_why(ev, job, lang)
    else:
        raise HTTPException(400, "Unknown topic")
    return explain.maybe_ai(res)


# -------------------------------------------------------------- monitoring
@app.post("/api/monitor")
def monitor(body: dict = Body(...)):
    """Evaluate conditions for an in-progress (simulated) job at a playback time.
    Persistent conditions are grouped into one alert; critical status is preserved."""
    job = store.get_job(body.get("job_id")) or {}
    fid = body.get("field_id") or job.get("field_id")
    at = _t(body.get("time"))
    a = _assess(fid, at, job.get("product_id"))
    critical = a["status"] in (engine.STOP, engine.INSUFFICIENT)
    active_rules = []
    alert = None
    new = False
    if critical:
        # One alert per field per episode of critical conditions (reduces duplicate
        # notifications); the message lists every triggered rule so nothing is hidden.
        crit = [c for c in a["checks"] if c["status"] in (engine.STOP, engine.INSUFFICIENT)]
        active_rules.append("critical")
        msg = " | ".join(f"{c['label']}: {c['measured']}" for c in crit)
        alert, new = store.raise_alert(fid, job.get("id"), "critical", a["status"], msg, at.isoformat())
        if new:
            store.record("alert", f"{a['status']} during application on {_field(fid)['name']}: {msg}",
                         {"checks": crit, "pass_index": body.get("pass_index"), "reading": a["reading"]},
                         field_id=fid, job_id=job.get("id"), status=a["status"], scenario_time=at.isoformat())
    cleared = store.clear_alerts(fid, active_rules)
    return {"time": at.isoformat(), "status": a["status"], "critical": critical, "new_alert": new, "alert": alert,
            "cleared_alerts": cleared, "reason": a["reason"], "assessment": a,
            "instruction": "Simulated vehicle paused. In a real operation, follow your stop procedure and label directions; "
                           "this prototype does not advise continuing to the row end." if critical else None}


@app.post("/api/scenario/inject")
def inject(body: dict = Body(...)):
    f = _field(body.get("field_id", "A"))
    if not f["sensor_id"]:
        raise HTTPException(400, "Field has no sensor")
    ev = SCENARIO.inject(f["sensor_id"], _t(body.get("time")), int(body.get("duration_min", 60)))
    store.record("scenario", f"Simulated critical change injected at {f['name']} ({ev['start']})", ev, field_id=f["id"],
                 scenario_time=ev["start"])
    return SCENARIO.meta()


@app.post("/api/scenario/reset")
def reset(body: dict = Body(default={})):
    SCENARIO.reset_events()
    store.reset_alerts()
    if body.get("jobs", True):
        store.seed(SCENARIO, force=True)
    STATE["overrides"] = {}
    store.record("scenario", "Demo scenario reset", None, scenario_time=SCENARIO.now.isoformat())
    p = _plan("demo reset")
    return {"scenario": SCENARIO.meta(), "plan_order": p["order"]}


# ------------------------------------------------------------------ alerts
@app.get("/api/alerts")
def alerts(active_only: bool = False):
    return store.list_alerts(active_only)


@app.post("/api/alerts/{aid}/ack")
def ack(aid: int, body: dict = Body(default={})):
    who = (body.get("operator") or "").strip() or "Operator (unnamed)"
    al = store.ack_alert(aid, who)
    if not al:
        raise HTTPException(404, "Unknown alert")
    store.record("ack", f"Alert {aid} acknowledged by {who}", al, field_id=al["field_id"], job_id=al["job_id"],
                 status=al["severity"], scenario_time=al["last_seen"], simulated=False)
    return al


# ------------------------------------------------------------------- areas
@app.post("/api/areas")
def add_area(body: dict = Body(...)):
    coords = body.get("coordinates") or []
    if len(coords) < 3:
        raise HTTPException(422, "An area needs at least 3 points")
    typ = body.get("type")
    if typ not in ("sensitive", "exclusion"):
        raise HTTPException(422, "type must be sensitive or exclusion")
    if coords[0] == coords[-1]:
        coords = coords[:-1]  # drop closing point of a GeoJSON ring
    poly = [to_xy(lon, lat) for lon, lat in coords]
    a = {"id": ("U" if typ == "sensitive" else "X") + uuid.uuid4().hex[:4].upper(), "_type": typ, "poly": poly,
         "name": (body.get("name") or "").strip() or ("User-marked area" if typ == "sensitive" else "User exclusion"),
         "user_added": True}
    if typ == "sensitive":
        kind = body.get("kind", "neighbor_crop")
        if kind not in ("neighbor_crop", "worker_area", "home", "road", "waterway"):
            raise HTTPException(422, "Unknown area kind")
        a["kind"] = kind
        a["constraint"] = {"type": "hold_when_toward", "source": "User-entered"} if body.get("hold_when_toward") else None
    else:
        a["field_id"] = body.get("field_id")
        _field(a["field_id"])
        a["source"] = "User-entered"
    store.add_area(a)
    store.record("area", f"{'Sensitive area' if typ == 'sensitive' else 'Exclusion'} added: {a['name']}", {k: v for k, v in a.items() if k != "poly"},
                 field_id=a.get("field_id"), scenario_time=SCENARIO.now.isoformat(), simulated=False)
    return {k: v for k, v in a.items() if k != "poly"}


@app.delete("/api/areas/{aid}")
def del_area(aid: str):
    store.delete_area(aid)
    store.record("area", f"Area removed: {aid}", None, scenario_time=SCENARIO.now.isoformat(), simulated=False)
    return {"ok": True}


# ----------------------------------------------------------------- records
@app.get("/api/records")
def records(limit: int = 200, kind: str | None = None):
    return store.list_records(min(limit, 1000), kind)


@app.post("/api/records/snapshot")
def snapshot(body: dict = Body(default={})):
    """Record the current assessment for a field (timestamped reading + triggered rules)."""
    fid = body.get("field_id", "A")
    at = _t(body.get("time"))
    a = _assess(fid, at)
    rid = store.record("assessment", f"{_field(fid)['name']}: {a['status']} - {a['headline']}",
                       {"reading": a["reading"], "checks": a["checks"], "metrics": a["metrics"], "ground_only": a["ground_only"]},
                       field_id=fid, status=a["status"], scenario_time=at.isoformat())
    return {"id": rid}


@app.get("/api/records/export.csv")
def export():
    return Response(store.export_csv(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=canopyguard_records.csv"})


# ---------------------------------------------------------------- regional
@app.get("/api/context/regional")
def regional_ctx():
    return regional.fetch()


# ------------------------------------------------------------------ static
@app.get("/")
def index():
    return FileResponse(os.path.join(WEB, "index.html"))




# ------------------------------------------------------------- recommend
import json as _json
_CREDITS = _json.load(open(os.path.join(os.path.dirname(__file__), "photo_credits.json"), encoding="utf-8"))
FIELD_PHOTO = {"A": "crop-romaine", "B": "crop-broccoli", "C": "crop-cauliflower", "D": "crop-lemon"}
EQUIP_PHOTO = {"ground_boom": "equip-boom", "drone": "equip-drone", "airblast": "equip-airblast", "aircraft": "equip-aircraft"}


@app.get("/api/recommend")
def recommend(field_id: str):
    _field(field_id)
    return scheduler.recommend(SCENARIO, store.list_jobs(), field_id, _user_areas(), _user_excl(), STATE["overrides"])


@app.get("/api/photos")
def photos():
    return {"credits": _CREDITS, "fields": FIELD_PHOTO, "equipment": EQUIP_PHOTO,
            "note": "Representative photos from Wikimedia Commons. They are not photos of the fictional fields or of the specific units in this plan."}


app.mount("/", StaticFiles(directory=WEB), name="web")
