"""ML temporal forecaster: calibration, skill vs baselines, no look-ahead, API wiring."""
from datetime import timedelta

import numpy as np
from fastapi.testclient import TestClient

from app import forecast as F
from app.config import thresholds
from app.main import app
from app.scenario import SCENARIO

client = TestClient(app)


def test_beats_persistence_and_climatology_on_held_out_days():
    m = F.model().metrics
    assert m["brier"] < m["brier_persistence"]
    assert m["brier"] < m["brier_climatology"]
    assert m["skill_vs_persistence_pct"] > 0 and m["skill_vs_climatology_pct"] > 0


def test_calibrated_on_held_out_days():
    m = F.model().metrics
    assert m["calibration_error"] < 0.05
    for r in m["reliability"]:
        assert abs(r["mean_forecast"] - r["observed_rate"]) < 0.1


def test_skill_decays_with_lead_time():
    pl = F.model().metrics["per_lead"]
    assert pl[0]["brier"] < pl[-1]["brier"]


def test_flag_matches_engine_thresholds():
    t = thresholds()
    assert F.flag(np.array(1.0), np.array(5.0), t)          # inversion beyond ±0.71 °F
    assert not F.flag(np.array(0.5), np.array(5.0), t)      # within uncertainty, wind ok
    assert F.flag(np.array(-2.0), np.array(2.0), t)         # too calm
    assert F.flag(np.array(-2.0), np.array(12.0), t)        # too windy


def test_dawn_inversion_forecast_finds_later_window():
    r = F.forecast(SCENARIO, "S1", SCENARIO.now)
    assert r["flag_now"] is True
    assert r["hours"][0]["p_flag"] > 0.5                    # inversion persists at first lead
    assert r["window"] is not None and r["window"]["start"] > SCENARIO.now.isoformat()
    assert all(0 <= h["p_flag"] <= 1 for h in r["hours"])


def test_no_look_ahead():
    """The forecast must not change if future scenario readings change."""
    a = F.forecast(SCENARIO, "S1", SCENARIO.now)
    SCENARIO.inject("S1", SCENARIO.now + timedelta(hours=3), 60)
    try:
        b = F.forecast(SCENARIO, "S1", SCENARIO.now)
    finally:
        SCENARIO.reset_events()
    assert [h["p_flag"] for h in a["hours"]] == [h["p_flag"] for h in b["hours"]]


def test_api_forecast_and_record():
    r = client.get("/api/forecast", params={"field_id": "A"}).json()
    assert r["field_id"] == "A" and len(r["hours"]) == 12
    recs = client.get("/api/records", params={"kind": "forecast"}).json()
    items = recs["records"] if isinstance(recs, dict) else recs
    assert any(x["field_id"] == "A" for x in items)


def test_api_field_without_sensor_is_not_assessed():
    r = client.get("/api/forecast", params={"field_id": "D"}).json()
    assert r["status"] == "not_assessed" and r["hours"] == []


def test_api_model_card():
    r = client.get("/api/forecast/model").json()
    assert "isotonic" in r["model"]["algorithm"] and r["skill"]["test_days"] > 0
