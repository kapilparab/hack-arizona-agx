import math
import numpy as np
from scipy.interpolate import PchipInterpolator
from typing import Tuple, List, Optional
from app.schemas import (
    TowerReading, ChemicalProduct, Assessment, StatusEnum,
    RuleEvaluation, TeeJetNozzleType, ChemicalCategory, SpatialPlumeGeometry,
    HeightLevelReading, HeightProfile, MultiHeightInversionAnalysis,
    InversionTypeEnum, InversionSeverityEnum, SprayMethodEnum,
    SprayMethodInfo, SPRAY_METHOD_CONFIGS, SprayHeightRiskAnalysis,
    InterpolatedHeightPoint, POPULAR_PRODUCTS
)


def angle_diff(deg1: float, deg2: float) -> float:
    """Computes the shortest angular difference (0 to 180 degrees) between two compass bearings."""
    diff = abs(deg1 - deg2) % 360
    return 360 - diff if diff > 180 else diff


def analyze_multi_height_profile(r: TowerReading) -> Tuple[HeightProfile, MultiHeightInversionAnalysis]:
    """
    Evaluates vertical microclimate stratification from ground level (0m soil skin)
    up through 2m canopy, 80m low aloft, 120m mid aloft, and 180m high aloft boundary layers.
    Identifies 4 distinct inversion regimes:
      1. Surface Radiation Inversion (0m -> 2m)
      2. Low-Level Inversion Lid (2m -> 80m, primary EPA trigger)
      3. Elevated Capping Inversion (80m -> 120m/180m aloft)
      4. Deep Full-Column Inversion (continuous 0m -> 180m)
    """
    t_0m = r.t_ground_0m_f
    t_2m = r.t_low_f
    t_80m = r.t_high_f
    t_120m = r.t_120m_f
    t_180m = r.t_180m_f

    w_10m = r.wind_low_mph
    d_10m = r.dir_low_deg
    w_80m = r.wind_high_mph
    d_80m = r.dir_high_deg
    w_120m = r.wind_120m_mph
    d_120m = r.dir_120m_deg
    w_180m = r.wind_180m_mph
    d_180m = r.dir_180m_deg

    # Height levels
    lvl_0m = HeightLevelReading(
        height_m=0.0,
        height_name="Ground Level (0m Soil Skin)",
        temp_f=round(t_0m, 2),
        delta_t_from_ground_f=0.0,
        delta_t_from_2m_f=round(t_0m - t_2m, 2),
        lapse_rate_f_per_100m=0.0,
        is_inverted=False
    )
    # 0m to 2m lapse rate: (T_2m - T_0m) / (2m / 100m)
    lapse_0_2 = round((t_2m - t_0m) / 0.02, 2)
    lvl_2m = HeightLevelReading(
        height_m=2.0,
        height_name="Canopy Height (2m / 5-6ft)",
        temp_f=round(t_2m, 2),
        wind_speed_mph=round(w_10m, 1),
        wind_dir_deg=round(d_10m, 1),
        delta_t_from_ground_f=round(t_2m - t_0m, 2),
        delta_t_from_2m_f=0.0,
        lapse_rate_f_per_100m=lapse_0_2,
        is_inverted=(t_2m > t_0m)
    )
    # 2m to 80m lapse rate: (T_80m - T_2m) / (78m / 100m)
    lapse_2_80 = round((t_80m - t_2m) / 0.78, 2)
    lvl_80m = HeightLevelReading(
        height_m=80.0,
        height_name="Low Aloft (80m / ~262ft)",
        temp_f=round(t_80m, 2),
        wind_speed_mph=round(w_80m, 1),
        wind_dir_deg=round(d_80m, 1),
        delta_t_from_ground_f=round(t_80m - t_0m, 2),
        delta_t_from_2m_f=round(t_80m - t_2m, 2),
        lapse_rate_f_per_100m=lapse_2_80,
        is_inverted=(t_80m > t_2m)
    )
    # 80m to 120m lapse rate: (T_120m - T_80m) / (40m / 100m)
    lapse_80_120 = round((t_120m - t_80m) / 0.40, 2)
    lvl_120m = HeightLevelReading(
        height_m=120.0,
        height_name="Mid Aloft (120m / ~394ft)",
        temp_f=round(t_120m, 2),
        wind_speed_mph=round(w_120m, 1),
        wind_dir_deg=round(d_120m, 1),
        delta_t_from_ground_f=round(t_120m - t_0m, 2),
        delta_t_from_2m_f=round(t_120m - t_2m, 2),
        lapse_rate_f_per_100m=lapse_80_120,
        is_inverted=(t_120m > t_80m)
    )
    # 120m to 180m lapse rate: (T_180m - T_120m) / (60m / 100m)
    lapse_120_180 = round((t_180m - t_120m) / 0.60, 2)
    lvl_180m = HeightLevelReading(
        height_m=180.0,
        height_name="High Aloft (180m / ~591ft)",
        temp_f=round(t_180m, 2),
        wind_speed_mph=round(w_180m, 1),
        wind_dir_deg=round(d_180m, 1),
        delta_t_from_ground_f=round(t_180m - t_0m, 2),
        delta_t_from_2m_f=round(t_180m - t_2m, 2),
        lapse_rate_f_per_100m=lapse_120_180,
        is_inverted=(t_180m > t_120m)
    )

    profile = HeightProfile(
        ground_0m=lvl_0m,
        canopy_2m=lvl_2m,
        aloft_80m=lvl_80m,
        aloft_120m=lvl_120m,
        aloft_180m=lvl_180m,
        levels=[lvl_0m, lvl_2m, lvl_80m, lvl_120m, lvl_180m]
    )

    # Inversion Deltas relative to 2m canopy reference
    dt_ground_canopy = round(t_2m - t_0m, 2)
    dt_2_80 = round(t_80m - t_2m, 2)
    dt_2_120 = round(t_120m - t_2m, 2)
    dt_2_180 = round(t_180m - t_2m, 2)

    # Wind Shear and Directional Shear across all aloft tiers relative to 10m surface
    shear_80 = abs(w_80m - w_10m)
    shear_120 = abs(w_120m - w_10m)
    shear_180 = abs(w_180m - w_10m)
    max_wind_shear = round(max(shear_80, shear_120, shear_180), 1)

    dir_shear_80 = angle_diff(d_80m, d_10m)
    dir_shear_120 = angle_diff(d_120m, d_10m)
    dir_shear_180 = angle_diff(d_180m, d_10m)
    max_dir_shear = round(max(dir_shear_80, dir_shear_120, dir_shear_180), 1)

    # Inversion Classifications
    inv_types: List[InversionTypeEnum] = []

    # 1. Surface radiation inversion: Ground colder than canopy air
    if dt_ground_canopy >= 1.5:
        inv_types.append(InversionTypeEnum.SURFACE_RADIATION)

    # 2. Low-level inversion lid: Canopy cooler than 80m
    if dt_2_80 > 0.0:
        inv_types.append(InversionTypeEnum.LOW_LEVEL_LID)

    # 3. Elevated capping inversion: Warm layer above 80m (120m or 180m warmer than 80m or 2m)
    if (t_120m > t_80m or t_180m > t_120m or dt_2_120 > 0.5 or dt_2_180 > 0.5) and InversionTypeEnum.LOW_LEVEL_LID not in inv_types:
        inv_types.append(InversionTypeEnum.ELEVATED_CAP)

    # 4. Deep column inversion: Inversion spans all tiers from ground/canopy to 180m
    if dt_2_80 > 0.0 and dt_2_120 > 0.0 and dt_2_180 > 0.0:
        inv_types.append(InversionTypeEnum.DEEP_COLUMN)

    inversion_detected = len(inv_types) > 0
    if InversionTypeEnum.DEEP_COLUMN in inv_types:
        primary_type = InversionTypeEnum.DEEP_COLUMN
    elif InversionTypeEnum.LOW_LEVEL_LID in inv_types:
        primary_type = InversionTypeEnum.LOW_LEVEL_LID
    elif InversionTypeEnum.ELEVATED_CAP in inv_types:
        primary_type = InversionTypeEnum.ELEVATED_CAP
    elif InversionTypeEnum.SURFACE_RADIATION in inv_types:
        primary_type = InversionTypeEnum.SURFACE_RADIATION
    else:
        primary_type = InversionTypeEnum.NONE

    # Max inversion delta
    positive_deltas = [d for d in [dt_ground_canopy, dt_2_80, dt_2_120, dt_2_180] if d > 0.0]
    max_dt = max(positive_deltas) if positive_deltas else 0.0

    # Max inversion height
    max_h = 0.0
    if dt_2_180 > 0.0 or t_180m > t_120m:
        max_h = 180.0
    elif dt_2_120 > 0.0 or t_120m > t_80m:
        max_h = 120.0
    elif dt_2_80 > 0.0:
        max_h = 80.0
    elif dt_ground_canopy >= 1.5:
        max_h = 2.0

    # Severity classification
    if max_dt > 5.0:
        severity = InversionSeverityEnum.EXTREME
    elif max_dt >= 2.5:
        severity = InversionSeverityEnum.STRONG
    elif max_dt >= 1.0:
        severity = InversionSeverityEnum.MODERATE
    elif max_dt > 0.0:
        severity = InversionSeverityEnum.MILD
    else:
        severity = InversionSeverityEnum.NONE

    # Trapping Risk Score (0 - 100)
    trapping_score = min(100.0, max(0.0, (
        (max_dt * 15.0) +
        (15.0 if InversionTypeEnum.SURFACE_RADIATION in inv_types else 0.0) +
        (25.0 if InversionTypeEnum.LOW_LEVEL_LID in inv_types else 0.0) +
        (20.0 if InversionTypeEnum.ELEVATED_CAP in inv_types else 0.0) +
        (25.0 if InversionTypeEnum.DEEP_COLUMN in inv_types else 0.0) +
        (max_wind_shear * 1.5)
    )))

    # AgDRIFT dispersion multiplier
    if severity == InversionSeverityEnum.EXTREME:
        drift_mult = 3.8
    elif severity == InversionSeverityEnum.STRONG:
        drift_mult = 2.8
    elif severity == InversionSeverityEnum.MODERATE:
        drift_mult = 2.0
    elif severity == InversionSeverityEnum.MILD:
        drift_mult = 1.4
    else:
        drift_mult = 1.0

    summary = (
        f"Multi-tier vertical analysis: 0m={t_0m:.1f}°F, 2m={t_2m:.1f}°F, 80m={t_80m:.1f}°F, "
        f"120m={t_120m:.1f}°F, 180m={t_180m:.1f}°F. "
        f"{'INVERSION ACTIVE: ' + primary_type.value if inversion_detected else 'Normal atmospheric lapse.'} "
        f"Max ΔT aloft: +{max_dt:.1f}°F. Aloft wind shear: {max_wind_shear:.1f} mph ({max_dir_shear:.0f}° divergence)."
    )

    analysis = MultiHeightInversionAnalysis(
        inversion_detected=inversion_detected,
        primary_inversion_type=primary_type,
        inversion_types=inv_types,
        severity=severity,
        max_delta_t_f=round(max_dt, 2),
        max_inversion_height_m=max_h,
        ground_to_canopy_delta_f=dt_ground_canopy,
        canopy_to_80m_delta_f=dt_2_80,
        canopy_to_120m_delta_f=dt_2_120,
        canopy_to_180m_delta_f=dt_2_180,
        max_wind_shear_mph=max_wind_shear,
        max_dir_shear_deg=max_dir_shear,
        trapping_risk_score=round(trapping_score, 1),
        drift_dispersion_multiplier=drift_mult,
        vertical_profile_summary=summary
    )

    return profile, analysis


class AtmosphericProfileInterpolator:
    """
    Continuous microclimate interpolator using Piecewise Cubic Hermite Interpolating Polynomials (PCHIP)
    for vertical temperature and wind profiles across the agricultural boundary layer.
    Guarantees monotonicity between measured sounding heights without oscillatory artifacts,
    and resolves wind direction across circular unit vectors (u, v).
    """

    def __init__(self, reading: TowerReading):
        self.reading = reading
        self._build_models()

    def _build_models(self):
        r = self.reading
        # Temperature anchors: 0m, 2m, 80m, 120m, 180m
        self.t_heights = np.array([0.0, 2.0, 80.0, 120.0, 180.0], dtype=float)
        self.t_vals = np.array([
            r.t_ground_0m_f,
            r.t_low_f,
            r.t_high_f,
            r.t_120m_f,
            r.t_180m_f
        ], dtype=float)
        self.pchip_t = PchipInterpolator(self.t_heights, self.t_vals)

        # Wind speed anchors: 0m (0 mph), 2m (canopy), 10m, 80m, 120m, 180m
        w_canopy = max(0.0, r.wind_low_mph * 0.75)
        self.w_heights = np.array([0.0, 2.0, 10.0, 80.0, 120.0, 180.0], dtype=float)
        self.w_speeds = np.array([
            0.0,
            w_canopy,
            r.wind_low_mph,
            r.wind_high_mph,
            r.wind_120m_mph,
            r.wind_180m_mph
        ], dtype=float)
        self.pchip_speed = PchipInterpolator(self.w_heights, self.w_speeds)

        # Wind direction anchors with circular vector decomposition
        self.w_dirs = np.array([
            r.dir_low_deg,
            r.dir_low_deg,
            r.dir_low_deg,
            r.dir_high_deg,
            r.dir_120m_deg,
            r.dir_180m_deg
        ], dtype=float)
        rads = np.radians(self.w_dirs)
        self.pchip_u = PchipInterpolator(self.w_heights, np.sin(rads))
        self.pchip_v = PchipInterpolator(self.w_heights, np.cos(rads))

    def temperature_at(self, h: float) -> float:
        """Interpolates temperature in °F at height h in meters."""
        h_clamped = max(0.0, float(h))
        if h_clamped <= 180.0:
            return float(self.pchip_t(h_clamped))
        t_180 = float(self.pchip_t(180.0))
        # Standard free atmospheric dry adiabatic lapse beyond 180m (~-1.8°F / 100m)
        return float(t_180 - ((h_clamped - 180.0) / 100.0) * 1.8)

    def wind_at(self, h: float) -> Tuple[float, float]:
        """Interpolates (wind_speed_mph, wind_direction_deg) at height h in meters."""
        h_clamped = max(0.0, float(h))
        if h_clamped <= 180.0:
            sp = max(0.0, float(self.pchip_speed(h_clamped)))
            u = float(self.pchip_u(h_clamped))
            v = float(self.pchip_v(h_clamped))
        else:
            sp = float(self.pchip_speed(180.0))
            u = float(self.pchip_u(180.0))
            v = float(self.pchip_v(180.0))
        direction = (float(np.degrees(np.arctan2(u, v))) + 360.0) % 360.0
        return round(sp, 1), round(direction, 1)

    def lapse_rate_at(self, h: float, delta_h: float = 0.5) -> float:
        """Computes local vertical lapse rate in °F per 100 meters at height h."""
        h1 = max(0.0, float(h) - delta_h)
        h2 = float(h) + delta_h
        t1 = self.temperature_at(h1)
        t2 = self.temperature_at(h2)
        dh_100m = (h2 - h1) / 100.0
        return round((t2 - t1) / dh_100m, 2)

    def interpolate_heights(
        self,
        heights: List[float],
        spray_height_m: Optional[float] = None
    ) -> List[InterpolatedHeightPoint]:
        points = []
        t_ground = self.temperature_at(0.0)
        t_spray = self.temperature_at(spray_height_m) if spray_height_m is not None else None

        for h in sorted(heights):
            temp = round(self.temperature_at(h), 2)
            spd, d = self.wind_at(h)
            lapse = self.lapse_rate_at(h)
            dt_ground = round(temp - t_ground, 2)
            dt_spray = round(temp - t_spray, 2) if t_spray is not None else None
            is_inv = lapse > 0.0

            points.append(InterpolatedHeightPoint(
                height_m=round(h, 2),
                temp_f=temp,
                wind_speed_mph=spd,
                wind_dir_deg=d,
                lapse_rate_f_per_100m=lapse,
                delta_t_from_ground_f=dt_ground,
                delta_t_from_spray_f=dt_spray,
                is_inverted_locally=is_inv
            ))
        return points

    def analyze_spray_height(
        self,
        spray_method: SprayMethodEnum = SprayMethodEnum.TRACTOR,
        custom_height_m: Optional[float] = None
    ) -> SprayHeightRiskAnalysis:
        if custom_height_m is not None and custom_height_m > 0:
            h_spray = float(custom_height_m)
        else:
            cfg = SPRAY_METHOD_CONFIGS.get(spray_method.value, SPRAY_METHOD_CONFIGS["tractor"])
            h_spray = cfg.default_spray_height_m

        h_plus_1m = round(h_spray + 1.0, 2)
        h_plus_3m = round(h_spray + 3.0, 2)

        t_spray = round(self.temperature_at(h_spray), 2)
        t_plus_1m = round(self.temperature_at(h_plus_1m), 2)
        t_plus_3m = round(self.temperature_at(h_plus_3m), 2)

        dt_1m = round(t_plus_1m - t_spray, 2)
        dt_3m = round(t_plus_3m - t_spray, 2)

        w_spray, d_spray = self.wind_at(h_spray)
        w_plus_1m, d_plus_1m = self.wind_at(h_plus_1m)
        w_plus_3m, d_plus_3m = self.wind_at(h_plus_3m)

        shear_1m = round(abs(w_plus_1m - w_spray), 1)
        shear_3m = round(abs(w_plus_3m - w_spray), 1)

        dir_shear_1m = round(angle_diff(d_plus_1m, d_spray), 1)
        dir_shear_3m = round(angle_diff(d_plus_3m, d_spray), 1)

        inv_detected = (dt_3m > 0.0 or dt_1m > 0.0)

        if dt_3m >= 2.0 or dt_1m >= 1.5:
            severity = "Severe Spray-Plane Inversion (Lid Active)"
            risk = StatusEnum.STOP
            rec = f"DO NOT SPRAY: Strong thermal inversion lid (+{dt_3m:.1f}°F at +3m) directly capping {h_spray:.1f}m spray plane. Droplets will form horizontal drift cloud."
        elif dt_3m > 0.0 or dt_1m > 0.0:
            severity = "Moderate Spray-Plane Inversion (Lid Active)"
            risk = StatusEnum.STOP
            rec = f"DO NOT SPRAY: Positive thermal gradient (+{dt_3m:.1f}°F at +3m) capping spray release plane. Violates EPA spray drift inversion mandate."
        elif abs(dt_3m) < 0.05 and abs(dt_1m) < 0.02:
            severity = "Isothermal / Transitioning"
            risk = StatusEnum.CAUTION
            rec = f"CAUTION: Neutral temperature gradient at spray plane. Inversion may be transitioning."
        else:
            severity = "Normal Lapse (Safe Vertical Dispersion)"
            risk = StatusEnum.GO
            rec = f"GO: Normal lapse rate ({dt_3m:.1f}°F at +3m above release) allows safe vertical dispersion."

        return SprayHeightRiskAnalysis(
            spray_method=spray_method,
            spray_height_m=round(h_spray, 2),
            height_plus_1m=h_plus_1m,
            height_plus_3m=h_plus_3m,
            temp_at_spray_height_f=t_spray,
            temp_at_plus_1m_f=t_plus_1m,
            temp_at_plus_3m_f=t_plus_3m,
            delta_t_1m_f=dt_1m,
            delta_t_3m_f=dt_3m,
            wind_at_spray_height_mph=w_spray,
            wind_at_plus_1m_mph=w_plus_1m,
            wind_at_plus_3m_mph=w_plus_3m,
            dir_at_spray_height_deg=d_spray,
            dir_at_plus_1m_deg=d_plus_1m,
            dir_at_plus_3m_deg=d_plus_3m,
            wind_shear_1m_mph=shear_1m,
            wind_shear_3m_mph=shear_3m,
            dir_shear_1m_deg=dir_shear_1m,
            dir_shear_3m_deg=dir_shear_3m,
            spray_inversion_detected=inv_detected,
            spray_inversion_active=inv_detected,
            spray_inversion_severity=severity,
            spray_plane_risk=risk,
            recommendation=rec
        )


def calculate_drift_distance(
    wind_mph: float,
    nozzle: TeeJetNozzleType,
    boom_height_in: int,
    drift_multiplier: float = 1.0,
    aloft_wind_shear: float = 0.0
) -> float:
    """
    Estimates downwind drift distance (in feet) using empirical EPA AgDRIFT curve fitting
    augmented with multi-height inversion trapping and aloft shear multipliers.
    """
    nozzle_factors = {
        TeeJetNozzleType.FINE: 4.5,
        TeeJetNozzleType.MEDIUM: 2.2,
        TeeJetNozzleType.COARSE: 1.0,
        TeeJetNozzleType.VERY_COARSE: 0.6,
        TeeJetNozzleType.ULTRA_COARSE: 0.3
    }
    factor = nozzle_factors.get(nozzle, 1.0)
    boom_factor = (boom_height_in / 24.0) ** 1.3
    shear_factor = 1.0 + (min(aloft_wind_shear, 15.0) * 0.04)
    
    # Base physics: D = V_wind * factor * boom_height * inversion_multiplier * shear_factor
    base_dist = (wind_mph * 22.0) * factor * boom_factor * drift_multiplier * shear_factor
    return round(max(30.0, base_dist), 1)


def build_drift_cone_polygon(lat: float, lon: float, bearing_deg: float, distance_ft: float, angle_deg: float = 35.0) -> List[List[float]]:
    """Generates a triangular downwind drift cone in [longitude, latitude] GeoJSON format."""
    meters_to_lat = 1.0 / 111000.0
    meters_to_lon = 1.0 / (111000.0 * math.cos(math.radians(lat)))
    dist_m = distance_ft * 0.3048

    downwind_bearing = (bearing_deg + 180.0) % 360.0
    left_bearing = math.radians(downwind_bearing - (angle_deg / 2.0))
    right_bearing = math.radians(downwind_bearing + (angle_deg / 2.0))

    p1 = [round(lon, 6), round(lat, 6)]
    p2 = [
        round(lon + (dist_m * math.sin(left_bearing) * meters_to_lon), 6),
        round(lat + (dist_m * math.cos(left_bearing) * meters_to_lat), 6)
    ]
    p3 = [
        round(lon + (dist_m * math.sin(right_bearing) * meters_to_lon), 6),
        round(lat + (dist_m * math.cos(right_bearing) * meters_to_lat), 6)
    ]
    return [p1, p2, p3, p1]


def evaluate_ground_station_only(r: TowerReading, product: ChemicalProduct) -> StatusEnum:
    """What a standard 5 ft single-height weather station concludes without aloft data."""
    if r.wind_low_mph < 3.0 or r.wind_low_mph > product.max_label_wind_mph:
        return StatusEnum.STOP
    if r.wind_low_mph > 8.0 or r.t_low_f > product.max_label_temp_f:
        return StatusEnum.CAUTION
    return StatusEnum.GO


def assess_drift_risk(
    r: TowerReading,
    product: Optional[ChemicalProduct] = None,
    nozzle: TeeJetNozzleType = TeeJetNozzleType.MEDIUM,
    boom_height_inches: int = 24,
    spray_method: SprayMethodEnum = SprayMethodEnum.TRACTOR,
    spray_height_m: Optional[float] = None
) -> Assessment:
    prod = product or POPULAR_PRODUCTS["radiant"]
    evals: List[RuleEvaluation] = []
    level = 0  # 0: GO, 1: CAUTION, 2: STOP

    profile, multi_analysis = analyze_multi_height_profile(r)
    interpolator = AtmosphericProfileInterpolator(r)
    spray_analysis = interpolator.analyze_spray_height(spray_method, spray_height_m)

    delta_t = multi_analysis.canopy_to_80m_delta_f
    wind_shear = multi_analysis.max_wind_shear_mph
    dir_shear = multi_analysis.max_dir_shear_deg

    # 1. Multi-Tier Inversion Rules
    if multi_analysis.severity in [InversionSeverityEnum.STRONG, InversionSeverityEnum.EXTREME]:
        level = max(level, 2)
        evals.append(RuleEvaluation(
            rule_name="EPA Inversion Prohibition (Multi-Height)",
            status=StatusEnum.STOP,
            measured=f"+{multi_analysis.max_delta_t_f:.1f}°F ({multi_analysis.primary_inversion_type.value})",
            threshold="< 0.0°F (normal lapse)",
            reason=f"Severe thermal inversion lid up to {multi_analysis.max_inversion_height_m:.0f}m. Fine droplets trapped in stagnant suspension will drift off-target for miles."
        ))
    elif multi_analysis.inversion_detected:
        level = max(level, 2)
        evals.append(RuleEvaluation(
            rule_name="EPA Inversion Prohibition (Multi-Height)",
            status=StatusEnum.STOP,
            measured=f"+{multi_analysis.max_delta_t_f:.1f}°F ({multi_analysis.primary_inversion_type.value})",
            threshold="< 0.0°F",
            reason=f"Thermal stratification detected: legal violation of EPA spray drift mandate ({multi_analysis.primary_inversion_type.value})."
        ))
    elif delta_t >= -1.0:
        level = max(level, 1)
        evals.append(RuleEvaluation(
            rule_name="Atmospheric Mixing",
            status=StatusEnum.CAUTION,
            measured=f"{delta_t:.1f}°F lapse",
            threshold="< -1.0°F",
            reason="Isothermal layer: weak vertical mixing, inversion layer transitioning."
        ))
    else:
        evals.append(RuleEvaluation(
            rule_name="Atmospheric Mixing",
            status=StatusEnum.GO,
            measured=f"{delta_t:.1f}°F lapse",
            threshold="Normal lapse",
            reason="Normal daytime lapse rate allows safe vertical dispersion."
        ))

    # 2. Surface Radiation Inversion Check (0m Ground to 2m Canopy)
    if multi_analysis.ground_to_canopy_delta_f >= 2.0:
        level = max(level, 2)
        evals.append(RuleEvaluation(
            rule_name="Ground-Level Radiative Inversion (0m-2m)",
            status=StatusEnum.STOP,
            measured=f"Ground 0m is {abs(multi_analysis.ground_to_canopy_delta_f):.1f}°F colder than canopy",
            threshold="< +1.0°F gradient",
            reason="Cold air pooling at desert soil surface creates ultra-stable micro-inversion layer trapping fine spray right at release height."
        ))

    # 3. EPA Wind Speed Limits (3.0 – 10.0 mph)
    if r.wind_low_mph < 3.0:
        level = max(level, 2)
        evals.append(RuleEvaluation(
            rule_name="EPA Minimum Wind",
            status=StatusEnum.STOP,
            measured=f"{r.wind_low_mph:.1f} mph",
            threshold=">= 3.0 mph",
            reason="Dead calm / stagnant air (<3 mph). Droplets remain suspended without predictable drift vector."
        ))
    elif r.wind_low_mph > prod.max_label_wind_mph:
        level = max(level, 2)
        evals.append(RuleEvaluation(
            rule_name="EPA Maximum Wind",
            status=StatusEnum.STOP,
            measured=f"{r.wind_low_mph:.1f} mph",
            threshold=f"<= {prod.max_label_wind_mph} mph",
            reason=f"Surface wind exceeds EPA legal label maximum ({prod.max_label_wind_mph} mph)."
        ))
    elif r.wind_low_mph > 8.0:
        level = max(level, 1)
        evals.append(RuleEvaluation(
            rule_name="Surface Wind Buffer",
            status=StatusEnum.CAUTION,
            measured=f"{r.wind_low_mph:.1f} mph",
            threshold="3.0–8.0 mph",
            reason="Wind near upper margin. Recommend switching to TeeJet AIXR Coarse or TTI Ultra-Coarse nozzles."
        ))
    else:
        evals.append(RuleEvaluation(
            rule_name="Surface Wind",
            status=StatusEnum.GO,
            measured=f"{r.wind_low_mph:.1f} mph",
            threshold="3.0–8.0 mph",
            reason="Ideal laminar surface wind within EPA label specifications."
        ))

    # 4. Multi-Tier Aloft Wind Shear across Canopy & Upper Tiers
    if wind_shear > 8.0 or dir_shear > 90.0:
        level = max(level, 2)
        evals.append(RuleEvaluation(
            rule_name="Multi-Tier Canopy Wind Shear",
            status=StatusEnum.STOP,
            measured=f"Δ{wind_shear:.1f} mph, {dir_shear:.0f}° divergence across column",
            threshold="ΔV <= 5 mph, Δθ <= 45°",
            reason=f"Severe aloft wind shear: aloft flow is moving {wind_shear:.0f} mph faster with {dir_shear:.0f}° crosswind divergence."
        ))
    elif wind_shear > 5.0 or dir_shear > 45.0:
        level = max(level, 1)
        evals.append(RuleEvaluation(
            rule_name="Multi-Tier Canopy Wind Shear",
            status=StatusEnum.CAUTION,
            measured=f"Δ{wind_shear:.1f} mph, {dir_shear:.0f}° divergence",
            threshold="ΔV <= 5 mph",
            reason="Moderate aloft wind shear across boundary layer. Fine droplet fraction will detach into upper flow."
        ))

    # 5. Chemical Mode of Action & TeeJet Nozzle Interaction
    if prod.category == ChemicalCategory.HERBICIDE_SYSTEMIC and nozzle in [TeeJetNozzleType.FINE, TeeJetNozzleType.MEDIUM]:
        level = max(level, 2)
        evals.append(RuleEvaluation(
            rule_name="Systemic Herbicide / Nozzle Mismatch",
            status=StatusEnum.STOP,
            measured=f"{nozzle.value}",
            threshold="Coarse or Ultra-Coarse",
            reason=f"High off-target risk: Systemic herbicide ({prod.name}) applied with fine/medium droplets risks total kill of adjacent crops."
        ))

    if boom_height_inches > 30 and level == 1:
        level = 2
        evals.append(RuleEvaluation(
            rule_name="Boom Release Height",
            status=StatusEnum.STOP,
            measured=f"{boom_height_inches} inches",
            threshold="<= 24 inches",
            reason="Excessive boom height significantly widens the downwind drift cone in desert winds."
        ))

    # 6. Spray-Plane Inversion Lid (+1m and +3m Above Release Height)
    if spray_analysis.spray_plane_risk == StatusEnum.STOP:
        level = max(level, 2)
        evals.append(RuleEvaluation(
            rule_name="Spray-Plane Inversion Lid (+1m/+3m Above Release)",
            status=StatusEnum.STOP,
            measured=f"+{spray_analysis.delta_t_3m_f:.1f}°F at +3m above {spray_analysis.spray_height_m}m {spray_analysis.spray_method.value} release",
            threshold="<= 0.0°F (normal lapse)",
            reason=spray_analysis.recommendation
        ))
    elif spray_analysis.spray_plane_risk == StatusEnum.CAUTION:
        level = max(level, 1)
        evals.append(RuleEvaluation(
            rule_name="Spray-Plane Atmospheric Mixing",
            status=StatusEnum.CAUTION,
            measured=f"{spray_analysis.delta_t_3m_f:.1f}°F at +3m above {spray_analysis.spray_height_m}m release",
            threshold="< -1.0°F",
            reason=spray_analysis.recommendation
        ))

    overall_status = [StatusEnum.GO, StatusEnum.CAUTION, StatusEnum.STOP][level]
    ground_status = evaluate_ground_station_only(r, prod)
    blind_spot_caught = (ground_status == StatusEnum.GO and overall_status != StatusEnum.GO)

    # Compute spatial drift plume geometry with multi-height dispersion multiplier
    drift_dist_ft = calculate_drift_distance(
        r.wind_low_mph, nozzle, boom_height_inches,
        drift_multiplier=multi_analysis.drift_dispersion_multiplier,
        aloft_wind_shear=wind_shear
    )
    poly = build_drift_cone_polygon(r.lat, r.lon, r.dir_low_deg, drift_dist_ft)
    
    # Check if plume encroaches past a standard 20/40-acre parcel buffer
    encroached = drift_dist_ft > prod.buffer_required_ft
    encroached_names = ["Adjacent Organic Romaine Block (40 ac)"] if encroached else []

    plume = SpatialPlumeGeometry(
        origin_lat=r.lat,
        origin_lon=r.lon,
        wind_bearing_deg=r.dir_low_deg,
        plume_distance_ft=drift_dist_ft,
        plume_cone_angle_deg=35.0,
        risk_level=overall_status,
        polygon_coordinates=poly,
        buffer_encroachment=encroached,
        encroached_parcels=encroached_names
    )

    headlines = {
        StatusEnum.GO: "GO — SAFE SPRAY WINDOW ACTIVE",
        StatusEnum.CAUTION: "CAUTION — MARGINAL DRIFT RISK (ADJUST NOZZLE/BUFFER)",
        StatusEnum.STOP: "STOP — DO NOT SPRAY (HAZARDOUS INVERSION OR SHEAR)"
    }
    
    reasons = [e.reason for e in evals if e.status == overall_status]
    plain_explanation = " | ".join(reasons) if reasons else "All microclimate, multi-height stability, and nozzle criteria within safe limits."

    return Assessment(
        timestamp=r.timestamp,
        overall_status=overall_status,
        headline=headlines[overall_status],
        plain_explanation=plain_explanation,
        ground_only_status=ground_status,
        blind_spot_caught=blind_spot_caught,
        delta_t_f=delta_t,
        wind_shear_mph=wind_shear,
        dir_shear_deg=dir_shear,
        evaluations=evals,
        reading=r,
        product=prod,
        nozzle=nozzle,
        boom_height_inches=boom_height_inches,
        multi_height_analysis=multi_analysis,
        height_profile=profile,
        spray_risk_analysis=spray_analysis,
        spatial_plume=plume
    )
