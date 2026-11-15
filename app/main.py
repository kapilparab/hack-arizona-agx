from fastapi import FastAPI, Query, Response, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List, Optional, Literal
from app.schemas import (
    Assessment, TowerReading, ChemicalProduct, TeeJetNozzleType,
    HeightProfile, MultiHeightInversionAnalysis, SprayMethodEnum,
    SprayMethodInfo, SPRAY_METHOD_CONFIGS, SprayHeightRiskAnalysis,
    InterpolatedHeightPoint, HeightInterpolationResponse, POPULAR_PRODUCTS
)
from app.rules import (
    assess_drift_risk, analyze_multi_height_profile,
    AtmosphericProfileInterpolator
)
from app.sources.openmeteo import fetch_openmeteo_live, LOCATIONS
from app.sources.simulator import SCENARIOS, get_scenario
from app.forecast.model import SprayRiskForecaster
from app.store import record_assessment, get_recent_logs, export_csv

app = FastAPI(
    title="CanopyGuard Pro — Multi-Height Weather Intelligence API",
    description="Precision microclimate, continuous vertical interpolation, thermal inversion drift detection, and spatial plume modeling for South Arizona agriculture.",
    version="1.3.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

forecaster = SprayRiskForecaster()

# Pre-defined 20, 40, and 80-acre parcels at UofA Yuma Ag Center (Valley Basin)
PARCELS = [
    {
        "id": "yac-20a",
        "name": "Block 14A — Leafy Greens (Radiant Insecticide Treatment)",
        "acres": 20,
        "crop": "Romaine Lettuce",
        "is_sensitive": False,
        "center_lat": 32.7145,
        "center_lon": -114.7010,
        "boundary_geojson": {
            "type": "Polygon",
            "coordinates": [[
                [-114.7025, 32.7135],
                [-114.6995, 32.7135],
                [-114.6995, 32.7155],
                [-114.7025, 32.7155],
                [-114.7025, 32.7135]
            ]]
        }
    },
    {
        "id": "yac-40a",
        "name": "Block 15 — Certified Organic Spinach (Sensitive Downwind Receptor)",
        "acres": 40,
        "crop": "Organic Spinach",
        "is_sensitive": True,
        "center_lat": 32.7120,
        "center_lon": -114.6970,
        "boundary_geojson": {
            "type": "Polygon",
            "coordinates": [[
                [-114.6990, 32.7100],
                [-114.6950, 32.7100],
                [-114.6950, 32.7140],
                [-114.6990, 32.7140],
                [-114.6990, 32.7100]
            ]]
        }
    },
    {
        "id": "yac-80a",
        "name": "Block 18 — Desert Melons & Cucurbits (Prefar Herbicide Treatment)",
        "acres": 80,
        "crop": "Cantaloupe / Watermelon",
        "is_sensitive": False,
        "center_lat": 32.7090,
        "center_lon": -114.7030,
        "boundary_geojson": {
            "type": "Polygon",
            "coordinates": [[
                [-114.7060, 32.7060],
                [-114.7000, 32.7060],
                [-114.7000, 32.7120],
                [-114.7060, 32.7120],
                [-114.7060, 32.7060]
            ]]
        }
    }
]


@app.get("/")
def get_root():
    return {
        "service": "CanopyGuard Pro API",
        "version": "1.3.0",
        "description": "Multi-height microclimate, predictive height interpolation, and spray drift risk intelligence for South Arizona agriculture",
        "endpoints": [
            "/assess",
            "/assess/profile",
            "/interpolate",
            "/spray-methods",
            "/forecast",
            "/map/parcels",
            "/scenarios",
            "/chemicals",
            "/logs",
            "/logs/export",
            "/health"
        ]
    }


@app.get("/health")
def get_health():
    return {"status": "healthy", "service": "CanopyGuard Pro", "version": "1.3.0"}


def _resolve_reading(
    source: str,
    location_id: str = "yuma_valley",
    scenario_id: str = "yuma_radiation_inversion",
    t_ground_0m: float = 62.0,
    t_low: float = 64.0,
    t_high: float = 62.0,
    t_120m: float = 61.5,
    t_180m: float = 60.5,
    w_low: float = 4.5,
    w_high: float = 6.0,
    w_120m: float = 7.0,
    w_180m: float = 7.5,
    d_low: float = 320.0,
    d_high: float = 325.0
) -> TowerReading:
    if source == "live":
        loc = LOCATIONS.get(location_id, LOCATIONS["yuma_valley"])
        return fetch_openmeteo_live(loc["lat"], loc["lon"], loc["name"])
    elif source == "scenario":
        return get_scenario(scenario_id)
    else:
        return TowerReading(
            t_ground_0m_f=t_ground_0m,
            t_low_f=t_low,
            t_high_f=t_high,
            t_120m_f=t_120m,
            t_180m_f=t_180m,
            wind_low_mph=w_low,
            wind_high_mph=w_high,
            wind_120m_mph=w_120m,
            wind_180m_mph=w_180m,
            dir_low_deg=d_low,
            dir_high_deg=d_high,
            dir_120m_deg=d_high,
            dir_180m_deg=d_high,
            location_name="Manual Multi-Height Scrubber Reading",
            lat=32.7130,
            lon=-114.7000
        )


@app.get("/assess", response_model=Assessment)
def get_assessment(
    source: Literal["live", "scenario", "custom"] = Query("live"),
    location_id: str = Query("yuma_valley"),
    scenario_id: str = Query("yuma_radiation_inversion"),
    product_id: str = Query("radiant"),
    nozzle: TeeJetNozzleType = Query(TeeJetNozzleType.MEDIUM),
    boom_height_in: int = 24,
    spray_method: SprayMethodEnum = Query(SprayMethodEnum.TRACTOR),
    spray_height_m: Optional[float] = Query(None, description="Optional custom spray release height in meters"),
    t_ground_0m: float = 62.0,
    t_low: float = 64.0,
    t_high: float = 62.0,
    t_120m: float = 61.5,
    t_180m: float = 60.5,
    w_low: float = 4.5,
    w_high: float = 6.0,
    w_120m: float = 7.0,
    w_180m: float = 7.5,
    d_low: float = 320.0,
    d_high: float = 325.0
) -> Assessment:
    prod = POPULAR_PRODUCTS.get(product_id, POPULAR_PRODUCTS["radiant"])
    reading = _resolve_reading(
        source, location_id, scenario_id,
        t_ground_0m, t_low, t_high, t_120m, t_180m,
        w_low, w_high, w_120m, w_180m, d_low, d_high
    )
    assessment = assess_drift_risk(
        reading, prod, nozzle, boom_height_in,
        spray_method=spray_method, spray_height_m=spray_height_m
    )
    record_assessment(assessment)
    return assessment


@app.get("/assess/profile")
def get_profile(
    source: Literal["live", "scenario", "custom"] = Query("live"),
    location_id: str = Query("yuma_valley"),
    scenario_id: str = Query("yuma_radiation_inversion"),
    t_ground_0m: float = 62.0,
    t_low: float = 64.0,
    t_high: float = 62.0,
    t_120m: float = 61.5,
    t_180m: float = 60.5,
    w_low: float = 5.0,
    w_high: float = 6.0
):
    reading = _resolve_reading(
        source, location_id, scenario_id,
        t_ground_0m=t_ground_0m, t_low=t_low, t_high=t_high,
        t_120m=t_120m, t_180m=t_180m, w_low=w_low, w_high=w_high
    )
    profile, analysis = analyze_multi_height_profile(reading)
    return {
        "profile": profile,
        "analysis": analysis
    }


@app.get("/spray-methods")
def list_spray_methods():
    """Returns available spray methods and default release heights for frontend selection."""
    return [cfg.model_dump() for cfg in SPRAY_METHOD_CONFIGS.values()]


@app.get("/interpolate", response_model=HeightInterpolationResponse)
def get_interpolated_profile(
    heights: str = Query("0.6,1.6,2.0,3.6,5.0,10.0,20.0,50.0,80.0,120.0,180.0", description="Comma-separated heights in meters"),
    spray_method: SprayMethodEnum = Query(SprayMethodEnum.TRACTOR),
    spray_height_m: Optional[float] = Query(None, description="Optional custom spray height in meters"),
    source: Literal["live", "scenario", "custom"] = Query("scenario"),
    location_id: str = Query("yuma_valley"),
    scenario_id: str = Query("yuma_radiation_inversion"),
    t_ground_0m: float = 62.0,
    t_low: float = 64.0,
    t_high: float = 62.0,
    t_120m: float = 61.5,
    t_180m: float = 60.5,
    w_low: float = 4.5,
    w_high: float = 6.0
) -> HeightInterpolationResponse:
    """
    Interpolates continuous temperature and wind vector at arbitrary user-provided heights.
    Evaluates temperature and wind at 1m and 3m above the spray release plane.
    """
    reading = _resolve_reading(
        source, location_id, scenario_id,
        t_ground_0m=t_ground_0m, t_low=t_low, t_high=t_high,
        t_120m=t_120m, t_180m=t_180m, w_low=w_low, w_high=w_high
    )
    h_list = []
    for part in heights.split(","):
        part = part.strip()
        if part:
            try:
                h_list.append(float(part))
            except ValueError:
                pass

    if not h_list:
        h_list = [0.6, 1.6, 2.0, 3.6, 5.0, 10.0, 80.0]

    cfg = SPRAY_METHOD_CONFIGS.get(spray_method.value, SPRAY_METHOD_CONFIGS["tractor"])
    h_spray = spray_height_m if (spray_height_m is not None and spray_height_m > 0) else cfg.default_spray_height_m

    interpolator = AtmosphericProfileInterpolator(reading)
    points = interpolator.interpolate_heights(sorted(list(set(h_list))), spray_height_m=h_spray)
    spray_analysis = interpolator.analyze_spray_height(spray_method, spray_height_m)

    return HeightInterpolationResponse(
        timestamp=reading.timestamp,
        location_name=reading.location_name,
        requested_heights=sorted(h_list),
        points=points,
        spray_analysis=spray_analysis
    )


@app.post("/interpolate", response_model=HeightInterpolationResponse)
def post_interpolated_profile(
    body: Dict[str, Any] = Body(...)
) -> HeightInterpolationResponse:
    """
    POST endpoint to interpolate temperatures and winds at user-provided list of heights.
    Payload: {"heights": [0.6, 1.6, 2.5, 5.0], "spray_method": "drone", "spray_height_m": 2.5, "source": "scenario"}
    """
    heights_raw = body.get("heights", [0.6, 1.6, 2.0, 3.6, 5.0, 10.0, 80.0])
    h_list = [float(h) for h in heights_raw if isinstance(h, (int, float))]
    if not h_list:
        h_list = [0.6, 1.6, 2.0, 3.6, 5.0, 10.0, 80.0]

    spray_method_str = body.get("spray_method", "tractor")
    try:
        spray_method = SprayMethodEnum(spray_method_str)
    except ValueError:
        spray_method = SprayMethodEnum.TRACTOR

    spray_height_m = body.get("spray_height_m")
    source = body.get("source", "scenario")
    location_id = body.get("location_id", "yuma_valley")
    scenario_id = body.get("scenario_id", "yuma_radiation_inversion")

    reading = _resolve_reading(source, location_id, scenario_id)
    cfg = SPRAY_METHOD_CONFIGS.get(spray_method.value, SPRAY_METHOD_CONFIGS["tractor"])
    h_spray = float(spray_height_m) if (spray_height_m is not None and float(spray_height_m) > 0) else cfg.default_spray_height_m

    interpolator = AtmosphericProfileInterpolator(reading)
    points = interpolator.interpolate_heights(sorted(list(set(h_list))), spray_height_m=h_spray)
    spray_analysis = interpolator.analyze_spray_height(spray_method, spray_height_m)

    return HeightInterpolationResponse(
        timestamp=reading.timestamp,
        location_name=reading.location_name,
        requested_heights=sorted(h_list),
        points=points,
        spray_analysis=spray_analysis
    )


@app.get("/map/parcels")
def list_parcels():
    return PARCELS


@app.get("/forecast")
def get_forecast(
    t_low: float = 64.0,
    delta_t: float = 1.5,
    wind: float = 5.0,
    start_hour: int = 6,
    spray_method: SprayMethodEnum = Query(SprayMethodEnum.TRACTOR),
    spray_height_m: Optional[float] = Query(None, description="Optional custom spray height in meters")
):
    cfg = SPRAY_METHOD_CONFIGS.get(spray_method.value, SPRAY_METHOD_CONFIGS["tractor"])
    h_spray = spray_height_m if (spray_height_m is not None and spray_height_m > 0) else cfg.default_spray_height_m
    hours, windows = forecaster.forecast_12h(
        t_low, delta_t, wind, start_hour,
        spray_method=spray_method, spray_height_m=spray_height_m
    )
    return {
        "brier_improvement_vs_persistence": f"{forecaster.brier_improvement}%",
        "spray_method": spray_method.value,
        "spray_height_m": h_spray,
        "height_plus_1m": round(h_spray + 1.0, 2),
        "height_plus_3m": round(h_spray + 3.0, 2),
        "hourly_forecast": hours,
        "recommended_windows": windows
    }


@app.get("/scenarios")
def list_scenarios():
    return {k: {"name": v["name"], "description": v["description"]} for k, v in SCENARIOS.items()}


@app.get("/chemicals")
def list_chemicals():
    return {k: v.model_dump() for k, v in POPULAR_PRODUCTS.items()}


@app.get("/logs")
def list_logs(limit: int = 50):
    return get_recent_logs(limit)


@app.get("/logs/export")
def download_logs():
    csv_data = export_csv()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=canopyguard_epa_audit.csv"}
    )
