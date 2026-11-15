"""SQLite persistence: treatment requests, user-marked areas, an append-only
record log, and grouped alerts. Append-only is enforced by this app's code
paths only; it is NOT tamper-proof or a regulatory record system."""
import csv
import io
import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta
from app.config import MST, RULE_VERSION

DB_PATH = os.environ.get("CANOPYGUARD_DB", os.path.join(os.path.dirname(__file__), "..", "data", "canopyguard.db"))
_lock = threading.RLock()  # one shared connection: serialize ALL access, reads included

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT);
CREATE TABLE IF NOT EXISTS areas (id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS records (
  id INTEGER PRIMARY KEY AUTOINCREMENT, recorded_at TEXT NOT NULL, scenario_time TEXT,
  kind TEXT NOT NULL, field_id TEXT, job_id TEXT, status TEXT, summary TEXT,
  rule_version TEXT, simulated INTEGER, payload TEXT);
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, field_id TEXT, job_id TEXT, rule TEXT, severity TEXT,
  message TEXT, first_seen TEXT, last_seen TEXT, occurrences INTEGER, active INTEGER,
  acknowledged_by TEXT, acknowledged_at TEXT, scenario_time TEXT);
"""


def _conn():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


_db = None


def db():
    global _db
    with _lock:
        if _db is None:
            _db = _conn()
            _db.executescript(SCHEMA)
    return _db


def now_iso():
    return datetime.now(MST).isoformat(timespec="seconds")


# ------------------------------------------------------------------ jobs
def default_jobs(scn):
    d0 = scn.day0
    at = lambda day, hh, mm=0: (d0 + timedelta(days=day, hours=hh, minutes=mm)).isoformat()
    return [
        {"id": "J-A", "field_id": "A", "reference": "PCA recommendation #DEMO-1042 (fictional)", "reference_type": "pca",
         "product_id": "demo_r", "earliest_start": at(0, 5), "preferred_start": at(0, 6), "latest_completion": at(0, 13),
         "priority": "medium", "unit_id": "U1", "orientation_deg": 0, "status": "open",
         "notes": "Treatment need set by the PCA; urgency is an input, not inferred."},
        {"id": "J-B", "field_id": "B", "reference": "Spray program, application 3 of 4 (fictional)", "reference_type": "schedule",
         "product_id": "demo_r", "earliest_start": at(0, 5), "preferred_start": at(0, 6, 30), "latest_completion": at(0, 10),
         "priority": "high", "unit_id": "U1", "orientation_deg": 0, "status": "open",
         "notes": "PCA asked for completion before 10:00."},
        {"id": "J-C", "field_id": "C", "reference": "PCA recommendation #DEMO-1047 (fictional)", "reference_type": "pca",
         "product_id": "demo_r", "earliest_start": at(0, 5), "preferred_start": at(0, 9), "latest_completion": at(1, 12),
         "priority": "normal", "unit_id": "U1", "orientation_deg": 0, "status": "open", "notes": ""},
        {"id": "J-D", "field_id": "D", "reference": "Grower request (fictional)", "reference_type": "pca",
         "product_id": "unknown", "earliest_start": at(0, 6), "preferred_start": at(0, 8), "latest_completion": at(1, 16),
         "priority": "normal", "unit_id": "U2", "orientation_deg": 0, "status": "open",
         "notes": "No paired-height sensor near this orchard."},
    ]


def seed(scn, force=False):
    with _lock:
        c = db()
        if force:
            c.execute("DELETE FROM jobs")
            c.execute("DELETE FROM areas")
            c.execute("DELETE FROM alerts")
        n = c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        if n == 0:
            for j in default_jobs(scn):
                c.execute("INSERT INTO jobs VALUES (?,?,?)", (j["id"], json.dumps(j), now_iso()))
        c.commit()


def _all(sql, args=()):
    with _lock:
        return db().execute(sql, args).fetchall()


def _one(sql, args=()):
    with _lock:
        return db().execute(sql, args).fetchone()


def list_jobs():
    return [json.loads(r["data"]) for r in _all("SELECT data FROM jobs ORDER BY rowid")]


def get_job(jid):
    r = _one("SELECT data FROM jobs WHERE id=?", (jid,))
    return json.loads(r["data"]) if r else None


def upsert_job(job):
    with _lock:
        db().execute("INSERT INTO jobs VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                     (job["id"], json.dumps(job), now_iso()))
        db().commit()


def delete_job(jid):
    with _lock:
        db().execute("DELETE FROM jobs WHERE id=?", (jid,))
        db().commit()


# ----------------------------------------------------------------- areas
def list_areas(kind=None):
    rows = [json.loads(r["data"]) for r in _all("SELECT data FROM areas ORDER BY rowid")]
    return [a for a in rows if kind is None or a.get("_type") == kind]


def add_area(a):
    with _lock:
        db().execute("INSERT OR REPLACE INTO areas VALUES (?,?)", (a["id"], json.dumps(a)))
        db().commit()


def delete_area(aid):
    with _lock:
        db().execute("DELETE FROM areas WHERE id=?", (aid,))
        db().commit()


# --------------------------------------------------------------- records
def record(kind, summary, payload=None, field_id=None, job_id=None, status=None, scenario_time=None, simulated=True):
    with _lock:
        cur = db().execute(
            "INSERT INTO records (recorded_at, scenario_time, kind, field_id, job_id, status, summary, rule_version, simulated, payload)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (now_iso(), scenario_time, kind, field_id, job_id, status, summary, RULE_VERSION, 1 if simulated else 0,
             json.dumps(payload, default=str) if payload is not None else None))
        db().commit()
        return cur.lastrowid


def list_records(limit=200, kind=None):
    q = "SELECT * FROM records" + (" WHERE kind=?" if kind else "") + " ORDER BY id DESC LIMIT ?"
    args = (kind, limit) if kind else (limit,)
    out = []
    for r in _all(q, args):
        d = dict(r)
        d["simulated"] = bool(d["simulated"])
        d["payload"] = json.loads(d["payload"]) if d["payload"] else None
        out.append(d)
    return out


def export_csv():
    buf = io.StringIO()
    w = csv.writer(buf)
    cols = ["id", "recorded_at", "scenario_time", "kind", "field_id", "job_id", "status", "summary", "rule_version", "simulated", "payload"]
    w.writerow(cols)
    for r in _all("SELECT * FROM records ORDER BY id"):
        w.writerow([r[c] for c in cols])
    return buf.getvalue()


# ---------------------------------------------------------------- alerts
def raise_alert(field_id, job_id, rule, severity, message, scenario_time):
    """Group persistent conditions: same field+rule while active -> one alert, occurrence count++.
    Returns (alert, is_new)."""
    with _lock:
        c = db()
        r = c.execute("SELECT * FROM alerts WHERE field_id=? AND rule=? AND active=1", (field_id, rule)).fetchone()
        if r:
            c.execute("UPDATE alerts SET last_seen=?, occurrences=occurrences+1, message=? WHERE id=?",
                      (scenario_time, message, r["id"]))
            c.commit()
            return dict(c.execute("SELECT * FROM alerts WHERE id=?", (r["id"],)).fetchone()), False
        cur = c.execute("INSERT INTO alerts (field_id, job_id, rule, severity, message, first_seen, last_seen, occurrences, active, scenario_time)"
                        " VALUES (?,?,?,?,?,?,?,1,1,?)", (field_id, job_id, rule, severity, message, scenario_time, scenario_time, scenario_time))
        c.commit()
        return dict(c.execute("SELECT * FROM alerts WHERE id=?", (cur.lastrowid,)).fetchone()), True


def clear_alerts(field_id, active_rules):
    with _lock:
        c = db()
        rows = c.execute("SELECT id, rule FROM alerts WHERE field_id=? AND active=1", (field_id,)).fetchall()
        cleared = [r["id"] for r in rows if r["rule"] not in active_rules]
        for i in cleared:
            c.execute("UPDATE alerts SET active=0 WHERE id=?", (i,))
        c.commit()
        return cleared


def list_alerts(active_only=False):
    q = "SELECT * FROM alerts" + (" WHERE active=1" if active_only else "") + " ORDER BY id DESC"
    return [dict(r) for r in _all(q)]


def ack_alert(aid, who):
    with _lock:
        c = db()
        c.execute("UPDATE alerts SET acknowledged_by=?, acknowledged_at=? WHERE id=?", (who, now_iso(), aid))
        c.commit()
        r = c.execute("SELECT * FROM alerts WHERE id=?", (aid,)).fetchone()
        return dict(r) if r else None


def reset_alerts():
    with _lock:
        db().execute("DELETE FROM alerts")
        db().commit()
