from __future__ import annotations

from pathlib import Path

from app.models.schemas import RequirementInput
from app.tools.repo_inspector import RepoInspector


def test_repo_inspector_detects_python(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")

    inspector = RepoInspector(tmp_path)
    requirement = RequirementInput(repo=str(tmp_path), requirement_text="Add feature")
    result = inspector.inspect(requirement)

    assert "python" in result.project_types
    assert "pytest -q" in result.inferred_commands["test"]
    assert "ruff check ." in result.inferred_commands["lint"]


def test_repo_inspector_honors_command_overrides(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module demo\n", encoding="utf-8")
    requirement = RequirementInput(
        repo=str(tmp_path),
        requirement_text="Add endpoint",
        test_commands=["go test ./integration/..."],
        lint_commands=["golangci-lint run"],
    )

    result = RepoInspector(tmp_path).inspect(requirement)
    assert result.inferred_commands["test"] == ["go test ./integration/..."]
    assert result.inferred_commands["lint"] == ["golangci-lint run"]
