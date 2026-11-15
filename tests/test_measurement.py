"""Measurement model, interpolation, nozzle engine and live-data honesty tests."""
import os
from datetime import datetime, timedelta

os.environ.setdefault("CANOPYGUARD_DB", ":memory:")

from app import engine, nozzles, profile, realdata  # noqa: E402
from app.config import MST  # noqa: E402
from app.measure import classify_pair  # noqa: E402

T0 = datetime(2026, 11, 16, 6, 0, tzinfo=MST)


def lv(h, ref, T, W=None, D=None, wind=True, wh=None, obs=T0):
    return {"height_ft": h, "ref": ref, "temp_f": T, "temp_observed_at": obs.isoformat(), "temp_accuracy_f": 0.5,
            "wind_installed": wind, "wind_height_ft": wh or h, "wind_ref": ref, "wind_mph": W, "dir_from_deg": D}


def rd(lo, up):
    return {"sensor_id": "T", "observed_at": T0.isoformat(), "kind": "simulated_observation", "source": "test", "lower": lo, "upper": up,
            "rh_pct": 40, "rain_prob_pct": 5}


def test_config_classification_is_not_interchangeable():
    assert classify_pair(0.75, 9, "canopy") == "near_surface"
    assert classify_pair(5, 30, "ground") == "challenge_tower"
    assert classify_pair(5, 30, "canopy") == "other"
    assert classify_pair(2, 9, "canopy") == "other"


def test_misaligned_pair_is_insufficient():
    up = lv(9, "canopy", 52, wind=False, obs=T0 - timedelta(minutes=12))
    a = engine.assess(rd(lv(0.75, "canopy", 50, 5, 350, wh=6.6), up), T0)
    assert a["status"] == engine.INSUFFICIENT and "apart" in a["checks"][0]["measured"]


def test_different_reference_surfaces_are_not_a_pair():
    a = engine.assess(rd(lv(5, "ground", 50, 5, 350), lv(9, "canopy", 49, 6, 350)), T0)
    assert a["status"] == engine.INSUFFICIENT


def test_single_wind_height_shear_not_assessed():
    a = engine.assess(rd(lv(0.75, "canopy", 50, 5, 350, wh=6.6), lv(9, "canopy", 49, wind=False)), T0)
    shear = next(c for c in a["checks"] if c["id"] == "shear")
    assert shear["status"] == engine.NA and a["status"] == engine.GO


def test_temperature_not_extrapolated_and_interpolated_inside():
    r = rd(lv(5, "ground", 50, 5, 0), lv(30, "ground", 55, 6, 0))
    assert profile.temperature_at(2.0, r, 1.0)["status"] == "outside_measured_range"
    mid = profile.temperature_at(17.5, r, 1.0)
    assert mid["status"] == "interpolated" and abs(mid["value_f"] - 52.5) < 1e-6


def test_log_wind_increases_with_height_and_flags_inversion():
    r = rd(lv(5, "ground", 50, 4, 0), lv(30, "ground", 49, 8, 0))
    low, high = profile.wind_at(6, r, 1.0)["value_mph"], profile.wind_at(25, r, 1.0)["value_mph"]
    assert low < high
    rel = profile.at_release("drone", {"height_m": 3}, r, 1.0, inversion_flagged=True)
    assert rel["wind"]["status"] == "estimated_unreliable"


def test_model_profile_analysis_detects_surface_based_layer():
    lvls = [{"height_agl_m": 10, "t_f": 60.3}, {"height_agl_m": 39, "t_f": 60.4}, {"height_agl_m": 89, "t_f": 63.2}, {"height_agl_m": 172, "t_f": 62.0}]
    a = profile.analyze_model_profile(lvls)
    assert a["regime"].startswith("surface-based") and a["inversion_top_m"] == 89
    assert "not resolved" in a["resolution_note"]


def test_nozzle_formula_and_documented_operating_point():
    assert abs(nozzles.required_gpm(15, 8, 20) - 0.40404) < 1e-4
    r = nozzles.evaluate(15, 8, 20, min_class="M", pump_min_psi=15, pump_max_psi=75, release_height_in=20)
    best = next(c for c in r["candidates"] if c["id"] == r["recommended"])
    assert best["model"] == "AIXR11004" and best["droplet_class"] == "C"     # TeeJet p.94: 40-50 psi rows are C
    assert any("Smaller" in a for a in best["alternatives"])


def test_nozzle_no_candidate_when_requirement_unmet():
    r = nozzles.evaluate(15, 8, 20, min_class="VC", pump_min_psi=15, pump_max_psi=75, release_height_in=20)
    assert r["status"] == "none" and r["recommended"] is None


def test_nozzle_missing_essential_inputs_blocks():
    r = nozzles.evaluate(None, 8, 20)
    assert r["status"] == "blocked" and "carrier volume" in r["message"]


def test_live_data_failure_is_explicit_not_simulated(monkeypatch, tmp_path):
    monkeypatch.setattr(realdata, "CACHE", str(tmp_path))
    def boom(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr(realdata, "_get", boom)
    r = realdata.nws_hourly(32.66, -114.72)
    assert r["status"] == "unavailable" and "periods" not in r
    m = realdata.station_meta("az02")
    assert m["status"] == "unavailable"
