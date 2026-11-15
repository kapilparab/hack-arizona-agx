"""Deterministic simulated scenario: paired-height sensor readings (5 ft / 30 ft)
and a simulated rain forecast, on 15-minute slots for "today" and "tomorrow"
(dates anchored to the server's current Arizona date; times fixed).

Everything here is SIMULATED demonstration data."""
from datetime import datetime, timedelta, time
from app.config import MST, SLOT_MIN

# keyframes: hour -> (t_low, t_high, w_low, w_high, dir_low_from, dir_high_from, rh)
_S1_DAY0 = {
    0: (52, 55.5, 2.8, 4.0, 340, 15, 55), 3: (49, 53, 3.2, 4.5, 345, 20, 60),
    5: (47.5, 51.5, 4.0, 5.0, 350, 25, 64), 6: (47, 50.8, 4.2, 5.5, 355, 30, 65),
    7: (49, 52, 4.5, 6.0, 0, 28, 60), 8: (55, 56.2, 5.0, 6.5, 330, 300, 50),
    8.5: (58, 58.3, 5.2, 6.6, 280, 270, 46), 9: (61, 60, 5.5, 7.0, 250, 255, 42),
    10: (65, 63, 6.0, 7.5, 245, 250, 36), 12: (70, 67, 7.0, 8.5, 240, 245, 30),
    13: (72, 68.5, 8.5, 11.0, 220, 230, 30), 14: (72, 68.8, 11.0, 15.0, 210, 220, 34),
    15: (69, 66, 12.5, 17.0, 205, 215, 45), 17: (64, 62, 9.0, 12.0, 220, 230, 55),
    18: (60, 60.5, 6.0, 8.0, 300, 330, 60), 20: (56, 58.5, 4.0, 6.0, 340, 10, 62),
    24: (52, 55.5, 2.8, 4.0, 340, 15, 64),
}
_S2_DAY0 = {
    0: (54, 55.5, 3.5, 5.0, 330, 340, 50), 5: (50, 51.2, 4.2, 5.5, 335, 345, 55),
    6: (50.5, 50.8, 4.5, 6.0, 340, 350, 55), 6.5: (52, 51, 4.8, 6.2, 345, 355, 52),
    7: (54, 52.5, 5.0, 6.5, 350, 0, 48), 9: (62, 60, 6.0, 7.5, 330, 340, 38),
    12: (70, 67.5, 7.0, 9.0, 300, 310, 30), 13: (72, 69, 8.5, 11.0, 240, 245, 30),
    14: (72, 69, 11.5, 15.5, 220, 225, 34), 15: (69, 66.5, 12.0, 16.0, 215, 220, 45),
    17: (64, 62.5, 8.0, 11.0, 230, 240, 55), 18: (60, 60.6, 5.5, 7.5, 300, 320, 58),
    20: (56, 57.5, 4.0, 6.0, 330, 340, 60), 24: (54, 55.5, 3.5, 5.0, 330, 340, 60),
}
# Day 1: calmer, dry; inversions break a little later at S1
_S1_DAY1 = dict(_S1_DAY0)
_S1_DAY1.update({13: (71, 68, 6.5, 8.0, 240, 245, 30), 14: (72, 68.5, 6.5, 8.0, 240, 245, 28),
                 15: (71, 68, 6.0, 7.5, 245, 250, 28), 17: (66, 64, 5.0, 6.5, 260, 270, 34)})
_S2_DAY1 = dict(_S2_DAY0)
_S2_DAY1.update({13: (71, 68.5, 6.5, 8.0, 300, 310, 30), 14: (72, 69, 6.5, 8.0, 300, 310, 28),
                 15: (71, 68.5, 6.0, 7.5, 300, 310, 28), 17: (66, 64.5, 5.0, 6.5, 310, 320, 34)})

KEYS = {"S1": (_S1_DAY0, _S1_DAY1), "S2": (_S2_DAY0, _S2_DAY1)}

# Simulated hourly precipitation probability (%), day0 / day1
_RAIN0 = {0: 5, 11: 10, 12: 20, 13: 30, 14: 35, 15: 60, 16: 70, 18: 70, 19: 50, 20: 30, 22: 10, 24: 5}
_RAIN1 = {0: 5, 24: 5}

# Simulated telemetry gap: S2 upper sensor drops out (demonstrates missing data)
GAPS = [{"sensor": "S2", "height": "upper", "day": 0, "start": 12.0, "end": 12.75}]

DEMO_NOW = time(5, 30)


def _interp(frames: dict, h: float):
    ks = sorted(frames)
    for a, b in zip(ks, ks[1:]):
        if a <= h <= b:
            fa, fb = frames[a], frames[b]
            r = 0 if b == a else (h - a) / (b - a)
            out = []
            for i, (va, vb) in enumerate(zip(fa, fb)):
                if i in (4, 5):  # circular interpolate directions
                    d = ((vb - va + 540) % 360) - 180
                    out.append(round((va + d * r) % 360, 0))
                else:
                    out.append(round(va + (vb - va) * r, 1))
            return out
    return list(frames[ks[-1]])


class Scenario:
    def __init__(self, day0=None):
        today = (day0 or datetime.now(MST).date())
        self.day0 = datetime.combine(today, time(0, 0), MST)
        self.now = datetime.combine(today, DEMO_NOW, MST)
        self.end = self.day0 + timedelta(days=2)
        self.events = []  # injected critical changes

    # ------------------------------------------------------------------ meta
    def meta(self):
        return {"id": "yuma-dawn-inversion", "name": "Yuma Valley dawn inversion (simulated)",
                "day0": self.day0.isoformat(), "now": self.now.isoformat(), "end": self.end.isoformat(),
                "timezone": "America/Phoenix (MST, UTC-7, no DST)", "slot_min": SLOT_MIN,
                "status": "simulated",
                "description": "Simulated paired-height masts S1 and S2 at 5 ft and 30 ft. Times before the scenario clock "
                               "are simulated observations; later times are a simulated scenario forecast.",
                "events": self.events}

    def slots(self):
        t = self.day0
        while t < self.end:
            yield t
            t += timedelta(minutes=SLOT_MIN)

    def floor_slot(self, t: datetime) -> datetime:
        t = t.astimezone(MST)
        m = (t.minute // SLOT_MIN) * SLOT_MIN
        return t.replace(minute=m, second=0, microsecond=0)

    def kind_at(self, t: datetime) -> str:
        return "simulated_observation" if t <= self.now else "simulated_forecast"

    # -------------------------------------------------------------- readings
    def reading(self, sensor_id: str, t: datetime) -> dict | None:
        """Paired-height reading for the slot containing t, or None outside horizon/unknown sensor."""
        if sensor_id not in KEYS or not (self.day0 <= t < self.end):
            return None
        slot = self.floor_slot(t)
        day = (slot.date() - self.day0.date()).days
        h = slot.hour + slot.minute / 60
        tl, th, wl, wh, dl, dh, rh = _interp(KEYS[sensor_id][day], h)
        from app.demo_data import sensor as _sensor, SIM_ACCURACY
        meta = _sensor(sensor_id)
        T = {x["level"]: x for x in meta["temp"]}
        W = {x["level"]: x for x in meta["wind"]}
        obs = slot.isoformat()
        def level(lv, temp, wind, d):
            w = W.get(lv)
            return {"height_ft": T[lv]["height_ft"], "ref": T[lv]["ref"], "temp_f": temp, "temp_observed_at": obs,
                    "temp_accuracy_f": meta["temp_accuracy_f"],
                    "wind_height_ft": w["height_ft"] if w else None, "wind_ref": w["ref"] if w else None,
                    "wind_mph": wind if w else None, "dir_from_deg": d if w else None, "wind_observed_at": obs if w else None,
                    "wind_installed": bool(w), "missing_reason": None if w else None}
        lower = level("lower", tl, wl, dl)
        upper = level("upper", th, wh, dh)
        lower["gust_mph"] = round(wl * 1.35, 1)
        if not upper["wind_installed"]:
            upper["wind_note"] = "No wind sensor installed at this level"
        for g in GAPS:
            if g["sensor"] == sensor_id and g["day"] == day and g["start"] <= h < g["end"]:
                target = upper if g["height"] == "upper" else lower
                target["temp_f"] = None
                if target["wind_installed"]:
                    target["wind_mph"] = target["dir_from_deg"] = None
                target["missing_reason"] = "Simulated telemetry gap"
        for e in self.events:
            st = datetime.fromisoformat(e["start"])
            if e["sensor"] == sensor_id and st <= slot < st + timedelta(minutes=e["duration_min"]):
                lower.update(e["lower"])
                if upper["wind_installed"]:
                    upper.update(e["upper"])
                lower["event"] = e["label"]
        kind = self.kind_at(slot)
        return {"sensor_id": sensor_id, "observed_at": obs, "kind": kind, "config": meta["config"],
                "source": "Simulated paired-height mast (demo)", "units": {"temp": "degF", "wind": "mph", "dir": "deg from"},
                "lower": lower, "upper": upper, "rh_pct": rh, "rain_prob_pct": self.rain_prob(slot),
                "accuracy_note": SIM_ACCURACY, "shielding": meta["shielding"], "averaging": meta["averaging"], "gust_interval": meta["gust"],
                "mast_xy": meta["xy"]}

    def trend(self, sensor_id, t, minutes=60):
        """Upper-minus-lower temperature trend (°F per hour) from 3+ aligned simulated pairs."""
        pts = []
        for k in range(0, minutes + 1, 15):
            r = self.reading(sensor_id, t - timedelta(minutes=k))
            if r and r["lower"]["temp_f"] is not None and r["upper"]["temp_f"] is not None:
                pts.append((k, r["upper"]["temp_f"] - r["lower"]["temp_f"]))
        if len(pts) < 3:
            return None
        n = len(pts); mx = sum(p[0] for p in pts) / n; my = sum(p[1] for p in pts) / n
        sxx = sum((p[0] - mx) ** 2 for p in pts)
        slope_per_min = -sum((p[0] - mx) * (p[1] - my) for p in pts) / sxx  # k counts minutes back in time
        return {"per_hour_f": round(slope_per_min * 60, 2), "points": n, "window_min": minutes}

    def rain_prob(self, t: datetime) -> float | None:
        if not (self.day0 <= t < self.end):
            return None
        slot = self.floor_slot(t)
        day = (slot.date() - self.day0.date()).days
        h = slot.hour + slot.minute / 60
        frames = _RAIN0 if day == 0 else _RAIN1
        ks = sorted(frames)
        for a, b in zip(ks, ks[1:]):
            if a <= h <= b:
                return round(frames[a] + (frames[b] - frames[a]) * ((h - a) / (b - a) if b > a else 0), 0)
        return float(frames[ks[-1]])

    def rain_series(self):
        return [{"time": t.isoformat(), "prob_pct": self.rain_prob(t), "kind": "simulated_forecast"}
                for t in self.slots() if t.minute == 0]

    # ---------------------------------------------------------------- events
    def inject(self, sensor_id: str, start: datetime, duration_min: int = 60):
        ev = {"id": f"E{len(self.events) + 1}", "sensor": sensor_id, "start": self.floor_slot(start).isoformat(),
              "duration_min": duration_min, "label": "Simulated critical change: sudden wind surge",
              "lower": {"wind_mph": 13.5, "gust_mph": 19.0}, "upper": {"wind_mph": 18.0}}
        self.events.append(ev)
        return ev

    def reset_events(self):
        self.events = []


SCENARIO = Scenario()
