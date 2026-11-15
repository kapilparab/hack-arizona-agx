"""Illustrative parallel application passes clipped to a field polygon.
These are demonstration paths, not validated navigation commands."""
import math
from app.geo import rotate, to_lonlat, area_m2


def _intervals_on_line(poly, y):
    xs = []
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    xs.sort()
    return [(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2)]


def _subtract(intervals, cuts):
    out = intervals
    for c0, c1 in cuts:
        nxt = []
        for a, b in out:
            if c1 <= a or c0 >= b:
                nxt.append((a, b))
                continue
            if c0 > a:
                nxt.append((a, c0))
            if c1 < b:
                nxt.append((c1, b))
        out = nxt
    return [(a, b) for a, b in out if b - a > 1.0]


def generate(field_poly, swath_m: float, orientation_deg: float = 0.0, exclusions=(), headland_turn=True):
    """Passes run along `orientation_deg` (0 = north-south rows). Returns segments in lon/lat."""
    swath_m = max(1.0, float(swath_m))
    # rotate so passes are horizontal (along x) in the working frame
    rot = orientation_deg - 90.0
    P = [rotate(p, -rot) for p in field_poly]
    X = [[rotate(p, -rot) for p in e] for e in exclusions]
    ys = [p[1] for p in P]
    y = min(ys) + swath_m / 2
    lines = []
    while y < max(ys):
        iv = _intervals_on_line(P, y)
        cuts = []
        for e in X:
            cuts += _intervals_on_line(e, y)
        lines.append((y, iv, _subtract(iv, cuts)))
        y += swath_m

    segs = []
    pos = None
    spray_m = turn_m = transit_m = 0.0
    excluded_m = 0.0
    for idx, (y, full, keep) in enumerate(lines):
        ltr = idx % 2 == 0
        parts = keep if ltr else [(b, a) for a, b in reversed(keep)]
        excluded_m += sum(b - a for a, b in full) - sum(b - a for a, b in keep)
        for j, (a, b) in enumerate(parts):
            start, end = (a, y), (b, y)
            if pos is not None:
                gap = math.dist(pos, start)
                if j == 0 and headland_turn:
                    # semicircular-ish headland turn between consecutive lines
                    # semicircle bulging outward past the end of the previous pass
                    bulge = 1 if (idx - 1) % 2 == 0 else -1
                    r = max(abs(start[1] - pos[1]) / 2, swath_m / 2)
                    pts = [pos]
                    for k in range(1, 8):
                        th = math.pi * k / 8
                        f = (1 - math.cos(th)) / 2
                        pts.append((pos[0] + (start[0] - pos[0]) * f + bulge * r * math.sin(th),
                                    pos[1] + (start[1] - pos[1]) * f))
                    pts.append(start)
                    L = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
                    turn_m += L
                    segs.append({"type": "turn", "pts": pts, "length_m": L, "pass": idx})
                else:
                    transit_m += gap
                    segs.append({"type": "transit", "pts": [pos, start], "length_m": gap, "pass": idx,
                                 "note": "Non-spraying move around an excluded area"})
            L = abs(b - a)
            spray_m += L
            segs.append({"type": "spray", "pts": [start, end], "length_m": L, "pass": idx})
            pos = end

    for s in segs:
        s["coords"] = [to_lonlat(*rotate(p, rot)) for p in s.pop("pts")]
        s["length_m"] = round(s["length_m"], 1)
    field_area = area_m2(field_poly)
    excluded_area = excluded_m * swath_m
    return {"segments": segs, "passes": len(lines), "spray_m": round(spray_m), "turn_m": round(turn_m),
            "transit_m": round(transit_m), "orientation_deg": orientation_deg, "swath_m": swath_m,
            "treated_acres": round(spray_m * swath_m / 4046.86, 1),
            "excluded_acres": round(excluded_area / 4046.86, 2), "field_acres": round(field_area / 4046.86, 1),
            "turns": sum(1 for s in segs if s["type"] == "turn"),
            "note": "Illustrative passes for demonstration - not validated navigation commands."}
