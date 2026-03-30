from __future__ import annotations

import subprocess
from pathlib import Path

from app.config import load_settings
from app.models.schemas import RunCreateRequest
from app.orchestration.graph import PipelineService
from app.orchestration.nodes import PipelineNodes


def _run(cmd: list[str], cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stdout}\n{result.stderr}")


def test_graph_smoke_dry_run(tmp_path: Path, monkeypatch) -> None:
    source_repo = tmp_path / "source-repo"
    source_repo.mkdir(parents=True, exist_ok=True)
    _run(["git", "init"], cwd=source_repo)
    _run(["git", "checkout", "-b", "main"], cwd=source_repo)
    _run(["git", "config", "user.email", "test@example.com"], cwd=source_repo)
    _run(["git", "config", "user.name", "Test User"], cwd=source_repo)
    (source_repo / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (source_repo / "reports.py").write_text(
        "def render_reports():\n    return []\n",
        encoding="utf-8",
    )
    _run(["git", "add", "-A"], cwd=source_repo)
    _run(["git", "commit", "-m", "initial"], cwd=source_repo)

    config_path = tmp_path / "settings.yaml"
    config_path.write_text(
        f"""
model:
  base_url: "http://127.0.0.1:9999/v1"
  model_name: "qwen3"
  api_key: ""
  timeout_seconds: 1
  max_retries: 1
workspace:
  root: "{(tmp_path / "workspace").as_posix()}"
  keep_runs: 5
limits:
  max_iterations: 4
  max_fix_loops: 2
  max_files_changed: 20
  max_lines_changed: 1000
  max_tool_calls: 200
commands:
  allowlist:
    - "^pytest(\\\\s|$)"
    - "^ruff(\\\\s|$)"
    - "^mypy(\\\\s|$)"
  defaults:
    test: ["pytest -q"]
    lint: []
    typecheck: []
    build: []
github:
  enabled: false
  auto_open_pr: false
sandbox:
  docker_enabled: false
  image: "python:3.11-slim"
runtime:
  dry_run: true
  explain_mode: true
""".strip(),
        encoding="utf-8",
    )

    def fake_llm_json(self, *, prompt_name, user_payload, schema, fallback):  # type: ignore[no-untyped-def]
        _ = prompt_name, user_payload, schema
        return fallback()

    monkeypatch.setattr(PipelineNodes, "_llm_json", fake_llm_json)

    settings = load_settings(config_path)
    service = PipelineService(settings=settings, base_dir=Path.cwd())
    result = service.run(
        RunCreateRequest(
            repo=str(source_repo),
            requirement=(
                "As a user, I want CSV export on the reports page so that I can "
                "download report data for offline analysis."
            ),
            acceptance_criteria=[
                "Add Export CSV button on reports page",
                "Download includes current table filters",
            ],
            base_branch="main",
            dry_run=True,
            no_pr=True,
        )
    )

    assert result["status"] == "success"
    assert result["current_stage"] == "DONE"
    assert "pr_payload" in result
    assert isinstance(result.get("artifacts", {}), dict)
