from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.db import get_connection, init_db


class RunStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        init_db(db_path)

    def create_run(
        self,
        *,
        run_id: str,
        repo_source: str,
        workspace_path: str,
        state: dict[str, Any],
        status: str = "running",
        current_stage: str = "INTAKE",
    ) -> None:
        now = _utc_now()
        payload = json.dumps(state, ensure_ascii=True)
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    run_id, status, current_stage, repo_source, workspace_path,
                    state_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, status, current_stage, repo_source, workspace_path, payload, now, now),
            )
            conn.commit()

    def update_run(
        self,
        *,
        run_id: str,
        status: str,
        current_stage: str,
        state: dict[str, Any],
    ) -> None:
        now = _utc_now()
        payload = json.dumps(state, ensure_ascii=True)
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = ?, current_stage = ?, state_json = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (status, current_stage, payload, now, run_id),
            )
            conn.commit()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with get_connection(self.db_path) as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None

        result = dict(row)
        result["state"] = json.loads(result["state_json"])
        result["artifacts"] = self.list_artifacts(run_id)
        return result

    def add_artifact(self, *, run_id: str, name: str, path: str) -> None:
        now = _utc_now()
        with get_connection(self.db_path) as conn:
            conn.execute(
                "INSERT INTO artifacts (run_id, name, path, created_at) VALUES (?, ?, ?, ?)",
                (run_id, name, path, now),
            )
            conn.commit()

    def list_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT name, path, created_at FROM artifacts WHERE run_id = ? ORDER BY id",
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
