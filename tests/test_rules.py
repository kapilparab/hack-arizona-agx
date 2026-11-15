import pytest
from app.schemas import (
    TowerReading, ChemicalProduct, ChemicalCategory, ApplicationTiming,
    TeeJetNozzleType, StatusEnum, POPULAR_PRODUCTS
)
from app.rules import (
    angle_diff, calculate_drift_distance, build_drift_cone_polygon,
    evaluate_ground_station_only, assess_drift_risk
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
    # Systemic herbicide (Prefar) with fine/medium nozzle must trigger STOP
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
