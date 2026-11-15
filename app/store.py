import os
import sqlite3
import csv
import io
from typing import List, Dict, Any, Optional
from app.schemas import Assessment

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "canopyguard.db")


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None):
    conn = get_db_connection(db_path)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS compliance_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                location_name TEXT,
                lat REAL,
                lon REAL,
                overall_status TEXT NOT NULL,
                headline TEXT,
                ground_only_status TEXT,
                blind_spot_caught INTEGER,
                t_ground_0m REAL,
                t_2m REAL,
                t_80m REAL,
                t_120m REAL,
                t_180m REAL,
                wind_low_mph REAL,
                wind_high_mph REAL,
                wind_120m_mph REAL,
                wind_180m_mph REAL,
                dir_low_deg REAL,
                dir_high_deg REAL,
                delta_t_f REAL,
                wind_shear_mph REAL,
                dir_shear_deg REAL,
                inversion_detected INTEGER,
                primary_inversion_type TEXT,
                inversion_severity TEXT,
                trapping_risk_score REAL,
                product_name TEXT,
                chemical_category TEXT,
                nozzle TEXT,
                boom_height_inches INTEGER,
                drift_distance_ft REAL,
                buffer_encroachment INTEGER,
                plain_explanation TEXT
            )
        """)
    conn.close()


def record_assessment(assessment: Assessment, db_path: Optional[str] = None) -> int:
    init_db(db_path)
    conn = get_db_connection(db_path)
    
    r = assessment.reading
    p = assessment.product
    plume = assessment.spatial_plume
    m = assessment.multi_height_analysis

    inv_detected = 1 if (m and m.inversion_detected) else 0
    inv_type = m.primary_inversion_type.value if m else "N/A"
    inv_sev = m.severity.value if m else "N/A"
    trapping_score = m.trapping_risk_score if m else 0.0

    drift_dist = plume.plume_distance_ft if plume else 0.0
    encroached = 1 if (plume and plume.buffer_encroachment) else 0

    with conn:
        cur = conn.execute("""
            INSERT INTO compliance_logs (
                timestamp, location_name, lat, lon, overall_status, headline,
                ground_only_status, blind_spot_caught, t_ground_0m, t_2m, t_80m,
                t_120m, t_180m, wind_low_mph, wind_high_mph, wind_120m_mph,
                wind_180m_mph, dir_low_deg, dir_high_deg, delta_t_f, wind_shear_mph,
                dir_shear_deg, inversion_detected, primary_inversion_type,
                inversion_severity, trapping_risk_score, product_name, chemical_category,
                nozzle, boom_height_inches, drift_distance_ft, buffer_encroachment,
                plain_explanation
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            assessment.timestamp.isoformat(),
            r.location_name,
            r.lat,
            r.lon,
            assessment.overall_status.value,
            assessment.headline,
            assessment.ground_only_status.value,
            1 if assessment.blind_spot_caught else 0,
            r.t_ground_0m_f,
            r.t_low_f,
            r.t_high_f,
            r.t_120m_f,
            r.t_180m_f,
            r.wind_low_mph,
            r.wind_high_mph,
            r.wind_120m_mph,
            r.wind_180m_mph,
            r.dir_low_deg,
            r.dir_high_deg,
            assessment.delta_t_f,
            assessment.wind_shear_mph,
            assessment.dir_shear_deg,
            inv_detected,
            inv_type,
            inv_sev,
            trapping_score,
            p.name,
            p.category.value,
            assessment.nozzle.value,
            assessment.boom_height_inches,
            drift_dist,
            encroached,
            assessment.plain_explanation
        ))
        log_id = cur.lastrowid
    conn.close()
    return log_id or 0


def get_recent_logs(limit: int = 50, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    init_db(db_path)
    conn = get_db_connection(db_path)
    cur = conn.execute("""
        SELECT * FROM compliance_logs
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def export_csv(db_path: Optional[str] = None) -> str:
    init_db(db_path)
    conn = get_db_connection(db_path)
    cur = conn.execute("SELECT * FROM compliance_logs ORDER BY id DESC")
    rows = cur.fetchall()
    
    output = io.StringIO()
    if rows:
        writer = csv.writer(output)
        writer.writerow(rows[0].keys())
        for row in rows:
            writer.writerow(tuple(row))
    else:
        writer = csv.writer(output)
        writer.writerow([
            "id", "timestamp", "location_name", "lat", "lon", "overall_status",
            "headline", "ground_only_status", "blind_spot_caught", "t_ground_0m",
            "t_2m", "t_80m", "t_120m", "t_180m", "wind_low_mph", "wind_high_mph",
            "wind_120m_mph", "wind_180m_mph", "dir_low_deg", "dir_high_deg",
            "delta_t_f", "wind_shear_mph", "dir_shear_deg", "inversion_detected",
            "primary_inversion_type", "inversion_severity", "trapping_risk_score",
            "product_name", "chemical_category", "nozzle", "boom_height_inches",
            "drift_distance_ft", "buffer_encroachment", "plain_explanation"
        ])
    conn.close()
    return output.getvalue()


def clear_logs(db_path: Optional[str] = None):
    init_db(db_path)
    conn = get_db_connection(db_path)
    with conn:
        conn.execute("DELETE FROM compliance_logs")
    conn.close()
