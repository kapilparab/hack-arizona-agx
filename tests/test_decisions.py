"""Versioned decisions, persistence, trends, field observations and surface checks."""
import os
from datetime import datetime, timedelta

os.environ.setdefault("OBSERVAIR_DB", ":memory:")

from fastapi.testclient import TestClient  # noqa: E402

from app import engine  # noqa: E402
from app.config import MST, thresholds  # noqa: E402
from app.main import app  # noqa: E402

T0 = datetime(2026, 11, 16, 9, 0, tzinfo=MST)


def lv(h, T, W=5, D=0):
    return {"height_ft": h, "ref": "ground", "temp_f": T, "temp_observed_at": T0.isoformat(), "temp_accuracy_f": 0.5,
            "wind_installed": True, "wind_height_ft": h, "wind_ref": "ground", "wind_mph": W, "dir_from_deg": D}


def rd(tl, th, t=T0):
    r = {"sensor_id": "T", "observed_at": t.isoformat(), "kind": "simulated_observation", "source": "t",
         "lower": lv(5, tl), "upper": lv(30, th), "rh_pct": 40, "rain_prob_pct": 5}
    r["lower"]["temp_observed_at"] = r["upper"]["temp_observed_at"] = t.isoformat()
    return r


def test_one_clean_reading_after_inversion_is_only_caution():
    prev = rd(50, 53, T0 - timedelta(minutes=15))           # +3 °F inversion
    a = engine.assess(rd(55, 54), T0, prev_reading=prev)     # now cooler aloft
    assert a["status"] == engine.CAUTION
    assert any(c["id"] == "inversion_persistence" for c in a["checks"])
    b = engine.assess(rd(55, 54), T0, prev_reading=rd(55, 54.2, T0 - timedelta(minutes=15)))
    assert b["status"] == engine.GO


def test_trend_classification_weakening_does_not_clear():
    m = {"delta_t_uncertainty_f": 0.71, "delta_t_f": 2.0}
    c = engine.classify_trend({"per_hour_f": -2.5, "points": 5, "window_min": 60}, m, thresholds())
    assert c["class"] == "weakening" and "does not clear" in c["text"]
    u = engine.classify_trend({"per_hour_f": 0.3, "points": 5, "window_min": 60}, m, thresholds())
    assert u["class"] == "uncertain"
    assert engine.classify_trend(None, m, thresholds())["class"] == "uncertain"


def test_observation_adds_caution_but_never_clears():
    obs_signs = [{"id": 1, "observer": "PCA", "scenario_time": T0.isoformat(), "items": {"dust_suspended": "yes"}}]
    obs_none = [{"id": 2, "observer": "PCA", "scenario_time": T0.isoformat(), "items": {k: "no" for k in ("dust_suspended", "smoke_layer", "fog", "dew", "frost")}}]
    assert engine.assess(rd(55, 54), T0, observations=obs_signs)["status"] == engine.CAUTION
    stop = engine.assess(rd(50, 53), T0, observations=obs_none)
    assert stop["status"] == engine.STOP                     # "no signs" cannot override a measured inversion


def test_decision_id_is_shared_across_screens_and_records():
    c = TestClient(app)
    c.post("/api/scenario/reset", json={})
    t = c.get("/api/meta").json()["scenario"]["now"]
    a = c.get("/api/assess", params={"field_id": "A", "time": t}).json()
    a2 = c.get("/api/assess/all", params={"time": t}).json()
    e = c.get("/api/explain", params={"topic": "hold", "field_id": "A", "time": t}).json()
    rid = c.post("/api/records/snapshot", json={"field_id": "A", "time": t}).json()["id"]
    rec = next(r for r in c.get("/api/records").json() if r["id"] == rid)
    m = c.post("/api/monitor", json={"job_id": "J-A", "time": t}).json()
    assert a["decision_id"] == e["decision_id"] == rec["payload"]["decision_id"] == m["decision_id"]
    assert a["decision_id"].startswith("d-") and a2["fields"][0]["field_id"] == "A"


def test_alert_needs_consecutive_clear_checks():
    c = TestClient(app)
    c.post("/api/scenario/reset", json={})
    plan = c.post("/api/schedule", json={}).json()
    ja = next(r for r in plan["jobs"] if r["job_id"] == "J-A")
    start = datetime.fromisoformat(ja["start"])
    c.post("/api/scenario/inject", json={"field_id": "A", "time": start.isoformat(), "duration_min": 15})
    assert c.post("/api/monitor", json={"job_id": "J-A", "time": start.isoformat()}).json()["critical"]
    t1 = (start + timedelta(minutes=15)).isoformat()
    m1 = c.post("/api/monitor", json={"job_id": "J-A", "time": t1}).json()
    assert not m1["critical"] and m1["cleared_alerts"] == [] and m1["clearing"]          # one clean check: still active
    m2 = c.post("/api/monitor", json={"job_id": "J-A", "time": (start + timedelta(minutes=30)).isoformat()}).json()
    assert m2["cleared_alerts"]                                                         # second clean check clears it


def test_surface_checks_keep_unknowns_explicit():
    c = TestClient(app)
    c.post("/api/scenario/reset", json={})
    plan = c.post("/api/schedule", json={}).json()
    rb = next(r for r in plan["jobs"] if r["job_id"] == "J-B")
    s = {x["id"]: x for x in rb["surface"]}
    assert set(s) == {"drift", "rainfast", "runoff", "wetness", "activation"}
    assert s["runoff"]["status"] == "unknown" and s["activation"]["status"] == "unknown"
    assert rb["pre_checks"] and "fresh paired-height" in rb["pre_checks"][0]


def test_field_observation_api_records_and_validates():
    c = TestClient(app)
    c.post("/api/scenario/reset", json={})
    r = c.post("/api/observations", json={"field_id": "B", "observer": "Demo PCA", "items": {"fog": "yes", "cloud_cover": "clear"}})
    assert r.status_code == 200 and r.json()["items"]["dust_suspended"] == "not_checked"
    assert c.post("/api/observations", json={"field_id": "B", "items": {"fog": "maybe"}}).status_code == 422
    assert any(x["kind"] == "observation" for x in c.get("/api/records").json())


def test_schedule_start_decision_matches_status_screen():
    c = TestClient(app)
    c.post("/api/scenario/reset", json={})
    plan = c.post("/api/schedule", json={}).json()
    r = next(x for x in plan["jobs"] if x["scheduled"])
    fid = next(j for j in c.get("/api/jobs").json() if j["id"] == r["job_id"])["field_id"]
    a = c.get("/api/assess", params={"field_id": fid, "time": r["start"]}).json()
    assert r["start_decision_id"] == a["decision_id"]


def test_airblast_nozzles_explain_what_is_missing():
    c = TestClient(app)
    c.post("/api/scenario/reset", json={})
    ev = c.post("/api/equipment/evaluate", json={"field_id": "D", "unit_id": "U2"}).json()
    ne = ev["nozzle_engine"]
    assert ne["status"] == "not_modelled" and ne["candidates"] == []
    needs = {n["label"]: n for n in ne["needs"]}
    assert needs["Tree height"]["value"] == "12.0 ft"            # from the field record
    assert needs["Skirt height"]["value"] is None                 # unknowns stay explicit
    assert ne["advisor"]["url"].startswith("https://ucanr.edu")
