"""Regional weather context from the Open-Meteo forecast model.

These are MODEL estimates at their native heights (temperature 2 m and 80 m,
wind 10 m and 80 m) for a grid cell, not paired-height observations above any
field. They are shown as context only and never drive a Go/Stop decision.
A failed request returns an explicit unavailable/stale state - never
fabricated values."""
import json
import time
import urllib.request
from datetime import datetime
from app.config import MST

URL = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
       "&current=temperature_2m,temperature_80m,wind_speed_10m,wind_speed_80m,wind_direction_10m,"
       "wind_direction_80m,relative_humidity_2m,wind_gusts_10m,shortwave_radiation"
       "&hourly=precipitation_probability&forecast_hours=12"
       "&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=America%2FPhoenix")
FRESH_S = 900
_cache: dict = {}

VARS = {
    "temperature_2m": ("Air temperature", 2, "°F"), "temperature_80m": ("Air temperature", 80, "°F"),
    "wind_speed_10m": ("Wind speed", 10, "mph"), "wind_speed_80m": ("Wind speed", 80, "mph"),
    "wind_direction_10m": ("Wind direction (from)", 10, "°"), "wind_direction_80m": ("Wind direction (from)", 80, "°"),
    "relative_humidity_2m": ("Relative humidity", 2, "%"), "wind_gusts_10m": ("Wind gusts", 10, "mph"),
    "shortwave_radiation": ("Shortwave radiation", None, "W/m²"),
}


def fetch(lat=32.66, lon=-114.72, opener=urllib.request.urlopen):
    key = (round(lat, 3), round(lon, 3))
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit["_t"] < FRESH_S:
        return {**hit["data"], "cache": "fresh"}
    try:
        req = urllib.request.Request(URL.format(lat=lat, lon=lon), headers={"User-Agent": "Observair-prototype"})
        with opener(req, timeout=5) as r:
            raw = json.loads(r.read().decode())
        cur = raw.get("current") or {}
        vals = []
        for k, (label, h, unit) in VARS.items():
            v = cur.get(k)
            vals.append({"key": k, "label": label, "height_m": h, "unit": unit, "value": v,
                         "missing": v is None})
        hourly = raw.get("hourly") or {}
        data = {
            "status": "ok", "source": "Open-Meteo forecast API (model estimate)", "source_url": "https://open-meteo.com",
            "kind": "model_estimate", "location": {"lat": raw.get("latitude"), "lon": raw.get("longitude")},
            "source_time": cur.get("time"), "source_timezone": raw.get("timezone"),
            "retrieved_at": datetime.now(MST).isoformat(timespec="seconds"), "values": vals,
            "precip_prob": [{"time": t, "prob_pct": p} for t, p in zip(hourly.get("time", []), hourly.get("precipitation_probability", []))],
            "note": "Grid-cell model values at 2 m / 10 m / 80 m. Not field observations and not the 5 ft / 30 ft paired sensors. "
                    "Not used for Go/Stop. A model temperature difference is not a measured local inversion.",
        }
        _cache[key] = {"_t": now, "data": data}
        return {**data, "cache": "fresh"}
    except Exception as e:
        if hit:
            age = int((now - hit["_t"]) / 60)
            return {**hit["data"], "status": "stale", "cache": "stale", "stale_minutes": age,
                    "error": f"Refresh failed ({type(e).__name__}); showing last values from {age} min ago."}
        return {"status": "unavailable", "source": "Open-Meteo forecast API", "kind": "model_estimate",
                "retrieved_at": datetime.now(MST).isoformat(timespec="seconds"),
                "error": f"Regional context unavailable ({type(e).__name__}). No values shown.", "values": []}
