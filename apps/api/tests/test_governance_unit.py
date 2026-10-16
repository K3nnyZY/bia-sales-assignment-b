import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.governance.models import VersionGovernance
from app.governance.schemas import EvaluateRequest, GovernanceAction, SuiteCreate
from app.governance.service import check_action


@pytest.mark.parametrize("checks", [["unknown"], ["invoice", "invoice"], []])
def test_suite_rejects_unknown_duplicate_and_empty_checks(checks):
    with pytest.raises(ValidationError):
        SuiteCreate(id="test-suite", version=1, name="Test", checks=checks)


@pytest.mark.parametrize(
    "extra",
    [
        {"permissions": ["admin"]},
        {"expected_results": {"passed": True}},
        {"caller_id": "demo-administrator"},
    ],
)
def test_evaluation_cannot_supply_privileges_or_results(extra):
    with pytest.raises(ValidationError):
        EvaluateRequest(expected_config_hash="a" * 64, **extra)


@pytest.mark.parametrize("revision,hash_value", [(2, "a" * 64), (1, "b" * 64)])
def test_governance_rejects_stale_revision_or_mismatched_hash(revision, hash_value):
    item = VersionGovernance(config_hash="a" * 64, revision=1)
    with pytest.raises(HTTPException) as caught:
        check_action(
            item, GovernanceAction(expected_revision=revision, expected_config_hash=hash_value)
        )
    assert caught.value.status_code == 409
