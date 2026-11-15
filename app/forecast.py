"""Calibrated ML temporal forecaster: probability that a Stop-level drift flag will be
present 1-12 h ahead at a paired-height mast.

Idea adapted from the backend-implementation branch (HistGradientBoosting predicting
hourly P(unsafe)), rebuilt so the numbers it reports are measured, not asserted:

- Training data: a stochastic weather generator for paired-height masts (SIMULATED).
  Each synthetic day draws its own nocturnal inversion strength, burn-off and onset
  times, daytime lapse, night wind and afternoon wind peak, plus AR(1) noise, gust
  bursts and sensor noise. It is a demonstration climatology, not Yuma data.
- Target: the engine's Stop-level drift conditions at the target time:
  upper-minus-lower temperature above the combined sensor uncertainty (inversion), or
  lower wind outside the configured window (default 3-10 mph).
- Features use only what is known at issue time: current and 1-h-old readings,
  hour of day, lead time and target hour.
- Model: HistGradientBoostingClassifier, then isotonic calibration fitted on separate
  calibration days. Scores are computed on held-out test days against two baselines:
  conditional persistence (P(flag at lead | flag now)) and hourly climatology.

The forecast is advisory context. It never sets the current Go/Caution/Stop status,
which always comes from the measured readings in app.engine."""
import math
import threading
import time

import numpy as np

from app.config import thresholds

MODEL_VERSION = "obs-fcst-0.1.0"
SLOTS_PER_H = 4  # 15-minute generator resolution
LEADS_H = list(range(1, 13))
FEATURES = ["hod_sin", "hod_cos", "lead_h", "tgt_sin", "tgt_cos", "dT_f", "dT_change_1h_f",
            "wind_low_mph", "wind_change_1h_mph", "speed_diff_mph", "flag_now"]
BANDS = [(0.2, "low", "Low"), (0.5, "moderate", "Moderate"), (1.01, "high", "High")]


def _sig(x):
    return 1.0 / (1.0 + np.exp(-x))


# ------------------------------------------------------------- generator
def simulate(n_days: int, seed: int = 7):
    """Continuous 15-min series for one synthetic mast over n_days (SIMULATED).
    Returns dict of arrays: hod, dT (upper - lower, °F), w_lo, w_up (mph)."""
    rng = np.random.default_rng(seed)
    n = n_days + 1
    calm_night = rng.random(n) < 0.22                      # windy / cloudy nights: no inversion
    S = np.where(calm_night, rng.uniform(-0.6, 0.5, n), rng.uniform(0.8, 6.5, n))
    Wn = np.where(calm_night, rng.uniform(4.5, 11.0, n), rng.uniform(0.8, 6.5, n))
    burn = rng.uniform(6.8, 9.2, n) + 0.12 * np.clip(S, 0, None)  # stronger inversions burn off later
    onset = rng.uniform(17.3, 19.8, n)
    lapse = rng.uniform(0.8, 3.6, n)
    Wd = rng.uniform(4.5, 16.5, n)
    peak = rng.uniform(13.0, 16.0, n)
    scale = rng.uniform(0.45, 1.25, n)                     # height separation differs between masts

    hod = np.tile(np.arange(24 * SLOTS_PER_H) / SLOTS_PER_H, n_days)
    day = np.repeat(np.arange(n_days), 24 * SLOTS_PER_H)
    morning = hod < 12
    nd = np.where(morning, day, day + 1)                   # the night that is ending (AM) or starting (PM)
    stab = np.where(morning, 1 - _sig((hod - burn[day]) / 0.35), _sig((hod - onset[day]) / 0.6))
    daycurve = np.clip(np.sin(np.pi * (hod - 6) / 14), 0, None)
    dT = scale[nd] * (stab * S[nd] - (1 - stab) * lapse[day] * daycurve)
    bump = np.exp(-((hod - peak[day]) / 3.0) ** 2)
    w = stab * Wn[nd] + (1 - stab) * (Wn[nd] + (Wd[day] - Wn[nd]) * np.maximum(bump, 0.25))

    m = len(hod)
    ar_t, ar_w = np.zeros(m), np.zeros(m)
    et, ew = rng.normal(0, 0.22, m), rng.normal(0, 0.55, m)
    for i in range(1, m):
        ar_t[i] = 0.85 * ar_t[i - 1] + et[i]
        ar_w[i] = 0.85 * ar_w[i - 1] + ew[i]
    gust = np.zeros(m)
    for s in np.flatnonzero(rng.random(m) < 0.004):        # occasional wind surges, 1-2 h
        gust[s:s + rng.integers(4, 9)] += rng.uniform(4, 9)
    dT = dT + ar_t + rng.normal(0, 0.15, m)                # last term: sensor noise
    w_lo = np.clip(w + ar_w + gust, 0, None)
    w_up = w_lo * (1.1 + 0.7 * stab * rng.uniform(0.5, 1.0, m)) + rng.normal(0, 0.4, m)
    return {"hod": hod, "dT": dT, "w_lo": w_lo, "w_up": np.clip(w_up, 0, None)}


def flag(dT, w_lo, t):
    """Stop-level drift condition, same thresholds the engine uses."""
    u = math.sqrt(2) * t["sensor_temp_accuracy_f"]
    return (dT > u) | (w_lo < t["wind_min_mph"]) | (w_lo > t["wind_max_mph"])


def _features(hod, dT, dT_1h, w, w_1h, wu, lead, flag_now):
    tgt = (hod + lead) % 24
    return np.column_stack([np.sin(2 * np.pi * hod / 24), np.cos(2 * np.pi * hod / 24), lead,
                            np.sin(2 * np.pi * tgt / 24), np.cos(2 * np.pi * tgt / 24),
                            dT, dT - dT_1h, w, w - w_1h, wu - w, flag_now.astype(float)])


def dataset(series, t, rng, anchor_every=2):
    hod, dT, wl, wu = series["hod"], series["dT"], series["w_lo"], series["w_up"]
    y_all = flag(dT, wl, t)
    n = len(hod)
    idx = np.arange(SLOTS_PER_H, n - 12 * SLOTS_PER_H, anchor_every)
    wu_obs = wu[idx].copy()
    wu_obs[rng.random(len(idx)) < 0.3] = np.nan            # some masts have no upper anemometer
    X, Y, meta = [], [], []
    for L in LEADS_H:
        X.append(_features(hod[idx], dT[idx], dT[idx - SLOTS_PER_H], wl[idx], wl[idx - SLOTS_PER_H], wu_obs,
                           np.full(len(idx), L), y_all[idx]))
        Y.append(y_all[idx + L * SLOTS_PER_H])
        meta.append(np.column_stack([np.full(len(idx), L), (hod[idx] + L) % 24, y_all[idx]]))
    return np.vstack(X), np.concatenate(Y).astype(int), np.vstack(meta)


def _brier(p, y):
    return float(np.mean((p - y) ** 2))


# ----------------------------------------------------------------- model
class Forecaster:
    def __init__(self, seed=7, train_days=300, calib_days=60, test_days=60):
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.isotonic import IsotonicRegression
        t0 = time.time()
        t = thresholds()
        self.thresholds = t
        rng = np.random.default_rng(seed + 1)
        tr = dataset(simulate(train_days, seed), t, rng)
        ca = dataset(simulate(calib_days, seed + 100), t, rng)
        te = dataset(simulate(test_days, seed + 200), t, rng)

        self.clf = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.06, max_leaf_nodes=31,
                                                  l2_regularization=1.0, random_state=seed)
        self.clf.fit(tr[0], tr[1])
        self.iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        self.iso.fit(self.clf.predict_proba(ca[0])[:, 1], ca[1])

        # baselines fitted on training days only
        Ltr, Htr, Ftr = tr[2][:, 0], tr[2][:, 1].astype(int), tr[2][:, 2]
        self.persist = {(int(L), int(f)): float(tr[1][(Ltr == L) & (Ftr == f)].mean())
                        for L in LEADS_H for f in (0, 1) if ((Ltr == L) & (Ftr == f)).any()}
        self.clim = {h: float(tr[1][Htr == h].mean()) for h in range(24)}

        X, y, M = te
        p_raw = self.clf.predict_proba(X)[:, 1]
        p = self.iso.predict(p_raw)
        p_per = np.array([self.persist.get((int(L), int(f)), 0.5) for L, f in zip(M[:, 0], M[:, 2])])
        p_cli = np.array([self.clim[int(h)] for h in M[:, 1].astype(int)])
        b, bp, bc = _brier(p, y), _brier(p_per, y), _brier(p_cli, y)
        bins = np.linspace(0, 1, 11)
        rel = []
        for lo, hi in zip(bins[:-1], bins[1:]):
            m = (p >= lo) & ((p < hi) if hi < 1 else (p <= hi))
            if m.sum() >= 30:
                rel.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": int(m.sum()), "mean_forecast": round(float(p[m].mean()), 3),
                            "observed_rate": round(float(y[m].mean()), 3)})
        ece = sum(r["n"] * abs(r["mean_forecast"] - r["observed_rate"]) for r in rel) / max(1, sum(r["n"] for r in rel))
        per_lead = []
        for L in LEADS_H:
            m = M[:, 0] == L
            per_lead.append({"lead_h": L, "brier": round(_brier(p[m], y[m]), 4),
                             "brier_persistence": round(_brier(p_per[m], y[m]), 4),
                             "brier_climatology": round(_brier(p_cli[m], y[m]), 4)})
        self.metrics = {
            "test_rows": int(len(y)), "test_days": test_days, "base_rate": round(float(y.mean()), 3),
            "brier": round(b, 4), "brier_uncalibrated": round(_brier(p_raw, y), 4),
            "brier_persistence": round(bp, 4), "brier_climatology": round(bc, 4),
            "skill_vs_persistence_pct": round(100 * (1 - b / bp), 1),
            "skill_vs_climatology_pct": round(100 * (1 - b / bc), 1),
            "calibration_error": round(float(ece), 3), "reliability": rel, "per_lead": per_lead,
        }
        self.info = {"model_version": MODEL_VERSION, "algorithm": "HistGradientBoostingClassifier + isotonic calibration",
                     "features": FEATURES, "target": "Stop-level drift flag at target time (inversion beyond combined "
                     "sensor uncertainty, or lower wind outside the configured window)",
                     "training": {"days": train_days, "calibration_days": calib_days, "test_days": test_days, "seed": seed,
                                  "data": "Stochastic paired-height weather generator (SIMULATED, not field data)"},
                     "train_seconds": round(time.time() - t0, 2),
                     "baselines": {"persistence": "P(flag at lead | flag now), fitted on training days",
                                   "climatology": "P(flag) by target hour of day, fitted on training days"},
                     "limits": ["Trained on simulated weather; skill on real masts is unknown until it is validated on observed data.",
                                "Predicts the engine's Stop-level drift flags only; it does not know about products, neighbors or rain.",
                                "Advisory context: it never changes the current Go/Caution/Stop status."]}

    def predict(self, X):
        return self.iso.predict(self.clf.predict_proba(X)[:, 1])


_MODEL = None
_LOCK = threading.Lock()


def model() -> Forecaster:
    global _MODEL
    with _LOCK:
        if _MODEL is None:
            _MODEL = Forecaster()
        return _MODEL


def warm():
    threading.Thread(target=model, daemon=True).start()


def band(p):
    for hi, key, label in BANDS:
        if p < hi:
            return key, label
    return "high", "High"


# ---------------------------------------------------------- application
def forecast(scenario, sensor_id: str, at, overrides=None, horizon_h: int = 12):
    """Issue a forecast for one mast at time `at`, using only readings at or before `at`."""
    from datetime import timedelta
    t = thresholds(overrides)
    now = scenario.reading(sensor_id, at) if sensor_id else None
    ago = scenario.reading(sensor_id, at - timedelta(hours=1)) if sensor_id else None

    def vals(r):
        if not r:
            return None
        lo, up = r["lower"], r["upper"]
        if lo.get("temp_f") is None or up.get("temp_f") is None or lo.get("wind_mph") is None:
            return None
        return {"dT": up["temp_f"] - lo["temp_f"], "w": lo["wind_mph"],
                "wu": up.get("wind_mph") if up.get("wind_installed") else None}

    v, v1 = vals(now), vals(ago)
    base = {"model": model().info, "skill": model().metrics, "sensor_id": sensor_id, "issued_at": at.isoformat(),
            "status": "simulated", "disclaimer": "Probabilistic outlook from a model trained on simulated weather. "
            "It does not replace measured checks, the product label, or on-site judgement."}
    if not v or not v1:
        return {**base, "status": "insufficient_data", "hours": [], "window": None, "warning": None,
                "message": "Needs a complete paired reading now and one hour ago at this mast."}

    m = model()
    u = math.sqrt(2) * t["sensor_temp_accuracy_f"]
    flag_now = bool(v["dT"] > u or v["w"] < t["wind_min_mph"] or v["w"] > t["wind_max_mph"])
    hod = at.hour + at.minute / 60
    leads = np.arange(1, horizon_h + 1)
    n = len(leads)
    X = _features(np.full(n, hod), np.full(n, v["dT"]), np.full(n, v1["dT"]), np.full(n, v["w"]), np.full(n, v1["w"]),
                  np.full(n, np.nan if v["wu"] is None else v["wu"]), leads, np.full(n, flag_now))
    p = m.predict(X)
    hours = []
    for L, pi in zip(leads, p):
        tt = at + timedelta(hours=int(L))
        key, label = band(float(pi))
        sr = vals(scenario.reading(sensor_id, tt))  # the demo scenario's own simulated forecast, for comparison
        hours.append({"lead_h": int(L), "time": tt.isoformat(), "p_flag": round(float(pi), 3), "band": key, "band_label": label,
                      "climatology": round(m.clim[int(tt.hour)], 3),
                      "scenario_flag": None if not sr else bool(flag(np.array(sr["dT"]), np.array(sr["w"]), t))})
    # first run of >= 2 consecutive low-probability hours
    window = None
    for i in range(n - 1):
        if hours[i]["band"] == "low" and hours[i + 1]["band"] == "low":
            j = i
            while j + 1 < n and hours[j + 1]["band"] == "low":
                j += 1
            window = {"start": hours[i]["time"], "end": hours[j]["time"],
                      "hours": j - i + 1, "max_p": max(h["p_flag"] for h in hours[i:j + 1])}
            break
    warning = None
    if not flag_now:
        soon = next((h for h in hours[:3] if h["band"] == "high"), None)
        if soon:
            warning = {"time": soon["time"], "p_flag": soon["p_flag"],
                       "text": f"Conditions are likely to turn bad by {soon['time'][11:16]} (P = {soon['p_flag']:.0%})."}
    return {**base, "flag_now": flag_now, "inputs": {"dT_f": round(v["dT"], 2), "dT_1h_ago_f": round(v1["dT"], 2),
            "wind_low_mph": v["w"], "wind_low_1h_ago_mph": v1["w"], "wind_up_mph": v["wu"]},
            "hours": hours, "window": window, "warning": warning}
