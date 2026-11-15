import pytest
from app.forecast.model import SprayRiskForecaster


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
