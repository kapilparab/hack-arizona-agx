import math
from typing import Tuple, List, Optional
from app.schemas import (
    TowerReading, ChemicalProduct, Assessment, StatusEnum,
    RuleEvaluation, TeeJetNozzleType, ChemicalCategory, SpatialPlumeGeometry,
    HeightLevelReading, HeightProfile, MultiHeightInversionAnalysis,
    InversionTypeEnum, InversionSeverityEnum, POPULAR_PRODUCTS
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
    boom_height_inches: int = 24
) -> Assessment:
    prod = product or POPULAR_PRODUCTS["radiant"]
    evals: List[RuleEvaluation] = []
    level = 0  # 0: GO, 1: CAUTION, 2: STOP

    profile, multi_analysis = analyze_multi_height_profile(r)
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
        spatial_plume=plume
    )
