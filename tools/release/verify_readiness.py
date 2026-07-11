from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

REQUIRED_DECISIONS = {
    "Q-001": "production operator, domain, ICP and cloud account",
    "Q-002": "model and embedding provider plus data region",
    "Q-003": "initial administrator authentication method",
    "Q-004": "pilot enterprise content and evidence acceptance",
    "Q-005": "pilot population and capacity target",
    "Q-006": "external notification scope",
    "Q-007": "data ownership and processor boundaries",
    "Q-008": "conversation, lead, audit and backup retention",
    "Q-009": "AI disclosure, privacy, consent and complaint owner",
    "Q-010": "delivery team and operating capacity",
    "Q-011": "success criteria and severe incident thresholds",
    "Q-012": "platform support access and break-glass policy",
}
PLACEHOLDER_PATTERN = re.compile(
    r"(^|\b)(tbd|todo|pending|unknown|example|replace|待确认|待定|未确认)(\b|$)",
    re.IGNORECASE,
)
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)


@dataclass(frozen=True)
class VerificationResult:
    ready: bool
    release_id: str | None
    git_sha: str | None
    target_environment: str | None
    approved_decisions: int
    required_decisions: int
    errors: list[str]


def _non_placeholder(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not PLACEHOLDER_PATTERN.search(value)


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _valid_evidence(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for item in value:
        if not isinstance(item, dict):
            return False
        if item.get("type") not in {"document", "ticket", "url", "artifact"}:
            return False
        if not _non_placeholder(item.get("reference")):
            return False
    return True


def verify(payload: Any, *, expected_git_sha: str | None = None) -> VerificationResult:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return VerificationResult(False, None, None, None, 0, len(REQUIRED_DECISIONS), ["root must be an object"])
    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")

    release = payload.get("release")
    if not isinstance(release, dict):
        release = {}
        errors.append("release must be an object")
    release_id = release.get("release_id") if isinstance(release.get("release_id"), str) else None
    git_sha = release.get("git_sha") if isinstance(release.get("git_sha"), str) else None
    target_environment = (
        release.get("target_environment")
        if isinstance(release.get("target_environment"), str)
        else None
    )
    if not _non_placeholder(release_id):
        errors.append("release.release_id must be non-placeholder text")
    if not git_sha or not GIT_SHA_PATTERN.fullmatch(git_sha):
        errors.append("release.git_sha must be a 40-character commit SHA")
    if expected_git_sha and git_sha and git_sha.lower() != expected_git_sha.lower():
        errors.append("release.git_sha does not match the expected deployment commit")
    if target_environment != "production":
        errors.append("release.target_environment must be production")

    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        decisions = []
        errors.append("decisions must be an array")
    by_id: dict[str, dict[str, Any]] = {}
    for item in decisions:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            errors.append("every decision must be an object with an id")
            continue
        decision_id = item["id"]
        if decision_id in by_id:
            errors.append(f"{decision_id}: duplicate decision")
            continue
        by_id[decision_id] = item

    approved = 0
    for decision_id, title in REQUIRED_DECISIONS.items():
        item = by_id.get(decision_id)
        if item is None:
            errors.append(f"{decision_id}: missing ({title})")
            continue
        item_errors: list[str] = []
        if item.get("status") != "approved":
            item_errors.append("status is not approved")
        for field in ("owner", "decision", "approved_by"):
            if not _non_placeholder(item.get(field)):
                item_errors.append(f"{field} is missing or placeholder")
        if not _valid_timestamp(item.get("approved_at")):
            item_errors.append("approved_at must be an ISO-8601 timestamp with timezone")
        if not _valid_evidence(item.get("evidence")):
            item_errors.append("evidence must contain a typed, non-placeholder reference")
        if item_errors:
            errors.extend(f"{decision_id}: {message}" for message in item_errors)
        else:
            approved += 1

    return VerificationResult(
        ready=not errors,
        release_id=release_id,
        git_sha=git_sha,
        target_environment=target_environment,
        approved_decisions=approved,
        required_decisions=len(REQUIRED_DECISIONS),
        errors=errors,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-closed verification of the 12 production P0 approvals.",
    )
    parser.add_argument("--approvals", type=Path, required=True)
    parser.add_argument("--expected-git-sha")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = json.loads(args.approvals.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ready": False, "errors": [f"cannot read approvals: {exc}"]}, ensure_ascii=False))
        return 1
    result = verify(payload, expected_git_sha=args.expected_git_sha)
    rendered = json.dumps(asdict(result), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result.ready else 2


if __name__ == "__main__":
    sys.exit(main())
