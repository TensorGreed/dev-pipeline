from __future__ import annotations

import subprocess
from pathlib import Path

from app.tools.git_tools import GitTools


def _run(cmd: list[str], cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stdout}\n{result.stderr}")


def test_git_tools_branch_and_commit(tmp_path: Path) -> None:
    _run(["git", "init"], cwd=tmp_path)
    _run(["git", "checkout", "-b", "main"], cwd=tmp_path)
    _run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path)
    _run(["git", "config", "user.name", "Test User"], cwd=tmp_path)
    (tmp_path / "app.py").write_text("print('v1')\n", encoding="utf-8")
    _run(["git", "add", "-A"], cwd=tmp_path)
    _run(["git", "commit", "-m", "init"], cwd=tmp_path)

    git_tools = GitTools(tmp_path)
    git_tools.git_checkout_new_branch(base_branch="main", feature_branch="feature/test")
    (tmp_path / "app.py").write_text("print('v2')\n", encoding="utf-8")
    commit_sha = git_tools.git_commit(message="feat: update app")

    assert git_tools.current_branch() == "feature/test"
    assert commit_sha is not None
    assert len(commit_sha) >= 7
