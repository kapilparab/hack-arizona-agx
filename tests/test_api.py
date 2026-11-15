import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "CanopyGuard Pro API"
    assert "/assess" in data["endpoints"]


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_assess_scenario():
    # Hero scenario: Yuma Radiation Inversion
    response = client.get("/assess?source=scenario&scenario_id=yuma_radiation_inversion")
    assert response.status_code == 200
    data = response.json()
    assert data["overall_status"] == "STOP"
    assert data["multi_height_analysis"]["inversion_detected"] is True
    assert data["reading"]["t_ground_0m_f"] == 54.0
    assert data["spatial_plume"] is not None


def test_assess_custom_multi_height():
    # Elevated cap custom scenario
    response = client.get(
        "/assess?source=custom"
        "&t_ground_0m=71.0&t_low=70.0&t_high=68.5&t_120m=73.0&t_180m=75.0"
        "&w_low=5.0&w_high=6.0"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["overall_status"] == "STOP"
    assert data["blind_spot_caught"] is True
    assert data["ground_only_status"] == "GO"


def test_assess_profile():
    response = client.get("/assess/profile?source=scenario&scenario_id=yuma_radiation_inversion")
    assert response.status_code == 200
    data = response.json()
    assert "profile" in data
    assert "analysis" in data
    assert len(data["profile"]["levels"]) == 5
    assert data["analysis"]["inversion_detected"] is True


def test_map_parcels():
    response = client.get("/map/parcels")
    assert response.status_code == 200
    parcels = response.json()
    assert len(parcels) == 3
    assert any(p["acres"] == 20 for p in parcels)
    assert any(p["is_sensitive"] for p in parcels)


def test_forecast():
    response = client.get("/forecast?t_low=62.0&delta_t=3.0&wind=4.0")
    assert response.status_code == 200
    data = response.json()
    assert "brier_improvement_vs_persistence" in data
    assert len(data["hourly_forecast"]) == 12
    assert "recommended_windows" in data


def test_scenarios():
    response = client.get("/scenarios")
    assert response.status_code == 200
    data = response.json()
    assert "yuma_radiation_inversion" in data
    assert "marana_wind_shear" in data
    assert "yuma_elevated_cap" in data
    assert "yuma_ideal_window" in data


def test_chemicals():
    response = client.get("/chemicals")
    assert response.status_code == 200
    data = response.json()
    assert "radiant" in data
    assert "prefar" in data


def test_logs_and_export():
    # Call assess to generate a log entry
    client.get("/assess?source=scenario&scenario_id=yuma_ideal_window")
    
    # Retrieve logs
    response = client.get("/logs?limit=5")
    assert response.status_code == 200
    logs = response.json()
    assert len(logs) >= 1

    # Export CSV
    csv_resp = client.get("/logs/export")
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert "overall_status" in csv_resp.text
