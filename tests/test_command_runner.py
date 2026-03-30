from __future__ import annotations

from pathlib import Path

import pytest

from app.config import SandboxConfig
from app.runtime.sandbox import SandboxExecutor
from app.tools.command_runner import CommandNotAllowed, CommandRunner


def test_command_allowlist_enforced(tmp_path: Path) -> None:
    runner = CommandRunner(
        allowlist_patterns=[r"^python(\s|$)"],
        sandbox=SandboxExecutor(SandboxConfig(docker_enabled=False)),
    )

    result = runner.run_command(command='python -c "print(123)"', cwd=tmp_path)
    assert result.success is True
    assert "123" in result.stdout

    with pytest.raises(CommandNotAllowed):
        runner.run_command(command="echo hello", cwd=tmp_path)


def test_command_blocks_dangerous_chain(tmp_path: Path) -> None:
    runner = CommandRunner(
        allowlist_patterns=[r"^python(\s|$)"],
        sandbox=SandboxExecutor(SandboxConfig(docker_enabled=False)),
    )
    with pytest.raises(CommandNotAllowed):
        runner.run_command(command='python -c "print(1)" && echo pwned', cwd=tmp_path)
