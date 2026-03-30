from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from app.config import Settings
from app.llm.client import LLMClient
from app.models.schemas import RequirementInput, RunCreateRequest
from app.models.state import PipelineState, make_initial_state
from app.orchestration.nodes import PipelineContext, PipelineNodes
from app.runtime.workspace import WorkspaceManager
from app.storage.runs import RunStore


def build_graph(nodes: PipelineNodes) -> Any:
    graph = StateGraph(PipelineState)
    graph.add_node("intake", nodes.intake)
    graph.add_node("inspect", nodes.inspect)
    graph.add_node("plan", nodes.plan)
    graph.add_node("implement", nodes.implement)
    graph.add_node("verify", nodes.verify)
    graph.add_node("review", nodes.review)
    graph.add_node("fix_or_pr", nodes.fix_or_pr)
    graph.add_node("fix", nodes.fixer)
    graph.add_node("pr_writer", nodes.pr_writer)
    graph.add_node("done", nodes.done)

    graph.add_edge(START, "intake")
    graph.add_edge("intake", "inspect")
    graph.add_edge("inspect", "plan")
    graph.add_edge("plan", "implement")
    graph.add_edge("implement", "verify")
    graph.add_edge("verify", "review")
    graph.add_edge("review", "fix_or_pr")
    graph.add_conditional_edges(
        "fix_or_pr",
        nodes.route_after_fix_or_pr,
        {
            "fix": "fix",
            "pr_writer": "pr_writer",
            "done": "done",
        },
    )
    graph.add_edge("fix", "verify")
    graph.add_edge("pr_writer", "done")
    graph.add_edge("done", END)
    return graph.compile()


class PipelineService:
    def __init__(self, settings: Settings, base_dir: Path) -> None:
        self.settings = settings
        self.base_dir = base_dir
        self.workspace_manager = WorkspaceManager(
            root=settings.workspace_root(base_dir),
            keep_runs=settings.workspace.keep_runs,
        )
        self.run_store = RunStore(settings.db_path(base_dir))
        llm_client = LLMClient(
            base_url=settings.model.base_url,
            model_name=settings.model.model_name,
            api_key=settings.model.api_key,
            timeout_seconds=settings.model.timeout_seconds,
            max_retries=settings.model.max_retries,
        )
        self.nodes = PipelineNodes(
            PipelineContext(
                settings=settings,
                run_store=self.run_store,
                llm_client=llm_client,
                prompt_dir=base_dir / "prompts",
            )
        )
        self.graph = build_graph(self.nodes)

    def create_run(self, request: RunCreateRequest, run_id: str | None = None) -> str:
        resolved_run_id = run_id or uuid.uuid4().hex[:12]
        requirement = request.to_requirement_input()
        run_root = self.workspace_manager.create_run_root(resolved_run_id)
        repo_path = self.workspace_manager.clone_repo(
            repo_source=requirement.repo,
            run_root=run_root,
            base_branch=requirement.base_branch,
        )

        initial_state = make_initial_state(
            run_id=resolved_run_id,
            requirement=requirement,
            workspace_path=str(run_root),
            repo_path=str(repo_path),
        )
        initial_state["base_branch"] = requirement.base_branch
        if request.max_iterations is not None:
            initial_state["max_iterations_override"] = request.max_iterations

        state_payload = dict(initial_state)
        self.run_store.create_run(
            run_id=resolved_run_id,
            repo_source=requirement.repo,
            workspace_path=str(run_root),
            state=state_payload,
            status="running",
            current_stage="INTAKE",
        )
        return resolved_run_id

    def execute_run(self, run_id: str) -> dict[str, Any]:
        run = self.run_store.get_run(run_id)
        if run is None:
            raise ValueError(f"run not found: {run_id}")
        state = cast(dict[str, Any], dict(run["state"]))
        result = cast(dict[str, Any], self.graph.invoke(state))
        self.workspace_manager.cleanup_old_runs()
        return result

    def run(self, request: RunCreateRequest) -> dict[str, Any]:
        run_id = self.create_run(request)
        return self.execute_run(run_id)

    def resume(self, run_id: str) -> dict[str, Any]:
        run = self.run_store.get_run(run_id)
        if run is None:
            raise ValueError(f"run not found: {run_id}")
        state = cast(dict[str, Any], dict(run["state"]))
        if state.get("status") == "success":
            return state
        state["status"] = "running"
        state["resume_mode"] = True
        state["resume_from_stage"] = state.get("current_stage", "INTAKE")
        result = cast(dict[str, Any], self.graph.invoke(state))
        return result

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self.run_store.get_run(run_id)


def requirement_from_text(
    repo: str,
    requirement_text: str,
    base_branch: str = "main",
) -> RequirementInput:
    return RequirementInput(repo=repo, requirement_text=requirement_text, base_branch=base_branch)
