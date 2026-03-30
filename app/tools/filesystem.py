from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class FileSystemError(RuntimeError):
    """Raised when file operations violate workspace boundaries."""


@dataclass(slots=True)
class SearchMatch:
    path: str
    line: int
    content: str


class WorkspaceFileSystem:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def _resolve(self, relative_path: str) -> Path:
        candidate = (self.repo_root / relative_path).resolve()
        if self.repo_root not in candidate.parents and candidate != self.repo_root:
            raise FileSystemError(f"path escapes workspace: {relative_path}")
        return candidate

    def read_file(self, relative_path: str) -> str:
        file_path = self._resolve(relative_path)
        if not file_path.exists() or file_path.is_dir():
            raise FileSystemError(f"file not found: {relative_path}")
        return file_path.read_text(encoding="utf-8")

    def write_file(self, relative_path: str, content: str) -> None:
        file_path = self._resolve(relative_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    def list_files(self, relative_path: str = ".", max_files: int = 1000) -> list[str]:
        base = self._resolve(relative_path)
        if not base.exists():
            return []

        files: list[str] = []
        for path in base.rglob("*"):
            if ".git" in path.parts:
                continue
            if path.is_file():
                files.append(str(path.relative_to(self.repo_root)).replace("\\", "/"))
                if len(files) >= max_files:
                    break
        return sorted(files)

    def search_code(
        self,
        pattern: str,
        relative_path: str = ".",
        max_results: int = 200,
    ) -> list[SearchMatch]:
        target = self._resolve(relative_path)
        try:
            cmd = [
                "rg",
                "--line-number",
                "--no-heading",
                "--color",
                "never",
                pattern,
                str(target),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode not in {0, 1}:
                return []
            return self._parse_rg_output(res.stdout, max_results)
        except FileNotFoundError:
            return self._search_fallback(pattern, target, max_results)

    def _parse_rg_output(self, output: str, max_results: int) -> list[SearchMatch]:
        matches: list[SearchMatch] = []
        for line in output.splitlines():
            if len(matches) >= max_results:
                break
            try:
                file_part, line_part, content = line.split(":", 2)
                rel = Path(file_part).resolve().relative_to(self.repo_root)
                matches.append(
                    SearchMatch(
                        path=str(rel).replace("\\", "/"),
                        line=int(line_part),
                        content=content.strip(),
                    )
                )
            except (ValueError, OSError):
                continue
        return matches

    def _search_fallback(self, pattern: str, target: Path, max_results: int) -> list[SearchMatch]:
        matches: list[SearchMatch] = []
        for file_path in target.rglob("*"):
            if len(matches) >= max_results:
                break
            if ".git" in file_path.parts or not file_path.is_file():
                continue
            try:
                text = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for idx, line in enumerate(text.splitlines(), start=1):
                if pattern in line:
                    rel = file_path.relative_to(self.repo_root)
                    matches.append(
                        SearchMatch(
                            path=str(rel).replace("\\", "/"),
                            line=idx,
                            content=line.strip(),
                        )
                    )
                    if len(matches) >= max_results:
                        break
        return matches
