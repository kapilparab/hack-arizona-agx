from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from enum import Enum


class StatusEnum(str, Enum):
    GO = "GO"
    CAUTION = "CAUTION"
    STOP = "STOP"


class ChemicalCategory(str, Enum):
    INSECTICIDE = "Insecticide"
    HERBICIDE_SYSTEMIC = "Herbicide (Systemic - High Crop Kill Risk)"
    HERBICIDE_CONTACT = "Herbicide (Contact - Foliar Speckling Risk)"
    FUNGICIDE = "Fungicide"


class ApplicationTiming(str, Enum):
    PRE_EMERGENT = "Pre-Emergent (Soil Applied - e.g., Prefar)"
    POST_EMERGENT = "Post-Emergent (Foliar Applied)"


class TeeJetNozzleType(str, Enum):
    FINE = "TeeJet TX / Hollow Cone (Fine/Mist, <200 µm)"
    MEDIUM = "TeeJet XR / Flat Fan (Medium, 200–300 µm)"
    COARSE = "TeeJet AIXR / Air Induction (Coarse, 300–400 µm)"
    VERY_COARSE = "TeeJet Turbo TT (Very Coarse, 400–500 µm)"
    ULTRA_COARSE = "TeeJet TTI / Air Induction (Ultra Coarse, >500 µm)"


class InversionTypeEnum(str, Enum):
    NONE = "Normal Atmospheric Lapse (Safe Dispersion)"
    SURFACE_RADIATION = "Surface Radiation Inversion (0m Soil - 2m Canopy)"
    LOW_LEVEL_LID = "Low-Level Inversion Lid (2m Canopy - 80m Aloft)"
    ELEVATED_CAP = "Elevated Capping Inversion (80m - 180m Aloft)"
    DEEP_COLUMN = "Deep Multi-Tier Inversion (Continuous Column 0m - 180m)"


class InversionSeverityEnum(str, Enum):
    NONE = "None"
    MILD = "Mild (+0.1°F to +1.0°F)"
    MODERATE = "Moderate (+1.0°F to +2.5°F)"
    STRONG = "Strong (+2.5°F to +5.0°F)"
    EXTREME = "Extreme (> +5.0°F)"


class ChemicalProduct(BaseModel):
    id: str
    name: str
    active_ingredient: str
    category: ChemicalCategory
    timing: ApplicationTiming
    default_nozzle: TeeJetNozzleType
    max_label_wind_mph: float = 10.0
    max_label_temp_f: float = 90.0
    buffer_required_ft: float = 100.0


POPULAR_PRODUCTS: Dict[str, ChemicalProduct] = {
    "radiant": ChemicalProduct(
        id="radiant",
        name="Radiant® SC",
        active_ingredient="Spinetoram",
        category=ChemicalCategory.INSECTICIDE,
        timing=ApplicationTiming.POST_EMERGENT,
        default_nozzle=TeeJetNozzleType.MEDIUM,
        max_label_wind_mph=10.0,
        max_label_temp_f=90.0,
        buffer_required_ft=50.0
    ),
    "prefar": ChemicalProduct(
        id="prefar",
        name="Prefar® 4-E",
        active_ingredient="Bensulide",
        category=ChemicalCategory.HERBICIDE_SYSTEMIC,
        timing=ApplicationTiming.PRE_EMERGENT,
        default_nozzle=TeeJetNozzleType.ULTRA_COARSE,
        max_label_wind_mph=10.0,
        max_label_temp_f=85.0,
        buffer_required_ft=150.0
    )
}


class FieldParcel(BaseModel):
    id: str
    name: str
    acres: int = Field(..., description="20, 40, or 80 acres")
    crop_type: str
    is_sensitive: bool = False
    center_lat: float
    center_lon: float
    boundary_geojson: Dict[str, Any]


class HeightLevelReading(BaseModel):
    height_m: float = Field(..., description="Height above ground level in meters (0m, 2m, 10m, 80m, 120m, 180m)")
    height_name: str = Field(..., description="Human-readable level description")
    temp_f: float = Field(..., description="Temperature at this level in °F")
    wind_speed_mph: Optional[float] = Field(default=None, description="Wind speed at this level in mph")
    wind_dir_deg: Optional[float] = Field(default=None, description="Wind direction at this level in degrees")
    delta_t_from_ground_f: float = Field(default=0.0, description="Temperature delta relative to ground 0m (T_h - T_0m)")
    delta_t_from_2m_f: float = Field(default=0.0, description="Temperature delta relative to 2m canopy (T_h - T_2m)")
    lapse_rate_f_per_100m: float = Field(default=0.0, description="Vertical lapse rate in °F per 100 meters")
    is_inverted: bool = Field(default=False, description="True if warmer than the level below (inversion)")


class HeightProfile(BaseModel):
    ground_0m: HeightLevelReading
    canopy_2m: HeightLevelReading
    aloft_80m: HeightLevelReading
    aloft_120m: HeightLevelReading
    aloft_180m: HeightLevelReading
    levels: List[HeightLevelReading] = Field(default_factory=list)


class MultiHeightInversionAnalysis(BaseModel):
    inversion_detected: bool = Field(..., description="True if any inversion layer exists from 0m to 180m")
    primary_inversion_type: InversionTypeEnum
    inversion_types: List[InversionTypeEnum] = Field(default_factory=list)
    severity: InversionSeverityEnum
    max_delta_t_f: float = Field(..., description="Peak positive temperature inversion delta across any level")
    max_inversion_height_m: float = Field(..., description="Highest altitude where inversion persists")
    ground_to_canopy_delta_f: float = Field(..., description="T_2m - T_0m (Surface radiation cooling delta)")
    canopy_to_80m_delta_f: float = Field(..., description="T_80m - T_2m (Primary EPA inversion delta)")
    canopy_to_120m_delta_f: float = Field(..., description="T_120m - T_2m (Mid-aloft inversion delta)")
    canopy_to_180m_delta_f: float = Field(..., description="T_180m - T_2m (High-aloft synoptic delta)")
    max_wind_shear_mph: float = Field(..., description="Maximum wind speed difference between surface and aloft tiers")
    max_dir_shear_deg: float = Field(..., description="Maximum directional crosswind divergence aloft")
    trapping_risk_score: float = Field(..., description="Composite chemical trapping index from 0.0 (safe) to 100.0 (extreme)")
    drift_dispersion_multiplier: float = Field(..., description="AgDRIFT downwind distance multiplier based on vertical stability")
    vertical_profile_summary: str = Field(..., description="Detailed explanation of vertical atmospheric stratification")


class TowerReading(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    location_name: str = "UofA Yuma Ag Center (Block 12)"
    lat: float = 32.7130
    lon: float = -114.7000
    elevation_ft: float = 140.0
    # Ground level (0m soil skin)
    t_ground_0m_f: float = Field(default=62.0, description="True ground / soil surface skin temperature in °F")
    # Canopy level (2m / 5-6ft)
    t_low_f: float = Field(..., description="Temperature at 2m canopy / weather station in °F")
    wind_low_mph: float = Field(..., description="Wind speed at 2m/10m surface anemometer in mph")
    dir_low_deg: float = Field(default=0.0, description="Wind direction surface in degrees")
    rh_low: float = Field(default=25.0, description="Relative humidity % at 2m")
    # Low aloft level (80m / ~262ft)
    t_high_f: float = Field(..., description="Temperature at 80m aloft in °F")
    wind_high_mph: float = Field(..., description="Wind speed at 80m aloft in mph")
    dir_high_deg: float = Field(default=0.0, description="Wind direction at 80m aloft in degrees")
    # Mid aloft level (120m / ~394ft)
    t_120m_f: float = Field(default=62.0, description="Temperature at 120m aloft in °F")
    wind_120m_mph: float = Field(default=6.0, description="Wind speed at 120m aloft in mph")
    dir_120m_deg: float = Field(default=0.0, description="Wind direction at 120m aloft in degrees")
    # High aloft level (180m / ~591ft)
    t_180m_f: float = Field(default=61.0, description="Temperature at 180m aloft in °F")
    wind_180m_mph: float = Field(default=6.5, description="Wind speed at 180m aloft in mph")
    dir_180m_deg: float = Field(default=0.0, description="Wind direction at 180m aloft in degrees")
    solar_rad_w_m2: float = Field(default=0.0, description="Shortwave solar radiation W/m²")


class RuleEvaluation(BaseModel):
    rule_name: str
    status: StatusEnum
    measured: str
    threshold: str
    reason: str


class SpatialPlumeGeometry(BaseModel):
    origin_lat: float
    origin_lon: float
    wind_bearing_deg: float
    plume_distance_ft: float
    plume_cone_angle_deg: float
    risk_level: StatusEnum
    polygon_coordinates: List[List[float]]
    buffer_encroachment: bool
    encroached_parcels: List[str]


class Assessment(BaseModel):
    timestamp: datetime
    overall_status: StatusEnum
    headline: str
    plain_explanation: str
    ground_only_status: StatusEnum
    blind_spot_caught: bool
    delta_t_f: float
    wind_shear_mph: float
    dir_shear_deg: float
    evaluations: List[RuleEvaluation]
    reading: TowerReading
    product: ChemicalProduct
    nozzle: TeeJetNozzleType
    boom_height_inches: int
    multi_height_analysis: Optional[MultiHeightInversionAnalysis] = None
    height_profile: Optional[HeightProfile] = None
    spatial_plume: Optional[SpatialPlumeGeometry] = None
