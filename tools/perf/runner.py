from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import platform
import re
import ssl
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

REPORT_SCHEMA_VERSION = "cf-perf/v1"
SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
SAFE_ERROR_CODE = re.compile(r"^[A-Za-z0-9._-]{1,96}$")


class LoadProtocolError(RuntimeError):
    """A target response did not satisfy the expected public API protocol."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = _safe_error_code(code)


@dataclass(frozen=True, slots=True)
class GateThresholds:
    max_error_rate: float = 0.01
    max_p75_ms: float | None = None
    max_p95_ms: float | None = None
    max_ttft_p95_ms: float | None = None
    max_total_p95_ms: float | None = None
    min_success_rps: float | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.max_error_rate <= 1:
            raise ValueError("max_error_rate must be between 0 and 1")
        for value in (
            self.max_p75_ms,
            self.max_p95_ms,
            self.max_ttft_p95_ms,
            self.max_total_p95_ms,
        ):
            if value is not None and value <= 0:
                raise ValueError("latency thresholds must be positive")
        if self.min_success_rps is not None and self.min_success_rps <= 0:
            raise ValueError("min_success_rps must be positive")

    def to_dict(self) -> dict[str, float | None]:
        return {
            "max_error_rate": self.max_error_rate,
            "max_p75_ms": self.max_p75_ms,
            "max_p95_ms": self.max_p95_ms,
            "max_ttft_p95_ms": self.max_ttft_p95_ms,
            "max_total_p95_ms": self.max_total_p95_ms,
            "min_success_rps": self.min_success_rps,
        }


@dataclass(frozen=True, slots=True)
class HttpLoadConfig:
    url: str
    requests: int
    concurrency: int
    warmup_requests: int = 0
    timeout_seconds: float = 15.0
    method: str = "GET"
    headers: tuple[tuple[str, str], ...] = ()
    body: bytes | None = None
    expected_statuses: frozenset[int] | None = None
    scenario_name: str = "http"
    run_id: str = ""
    verify: bool | ssl.SSLContext = True

    def __post_init__(self) -> None:
        _validate_target_url(self.url)
        _validate_workload(self.requests, self.concurrency, self.warmup_requests)
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not re.fullmatch(r"[A-Z]+", self.method.upper()):
            raise ValueError("method must contain only uppercase letters")
        _validate_run_id(self.run_id)
        _validate_label(self.scenario_name, "scenario_name")


@dataclass(frozen=True, slots=True)
class RagLoadConfig:
    base_url: str
    card_slug: str
    questions: tuple[str, ...]
    dataset_sha256: str
    requests: int
    concurrency: int
    warmup_requests: int = 0
    timeout_seconds: float = 20.0
    scenario_name: str = "rag"
    run_id: str = ""
    verify: bool | ssl.SSLContext = True

    def __post_init__(self) -> None:
        _validate_target_url(self.base_url)
        _validate_workload(self.requests, self.concurrency, self.warmup_requests)
        if re.fullmatch(r"[a-z0-9][a-z0-9-]{1,94}[a-z0-9]", self.card_slug.strip()) is None:
            raise ValueError("card_slug does not satisfy the public slug contract")
        if not self.questions:
            raise ValueError("questions cannot be empty")
        if any(not question.strip() or len(question) > 2_000 for question in self.questions):
            raise ValueError("every question must contain 1-2000 characters")
        if not re.fullmatch(r"[a-f0-9]{64}", self.dataset_sha256):
            raise ValueError("dataset_sha256 must be a lowercase SHA-256 digest")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        _validate_run_id(self.run_id)
        _validate_label(self.scenario_name, "scenario_name")


@dataclass(frozen=True, slots=True)
class Sample:
    ok: bool
    total_ms: float
    ttft_ms: float | None = None
    status_code: int | None = None
    bytes_received: int = 0
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class RagSession:
    token: str
    conversation_id: str


def load_questions(path: Path) -> tuple[tuple[str, ...], str]:
    raw = path.read_bytes()
    if len(raw) > 5_000_000:
        raise ValueError("question dataset exceeds 5 MB")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("question dataset must be valid UTF-8 JSON") from exc

    if isinstance(payload, list):
        questions = payload
    elif isinstance(payload, dict) and isinstance(payload.get("cases"), list):
        questions = [
            item.get("question") if isinstance(item, dict) else None
            for item in payload["cases"]
        ]
    else:
        raise ValueError(
            "question dataset must be a string array or an object with cases[].question"
        )
    if not questions or any(not isinstance(value, str) for value in questions):
        raise ValueError("question dataset contains an invalid question")
    normalized = tuple(value.strip() for value in questions)
    if any(not value or len(value) > 2_000 for value in normalized):
        raise ValueError("every question must contain 1-2000 characters")
    return normalized, hashlib.sha256(raw).hexdigest()


async def run_http_load(
    config: HttpLoadConfig,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    timeout = httpx.Timeout(config.timeout_seconds)
    limits = httpx.Limits(
        max_connections=max(config.concurrency * 2, 10),
        max_keepalive_connections=max(config.concurrency, 5),
    )
    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        verify=config.verify,
        transport=transport,
        follow_redirects=False,
    ) as client:
        warmup = await _run_http_samples(client, config, config.warmup_requests)
        measured_started = time.perf_counter()
        samples = await _run_http_samples(client, config, config.requests)
        measured_seconds = max(time.perf_counter() - measured_started, 0.000_001)

    body_digest = hashlib.sha256(config.body).hexdigest() if config.body is not None else None
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "mode": "http",
        "scenario": config.scenario_name,
        "run_id": config.run_id,
        "started_at": started_at.isoformat(),
        "target": _sanitized_target(config.url),
        "environment": _environment_metadata(),
        "workload": {
            "requests": config.requests,
            "concurrency": config.concurrency,
            "warmup_requests": config.warmup_requests,
            "timeout_seconds": config.timeout_seconds,
            "method": config.method.upper(),
            "header_names": sorted(name.lower() for name, _ in config.headers),
            "body_bytes": len(config.body) if config.body is not None else 0,
            "body_sha256": body_digest,
            "expected_statuses": sorted(config.expected_statuses or ()),
        },
        "warmup": _warmup_summary(warmup),
        "metrics": _metrics(samples, measured_seconds, include_ttft=False),
    }


async def run_rag_load(
    config: RagLoadConfig,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    timeout = httpx.Timeout(config.timeout_seconds)
    limits = httpx.Limits(
        max_connections=max(config.concurrency * 2, 10),
        max_keepalive_connections=max(config.concurrency, 5),
    )
    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        verify=config.verify,
        transport=transport,
        follow_redirects=False,
    ) as client:
        setup_started = time.perf_counter()
        try:
            policy_versions = await _load_policy_versions(client, config)
        except Exception as exc:  # A setup outage must still produce a failed gate report.
            sessions: list[RagSession | BaseException] = [exc] * config.concurrency
        else:
            sessions = await asyncio.gather(
                *(
                    _create_rag_session(client, config, policy_versions, virtual_user)
                    for virtual_user in range(config.concurrency)
                ),
                return_exceptions=True,
            )
        setup_seconds = max(time.perf_counter() - setup_started, 0.000_001)

        warmup_samples = await _run_rag_phase(
            client,
            config,
            sessions,
            config.warmup_requests,
            phase="warmup",
        )
        measured_started = time.perf_counter()
        samples = await _run_rag_phase(
            client,
            config,
            sessions,
            config.requests,
            phase="measured",
        )
        measured_seconds = max(time.perf_counter() - measured_started, 0.000_001)

    setup_errors = Counter(
        _exception_error_code(value) for value in sessions if isinstance(value, BaseException)
    )
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "mode": "rag",
        "scenario": config.scenario_name,
        "run_id": config.run_id,
        "started_at": started_at.isoformat(),
        "target": _sanitized_target(config.base_url),
        "environment": _environment_metadata(),
        "workload": {
            "requests": config.requests,
            "concurrent_conversations": config.concurrency,
            "warmup_requests": config.warmup_requests,
            "timeout_seconds": config.timeout_seconds,
            "card_slug": config.card_slug,
            "question_count": len(config.questions),
            "dataset_sha256": config.dataset_sha256,
            "session_model": "one conversation per virtual user",
        },
        "setup": {
            "duration_seconds": round(setup_seconds, 6),
            "successful_sessions": sum(isinstance(value, RagSession) for value in sessions),
            "failed_sessions": sum(isinstance(value, BaseException) for value in sessions),
            "errors": dict(sorted(setup_errors.items())),
        },
        "warmup": _warmup_summary(warmup_samples),
        "metrics": _metrics(samples, measured_seconds, include_ttft=True),
    }


def evaluate_gate(report: dict[str, Any], thresholds: GateThresholds) -> dict[str, Any]:
    metrics = report["metrics"]
    failures: list[str] = []
    if metrics["samples"] <= 0:
        failures.append("no measured samples")
    if metrics["successes"] <= 0:
        failures.append("no successful samples")
    if metrics["error_rate"] > thresholds.max_error_rate:
        failures.append(
            f"error_rate {metrics['error_rate']:.6f} exceeds {thresholds.max_error_rate:.6f}"
        )

    latency = metrics["latency_ms"]
    _check_maximum(failures, "latency.p75_ms", latency["p75"], thresholds.max_p75_ms)
    _check_maximum(failures, "latency.p95_ms", latency["p95"], thresholds.max_p95_ms)
    if report["mode"] == "rag":
        ttft = metrics["ttft_ms"]
        _check_maximum(
            failures,
            "ttft.p95_ms",
            ttft["p95"],
            thresholds.max_ttft_p95_ms,
        )
        _check_maximum(
            failures,
            "total.p95_ms",
            latency["p95"],
            thresholds.max_total_p95_ms,
        )
    if (
        thresholds.min_success_rps is not None
        and metrics["success_rps"] < thresholds.min_success_rps
    ):
        failures.append(
            f"success_rps {metrics['success_rps']:.6f} is below "
            f"{thresholds.min_success_rps:.6f}"
        )
    return {
        "passed": not failures,
        "thresholds": thresholds.to_dict(),
        "failures": failures,
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


async def _run_http_samples(
    client: httpx.AsyncClient,
    config: HttpLoadConfig,
    count: int,
) -> list[Sample]:
    results: list[Sample | None] = [None] * count
    next_index = 0

    async def worker() -> None:
        nonlocal next_index
        while True:
            index = next_index
            if index >= count:
                return
            next_index += 1
            results[index] = await _http_sample(client, config)

    await asyncio.gather(*(worker() for _ in range(min(config.concurrency, count))))
    return [sample for sample in results if sample is not None]


async def _http_sample(client: httpx.AsyncClient, config: HttpLoadConfig) -> Sample:
    started = time.perf_counter()
    try:
        response = await client.request(
            config.method.upper(),
            config.url,
            headers=dict(config.headers),
            content=config.body,
        )
        elapsed_ms = (time.perf_counter() - started) * 1_000
        expected = (
            response.status_code in config.expected_statuses
            if config.expected_statuses
            else 200 <= response.status_code < 300
        )
        return Sample(
            ok=expected,
            total_ms=elapsed_ms,
            status_code=response.status_code,
            bytes_received=len(response.content),
            error_code=None if expected else f"http_{response.status_code}",
        )
    except httpx.TimeoutException:
        return Sample(
            ok=False,
            total_ms=(time.perf_counter() - started) * 1_000,
            error_code="timeout",
        )
    except httpx.HTTPError:
        return Sample(
            ok=False,
            total_ms=(time.perf_counter() - started) * 1_000,
            error_code="network_error",
        )


async def _load_policy_versions(
    client: httpx.AsyncClient,
    config: RagLoadConfig,
) -> tuple[str, str]:
    slug = quote(config.card_slug.strip(), safe="")
    payload = await _request_json(
        client,
        "GET",
        f"{config.base_url.rstrip('/')}/public/cards/{slug}",
    )
    try:
        versions = payload["data"]["policy_versions"]
        privacy = versions["privacy"]
        chat_notice = versions["chat_notice"]
    except (KeyError, TypeError) as exc:
        raise LoadProtocolError("invalid_policy_versions") from exc
    if (
        not isinstance(privacy, str)
        or not privacy
        or not isinstance(chat_notice, str)
        or not chat_notice
    ):
        raise LoadProtocolError("invalid_policy_versions")
    return privacy, chat_notice


async def _create_rag_session(
    client: httpx.AsyncClient,
    config: RagLoadConfig,
    policy_versions: tuple[str, str],
    virtual_user: int,
) -> RagSession:
    privacy_version, chat_notice_version = policy_versions
    slug = quote(config.card_slug.strip(), safe="")
    base = config.base_url.rstrip("/")
    nonce = uuid.uuid4().hex
    visit = await _request_json(
        client,
        "POST",
        f"{base}/public/cards/{slug}/visits",
        headers={"Idempotency-Key": _idempotency_key(config.run_id, virtual_user, nonce, "visit")},
        json_body={
            "source": "performance_acceptance",
            "campaign": config.run_id or None,
            "privacy_notice_version": privacy_version,
        },
        expected_status=201,
    )
    try:
        token = visit["data"]["visitor_session_token"]
    except (KeyError, TypeError) as exc:
        raise LoadProtocolError("invalid_visit_response") from exc
    if not isinstance(token, str) or not token:
        raise LoadProtocolError("invalid_visit_response")
    auth_headers = {"Authorization": f"Bearer {token}"}
    await _request_json(
        client,
        "POST",
        f"{base}/public/cards/{slug}/consents",
        headers={
            **auth_headers,
            "Idempotency-Key": _idempotency_key(config.run_id, virtual_user, nonce, "consent"),
        },
        json_body={
            "scope": "chat_notice",
            "policy_version": chat_notice_version,
            "granted": True,
        },
        expected_status=201,
    )
    conversation = await _request_json(
        client,
        "POST",
        f"{base}/public/cards/{slug}/conversations",
        headers={
            **auth_headers,
            "Idempotency-Key": _idempotency_key(
                config.run_id,
                virtual_user,
                nonce,
                "conversation",
            ),
        },
        json_body={"chat_notice_version": chat_notice_version},
        expected_status=201,
    )
    try:
        conversation_id = conversation["data"]["id"]
    except (KeyError, TypeError) as exc:
        raise LoadProtocolError("invalid_conversation_response") from exc
    if not isinstance(conversation_id, str) or not conversation_id:
        raise LoadProtocolError("invalid_conversation_response")
    return RagSession(token=token, conversation_id=conversation_id)


async def _run_rag_phase(
    client: httpx.AsyncClient,
    config: RagLoadConfig,
    sessions: list[RagSession | BaseException],
    count: int,
    *,
    phase: Literal["warmup", "measured"],
) -> list[Sample]:
    results: list[Sample | None] = [None] * count

    async def virtual_user_worker(virtual_user: int) -> None:
        session = sessions[virtual_user]
        assigned = range(virtual_user, count, config.concurrency)
        if isinstance(session, BaseException):
            code = _exception_error_code(session)
            for index in assigned:
                results[index] = Sample(ok=False, total_ms=0.0, error_code=code)
            return
        for index in assigned:
            question = config.questions[index % len(config.questions)]
            results[index] = await _rag_sample(
                client,
                config,
                session,
                virtual_user=virtual_user,
                sample_index=index,
                phase=phase,
                question=question,
            )

    await asyncio.gather(
        *(virtual_user_worker(virtual_user) for virtual_user in range(config.concurrency))
    )
    return [sample for sample in results if sample is not None]


async def _rag_sample(
    client: httpx.AsyncClient,
    config: RagLoadConfig,
    session: RagSession,
    *,
    virtual_user: int,
    sample_index: int,
    phase: str,
    question: str,
) -> Sample:
    started = time.perf_counter()
    url = (
        f"{config.base_url.rstrip('/')}/public/conversations/"
        f"{quote(session.conversation_id, safe='')}/messages:stream"
    )
    nonce = uuid.uuid4().hex
    try:
        async with client.stream(
            "POST",
            url,
            headers={
                "Accept": "text/event-stream",
                "Authorization": f"Bearer {session.token}",
                "Idempotency-Key": _idempotency_key(
                    config.run_id,
                    virtual_user,
                    nonce,
                    f"{phase}-{sample_index}",
                ),
            },
            json={"content": question},
        ) as response:
            if response.status_code != 200:
                await response.aread()
                return Sample(
                    ok=False,
                    total_ms=(time.perf_counter() - started) * 1_000,
                    status_code=response.status_code,
                    bytes_received=len(response.content),
                    error_code=f"http_{response.status_code}",
                )
            content_type = response.headers.get("content-type", "").lower()
            if not content_type.startswith("text/event-stream"):
                await response.aread()
                raise LoadProtocolError("invalid_sse_content_type")
            return await _consume_sse(response, started)
    except LoadProtocolError as exc:
        return Sample(
            ok=False,
            total_ms=(time.perf_counter() - started) * 1_000,
            status_code=200,
            error_code=exc.code,
        )
    except httpx.TimeoutException:
        return Sample(
            ok=False,
            total_ms=(time.perf_counter() - started) * 1_000,
            error_code="timeout",
        )
    except httpx.HTTPError:
        return Sample(
            ok=False,
            total_ms=(time.perf_counter() - started) * 1_000,
            error_code="network_error",
        )


async def _consume_sse(response: httpx.Response, started: float) -> Sample:
    event_name = ""
    data_lines: list[str] = []
    saw_started = False
    ttft_ms: float | None = None
    bytes_received = 0

    async for line in response.aiter_lines():
        bytes_received += len(line.encode("utf-8")) + 1
        if line.startswith(":"):
            continue
        if line == "":
            if not event_name:
                data_lines.clear()
                continue
            payload = "\n".join(data_lines)
            if event_name == "message.started":
                saw_started = True
            elif event_name == "message.delta":
                if not saw_started:
                    raise LoadProtocolError("sse_delta_before_started")
                try:
                    delta = json.loads(payload)
                except json.JSONDecodeError as exc:
                    raise LoadProtocolError("invalid_sse_delta") from exc
                if (
                    not isinstance(delta, dict)
                    or not isinstance(delta.get("text"), str)
                    or not delta["text"]
                ):
                    raise LoadProtocolError("invalid_sse_delta")
                if ttft_ms is None:
                    ttft_ms = (time.perf_counter() - started) * 1_000
            elif event_name == "message.error":
                code = "message_error"
                try:
                    value = json.loads(payload)
                    if isinstance(value, dict) and isinstance(value.get("code"), str):
                        code = f"message_error_{value['code']}"
                except json.JSONDecodeError:
                    code = "invalid_sse_error"
                return Sample(
                    ok=False,
                    total_ms=(time.perf_counter() - started) * 1_000,
                    status_code=response.status_code,
                    bytes_received=bytes_received,
                    error_code=_safe_error_code(code),
                )
            elif event_name == "message.completed":
                if not saw_started:
                    raise LoadProtocolError("sse_completed_before_started")
                if ttft_ms is None:
                    raise LoadProtocolError("sse_completed_without_delta")
                return Sample(
                    ok=True,
                    total_ms=(time.perf_counter() - started) * 1_000,
                    ttft_ms=ttft_ms,
                    status_code=response.status_code,
                    bytes_received=bytes_received,
                )
            event_name = ""
            data_lines.clear()
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    raise LoadProtocolError("sse_stream_incomplete")


async def _request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    expected_status: int = 200,
) -> dict[str, Any]:
    try:
        response = await client.request(method, url, headers=headers, json=json_body)
    except httpx.TimeoutException as exc:
        raise LoadProtocolError("setup_timeout") from exc
    except httpx.HTTPError as exc:
        raise LoadProtocolError("setup_network_error") from exc
    if response.status_code != expected_status:
        raise LoadProtocolError(f"setup_http_{response.status_code}")
    try:
        value = response.json()
    except json.JSONDecodeError as exc:
        raise LoadProtocolError("setup_invalid_json") from exc
    if not isinstance(value, dict):
        raise LoadProtocolError("setup_invalid_json")
    return value


def _metrics(
    samples: list[Sample],
    duration_seconds: float,
    *,
    include_ttft: bool,
) -> dict[str, Any]:
    successful = [sample for sample in samples if sample.ok]
    errors = Counter(sample.error_code or "unknown_error" for sample in samples if not sample.ok)
    statuses = Counter(
        str(sample.status_code) for sample in samples if sample.status_code is not None
    )
    result: dict[str, Any] = {
        "samples": len(samples),
        "successes": len(successful),
        "errors_count": len(samples) - len(successful),
        "error_rate": round((len(samples) - len(successful)) / len(samples), 6) if samples else 1.0,
        "duration_seconds": round(duration_seconds, 6),
        "attempt_rps": round(len(samples) / duration_seconds, 6),
        "success_rps": round(len(successful) / duration_seconds, 6),
        "bytes_received": sum(sample.bytes_received for sample in samples),
        "status_codes": dict(sorted(statuses.items())),
        "errors": dict(sorted(errors.items())),
        "latency_ms": _distribution([sample.total_ms for sample in successful]),
    }
    if include_ttft:
        result["ttft_ms"] = _distribution(
            [sample.ttft_ms for sample in successful if sample.ttft_ms is not None]
        )
    return result


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "p50": None,
            "p75": None,
            "p95": None,
            "p99": None,
            "max": None,
        }
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "min": round(ordered[0], 3),
        "p50": round(_nearest_rank(ordered, 0.50), 3),
        "p75": round(_nearest_rank(ordered, 0.75), 3),
        "p95": round(_nearest_rank(ordered, 0.95), 3),
        "p99": round(_nearest_rank(ordered, 0.99), 3),
        "max": round(ordered[-1], 3),
    }


def _nearest_rank(ordered: list[float], quantile: float) -> float:
    if not ordered:
        raise ValueError("ordered values cannot be empty")
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


def _warmup_summary(samples: list[Sample]) -> dict[str, Any]:
    errors = Counter(sample.error_code or "unknown_error" for sample in samples if not sample.ok)
    return {
        "samples": len(samples),
        "errors_count": sum(errors.values()),
        "errors": dict(sorted(errors.items())),
    }


def _check_maximum(
    failures: list[str],
    name: str,
    actual: float | None,
    threshold: float | None,
) -> None:
    if threshold is None:
        return
    if actual is None:
        failures.append(f"{name} is unavailable")
    elif actual > threshold:
        failures.append(f"{name} {actual:.3f} exceeds {threshold:.3f}")


def _environment_metadata() -> dict[str, str]:
    return {
        "environment": os.getenv("PERF_ENVIRONMENT", "unspecified"),
        "build_id": os.getenv("PERF_BUILD_ID") or os.getenv("GITHUB_SHA", "unknown"),
        "python": platform.python_version(),
        "os": platform.system(),
        "architecture": platform.machine(),
    }


def _sanitized_target(value: str) -> dict[str, Any]:
    parsed = urlsplit(value)
    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    port = f":{parsed.port}" if parsed.port is not None else ""
    return {
        "url": urlunsplit((parsed.scheme, f"{hostname}{port}", parsed.path or "/", "", "")),
        "query_present": bool(parsed.query),
    }


def _validate_target_url(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("target must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("target URL must not contain credentials")
    if parsed.fragment:
        raise ValueError("target URL must not contain a fragment")


def _validate_workload(requests: int, concurrency: int, warmup_requests: int) -> None:
    if requests <= 0 or requests > 1_000_000:
        raise ValueError("requests must be between 1 and 1,000,000")
    if concurrency <= 0 or concurrency > 1_000:
        raise ValueError("concurrency must be between 1 and 1,000")
    if concurrency > requests:
        raise ValueError("concurrency cannot exceed measured requests")
    if warmup_requests < 0 or warmup_requests > 100_000:
        raise ValueError("warmup_requests must be between 0 and 100,000")


def _validate_run_id(run_id: str) -> None:
    if run_id and SAFE_RUN_ID.fullmatch(run_id) is None:
        raise ValueError("run_id must use 1-64 letters, digits, dots, underscores or hyphens")


def _validate_label(value: str, name: str) -> None:
    if not value.strip() or len(value) > 128 or any(ord(character) < 32 for character in value):
        raise ValueError(f"{name} must contain 1-128 printable characters")


def _idempotency_key(run_id: str, virtual_user: int, nonce: str, suffix: str) -> str:
    prefix = run_id or "run"
    digest = hashlib.sha256(
        f"{prefix}:{virtual_user}:{nonce}:{suffix}".encode("utf-8")
    ).hexdigest()[:40]
    return f"perf-{digest}"


def _safe_error_code(value: str) -> str:
    normalized = value[:96]
    return normalized if SAFE_ERROR_CODE.fullmatch(normalized) else "protocol_error"


def _exception_error_code(value: BaseException) -> str:
    if isinstance(value, LoadProtocolError):
        return value.code
    if isinstance(value, httpx.TimeoutException):
        return "setup_timeout"
    if isinstance(value, httpx.HTTPError):
        return "setup_network_error"
    return "setup_error"


def default_run_id() -> str:
    return f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"


def build_ssl_context(ca_file: Path | None) -> bool | ssl.SSLContext:
    if ca_file is None:
        return True
    return ssl.create_default_context(cafile=str(ca_file))


def concise_result(report: dict[str, Any]) -> dict[str, Any]:
    metrics = report["metrics"]
    result: dict[str, Any] = {
        "mode": report["mode"],
        "samples": metrics["samples"],
        "successes": metrics["successes"],
        "error_rate": metrics["error_rate"],
        "p95_ms": metrics["latency_ms"]["p95"],
        "success_rps": metrics["success_rps"],
        "gate_passed": report.get("gate", {}).get("passed"),
    }
    if report["mode"] == "rag":
        result["ttft_p95_ms"] = metrics["ttft_ms"]["p95"]
    return result


__all__ = [
    "GateThresholds",
    "HttpLoadConfig",
    "RagLoadConfig",
    "build_ssl_context",
    "concise_result",
    "default_run_id",
    "evaluate_gate",
    "load_questions",
    "run_http_load",
    "run_rag_load",
    "write_report",
]
