from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high", "critical"]


class RequirementInput(BaseModel):
    repo: str
    requirement_text: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    base_branch: str = "main"
    target_branch: str | None = None
    test_commands: list[str] | None = None
    lint_commands: list[str] | None = None
    build_commands: list[str] | None = None
    typecheck_commands: list[str] | None = None
    coding_conventions: str | None = None
    project_rules: list[str] = Field(default_factory=list)
    dry_run: bool = False
    no_pr: bool = False


class TaskSpec(BaseModel):
    normalized_requirement: str
    acceptance_criteria: list[str]
    assumptions: list[str] = Field(default_factory=list)
    completion_definition: list[str] = Field(default_factory=list)


class RepoInspection(BaseModel):
    project_types: list[str] = Field(default_factory=list)
    inferred_commands: dict[str, list[str]] = Field(default_factory=dict)
    repo_map: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class PlanStep(BaseModel):
    step_id: str
    description: str
    rationale: str
    impacted_files: list[str] = Field(default_factory=list)
    verification_commands: list[str] = Field(default_factory=list)
    completion_signal: str


class PlanOutput(BaseModel):
    summary: str
    impacted_files: list[str] = Field(default_factory=list)
    steps: list[PlanStep] = Field(default_factory=list)
    completion_criteria: list[str] = Field(default_factory=list)
    test_strategy: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class FileEdit(BaseModel):
    path: str
    action: Literal["create", "update"]
    content: str
    reason: str


class ImplementationOutput(BaseModel):
    summary: str
    edits: list[FileEdit] = Field(default_factory=list)
    commit_message: str = "feat: automated implementation"


class CommandExecution(BaseModel):
    command: str
    return_code: int
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    success: bool = False
    skipped: bool = False


class VerifyResult(BaseModel):
    commands: list[CommandExecution] = Field(default_factory=list)
    all_passed: bool
    failed_commands: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ReviewFinding(BaseModel):
    finding_id: str
    severity: Severity
    title: str
    description: str
    file_path: str | None = None
    line: int | None = None
    suggestion: str | None = None
    blocking: bool = False


class ReviewOutput(BaseModel):
    gate_pass: bool
    summary: str
    findings: list[ReviewFinding] = Field(default_factory=list)
    resolved_criteria: list[str] = Field(default_factory=list)
    residual_risks: list[str] = Field(default_factory=list)


class PRPayload(BaseModel):
    title: str
    body: str
    checklist: list[str] = Field(default_factory=list)
    change_summary: list[str] = Field(default_factory=list)
    test_evidence: list[str] = Field(default_factory=list)
    unresolved_risks: list[str] = Field(default_factory=list)
    gh_command: str | None = None


class RunCreateRequest(BaseModel):
    repo: str
    requirement: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    base_branch: str = "main"
    target_branch: str | None = None
    test_commands: list[str] | None = None
    lint_commands: list[str] | None = None
    build_commands: list[str] | None = None
    typecheck_commands: list[str] | None = None
    coding_conventions: str | None = None
    project_rules: list[str] = Field(default_factory=list)
    dry_run: bool = False
    no_pr: bool = False
    max_iterations: int | None = None

    def to_requirement_input(self) -> RequirementInput:
        return RequirementInput(
            repo=self.repo,
            requirement_text=self.requirement,
            acceptance_criteria=self.acceptance_criteria,
            base_branch=self.base_branch,
            target_branch=self.target_branch,
            test_commands=self.test_commands,
            lint_commands=self.lint_commands,
            build_commands=self.build_commands,
            typecheck_commands=self.typecheck_commands,
            coding_conventions=self.coding_conventions,
            project_rules=self.project_rules,
            dry_run=self.dry_run,
            no_pr=self.no_pr,
        )


class RunResponse(BaseModel):
    run_id: str
    status: str
    current_stage: str
    message: str | None = None
    artifact_paths: dict[str, str] = Field(default_factory=dict)
