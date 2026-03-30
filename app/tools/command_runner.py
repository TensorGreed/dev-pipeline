from __future__ import annotations

import re
import time
from pathlib import Path

from app.models.schemas import CommandExecution
from app.runtime.sandbox import SandboxExecutor


class CommandNotAllowed(RuntimeError):
    """Raised when a command fails allowlist policy."""


class CommandRunner:
    def __init__(self, allowlist_patterns: list[str], sandbox: SandboxExecutor) -> None:
        self.allowlist = [re.compile(pattern) for pattern in allowlist_patterns]
        self.sandbox = sandbox

    def is_allowed(self, command: str) -> bool:
        if any(token in command for token in ["&&", "||", ";", "`", ">", "<"]):
            return False
        return any(pattern.search(command.strip()) for pattern in self.allowlist)

    def run_command(
        self,
        *,
        command: str,
        cwd: Path,
        timeout_seconds: int = 900,
    ) -> CommandExecution:
        if not self.is_allowed(command):
            raise CommandNotAllowed(f"command is not allowlisted: {command}")

        started = time.perf_counter()
        process = self.sandbox.run(command=command, cwd=cwd, timeout_seconds=timeout_seconds)
        duration = time.perf_counter() - started

        return CommandExecution(
            command=command,
            return_code=process.returncode,
            stdout=process.stdout,
            stderr=process.stderr,
            duration_seconds=duration,
            success=process.returncode == 0,
        )
