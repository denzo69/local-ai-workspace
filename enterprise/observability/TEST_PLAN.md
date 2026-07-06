# Observability Test Plan

This test plan defines validation for the planned observability layer.

## Test categories

| Area | Tests |
|---|---|
| Metrics config | metrics disabled by default, enabled by env/config |
| Metrics endpoint | returns metrics when enabled, denied/hidden when disabled |
| HTTP metrics | request count, status code count, latency buckets |
| RAG metrics | retrieval count, hit/miss count, latency |
| Tool metrics | tool route count, risk-level count, failure count |
| Auth metrics | login success/failure count, CSRF failure count |
| Logging | structured JSON contains required fields |
| Sanitization | logs do not contain passwords, tokens, raw memory or document text |
| Tracing | request id/span context created and propagated in test mode |
| Health checks | live/ready/security status paths return deterministic output |

## Suggested test files

```text
tests/test_observability_metrics.py
tests/test_observability_logging.py
tests/test_observability_sanitization.py
tests/test_observability_health.py
tests/test_enterprise_observability_docs.py
```

## Golden test

1. enable metrics in test config
2. send a chat request with mocked model provider
3. trigger a RAG lookup and tool routing decision
4. read metrics endpoint
5. assert request, RAG and tool counters changed
6. assert no prompt/body/secret content appears in metrics or logs

## Negative tests

The sprint must include tests for:

- disabled metrics endpoint
- missing runtime metrics state
- logging with secret-like values
- model provider failure log sanitization
- RAG/tool failure metrics
- health readiness failure branch

## Done criteria

Sprint 4 is done when:

- metrics behavior is configurable
- logs are structured and sanitized
- core counters have tests
- health/readiness checks are deterministic
- docs explain local and production-like modes
- observability does not require external services for tests
