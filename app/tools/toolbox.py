from __future__ import annotations

from pathlib import Path
from typing import Any

from app.models.schemas import CommandExecution, PRPayload
from app.tools.artifacts import ArtifactRecorder
from app.tools.command_runner import CommandRunner
from app.tools.filesystem import SearchMatch, WorkspaceFileSystem
from app.tools.git_tools import GitTools
from app.tools.github_tools import GitHubTools


class PipelineToolbox:
    """Strict tool interface exposed to orchestration nodes."""

    def __init__(
        self,
        *,
        repo_path: Path,
        command_runner: CommandRunner,
        artifact_recorder: ArtifactRecorder,
    ) -> None:
        self.repo_path = repo_path
        self.fs = WorkspaceFileSystem(repo_path)
        self.git = GitTools(repo_path)
        self.gh = GitHubTools(repo_path)
        self.command_runner = command_runner
        self.artifacts = artifact_recorder

    # Filesystem wrappers
    def read_file(self, path: str) -> str:
        return self.fs.read_file(path)

    def write_file(self, path: str, content: str) -> None:
        self.fs.write_file(path, content)

    def list_files(self, path: str = ".", max_files: int = 1000) -> list[str]:
        return self.fs.list_files(path, max_files=max_files)

    def search_code(
        self,
        pattern: str,
        path: str = ".",
        max_results: int = 200,
    ) -> list[SearchMatch]:
        return self.fs.search_code(pattern, path, max_results=max_results)

    # Command wrapper
    def run_command(self, command: str, timeout_seconds: int = 900) -> CommandExecution:
        return self.command_runner.run_command(
            command=command,
            cwd=self.repo_path,
            timeout_seconds=timeout_seconds,
        )

    # Git wrappers
    def git_status(self) -> str:
        return self.git.git_status()

    def git_diff(self, *, staged: bool = False, refspec: str | None = None) -> str:
        return self.git.git_diff(staged=staged, refspec=refspec)

    def git_checkout_new_branch(self, *, base_branch: str, feature_branch: str) -> str:
        return self.git.git_checkout_new_branch(
            base_branch=base_branch,
            feature_branch=feature_branch,
        )

    def git_commit(self, *, message: str) -> str | None:
        return self.git.git_commit(message=message)

    def git_push(self, *, remote: str = "origin", branch: str | None = None) -> str:
        return self.git.git_push(remote=remote, branch=branch)

    # PR wrappers
    def generate_pr_body(self, payload: PRPayload) -> str:
        return self.gh.generate_pr_body(payload)

    def create_pr_with_gh(
        self,
        *,
        payload: PRPayload,
        base_branch: str,
        head_branch: str,
        body_file_path: Path,
    ) -> CommandExecution:
        return self.gh.create_pr_with_gh(
            payload=payload,
            base_branch=base_branch,
            head_branch=head_branch,
            body_file_path=body_file_path,
        )

    # Artifact wrapper
    def record_artifact(
        self,
        *,
        run_id: str,
        artifacts_dir: Path,
        name: str,
        content: str | dict[str, Any] | list[Any],
    ) -> str:
        return self.artifacts.record_artifact(
            run_id=run_id,
            artifacts_dir=artifacts_dir,
            name=name,
            content=content,
        )
