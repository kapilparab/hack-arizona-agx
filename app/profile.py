"""Vertical interpolation and conditions at the spray plan's release height.

Temperature: linear interpolation between installed sensors on the same mast and
reference surface. No extrapolation: outside the measured range the value is
reported as unavailable (with the nearest measured level for context).

Wind: logarithmic profile with crop-based roughness, as in FAO Irrigation and
Drainage Paper 56 (zero-plane displacement d = 2/3 h, roughness length for momentum
z0m = 0.123 h). The log law assumes NEUTRAL stability; during an inversion (stable
air) real wind profiles differ, so the estimate is flagged and never drives Go/Stop.

Model profiles: layer-by-layer lapse rates, inverted layers, inversion top and
regime (adapted from the multi-height analysis in the backend-implementation branch,
applied here to HRRR native levels at their actual heights above model ground)."""
import math

FT = 0.3048
FAO56 = "FAO Irrigation and Drainage Paper 56 (Allen et al., 1998): d = 2/3 h, z0m = 0.123 h, logarithmic wind profile"


def _agl_ft(level_h_ft, ref, canopy_ft):
    return level_h_ft + (canopy_ft or 0) if ref == "canopy" else level_h_ft


def temperature_at(z_agl_ft, reading, canopy_ft):
    lo, up = reading["lower"], reading["upper"]
    if lo.get("temp_f") is None or up.get("temp_f") is None:
        return {"value_f": None, "status": "unavailable", "reason": "A paired temperature is missing."}
    za, zb = _agl_ft(lo["height_ft"], lo["ref"], canopy_ft), _agl_ft(up["height_ft"], up["ref"], canopy_ft)
    if not (za - 1e-6 <= z_agl_ft <= zb + 1e-6):
        near = lo if z_agl_ft < za else up
        return {"value_f": None, "status": "outside_measured_range", "measured_range_ft_agl": [round(za, 2), round(zb, 2)],
                "nearest": {"height_ft_agl": round(min(max(z_agl_ft, za), zb), 2), "temp_f": near["temp_f"]},
                "reason": f"Release height {z_agl_ft:.1f} ft above ground is outside the measured {za:.1f}-{zb:.1f} ft range; not extrapolated."}
    f = (z_agl_ft - za) / (zb - za) if zb > za else 0
    return {"value_f": round(lo["temp_f"] + f * (up["temp_f"] - lo["temp_f"]), 2), "status": "interpolated",
            "method": "Linear interpolation between the two installed sensors", "measured_range_ft_agl": [round(za, 2), round(zb, 2)]}


def wind_at(z_agl_ft, reading, canopy_ft):
    """Neutral log-law estimate from the measured wind level(s). h = canopy height."""
    h_m = max((canopy_ft or 0.4) * FT, 0.12)          # FAO-56 reference grass 0.12 m when no canopy is entered
    d, z0 = 2 / 3 * h_m, 0.123 * h_m
    z = z_agl_ft * FT
    levels = [lv for lv in (reading["lower"], reading["upper"]) if lv.get("wind_installed", True) and lv.get("wind_mph") is not None]
    if not levels:
        return {"value_mph": None, "status": "unavailable", "reason": "No measured wind."}
    if z <= d + z0:
        return {"value_mph": None, "status": "inside_canopy", "reason": f"Release height is within the canopy roughness layer (d + z0 = {(d + z0) / FT:.1f} ft); the log profile does not apply."}
    zr = lambda lv: _agl_ft(lv.get("wind_height_ft", lv["height_ft"]), lv.get("wind_ref", lv["ref"]), canopy_ft) * FT
    if len(levels) >= 2:
        (a, b) = sorted(levels, key=zr)[:2]
        za, zb = zr(a), zr(b)
        # fit u* and z0 from two levels (neutral): u = (u*/k) ln((z-d)/z0)
        la, lb = math.log((za - d)), math.log((zb - d))
        ua, ub = a["wind_mph"], b["wind_mph"]
        if ub > ua and lb > la:
            slope = (ub - ua) / (lb - la)
            val = ua + slope * (math.log(max(z - d, 1e-3)) - la)
            method = "Log-law fitted through the two measured wind levels (d = 2/3 h)"
        else:
            val = ua * math.log((z - d) / z0) / math.log((za - d) / z0)
            method = "Log-law from the lower wind level (upper level not stronger, so a two-level fit is not meaningful)"
        ref = f"{za / FT:.1f} and {zb / FT:.1f} ft"
    else:
        a = levels[0]
        za = zr(a)
        val = a["wind_mph"] * math.log((z - d) / z0) / math.log((za - d) / z0)
        method = "Log-law from the single measured wind level"
        ref = f"{za / FT:.1f} ft"
    return {"value_mph": round(max(val, 0), 2), "status": "estimated", "method": method, "from_levels": ref,
            "roughness": {"canopy_ft": canopy_ft, "d_ft": round(d / FT, 2), "z0_ft": round(z0 / FT, 3)}, "source": FAO56,
            "validity": "Assumes neutral stability; not valid during an inversion. Context only - decisions use measured winds."}


def release_height(unit_type, cfg, canopy_ft):
    """Release height above ground for a spray plan, with its reference and source."""
    if unit_type == "ground_boom":
        hb = cfg.get("boom_height_in")
        return None if hb is None else {"agl_ft": round((canopy_ft or 0) + hb / 12, 2), "above": "canopy (target)",
                                        "value": f"{hb} in above the target canopy", "source": "Equipment configuration (operator input)"}
    if unit_type == "drone":
        hm = cfg.get("height_m")
        return None if hm is None else {"agl_ft": round((canopy_ft or 0) + hm / FT, 2), "above": "canopy",
                                        "value": f"{hm} m above the canopy", "source": "Equipment configuration (operator input)"}
    if unit_type == "airblast":
        hm = cfg.get("manifold_height_ft")
        return None if hm is None else {"agl_ft": hm, "above": "ground", "value": f"{hm} ft above ground (nozzle manifold)",
                                        "source": "Equipment configuration (operator input)"}
    return None


def at_release(unit_type, cfg, reading, canopy_ft, inversion_flagged):
    rh = release_height(unit_type, cfg, canopy_ft)
    if not rh:
        return {"status": "unavailable", "reason": "Release height not entered for this equipment."}
    if not reading:
        return {"status": "unavailable", "reason": "No paired reading.", "release": rh}
    t = temperature_at(rh["agl_ft"], reading, canopy_ft)
    w = wind_at(rh["agl_ft"], reading, canopy_ft)
    if inversion_flagged and w.get("value_mph") is not None:
        w["validity"] = "Inversion flagged: the neutral log-law estimate is unreliable now. Shown for context only."
        w["status"] = "estimated_unreliable"
    return {"status": "ok", "release": rh, "temperature": t, "wind": w,
            "note": "Estimates at release height are context. Go/Stop uses the measured paired-height checks."}


def analyze_model_profile(levels):
    """Layer-by-layer analysis of a model profile [{height_agl_m, t_f}, ...] (lowest first)."""
    lv = sorted([x for x in levels if x.get("t_f") is not None and x.get("height_agl_m") is not None], key=lambda x: x["height_agl_m"])
    if len(lv) < 2:
        return {"status": "unavailable"}
    layers = []
    for a, b in zip(lv, lv[1:]):
        dz = b["height_agl_m"] - a["height_agl_m"]
        rate = (b["t_f"] - a["t_f"]) / dz * 100 if dz > 0 else None
        layers.append({"from_m": a["height_agl_m"], "to_m": b["height_agl_m"], "dt_f": round(b["t_f"] - a["t_f"], 2),
                       "lapse_f_per_100m": round(rate, 2) if rate is not None else None, "inverted": b["t_f"] > a["t_f"]})
    inv = [l for l in layers if l["inverted"]]
    surface_based = bool(layers and layers[0]["inverted"])
    top = None
    if surface_based:
        top = layers[0]["to_m"]
        for l in layers[1:]:
            if not l["inverted"]:
                break
            top = l["to_m"]
    regime = ("surface-based (model-indicated)" if surface_based else "elevated (model-indicated)" if inv else "none indicated")
    strength = round(max(x["t_f"] for x in lv if x["height_agl_m"] <= (top or lv[0]["height_agl_m"])) - lv[0]["t_f"], 2) if surface_based else 0.0
    return {"status": "ok", "layers": layers, "regime": regime, "inversion_top_m": top, "surface_inversion_strength_f": strength,
            "lowest_level_m": lv[0]["height_agl_m"],
            "resolution_note": f"The lowest model level is about {lv[0]['height_agl_m']:.0f} m above model ground, so a shallow inversion between 6 in and 10 ft is not resolved. This never overrides local sensors."}


# ---------------------------------------------------------------------------
# Multi-level interpolation and spray-plane analysis (ported from the
# backend-implementation branch's AtmosphericProfileInterpolator, with two
# changes: no extrapolation outside measured heights, and wind direction
# interpolated through speed-weighted u/v components).
def _pchip(xs, ys):
    from scipy.interpolate import PchipInterpolator
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    xs, ys = [xs[i] for i in order], [ys[i] for i in order]
    if len(xs) < 2 or xs[0] == xs[-1]:
        return None, None
    return PchipInterpolator(xs, ys, extrapolate=False), (xs[0], xs[-1])


def _levels(reading, canopy_ft):
    t, w = [], []
    for lv in (reading["lower"], reading["upper"]):
        if lv.get("temp_f") is not None:
            t.append((_agl_ft(lv["height_ft"], lv["ref"], canopy_ft) * FT, lv["temp_f"]))
        if lv.get("wind_installed", True) and lv.get("wind_mph") is not None and lv.get("dir_from_deg") is not None:
            w.append((_agl_ft(lv.get("wind_height_ft", lv["height_ft"]), lv.get("wind_ref", lv["ref"]), canopy_ft) * FT, lv["wind_mph"], lv["dir_from_deg"]))
    return t, w


class ProfileInterpolator:
    """Shape-preserving (PCHIP) interpolation across all measured levels. Returns None
    outside the measured range rather than extrapolating."""

    def __init__(self, t_levels, w_levels):
        self.t, self.t_rng = _pchip([z for z, _ in t_levels], [v for _, v in t_levels]) if len(t_levels) >= 2 else (None, None)
        if len(w_levels) >= 2:
            zs = [z for z, _, _ in w_levels]
            self.spd, self.w_rng = _pchip(zs, [s for _, s, _ in w_levels])
            rad = [math.radians(d) for _, _, d in w_levels]
            self.u, _ = _pchip(zs, [-s * math.sin(r) for (_, s, _), r in zip(w_levels, rad)])
            self.v, _ = _pchip(zs, [-s * math.cos(r) for (_, s, _), r in zip(w_levels, rad)])
        else:
            self.spd = self.u = self.v = self.w_rng = None

    def temperature(self, z_m):
        if self.t is None:
            return None
        v = float(self.t(z_m))
        return None if math.isnan(v) else v

    def wind(self, z_m):
        if self.spd is None:
            return None, None
        s = float(self.spd(z_m))
        if math.isnan(s):
            return None, None
        u, v = float(self.u(z_m)), float(self.v(z_m))
        return s, (math.degrees(math.atan2(-u, -v)) + 360) % 360


def spray_plane(release_agl_ft, reading, canopy_ft, offsets_m=(1.0, 3.0)):
    """Temperature difference and wind change from the release height to +1 m and +3 m above it,
    using only measured heights (no extrapolation). A positive difference means warmer air above
    the release height - an inversion layer that release droplets would sit under."""
    from app.geo import angle_diff
    if not reading:
        return {"status": "unavailable", "reason": "No paired reading."}
    t_lv, w_lv = _levels(reading, canopy_ft)
    ip = ProfileInterpolator(t_lv, w_lv)
    z0 = release_agl_ft * FT
    t0 = ip.temperature(z0)
    s0, d0 = ip.wind(z0)
    rows = []
    for dz in offsets_m:
        z = z0 + dz
        t = ip.temperature(z)
        s, d = ip.wind(z)
        rows.append({"offset_m": dz, "height_agl_ft": round(z / FT, 1),
                     "dt_f": None if (t is None or t0 is None) else round(t - t0, 2),
                     "speed_change_mph": None if (s is None or s0 is None) else round(s - s0, 2),
                     "dir_change_deg": None if (d is None or d0 is None) else round(angle_diff(d, d0)),
                     "status": "interpolated" if (t is not None and t0 is not None) else "outside_measured_range"})
    rng = ip.t_rng
    return {"status": "ok", "release_agl_ft": release_agl_ft, "rows": rows,
            "measured_temp_range_ft_agl": [round(rng[0] / FT, 2), round(rng[1] / FT, 2)] if rng else None,
            "method": "PCHIP across measured levels (linear when only two), wind direction via u/v components; no extrapolation",
            "note": "Within-layer values are interpolated between sensors, not measured at these heights. A two-sensor mast gives a straight-line profile."}
