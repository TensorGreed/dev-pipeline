from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from app.models.schemas import CommandExecution, PRPayload


class GitHubTools:
    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path

    def generate_pr_body(self, payload: PRPayload) -> str:
        checklist_lines = "\n".join(f"- [ ] {item}" for item in payload.checklist)
        change_lines = "\n".join(f"- {item}" for item in payload.change_summary)
        test_lines = "\n".join(f"- {item}" for item in payload.test_evidence)
        risk_lines = "\n".join(f"- {item}" for item in payload.unresolved_risks)

        return (
            "## Summary\n"
            f"{payload.body}\n\n"
            "## Change Summary\n"
            f"{change_lines or '- No change summary provided.'}\n\n"
            "## Test Evidence\n"
            f"{test_lines or '- No test evidence provided.'}\n\n"
            "## Risks\n"
            f"{risk_lines or '- No unresolved risks reported.'}\n\n"
            "## Checklist\n"
            f"{checklist_lines or '- [ ] Manual review'}\n"
        )

    def build_gh_command(self, *, title: str, body_file: str, base: str, head: str) -> str:
        return (
            f"gh pr create --title \"{title}\" --body-file \"{body_file}\" "
            f"--base {base} --head {head}"
        )

    def create_pr_with_gh(
        self,
        *,
        payload: PRPayload,
        base_branch: str,
        head_branch: str,
        body_file_path: Path,
    ) -> CommandExecution:
        if shutil.which("gh") is None:
            return CommandExecution(
                command="gh pr create",
                return_code=127,
                stderr="GitHub CLI not installed",
                success=False,
            )

        command = [
            "gh",
            "pr",
            "create",
            "--title",
            payload.title,
            "--body-file",
            str(body_file_path),
            "--base",
            base_branch,
            "--head",
            head_branch,
        ]
        process = subprocess.run(command, cwd=self.repo_path, capture_output=True, text=True)
        return CommandExecution(
            command=" ".join(command),
            return_code=process.returncode,
            stdout=process.stdout,
            stderr=process.stderr,
            success=process.returncode == 0,
        )
