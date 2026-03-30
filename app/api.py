from __future__ import annotations

import os
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException

from app.config import load_settings
from app.logging import configure_logging
from app.models.schemas import RunCreateRequest, RunResponse
from app.orchestration.graph import PipelineService


def create_app() -> FastAPI:
    config_path = os.getenv("ADP_CONFIG", "config/settings.example.yaml")
    base_dir = Path.cwd()
    settings = load_settings(config_path)
    configure_logging(settings.runtime.log_level)
    service = PipelineService(settings=settings, base_dir=base_dir)

    app = FastAPI(title="Autonomous Dev Pipeline", version="0.1.0")
    app.state.service = service

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/runs", response_model=RunResponse, status_code=202)
    def create_run(request: RunCreateRequest, background_tasks: BackgroundTasks) -> RunResponse:
        run_id = service.create_run(request)
        background_tasks.add_task(service.execute_run, run_id)
        return RunResponse(
            run_id=run_id,
            status="running",
            current_stage="INTAKE",
            message="Run accepted.",
            artifact_paths={},
        )

    @app.get("/runs/{run_id}", response_model=RunResponse)
    def get_run(run_id: str) -> RunResponse:
        run = service.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")

        artifacts = {entry["name"]: entry["path"] for entry in run["artifacts"]}
        state = run["state"]
        return RunResponse(
            run_id=run["run_id"],
            status=run["status"],
            current_stage=run["current_stage"],
            message=state.get("final_message", ""),
            artifact_paths=artifacts,
        )

    return app
