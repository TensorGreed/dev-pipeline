from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.storage.runs import RunStore


class ArtifactRecorder:
    def __init__(self, run_store: RunStore) -> None:
        self.run_store = run_store

    def record_artifact(
        self,
        *,
        run_id: str,
        artifacts_dir: Path,
        name: str,
        content: str | dict[str, Any] | list[Any],
    ) -> str:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        safe_name = self._sanitize_name(name)
        file_path = artifacts_dir / safe_name

        if isinstance(content, str):
            payload = content
        else:
            payload = json.dumps(content, indent=2, ensure_ascii=True)

        file_path.write_text(payload, encoding="utf-8")
        self.run_store.add_artifact(run_id=run_id, name=safe_name, path=str(file_path))
        return str(file_path)

    def _sanitize_name(self, name: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
        return cleaned or "artifact.txt"
