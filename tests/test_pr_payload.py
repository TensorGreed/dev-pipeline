from __future__ import annotations

from pathlib import Path

from app.models.schemas import PRPayload
from app.tools.github_tools import GitHubTools


def test_generate_pr_body_contains_sections(tmp_path: Path) -> None:
    payload = PRPayload(
        title="feat: csv export",
        body="Adds CSV export with current table filters.",
        checklist=["Tests updated", "Manual QA completed"],
        change_summary=["Added export button", "Updated serializer"],
        test_evidence=["pytest -q passed"],
        unresolved_risks=["Large datasets may need async export in follow-up"],
    )
    body = GitHubTools(tmp_path).generate_pr_body(payload)
    assert "## Summary" in body
    assert "## Change Summary" in body
    assert "## Test Evidence" in body
    assert "## Risks" in body
    assert "- [ ] Tests updated" in body
