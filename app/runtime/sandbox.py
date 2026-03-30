from __future__ import annotations

import subprocess
from pathlib import Path

from app.config import SandboxConfig


class SandboxExecutor:
    def __init__(self, settings: SandboxConfig) -> None:
        self.settings = settings

    def run(
        self,
        *,
        command: str,
        cwd: Path,
        timeout_seconds: int,
    ) -> subprocess.CompletedProcess[str]:
        if self.settings.docker_enabled:
            docker_cmd = [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{cwd.resolve()}:/workspace",
                "-w",
                "/workspace",
                self.settings.image,
                "sh",
                "-lc",
                command,
            ]
            return subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )

        return subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            shell=True,
            timeout=timeout_seconds,
        )
