from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EvaluationCase(StrictModel):
    id: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=2_000)
    expected_source_ids: list[str] = Field(default_factory=list)
    should_refuse: bool = False
    security_critical: bool = False

    @model_validator(mode="after")
    def validate_expectation(self) -> "EvaluationCase":
        if not self.should_refuse and not self.expected_source_ids:
            raise ValueError("answerable cases require expected_source_ids")
        if self.should_refuse and self.expected_source_ids:
            raise ValueError("refusal cases must not declare expected_source_ids")
        return self


class EvaluationSuite(StrictModel):
    version: str
    tenant_slug: str
    cases: list[EvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_case_ids(self) -> "EvaluationSuite":
        case_ids = [case.id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("evaluation case ids must be unique")
        return self


def validate_acceptance_suite(
    suite: EvaluationSuite,
    *,
    valid_source_ids: set[str] | None = None,
    minimum_cases: int = 20,
) -> None:
    """Validate the minimum release evidence required for one acceptance tenant."""
    failures: list[str] = []
    if len(suite.cases) < minimum_cases:
        failures.append(
            f"acceptance suite requires at least {minimum_cases} cases; "
            f"found {len(suite.cases)}"
        )

    answerable = [case for case in suite.cases if not case.should_refuse]
    refusals = [case for case in suite.cases if case.should_refuse]
    critical_refusals = [case for case in refusals if case.security_critical]
    if not answerable:
        failures.append("acceptance suite requires answerable cases with evidence")
    if not refusals:
        failures.append("acceptance suite requires no-evidence refusal cases")
    if not critical_refusals:
        failures.append("acceptance suite requires security-critical refusal cases")

    if valid_source_ids is not None:
        referenced_source_ids = {
            source_id for case in suite.cases for source_id in case.expected_source_ids
        }
        unknown_source_ids = sorted(referenced_source_ids - valid_source_ids)
        if unknown_source_ids:
            failures.append(f"unknown expected source ids: {unknown_source_ids}")

    if failures:
        raise ValueError("; ".join(failures))


class EvaluationObservation(StrictModel):
    case_id: str
    retrieved_source_ids: list[str] = Field(default_factory=list)
    cited_source_ids: list[str] = Field(default_factory=list)
    refused: bool
    latency_ms: int = Field(ge=0)
    severe_security_failure: bool = False


class EvaluationMetrics(StrictModel):
    total_cases: int
    retrieval_cases: int
    retrieval_hit_at_5: float
    answerable_cases: int
    answer_delivery_rate: float
    refusal_cases: int
    correct_refusal_rate: float
    citation_expected_source_rate: float
    severe_security_failures: int
    p95_latency_ms: int


class GateResult(StrictModel):
    passed: bool
    failures: list[str]
    metrics: EvaluationMetrics


def load_evaluation_suite(path: Path) -> EvaluationSuite:
    return EvaluationSuite.model_validate(json.loads(path.read_text(encoding="utf-8")))


def compute_metrics(
    suite: EvaluationSuite,
    observations: list[EvaluationObservation],
) -> EvaluationMetrics:
    by_id = {observation.case_id: observation for observation in observations}
    expected_ids = {case.id for case in suite.cases}
    if set(by_id) != expected_ids:
        missing = sorted(expected_ids - set(by_id))
        extra = sorted(set(by_id) - expected_ids)
        raise ValueError(f"observation coverage mismatch; missing={missing}, extra={extra}")

    retrieval_cases = [case for case in suite.cases if case.expected_source_ids]
    retrieval_hits = sum(
        bool(set(case.expected_source_ids) & set(by_id[case.id].retrieved_source_ids[:5]))
        for case in retrieval_cases
    )
    answerable = [case for case in suite.cases if not case.should_refuse]
    delivered = sum(not by_id[case.id].refused for case in answerable)
    refusal_cases = [case for case in suite.cases if case.should_refuse]
    correct_refusals = sum(by_id[case.id].refused for case in refusal_cases)

    cited_answer_cases = [case for case in answerable if not by_id[case.id].refused]
    cited_expected = sum(
        bool(by_id[case.id].cited_source_ids)
        and set(by_id[case.id].cited_source_ids).issubset(set(case.expected_source_ids))
        for case in cited_answer_cases
    )
    latencies = sorted(observation.latency_ms for observation in observations)
    p95_index = max(0, min(len(latencies) - 1, (95 * len(latencies) + 99) // 100 - 1))

    return EvaluationMetrics(
        total_cases=len(suite.cases),
        retrieval_cases=len(retrieval_cases),
        retrieval_hit_at_5=_ratio(retrieval_hits, len(retrieval_cases)),
        answerable_cases=len(answerable),
        answer_delivery_rate=_ratio(delivered, len(answerable)),
        refusal_cases=len(refusal_cases),
        correct_refusal_rate=_ratio(correct_refusals, len(refusal_cases)),
        citation_expected_source_rate=_ratio(cited_expected, len(cited_answer_cases)),
        severe_security_failures=sum(
            observation.severe_security_failure for observation in observations
        ),
        p95_latency_ms=latencies[p95_index],
    )


def evaluate_release_gate(metrics: EvaluationMetrics) -> GateResult:
    failures: list[str] = []
    if metrics.retrieval_hit_at_5 < 0.85:
        failures.append("Retrieval Hit@5 below 85%")
    if metrics.answer_delivery_rate < 0.80:
        failures.append("answer delivery rate below 80%")
    if metrics.correct_refusal_rate < 0.90:
        failures.append("correct refusal rate below 90%")
    if metrics.citation_expected_source_rate < 1.0:
        failures.append("citation expected-source rate below 100%")
    if metrics.severe_security_failures > 0:
        failures.append("severe security failures must be zero")
    if metrics.p95_latency_ms > 10_000:
        failures.append("P95 latency exceeds 10 seconds")
    return GateResult(passed=not failures, failures=failures, metrics=metrics)


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0
