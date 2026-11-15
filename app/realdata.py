"""Bounded real-data pipeline for one Arizona study area (Yuma).

Sources (verified while building):
- AZMET hourly observations (api.azmet.arizona.edu) and station metadata pages
  (azmet.arizona.edu/about/station-metadata/<id>): location, sensor models, heights.
- NOAA HRRR via Herbie from the AWS archive: wrfsfc (2 m TMP, 10 m UGRD/VGRD, surface HGT)
  and wrfnat (TMP, HGT on the lowest hybrid levels).
- NWS API hourly point forecast.
Everything is cached under data/cache. Failures return explicit 'unavailable'
states; nothing is replaced with simulated data.

Fusion baseline (EXPERIMENTAL): HRRR 2 m temperature plus an inverse-distance-weighted
field of AZMET (1.5 m) minus HRRR (2 m) residuals. The 0.5 m height difference is a
documented assumption; this is NOT regression kriging and has no fitted spatial model."""
import html as _html
import json
import math
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import numpy as np

from app.config import MST

CACHE = os.path.join(os.path.dirname(__file__), "..", "data", "cache")
UA = {"User-Agent": "CanopyGuard-prototype/0.1 (hackathon demo)"}
STATIONS = ["az02", "az14", "az36"]           # Yuma Valley, Yuma N.Gila, Yuma South
BBOX = (-114.85, 32.50, -114.40, 32.85)       # HRRR subset (lon/lat)
HRRR_RES = "3 km native grid (HRRR)"


def _get(url, timeout=30):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def _cache_json(name, fn, max_age_s=None):
    os.makedirs(CACHE, exist_ok=True)
    f = os.path.join(CACHE, name)
    if os.path.exists(f) and (max_age_s is None or (datetime.now().timestamp() - os.path.getmtime(f)) < max_age_s):
        return json.load(open(f, encoding="utf-8"))
    data = fn()
    if data.get("status") != "unavailable":
        json.dump(data, open(f, "w", encoding="utf-8"))
    return data


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ---------------------------------------------------------------- AZMET
def station_meta(sid):
    def fetch():
        try:
            raw = _get(f"https://azmet.arizona.edu/about/station-metadata/{sid}").decode("utf-8", "ignore")
        except Exception as e:
            return {"status": "unavailable", "error": type(e).__name__, "id": sid}
        t = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", raw)))
        g = lambda pat: (re.search(pat, t) or [None, None])[1]
        name = g(r"^\s*([A-Za-z .]+?) \| The Arizona") or sid
        cur = re.search(r"General location: ([-0-9.]+), ([-0-9.]+) Elevation: (\d+) ft", t)
        sens = lambda label: re.search(label + r" SENSOR: (.+?) SENSOR HEIGHT: [0-9.]+ ft \(([0-9.]+) m\)", t)
        temp, wind, rh = sens("Air Temperature"), re.search(r"SPEED SENSOR: (.+?) SPEED SENSOR HEIGHT: [0-9.]+ ft \(([0-9.]+) m\)", t), sens("Relative Humidity")
        site = g(r"Site Description: (.+?) Air Temperature")
        return {"status": "ok", "id": sid, "name": name.strip(), "lat": float(cur[1]) if cur else None, "lon": float(cur[2]) if cur else None,
                "elevation_ft": int(cur[3]) if cur else None, "site": site,
                "temp_sensor": temp[1] if temp else None, "temp_height_m": float(temp[2]) if temp else None,
                "wind_sensor": wind[1] if wind else None, "wind_height_m": float(wind[2]) if wind else None,
                "rh_height_m": float(rh[2]) if rh else None,
                "coord_precision": "2 decimal places (~0.6-1.1 km) as published",
                "source": f"https://azmet.arizona.edu/about/station-metadata/{sid}"}
    return _cache_json(f"azmet_meta_{sid}.json", fetch, max_age_s=7 * 86400)


def azmet_hourly(sid, start_mst: datetime, hours: int):
    key = f"azmet_{sid}_{start_mst:%Y%m%dT%H}_{hours}.json"
    def fetch():
        url = f"https://api.azmet.arizona.edu/v1/observations/hourly/{sid}/{start_mst:%Y-%m-%dT%H:%M}/P{hours // 24}DT{hours % 24}H"
        try:
            d = json.loads(_get(url))
        except Exception as e:
            return {"status": "unavailable", "error": type(e).__name__}
        meta = station_meta(sid)
        rows = []
        for r in d.get("data", []):
            f = lambda k: (None if r.get(k) in (None, "", "-99999", "-9999") else float(r[k]))
            # AZMET hourly datetime is the END of the hourly period, local time (MST)
            rows.append({"time": datetime.strptime(r["date_datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=MST).isoformat(),
                         "temp_c": f("temp_airC"), "temp_30cm_c": f("temp_air_30cmC"), "rh_pct": f("relative_humidity"),
                         "wind_mps": f("wind_spd_mps"), "wind_2min_mps": f("wind_2min_spd_mean_mps"), "wind_dir": f("wind_vector_dir"),
                         "gust_mps": f("wind_spd_max_mps"), "precip_mm": f("precip_total"), "solar_mj": f("sol_rad_total"),
                         "needs_review": r.get("meta_needs_review"), "station_name": r.get("meta_station_name")})
        return {"status": "ok", "station": sid, "rows": rows, "retrieved_at": datetime.now(MST).isoformat(timespec="seconds"), "meta": meta,
                "notes": "Hourly values; air temperature is an hourly average at the documented sensor height."}
    return _cache_json(key, fetch, max_age_s=1800 if start_mst > datetime.now(MST) - timedelta(days=1) else None)


# ------------------------------------------------------------------ HRRR
def _rotate(u, v, lon, attrs):
    """Grid-relative to earth-relative wind for HRRR's Lambert conformal grid."""
    lov = float(attrs.get("GRIB_LoVInDegrees", 262.5))
    lat1 = float(attrs.get("GRIB_Latin1InDegrees", 38.5))
    cone = math.sin(math.radians(lat1))
    lon360 = np.where(lon < 0, lon + 360, lon)
    ang = np.radians(cone * (lon360 - lov))
    return np.cos(ang) * u + np.sin(ang) * v, -np.sin(ang) * u + np.cos(ang) * v


def hrrr(cycle_utc: datetime, fxx=0, native=True):
    """Subset HRRR surface (+ optional native-level) fields for the study area at one cycle/lead."""
    key = f"hrrr_{cycle_utc:%Y%m%d%H}_f{fxx:02d}{'_nat' if native else ''}.json"
    def fetch():
        try:
            import warnings
            warnings.filterwarnings("ignore")
            from herbie import Herbie
            sd = os.path.join(CACHE, "herbie")
            Hs = Herbie(cycle_utc.strftime("%Y-%m-%d %H:%M"), model="hrrr", product="sfc", fxx=fxx, save_dir=sd, verbose=False)
            ds = Hs.xarray(r":(?:TMP:2 m above ground|UGRD:10 m above ground|VGRD:10 m above ground|HGT:surface)", remove_grib=True)
            dsl = ds if isinstance(ds, list) else [ds]
            dn = None
            if native:
                Hn = Herbie(cycle_utc.strftime("%Y-%m-%d %H:%M"), model="hrrr", product="nat", fxx=fxx, save_dir=sd, verbose=False)
                dn = Hn.xarray(r":(?:TMP|HGT):(?:[1-9]|10) hybrid level:", remove_grib=True)
                dn = dn[0] if isinstance(dn, list) else dn
        except Exception as e:
            return {"status": "unavailable", "error": f"{type(e).__name__}: {str(e)[:160]}"}
        get = lambda name: next((d[name] for d in dsl if name in d), None)
        t2, u10, v10, orog = get("t2m"), get("u10"), get("v10"), get("orog")
        lat = t2.latitude.values
        lon = np.where(t2.longitude.values > 180, t2.longitude.values - 360, t2.longitude.values)
        x0, y0, x1, y1 = BBOX
        mask = (lat >= y0) & (lat <= y1) & (lon >= x0) & (lon <= x1)
        jj, ii = np.where(mask)
        ue, ve = _rotate(u10.values, v10.values, t2.longitude.values, u10.attrs)
        cells = []
        for j, i in zip(jj, ii):
            prof = []
            for k in range(dn.sizes["hybrid"] if dn is not None else 0):
                gh = float(dn["gh"].values[k, j, i])
                prof.append({"level": int(dn["hybrid"].values[k]), "t_f": round((float(dn["t"].values[k, j, i]) - 273.15) * 9 / 5 + 32, 2),
                             "gh_gpm": round(gh, 1), "height_agl_m": round(gh - float(orog.values[j, i]), 1)})
            spd = math.hypot(float(ue[j, i]), float(ve[j, i]))
            cells.append({"lat": round(float(lat[j, i]), 5), "lon": round(float(lon[j, i]), 5),
                          "t2m_f": round((float(t2.values[j, i]) - 273.15) * 9 / 5 + 32, 2),
                          "wind10_mph": round(spd * 2.23694, 2), "wind10_from": round((math.degrees(math.atan2(-ue[j, i], -ve[j, i])) + 360) % 360, 0),
                          "orog_m": round(float(orog.values[j, i]), 1), "profile": prof})
        vt = cycle_utc + timedelta(hours=fxx)
        return {"status": "ok", "model": "HRRR", "cycle_utc": cycle_utc.isoformat(), "lead_h": fxx, "valid_utc": vt.isoformat(),
                "valid_mst": vt.astimezone(MST).isoformat(), "retrieved_at": datetime.now(MST).isoformat(timespec="seconds"),
                "resolution": HRRR_RES, "cells": cells,
                "heights": {"t2m": "2 m above model ground", "wind10": "10 m above model ground (rotated from grid- to earth-relative)",
                            "native": "hybrid levels; height above model ground = geopotential height (gpm) minus model surface height (gpm ~ m)"},
                "source": "NOAA HRRR via Herbie, AWS archive (noaa-hrrr-bdp-pds)", "url": "https://www.nco.ncep.noaa.gov/pmb/products/hrrr/"}
    return _cache_json(key, fetch)


def latest_cycle(now_utc=None):
    now_utc = now_utc or datetime.now(timezone.utc)
    return (now_utc - timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)


def _nearest_cell(cells, lat, lon):
    best = min(cells, key=lambda c: haversine_m(lat, lon, c["lat"], c["lon"]))
    return best, haversine_m(lat, lon, best["lat"], best["lon"])


def _idw(points, lat, lon, power=2):
    ws = [(1 / max(haversine_m(lat, lon, p["lat"], p["lon"]), 100.0) ** power, p) for p in points]
    s = sum(w for w, _ in ws)
    return sum(w * p["value"] for w, p in ws) / s, [{"id": p["id"], "weight": round(w / s, 3)} for w, p in ws]


# ---------------------------------------------------------------- fusion
def station_obs_at(valid_mst: datetime):
    """AZMET hourly temperature for the hour ending at valid_mst (+1 h window) per station."""
    out, missing = [], []
    for sid in STATIONS:
        meta = station_meta(sid)
        h = azmet_hourly(sid, valid_mst - timedelta(hours=1), 2)
        if meta.get("status") != "ok" or h.get("status") != "ok":
            missing.append({"id": sid, "reason": (h.get("error") or meta.get("error") or "unavailable")})
            continue
        row = next((r for r in h["rows"] if r["time"] == valid_mst.isoformat()), None)
        if not row or row["temp_c"] is None:
            missing.append({"id": sid, "reason": "No hourly value for this hour"})
            continue
        out.append({"id": sid, "name": row.get("station_name") or meta["name"], "lat": meta["lat"], "lon": meta["lon"], "time": row["time"],
                    "temp_f": round(row["temp_c"] * 9 / 5 + 32, 2), "height_m": meta["temp_height_m"],
                    "wind_mph": None if row["wind_mps"] is None else round(row["wind_mps"] * 2.23694, 1), "wind_from": row["wind_dir"],
                    "wind_height_m": meta["wind_height_m"], "rh_pct": row["rh_pct"], "source": meta["source"],
                    "status": "observed", "averaging": "hourly average (temperature)"})
    return out, missing


def estimate(lat, lon, valid_mst: datetime):
    """Raw model, nearby stations, and experimental corrected estimate at a location."""
    cyc = valid_mst.astimezone(timezone.utc).replace(tzinfo=None)
    model = hrrr(cyc.replace(tzinfo=timezone.utc), 0)
    stations, missing = station_obs_at(valid_mst)
    res = {"location": {"lat": lat, "lon": lon}, "valid_mst": valid_mst.isoformat(), "model": None, "stations": [], "missing": missing,
           "corrected": None, "nearest_station": None, "idw_stations": None, "local_paired_sensor": False,
           "assumptions": ["HRRR 2 m and AZMET 1.5 m temperatures are treated as comparable for screening (0.5 m height difference).",
                           "Inverse-distance weighting (power 2, 100 m minimum distance); no fitted spatial model, not kriging.",
                           "AZMET coordinates are published to 2 decimal places (~1 km)."],
           "status": "experimental"}
    if model.get("status") != "ok":
        res["model_error"] = model.get("error")
    else:
        c, d = _nearest_cell(model["cells"], lat, lon)
        res["model"] = {"t2m_f": c["t2m_f"], "wind10_mph": c["wind10_mph"], "wind10_from": c["wind10_from"], "cell_distance_km": round(d / 1000, 2),
                        "resolution": model["resolution"], "cycle_utc": model["cycle_utc"], "valid_mst": model["valid_mst"], "lead_h": model["lead_h"],
                        "profile": c["profile"], "orog_m": c["orog_m"], "heights": model["heights"], "source": model["source"]}
    for s in stations:
        s["distance_km"] = round(haversine_m(lat, lon, s["lat"], s["lon"]) / 1000, 2)
        if model.get("status") == "ok":
            mc, _ = _nearest_cell(model["cells"], s["lat"], s["lon"])
            s["model_at_station_f"] = mc["t2m_f"]
            s["residual_f"] = round(s["temp_f"] - mc["t2m_f"], 2)
    res["stations"] = sorted(stations, key=lambda s: s["distance_km"])
    if stations:
        ns = res["stations"][0]
        res["nearest_station"] = {"id": ns["id"], "temp_f": ns["temp_f"], "distance_km": ns["distance_km"]}
        v, w = _idw([{"id": s["id"], "lat": s["lat"], "lon": s["lon"], "value": s["temp_f"]} for s in stations], lat, lon)
        res["idw_stations"] = {"temp_f": round(v, 2), "weights": w}
    if res["model"] and stations and all("residual_f" in s for s in stations):
        rv, w = _idw([{"id": s["id"], "lat": s["lat"], "lon": s["lon"], "value": s["residual_f"]} for s in stations], lat, lon)
        res["corrected"] = {"temp_f": round(res["model"]["t2m_f"] + rv, 2), "residual_f": round(rv, 2), "weights": w,
                            "label": "Experimental: model + IDW of station-minus-model residuals"}
    return res


def validate(day_mst: datetime, hours=range(0, 24, 2)):
    """Leave-one-station-out comparison over one day (analysis hours only; no future data).
    For each hour and held-out station, predict its 1.5 m temperature from the OTHER stations."""
    key = f"validation_{day_mst:%Y%m%d}_{len(list(hours))}.json"
    def run():
        rows = []
        for h in hours:
            vt = day_mst.replace(hour=h, minute=0, second=0, microsecond=0)
            model = hrrr(vt.astimezone(timezone.utc), 0, native=False)
            stations, _ = station_obs_at(vt)
            if model.get("status") != "ok" or len(stations) < 3:
                continue
            for s in stations:
                s["model"] = _nearest_cell(model["cells"], s["lat"], s["lon"])[0]["t2m_f"]
            for tgt in stations:
                others = [s for s in stations if s["id"] != tgt["id"]]
                near = min(others, key=lambda s: haversine_m(tgt["lat"], tgt["lon"], s["lat"], s["lon"]))
                idw, _ = _idw([{"id": s["id"], "lat": s["lat"], "lon": s["lon"], "value": s["temp_f"]} for s in others], tgt["lat"], tgt["lon"])
                resid, _ = _idw([{"id": s["id"], "lat": s["lat"], "lon": s["lon"], "value": s["temp_f"] - s["model"]} for s in others], tgt["lat"], tgt["lon"])
                rows.append({"time": vt.isoformat(), "station": tgt["id"], "obs": tgt["temp_f"], "raw_model": tgt["model"],
                             "nearest_station": near["temp_f"], "idw_stations": idw, "corrected": tgt["model"] + resid})
        if not rows:
            return {"status": "unavailable", "error": "Not enough model or station data for the period"}
        def metrics(k):
            e = np.array([r[k] - r["obs"] for r in rows])
            return {"mae_f": round(float(np.abs(e).mean()), 2), "rmse_f": round(float(np.sqrt((e ** 2).mean())), 2), "bias_f": round(float(e.mean()), 2)}
        return {"status": "ok", "n": len(rows), "period": f"{day_mst:%Y-%m-%d} MST, hours {list(hours)}", "stations": STATIONS,
                "method": "Leave-one-station-out: each station is predicted from the other two; HRRR analyses (f00) only, so no future data enter.",
                "results": {k: metrics(k) for k in ("raw_model", "nearest_station", "idw_stations", "corrected")},
                "caveat": "Three stations and one day: a small sample. Surface (1.5 m) temperature skill says nothing about detecting shallow inversions.",
                "computed_at": datetime.now(MST).isoformat(timespec="seconds")}
    return _cache_json(key, run)


# ------------------------------------------------------------------- NWS
def nws_hourly(lat, lon):
    def fetch():
        try:
            pt = json.loads(_get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}"))
            fc = json.loads(_get(pt["properties"]["forecastHourly"]))
        except Exception as e:
            return {"status": "unavailable", "error": type(e).__name__}
        periods = []
        for p in fc["properties"]["periods"][:48]:
            spd = re.findall(r"\d+", p.get("windSpeed") or "")
            periods.append({"start": p["startTime"], "end": p["endTime"], "temp_f": p.get("temperature"),
                            "wind_mph": int(spd[0]) if spd else None, "wind_from": p.get("windDirection"),
                            "pop_pct": (p.get("probabilityOfPrecipitation") or {}).get("value"), "short": p.get("shortForecast")})
        return {"status": "ok", "source": "NWS API hourly forecast", "office": pt["properties"].get("gridId"),
                "grid": f"{pt['properties'].get('gridX')},{pt['properties'].get('gridY')} (2.5 km NWS grid)",
                "issued": fc["properties"].get("updateTime"), "generated": fc["properties"].get("generatedAt"),
                "retrieved_at": datetime.now(MST).isoformat(timespec="seconds"),
                "heights": "Not specified by the source (point forecast); not comparable with mast heights.", "periods": periods}
    return _cache_json(f"nws_{lat:.3f}_{lon:.3f}.json", fetch, max_age_s=3600)
