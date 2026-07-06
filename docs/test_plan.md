# Test Plan — Local AI Workspace

This checklist follows the project architecture: FastAPI API, RAG, memory, tool calling, error handling, security and lightweight performance.

Use the Status column for manual review notes such as `PASS`, `FAIL`, `TODO` or `N/A`.

| Category | Test case | Description | Expected result | Status |
| --- | --- | --- | --- | --- |
| API — basic routes | `GET /health` | Service returns health status | `200` and JSON status payload | TODO |
| API — query | `POST /query` with short prompt | Normal user query | Returns an assistant response | TODO |
| API — validation | `POST /query` with empty prompt | Input validation | `400` or structured validation error | TODO |
| API — validation | `POST /query` with too-long prompt | Input size boundary | `413` or project-specific validation error | TODO |
| RAG — ingest | `POST /documents` | Ingest a document | `200` and document/source identifier | TODO |
| RAG — ingest validation | `POST /documents` with invalid payload | Payload validation | `400` or structured validation error | TODO |
| RAG — retrieval | `POST /query` with indexed document | Question answered from document | Answer includes document-grounded content/source boundary | TODO |
| RAG — fallback | `POST /query` without relevant document | Retrieval fallback | Safe fallback or model answer with uncertainty | TODO |
| Memory — session | Two related `POST /query` calls | Second query can use first context | Relevant previous context is available when allowed | TODO |
| Memory — reset | Delete/reset memory endpoint | Clear memory state | Memory is cleared and later queries do not use old context | TODO |
| Tool calling | Valid tool request | Tool execution path | Returns validated tool output | TODO |
| Tool calling | Invalid tool schema | Schema validation | `400` or safe validation error | TODO |
| Tool orchestration | Mocked LLM -> tool -> answer | End-to-end tool chain without real LLM | Tool result is incorporated into final response | TODO |
| Error handling | Mock timeout | Simulate slow LLM/tool call | Timeout is handled with a clear error response | TODO |
| Error handling | Ollama offline | Mock provider failure | Clear provider error or fallback behavior | TODO |
| Security | SQL injection-style input | Parameter safety | No state mutation; safe rejection or normal sanitized handling | TODO |
| Security | Path traversal | File path boundary | Access is denied outside allowed project paths | TODO |
| Security | Rate limit, if enabled | Too many requests | `429` or documented throttle behavior | TODO |
| Performance | 10-20 concurrent requests | Lightweight load smoke test | Service remains responsive and does not crash | TODO |
| Coverage | Full suite with coverage | CI coverage gate | Coverage stays at or above current threshold | TODO |

## Coverage targets

Raise coverage gates gradually:

1. `60%` — baseline regression guard.
2. `75%` — practical dev-team gate.
3. `85%` — strong portfolio and small-service quality gate.
4. `90%+` — advanced target once edge paths are mature.

Avoid forcing `100%` unless every remaining uncovered path is meaningful and maintainable to test.
