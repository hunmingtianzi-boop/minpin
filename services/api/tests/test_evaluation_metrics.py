from __future__ import annotations

from pathlib import Path

import pytest

from app.evaluation import (
    EvaluationObservation,
    compute_metrics,
    evaluate_release_gate,
    load_evaluation_suite,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "filename,count",
    [("template.v1.json", 7), ("tuotu.v1.json", 13)],
)
def test_evaluation_suites_validate(filename: str, count: int) -> None:
    suite = load_evaluation_suite(ROOT / "packages" / "evals" / filename)
    assert len(suite.cases) == count


def test_release_gate_passes_complete_supported_observations() -> None:
    suite = load_evaluation_suite(ROOT / "packages" / "evals" / "template.v1.json")
    observations = [
        EvaluationObservation(
            case_id=case.id,
            retrieved_source_ids=case.expected_source_ids,
            cited_source_ids=[] if case.should_refuse else case.expected_source_ids,
            refused=case.should_refuse,
            latency_ms=500,
        )
        for case in suite.cases
    ]

    result = evaluate_release_gate(compute_metrics(suite, observations))

    assert result.passed is True
    assert result.metrics.retrieval_hit_at_5 == 1.0
    assert result.metrics.correct_refusal_rate == 1.0


def test_release_gate_blocks_security_failure() -> None:
    suite = load_evaluation_suite(ROOT / "packages" / "evals" / "template.v1.json")
    observations = [
        EvaluationObservation(
            case_id=case.id,
            retrieved_source_ids=case.expected_source_ids,
            cited_source_ids=[] if case.should_refuse else case.expected_source_ids,
            refused=case.should_refuse,
            latency_ms=500,
            severe_security_failure=case.security_critical,
        )
        for case in suite.cases
    ]

    result = evaluate_release_gate(compute_metrics(suite, observations))

    assert result.passed is False
    assert result.metrics.severe_security_failures == 1
