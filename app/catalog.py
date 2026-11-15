"""Equipment, nozzle/atomizer and product catalog.

Honesty rules applied here:
- Manufacturer figures (pressure ranges, droplet tables, drone specs) were NOT
  verified during this build, so they are left null with a source link to consult.
- Droplet classification for a configured nozzle is operator-entered from the
  manufacturer chart and labeled as such.
- Products are fictional demo entries; their constraints are demo assumptions.
"""

ASABE_CLASSES = ["VF", "F", "M", "C", "VC", "XC", "UC"]
ASABE_NAMES = {"VF": "Very Fine", "F": "Fine", "M": "Medium", "C": "Coarse",
               "VC": "Very Coarse", "XC": "Extremely Coarse", "UC": "Ultra Coarse"}
ASABE_NOTE = ("ASABE S572 classes are assigned by comparison with reference nozzles; "
              "the class for a tip depends on its size and operating pressure. Read it from the manufacturer chart.")

EQUIPMENT_TYPES = {
    "ground_boom": {
        "name": "Tractor-mounted / self-propelled boom sprayer",
        "illustration": "img/boom.svg", "illustration_note": "Generic illustration, not a specific product",
        "nozzle_family": "hydraulic_flat_fan", "crop_classes": ["row"],
        "fields": ["nozzle_id", "orifice_size", "pressure_psi", "nozzle_spacing_in", "speed_mph",
                   "rate_gpa", "boom_height_in", "swath_ft", "tank_gal", "refill_min", "setup_min", "turn_s",
                   "droplet_class_entered"],
    },
    "airblast": {
        "name": "Orchard airblast sprayer",
        "illustration": "img/airblast.svg", "illustration_note": "Generic illustration, not a specific product",
        "nozzle_family": "hollow_cone", "crop_classes": ["orchard"],
        "fields": ["nozzle_id", "pressure_psi", "speed_mph", "rate_gpa", "row_spacing_ft", "tank_gal",
                   "refill_min", "setup_min", "turn_s", "fan_setting", "droplet_class_entered"],
        "advisor": {"name": "UC Airblast Spray Advisor", "url": "https://ucanr.edu/site/airblast-spray-advisor",
                    "note": "Canopy and airflow calibration is not modeled here; use the UC advisor for those inputs."},
    },
    "drone": {
        "name": "Agricultural spray drone",
        "illustration": "img/drone.svg",
        "illustration_note": "Generic illustration. Reference product: DJI AGRAS T50 (see source). Not a manufacturer photo.",
        "reference": {"model": "DJI AGRAS T50", "url": "https://ag.dji.com/t50", "faq": "https://ag.dji.com/t50/faq",
                      "note": "Cited as a reference product only. Not claimed to be optimal or in local use. "
                              "Specifications were not verified in this build - check the DJI page before relying on any figure."},
        "nozzle_family": "drone_atomizer", "crop_classes": ["row", "orchard"],
        "fields": ["nozzle_id", "droplet_um", "flow_l_min", "swath_m", "speed_m_s", "height_m", "rate_l_ha",
                   "tank_l", "battery_swap_min", "refill_min", "setup_min", "turn_s"],
    },
    "aircraft": {
        "name": "Fixed-wing / rotary aircraft (optional extension)", "illustration": "img/aircraft.svg",
        "illustration_note": "Generic illustration", "nozzle_family": None, "crop_classes": [],
        "unsupported": "Not implemented in this prototype: aerial application planning needs flight-line, "
                       "ferry and swath-displacement inputs that are not modeled.",
    },
    "chemigation": {
        "name": "Irrigation sprinkler / chemigation", "illustration": None, "nozzle_family": None, "crop_classes": [],
        "unsupported": "Kept separate and unsupported: chemigation has its own system and label requirements "
                       "that this prototype does not implement.",
    },
}

UNVERIFIED = "Not verified in this build - consult the source before use"

NOZZLES = {
    "teejet_xr": {
        "model": "TeeJet XR (Extended Range flat fan)", "family": "hydraulic_flat_fan", "application": "Ground boom broadcast",
        "compatible_with": ["ground_boom"], "illustration": "img/nozzle-flatfan.svg",
        "illustration_note": "Generic flat-fan illustration, not a manufacturer photo",
        "pressure_range_psi": None, "droplet_by_pressure": None, "verified": False, "verification_note": UNVERIFIED,
        "source": "https://www.teejet.com", "tradeoff": "Conventional flat fan. Typically produces finer spectra than air-induction "
        "tips of the same size, which can improve coverage but increases the fine fraction that can move off-target.",
    },
    "teejet_aixr": {
        "model": "TeeJet AIXR (air-induction flat fan)", "family": "hydraulic_flat_fan", "application": "Ground boom broadcast",
        "compatible_with": ["ground_boom"], "illustration": "img/nozzle-airinduction.svg",
        "illustration_note": "Generic air-induction illustration, not a manufacturer photo",
        "pressure_range_psi": None, "droplet_by_pressure": None, "verified": False, "verification_note": UNVERIFIED,
        "source": "https://www.teejet.com/spray-application-products/spray-product-type/spray-tips/aixr",
        "tradeoff": "Air induction produces coarser droplets than a conventional tip of the same size. Fewer fines, "
                    "but coverage on small targets may drop - check the treatment requirement.",
    },
    "teejet_tti": {
        "model": "TeeJet TTI (Turbo TeeJet Induction)", "family": "hydraulic_flat_fan", "application": "Ground boom broadcast",
        "compatible_with": ["ground_boom"], "illustration": "img/nozzle-airinduction.svg",
        "illustration_note": "Generic air-induction illustration, not a manufacturer photo",
        "pressure_range_psi": None, "droplet_by_pressure": None, "verified": False, "verification_note": UNVERIFIED,
        "source": "https://www.teejet.com/spray-application-products/spray-product-type/spray-tips/tti",
        "tradeoff": "Among the coarsest induction tips. Not automatically best: very coarse spectra can reduce coverage "
                    "and may not meet a product's coverage needs.",
    },
    "hollow_cone_airblast": {
        "model": "Hollow-cone disc-core (generic airblast)", "family": "hollow_cone", "application": "Orchard airblast",
        "compatible_with": ["airblast"], "illustration": "img/nozzle-cone.svg",
        "illustration_note": "Generic hollow-cone illustration", "pressure_range_psi": None, "droplet_by_pressure": None,
        "verified": False, "verification_note": UNVERIFIED, "source": "https://ucanr.edu/site/airblast-spray-advisor",
        "tradeoff": "Airblast deposition depends heavily on fan airflow and canopy; nozzle choice alone does not set drift potential.",
    },
    "dji_t50_atomizer": {
        "model": "DJI AGRAS T50 centrifugal atomizing system (reference)", "family": "drone_atomizer",
        "application": "Drone application", "compatible_with": ["drone"], "illustration": "img/nozzle-atomizer.svg",
        "illustration_note": "Generic rotary-atomizer illustration, not a DJI photo",
        "pressure_range_psi": None, "droplet_by_pressure": None, "verified": False, "verification_note": UNVERIFIED,
        "source": "https://ag.dji.com/t50",
        "tradeoff": "Droplet size is set electronically in micrometres, not as an ASABE class from a pressure chart. "
                    "A product requirement stated as an ASABE class cannot be verified from the atomizer setting alone.",
        "not_compatible_note": "TeeJet tractor tips are not interchangeable with this atomizing system.",
    },
}

DEMO = "Demo assumption - replace with the product label"
PRODUCTS = {
    "demo_r": {
        "name": "Demo Insecticide R (fictional)", "is_demo": True,
        "constraints": {
            "max_wind_mph": {"value": 10.0, "source": DEMO},
            "min_droplet_class": {"value": "M", "source": DEMO},
            "rainfast_h": {"value": 4.0, "source": DEMO},
            "temp_range_f": {"value": None, "source": "Not entered"},
            "methods": {"value": ["ground_boom", "airblast", "drone"], "source": DEMO},
            "buffers": {"value": [], "source": DEMO},
        },
    },
    "demo_h": {
        "name": "Demo Herbicide H (fictional)", "is_demo": True,
        "constraints": {
            "max_wind_mph": {"value": 10.0, "source": DEMO},
            "min_droplet_class": {"value": "C", "source": DEMO},
            "rainfast_h": {"value": 6.0, "source": DEMO},
            "temp_range_f": {"value": [40, 85], "source": DEMO},
            "methods": {"value": ["ground_boom"], "source": DEMO},
            "buffers": {"value": [{"kind": "waterway", "ft": 100}], "source": DEMO},
        },
    },
    "unknown": {
        "name": "Operator product - label constraints not entered", "is_demo": False,
        "constraints": {
            "max_wind_mph": {"value": None, "source": "Not entered"},
            "min_droplet_class": {"value": None, "source": "Not entered"},
            "rainfast_h": {"value": None, "source": "Not entered"},
            "temp_range_f": {"value": None, "source": "Not entered"},
            "methods": {"value": None, "source": "Not entered"},
            "buffers": {"value": None, "source": "Not entered"},
        },
    },
}

DEMO_INPUT = "Operator input (demo value)"
COST_SOURCE = "Demo cost inputs - replace with your own labor and machine rates"
LABOR_USD_PER_PERSON_H = 24.0
EQUIPMENT_UNITS = [
    {"id": "U1", "crew_size": 2, "machine_usd_per_h": 110, "name": "Rig 1 - 60 ft boom", "type": "ground_boom", "crew": "Crew 1 (2 people)",
     "shift": ["06:00", "18:00"], "travel_mph": 25,
     "config": {"nozzle_id": "teejet_aixr", "orifice_size": "04", "pressure_psi": 40, "nozzle_spacing_in": 20,
                "speed_mph": 8, "rate_gpa": 15, "boom_height_in": 20, "swath_ft": 60, "tank_gal": 600,
                "refill_min": 20, "setup_min": 20, "turn_s": 30, "droplet_class_entered": None,
                "pump_min_psi": 15, "pump_max_psi": 75},
     "config_source": DEMO_INPUT + "; droplet class looked up from the TeeJet guide at the configured tip and pressure"},
    {"id": "U2", "crew_size": 2, "machine_usd_per_h": 55, "name": "Rig 2 - orchard airblast", "type": "airblast", "crew": "Crew 2 (2 people)",
     "shift": ["06:00", "16:00"], "travel_mph": 20,
     "config": {"nozzle_id": "hollow_cone_airblast", "pressure_psi": 150, "speed_mph": 2.5, "rate_gpa": 100,
                "row_spacing_ft": 22, "tank_gal": 500, "refill_min": 25, "setup_min": 25, "turn_s": 45, "manifold_height_ft": 4.0,
                "fan_setting": "low", "droplet_class_entered": None},
     "config_source": DEMO_INPUT},
    {"id": "U3", "crew_size": 2, "machine_usd_per_h": 65, "name": "Drone team (T50 reference config)", "type": "drone", "crew": "Crew 3 (pilot + loader)",
     "shift": ["07:00", "17:00"], "travel_mph": 25,
     "config": {"nozzle_id": "dji_t50_atomizer", "droplet_um": 250, "flow_l_min": 16, "swath_m": 9, "speed_m_s": 6,
                "height_m": 3, "rate_l_ha": 20, "tank_l": 40, "battery_swap_min": 3, "refill_min": 3,
                "setup_min": 15, "turn_s": 8},
     "config_source": DEMO_INPUT + "; not manufacturer-verified - check ag.dji.com/t50"},
]


def unit(uid):
    return next((u for u in EQUIPMENT_UNITS if u["id"] == uid), None)


def catalog_payload():
    return {"equipment_types": EQUIPMENT_TYPES, "nozzles": NOZZLES, "products": PRODUCTS,
            "units": EQUIPMENT_UNITS, "asabe": {"classes": ASABE_CLASSES, "names": ASABE_NAMES, "note": ASABE_NOTE}}
