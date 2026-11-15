"""Source-backed ground-boom nozzle candidate engine (conventional broadcast spraying).

Only values transcribed from the loaded source are used. Anything else is
reported as a missing check - never estimated into a "verified" claim.

Source: TeeJet Technologies, "A User's Guide to Spray Technology" (li-tj416),
  p.19-20 (nominal flow-rate convention), p.76 (droplet class by tip size:
  XR110 at 30 psi, AIXR at 60 psi), p.94 (GPM formula and AIXR11004 table).
Supporting text: Purdue PPP-153 (nozzle colour code is separate from droplet-class
  colours; operating near range limits degrades pattern; XR produces more fines than
  AIXR at the same capacity)."""
import math
from app.catalog import ASABE_CLASSES, ASABE_NAMES

TJ = "TeeJet li-tj416 User's Guide to Spray Technology"
TJ_URL = "https://www.teejet.com/de-de/-/media/dam/agricultural/usa/sales-material/product-market-bulletin/li-tj416_user-guide-to-spray-technology.pdf"
PURDUE = "Purdue PPP-153 Agricultural Spray Nozzles: A Comprehensive Review"
PURDUE_URL = "https://ag.purdue.edu/department/extension/ppp/resources/ppp-publications/mobile/ppp-153/agricultural-spray-nozzles-a-comprehensive-review.html"

# Size code -> nominal GPM at 40 psi (TeeJet p.19: numbers are the nominal flow in US GPM at 40 PSI).
SIZES = {"01": 0.10, "015": 0.15, "02": 0.20, "025": 0.25, "03": 0.30, "04": 0.40, "05": 0.50,
         "06": 0.60, "08": 0.80, "10": 1.00, "15": 1.50, "20": 2.00}

# Documented droplet class at documented operating points: {(family, size): {psi: (class, gpm or None, page)}}
DOC = {}
for size, cls in zip(["01", "015", "02", "025", "03", "04", "05", "06", "08", "10", "15", "20"],
                     ["F", "F", "F", "M", "M", "M", "M", "M", "M", "C", "C", "VC"]):
    DOC[("XR", size)] = {30: (cls, None, 76)}
for size, cls in zip(["015", "02", "025", "03", "04", "05", "06", "08", "10"], ["M", "M", "M", "M", "C", "C", "C", "VC", "VC"]):
    DOC[("AIXR", size)] = {60: (cls, None, 76)}
# Full pressure table for AIXR11004 (p.94)
DOC[("AIXR", "04")] = {15: ("XC", 0.24, 94), 20: ("VC", 0.28, 94), 30: ("VC", 0.35, 94), 40: ("C", 0.40, 94),
                       50: ("C", 0.45, 94), 60: ("C", 0.49, 94), 75: ("M", 0.55, 94), 90: ("M", 0.60, 94)}

FAMILIES = {
    "XR": {"model": "TeeJet XR110 (Extended Range flat fan)", "angle": 110, "pattern": "Tapered flat fan",
           "why": "Conventional flat fan: finer spectrum at a given size than air-induction tips (Purdue PPP-153), which can aid coverage but adds driftable fines."},
    "AIXR": {"model": "TeeJet AIXR110 (Air Induction XR flat fan)", "angle": 110, "pattern": "Tapered flat fan, air-induction",
             "why": "Air induction produces fewer fine droplets than XR at the same capacity (Purdue PPP-153); coarser spectra can reduce coverage on small targets."},
}


def required_gpm(gpa, mph, spacing_in):
    """US GPA x MPH x nozzle spacing (in) / 5940 - conventional broadcast ground boom (TeeJet p.94)."""
    return gpa * mph * spacing_in / 5940


def _doc_class(family, size, psi):
    """Droplet class at psi if documented, or bounded between two documented rows of the same class."""
    rows = DOC.get((family, size), {})
    if not rows:
        return None, "No droplet table for this tip in the loaded source"
    pts = sorted(rows)
    for p_ in pts:
        if abs(p_ - psi) < 0.5:
            return rows[p_][0], f"{TJ} p.{rows[p_][2]} ({p_} psi row)"
    below = [p_ for p_ in pts if p_ < psi]
    above = [p_ for p_ in pts if p_ > psi]
    if below and above and rows[below[-1]][0] == rows[above[0]][0]:
        return rows[below[-1]][0], f"{TJ} p.{rows[below[-1]][2]} (between the {below[-1]} and {above[0]} psi rows, both {rows[below[-1]][0]})"
    return None, (f"Droplet class at {psi:.0f} psi is not documented in the loaded source (documented: "
                  + ", ".join(f"{p_} psi {rows[p_][0]}" for p_ in pts) + ")")


def _doc_range(family, size):
    rows = DOC.get((family, size), {})
    if len(rows) >= 2:
        return min(rows), max(rows)
    return None


def evaluate(gpa, mph, spacing_in, *, min_class=None, pump_min_psi=None, pump_max_psi=None, release_height_in=None,
             families=("AIXR", "XR"), configured=None):
    """Return candidate cards for every documented family/size. Ranking: fully documented
    operating point that meets the entered droplet requirement first, then smaller pressure-limit
    risk. Coarser is not assumed better."""
    missing_inputs = [n for n, v in (("carrier volume (GPA)", gpa), ("ground speed (mph)", mph), ("nozzle spacing (in)", spacing_in)) if not v]
    if missing_inputs:
        return {"status": "blocked", "message": "Nozzle candidates need: " + ", ".join(missing_inputs) + ".", "candidates": [], "required_gpm": None}
    q = required_gpm(gpa, mph, spacing_in)
    cands = []
    for fam in families:
        for size, q40 in SIZES.items():
            if (fam, size) not in DOC:
                continue
            psi = 40 * (q / q40) ** 2   # flow scales with the square root of pressure (nominal-rating convention)
            rng = _doc_range(fam, size)
            cls, cls_src = _doc_class(fam, size, psi)
            checks, missing = [], []
            if rng:
                ok = rng[0] <= psi <= rng[1]
                checks.append(("Pressure within documented table range", ok, f"{rng[0]}-{rng[1]} psi ({TJ} p.94)"))
            else:
                missing.append("Documented operating-pressure range for this tip (not in the loaded source)")
                ok = None
            if pump_max_psi is not None:
                checks.append(("Within pump/controller limit", psi <= pump_max_psi and (pump_min_psi is None or psi >= pump_min_psi),
                               f"{pump_min_psi or 0}-{pump_max_psi} psi (operator-entered)"))
            else:
                missing.append("Pump/controller pressure limits")
            if cls is None:
                missing.append(cls_src)
            if min_class:
                if cls:
                    checks.append((f"Droplet class {cls} meets {min_class}-or-coarser requirement",
                                   ASABE_CLASSES.index(cls) >= ASABE_CLASSES.index(min_class), "Product requirement (as entered)"))
                else:
                    missing.append("Droplet-class requirement check (class unknown at this pressure)")
            else:
                missing.append("Product droplet-class requirement (not entered)")
            missing.append("PWM compatibility (not modelled)")
            if release_height_in is None:
                missing.append("Boom release height")
            # expected flow at the proposed pressure: table value when documented at that row
            rows = DOC.get((fam, size), {})
            row = next((rows[p_] for p_ in rows if abs(p_ - psi) < 0.5 and rows[p_][1] is not None), None)
            expected = row[1] if row else round(q40 * math.sqrt(psi / 40), 3)
            failed = [("Fails: " + c[0].lower()) for c in checks if c[1] is False]
            verified = cls is not None and ok is True and not failed and min_class is not None
            cands.append({
                "id": f"{fam}110{size}", "family": fam, "model": f"{fam}110{size}", "family_name": FAMILIES[fam]["model"],
                "size_code": size, "nominal_gpm_at_40psi": q40, "angle_deg": FAMILIES[fam]["angle"], "pattern": FAMILIES[fam]["pattern"],
                "proposed_psi": round(psi, 1), "required_gpm": round(q, 3), "expected_gpm": round(expected, 3),
                "droplet_class": cls, "droplet_class_name": ASABE_NAMES.get(cls) if cls else None, "droplet_source": cls_src,
                "checks": [{"label": c[0], "ok": c[1], "source": c[2]} for c in checks],
                "missing": missing, "failed": failed, "fully_documented": verified,
                "family_fit": FAMILIES[fam]["why"],
                "source": {"title": TJ, "url": TJ_URL, "pages": sorted({r[2] for r in rows.values()})},
                "selected": configured == f"{fam}110{size}",
            })

    def rank(c):
        risk = 0 if c["fully_documented"] else 1
        margin = 0
        rng = _doc_range(c["family"], c["size_code"])
        if rng:
            margin = -min(c["proposed_psi"] - rng[0], rng[1] - c["proposed_psi"])   # prefer mid-range pressure
        return (risk, len(c["failed"]), margin, c["proposed_psi"])

    cands.sort(key=rank)
    best = cands[0] if cands and cands[0]["fully_documented"] else None
    for c in cands:
        fam_sizes = [x for x in cands if x["family"] == c["family"]]
        smaller = [x for x in fam_sizes if SIZES[x["size_code"]] < SIZES[c["size_code"]]]
        larger = [x for x in fam_sizes if SIZES[x["size_code"]] > SIZES[c["size_code"]]]
        c["why_size"] = (f"Delivers the required {q:.3f} GPM at about {c['proposed_psi']:.0f} psi "
                         f"(nominal {c['nominal_gpm_at_40psi']} GPM at 40 psi).")
        notes = []
        def why_not(x):
            docs = [m_ for m_ in x["missing"] if m_.startswith("Droplet class at")] or [m_ for m_ in x["missing"] if m_.startswith("Documented operating-pressure")]
            issues = x["failed"] + docs[:1]
            return f"{x['model']} would need about {x['proposed_psi']:.0f} psi" + (f" ({'; '.join(issues)})" if issues else " (documented checks pass)") + "."
        if smaller:
            notes.append("Smaller: " + why_not(max(smaller, key=lambda x: SIZES[x["size_code"]])))
        if larger:
            notes.append("Larger: " + why_not(min(larger, key=lambda x: SIZES[x["size_code"]])))
        c["alternatives"] = notes
        c["rank_reason"] = ("Recommended: fully documented operating point that meets the entered requirement, with the most pressure margin."
                            if c is best else ("Candidate: documented checks pass but other candidates rank higher." if c["fully_documented"]
                                               else "Not recommended: " + ("; ".join(c["failed"] + c["missing"][:2]))))
    return {"status": "ok" if best else "none", "required_gpm": round(q, 3),
            "formula": "GPM per nozzle = GPA x MPH x spacing(in) / 5940 (conventional broadcast ground boom; US units)",
            "formula_source": f"{TJ} p.94", "recommended": best["id"] if best else None,
            "message": None if best else "No candidate has a fully documented operating point that meets the entered requirement.",
            "candidates": cands[:8],
            "notes": ["Nozzle size code is nominal flow at 40 psi; it is not a droplet size. Tip colour codes are separate from droplet-class colours (Purdue PPP-153).",
                      "A nozzle change cannot override an inversion or any other blocking weather condition.",
                      "No quantified drift reduction is claimed."]}
