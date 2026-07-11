from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from .runner import (
    GateThresholds,
    HttpLoadConfig,
    RagLoadConfig,
    build_ssl_context,
    concise_result,
    default_run_id,
    evaluate_gate,
    load_questions,
    run_http_load,
    run_rag_load,
    write_report,
)

HTTP_PROFILES: dict[str, dict[str, float | None]] = {
    "public-card": {"max_p75_ms": 2_500.0, "max_p95_ms": None},
    "admin-list": {"max_p75_ms": None, "max_p95_ms": 1_000.0},
    "custom": {"max_p75_ms": None, "max_p95_ms": None},
}
HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Repeatable HTTP and public RAG load runner with machine-readable gates."
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    http = subparsers.add_parser("http", help="Load one HTTP endpoint.")
    _add_common_workload(http)
    http.add_argument("--url", required=True)
    http.add_argument("--method", default="GET")
    http.add_argument("--profile", choices=sorted(HTTP_PROFILES), default="custom")
    http.add_argument(
        "--header-env",
        action="append",
        default=[],
        metavar="HEADER=ENV_VAR",
        help="Read a header value from an environment variable; values are never reported.",
    )
    http.add_argument("--body-file", type=Path)
    http.add_argument("--expected-status", type=int, action="append", default=[])
    http.add_argument("--max-p75-ms", type=float)
    http.add_argument("--max-p95-ms", type=float)

    rag = subparsers.add_parser(
        "rag",
        help="Load the full public visit/consent/conversation/SSE answer flow.",
    )
    _add_common_workload(rag)
    rag.add_argument("--base-url", required=True, help="API prefix, for example .../api/v1")
    rag.add_argument("--card-slug", required=True)
    rag.add_argument("--questions", required=True, type=Path)
    rag.add_argument("--max-ttft-p95-ms", type=float, default=5_000.0)
    rag.add_argument("--max-total-p95-ms", type=float, default=10_000.0)
    return parser


def _add_common_workload(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--requests", type=int, required=True)
    parser.add_argument("--concurrency", type=int, required=True)
    parser.add_argument("--warmup-requests", type=int, default=0)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--scenario", default="acceptance")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--ca-file", type=Path)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--min-success-rps", type=float)


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    run_id = args.run_id or default_run_id()
    verify = build_ssl_context(args.ca_file)
    if args.mode == "http":
        profile = HTTP_PROFILES[args.profile]
        max_p75 = args.max_p75_ms if args.max_p75_ms is not None else profile["max_p75_ms"]
        max_p95 = args.max_p95_ms if args.max_p95_ms is not None else profile["max_p95_ms"]
        body = _read_body(args.body_file)
        headers = _resolve_headers(args.header_env)
        config = HttpLoadConfig(
            url=args.url,
            requests=args.requests,
            concurrency=args.concurrency,
            warmup_requests=args.warmup_requests,
            timeout_seconds=args.timeout_seconds,
            method=args.method.upper(),
            headers=headers,
            body=body,
            expected_statuses=frozenset(args.expected_status) or None,
            scenario_name=args.scenario,
            run_id=run_id,
            verify=verify,
        )
        thresholds = GateThresholds(
            max_error_rate=args.max_error_rate,
            max_p75_ms=max_p75,
            max_p95_ms=max_p95,
            min_success_rps=args.min_success_rps,
        )
        report = await run_http_load(config)
    else:
        questions, digest = load_questions(args.questions)
        config = RagLoadConfig(
            base_url=args.base_url,
            card_slug=args.card_slug,
            questions=questions,
            dataset_sha256=digest,
            requests=args.requests,
            concurrency=args.concurrency,
            warmup_requests=args.warmup_requests,
            timeout_seconds=args.timeout_seconds,
            scenario_name=args.scenario,
            run_id=run_id,
            verify=verify,
        )
        thresholds = GateThresholds(
            max_error_rate=args.max_error_rate,
            max_ttft_p95_ms=args.max_ttft_p95_ms,
            max_total_p95_ms=args.max_total_p95_ms,
            min_success_rps=args.min_success_rps,
        )
        report = await run_rag_load(config)
    report["gate"] = evaluate_gate(report, thresholds)
    write_report(args.output, report)
    return report


def _read_body(path: Path | None) -> bytes | None:
    if path is None:
        return None
    body = path.read_bytes()
    if len(body) > 1_000_000:
        raise ValueError("HTTP request body exceeds 1 MB")
    return body


def _resolve_headers(values: list[str]) -> tuple[tuple[str, str], ...]:
    headers: dict[str, str] = {}
    for definition in values:
        name, separator, environment_name = definition.partition("=")
        if not separator or HEADER_NAME.fullmatch(name) is None or not environment_name:
            raise ValueError("--header-env must use HEADER=ENV_VAR")
        value = os.getenv(environment_name)
        if value is None:
            raise ValueError(f"required header environment variable is missing: {environment_name}")
        if "\r" in value or "\n" in value:
            raise ValueError(f"header environment variable contains a newline: {environment_name}")
        headers[name] = value
    return tuple(headers.items())


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = asyncio.run(_run(args))
    except (OSError, ValueError, RuntimeError) as exc:
        print(
            json.dumps(
                {"status": "configuration_or_runtime_error", "error_type": type(exc).__name__},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(concise_result(report), ensure_ascii=False, sort_keys=True))
    return 0 if report["gate"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
