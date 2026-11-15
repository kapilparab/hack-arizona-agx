import pytest
from app.schemas import (
    TowerReading, InversionTypeEnum, InversionSeverityEnum,
    StatusEnum, POPULAR_PRODUCTS, TeeJetNozzleType
)
from app.rules import analyze_multi_height_profile, assess_drift_risk


def test_surface_radiation_inversion_detection():
    # Ground 0m is cold (52.0°F) while 2m is 58.0°F -> Surface Radiation Inversion!
    r = TowerReading(
        t_ground_0m_f=52.0,
        t_low_f=58.0,
        t_high_f=56.0,
        t_120m_f=55.0,
        t_180m_f=54.0,
        wind_low_mph=4.0,
        wind_high_mph=4.5
    )
    profile, analysis = analyze_multi_height_profile(r)
    assert analysis.inversion_detected is True
    assert InversionTypeEnum.SURFACE_RADIATION in analysis.inversion_types
    assert analysis.ground_to_canopy_delta_f == 6.0
    assert profile.ground_0m.temp_f == 52.0
    assert profile.canopy_2m.is_inverted is True


def test_low_level_epa_inversion_detection():
    # 2m canopy is 58.0°F, 80m aloft is 63.5°F (+5.5°F) -> Low-Level Lid
    r = TowerReading(
        t_ground_0m_f=58.0,
        t_low_f=58.0,
        t_high_f=63.5,
        t_120m_f=62.0,
        t_180m_f=61.0,
        wind_low_mph=4.0,
        wind_high_mph=4.5
    )
    profile, analysis = analyze_multi_height_profile(r)
    assert analysis.inversion_detected is True
    assert InversionTypeEnum.LOW_LEVEL_LID in analysis.inversion_types
    assert analysis.canopy_to_80m_delta_f == 5.5
    assert analysis.severity == InversionSeverityEnum.EXTREME
    assert profile.aloft_80m.is_inverted is True


def test_elevated_capping_inversion_blind_spot():
    # 2m is 70.0°F, 80m is 68.5°F (-1.5°F lapse - looks safe at ground!).
    # BUT 120m is 73.0°F and 180m is 75.0°F (+6.5°F warm lid aloft!)
    r = TowerReading(
        t_ground_0m_f=71.0,
        t_low_f=70.0,
        t_high_f=68.5,
        t_120m_f=73.0,
        t_180m_f=75.0,
        wind_low_mph=5.0,
        wind_high_mph=6.0,
        wind_120m_mph=8.5,
        wind_180m_mph=11.0
    )
    profile, analysis = analyze_multi_height_profile(r)
    assert analysis.inversion_detected is True
    assert InversionTypeEnum.ELEVATED_CAP in analysis.inversion_types
    assert analysis.max_inversion_height_m == 180.0
    assert profile.aloft_120m.is_inverted is True
    assert profile.aloft_180m.is_inverted is True

    # Assess drift risk: Ground station says GO, but multi-height catches the blind spot!
    assessment = assess_drift_risk(r, product=POPULAR_PRODUCTS["radiant"])
    assert assessment.ground_only_status == StatusEnum.GO
    assert assessment.overall_status == StatusEnum.STOP
    assert assessment.blind_spot_caught is True


def test_deep_column_inversion():
    # Ground 54°F, 2m 58°F, 80m 64°F, 120m 66°F, 180m 67°F
    r = TowerReading(
        t_ground_0m_f=54.0,
        t_low_f=58.0,
        t_high_f=64.0,
        t_120m_f=66.0,
        t_180m_f=67.0,
        wind_low_mph=3.8,
        wind_high_mph=4.5
    )
    profile, analysis = analyze_multi_height_profile(r)
    assert InversionTypeEnum.DEEP_COLUMN in analysis.inversion_types
    assert analysis.severity == InversionSeverityEnum.EXTREME
    assert analysis.drift_dispersion_multiplier >= 2.8


def test_multi_tier_wind_shear():
    # Surface wind 4.8 mph @ 270°, aloft 80m 14.5 mph @ 210°, 180m 21.0 mph @ 180°
    r = TowerReading(
        t_ground_0m_f=67.0,
        t_low_f=66.0,
        t_high_f=65.0,
        t_120m_f=64.0,
        t_180m_f=63.0,
        wind_low_mph=4.8,
        wind_high_mph=14.5,
        wind_120m_mph=17.8,
        wind_180m_mph=21.0,
        dir_low_deg=270.0,
        dir_high_deg=210.0,
        dir_120m_deg=195.0,
        dir_180m_deg=180.0
    )
    profile, analysis = analyze_multi_height_profile(r)
    assert analysis.max_wind_shear_mph == 16.2  # 21.0 - 4.8
    assert analysis.max_dir_shear_deg == 90.0   # 270 vs 180

    assessment = assess_drift_risk(r, product=POPULAR_PRODUCTS["radiant"])
    assert assessment.overall_status == StatusEnum.STOP
    assert any("Canopy Wind Shear" in e.rule_name for e in assessment.evaluations)


def test_clean_daytime_lapse_rate():
    # Surface ground 76°F, 2m 72°F, 80m 69.5°F, 120m 68°F, 180m 66.5°F
    r = TowerReading(
        t_ground_0m_f=76.0,
        t_low_f=72.0,
        t_high_f=69.5,
        t_120m_f=68.0,
        t_180m_f=66.5,
        wind_low_mph=5.5,
        wind_high_mph=6.8,
        wind_120m_mph=7.2,
        wind_180m_mph=7.5,
        dir_low_deg=340.0,
        dir_high_deg=345.0
    )
    profile, analysis = analyze_multi_height_profile(r)
    assert analysis.inversion_detected is False
    assert analysis.primary_inversion_type == InversionTypeEnum.NONE
    assert analysis.severity == InversionSeverityEnum.NONE

    assessment = assess_drift_risk(r, product=POPULAR_PRODUCTS["radiant"], nozzle=TeeJetNozzleType.MEDIUM)
    assert assessment.overall_status == StatusEnum.GO
    assert assessment.blind_spot_caught is False
