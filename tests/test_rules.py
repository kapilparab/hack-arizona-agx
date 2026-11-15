import pytest
from app.schemas import (
    TowerReading, ChemicalProduct, ChemicalCategory, ApplicationTiming,
    TeeJetNozzleType, StatusEnum, SprayMethodEnum, POPULAR_PRODUCTS
)
from app.rules import (
    angle_diff, calculate_drift_distance, build_drift_cone_polygon,
    evaluate_ground_station_only, assess_drift_risk, AtmosphericProfileInterpolator
)


def test_angle_diff():
    assert angle_diff(0, 0) == 0
    assert angle_diff(350, 10) == 20
    assert angle_diff(10, 350) == 20
    assert angle_diff(180, 0) == 180
    assert angle_diff(90, 270) == 180
    assert angle_diff(45, 90) == 45


def test_calculate_drift_distance():
    # Fine nozzle should drift significantly farther than ultra-coarse
    dist_fine = calculate_drift_distance(wind_mph=5.0, nozzle=TeeJetNozzleType.FINE, boom_height_in=24)
    dist_ultra = calculate_drift_distance(wind_mph=5.0, nozzle=TeeJetNozzleType.ULTRA_COARSE, boom_height_in=24)
    assert dist_fine > dist_ultra * 10

    # Boom height increases drift distance
    dist_high_boom = calculate_drift_distance(wind_mph=5.0, nozzle=TeeJetNozzleType.MEDIUM, boom_height_in=36)
    dist_normal_boom = calculate_drift_distance(wind_mph=5.0, nozzle=TeeJetNozzleType.MEDIUM, boom_height_in=24)
    assert dist_high_boom > dist_normal_boom

    # Multiplier and shear increase drift distance
    dist_inv = calculate_drift_distance(wind_mph=5.0, nozzle=TeeJetNozzleType.MEDIUM, boom_height_in=24, drift_multiplier=2.5)
    dist_norm = calculate_drift_distance(wind_mph=5.0, nozzle=TeeJetNozzleType.MEDIUM, boom_height_in=24, drift_multiplier=1.0)
    assert dist_inv > dist_norm


def test_build_drift_cone_polygon():
    poly = build_drift_cone_polygon(lat=32.7130, lon=-114.7000, bearing_deg=315.0, distance_ft=200.0)
    assert len(poly) == 4
    # Polygon should close
    assert poly[0] == poly[-1]
    # Origin should be first point
    assert poly[0] == [-114.7000, 32.7130]


def test_evaluate_ground_station_only():
    prod = POPULAR_PRODUCTS["radiant"]
    
    # Calm wind (< 3 mph) -> STOP
    r_calm = TowerReading(t_low_f=65.0, wind_low_mph=2.0, t_high_f=64.0, wind_high_mph=2.5)
    assert evaluate_ground_station_only(r_calm, prod) == StatusEnum.STOP

    # Excessive wind (> 10 mph) -> STOP
    r_high_wind = TowerReading(t_low_f=65.0, wind_low_mph=12.0, t_high_f=64.0, wind_high_mph=14.0)
    assert evaluate_ground_station_only(r_high_wind, prod) == StatusEnum.STOP

    # Upper marginal wind (8.5 mph) -> CAUTION
    r_caution = TowerReading(t_low_f=65.0, wind_low_mph=8.5, t_high_f=64.0, wind_high_mph=9.0)
    assert evaluate_ground_station_only(r_caution, prod) == StatusEnum.CAUTION

    # Safe wind (5.0 mph) -> GO
    r_safe = TowerReading(t_low_f=65.0, wind_low_mph=5.0, t_high_f=64.0, wind_high_mph=6.0)
    assert evaluate_ground_station_only(r_safe, prod) == StatusEnum.GO


def test_assess_drift_risk_systemic_nozzle_mismatch():
    prefar = POPULAR_PRODUCTS["prefar"]
    r = TowerReading(
        t_ground_0m_f=70.0,
        t_low_f=68.0,
        t_high_f=65.0,
        wind_low_mph=5.0,
        wind_high_mph=6.0
    )
    assessment = assess_drift_risk(r, product=prefar, nozzle=TeeJetNozzleType.FINE)
    assert assessment.overall_status == StatusEnum.STOP
    assert any("Systemic Herbicide / Nozzle Mismatch" in e.rule_name for e in assessment.evaluations)


def test_atmospheric_profile_interpolator_monotonicity():
    # Dawn inversion: 0m=54°F, 2m=58.2°F, 80m=64.0°F, 120m=65.5°F, 180m=66.8°F
    r = TowerReading(
        t_ground_0m_f=54.0,
        t_low_f=58.2,
        t_high_f=64.0,
        t_120m_f=65.5,
        t_180m_f=66.8,
        wind_low_mph=3.8,
        wind_high_mph=4.5
    )
    interp = AtmosphericProfileInterpolator(r)
    
    # Check exact anchor reproduction
    assert abs(interp.temperature_at(0.0) - 54.0) < 1e-4
    assert abs(interp.temperature_at(2.0) - 58.2) < 1e-4
    assert abs(interp.temperature_at(80.0) - 64.0) < 1e-4
    assert abs(interp.temperature_at(120.0) - 65.5) < 1e-4
    assert abs(interp.temperature_at(180.0) - 66.8) < 1e-4

    # Check strict monotonicity on inversion curve
    test_heights = [0.0, 0.5, 1.0, 1.6, 2.0, 2.5, 3.6, 5.0, 10.0, 25.0, 50.0, 80.0]
    temps = [interp.temperature_at(h) for h in test_heights]
    for i in range(len(temps) - 1):
        assert temps[i] <= temps[i + 1]


def test_atmospheric_profile_interpolator_wind_circular():
    # Surface wind 350°, aloft wind 10°
    r = TowerReading(
        t_ground_0m_f=65.0,
        t_low_f=64.0,
        t_high_f=62.0,
        wind_low_mph=5.0,
        wind_high_mph=10.0,
        dir_low_deg=350.0,
        dir_high_deg=10.0
    )
    interp = AtmosphericProfileInterpolator(r)
    
    # Midway direction should cross 0° / 360° (e.g. ~0°), NOT go through 180° south!
    mid_spd, mid_dir = interp.wind_at(45.0)
    assert mid_dir < 20.0 or mid_dir > 340.0


def test_spray_height_analysis_tractor():
    # Strong surface inversion
    r = TowerReading(
        t_ground_0m_f=52.0,
        t_low_f=58.0,
        t_high_f=64.0,
        wind_low_mph=4.0,
        wind_high_mph=5.0
    )
    interp = AtmosphericProfileInterpolator(r)
    analysis = interp.analyze_spray_height(spray_method=SprayMethodEnum.TRACTOR)
    
    assert analysis.spray_height_m == 0.6
    assert analysis.height_plus_1m == 1.6
    assert analysis.height_plus_3m == 3.6
    # In surface inversion, temperature at +1m and +3m should be warmer than at 0.6m
    assert analysis.delta_t_1m_f > 0.0
    assert analysis.delta_t_3m_f > 0.0
    assert analysis.spray_inversion_detected is True
    assert analysis.spray_plane_risk == StatusEnum.STOP


def test_spray_height_analysis_drone_and_aircraft():
    r = TowerReading(
        t_ground_0m_f=75.0,
        t_low_f=72.0,
        t_high_f=69.0,
        wind_low_mph=5.0,
        wind_high_mph=8.0
    )
    interp = AtmosphericProfileInterpolator(r)
    
    # Drone (2.5m) in daytime normal lapse
    drone_analysis = interp.analyze_spray_height(spray_method=SprayMethodEnum.DRONE)
    assert drone_analysis.spray_height_m == 2.5
    assert drone_analysis.height_plus_3m == 5.5
    assert drone_analysis.delta_t_3m_f <= 0.0
    assert drone_analysis.spray_plane_risk == StatusEnum.GO

    # Aircraft (4.5m)
    aircraft_analysis = interp.analyze_spray_height(spray_method=SprayMethodEnum.AIRCRAFT)
    assert aircraft_analysis.spray_height_m == 4.5
    assert aircraft_analysis.height_plus_3m == 7.5
