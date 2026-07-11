from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import httpx

from tools.perf.runner import (
    GateThresholds,
    HttpLoadConfig,
    RagLoadConfig,
    _distribution,
    evaluate_gate,
    load_questions,
    run_http_load,
    run_rag_load,
)


def test_distribution_uses_nearest_rank() -> None:
    distribution = _distribution([float(value) for value in range(1, 101)])

    assert distribution["p50"] == 50
    assert distribution["p75"] == 75
    assert distribution["p95"] == 95
    assert distribution["p99"] == 99


def test_http_report_redacts_query_header_values_and_body() -> None:
    secret_header = "Bearer secret-value-that-must-not-appear"  # noqa: S105
    secret_body = b'{"secret":"must-not-appear"}'

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == secret_header
        assert await request.aread() == secret_body
        return httpx.Response(200, json={"ok": True})

    report = asyncio.run(
        run_http_load(
            HttpLoadConfig(
                url="https://api.example.test/admin/cards?private=query",
                requests=3,
                concurrency=2,
                headers=(("Authorization", secret_header),),
                body=secret_body,
                method="POST",
                run_id="unit-http",
            ),
            transport=httpx.MockTransport(handler),
        )
    )
    serialized = json.dumps(report)

    assert report["metrics"]["successes"] == 3
    assert report["target"]["query_present"] is True
    assert "private=query" not in serialized
    assert secret_header not in serialized
    assert "must-not-appear" not in serialized
    assert report["workload"]["header_names"] == ["authorization"]


def test_rag_flow_measures_delta_and_completion_without_reporting_question_or_token() -> None:
    question = "private performance question"
    token = "private-visitor-token"  # noqa: S105
    conversation_id = "11111111-1111-4111-8111-111111111111"

    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path.endswith("/public/cards/sample"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "policy_versions": {"privacy": "privacy-v1", "chat_notice": "chat-v1"}
                    }
                },
            )
        if path.endswith("/visits"):
            return httpx.Response(201, json={"data": {"visitor_session_token": token}})
        if path.endswith("/consents"):
            assert request.headers["Authorization"] == f"Bearer {token}"
            return httpx.Response(201, json={"data": {"id": "consent"}})
        if path.endswith("/conversations"):
            return httpx.Response(201, json={"data": {"id": conversation_id}})
        if path.endswith("/messages:stream"):
            assert request.headers["Authorization"] == f"Bearer {token}"
            assert json.loads(await request.aread()) == {"content": question}
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                content=(
                    'event: message.started\ndata: {"message_id":"1"}\n\n'
                    'event: message.delta\ndata: {"text":"answer"}\n\n'
                    'event: message.completed\ndata: {"message_id":"1"}\n\n'
                ).encode(),
            )
        return httpx.Response(404)

    report = asyncio.run(
        run_rag_load(
            RagLoadConfig(
                base_url="https://api.example.test/api/v1",
                card_slug="sample",
                questions=(question,),
                dataset_sha256=hashlib.sha256(question.encode()).hexdigest(),
                requests=2,
                concurrency=1,
                run_id="unit-rag",
            ),
            transport=httpx.MockTransport(handler),
        )
    )
    report["gate"] = evaluate_gate(
        report,
        GateThresholds(max_error_rate=0, max_ttft_p95_ms=5_000, max_total_p95_ms=10_000),
    )
    serialized = json.dumps(report)

    assert report["metrics"]["successes"] == 2
    assert report["metrics"]["ttft_ms"]["count"] == 2
    assert report["gate"]["passed"] is True
    assert question not in serialized
    assert token not in serialized


def test_gate_fails_closed_when_every_request_fails() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    report = asyncio.run(
        run_http_load(
            HttpLoadConfig(
                url="https://api.example.test/health/ready",
                requests=2,
                concurrency=1,
                run_id="unit-failure",
            ),
            transport=httpx.MockTransport(handler),
        )
    )
    gate = evaluate_gate(report, GateThresholds(max_error_rate=0, max_p95_ms=1_000))

    assert gate["passed"] is False
    assert "no successful samples" in gate["failures"]
    assert any("error_rate" in failure for failure in gate["failures"])
    assert any("latency.p95_ms is unavailable" in failure for failure in gate["failures"])


def test_rag_policy_setup_outage_still_produces_a_failed_report() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    question = "Question?"
    report = asyncio.run(
        run_rag_load(
            RagLoadConfig(
                base_url="https://api.example.test/api/v1",
                card_slug="sample",
                questions=(question,),
                dataset_sha256=hashlib.sha256(question.encode()).hexdigest(),
                requests=3,
                concurrency=2,
                run_id="unit-setup-outage",
            ),
            transport=httpx.MockTransport(handler),
        )
    )
    gate = evaluate_gate(
        report,
        GateThresholds(max_error_rate=0, max_ttft_p95_ms=5_000, max_total_p95_ms=10_000),
    )

    assert report["setup"]["failed_sessions"] == 2
    assert report["metrics"]["samples"] == 3
    assert report["metrics"]["errors"] == {"setup_http_503": 3}
    assert gate["passed"] is False


def test_load_questions_accepts_eval_case_format_without_echoing_content(tmp_path: Path) -> None:
    path = tmp_path / "eval.json"
    path.write_text(
        json.dumps({"version": "v1", "cases": [{"id": "one", "question": "Question?"}]}),
        encoding="utf-8",
    )

    questions, digest = load_questions(path)

    assert questions == ("Question?",)
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
