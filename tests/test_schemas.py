from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.schemas import RequirementInput, ReviewFinding, RunCreateRequest


def test_run_request_to_requirement_input() -> None:
    request = RunCreateRequest(
        repo="/tmp/demo",
        requirement="Implement CSV export",
        acceptance_criteria=["Button exists", "Serializer includes filters"],
        base_branch="main",
    )
    requirement = request.to_requirement_input()
    assert isinstance(requirement, RequirementInput)
    assert requirement.requirement_text == "Implement CSV export"


def test_review_finding_severity_validation() -> None:
    with pytest.raises(ValidationError):
        ReviewFinding(
            finding_id="F-1",
            severity="urgent",  # type: ignore[arg-type]
            title="Invalid",
            description="Bad severity",
        )
