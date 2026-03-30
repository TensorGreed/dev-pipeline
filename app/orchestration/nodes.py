from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import Settings
from app.llm.client import LLMClient, LLMError
from app.models.schemas import (
    CommandExecution,
    ImplementationOutput,
    PlanOutput,
    PlanStep,
    PRPayload,
    RepoInspection,
    RequirementInput,
    ReviewFinding,
    ReviewOutput,
    TaskSpec,
    VerifyResult,
)
from app.runtime.limits import LimitTracker, LimitViolation
from app.runtime.sandbox import SandboxExecutor
from app.storage.runs import RunStore
from app.tools.artifacts import ArtifactRecorder
from app.tools.command_runner import CommandNotAllowed, CommandRunner
from app.tools.git_tools import GitToolError
from app.tools.repo_inspector import RepoInspector
from app.tools.toolbox import PipelineToolbox

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PipelineContext:
    settings: Settings
    run_store: RunStore
    llm_client: LLMClient
    prompt_dir: Path


class PipelineNodes:
    def __init__(self, context: PipelineContext) -> None:
        self.context = context
        self.limit_tracker = LimitTracker(context.settings.limits)

    def intake(self, state: dict[str, Any]) -> dict[str, Any]:
        def work(next_state: dict[str, Any]) -> None:
            requirement = RequirementInput.model_validate(next_state["requirement_input"])
            user_payload = {
                "requirement": requirement.requirement_text,
                "acceptance_criteria": requirement.acceptance_criteria,
                "project_rules": requirement.project_rules,
                "coding_conventions": requirement.coding_conventions,
            }
            spec = self._llm_json(
                prompt_name="intake",
                user_payload=user_payload,
                schema=TaskSpec,
                fallback=lambda: self._fallback_task_spec(requirement),
            )
            next_state["task_spec"] = spec.model_dump(mode="python")
            self._record_artifact(next_state, "intake_task_spec.json", next_state["task_spec"])

        return self._run_stage(state, "INTAKE", work)

    def inspect(self, state: dict[str, Any]) -> dict[str, Any]:
        def work(next_state: dict[str, Any]) -> None:
            requirement = RequirementInput.model_validate(next_state["requirement_input"])
            inspector = RepoInspector(Path(next_state["repo_path"]))
            inspection = inspector.inspect(requirement)

            # Fill any missing command categories with configured defaults.
            defaults = self.context.settings.commands.defaults
            inferred = inspection.inferred_commands
            for key, fallback in {
                "test": defaults.test,
                "lint": defaults.lint,
                "typecheck": defaults.typecheck,
                "build": defaults.build,
            }.items():
                if not inferred.get(key):
                    inferred[key] = list(fallback)

            next_state["repo_inspection"] = inspection.model_dump(mode="python")
            next_state["verification_commands"] = inferred
            self._record_artifact(next_state, "repo_inspection.json", next_state["repo_inspection"])

        return self._run_stage(state, "INSPECT", work)

    def plan(self, state: dict[str, Any]) -> dict[str, Any]:
        def work(next_state: dict[str, Any]) -> None:
            requirement = RequirementInput.model_validate(next_state["requirement_input"])
            task_spec = TaskSpec.model_validate(next_state["task_spec"])
            inspection = RepoInspection.model_validate(next_state["repo_inspection"])

            user_payload = {
                "task_spec": task_spec.model_dump(mode="python"),
                "repo_map": inspection.repo_map[:300],
                "project_types": inspection.project_types,
                "inferred_commands": inspection.inferred_commands,
            }
            plan_output = self._llm_json(
                prompt_name="planner",
                user_payload=user_payload,
                schema=PlanOutput,
                fallback=lambda: self._fallback_plan(requirement, task_spec, inspection),
            )
            next_state["plan"] = plan_output.model_dump(mode="python")
            self._record_artifact(next_state, "plan.json", next_state["plan"])

        return self._run_stage(state, "PLAN", work)

    def implement(self, state: dict[str, Any]) -> dict[str, Any]:
        def work(next_state: dict[str, Any]) -> None:
            requirement = RequirementInput.model_validate(next_state["requirement_input"])
            plan = PlanOutput.model_validate(next_state["plan"])
            toolbox = self._toolbox(next_state)

            iteration = int(next_state.get("iteration", 0)) + 1
            next_state["iteration"] = iteration
            self.limit_tracker.assert_iteration(iteration)

            if not next_state.get("feature_branch"):
                feature_branch = requirement.target_branch or f"autobot/{next_state['run_id'][:8]}"
                try:
                    toolbox.git_checkout_new_branch(
                        base_branch=requirement.base_branch,
                        feature_branch=feature_branch,
                    )
                except GitToolError:
                    current_branch = toolbox.git.current_branch()
                    toolbox.git_checkout_new_branch(
                        base_branch=current_branch,
                        feature_branch=feature_branch,
                    )
                next_state["feature_branch"] = feature_branch

            context_files = self._load_file_context(toolbox, plan.impacted_files[:8])
            user_payload = {
                "task_spec": next_state["task_spec"],
                "plan": plan.model_dump(mode="python"),
                "context_files": context_files,
                "repo_path": next_state["repo_path"],
            }
            implementation = self._llm_json(
                prompt_name="implementer",
                user_payload=user_payload,
                schema=ImplementationOutput,
                fallback=lambda: ImplementationOutput(
                    summary="No implementation generated.",
                    edits=[],
                    commit_message="feat: baseline automated implementation",
                ),
            )

            touched = self._apply_edits(next_state, toolbox, implementation)
            if touched:
                next_state["files_touched"] = sorted(
                    set(next_state.get("files_touched", []) + touched)
                )
            self._record_artifact(
                next_state,
                f"implementation_iter_{iteration}.json",
                implementation.model_dump(mode="python"),
            )
            self._increment_tool_calls(next_state, 1 + len(implementation.edits))

        return self._run_stage(state, "IMPLEMENT", work)

    def verify(self, state: dict[str, Any]) -> dict[str, Any]:
        def work(next_state: dict[str, Any]) -> None:
            toolbox = self._toolbox(next_state)
            verification_commands = dict(next_state.get("verification_commands", {}))
            ordered_commands = (
                list(verification_commands.get("test", []))
                + list(verification_commands.get("lint", []))
                + list(verification_commands.get("typecheck", []))
                + list(verification_commands.get("build", []))
            )

            executions: list[CommandExecution] = []
            if next_state.get("dry_run"):
                for command in ordered_commands:
                    executions.append(
                        CommandExecution(
                            command=command,
                            return_code=0,
                            stdout="dry-run: command not executed",
                            success=True,
                            skipped=True,
                        )
                    )
            else:
                for command in ordered_commands:
                    try:
                        executions.append(toolbox.run_command(command))
                    except CommandNotAllowed as exc:
                        executions.append(
                            CommandExecution(
                                command=command,
                                return_code=126,
                                stderr=str(exc),
                                success=False,
                            )
                        )

            all_passed = all(execution.success for execution in executions) if executions else True
            failed_commands = [
                execution.command for execution in executions if not execution.success
            ]
            verify_result = VerifyResult(
                commands=executions,
                all_passed=all_passed,
                failed_commands=failed_commands,
                notes=[],
            )
            next_state["verify_result"] = verify_result.model_dump(mode="python")
            next_state["commands_run"] = next_state.get("commands_run", []) + [
                execution.model_dump(mode="python") for execution in executions
            ]

            self.limit_tracker.assert_diff(Path(next_state["repo_path"]))
            self._increment_tool_calls(next_state, len(executions))
            self._record_artifact(next_state, "verify_result.json", next_state["verify_result"])

        return self._run_stage(state, "VERIFY", work)

    def review(self, state: dict[str, Any]) -> dict[str, Any]:
        def work(next_state: dict[str, Any]) -> None:
            toolbox = self._toolbox(next_state)
            base_branch = next_state.get("base_branch", "main")
            try:
                diff = toolbox.git_diff(refspec=f"{base_branch}...HEAD")
            except GitToolError:
                diff = toolbox.git_diff()
            diff = diff[:50000]

            verify_result = VerifyResult.model_validate(
                next_state.get("verify_result", {"all_passed": True})
            )
            user_payload = {
                "task_spec": next_state.get("task_spec", {}),
                "verify_result": verify_result.model_dump(mode="python"),
                "diff": diff,
            }
            review = self._llm_json(
                prompt_name="reviewer",
                user_payload=user_payload,
                schema=ReviewOutput,
                fallback=lambda: self._fallback_review(verify_result),
            )

            normalized_findings: list[ReviewFinding] = []
            for finding in review.findings:
                if finding.severity in {"high", "critical"}:
                    finding.blocking = True
                normalized_findings.append(finding)
            normalized_review = ReviewOutput(
                gate_pass=review.gate_pass,
                summary=review.summary,
                findings=normalized_findings,
                resolved_criteria=review.resolved_criteria,
                residual_risks=review.residual_risks,
            )
            next_state["review"] = normalized_review.model_dump(mode="python")

            self._increment_tool_calls(next_state, 1)
            self._record_artifact(next_state, "review.json", next_state["review"])

        return self._run_stage(state, "REVIEW", work)

    def fix_or_pr(self, state: dict[str, Any]) -> dict[str, Any]:
        def work(next_state: dict[str, Any]) -> None:
            verify_result = VerifyResult.model_validate(
                next_state.get("verify_result", {"all_passed": True})
            )
            review = ReviewOutput.model_validate(
                next_state.get("review", {"gate_pass": True, "summary": "No review output."})
            )

            blocking = any(
                finding.blocking or finding.severity in {"high", "critical"}
                for finding in review.findings
            )
            need_fix = (not verify_result.all_passed) or (not review.gate_pass) or blocking
            next_state["should_fix"] = False

            if need_fix:
                current_fix_loops = int(next_state.get("fix_loops", 0))
                if current_fix_loops >= self.context.settings.limits.max_fix_loops:
                    next_state["status"] = "failed"
                    next_state["final_message"] = "Quality gates did not pass before max fix loops."
                    next_state.setdefault("errors", []).append(
                        "Exceeded max fix loops with unresolved quality gates."
                    )
                else:
                    next_state["should_fix"] = True

            self._record_artifact(
                next_state,
                "fix_or_pr_decision.json",
                {
                    "need_fix": need_fix,
                    "should_fix": next_state.get("should_fix", False),
                    "fix_loops": next_state.get("fix_loops", 0),
                    "status": next_state.get("status", "running"),
                },
            )

        return self._run_stage(state, "FIX_OR_PR", work)

    def fixer(self, state: dict[str, Any]) -> dict[str, Any]:
        def work(next_state: dict[str, Any]) -> None:
            toolbox = self._toolbox(next_state)
            plan = PlanOutput.model_validate(next_state["plan"])
            review = ReviewOutput.model_validate(next_state["review"])
            verify = VerifyResult.model_validate(next_state["verify_result"])

            fix_loops = int(next_state.get("fix_loops", 0)) + 1
            iteration = int(next_state.get("iteration", 0)) + 1
            next_state["fix_loops"] = fix_loops
            next_state["iteration"] = iteration
            self.limit_tracker.assert_fix_loops(fix_loops)
            self.limit_tracker.assert_iteration(iteration)

            relevant_files: list[str] = []
            for finding in review.findings:
                if finding.file_path:
                    relevant_files.append(finding.file_path)
            relevant_files.extend(plan.impacted_files)
            deduped_files = list(dict.fromkeys(relevant_files))[:8]
            context_files = self._load_file_context(toolbox, deduped_files)

            user_payload = {
                "review_findings": review.model_dump(mode="python"),
                "verify_result": verify.model_dump(mode="python"),
                "context_files": context_files,
            }
            fix_output = self._llm_json(
                prompt_name="fixer",
                user_payload=user_payload,
                schema=ImplementationOutput,
                fallback=lambda: ImplementationOutput(
                    summary="No fixes generated.",
                    edits=[],
                    commit_message=f"fix: address quality findings loop {fix_loops}",
                ),
            )

            touched = self._apply_edits(next_state, toolbox, fix_output)
            if touched:
                next_state["files_touched"] = sorted(
                    set(next_state.get("files_touched", []) + touched)
                )
            self._increment_tool_calls(next_state, 1 + len(fix_output.edits))
            self._record_artifact(
                next_state,
                f"fix_iter_{fix_loops}.json",
                fix_output.model_dump(mode="python"),
            )

        return self._run_stage(state, "FIX", work)

    def pr_writer(self, state: dict[str, Any]) -> dict[str, Any]:
        def work(next_state: dict[str, Any]) -> None:
            toolbox = self._toolbox(next_state)
            verify = VerifyResult.model_validate(next_state["verify_result"])
            review = ReviewOutput.model_validate(next_state["review"])

            if not verify.all_passed or not review.gate_pass:
                next_state["status"] = "failed"
                next_state["final_message"] = "Cannot draft PR while quality gates fail."
                return

            base_branch = next_state.get("base_branch", "main")
            feature_branch = next_state.get("feature_branch", "")
            commit_log = toolbox.git.commit_log_since(base_branch)

            user_payload = {
                "requirement": next_state["task_spec"],
                "files_touched": next_state.get("files_touched", []),
                "verify_result": next_state["verify_result"],
                "review": next_state["review"],
                "commit_log": commit_log,
            }
            payload = self._llm_json(
                prompt_name="pr_writer",
                user_payload=user_payload,
                schema=PRPayload,
                fallback=lambda: self._fallback_pr_payload(next_state, verify, review),
            )

            body_markdown = toolbox.generate_pr_body(payload)
            artifacts_dir = Path(next_state["workspace_path"]) / "artifacts"
            pr_body_path = Path(
                toolbox.record_artifact(
                    run_id=next_state["run_id"],
                    artifacts_dir=artifacts_dir,
                    name="pr_body.md",
                    content=body_markdown,
                )
            )

            if not next_state.get("no_pr") and self.context.settings.github.enabled:
                payload.gh_command = toolbox.gh.build_gh_command(
                    title=payload.title,
                    body_file=str(pr_body_path),
                    base=base_branch,
                    head=feature_branch,
                )
                if not next_state.get("dry_run"):
                    try:
                        toolbox.git_push(
                            remote=self.context.settings.github.remote,
                            branch=feature_branch,
                        )
                    except GitToolError as exc:
                        next_state.setdefault("errors", []).append(str(exc))
                    if self.context.settings.github.auto_open_pr:
                        create_result = toolbox.create_pr_with_gh(
                            payload=payload,
                            base_branch=base_branch,
                            head_branch=feature_branch,
                            body_file_path=pr_body_path,
                        )
                        self._record_artifact(
                            next_state,
                            "gh_pr_create_result.json",
                            create_result.model_dump(mode="python"),
                        )

            next_state["pr_payload"] = payload.model_dump(mode="python")
            next_state["status"] = "success"
            next_state["final_message"] = (
                "PR payload generated. Human review required before merge."
            )
            self._record_artifact(next_state, "pr_payload.json", next_state["pr_payload"])

        return self._run_stage(state, "PR_WRITER", work)

    def done(self, state: dict[str, Any]) -> dict[str, Any]:
        def work(next_state: dict[str, Any]) -> None:
            if next_state.get("status", "running") == "running":
                next_state["status"] = "success"
            if not next_state.get("final_message"):
                next_state["final_message"] = "Run finished."

        return self._run_stage(state, "DONE", work)

    @staticmethod
    def route_after_fix_or_pr(state: dict[str, Any]) -> str:
        if state.get("status") == "failed":
            return "done"
        if state.get("should_fix"):
            return "fix"
        return "pr_writer"

    def _run_stage(
        self,
        state: dict[str, Any],
        stage_name: str,
        work: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        if self._should_skip_stage(state, stage_name):
            return state

        next_state = dict(state)
        next_state.setdefault("status", "running")
        next_state.setdefault("errors", [])
        next_state.setdefault("tool_calls", 0)

        history = list(next_state.get("stage_history", []))
        history.append(stage_name)
        next_state["stage_history"] = history
        next_state["current_stage"] = stage_name
        if next_state.get("resume_mode") and next_state.get("resume_from_stage") == stage_name:
            next_state["resume_mode"] = False
            next_state["resume_from_stage"] = None

        try:
            work(next_state)
            self.limit_tracker.assert_tool_calls(int(next_state.get("tool_calls", 0)))
        except (LimitViolation, ValueError, KeyError, RuntimeError, GitToolError) as exc:
            logger.exception("Stage %s failed: %s", stage_name, exc)
            next_state["status"] = "failed"
            next_state["final_message"] = f"Stage {stage_name} failed"
            errors = list(next_state.get("errors", []))
            errors.append(str(exc))
            next_state["errors"] = errors

        self._persist(next_state)
        return next_state

    def _should_skip_stage(self, state: dict[str, Any], stage_name: str) -> bool:
        if not state.get("resume_mode"):
            return False
        completed = set(state.get("stage_history", []))
        resume_from = state.get("resume_from_stage")
        return stage_name in completed and stage_name != resume_from

    def _persist(self, state: dict[str, Any]) -> None:
        self.context.run_store.update_run(
            run_id=state["run_id"],
            status=state.get("status", "running"),
            current_stage=state.get("current_stage", "UNKNOWN"),
            state=state,
        )

    def _record_artifact(
        self,
        state: dict[str, Any],
        name: str,
        content: str | dict[str, Any] | list[Any],
    ) -> None:
        toolbox = self._toolbox(state)
        artifacts_dir = Path(state["workspace_path"]) / "artifacts"
        path = toolbox.record_artifact(
            run_id=state["run_id"],
            artifacts_dir=artifacts_dir,
            name=name,
            content=content,
        )
        artifacts = dict(state.get("artifacts", {}))
        artifacts[name] = path
        state["artifacts"] = artifacts

    def _toolbox(self, state: dict[str, Any]) -> PipelineToolbox:
        repo_path = Path(state["repo_path"])
        command_runner = CommandRunner(
            allowlist_patterns=self.context.settings.commands.allowlist,
            sandbox=SandboxExecutor(self.context.settings.sandbox),
        )
        return PipelineToolbox(
            repo_path=repo_path,
            command_runner=command_runner,
            artifact_recorder=ArtifactRecorder(self.context.run_store),
        )

    def _llm_json(
        self,
        *,
        prompt_name: str,
        user_payload: dict[str, Any],
        schema: type[Any],
        fallback: Callable[[], Any],
    ) -> Any:
        system_prompt = self._load_prompt(prompt_name)
        user_prompt = json.dumps(user_payload, indent=2, ensure_ascii=True)
        try:
            return self.context.llm_client.chat_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
            )
        except LLMError as exc:
            logger.warning("LLM call failed for %s, using fallback: %s", prompt_name, exc)
            return fallback()

    def _load_prompt(self, prompt_name: str) -> str:
        path = self.context.prompt_dir / f"{prompt_name}.md"
        return path.read_text(encoding="utf-8")

    def _increment_tool_calls(self, state: dict[str, Any], count: int) -> None:
        state["tool_calls"] = int(state.get("tool_calls", 0)) + count

    def _load_file_context(
        self,
        toolbox: PipelineToolbox,
        candidate_paths: list[str],
    ) -> dict[str, str]:
        context_files: dict[str, str] = {}
        for path in candidate_paths:
            if not path:
                continue
            try:
                context_files[path] = toolbox.read_file(path)[:12000]
            except RuntimeError:
                continue
        return context_files

    def _apply_edits(
        self,
        state: dict[str, Any],
        toolbox: PipelineToolbox,
        implementation: ImplementationOutput,
    ) -> list[str]:
        touched: list[str] = []
        if state.get("dry_run"):
            return touched

        for edit in implementation.edits:
            normalized = edit.path.strip().replace("\\", "/")
            if normalized.startswith("/") or normalized.startswith("../"):
                continue
            if normalized.startswith(".git/"):
                continue
            toolbox.write_file(normalized, edit.content)
            touched.append(normalized)

        if touched:
            commit_message = implementation.commit_message.strip() or "feat: automated code changes"
            commit_sha = toolbox.git_commit(message=commit_message)
            if commit_sha:
                commit_shas = list(state.get("commit_shas", []))
                commit_shas.append(commit_sha)
                state["commit_shas"] = commit_shas
        return touched

    @staticmethod
    def _fallback_task_spec(requirement: RequirementInput) -> TaskSpec:
        acceptance = requirement.acceptance_criteria or _extract_bullets(
            requirement.requirement_text
        )
        if not acceptance:
            acceptance = [requirement.requirement_text.strip()]
        return TaskSpec(
            normalized_requirement=requirement.requirement_text.strip(),
            acceptance_criteria=acceptance,
            assumptions=[],
            completion_definition=acceptance,
        )

    @staticmethod
    def _fallback_plan(
        requirement: RequirementInput,
        task_spec: TaskSpec,
        inspection: RepoInspection,
    ) -> PlanOutput:
        impacted = _heuristic_impacted_files(
            requirement.requirement_text,
            inspection.repo_map,
            max_items=8,
        )
        verification = (
            inspection.inferred_commands.get("test", [])
            + inspection.inferred_commands.get("lint", [])
            + inspection.inferred_commands.get("typecheck", [])
        )
        return PlanOutput(
            summary="Fallback deterministic plan generated without model output.",
            impacted_files=impacted,
            steps=[
                PlanStep(
                    step_id="P1",
                    description="Update implementation files in scoped modules.",
                    rationale="Apply requirement behavior with minimal blast radius.",
                    impacted_files=impacted,
                    verification_commands=verification[:3],
                    completion_signal="Code compiles and requirement path is implemented.",
                ),
                PlanStep(
                    step_id="P2",
                    description="Add or update tests for acceptance criteria coverage.",
                    rationale="Prevent regressions and validate behavior.",
                    impacted_files=[path for path in impacted if "test" in path.lower()],
                    verification_commands=inspection.inferred_commands.get("test", []),
                    completion_signal="Relevant test coverage exists for new behavior.",
                ),
            ],
            completion_criteria=task_spec.completion_definition or task_spec.acceptance_criteria,
            test_strategy=inspection.inferred_commands.get("test", []),
            risks=["Model unavailable during planning; plan generated with heuristics."],
        )

    @staticmethod
    def _fallback_review(verify_result: VerifyResult) -> ReviewOutput:
        findings: list[ReviewFinding] = []
        for idx, failed_command in enumerate(verify_result.failed_commands, start=1):
            findings.append(
                ReviewFinding(
                    finding_id=f"VERIFY-{idx}",
                    severity="high",
                    title="Verification command failed",
                    description=f"Command failed during quality gates: {failed_command}",
                    suggestion="Address failing command output and rerun verification.",
                    blocking=True,
                )
            )
        gate_pass = verify_result.all_passed
        summary = "Verification passed." if gate_pass else "Verification failed."
        return ReviewOutput(
            gate_pass=gate_pass,
            summary=summary,
            findings=findings,
            resolved_criteria=[],
            residual_risks=[] if gate_pass else ["One or more quality gates are failing."],
        )

    @staticmethod
    def _fallback_pr_payload(
        state: dict[str, Any],
        verify: VerifyResult,
        review: ReviewOutput,
    ) -> PRPayload:
        task_spec = TaskSpec.model_validate(state["task_spec"])
        title = _trim_title(task_spec.normalized_requirement)
        test_evidence = [
            f"{execution.command}: {'PASS' if execution.success else 'FAIL'}"
            for execution in verify.commands
        ]
        return PRPayload(
            title=title,
            body=task_spec.normalized_requirement,
            checklist=[
                "Human reviewer validated requirement coverage",
                "Human reviewer validated regression risk",
                "Human reviewer approved test evidence",
            ],
            change_summary=[
                f"Touched files: {', '.join(state.get('files_touched', [])) or 'none'}"
            ],
            test_evidence=test_evidence,
            unresolved_risks=review.residual_risks,
            gh_command=None,
        )


def _extract_bullets(text: str) -> list[str]:
    bullets: list[str] = []
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned.startswith("- ") or cleaned.startswith("* "):
            bullets.append(cleaned[2:].strip())
    return bullets


def _heuristic_impacted_files(
    requirement_text: str,
    repo_map: list[str],
    max_items: int,
) -> list[str]:
    tokens = {token.lower() for token in re.findall(r"[A-Za-z0-9_]{4,}", requirement_text)}
    scored: list[tuple[int, str]] = []
    for path in repo_map:
        lowered = path.lower()
        score = sum(1 for token in tokens if token in lowered)
        if score > 0:
            scored.append((score, path))
    scored.sort(key=lambda item: (-item[0], item[1]))
    impacted = [path for _, path in scored[:max_items]]
    if not impacted:
        impacted = repo_map[:max_items]
    return impacted


def _trim_title(text: str, max_length: int = 72) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."
