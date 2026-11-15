"""USGS 3DEP terrain for the study area.

Rasters come from the USGS 3DEP Bare Earth DEM Dynamic ImageServer (exportImage),
resampled by the service to the requested grid (bilinear). Values are metres; the
service is referenced to NAVD88 (vertical datum as published by 3DEP). Resampling
never adds measured information; the native source resolution is reported separately
from the display grid. All calculations use the original elevations - visual
exaggeration on the map never changes them."""
import io
import json
import math
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime

import numpy as np

from app.config import MST

CACHE = os.path.join(os.path.dirname(__file__), "..", "data", "cache", "terrain")
SERVICE = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer"
EPQS = "https://epqs.nationalmap.gov/v1/json"
UA = {"User-Agent": "CanopyGuard-prototype/0.1"}
SOURCE = {"name": "USGS 3D Elevation Program (3DEP) Bare Earth DEM", "url": "https://www.usgs.gov/3d-elevation-program",
          "service": SERVICE, "units": "m", "vertical_datum": "NAVD88 (as published by 3DEP)",
          "note": "Native 3DEP resolution varies by location (1 m lidar where available, otherwise 1/3 arc-second ~10 m). The EPQS point service reports the native resolution used."}
AREAS = {
    # demo district (fields, masts, neighbours) ~10 m display grid
    "district": {"bbox": (-114.735, 32.645, -114.680, 32.680), "size": (515, 390)},
    # study area incl. AZMET Yuma stations and the Gila Mountains ~60 m display grid
    "study": {"bbox": (-114.80, 32.55, -114.45, 32.80), "size": (560, 470)},
}
_mem = {}


def _fetch(area):
    a = AREAS[area]
    q = {"bbox": ",".join(map(str, a["bbox"])), "bboxSR": 4326, "imageSR": 4326, "size": f"{a['size'][0]},{a['size'][1]}",
         "format": "tiff", "pixelType": "F32", "noData": -9999, "interpolation": "RSP_BilinearInterpolation", "f": "image"}
    import tifffile
    last = None
    for attempt in range(3):
        try:
            data = urllib.request.urlopen(urllib.request.Request(f"{SERVICE}/exportImage?" + urllib.parse.urlencode(q), headers=UA), timeout=90).read()
            arr = tifffile.imread(io.BytesIO(data)).astype("float32")
            arr[arr <= -9000] = np.nan
            return arr
        except Exception as e:  # service is occasionally busy (502); retry, then report unavailable
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"3DEP export failed: {type(last).__name__}: {last}")


def dem(area="district"):
    """Cached DEM dict, or {'status': 'unavailable', ...}. Never synthesises relief."""
    if area in _mem:
        return _mem[area]
    os.makedirs(CACHE, exist_ok=True)
    f = os.path.join(CACHE, f"{area}.npz")
    if os.path.exists(f):
        z = np.load(f, allow_pickle=True)
        d = {"elev": z["elev"], **json.loads(str(z["meta"]))}
    else:
        try:
            arr = _fetch(area)
        except Exception as e:
            return {"status": "unavailable", "error": str(e), "area": area}
        meta = {"area": area, "bbox": AREAS[area]["bbox"], "retrieved_at": datetime.now(MST).isoformat(timespec="seconds"), "status": "ok"}
        np.savez_compressed(f, elev=arr, meta=json.dumps(meta))
        d = {"elev": arr, **meta}
    x0, y0, x1, y1 = d["bbox"]
    H, W = d["elev"].shape
    d["px_m"] = ((x1 - x0) / W * 111320 * math.cos(math.radians((y0 + y1) / 2)), (y1 - y0) / H * 110540)
    d["status"] = "ok"
    _mem[area] = d
    return d


def _sample(d, lon, lat):
    x0, y0, x1, y1 = d["bbox"]
    H, W = d["elev"].shape
    fx = (lon - x0) / (x1 - x0) * W - 0.5
    fy = (y1 - lat) / (y1 - y0) * H - 0.5
    if not (0 <= fx <= W - 1 and 0 <= fy <= H - 1):
        return None
    i, j = int(fx), int(fy)
    i2, j2 = min(i + 1, W - 1), min(j + 1, H - 1)
    dx, dy = fx - i, fy - j
    e = d["elev"]
    v = (e[j, i] * (1 - dx) * (1 - dy) + e[j, i2] * dx * (1 - dy) + e[j2, i] * (1 - dx) * dy + e[j2, i2] * dx * dy)
    return None if np.isnan(v) else float(v)


def point(lon, lat, use_service=True):
    """Elevation at a point: district raster, else study raster, else the EPQS point service."""
    for area in ("district", "study"):
        d = dem(area)
        if d.get("status") == "ok":
            v = _sample(d, lon, lat)
            if v is not None:
                return {"elevation_m": round(v, 2), "elevation_ft": round(v / 0.3048, 1), "source": SOURCE["name"],
                        "method": f"Bilinear sample of the cached 3DEP {area} grid (~{d['px_m'][0]:.0f} m display cells)", "vertical_datum": SOURCE["vertical_datum"]}
    if use_service:
        try:
            q = urllib.parse.urlencode({"x": lon, "y": lat, "units": "Meters", "wkid": 4326, "includeDate": "false"})
            r = json.loads(urllib.request.urlopen(urllib.request.Request(f"{EPQS}?{q}", headers=UA), timeout=20).read())
            v = float(r["value"])
            return {"elevation_m": round(v, 2), "elevation_ft": round(v / 0.3048, 1), "source": SOURCE["name"] + " (EPQS point service)",
                    "method": f"EPQS point query, native resolution {r.get('resolution')} m", "vertical_datum": SOURCE["vertical_datum"]}
        except Exception as e:
            return {"elevation_m": None, "status": "unavailable", "error": f"{type(e).__name__}"}
    return {"elevation_m": None, "status": "outside cached terrain"}


def field_stats(ring_lonlat):
    """Elevation and slope inside a field polygon from the district raster (original values)."""
    d = dem("district")
    if d.get("status") != "ok":
        return {"status": "unavailable", "error": d.get("error")}
    return _stats(d, ring_lonlat)


def _stats(d, ring):
    x0, y0, x1, y1 = d["bbox"]
    H, W = d["elev"].shape
    xs = x0 + (np.arange(W) + 0.5) / W * (x1 - x0)
    ys = y1 - (np.arange(H) + 0.5) / H * (y1 - y0)
    gx, gy = np.meshgrid(xs, ys)
    inside = np.zeros_like(gx, dtype=bool)
    n = len(ring)
    for k in range(n - 1):  # even-odd ray casting, vectorised
        (xa, ya), (xb, yb) = ring[k], ring[k + 1]
        cond = ((ya > gy) != (yb > gy)) & (gx < (xb - xa) * (gy - ya) / ((yb - ya) or 1e-12) + xa)
        inside ^= cond
    e = d["elev"]
    vals = e[inside & ~np.isnan(e)]
    if vals.size == 0:
        return {"status": "no coverage"}
    dzdy, dzdx = np.gradient(e, d["px_m"][1], d["px_m"][0])
    slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))[inside & ~np.isnan(e)]
    return {"status": "ok", "min_m": round(float(vals.min()), 2), "max_m": round(float(vals.max()), 2), "mean_m": round(float(vals.mean()), 2),
            "relief_m": round(float(vals.max() - vals.min()), 2), "slope_mean_deg": round(float(slope.mean()), 2),
            "slope_p95_deg": round(float(np.percentile(slope, 95)), 2), "cells": int(vals.size),
            "grid": f"~{d['px_m'][0]:.0f} m display grid", "source": SOURCE["name"], "vertical_datum": SOURCE["vertical_datum"]}


def profile(coords, step_m=10):
    """Elevation profile along a polyline [[lon,lat],...] from cached rasters (original values)."""
    pts = []
    dist = 0.0
    for (a, b) in zip(coords, coords[1:]):
        mlon = 111320 * math.cos(math.radians(a[1]))
        seg = math.hypot((b[0] - a[0]) * mlon, (b[1] - a[1]) * 110540)
        n = max(1, int(seg // step_m))
        for k in range(n):
            f = k / n
            lon, lat = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
            v = point(lon, lat, use_service=False).get("elevation_m")
            pts.append({"d_m": round(dist + seg * f, 1), "elevation_m": v})
        dist += seg
    v = point(coords[-1][0], coords[-1][1], use_service=False).get("elevation_m")
    pts.append({"d_m": round(dist, 1), "elevation_m": v})
    good = [p["elevation_m"] for p in pts if p["elevation_m"] is not None]
    return {"points": pts, "length_m": round(dist, 1), "min_m": min(good) if good else None, "max_m": max(good) if good else None,
            "source": SOURCE["name"], "vertical_datum": SOURCE["vertical_datum"], "missing": sum(1 for p in pts if p["elevation_m"] is None)}


HYPSO = [(0.0, (34, 94, 74)), (0.25, (92, 140, 82)), (0.5, (190, 170, 98)), (0.75, (170, 112, 72)), (1.0, (240, 236, 228))]


def _color(t):
    t = max(0.0, min(1.0, t))
    for (a0, c0), (a1, c1) in zip(HYPSO, HYPSO[1:]):
        if t <= a1:
            f = (t - a0) / (a1 - a0)
            return [round(c0[k] + (c1[k] - c0[k]) * f) for k in range(3)]
    return list(HYPSO[-1][1])


def overlay(area="district"):
    """Elevation-coloured PNG (with simple hillshade) + legend range + contours GeoJSON."""
    d = dem(area)
    if d.get("status") != "ok":
        return d
    from PIL import Image
    e = d["elev"]
    lo, hi = float(np.nanmin(e)), float(np.nanmax(e))
    dzdy, dzdx = np.gradient(np.nan_to_num(e, nan=lo), d["px_m"][1], d["px_m"][0])
    slope = np.arctan(np.hypot(dzdx, dzdy))
    aspect = np.arctan2(-dzdx, dzdy)
    az, alt = math.radians(315), math.radians(45)
    shade = np.clip(np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1)
    t = (np.nan_to_num(e, nan=lo) - lo) / max(hi - lo, 1e-6)
    lut = np.array([_color(i / 255) for i in range(256)], dtype=np.float32)
    rgb = lut[(t * 255).astype(int)] * (0.55 + 0.45 * shade[..., None])
    alpha = np.where(np.isnan(e), 0, 200).astype(np.uint8)
    img = Image.fromarray(np.dstack([rgb.clip(0, 255).astype(np.uint8), alpha]), "RGBA")
    buf = io.BytesIO(); img.save(buf, "PNG")
    # contours
    feats = []
    try:
        from skimage import measure
        rng = hi - lo
        interval = 1.0 if rng < 15 else 2.0 if rng < 40 else 10.0 if rng < 200 else 25.0
        x0, y0, x1, y1 = d["bbox"]
        H, W = e.shape
        start = math.ceil(lo / interval) * interval
        for lvl in np.arange(start, hi, interval):
            for c in measure.find_contours(np.nan_to_num(e, nan=lo - 1), lvl):
                if len(c) < 6:
                    continue
                coords = [[round(x0 + (p[1] + 0.5) / W * (x1 - x0), 6), round(y1 - (p[0] + 0.5) / H * (y1 - y0), 6)] for p in c[::2]]
                feats.append({"type": "Feature", "properties": {"elev_m": float(lvl), "major": bool(round(lvl / interval) % 5 == 0)},
                              "geometry": {"type": "LineString", "coordinates": coords}})
    except Exception:
        interval = None
    x0, y0, x1, y1 = d["bbox"]
    return {"status": "ok", "png": buf.getvalue(), "range_m": [round(lo, 2), round(hi, 2)], "contour_interval_m": interval,
            "contours": {"type": "FeatureCollection", "features": feats}, "coordinates": [[x0, y1], [x1, y1], [x1, y0], [x0, y0]],
            "grid": f"{e.shape[1]}x{e.shape[0]} display cells (~{d['px_m'][0]:.0f} m)", "source": SOURCE, "retrieved_at": d.get("retrieved_at")}
