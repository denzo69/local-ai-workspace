# Observability Architecture

This document describes the planned observability architecture for Local AI Workspace Enterprise Edition.

## Design principles

- Local development must work without external observability services.
- Metrics and logs must not leak secrets, tokens or personal memory content.
- Observability must help debug AI routing, RAG and tool execution without exposing private data.
- Production-like deployments should be able to export metrics and traces.
- Security-relevant events should connect to audit logging without duplicating sensitive payloads.

## Metrics model

Suggested metric groups:

| Metric group | Examples |
|---|---|
| HTTP | request count, status codes, latency |
| Chat/model | model request count, model latency, fallback count |
| RAG | retrieval count, hit/miss count, source count, retrieval latency |
| Memory | read/write/delete/export counts |
| Tools | routed tool count, tool failures, tool latency |
| Safety | prompt-injection detections, blocked destructive requests |
| Auth | login success/failure, CSRF failures |
| Audit | audit append count, audit verification status |
| Backup | backup creation count, backup failures |

## Suggested endpoint

```text
GET /metrics
```

The endpoint should be optional and configurable.

Suggested config:

```text
SADE_METRICS_ENABLED=false
```

## Structured logging

Suggested JSON log fields:

```json
{
  "timestamp": "iso timestamp",
  "level": "INFO|WARNING|ERROR",
  "event": "chat.request",
  "request_id": "req_...",
  "user_id": "user_...",
  "workspace_id": "ws_...",
  "route": "/chat",
  "duration_ms": 0,
  "status_code": 200
}
```

Never log:

- passwords
- tokens
- refresh tokens
- CSRF tokens
- raw personal memory content
- uploaded document contents
- `.env` values

## Tracing plan

Trace boundaries:

```text
HTTP request
  -> auth/session check
  -> response planning
  -> memory lookup
  -> RAG retrieval
  -> tool routing
  -> model provider call
  -> output validation
  -> audit append
```

Suggested future technology:

- OpenTelemetry-compatible spans
- optional exporter configuration
- disabled-by-default local mode

## Dashboard outline

Suggested Grafana panels:

- request rate
- error rate
- p95 latency
- model latency
- RAG hit/miss ratio
- tool calls by risk level
- prompt-injection blocks
- auth failures
- audit verification status
- backup success/failure count

## Health and readiness

Potential endpoints:

```text
GET /health/live
GET /health/ready
GET /health/security
```

Readiness should check:

- app config loaded
- runtime directories accessible
- model provider status known
- audit log writable
- memory/RAG paths available

## Open questions

- Should `/metrics` require auth in local mode?
- Should security metrics be separate from general metrics?
- Should request IDs be generated at middleware level?
- Which fields should be included when workspace support is disabled?
