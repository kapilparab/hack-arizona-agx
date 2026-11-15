import time
import requests
from datetime import datetime, timezone
from typing import Dict, Any, Tuple
from app.schemas import TowerReading

_CACHE: Dict[str, Tuple[float, TowerReading]] = {}
CACHE_TTL_SECONDS = 600

# Arizona Agricultural Center Locations
LOCATIONS: Dict[str, Dict[str, Any]] = {
    "yuma_valley": {
        "name": "UofA Yuma Ag Center (Valley Basin)",
        "lat": 32.7130,
        "lon": -114.7000,
        "elevation": 140.0
    },
    "yuma_mesa": {
        "name": "Yuma Mesa Citrus/Vegetable Block",
        "lat": 32.6100,
        "lon": -114.6200,
        "elevation": 210.0
    },
    "marana_pima": {
        "name": "UofA Marana Ag Center (Pima County)",
        "lat": 32.4380,
        "lon": -111.2280,
        "elevation": 1980.0
    }
}

OFFLINE_FALLBACK: Dict[str, Any] = {
    "t_ground_0m_f": 62.0,
    "t_low_f": 64.5,
    "t_high_f": 62.0,
    "t_120m_f": 60.5,
    "t_180m_f": 59.0,
    "wind_low_mph": 4.5,
    "wind_high_mph": 6.0,
    "wind_120m_mph": 6.8,
    "wind_180m_mph": 7.5,
    "dir_low_deg": 330.0,
    "dir_high_deg": 335.0,
    "dir_120m_deg": 338.0,
    "dir_180m_deg": 340.0,
    "rh_low": 24.0,
    "solar_rad_w_m2": 550.0
}


def fetch_openmeteo_live(
    lat: float = 32.7130,
    lon: float = -114.7000,
    loc_name: str = "UofA Yuma Ag Center"
) -> TowerReading:
    """
    Fetches live multi-height weather readings from Open-Meteo API.
    Retrieves ground level (0m soil skin) and all aloft levels (2m, 80m, 120m, 180m)
    with wind vectors across all heights.
    """
    cache_key = f"{round(lat, 4)}_{round(lon, 4)}"
    now = time.time()
    
    if cache_key in _CACHE:
        cached_time, cached_reading = _CACHE[cache_key]
        if now - cached_time < CACHE_TTL_SECONDS:
            return cached_reading

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,temperature_80m,temperature_120m,temperature_180m,"
        "wind_speed_10m,wind_speed_80m,wind_speed_120m,wind_speed_180m,"
        "wind_direction_10m,wind_direction_80m,wind_direction_120m,wind_direction_180m,"
        "relative_humidity_2m,shortwave_radiation,soil_temperature_0cm"
        "&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=auto"
    )

    try:
        resp = requests.get(url, timeout=5.0)
        resp.raise_for_status()
        data = resp.json().get("current", {})

        reading = TowerReading(
            timestamp=datetime.now(timezone.utc),
            location_name=loc_name,
            lat=lat,
            lon=lon,
            t_ground_0m_f=float(data.get("soil_temperature_0cm") if data.get("soil_temperature_0cm") is not None else 62.0),
            t_low_f=float(data.get("temperature_2m") if data.get("temperature_2m") is not None else 64.0),
            t_high_f=float(data.get("temperature_80m") if data.get("temperature_80m") is not None else 62.0),
            t_120m_f=float(data.get("temperature_120m") if data.get("temperature_120m") is not None else 61.5),
            t_180m_f=float(data.get("temperature_180m") if data.get("temperature_180m") is not None else 60.5),
            wind_low_mph=float(data.get("wind_speed_10m") if data.get("wind_speed_10m") is not None else 5.0),
            wind_high_mph=float(data.get("wind_speed_80m") if data.get("wind_speed_80m") is not None else 6.5),
            wind_120m_mph=float(data.get("wind_speed_120m") if data.get("wind_speed_120m") is not None else 7.0),
            wind_180m_mph=float(data.get("wind_speed_180m") if data.get("wind_speed_180m") is not None else 7.5),
            dir_low_deg=float(data.get("wind_direction_10m") if data.get("wind_direction_10m") is not None else 320.0),
            dir_high_deg=float(data.get("wind_direction_80m") if data.get("wind_direction_80m") is not None else 325.0),
            dir_120m_deg=float(data.get("wind_direction_120m") if data.get("wind_direction_120m") is not None else 330.0),
            dir_180m_deg=float(data.get("wind_direction_180m") if data.get("wind_direction_180m") is not None else 335.0),
            rh_low=float(data.get("relative_humidity_2m") if data.get("relative_humidity_2m") is not None else 25.0),
            solar_rad_w_m2=float(data.get("shortwave_radiation") if data.get("shortwave_radiation") is not None else 500.0)
        )
        _CACHE[cache_key] = (now, reading)
        return reading
    except Exception:
        return TowerReading(
            timestamp=datetime.now(timezone.utc),
            location_name=f"{loc_name} (Offline Cache Mode)",
            lat=lat,
            lon=lon,
            **OFFLINE_FALLBACK
        )
