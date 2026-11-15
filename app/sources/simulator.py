from datetime import datetime, timezone
from typing import Dict, Any
from app.schemas import TowerReading

SCENARIOS: Dict[str, Dict[str, Any]] = {
    "yuma_radiation_inversion": {
        "name": "Yuma Valley Dawn Inversion Trap (Deep Column)",
        "description": "Cold air drainage along the Colorado River basin creates steep radiation cooling at ground (54.0°F), rising to +66.8°F aloft (+8.6°F total inversion). Ground wind is calm (3.8 mph), but fine insecticide mist will stay suspended for miles.",
        "reading": TowerReading(
            timestamp=datetime.now(timezone.utc),
            location_name="UofA Yuma Ag Center (Valley Floor)",
            lat=32.7130,
            lon=-114.7000,
            elevation_ft=140.0,
            t_ground_0m_f=54.0,   # Ground is coldest
            t_low_f=58.2,         # 2m canopy
            t_high_f=64.0,        # 80m aloft (+5.8°F)
            t_120m_f=65.5,       # 120m aloft (+7.3°F)
            t_180m_f=66.8,       # 180m aloft (+8.6°F)
            wind_low_mph=3.8,     # Looks calm and safe (3.8 mph)
            wind_high_mph=4.5,
            wind_120m_mph=5.2,
            wind_180m_mph=6.0,
            dir_low_deg=310.0,
            dir_high_deg=315.0,
            dir_120m_deg=320.0,
            dir_180m_deg=325.0,
            rh_low=35.0,
            solar_rad_w_m2=0.0
        )
    },
    "marana_wind_shear": {
        "name": "Marana / Pima Katabatic Multi-Tier Wind Shear",
        "description": "Tortolita Mountain drainage produces 21.0 mph wind aloft divergent by 90° from the 4.8 mph ground breeze, ripping pesticide droplets out of the canopy into adjacent organic blocks.",
        "reading": TowerReading(
            timestamp=datetime.now(timezone.utc),
            location_name="UofA Marana Ag Center (Avra Valley)",
            lat=32.4380,
            lon=-111.2280,
            elevation_ft=1980.0,
            t_ground_0m_f=67.0,
            t_low_f=66.0,
            t_high_f=65.0,
            t_120m_f=64.2,
            t_180m_f=63.5,
            wind_low_mph=4.8,     # Safe ground wind
            wind_high_mph=14.5,   # Aloft shear
            wind_120m_mph=17.8,   # Mid-aloft shear
            wind_180m_mph=21.0,   # High aloft jet
            dir_low_deg=270.0,    # West ground breeze
            dir_high_deg=210.0,   # SSW aloft
            dir_120m_deg=195.0,   # SSW aloft
            dir_180m_deg=180.0,   # South aloft (90° shear!)
            rh_low=20.0,
            solar_rad_w_m2=600.0
        )
    },
    "yuma_elevated_cap": {
        "name": "Yuma Mesa Elevated Inversion Lid (Ground Station Blind Spot)",
        "description": "Surface station reports normal lapse (-1.5°F at 80m), misleading standard tools. However, a warm subsidence cap at 120m-180m (+6.0°F) traps rising chemical plumes and transports them downwind.",
        "reading": TowerReading(
            timestamp=datetime.now(timezone.utc),
            location_name="Yuma Mesa Citrus/Vegetable Block",
            lat=32.6100,
            lon=-114.6200,
            elevation_ft=210.0,
            t_ground_0m_f=71.0,
            t_low_f=70.0,         # 2m canopy
            t_high_f=68.5,        # 80m looks normal (-1.5°F lapse)
            t_120m_f=73.0,       # 120m warm cap (+4.5°F over 80m!)
            t_180m_f=74.5,       # 180m synoptic lid
            wind_low_mph=5.0,
            wind_high_mph=6.2,
            wind_120m_mph=8.5,
            wind_180m_mph=11.0,
            dir_low_deg=300.0,
            dir_high_deg=310.0,
            dir_120m_deg=330.0,
            dir_180m_deg=345.0,
            rh_low=22.0,
            solar_rad_w_m2=450.0
        )
    },
    "yuma_ideal_window": {
        "name": "Yuma Mid-Morning Ideal Spray Window",
        "description": "Desert sun has completely dissipated all inversion layers. Steady 5.5 mph breeze with consistent adiabatic lapse rate through all heights.",
        "reading": TowerReading(
            timestamp=datetime.now(timezone.utc),
            location_name="Yuma Mesa Citrus/Melon Block",
            lat=32.6100,
            lon=-114.6200,
            elevation_ft=210.0,
            t_ground_0m_f=76.0,
            t_low_f=72.0,
            t_high_f=69.5,        # Normal lapse rate
            t_120m_f=68.0,        # Consistent cooling aloft
            t_180m_f=66.5,        # Consistent cooling aloft
            wind_low_mph=5.5,     # Perfect 3-8 mph window
            wind_high_mph=6.8,
            wind_120m_mph=7.2,
            wind_180m_mph=7.5,
            dir_low_deg=340.0,
            dir_high_deg=345.0,
            dir_120m_deg=345.0,
            dir_180m_deg=350.0,
            rh_low=22.0,
            solar_rad_w_m2=750.0
        )
    }
}


def get_scenario(key: str) -> TowerReading:
    """Returns the TowerReading corresponding to a hero scenario key."""
    if key in SCENARIOS:
        return SCENARIOS[key]["reading"].model_copy(deep=True)
    return SCENARIOS["yuma_radiation_inversion"]["reading"].model_copy(deep=True)
