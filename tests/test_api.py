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


def test_spray_methods():
    response = client.get("/spray-methods")
    assert response.status_code == 200
    data = response.json()
    methods = {item["method"]: item for item in data}
    assert "tractor" in methods
    assert "drone" in methods
    assert "aircraft" in methods
    assert methods["drone"]["default_spray_height_m"] == 2.5
    assert methods["aircraft"]["default_spray_height_m"] == 4.5
    assert methods["tractor"]["default_spray_height_m"] == 0.6


def test_interpolate_get():
    response = client.get(
        "/interpolate?source=scenario&scenario_id=yuma_radiation_inversion"
        "&heights=0.5,1.5,2.5,3.5,5.5&spray_method=drone"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["requested_heights"]) == 5
    assert len(data["points"]) == 5
    assert data["spray_analysis"] is not None
    assert data["spray_analysis"]["spray_method"] == "drone"
    assert data["spray_analysis"]["spray_height_m"] == 2.5
    assert "delta_t_1m_f" in data["spray_analysis"]
    assert "delta_t_3m_f" in data["spray_analysis"]
    assert "spray_inversion_detected" in data["spray_analysis"]


def test_interpolate_post():
    payload = {
        "source": "scenario",
        "scenario_id": "yuma_radiation_inversion",
        "heights": [0.6, 1.6, 2.5, 3.6, 4.5, 7.5],
        "spray_method": "aircraft",
        "spray_height_m": 4.5,
    }
    response = client.post("/interpolate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["points"]) == 6
    assert data["spray_analysis"]["spray_method"] == "aircraft"
    assert data["spray_analysis"]["spray_height_m"] == 4.5


def test_assess_with_spray_method():
    response = client.get(
        "/assess?source=scenario&scenario_id=yuma_radiation_inversion&spray_method=aircraft"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["spray_risk_analysis"] is not None
    assert data["spray_risk_analysis"]["spray_method"] == "aircraft"
    assert data["spray_risk_analysis"]["spray_height_m"] == 4.5
    assert data["spray_risk_analysis"]["spray_inversion_detected"] is True
    assert data["spray_risk_analysis"]["spray_inversion_active"] is True


def test_forecast_with_spray_method():
    response = client.get(
        "/forecast?source=scenario&scenario_id=yuma_radiation_inversion&spray_method=drone"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["spray_method"] == "drone"
    assert data["spray_height_m"] == 2.5
    assert len(data["hourly_forecast"]) == 12
    first_hour = data["hourly_forecast"][0]
    assert "temp_at_spray_height_f" in first_hour
    assert "temp_at_plus_1m_f" in first_hour
    assert "temp_at_plus_3m_f" in first_hour
    assert "delta_t_3m_f" in first_hour
    assert "spray_inversion_active" in first_hour

