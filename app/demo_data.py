"""Fictional demonstration district near Yuma, AZ.

Every boundary, grower, sensor and neighbor here is invented for the demo.
The basemap underneath is real; these overlays are not."""
from app.geo import rect, ring_lonlat, area_m2, centroid, to_lonlat

FICTIONAL = "Fictional demonstration boundary"

# Local metres from geo.ORIGIN. 1 acre = 4046.86 m2.
FIELDS = [
    {"id": "A", "canopy_ft": 1.0, "name": "Field A", "crop": "Romaine lettuce", "crop_class": "row",
     "grower": "Riverbend Demo Farms (fictional)", "poly": rect(-900, 0, -498, 402),
     "sensor_id": "S1", "setting": "Low river-bottom block"},
    {"id": "B", "canopy_ft": 2.0, "name": "Field B", "crop": "Broccoli", "crop_class": "row",
     "grower": "Desert Row Produce (fictional)", "poly": rect(300, 250, 702, 451),
     "sensor_id": "S2", "setting": "Valley block"},
    {"id": "C", "canopy_ft": 1.8, "name": "Field C", "crop": "Cauliflower", "crop_class": "row",
     "grower": "Sandhill Demo Growers (fictional)",
     # slightly irregular quadrilateral so pass clipping is visible
     "poly": [(300, -400), (1104, -400), (1104, 2), (360, 2)],
     "sensor_id": "S2", "setting": "Valley block"},
    {"id": "D", "canopy_ft": 12.0, "name": "Field D", "crop": "Lemons (orchard)", "crop_class": "orchard",
     "grower": "Mesa Grove Demo Co. (fictional)", "poly": rect(2600, 1500, 3203, 1902),
     "sensor_id": None, "setting": "Mesa orchard block (no paired-height sensor nearby)"},
]

# Simulated masts with explicit installed heights and reference surfaces.
# S1 follows the challenge tower example; S2 follows the NDSU near-surface method
# (temperature 9 in above the canopy and 9 ft above it; one wind sensor at 2 m above ground).
SIM_ACCURACY = "±0.5 °F per temperature sensor (prototype assumption - replace with the sensor specification)"
SENSORS = [
    {"id": "S1", "name": "Mast S1 (simulated)", "xy": (-520, 380), "heights_ft": [5, 30], "config": "challenge_tower",
     "temp": [{"level": "lower", "height_ft": 5.0, "ref": "ground"}, {"level": "upper", "height_ft": 30.0, "ref": "ground"}],
     "wind": [{"level": "lower", "height_ft": 5.0, "ref": "ground"}, {"level": "upper", "height_ft": 30.0, "ref": "ground"}],
     "temp_accuracy_f": 0.5, "shielding": "Simulated aspirated radiation shields", "averaging": "10-min mean (simulated)",
     "gust": "3-s gust, max in 10 min (simulated)"},
    {"id": "S2", "name": "Mast S2 (simulated)", "xy": (500, 120), "heights_ft": [0.75, 9], "config": "near_surface",
     "temp": [{"level": "lower", "height_ft": 0.75, "ref": "canopy"}, {"level": "upper", "height_ft": 9.0, "ref": "canopy"}],
     "wind": [{"level": "lower", "height_ft": 6.56, "ref": "ground"}],
     "temp_accuracy_f": 0.5, "shielding": "Simulated shaded sensors", "averaging": "10-min mean (simulated)",
     "gust": "3-s gust, max in 10 min (simulated)"},
]

# kind: neighbor_crop | worker_area | home | road | waterway
SENSITIVE = [
    {"id": "N1", "kind": "neighbor_crop", "name": "Organic leafy greens block (fictional neighbor)",
     "poly": rect(-900, -220, -498, -20),
     "constraint": {"type": "hold_when_toward", "source": "User-entered (fictional grower agreement)"}},
    {"id": "W1", "kind": "worker_area", "name": "Crew staging area (fictional)",
     "poly": rect(720, 300, 800, 380), "constraint": None},
    {"id": "H1", "kind": "home", "name": "Farm residences (fictional)",
     "poly": rect(350, 480, 450, 560), "constraint": None},
    {"id": "R1", "kind": "road", "name": "County road (illustrative placement)",
     "poly": rect(-1000, 210, 1200, 225), "constraint": None},
    {"id": "K1", "kind": "waterway", "name": "Irrigation ditch (fictional)",
     "poly": rect(-930, -250, -915, 450), "constraint": None},
]

# User-marked exclusion areas (seeded example; more can be added in the UI)
EXCLUSIONS = [
    {"id": "X1", "field_id": "C", "name": "Pump station & well head (user-marked)",
     "poly": rect(700, -220, 760, -160), "source": "User-entered"},
]

YARD = {"id": "yard", "name": "Equipment yard (fictional)", "xy": (100, -650)}


def acres(poly) -> float:
    return round(area_m2(poly) / 4046.86, 1)


def poly_geojson(poly):
    return {"type": "Polygon", "coordinates": [ring_lonlat(poly)]}


def field(fid):
    return next((f for f in FIELDS if f["id"] == fid), None)


def sensor(sid):
    return next((s for s in SENSORS if s["id"] == sid), None)


def fields_payload(user_areas=(), user_exclusions=()):
    feats = []
    for f in FIELDS:
        feats.append({
            "type": "Feature", "geometry": poly_geojson(f["poly"]),
            "properties": {"id": f["id"], "name": f["name"], "crop": f["crop"], "crop_class": f["crop_class"],
                           "grower": f["grower"], "acres": acres(f["poly"]), "sensor_id": f["sensor_id"],
                           "setting": f["setting"], "label": FICTIONAL,
                           "centroid": to_lonlat(*centroid(f["poly"]))}})
    sens = []
    for a in list(SENSITIVE) + list(user_areas):
        sens.append({"type": "Feature", "geometry": poly_geojson(a["poly"]),
                     "properties": {"id": a["id"], "kind": a["kind"], "name": a["name"],
                                    "constraint": a.get("constraint"),
                                    "user_added": a.get("user_added", False),
                                    "label": "User-marked area" if a.get("user_added") else FICTIONAL}})
    excl = [{"type": "Feature", "geometry": poly_geojson(e["poly"]),
             "properties": {"id": e["id"], "field_id": e["field_id"], "name": e["name"], "source": e["source"]}}
            for e in list(EXCLUSIONS) + list(user_exclusions)]
    sensors = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": to_lonlat(*s["xy"])},
                "properties": {"id": s["id"], "name": s["name"], "heights_ft": s["heights_ft"], "config": s["config"],
                               "temp": s["temp"], "wind": s["wind"], "label": "Simulated paired-height sensor"}} for s in SENSORS]
    return {
        "fields": {"type": "FeatureCollection", "features": feats},
        "sensitive": {"type": "FeatureCollection", "features": sens},
        "exclusions": {"type": "FeatureCollection", "features": excl},
        "sensors": {"type": "FeatureCollection", "features": sensors},
        "yard": {"name": YARD["name"], "coordinates": to_lonlat(*YARD["xy"])},
        "notice": "All field boundaries, growers, sensors and neighbors are fictional demonstration data overlaid on a real basemap.",
    }
