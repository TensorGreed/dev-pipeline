from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.config import apply_cli_overrides, load_settings
from app.logging import configure_logging
from app.models.schemas import RunCreateRequest
from app.orchestration.graph import PipelineService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Autonomous Dev Pipeline CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Create and execute a run")
    run_parser.add_argument("--repo", required=True, help="Local repository path or git URL")
    run_parser.add_argument("--requirement-file", help="Path to requirement markdown/text file")
    run_parser.add_argument("--requirement", help="Requirement text")
    run_parser.add_argument("--base-branch", default="main")
    run_parser.add_argument("--target-branch", default=None)
    run_parser.add_argument("--config", default="config/settings.example.yaml")
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--no-pr", action="store_true")
    run_parser.add_argument("--max-iterations", type=int, default=None)
    run_parser.add_argument("--test-command", action="append", default=None)
    run_parser.add_argument("--lint-command", action="append", default=None)
    run_parser.add_argument("--build-command", action="append", default=None)
    run_parser.add_argument("--typecheck-command", action="append", default=None)

    status_parser = subparsers.add_parser("status", help="Read run status by id")
    status_parser.add_argument("--run-id", required=True)
    status_parser.add_argument("--config", default="config/settings.example.yaml")

    resume_parser = subparsers.add_parser("resume", help="Resume an existing run")
    resume_parser.add_argument("--run-id", required=True)
    resume_parser.add_argument("--config", default="config/settings.example.yaml")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    cwd = Path.cwd()

    if args.command == "run":
        _run_command(args, cwd)
    elif args.command == "status":
        _status_command(args, cwd)
    elif args.command == "resume":
        _resume_command(args, cwd)


def _run_command(args: argparse.Namespace, cwd: Path) -> None:
    requirement_text, acceptance = _resolve_requirement(args.requirement, args.requirement_file)
    if not requirement_text.strip():
        raise ValueError(
            "requirement text is required "
            "(either --requirement or --requirement-file)"
        )

    settings = load_settings(args.config)
    settings = apply_cli_overrides(
        settings,
        max_iterations=args.max_iterations,
        dry_run=args.dry_run or settings.runtime.dry_run,
        test_commands=args.test_command,
        lint_commands=args.lint_command,
        build_commands=args.build_command,
    )
    configure_logging(settings.runtime.log_level)

    service = PipelineService(settings=settings, base_dir=cwd)
    request = RunCreateRequest(
        repo=args.repo,
        requirement=requirement_text,
        acceptance_criteria=acceptance,
        base_branch=args.base_branch,
        target_branch=args.target_branch,
        test_commands=args.test_command,
        lint_commands=args.lint_command,
        build_commands=args.build_command,
        typecheck_commands=args.typecheck_command,
        dry_run=args.dry_run or settings.runtime.dry_run,
        no_pr=args.no_pr,
        max_iterations=args.max_iterations,
    )
    result = service.run(request)
    _print_run_summary(result)


def _status_command(args: argparse.Namespace, cwd: Path) -> None:
    settings = load_settings(args.config)
    configure_logging(settings.runtime.log_level)
    service = PipelineService(settings=settings, base_dir=cwd)
    run = service.get_run(args.run_id)
    if run is None:
        print(json.dumps({"error": f"run not found: {args.run_id}"}, indent=2))
        return
    print(
        json.dumps(
            {
                "run_id": run["run_id"],
                "status": run["status"],
                "current_stage": run["current_stage"],
                "updated_at": run["updated_at"],
                "artifact_count": len(run["artifacts"]),
            },
            indent=2,
        )
    )


def _resume_command(args: argparse.Namespace, cwd: Path) -> None:
    settings = load_settings(args.config)
    configure_logging(settings.runtime.log_level)
    service = PipelineService(settings=settings, base_dir=cwd)
    result = service.resume(args.run_id)
    _print_run_summary(result)


def _resolve_requirement(
    requirement: str | None,
    requirement_file: str | None,
) -> tuple[str, list[str]]:
    if requirement_file:
        text = Path(requirement_file).read_text(encoding="utf-8")
        return text, _extract_acceptance_criteria(text)
    return requirement or "", []


def _extract_acceptance_criteria(requirement_text: str) -> list[str]:
    criteria: list[str] = []
    in_section = False
    for raw_line in requirement_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower().startswith("acceptance criteria"):
            in_section = True
            continue
        if in_section and (line.startswith("- ") or line.startswith("* ")):
            criteria.append(line[2:].strip())
        elif in_section and not line.startswith("-") and not line.startswith("*"):
            # Stop once the bullet list ends.
            break
    return criteria


def _print_run_summary(state: dict[str, Any]) -> None:
    summary = {
        "run_id": state.get("run_id"),
        "status": state.get("status"),
        "current_stage": state.get("current_stage"),
        "feature_branch": state.get("feature_branch"),
        "files_touched": state.get("files_touched", []),
        "artifacts": state.get("artifacts", {}),
        "final_message": state.get("final_message", ""),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
