"""Product risk factors: volatility, mode of action and off-target hazard only tighten checks."""
import copy
from datetime import datetime, timedelta

from app import catalog, demo_data, engine
from app.config import MST
from app.geo import rect
from app.scenario import DEFAULT_SCENARIO, SCENARIO

P = catalog.PRODUCTS
FIELD_A = demo_data.field("A")
AT = datetime(2026, 7, 1, 10, 0, tzinfo=MST)


def reading(t_low, t_high, w_low=5.0, w_high=6.0, d_low=250, d_high=255):
    lv = lambda t, w, d, h: {"height_ft": h, "ref": "ground", "temp_f": t, "temp_observed_at": AT.isoformat(), "temp_accuracy_f": 0.5,
                             "wind_height_ft": h, "wind_ref": "ground", "wind_mph": w, "dir_from_deg": d,
                             "wind_observed_at": AT.isoformat(), "wind_installed": True}
    return {"sensor_id": "T", "observed_at": AT.isoformat(), "kind": "simulated_observation", "config": "challenge_tower", "source": "test",
            "lower": lv(t_low, w_low, d_low, 5.0), "upper": lv(t_high, w_high, d_high, 30.0), "rh_pct": 30}


def status(r, prod, areas=(), trend=None):
    a = engine.assess(r, AT, FIELD_A, list(areas), prod, {}, trend=trend)
    return a, {c["id"]: c["status"] for c in a["checks"]}


def test_heat_rules_by_volatility():
    hot = reading(92, 90)
    assert status(hot, P["demo_r"])[1]["product_volatility"] == "GO"        # low volatility: no heat rule
    assert status(hot, P["demo_h"])[1]["product_volatility"] == "CAUTION"   # moderate: Caution from 90 °F
    a, s = status(hot, P["demo_g"])
    assert s["product_volatility"] == "STOP" and a["status"] == "STOP"       # high: Stop from 90 °F
    assert status(reading(84, 82), P["demo_g"])[1]["product_volatility"] == "CAUTION"  # high: Caution from 80 °F


def test_weak_inversion_upgraded_only_for_volatile_products():
    weak = reading(60.0, 60.4)   # +0.4 °F, inside the ±0.71 °F combined uncertainty
    assert status(weak, P["demo_r"])[1]["inversion"] == "CAUTION"
    assert status(weak, P["demo_h"])[1]["inversion"] == "STOP"
    assert status(weak, P["demo_g"])[1]["inversion"] == "STOP"


def test_developing_inversion_caution_for_volatile_product():
    trend = {"per_hour_f": 1.2, "points": 5, "window_min": 60, "wind_per_hour_mph": -0.5}
    r = reading(64.0, 63.5)   # mixed now, upper warming relative to lower
    assert "product_vapor_window" not in status(r, P["demo_r"], trend=trend)[1]
    assert status(r, P["demo_g"], trend=trend)[1]["product_vapor_window"] == "CAUTION"


def test_high_hazard_raises_sensitive_crop_attention_to_stop():
    # wind from the north (0°) blows toward a crop block just south of Field A
    crop = {"id": "NX", "kind": "neighbor_crop", "name": "Test lettuce block", "poly": rect(-900, -120, -498, -20), "constraint": None}
    r = reading(60, 58, d_low=0, d_high=5)
    assert status(r, P["demo_r"], [crop])[1]["neighbor_NX"] == "CAUTION"
    a, s = status(r, P["demo_g"], [crop])
    assert s["neighbor_NX"] == "STOP" and a["status"] == "STOP"


def test_unknown_volatility_is_caution_not_go():
    assert status(reading(60, 58), P["unknown"])[1]["product_volatility"] == "CAUTION"


def test_product_rules_never_loosen():
    """For any reading, a volatile/high-hazard product is never less restrictive than a low-volatility one."""
    for tl, th, w in ((50, 54, 5), (60, 60.4, 5), (92, 90, 5), (70, 68, 2), (70, 68, 12)):
        r = reading(tl, th, w)
        low = engine.RANK[status(r, P["demo_r"])[0]["status"]]
        for pid in ("demo_h", "demo_g"):
            prod = copy.deepcopy(P[pid])
            prod["constraints"]["temp_range_f"] = {"value": None, "source": "test"}
            assert engine.RANK[status(r, prod)[0]["status"]] >= low


def test_evening_onset_weak_inversion_differs_by_product():
    SCENARIO.select("evening-onset")
    try:
        at = SCENARIO.now.replace(hour=18, minute=0)
        rd = SCENARIO.reading("S1", at)
        r = engine.assess(rd, at, FIELD_A, [], P["demo_r"], {}, prev_reading=SCENARIO.reading("S1", at - timedelta(minutes=15)))
        g = engine.assess(rd, at, FIELD_A, [], P["demo_g"], {}, prev_reading=SCENARIO.reading("S1", at - timedelta(minutes=15)))
        assert r["status"] == "CAUTION" and g["status"] == "STOP"
        assert "Possible weak inversion raised from Caution to Stop." in g["metrics"]["product_risk"]["adjustments"]
    finally:
        SCENARIO.select(DEFAULT_SCENARIO)
