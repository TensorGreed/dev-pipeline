from __future__ import annotations

import json
from pathlib import Path

from app.models.schemas import RepoInspection, RequirementInput


class RepoInspector:
    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path

    def inspect(self, requirement: RequirementInput) -> RepoInspection:
        repo_map = self._build_repo_map()
        project_types = self._detect_project_types(repo_map)
        commands = self._infer_commands(project_types)
        assumptions: list[str] = []

        if not project_types:
            assumptions.append(
                "Project type inference was uncertain; using configured default commands."
            )

        if requirement.test_commands is not None:
            commands["test"] = requirement.test_commands
        if requirement.lint_commands is not None:
            commands["lint"] = requirement.lint_commands
        if requirement.typecheck_commands is not None:
            commands["typecheck"] = requirement.typecheck_commands
        if requirement.build_commands is not None:
            commands["build"] = requirement.build_commands

        return RepoInspection(
            project_types=project_types,
            inferred_commands=commands,
            repo_map=repo_map,
            assumptions=assumptions,
        )

    def _build_repo_map(self, max_files: int = 800) -> list[str]:
        files: list[str] = []
        for path in self.repo_path.rglob("*"):
            if ".git" in path.parts or not path.is_file():
                continue
            files.append(str(path.relative_to(self.repo_path)).replace("\\", "/"))
            if len(files) >= max_files:
                break
        return sorted(files)

    def _detect_project_types(self, repo_map: list[str]) -> list[str]:
        found: list[str] = []
        file_set = set(repo_map)

        if any(name in file_set for name in ["pyproject.toml", "requirements.txt", "setup.py"]):
            found.append("python")
        if "package.json" in file_set:
            found.append("node")
        if "Cargo.toml" in file_set:
            found.append("rust")
        if "go.mod" in file_set:
            found.append("go")

        return found

    def _infer_commands(self, project_types: list[str]) -> dict[str, list[str]]:
        commands: dict[str, list[str]] = {
            "test": [],
            "lint": [],
            "typecheck": [],
            "build": [],
        }

        if "python" in project_types:
            commands["test"].append("pytest -q")
            commands["lint"].append("ruff check .")
            commands["typecheck"].append("mypy .")

        if "node" in project_types:
            node_commands = self._infer_node_commands()
            for key in commands:
                commands[key].extend(node_commands.get(key, []))

        if "rust" in project_types:
            commands["test"].append("cargo test")
            commands["lint"].append("cargo clippy --all-targets -- -D warnings")
            commands["build"].append("cargo build")

        if "go" in project_types:
            commands["test"].append("go test ./...")
            commands["build"].append("go build ./...")

        # Dedupe while preserving order.
        for key, value in commands.items():
            deduped: list[str] = []
            for cmd in value:
                if cmd not in deduped:
                    deduped.append(cmd)
            commands[key] = deduped

        return commands

    def _infer_node_commands(self) -> dict[str, list[str]]:
        package_json = self.repo_path / "package.json"
        if not package_json.exists():
            return {
                "test": ["npm test"],
                "lint": ["npm run lint"],
                "typecheck": ["npm run typecheck"],
                "build": ["npm run build"],
            }

        try:
            payload = json.loads(package_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {
                "test": ["npm test"],
                "lint": ["npm run lint"],
                "typecheck": ["npm run typecheck"],
                "build": ["npm run build"],
            }

        scripts = payload.get("scripts", {}) if isinstance(payload, dict) else {}
        script_names = set(scripts.keys()) if isinstance(scripts, dict) else set()

        return {
            "test": ["npm run test" if "test" in script_names else "npm test"],
            "lint": ["npm run lint"] if "lint" in script_names else [],
            "typecheck": ["npm run typecheck"]
            if "typecheck" in script_names
            else (["npm run tsc"] if "tsc" in script_names else []),
            "build": ["npm run build"] if "build" in script_names else [],
        }
