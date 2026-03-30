from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse


class WorkspaceError(RuntimeError):
    """Raised when workspace setup fails."""


class WorkspaceManager:
    def __init__(self, root: Path, keep_runs: int = 20) -> None:
        self.root = root
        self.keep_runs = keep_runs
        self.root.mkdir(parents=True, exist_ok=True)

    def create_run_root(self, run_id: str) -> Path:
        run_root = self.root / run_id
        run_root.mkdir(parents=True, exist_ok=True)
        (run_root / "artifacts").mkdir(parents=True, exist_ok=True)
        return run_root

    def clone_repo(
        self,
        *,
        repo_source: str,
        run_root: Path,
        base_branch: str | None = None,
    ) -> Path:
        repo_target = run_root / "repo"

        if repo_target.exists():
            shutil.rmtree(repo_target)

        clone_cmd = ["git", "clone", repo_source, str(repo_target)]
        result = subprocess.run(clone_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise WorkspaceError(
                f"git clone failed for '{repo_source}': {result.stdout}\n{result.stderr}"
            )

        if base_branch:
            checkout_cmd = ["git", "checkout", base_branch]
            checkout_res = subprocess.run(
                checkout_cmd,
                cwd=repo_target,
                capture_output=True,
                text=True,
            )
            if checkout_res.returncode != 0:
                raise WorkspaceError(
                    f"unable to checkout base branch '{base_branch}': "
                    f"{checkout_res.stdout}\n{checkout_res.stderr}"
                )

        return repo_target

    def cleanup_old_runs(self) -> None:
        run_dirs = sorted(
            [path for path in self.root.iterdir() if path.is_dir()],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for stale in run_dirs[self.keep_runs :]:
            shutil.rmtree(stale, ignore_errors=True)

    @staticmethod
    def is_probably_git_url(value: str) -> bool:
        parsed = urlparse(value)
        return bool(parsed.scheme and parsed.netloc) or value.endswith(".git")
