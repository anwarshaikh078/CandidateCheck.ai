import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from models.report_schema import CandidateReport


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "candidatecheck.db"


def init_db(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_name TEXT,
                target_role TEXT NOT NULL,
                risk_score INTEGER NOT NULL,
                risk_level TEXT NOT NULL,
                recommended_next_step TEXT NOT NULL,
                created_at TEXT NOT NULL,
                full_report_json TEXT NOT NULL
            )
            """
        )
        connection.commit()
    finally:
        connection.close()


def save_report(
    *,
    candidate_name: Optional[str],
    target_role: str,
    report: CandidateReport,
    db_path: Path = DB_PATH,
) -> int:
    init_db(db_path)
    payload = report.model_dump(mode="json")
    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.execute(
            """
            INSERT INTO reports (
                candidate_name,
                target_role,
                risk_score,
                risk_level,
                recommended_next_step,
                created_at,
                full_report_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate_name or "",
                target_role,
                report.risk_score,
                report.risk_level.value,
                report.recommended_next_step.value,
                datetime.now(timezone.utc).isoformat(),
                json.dumps(payload),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def fetch_reports(db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    init_db(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                id,
                candidate_name,
                target_role,
                risk_score,
                risk_level,
                recommended_next_step,
                created_at,
                full_report_json
            FROM reports
            ORDER BY datetime(created_at) DESC, id DESC
            """
        ).fetchall()
    finally:
        connection.close()

    reports = []
    for row in rows:
        item = dict(row)
        try:
            item["full_report"] = json.loads(item.pop("full_report_json"))
        except json.JSONDecodeError:
            item["full_report"] = {}
        reports.append(item)
    return reports
