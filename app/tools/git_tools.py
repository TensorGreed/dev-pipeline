from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitToolError(RuntimeError):
    """Raised when git commands fail."""


@dataclass(slots=True)
class GitDiffStats:
    files_changed: int
    lines_changed: int


class GitTools:
    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path

    def _run(self, args: list[str]) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise GitToolError(f"git {' '.join(args)} failed: {result.stdout}\n{result.stderr}")
        return result.stdout.strip()

    def git_status(self) -> str:
        return self._run(["status", "--short"])

    def git_diff(self, *, staged: bool = False, refspec: str | None = None) -> str:
        args = ["diff"]
        if staged:
            args.append("--cached")
        if refspec:
            args.append(refspec)
        return self._run(args)

    def current_branch(self) -> str:
        return self._run(["rev-parse", "--abbrev-ref", "HEAD"])

    def git_checkout_new_branch(self, *, base_branch: str, feature_branch: str) -> str:
        if feature_branch in {"main", "master"}:
            raise GitToolError("refusing to create feature branch as main/master")

        self._run(["checkout", base_branch])
        self._run(["checkout", "-B", feature_branch])
        return feature_branch

    def git_commit(self, *, message: str, add_all: bool = True) -> str | None:
        status = self.git_status()
        if not status.strip():
            return None

        if add_all:
            self._run(["add", "-A"])

        self._run(["commit", "-m", message])
        return self._run(["rev-parse", "HEAD"])

    def git_push(self, *, remote: str = "origin", branch: str | None = None) -> str:
        branch_name = branch or self.current_branch()
        # Force push intentionally unsupported.
        return self._run(["push", remote, branch_name])

    def changed_files(self) -> list[str]:
        output = self._run(["status", "--short"])
        files: list[str] = []
        for line in output.splitlines():
            if len(line) > 3:
                files.append(line[3:].strip())
        return files

    def diff_stats(self) -> GitDiffStats:
        output = self._run(["diff", "--numstat"])
        files = 0
        lines = 0
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            add, delete, _ = parts
            if add.isdigit() and delete.isdigit():
                files += 1
                lines += int(add) + int(delete)
        return GitDiffStats(files_changed=files, lines_changed=lines)

    def commit_log_since(self, base_branch: str) -> list[str]:
        output = self._run(["log", "--oneline", f"{base_branch}..HEAD"])
        return [line.strip() for line in output.splitlines() if line.strip()]
