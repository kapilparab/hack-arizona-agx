import os
import tempfile
import pytest
from app.schemas import TowerReading, Assessment, POPULAR_PRODUCTS, TeeJetNozzleType
from app.rules import assess_drift_risk
from app.store import init_db, record_assessment, get_recent_logs, export_csv, clear_logs


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_store_and_export(temp_db):
    r = TowerReading(
        t_ground_0m_f=55.0,
        t_low_f=58.0,
        t_high_f=63.0,
        wind_low_mph=4.0,
        wind_high_mph=5.0
    )
    assessment = assess_drift_risk(r, product=POPULAR_PRODUCTS["radiant"], nozzle=TeeJetNozzleType.MEDIUM)
    
    # Record assessment
    log_id = record_assessment(assessment, db_path=temp_db)
    assert log_id > 0

    # Retrieve logs
    logs = get_recent_logs(limit=10, db_path=temp_db)
    assert len(logs) == 1
    assert logs[0]["overall_status"] == assessment.overall_status.value
    assert logs[0]["product_name"] == "Radiant® SC"
    assert logs[0]["t_ground_0m"] == 55.0
    assert logs[0]["t_80m"] == 63.0

    # Export CSV
    csv_text = export_csv(db_path=temp_db)
    assert "Radiant® SC" in csv_text
    assert "timestamp" in csv_text

    # Clear logs
    clear_logs(db_path=temp_db)
    assert len(get_recent_logs(limit=10, db_path=temp_db)) == 0
