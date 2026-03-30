from __future__ import annotations

from typing import Any, TypedDict, cast

from pydantic import BaseModel, Field

from app.models.schemas import RequirementInput


class PipelineState(TypedDict, total=False):
    run_id: str
    status: str
    current_stage: str
    stage_history: list[str]
    repo_source: str
    workspace_path: str
    repo_path: str
    base_branch: str
    feature_branch: str | None
    requirement_input: dict[str, Any]
    task_spec: dict[str, Any]
    repo_inspection: dict[str, Any]
    plan: dict[str, Any]
    files_touched: list[str]
    commands_run: list[dict[str, Any]]
    verify_result: dict[str, Any]
    review: dict[str, Any]
    pr_payload: dict[str, Any]
    iteration: int
    fix_loops: int
    tool_calls: int
    artifacts: dict[str, str]
    errors: list[str]
    no_pr: bool
    dry_run: bool
    should_fix: bool
    final_message: str
    max_iterations_override: int | None


class PipelineStateSnapshot(BaseModel):
    run_id: str
    status: str = "running"
    current_stage: str = "INTAKE"
    stage_history: list[str] = Field(default_factory=list)
    repo_source: str
    workspace_path: str
    repo_path: str
    base_branch: str = "main"
    feature_branch: str | None = None
    requirement_input: dict[str, Any]
    task_spec: dict[str, Any] | None = None
    repo_inspection: dict[str, Any] | None = None
    plan: dict[str, Any] | None = None
    files_touched: list[str] = Field(default_factory=list)
    commands_run: list[dict[str, Any]] = Field(default_factory=list)
    verify_result: dict[str, Any] | None = None
    review: dict[str, Any] | None = None
    pr_payload: dict[str, Any] | None = None
    iteration: int = 0
    fix_loops: int = 0
    tool_calls: int = 0
    artifacts: dict[str, str] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    no_pr: bool = False
    dry_run: bool = False
    should_fix: bool = False
    final_message: str = ""
    max_iterations_override: int | None = None


def make_initial_state(
    *,
    run_id: str,
    requirement: RequirementInput,
    workspace_path: str,
    repo_path: str,
) -> PipelineState:
    snapshot = PipelineStateSnapshot(
        run_id=run_id,
        repo_source=requirement.repo,
        workspace_path=workspace_path,
        repo_path=repo_path,
        base_branch=requirement.base_branch,
        requirement_input=requirement.model_dump(mode="python"),
        no_pr=requirement.no_pr,
        dry_run=requirement.dry_run,
    )
    return cast(PipelineState, snapshot.model_dump(mode="python"))
