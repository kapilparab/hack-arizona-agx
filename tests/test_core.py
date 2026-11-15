import copy
import os
from datetime import date, datetime, timedelta

os.environ["CANOPYGUARD_DB"] = ":memory:"

import pytest  # noqa: E402

from app import catalog, demo_data, engine, equipment, regional, scheduler, store  # noqa: E402
from app.config import MST  # noqa: E402
from app.geo import angle_diff  # noqa: E402
from app.scenario import Scenario  # noqa: E402

DAY = date(2026, 11, 16)


@pytest.fixture
def scn():
    return Scenario(DAY)


def reading(t, tl=60, th=58, wl=5, wh=6, dl=350, dh=10):
    lv = lambda h, T, W, D: {"height_ft": h, "ref": "ground", "temp_f": T, "temp_observed_at": t.isoformat(), "temp_accuracy_f": 0.5,
                             "wind_height_ft": h, "wind_ref": "ground", "wind_mph": W, "dir_from_deg": D, "wind_installed": True}
    return {"sensor_id": "T", "observed_at": t.isoformat(), "kind": "simulated_observation", "source": "test",
            "lower": lv(5, tl, wl, dl), "upper": lv(30, th, wh, dh), "rh_pct": 40, "rain_prob_pct": 5}


T0 = datetime(2026, 11, 16, 9, 0, tzinfo=MST)


# ---------------------------------------------------------------- engine
def test_angle_wraparound():
    assert angle_diff(350, 10) == 20
    assert angle_diff(10, 350) == 20
    assert angle_diff(0, 180) == 180
    assert angle_diff(90, 270) == 180
    assert angle_diff(359, 1) == 2


def test_direction_shear_uses_circular_difference():
    a = engine.assess(reading(T0, dl=350, dh=10), T0)
    assert a["metrics"]["dir_diff_deg"] == 20
    assert a["status"] == engine.GO


def test_clear_inversion_is_stop_and_ground_only_misses_it():
    a = engine.assess(reading(T0, tl=48, th=52, wl=4), T0)
    assert a["status"] == engine.STOP
    assert a["ground_only"]["status"] == engine.GO
    assert a["blind_spot"] is True


def test_inversion_within_uncertainty_is_caution_not_stop():
    a = engine.assess(reading(T0, tl=50, th=50.4), T0)  # +0.4 < 0.71 combined uncertainty
    inv = next(c for c in a["checks"] if c["id"] == "inversion")
    assert inv["status"] == engine.CAUTION


@pytest.mark.parametrize("field,value", [("temp_f", None), ("wind_mph", None), ("dir_from_deg", None), ("temp_f", float("nan")), ("wind_mph", -3)])
def test_missing_or_invalid_never_go(field, value):
    r = reading(T0)
    r["upper"][field] = value
    a = engine.assess(r, T0)
    assert a["status"] == engine.INSUFFICIENT


def test_no_reading_is_insufficient():
    assert engine.assess(None, T0)["status"] == engine.INSUFFICIENT


def test_stale_reading_is_insufficient():
    a = engine.assess(reading(T0 - timedelta(minutes=45)), T0)
    assert a["status"] == engine.INSUFFICIENT


def test_wind_limits():
    assert engine.assess(reading(T0, wl=2.0), T0)["status"] == engine.STOP
    assert engine.assess(reading(T0, wl=11.0, wh=12), T0)["status"] == engine.STOP
    assert engine.assess(reading(T0, wl=5.0), T0)["status"] == engine.GO


def test_calm_direction_comparison_flagged_unreliable():
    a = engine.assess(reading(T0, wl=3.2, wh=1.0, dl=0, dh=180), T0)
    d = next(c for c in a["checks"] if c["id"] == "dir_shear")
    assert "unreliable" in d["measured"]
    assert a["metrics"]["dir_comparison_reliable"] is False


def test_go_text_does_not_promise_safety():
    a = engine.assess(reading(T0), T0)
    assert a["status"] == engine.GO
    assert "not a guarantee" in a["reason"]


def test_neighbor_wind_from_vs_toward():
    # Field A with wind FROM north moves air TOWARD the south, where neighbor N1 sits.
    f = demo_data.field("A")
    a = engine.assess(reading(T0, dl=0, dh=0), T0, f, demo_data.SENSITIVE)
    n1 = next(n for n in a["neighbors"] if n["area_id"] == "N1")
    assert n1["downwind"]["lower"]["toward_deg"] == 180
    assert n1["blocking"] is True
    assert a["status"] == engine.STOP
    # wind FROM south: air moves north, away from N1
    a2 = engine.assess(reading(T0, dl=180, dh=180), T0, f, demo_data.SENSITIVE)
    n1b = next(n for n in a2["neighbors"] if n["area_id"] == "N1")
    assert n1b["blocking"] is False


# -------------------------------------------------------------- scenario
def test_demo_story_field_a_dawn(scn):
    a = engine.assess(scn.reading("S1", scn.now), scn.now, demo_data.field("A"), demo_data.SENSITIVE)
    assert a["status"] == engine.STOP
    assert a["ground_only"]["status"] == engine.GO
    assert a["reading"]["lower"]["height_ft"] == 5 and a["reading"]["upper"]["height_ft"] == 30
    assert a["reading"]["kind"].startswith("simulated")


def test_telemetry_gap_is_insufficient(scn):
    t = scn.day0 + timedelta(hours=12, minutes=15)
    a = engine.assess(scn.reading("S2", t), t)
    assert a["status"] == engine.INSUFFICIENT


# ------------------------------------------------------------- equipment
def test_drone_cannot_verify_asabe_requirement():
    ev = equipment.evaluate(demo_data.field("B"), "U3", None, catalog.PRODUCTS["demo_r"])
    assert not ev["compatible"]
    assert any(i["code"] == "droplet_unverifiable" for i in ev["issues"])


def test_teejet_tip_not_compatible_with_drone():
    ev = equipment.evaluate(demo_data.field("B"), "U3", {"nozzle_id": "teejet_aixr"}, catalog.PRODUCTS["demo_r"])
    assert any(i["code"] == "nozzle_incompatible" for i in ev["issues"])


def test_airblast_on_row_crop_blocked():
    ev = equipment.evaluate(demo_data.field("B"), "U2", None, catalog.PRODUCTS["demo_r"])
    assert any(i["code"] == "crop_mismatch" for i in ev["issues"])


def test_documented_class_too_fine_blocks():
    # TeeJet guide p.76: XR11004 at 30 psi is Medium; Demo Herbicide H requires Coarse or coarser.
    ev = equipment.evaluate(demo_data.field("B"), "U1", {"nozzle_id": "teejet_xr", "orifice_size": "04", "pressure_psi": 30}, catalog.PRODUCTS["demo_h"])
    assert any(i["code"] == "droplet_too_fine" for i in ev["issues"])


def test_undocumented_pressure_falls_back_to_operator_entry_only():
    ev = equipment.evaluate(demo_data.field("B"), "U1", {"nozzle_id": "teejet_xr", "orifice_size": "04", "pressure_psi": 45}, catalog.PRODUCTS["demo_r"])
    assert any(i["code"] == "droplet_class_missing" for i in ev["issues"])
    ev2 = equipment.evaluate(demo_data.field("B"), "U1", {"nozzle_id": "teejet_xr", "orifice_size": "04", "pressure_psi": 45, "droplet_class_entered": "M"}, catalog.PRODUCTS["demo_r"])
    ok = next(i for i in ev2["issues"] if i["code"] == "droplet_ok")
    assert "Operator-entered" in ok["message"]


def test_herbicide_buffer_persists_across_equipment():
    p = catalog.PRODUCTS["demo_h"]
    ev = equipment.evaluate(demo_data.field("A"), "U1", None, p)
    assert any(i["code"] == "buffer_untreated" for i in ev["issues"])
    assert ev["path"]["excluded_acres"] > 0
    ev2 = equipment.evaluate(demo_data.field("A"), "U3", None, p)  # drone: also method not permitted
    assert any(i["code"] == "buffer_untreated" for i in ev2["issues"])
    assert any(i["code"] == "method_not_permitted" for i in ev2["issues"])


def test_paths_respect_exclusion():
    ev = equipment.evaluate(demo_data.field("C"), "U1", None, catalog.PRODUCTS["demo_r"])
    assert ev["path"]["excluded_acres"] > 0
    assert any(s["type"] == "transit" for s in ev["path"]["segments"])


def test_drone_duration_includes_battery_reloads():
    ev = equipment.evaluate(demo_data.field("A"), "U3", None, catalog.PRODUCTS["unknown"])
    est = ev["estimate"]
    assert est["loads"] > 1
    assert est["reload_min"] == (est["loads"] - 1) * (3 + 3)


def test_pressure_mismatch_warning():
    ev = equipment.evaluate(demo_data.field("B"), "U1", {"pressure_psi": 20}, catalog.PRODUCTS["demo_r"])
    assert any(i["code"] == "rate_mismatch" for i in ev["issues"])


# ------------------------------------------------------------- scheduler
def _jobs(scn):
    return store.default_jobs(scn)


def test_best_order_beats_request_order(scn):
    p = scheduler.plan(scn, _jobs(scn))
    assert p["sequences_evaluated"] == 24
    assert p["order"][:2] == ["J-B", "J-A"]
    assert "J-B" in p["chosen"]["scheduled"]
    assert "J-B" in p["default"]["unscheduled"]


def test_travel_and_setup_precede_start(scn):
    p = scheduler.plan(scn, _jobs(scn))
    for r in p["jobs"]:
        if r["scheduled"]:
            assert datetime.fromisoformat(r["start"]) - datetime.fromisoformat(r["depart"]) >= timedelta(minutes=r["travel_min"] + r["setup_min"])


def test_jobs_finish_before_deadline_and_rain_interval(scn):
    jobs = _jobs(scn)
    p = scheduler.plan(scn, jobs)
    for r in p["jobs"]:
        if not r["scheduled"]:
            continue
        j = next(x for x in jobs if x["id"] == r["job_id"])
        end = datetime.fromisoformat(r["end"])
        assert end <= datetime.fromisoformat(j["latest_completion"])
        t = end
        while t < end + timedelta(hours=4):
            assert scn.rain_prob(t) < 40
            t += timedelta(minutes=15)


def test_weather_never_relaxed(scn):
    p = scheduler.plan(scn, _jobs(scn))
    ctx = scheduler.Context(scn, _jobs(scn))
    for r in p["jobs"]:
        if r["scheduled"]:
            f = demo_data.field(next(j for j in _jobs(scn) if j["id"] == r["job_id"])["field_id"])
            t = datetime.fromisoformat(r["start"])
            while t < datetime.fromisoformat(r["end"]):
                ok, cause, _ = ctx.suit(f, "demo_r", t)
                assert ok, (r["job_id"], t, cause)
                t += timedelta(minutes=15)


def test_infeasible_job_stays_unscheduled_with_message(scn):
    jobs = _jobs(scn)
    jobs[1]["latest_completion"] = (scn.day0 + timedelta(hours=6)).isoformat()  # B by 06:00: impossible
    p = scheduler.plan(scn, jobs)
    rb = next(r for r in p["jobs"] if r["job_id"] == "J-B")
    assert rb["scheduled"] is False
    assert rb["message"].startswith("No suitable window found before the requested deadline")


def test_field_without_sensor_unscheduled(scn):
    p = scheduler.plan(scn, _jobs(scn))
    rd = next(r for r in p["jobs"] if r["job_id"] == "J-D")
    assert rd["scheduled"] is False and rd["reason_code"] == "data"


def test_unknown_rainfast_marks_check_incomplete(scn):
    jobs = [copy.deepcopy(_jobs(scn)[1])]
    jobs[0]["product_id"] = "unknown"
    p = scheduler.plan(scn, jobs)
    r = p["jobs"][0]
    assert r["scheduled"] and r["rain_ok"] is None and "incomplete" in r["rain_note"]


def test_incompatible_equipment_unscheduled(scn):
    jobs = [copy.deepcopy(_jobs(scn)[1])]
    jobs[0]["unit_id"] = "U3"  # drone cannot verify product droplet requirement
    p = scheduler.plan(scn, jobs)
    assert p["jobs"][0]["reason_code"] == "equipment_conflict"


# ------------------------------------------------------------ regional
def test_regional_failure_is_unavailable_not_fabricated():
    regional._cache.clear()

    def boom(*a, **k):
        raise OSError("offline")
    r = regional.fetch(1.0, 1.0, opener=boom)
    assert r["status"] == "unavailable"
    assert r["values"] == []


# ----------------------------------------------------------------- API
def test_api_flow_and_csv_export():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    c.post("/api/scenario/reset", json={})
    m = c.get("/api/meta").json()
    assert m["scenario"]["status"] == "simulated"
    a = c.get("/api/assess", params={"field_id": "A"}).json()
    assert a["status"] == "STOP" and a["ground_only"]["status"] == "GO"
    p = c.post("/api/schedule", json={"reason": "test"}).json()
    assert p["order"][0] == "J-B"
    e = c.get("/api/explain", params={"topic": "order", "lang": "es"}).json()
    assert e["mode"] == "rule_based" and e["lang"] == "es"
    for topic in ("hold", "neighbors", "missing", "rain", "equipment"):
        r = c.get("/api/explain", params={"topic": topic, "field_id": "A"})
        assert r.status_code == 200, topic
    # monitoring: inject a critical change during job A and expect one grouped alert
    start = p["jobs"][1]["start"]
    c.post("/api/scenario/inject", json={"field_id": "A", "time": start})
    m1 = c.post("/api/monitor", json={"job_id": "J-A", "time": start, "pass_index": 3}).json()
    assert m1["critical"] and m1["new_alert"]
    m2 = c.post("/api/monitor", json={"job_id": "J-A", "time": start, "pass_index": 3}).json()
    assert m2["critical"] and not m2["new_alert"]
    al = c.get("/api/alerts", params={"active_only": True}).json()
    assert len(al) == 1 and al[0]["occurrences"] == 2
    ack = c.post(f"/api/alerts/{al[0]['id']}/ack", json={"operator": "Test PCA"}).json()
    assert ack["acknowledged_by"] == "Test PCA"
    csv = c.get("/api/records/export.csv").text
    assert csv.startswith("id,recorded_at,scenario_time,kind")
    assert "alert" in csv and "ack" in csv and "cg-rules" in csv
    bad = c.post("/api/jobs", json={"field_id": "A"})
    assert bad.status_code == 422


def test_recommend_ranks_compatible_scheduled_unit_first(scn):
    r = scheduler.recommend(scn, _jobs(scn), "B")
    assert r["recommended_unit"] == "U1"
    first = r["options"][0]
    assert first["compatible"] and first["scheduled"]
    drone = next(o for o in r["options"] if o["unit_id"] == "U3")
    assert not drone["compatible"] and drone["why"].startswith("Blocked") and "droplet class" in drone["why"]


def test_recommend_never_recommends_without_window(scn):
    r = scheduler.recommend(scn, _jobs(scn), "D")
    assert r["recommended_unit"] is None
    assert r["message"].startswith("No equipment option gives a suitable window")


def test_recommend_economics_and_honest_savings(scn):
    r = scheduler.recommend(scn, _jobs(scn), "B")
    best = next(o for o in r["options"] if o["unit_id"] == r["recommended_unit"])
    e = best["economics"]
    assert e["on_site_min"] == e["travel_min"] + e["setup_min"] + e["job_min"]
    assert e["total_usd"] == e["labor_usd"] + e["machine_usd"] or abs(e["total_usd"] - e["labor_usd"] - e["machine_usd"]) <= 1
    assert 0 < e["spray_share_pct"] <= 100 and e["acres_per_hour"] > 0
    ids = {s["unit_id"] for s in r["savings"]}
    assert "U2" not in ids                      # wrong-crop airblast is never used to claim a saving
    drone = next(s for s in r["savings"] if s["unit_id"] == "U3")
    assert drone["reference_only"] is True      # blocked units are labeled reference only
    assert "Demo cost inputs" in r["cost_basis"]["source"]
    assert r["sequencing"] and "request order" in r["sequencing"]
