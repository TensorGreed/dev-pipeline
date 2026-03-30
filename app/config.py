from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator


class ModelConfig(BaseModel):
    base_url: str = "http://10.0.0.113/v1"
    model_name: str = "qwen3"
    api_key: str = ""
    timeout_seconds: int = 90
    max_retries: int = 2

    @field_validator("timeout_seconds", "max_retries")
    @classmethod
    def _positive_numbers(cls, value: int) -> int:
        if value < 1:
            raise ValueError("must be >= 1")
        return value


class WorkspaceConfig(BaseModel):
    root: str = ".workspace"
    keep_runs: int = 20

    @field_validator("keep_runs")
    @classmethod
    def _positive_keep_runs(cls, value: int) -> int:
        if value < 1:
            raise ValueError("keep_runs must be >= 1")
        return value


class LimitsConfig(BaseModel):
    max_iterations: int = 6
    max_fix_loops: int = 3
    max_files_changed: int = 50
    max_lines_changed: int = 2000
    max_tool_calls: int = 300

    @field_validator(
        "max_iterations",
        "max_fix_loops",
        "max_files_changed",
        "max_lines_changed",
        "max_tool_calls",
    )
    @classmethod
    def _positive_limits(cls, value: int) -> int:
        if value < 1:
            raise ValueError("limit values must be >= 1")
        return value


class CommandDefaults(BaseModel):
    test: list[str] = Field(default_factory=lambda: ["pytest -q"])
    lint: list[str] = Field(default_factory=lambda: ["ruff check ."])
    typecheck: list[str] = Field(default_factory=lambda: ["mypy ."])
    build: list[str] = Field(default_factory=list)


class CommandConfig(BaseModel):
    allowlist: list[str] = Field(
        default_factory=lambda: [
            r"^pytest(\s|$)",
            r"^ruff(\s|$)",
            r"^mypy(\s|$)",
            r"^python(\s|$)",
            r"^uv(\s|$)",
            r"^npm(\s|$)",
            r"^pnpm(\s|$)",
            r"^yarn(\s|$)",
            r"^node(\s|$)",
            r"^tsc(\s|$)",
            r"^cargo(\s|$)",
            r"^go(\s|$)",
        ]
    )
    defaults: CommandDefaults = Field(default_factory=CommandDefaults)


class GitHubConfig(BaseModel):
    enabled: bool = True
    auto_open_pr: bool = False
    remote: str = "origin"


class SandboxConfig(BaseModel):
    docker_enabled: bool = False
    image: str = "python:3.11-slim"


class RuntimeConfig(BaseModel):
    dry_run: bool = False
    explain_mode: bool = True
    log_level: str = "INFO"


class Settings(BaseModel):
    model: ModelConfig = Field(default_factory=ModelConfig)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    commands: CommandConfig = Field(default_factory=CommandConfig)
    github: GitHubConfig = Field(default_factory=GitHubConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)

    def workspace_root(self, base_dir: Path | None = None) -> Path:
        root = Path(self.workspace.root)
        if not root.is_absolute() and base_dir is not None:
            root = base_dir / root
        return root.resolve()

    def db_path(self, base_dir: Path | None = None) -> Path:
        return self.workspace_root(base_dir) / "runs.sqlite3"


def _set_nested_value(data: dict[str, Any], path: list[str], value: Any) -> None:
    current = data
    for key in path[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[path[-1]] = value


def _apply_env_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    env_to_key = {
        "MODEL_BASE_URL": ["model", "base_url"],
        "MODEL_NAME": ["model", "model_name"],
        "MODEL_API_KEY": ["model", "api_key"],
        "WORKSPACE_ROOT": ["workspace", "root"],
        "LOG_LEVEL": ["runtime", "log_level"],
    }
    for env_key, model_path in env_to_key.items():
        env_value = os.getenv(env_key)
        if env_value is not None:
            _set_nested_value(raw, model_path, env_value)
    return raw


def load_settings(path: str | Path) -> Settings:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"config file not found: {file_path}")

    with file_path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}

    if not isinstance(loaded, dict):
        raise ValueError("config root must be a mapping")

    loaded = _apply_env_overrides(loaded)

    try:
        return Settings.model_validate(loaded)
    except ValidationError as exc:
        raise ValueError(f"invalid config: {exc}") from exc


def apply_cli_overrides(
    settings: Settings,
    *,
    max_iterations: int | None = None,
    dry_run: bool | None = None,
    test_commands: list[str] | None = None,
    lint_commands: list[str] | None = None,
    build_commands: list[str] | None = None,
) -> Settings:
    updates: dict[str, Any] = settings.model_dump(mode="python")

    if max_iterations is not None:
        updates["limits"]["max_iterations"] = max_iterations
    if dry_run is not None:
        updates["runtime"]["dry_run"] = dry_run
    if test_commands is not None:
        updates["commands"]["defaults"]["test"] = test_commands
    if lint_commands is not None:
        updates["commands"]["defaults"]["lint"] = lint_commands
    if build_commands is not None:
        updates["commands"]["defaults"]["build"] = build_commands

    return Settings.model_validate(updates)
