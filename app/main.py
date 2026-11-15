"""Observair API + static web app (same origin, so it works from phones on the LAN)."""
import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles

from app import catalog, demo_data, engine, equipment, explain, forecast, regional, scheduler, store, terrain, realdata, measure, profile
from app.geo import ring_lonlat, centroid as geo_centroid, to_lonlat
import numpy as np
from app.config import DEFAULT_THRESHOLDS, MST, RULE_VERSION, thresholds
from app.geo import to_xy
from app.scenario import SCENARIO

app = FastAPI(title="Observair - spray-window decision support (prototype)", version=RULE_VERSION)
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
    if product_id is None:  # one decision per field+time: default to the open job's product everywhere
        product_id = (_job_for_field(fid) or {}).get("product_id")
    rd = SCENARIO.reading(f["sensor_id"], at) if f["sensor_id"] else None
    prod = catalog.PRODUCTS.get(product_id) if product_id else None
    tr = SCENARIO.trend(f["sensor_id"], at) if f["sensor_id"] else None
    prev = SCENARIO.reading(f["sensor_id"], at - timedelta(minutes=15)) if f["sensor_id"] else None
    a = engine.assess(rd, at, f, _areas(), prod, STATE["overrides"], trend=tr, prev_reading=prev, observations=_recent_obs(fid, at))
    a["field_id"] = fid
    if not f["sensor_id"]:
        a["reason"] = "No paired-height sensor covers this field. Inversions cannot be detected here, so it cannot be assessed."
    # conditions at the spray plan's release height (context; decisions use measured values)
    job = _job_for_field(fid)
    if job:
        u = catalog.unit(job["unit_id"])
        cfg = {**u["config"], **(job.get("config_override") or {})}
        inv = any(c["id"] == "inversion" and c["status"] in ("STOP", "CAUTION") for c in a["checks"])
        a["at_release"] = profile.at_release(u["type"], cfg, rd, f.get("canopy_ft"), inv)
        if a["at_release"].get("status") == "ok":
            a["at_release"]["spray_plane"] = profile.spray_plane(a["at_release"]["release"]["agl_ft"], rd, f.get("canopy_ft"))
        a["at_release"]["unit"] = u["name"]
    a["field_terrain"] = _TERRAIN_STATS.get(fid)
    return a


def _recent_obs(fid, at):
    win = thresholds(STATE["overrides"])["observation_valid_min"]
    out = []
    for o in store.list_observations(fid):
        st = o.get("scenario_time")
        if st and 0 <= (at - datetime.fromisoformat(st)).total_seconds() / 60 <= win:
            out.append(o)
    return out


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
_TERRAIN_STATS = {}


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
    if topic in ("hold", "neighbors", "missing"):
        res["decision_id"] = a["decision_id"]
        res["facts"]["decision_id"] = a["decision_id"]
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
                         {"checks": crit, "pass_index": body.get("pass_index"), "reading": a["reading"], "decision_id": a["decision_id"]},
                         field_id=fid, job_id=job.get("id"), status=a["status"], scenario_time=at.isoformat())
    clr = store.clear_alerts(fid, active_rules, int(thresholds(STATE["overrides"])["alert_clear_ticks"]))
    cleared = clr["cleared"]
    return {"time": at.isoformat(), "status": a["status"], "critical": critical, "new_alert": new, "alert": alert,
            "cleared_alerts": cleared, "clearing": clr["pending"], "decision_id": a["decision_id"], "reason": a["reason"], "assessment": a,
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
    store.reset_observations()
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
                       {"decision_id": a["decision_id"], "rule_version": a["rule_version"], "reading": a["reading"], "checks": a["checks"],
                        "metrics": a["metrics"], "ground_only": a["ground_only"], "at_release": a.get("at_release")},
                       field_id=fid, status=a["status"], scenario_time=at.isoformat())
    return {"id": rid}


@app.get("/api/records/export.csv")
def export():
    return Response(store.export_csv(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=observair_records.csv"})


# ---------------------------------------------------------------- regional
@app.get("/api/context/regional")
def regional_ctx():
    return regional.fetch()


# --------------------------------------------------------- requirements
@app.get("/api/requirements")
def requirements():
    return {"register": measure.REQUIREMENTS, "configs": measure.CONFIGS, "rule_version": RULE_VERSION}


# --------------------------------------------------------------- terrain
@app.get("/api/terrain/meta")
def terrain_meta():
    out = {"source": terrain.SOURCE, "areas": {}}
    for a in terrain.AREAS:
        d = terrain.dem(a)
        ok = d.get("status") == "ok"
        out["areas"][a] = {"status": d.get("status"), "bbox": terrain.AREAS[a]["bbox"], "error": d.get("error"),
                           "range_m": [round(float(np.nanmin(d["elev"])), 2), round(float(np.nanmax(d["elev"])), 2)] if ok else None,
                           "grid_m": round(d["px_m"][0], 1) if ok else None, "retrieved_at": d.get("retrieved_at")}
    return out


@app.get("/api/terrain/overlay.png")
def terrain_png(area: str = "district"):
    o = terrain.overlay(area if area in terrain.AREAS else "district")
    if o.get("status") != "ok":
        raise HTTPException(503, f"Terrain unavailable: {o.get('error')}")
    return Response(o["png"], media_type="image/png", headers={"Cache-Control": "max-age=3600"})


@app.get("/api/terrain/layer")
def terrain_layer(area: str = "district"):
    area = area if area in terrain.AREAS else "district"
    o = terrain.overlay(area)
    if o.get("status") != "ok":
        return {"status": "unavailable", "error": o.get("error")}
    return {k: v for k, v in o.items() if k != "png"} | {"image_url": f"/api/terrain/overlay.png?area={area}"}


@app.get("/api/terrain/point")
def terrain_point(lon: float, lat: float):
    return terrain.point(lon, lat)


@app.post("/api/terrain/profile")
def terrain_profile(body: dict = Body(...)):
    coords = body.get("coords") or []
    if len(coords) < 2:
        raise HTTPException(422, "Need at least two coordinates")
    return terrain.profile(coords[:400])


@app.get("/api/terrain/fields")
def terrain_fields():
    for f in demo_data.FIELDS:
        if f["id"] not in _TERRAIN_STATS:
            _TERRAIN_STATS[f["id"]] = terrain.field_stats(ring_lonlat(f["poly"]))
    return _TERRAIN_STATS


# ------------------------------------------------------------ live data
def _live_valid_time():
    # latest hour that both AZMET (hour-ending values) and an HRRR analysis are likely to have published
    return (datetime.now(MST) - timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)


@app.get("/api/live/estimate")
def live_estimate(field_id: str = "A", time: str | None = None):
    f = _field(field_id)
    lon, lat = to_lonlat(*geo_centroid(f["poly"]))
    vt = _t(time) if time else _live_valid_time()
    e = realdata.estimate(lat, lon, vt)
    if e.get("model"):
        e["model_profile_analysis"] = profile.analyze_model_profile(e["model"]["profile"])
    e["local_paired_sensor"] = bool(f["sensor_id"])
    e["local_paired_sensor_note"] = ("This field's paired-height mast exists only in the SIMULATED demo; the real data here are regional."
                                     if f["sensor_id"] else "No local paired-height sensor at this field.")
    return e


@app.get("/api/live/nws")
def live_nws(field_id: str = "A"):
    f = _field(field_id)
    lon, lat = to_lonlat(*geo_centroid(f["poly"]))
    return realdata.nws_hourly(lat, lon)


@app.get("/api/live/validation")
def live_validation(day: str | None = None):
    d = (datetime.fromisoformat(day).replace(tzinfo=MST) if day
         else (datetime.now(MST) - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0))
    return realdata.validate(d)


@app.get("/api/live/model_grid")
def live_model_grid():
    vt = _live_valid_time()
    m = realdata.hrrr(vt.astimezone(timezone.utc), 0)
    if m.get("status") != "ok":
        return m
    return {"status": "ok", "cells": [{"lat": c["lat"], "lon": c["lon"], "t2m_f": c["t2m_f"], "wind10_mph": c["wind10_mph"]} for c in m["cells"]],
            "resolution": m["resolution"], "valid_mst": m["valid_mst"], "cycle_utc": m["cycle_utc"], "source": m["source"]}


@app.get("/api/live/stations")
def live_stations():
    return [realdata.station_meta(s) for s in realdata.STATIONS]


# --------------------------------------------------------- plan accept
@app.post("/api/schedule/accept")
def accept_plan(body: dict = Body(default={})):
    p = STATE["plan"] or _plan("initial")
    who = (body.get("operator") or "").strip() or "Operator (unnamed)"
    STATE["accepted"] = {"by": who, "at": datetime.now(MST).isoformat(timespec="seconds"), "order": p["order"],
                         "generated_at": p["generated_at"], "rule_version": p["rule_version"]}
    store.record("plan_accepted", f"Plan accepted by {who}: {' → '.join(p['order'])}", {"accepted": STATE["accepted"], "jobs": p["jobs"]},
                 scenario_time=SCENARIO.now.isoformat(), simulated=True)
    return STATE["accepted"]


@app.get("/api/schedule/accepted")
def accepted_plan():
    return STATE.get("accepted") or {"status": "none"}


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





# --------------------------------------------------------- observations
OBS_ITEMS = {"dust_suspended": ["yes", "no", "not_checked"], "smoke_layer": ["yes", "no", "not_checked"],
             "fog": ["yes", "no", "not_checked"], "dew": ["yes", "no", "not_checked"], "frost": ["yes", "no", "not_checked"],
             "cloud_cover": ["clear", "partly", "overcast", "not_checked"], "wind_variability": ["steady", "variable", "not_checked"]}


@app.get("/api/observations")
def observations(field_id: str | None = None):
    return {"items": OBS_ITEMS, "observations": store.list_observations(field_id),
            "rules": "Supporting evidence only. Signs of stable air add caution; 'no' or 'not checked' never establishes safe conditions or overrides measured risk."}


@app.post("/api/observations")
def add_observation(body: dict = Body(...)):
    f = _field(body.get("field_id"))
    items = {k: (body.get("items") or {}).get(k, "not_checked") for k in OBS_ITEMS}
    for k, v in items.items():
        if v not in OBS_ITEMS[k]:
            raise HTTPException(422, f"Invalid value for {k}: {v}")
    lon, lat = to_lonlat(*geo_centroid(f["poly"]))
    o = {"field_id": f["id"], "observer": (body.get("observer") or "").strip() or None, "lat": body.get("lat") or lat, "lon": body.get("lon") or lon,
         "scenario_time": _t(body.get("time")).isoformat(), "items": items, "notes": (body.get("notes") or "").strip() or None}
    oid = store.add_observation(o)
    store.record("observation", f"Field observation at {f['name']} by {o['observer'] or 'unnamed observer'}: " +
                 ", ".join(f"{k.replace('_', ' ')}={v}" for k, v in items.items() if v != "not_checked") or "nothing checked",
                 o, field_id=f["id"], scenario_time=o["scenario_time"], simulated=False)
    return {"id": oid, **o}


# ---------------------------------------------------------------- forecast
forecast.warm()  # train in the background at startup (~2 s)
_FCST_LOGGED = set()


@app.get("/api/forecast/model")
def forecast_model():
    m = forecast.model()
    return {"model": m.info, "skill": m.metrics}


@app.get("/api/forecast")
def get_forecast(field_id: str, time: str | None = None, horizon_h: int = 12):
    f = _field(field_id)
    at = SCENARIO.floor_slot(_t(time))
    if not f["sensor_id"]:
        m = forecast.model()
        return {"field_id": field_id, "status": "not_assessed", "hours": [], "window": None, "warning": None,
                "model": m.info, "skill": m.metrics,
                "message": "No paired-height sensor covers this field, so no forecast can be issued."}
    r = forecast.forecast(SCENARIO, f["sensor_id"], at, STATE["overrides"], max(1, min(12, horizon_h)))
    r["field_id"] = field_id
    key = (field_id, r["issued_at"])
    if r.get("hours") and key not in _FCST_LOGGED:
        _FCST_LOGGED.add(key)
        w = r["window"]
        summary = (f"ML outlook for {f['name']} issued {r['issued_at'][11:16]}: " +
                   (f"next likely window {w['start'][11:16]}-{w['end'][11:16]} (P(flag) <= {w['max_p']:.0%})" if w else "no low-probability window in the next 12 h") +
                   (f"; warning: {r['warning']['text']}" if r.get("warning") else ""))
        store.record("forecast", summary, {"model_version": forecast.MODEL_VERSION, "inputs": r["inputs"], "hours": r["hours"],
                                           "window": w, "warning": r.get("warning")},
                     field_id=field_id, scenario_time=r["issued_at"])
    return r


# keep the static mount last so API routes registered above take precedence
app.mount("/", StaticFiles(directory=WEB), name="web")
