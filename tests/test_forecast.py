import pytest
from app.forecast.model import SprayRiskForecaster
from app.schemas import SprayMethodEnum


def test_forecast_model_initialization():
    forecaster = SprayRiskForecaster()
    assert forecaster.clf is not None
    assert forecaster.brier_improvement > 30.0


def test_forecast_12h():
    forecaster = SprayRiskForecaster()
    hours, windows = forecaster.forecast_12h(
        current_t_low=60.0,
        current_delta_t=4.0,  # Strong dawn inversion
        current_wind=3.5,
        start_hour=6
    )

    assert len(hours) == 12
    # First hour under strong inversion should be STOP
    assert hours[0]["status"] == "STOP"
    assert hours[0]["p_unsafe"] >= 0.0

    # Probabilities must be within [0, 1]
    for h in hours:
        assert 0.0 <= h["p_unsafe"] <= 1.0
        assert h["status"] in ["GO", "CAUTION", "STOP"]

    # Windows should be a list
    assert isinstance(windows, list)


def test_forecast_12h_with_spray_method():
    forecaster = SprayRiskForecaster()
    # Test with agricultural spray drone (2.5m)
    hours, windows = forecaster.forecast_12h(
        current_t_low=62.0,
        current_delta_t=3.0,
        current_wind=4.0,
        start_hour=6,
        spray_method=SprayMethodEnum.DRONE
    )

    assert len(hours) == 12
    for h in hours:
        assert h["spray_height_m"] == 2.5
        assert "temp_at_spray_height_f" in h
        assert "temp_at_plus_1m_f" in h
        assert "temp_at_plus_3m_f" in h
        assert "delta_t_3m_f" in h
        assert "wind_at_spray_height_mph" in h
        assert "wind_at_plus_1m_mph" in h
        assert "wind_at_plus_3m_mph" in h
        assert "spray_inversion_active" in h
        # Wind at +3m should be >= wind at spray height due to vertical shear
        assert h["wind_at_plus_3m_mph"] >= h["wind_at_spray_height_mph"]
