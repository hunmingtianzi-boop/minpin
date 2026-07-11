# HTTP / RAG performance harness

This directory contains two distinct gates:

- `python -m tools.perf.cli http ...` measures a deployed HTTP endpoint.
- `python -m tools.perf.cli rag ...` creates public visitor sessions and measures the
  complete consent/conversation/SSE answer flow. Time to first token is the first non-empty
  `message.delta`; total latency ends at `message.completed`.
- `python -m tools.perf.smoke ...` uses a loopback mock server to verify the harness,
  streaming parser and fail-closed gate in CI.

The mock smoke is not a production benchmark and cannot be used as V1.0 SLA evidence.
Acceptance commands, environment controls and report interpretation are documented in
`docs/18-性能压测与SLA验收.md`.

Reports intentionally omit request/response bodies, questions, tokens, header values and URL
queries. Only sanitized error categories are retained.
