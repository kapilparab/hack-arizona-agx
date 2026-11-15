"""Equipment compatibility, job-duration estimates, and nozzle comparison.

No equipment change can override a weather or product STOP: this module only
reports configuration conflicts; weather status is evaluated separately."""
import math
from app import catalog, demo_data, paths, nozzles
from app.geo import buffer_convex

FT = 0.3048


def swath_and_speed(utype: str, cfg: dict):
    if utype == "ground_boom":
        return cfg["swath_ft"] * FT, cfg["speed_mph"] * 0.44704, None
    if utype == "airblast":
        return cfg["row_spacing_ft"] * FT, cfg["speed_mph"] * 0.44704, None
    if utype == "drone":
        sw = cfg["swath_m"]
        # flow-limited ground speed: flow (L/s) / (rate L/m2 * swath m)
        flow_speed = (cfg["flow_l_min"] / 60) / ((cfg["rate_l_ha"] / 10000) * sw) if cfg["rate_l_ha"] > 0 else cfg["speed_m_s"]
        sp = min(cfg["speed_m_s"], flow_speed)
        note = None if sp == cfg["speed_m_s"] else f"Speed limited to {sp:.1f} m/s by flow rate and application rate."
        return sw, sp, note
    raise ValueError(f"unsupported equipment type {utype}")


def field_exclusions(field_id: str, product: dict | None, user_exclusions=(), user_areas=()):
    """User exclusions on this field plus product buffers around matching sensitive areas."""
    ex, buffers = [], []
    for e in list(demo_data.EXCLUSIONS) + list(user_exclusions):
        if e["field_id"] == field_id:
            ex.append(e["poly"])
    bufs = (product or {}).get("constraints", {}).get("buffers", {}).get("value") or []
    for b in bufs:
        for a in list(demo_data.SENSITIVE) + list(user_areas):
            if a["kind"] == b["kind"]:
                poly = buffer_convex(a["poly"], b["ft"] * FT)
                ex.append(poly)
                buffers.append({"area_id": a["id"], "area": a["name"], "ft": b["ft"],
                                "source": product["constraints"]["buffers"]["source"], "poly": poly})
    return ex, buffers


def plan_paths(field: dict, utype: str, cfg: dict, orientation_deg=0.0, product=None, user_exclusions=(), user_areas=()):
    sw, _, _ = swath_and_speed(utype, cfg)
    ex, buffers = field_exclusions(field["id"], product, user_exclusions, user_areas)
    return paths.generate(field["poly"], sw, orientation_deg, ex), buffers


def estimate(field: dict, utype: str, cfg: dict, plan: dict) -> dict:
    sw, sp, note = swath_and_speed(utype, cfg)
    spray_min = plan["spray_m"] / sp / 60
    turn_min = plan["turns"] * cfg.get("turn_s", 30) / 60
    transit_min = plan["transit_m"] / max(sp, 0.5) / 60
    acres = plan["treated_acres"]
    if utype == "drone":
        vol = cfg["rate_l_ha"] * acres * 0.404686
        loads = max(1, math.ceil(vol / cfg["tank_l"]))
        per_reload = cfg["refill_min"] + cfg["battery_swap_min"]
        unit_label = f"{vol:.0f} L"
        reload_note = "Assumes one battery swap per tank load (prototype assumption - adjust to your battery cycle)."
    else:
        vol = cfg["rate_gpa"] * acres
        loads = max(1, math.ceil(vol / cfg["tank_gal"]))
        per_reload = cfg["refill_min"]
        unit_label = f"{vol:.0f} gal"
        reload_note = "First load filled during setup."
    reload_min = (loads - 1) * per_reload
    total = spray_min + turn_min + transit_min + reload_min
    return {"spray_min": round(spray_min), "turn_min": round(turn_min), "transit_min": round(transit_min),
            "reload_min": round(reload_min), "loads": loads, "volume": unit_label, "setup_min": cfg.get("setup_min", 20),
            "total_min": int(math.ceil(total / 5) * 5), "speed_m_s": round(sp, 2), "swath_m": round(sw, 1),
            "treated_acres": acres,
            "notes": [n for n in (note, reload_note) if n],
            "basis": "Path length / speed + turns + reloads. Operator inputs; not a field-validated time study."}


def _pressure_check(cfg):
    """Standard broadcast calibration: gpm/nozzle = GPA x mph x spacing(in) / 5940.
    Tip size code '04' = nominal 0.4 gpm at 40 psi (rating convention); flow ~ sqrt(pressure)."""
    try:
        q40 = int(cfg["orifice_size"]) / 10
    except (KeyError, ValueError, TypeError):
        return None
    need_gpm = cfg["rate_gpa"] * cfg["speed_mph"] * cfg["nozzle_spacing_in"] / 5940
    need_psi = 40 * (need_gpm / q40) ** 2
    deliv_gpa = q40 * math.sqrt(cfg["pressure_psi"] / 40) * 5940 / (cfg["speed_mph"] * cfg["nozzle_spacing_in"])
    return {"required_gpm": round(need_gpm, 3), "required_psi": round(need_psi, 1),
            "configured_psi": cfg["pressure_psi"], "delivered_gpa_at_configured": round(deliv_gpa, 1),
            "mismatch": abs(deliv_gpa - cfg["rate_gpa"]) / cfg["rate_gpa"] > 0.10,
            "basis": "Standard broadcast calibration formula and nominal 40 psi tip rating; confirm with the manufacturer chart."}


def evaluate(field: dict, unit_id: str, cfg_override: dict | None, product: dict | None,
             orientation_deg=0.0, user_exclusions=(), user_areas=()):
    u = catalog.unit(unit_id)
    if not u:
        return {"error": f"Unknown equipment unit {unit_id}"}
    utype = u["type"]
    et = catalog.EQUIPMENT_TYPES[utype]
    cfg = {**u["config"], **(cfg_override or {})}
    issues = []

    def add(sev, code, msg, source=""):
        issues.append({"severity": sev, "code": code, "message": msg, "source": source})

    if et.get("unsupported"):
        add("block", "unsupported", et["unsupported"])
    if field["crop_class"] not in et["crop_classes"]:
        add("block", "crop_mismatch", f"{et['name']} is not set up for {field['crop']} ({field['crop_class']} crops) in this prototype.",
            "Prototype compatibility rule")
    noz = catalog.NOZZLES.get(cfg.get("nozzle_id"))
    if not noz or utype not in noz["compatible_with"]:
        add("block", "nozzle_incompatible",
            f"{noz['model'] if noz else cfg.get('nozzle_id')} is not compatible with {et['name']}." +
            (" TeeJet tractor tips are not interchangeable with drone atomizers." if utype == "drone" or (noz and noz['family'] == 'drone_atomizer') else ""),
            "Catalog compatibility")

    prod_c = (product or {}).get("constraints", {})
    methods = prod_c.get("methods", {}).get("value")
    if product is None or methods is None:
        add("warn", "method_unknown", "Permitted application methods not entered for this product.", "Not entered")
    elif utype not in methods:
        add("block", "method_not_permitted", f"{product['name']}: {et['name'].lower()} is not a permitted method.",
            prod_c["methods"]["source"])

    req = prod_c.get("min_droplet_class", {}).get("value")
    if req is None:
        add("warn", "droplet_req_unknown", "Droplet-size requirement not entered for this product - cannot check the configuration against it.", "Not entered")
    elif utype == "drone":
        add("block", "droplet_unverifiable",
            f"Product requires ASABE {catalog.ASABE_NAMES[req]} or coarser. The atomizer is set to {cfg.get('droplet_um')} µm, "
            "which is not an ASABE droplet class - the requirement cannot be verified until a class is confirmed for this setting.",
            prod_c["min_droplet_class"]["source"])
    else:
        # Ground boom / airblast: documented class at the configured tip and pressure first,
        # operator-entered class only as a labeled fallback.
        fam = {"teejet_xr": "XR", "teejet_aixr": "AIXR"}.get(cfg.get("nozzle_id"))
        doc_cls, doc_src = (nozzles._doc_class(fam, str(cfg.get("orifice_size")), float(cfg.get("pressure_psi") or 0))
                            if fam and utype == "ground_boom" else (None, "No documented table for this nozzle in the loaded source"))
        ent = doc_cls or cfg.get("droplet_class_entered")
        src = doc_src if doc_cls else "Operator-entered from the manufacturer chart (not verified by this app)"
        if not ent:
            add("block", "droplet_class_missing",
                f"Product requires ASABE {catalog.ASABE_NAMES[req]} or coarser, but the droplet class at this tip and pressure is not documented here and none was entered. {doc_src}.",
                prod_c["min_droplet_class"]["source"])
        elif catalog.ASABE_CLASSES.index(ent) < catalog.ASABE_CLASSES.index(req):
            add("block", "droplet_too_fine",
                f"Class {catalog.ASABE_NAMES[ent]} at this tip and pressure is finer than the required {catalog.ASABE_NAMES[req]} ({src}).",
                prod_c["min_droplet_class"]["source"])
        else:
            add("info", "droplet_ok", f"Class {catalog.ASABE_NAMES[ent]} meets the {catalog.ASABE_NAMES[req]}-or-coarser requirement ({src}).", src)

    pressure = _pressure_check(cfg) if utype == "ground_boom" else None
    if pressure and pressure["mismatch"]:
        add("warn", "rate_mismatch",
            f"At {cfg['pressure_psi']} psi this tip delivers about {pressure['delivered_gpa_at_configured']} GPA, not the "
            f"{cfg['rate_gpa']} GPA target (needs ~{pressure['required_psi']} psi). Pressure also changes droplet class.", pressure["basis"])

    plan = buffers = est = None
    if not any(i["code"] in ("unsupported",) for i in issues):
        plan, buffers = plan_paths(field, utype, cfg, orientation_deg, product, user_exclusions, user_areas)
        est = estimate(field, utype, cfg, plan)
        for b in buffers:
            add("warn", "buffer_untreated",
                f"{b['ft']} ft buffer from {b['area']} ({b['source']}) is excluded from treatment. "
                "Changing equipment does not remove this constraint.", b["source"])
        if plan["excluded_acres"] > 0:
            add("info", "excluded_area", f"{plan['excluded_acres']} ac inside the field is excluded and will not be treated.", "User-marked / buffer")

    candidates = []
    for nid, n in catalog.NOZZLES.items():
        if utype in n["compatible_with"]:
            candidates.append({"id": nid, "model": n["model"], "selected": nid == cfg.get("nozzle_id"),
                               "verified": n["verified"], "tradeoff": n["tradeoff"], "source": n["source"],
                               "illustration": n["illustration"], "illustration_note": n["illustration_note"],
                               "missing": [] if n["verified"] else ["Pressure-dependent droplet classification for the chosen size (manufacturer chart)"]})
    recommendation = {
        "status": "comparison_only",
        "message": "No nozzle is recommended: verified pressure-dependent droplet data is not loaded in this build. "
                   "Compare candidates and read the class for your tip size and pressure from the manufacturer chart.",
    }
    nozzle_eval = None
    if utype == "ground_boom":
        fam = {"teejet_xr": "XR", "teejet_aixr": "AIXR"}.get(cfg.get("nozzle_id"))
        nozzle_eval = nozzles.evaluate(cfg.get("rate_gpa"), cfg.get("speed_mph"), cfg.get("nozzle_spacing_in"),
                                       min_class=req, pump_min_psi=cfg.get("pump_min_psi"), pump_max_psi=cfg.get("pump_max_psi"),
                                       release_height_in=cfg.get("boom_height_in"),
                                       configured=f"{fam}110{cfg.get('orifice_size')}" if fam else None)
    elif utype == "airblast":
        nozzle_eval = {"status": "not_modelled", "candidates": [], "message": "Airblast nozzle/airflow selection depends on canopy and fan settings that are not modelled here. Use the UC Airblast Spray Advisor; ground-boom formulas are not applied to airblast."}
    elif utype == "drone":
        nozzle_eval = {"status": "not_modelled", "candidates": [], "message": "Drone centrifugal atomizers are configured by droplet size (µm), flow, swath, speed and height. TeeJet ground-boom formulas and compatibility are not applied."}
    blocking = [i for i in issues if i["severity"] == "block"]
    return {"unit": {k: u[k] for k in ("id", "name", "type", "crew", "shift")}, "type_info": {k: et.get(k) for k in ("name", "illustration", "illustration_note", "reference", "advisor", "unsupported")},
            "config": cfg, "config_source": u["config_source"], "issues": issues, "compatible": not blocking,
            "status": "conflict" if blocking else "candidate",
            "estimate": est, "path": plan, "buffers": [{k: v for k, v in b.items() if k != "poly"} for b in (buffers or [])],
            "pressure": pressure, "candidates": candidates, "recommendation": recommendation, "nozzle_engine": nozzle_eval,
            "weather_note": "Equipment choice cannot clear a weather or product Stop. An inversion blocks every configuration."}
