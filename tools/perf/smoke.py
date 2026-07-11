from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .runner import (
    GateThresholds,
    HttpLoadConfig,
    RagLoadConfig,
    default_run_id,
    evaluate_gate,
    run_http_load,
    run_rag_load,
    write_report,
)

SMOKE_DISCLAIMER = (
    "Loopback mock smoke validates the load harness, SSE parser and gate semantics only; "
    "it is not evidence that a deployed environment meets the V1.0 SLA."
)


class SmokeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    counter = 0
    counter_lock = threading.Lock()

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        if self.path == "/api/v1/health/live":
            self._json_response(200, {"status": "live"})
            return
        if self.path == "/api/v1/public/cards/ci-smoke":
            self._json_response(
                200,
                {
                    "data": {
                        "policy_versions": {
                            "privacy": "ci-privacy-v1",
                            "chat_notice": "ci-chat-v1",
                        }
                    }
                },
            )
            return
        self._json_response(404, {"error": {"code": "NOT_FOUND"}})

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
        body_length = int(self.headers.get("Content-Length", "0"))
        if body_length:
            self.rfile.read(body_length)
        if self.path == "/api/v1/public/cards/ci-smoke/visits":
            self._json_response(
                201,
                {
                    "data": {
                        "visit_id": str(uuid.uuid4()),
                        "visitor_session_token": "ci-smoke-visitor-token",
                        "expires_at": "2099-01-01T00:00:00Z",
                    }
                },
            )
            return
        if self.path == "/api/v1/public/cards/ci-smoke/consents":
            self._json_response(201, {"data": {"id": str(uuid.uuid4())}})
            return
        if self.path == "/api/v1/public/cards/ci-smoke/conversations":
            with self.counter_lock:
                type(self).counter += 1
                value = type(self).counter
            conversation_id = uuid.uuid5(uuid.NAMESPACE_URL, f"ci-conversation-{value}")
            self._json_response(
                201,
                {
                    "data": {
                        "id": str(conversation_id),
                        "status": "active",
                        "created_at": "2099-01-01T00:00:00Z",
                    }
                },
            )
            return
        if self.path.startswith("/api/v1/public/conversations/") and self.path.endswith(
            "/messages:stream"
        ):
            self._sse_response()
            return
        self._json_response(404, {"error": {"code": "NOT_FOUND"}})

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _json_response(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _sse_response(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        events = (
            ("message.started", {"message_id": str(uuid.uuid4()), "request_id": "ci-smoke"}),
            ("message.delta", {"text": "smoke answer"}),
            (
                "message.completed",
                {"message_id": str(uuid.uuid4()), "finish_reason": "stop", "lead_prompt": False},
            ),
        )
        for event, payload in events:
            self.wfile.write(
                f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n".encode()
            )
            self.wfile.flush()
            time.sleep(0.005)
        self.close_connection = True


async def run_smoke(base_url: str, run_id: str) -> dict[str, Any]:
    http_report = await run_http_load(
        HttpLoadConfig(
            url=f"{base_url}/health/live",
            requests=12,
            concurrency=3,
            warmup_requests=2,
            timeout_seconds=3,
            scenario_name="ci-loopback-http",
            run_id=run_id,
        )
    )
    http_report["gate"] = evaluate_gate(
        http_report,
        GateThresholds(max_error_rate=0, max_p95_ms=2_000),
    )

    question = "CI smoke question"
    rag_report = await run_rag_load(
        RagLoadConfig(
            base_url=base_url,
            card_slug="ci-smoke",
            questions=(question,),
            dataset_sha256=hashlib.sha256(question.encode()).hexdigest(),
            requests=4,
            concurrency=2,
            warmup_requests=2,
            timeout_seconds=3,
            scenario_name="ci-loopback-rag",
            run_id=run_id,
        )
    )
    rag_report["gate"] = evaluate_gate(
        rag_report,
        GateThresholds(
            max_error_rate=0,
            max_ttft_p95_ms=2_000,
            max_total_p95_ms=2_000,
        ),
    )
    return {
        "schema_version": "cf-perf-smoke/v1",
        "disclaimer": SMOKE_DISCLAIMER,
        "gate": {
            "passed": http_report["gate"]["passed"] and rag_report["gate"]["passed"],
            "http_passed": http_report["gate"]["passed"],
            "rag_passed": rag_report["gate"]["passed"],
        },
        "reports": {"http": http_report, "rag": rag_report},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic loopback perf smoke gate.")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", 0), SmokeHandler)
    thread = threading.Thread(target=server.serve_forever, name="perf-smoke-server", daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        report = asyncio.run(run_smoke(f"http://{host}:{port}/api/v1", default_run_id()))
        write_report(args.output, report)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    print(
        json.dumps(
            {
                "gate_passed": report["gate"]["passed"],
                "disclaimer": SMOKE_DISCLAIMER,
                "output": str(args.output),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["gate"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
