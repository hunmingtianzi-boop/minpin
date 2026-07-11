from __future__ import annotations

import copy

from tools.release.verify_readiness import REQUIRED_DECISIONS, verify

SHA = "a" * 40


def approved_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "release": {
            "release_id": "v1.0.0",
            "git_sha": SHA,
            "target_environment": "production",
        },
        "decisions": [
            {
                "id": decision_id,
                "status": "approved",
                "owner": "Named Owner",
                "decision": f"Approved scope for {decision_id}",
                "approved_by": "Named Approver",
                "approved_at": "2026-07-11T12:00:00+08:00",
                "evidence": [
                    {"type": "ticket", "reference": f"REL-{index:03d}"},
                ],
            }
            for index, decision_id in enumerate(REQUIRED_DECISIONS, start=1)
        ],
    }


def test_all_named_approvals_are_required() -> None:
    payload = approved_payload()
    result = verify(payload, expected_git_sha=SHA)

    assert result.ready is True
    assert result.approved_decisions == 12
    assert result.errors == []


def test_pending_and_placeholder_values_fail_closed() -> None:
    payload = approved_payload()
    decision = payload["decisions"][0]  # type: ignore[index]
    decision["status"] = "pending"  # type: ignore[index]
    decision["decision"] = "待确认"  # type: ignore[index]

    result = verify(payload)

    assert result.ready is False
    assert any("Q-001: status is not approved" in error for error in result.errors)
    assert any("Q-001: decision is missing or placeholder" in error for error in result.errors)


def test_duplicate_missing_and_wrong_commit_are_rejected() -> None:
    payload = approved_payload()
    decisions = payload["decisions"]  # type: ignore[assignment]
    decisions.append(copy.deepcopy(decisions[0]))  # type: ignore[union-attr,index]
    decisions.pop(1)  # type: ignore[union-attr]

    result = verify(payload, expected_git_sha="b" * 40)

    assert result.ready is False
    assert any("duplicate decision" in error for error in result.errors)
    assert any("Q-002: missing" in error for error in result.errors)
    assert any("does not match" in error for error in result.errors)
