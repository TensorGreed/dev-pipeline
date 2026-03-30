from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.config import LimitsConfig


class LimitViolation(RuntimeError):
    """Raised when runtime limits are exceeded."""


@dataclass(slots=True)
class DiffStats:
    files_changed: int
    lines_changed: int


class LimitTracker:
    def __init__(self, limits: LimitsConfig) -> None:
        self.limits = limits

    def assert_iteration(self, iteration: int) -> None:
        if iteration > self.limits.max_iterations:
            raise LimitViolation(
                f"max iterations exceeded ({iteration} > {self.limits.max_iterations})"
            )

    def assert_fix_loops(self, fix_loops: int) -> None:
        if fix_loops > self.limits.max_fix_loops:
            raise LimitViolation(
                f"max fix loops exceeded ({fix_loops} > {self.limits.max_fix_loops})"
            )

    def assert_tool_calls(self, tool_calls: int) -> None:
        if tool_calls > self.limits.max_tool_calls:
            raise LimitViolation(
                f"max tool calls exceeded ({tool_calls} > {self.limits.max_tool_calls})"
            )

    def assert_diff(self, repo_path: Path) -> DiffStats:
        stats = calculate_diff_stats(repo_path)
        if stats.files_changed > self.limits.max_files_changed:
            raise LimitViolation(
                "max files changed exceeded "
                f"({stats.files_changed} > {self.limits.max_files_changed})"
            )
        if stats.lines_changed > self.limits.max_lines_changed:
            raise LimitViolation(
                "max lines changed exceeded "
                f"({stats.lines_changed} > {self.limits.max_lines_changed})"
            )
        return stats


def calculate_diff_stats(repo_path: Path) -> DiffStats:
    cmd = ["git", "diff", "--numstat"]
    res = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True)
    output = res.stdout if res.returncode == 0 else ""

    cmd_staged = ["git", "diff", "--cached", "--numstat"]
    res_staged = subprocess.run(cmd_staged, cwd=repo_path, capture_output=True, text=True)
    output = f"{output}\n{res_staged.stdout if res_staged.returncode == 0 else ''}".strip()

    files_changed = 0
    lines_changed = 0
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added, deleted, _ = parts[0], parts[1], parts[2]
        if added.isdigit() and deleted.isdigit():
            files_changed += 1
            lines_changed += int(added) + int(deleted)

    return DiffStats(files_changed=files_changed, lines_changed=lines_changed)
