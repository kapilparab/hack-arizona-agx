"""Scenario library: each scenario shows what it claims, switching resets demo state."""
import pytest
from fastapi.testclient import TestClient

from app import demo_data, engine
from app import forecast as F
from app.main import app
from app.scenario import DEFAULT_SCENARIO, LIBRARY, SCENARIO

client = TestClient(app)


@pytest.fixture(autouse=True)
def restore_default():
    yield
    client.post("/api/scenario/select", json={"id": DEFAULT_SCENARIO})


def _assess_a():
    f = demo_data.field("A")
    return engine.assess(SCENARIO.reading("S1", SCENARIO.now), SCENARIO.now, f, [], None, {})


@pytest.mark.parametrize("sid", list(LIBRARY))
def test_expected_status_at_start(sid):
    SCENARIO.select(sid)
    assert _assess_a()["status"] == LIBRARY[sid]["expected_now"]["S1"]


def test_katabatic_shear_is_a_ground_station_blind_spot():
    SCENARIO.select("katabatic-shear")
    a = _assess_a()
    assert a["ground_only"]["status"] == "GO" and a["blind_spot"]
    flagged = {c["id"] for c in a["checks"] if c["status"] == "CAUTION"}
    assert {"speed_shear", "dir_shear"} <= flagged
    assert not any(c["id"] == "inversion" and c["status"] != "GO" for c in a["checks"])


def test_evening_onset_outlook_warns_before_flag():
    SCENARIO.select("evening-onset")
    r = F.forecast(SCENARIO, "S1", SCENARIO.now)
    assert r["flag_now"] is False and r["warning"] is not None
    later = SCENARIO.reading("S1", SCENARIO.now.replace(hour=20))
    assert later["upper"]["temp_f"] - later["lower"]["temp_f"] > 1.0  # the inversion does form


def test_well_mixed_has_no_flags_through_the_morning():
    SCENARIO.select("well-mixed")
    for h in range(6, 12):
        at = SCENARIO.now.replace(hour=h, minute=0)
        f = demo_data.field("A")
        assert engine.assess(SCENARIO.reading("S1", at), at, f, [], None, {})["status"] == "GO"


def test_api_select_switches_clock_and_records():
    r = client.post("/api/scenario/select", json={"id": "evening-onset"}).json()
    assert r["scenario"]["id"] == "evening-onset" and r["scenario"]["now"][11:16] == "17:00"
    assert client.get("/api/meta").json()["scenario"]["id"] == "evening-onset"
    recs = client.get("/api/records", params={"kind": "scenario"}).json()
    items = recs["records"] if isinstance(recs, dict) else recs
    assert any("Evening inversion onset" in x["summary"] for x in items)


def test_api_lists_library_and_rejects_unknown():
    lib = client.get("/api/scenarios").json()
    assert {s["id"] for s in lib["scenarios"]} == set(LIBRARY)
    assert client.post("/api/scenario/select", json={"id": "nope"}).status_code == 404
