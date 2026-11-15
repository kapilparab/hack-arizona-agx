"""Small planar geometry helpers in a local metric frame (equirectangular,
adequate over a few km). No external GIS dependency."""
import math

ORIGIN = (32.660, -114.720)  # lat, lon of the fictional demo district origin
_M_LAT = 110540.0
_M_LON = 111320.0 * math.cos(math.radians(ORIGIN[0]))


def to_lonlat(x: float, y: float) -> list[float]:
    return [round(ORIGIN[1] + x / _M_LON, 6), round(ORIGIN[0] + y / _M_LAT, 6)]


def to_xy(lon: float, lat: float) -> tuple[float, float]:
    return ((lon - ORIGIN[1]) * _M_LON, (lat - ORIGIN[0]) * _M_LAT)


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def ring_lonlat(poly):
    pts = [to_lonlat(x, y) for x, y in poly]
    return pts + [pts[0]]


def area_m2(poly) -> float:
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def centroid(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def angle_diff(a: float, b: float) -> float:
    """Smallest circular difference in degrees: 350 vs 10 -> 20."""
    d = abs(a - b) % 360.0
    return 360.0 - d if d > 180.0 else d


def bearing(p, q) -> float:
    """Compass bearing (0=N, 90=E) from p to q in the local frame."""
    return (math.degrees(math.atan2(q[0] - p[0], q[1] - p[1])) + 360.0) % 360.0


def _seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(p[0] - cx, p[1] - cy), (cx, cy)


def point_in_poly(p, poly) -> bool:
    x, y = p
    inside = False
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xi:
                inside = not inside
    return inside


def poly_distance(A, B):
    """Minimum distance between two polygons and the nearest point on B."""
    if any(point_in_poly(p, B) for p in A) or any(point_in_poly(p, A) for p in B):
        return 0.0, centroid(B)
    best = (float("inf"), None)
    for P, Q in ((A, B), (B, A)):
        for p in P:
            for i in range(len(Q)):
                d, c = _seg_dist(p, Q[i], Q[(i + 1) % len(Q)])
                if d < best[0]:
                    best = (d, c if Q is B else p)
    return best


def convex_hull(points):
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def buffer_convex(poly, d: float, n: int = 12):
    """Outward buffer of a convex polygon (hull of vertex circles)."""
    pts = []
    for x, y in poly:
        for k in range(n):
            a = 2 * math.pi * k / n
            pts.append((x + d * math.cos(a), y + d * math.sin(a)))
    return convex_hull(pts)


def rotate(p, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)
