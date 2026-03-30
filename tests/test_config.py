from __future__ import annotations

from pathlib import Path

from app.config import apply_cli_overrides, load_settings


def test_load_settings_example() -> None:
    settings = load_settings("config/settings.example.yaml")
    assert settings.model.base_url == "http://10.0.0.113/v1"
    assert settings.model.model_name == "qwen3"
    assert settings.limits.max_iterations > 0


def test_apply_cli_overrides() -> None:
    settings = load_settings("config/settings.example.yaml")
    updated = apply_cli_overrides(
        settings,
        max_iterations=3,
        dry_run=True,
        test_commands=["pytest tests -q"],
    )
    assert updated.limits.max_iterations == 3
    assert updated.runtime.dry_run is True
    assert updated.commands.defaults.test == ["pytest tests -q"]


def test_workspace_and_db_paths_are_resolved() -> None:
    settings = load_settings("config/settings.example.yaml")
    root = settings.workspace_root(Path.cwd())
    db_path = settings.db_path(Path.cwd())
    assert str(root).endswith(".workspace")
    assert db_path.name == "runs.sqlite3"
