# CI/CD Improvement Roadmap

Goal: raise Local AI Workspace to a **small production-team** CI/CD level without adding enterprise-level complexity too early.

## Current maturity

Local AI Workspace is already past the prototype stage: it has automated tests, branch coverage, GitHub Actions, documentation, auth/session tests, RAG tests, routing tests and portfolio release hygiene.

The next target is **Level 3: Small production service readiness**.

## Maturity model

| Level | Description | Project status |
| --- | --- | --- |
| 1. Prototype | Ad-hoc tests, local-only checks, no reliable CI | Already passed |
| 2. Dev-team tool | Basic CI, automated tests, simple Docker support, repeatable local setup | Mostly reached |
| 3. Small production service | Matrix builds, quality checks, dependency audit, coverage threshold, tag-based release image | Current roadmap target |
| 4. Mature production ecosystem | Observability, load-test pipeline, rollback strategy, dev/stage/prod environments | Future option only if the project grows |

## Phase 1 — CI robustness

### Actions runtime

- Use Node 24-compatible action versions where available.
- Avoid deprecated Node 20 action warnings in GitHub Actions.

### Python matrix

- Run tests on Python `3.10`, `3.11` and `3.12`.
- Keep `fail-fast: false` so one version failing does not hide results from the others.

### OS strategy

- Start with `ubuntu-latest` as the primary CI target.
- Keep the workflow matrix shape ready for adding `windows-latest` or `macos-latest` later if needed.

## Phase 2 — Quality and security

### Linting

- Add Ruff as the fast first-pass linter.
- Start as an advisory check if the existing codebase needs gradual cleanup.
- Promote to a blocking check once the initial findings are fixed.

### Type checking

- Add mypy as an advisory type-safety check.
- Keep strictness moderate at first.
- Increase strictness module-by-module instead of trying to make the whole AI workspace strict in one jump.

### Dependency audit

- Add `pip-audit` for dependency vulnerability checks.
- Start advisory while dependency pinning matures.
- Promote to blocking once the project has stable dependency policy.

## Phase 3 — Test and coverage policy

### Coverage threshold

- Enforce a low initial threshold such as `60%` so CI prevents accidental collapse.
- Raise gradually as the suite stabilizes:
  - `60%` baseline gate
  - `75%` dev-team quality gate
  - `85%` strong portfolio / production-readiness gate
  - `90%+` advanced target

### Coverage artifacts

- Upload `coverage.xml`, HTML coverage and pytest output as GitHub Actions artifacts.
- Keep reports visible for debugging failed or borderline runs.

## Phase 4 — Release pipeline

### Tag-based release

- Trigger release image builds from tags matching `v*`.
- Keep normal push and pull-request runs focused on tests and quality.

### Docker image

- Build the Docker image from the repository Dockerfile.
- Push tagged images to GitHub Container Registry (`ghcr.io`).
- Publish both the version tag and `latest` for simple demos.

### Later deploy targets

Optional future deployment targets, only if the project becomes useful beyond local demos:

- Railway
- Fly.io
- Render
- A private VPS

## Test coverage roadmap

### Stage 1 — API and regression coverage

- Test primary FastAPI routes with `TestClient`.
- Cover happy paths and error paths:
  - empty prompts
  - too-long prompts
  - missing parameters
  - auth/session failures
  - invalid uploads

### Stage 2 — RAG

- Add document ingestion tests with a mocked embedder.
- Add golden retrieval tests: query -> expected source document.
- Simulate slow model or embedding calls and verify timeout behavior.

### Stage 3 — Memory

- Test user/session memory retention and reset behavior.
- Test persistence if the backend uses SQLite or file storage.
- Cover edge cases:
  - large memory sets
  - deletion
  - stale entries
  - malformed memory files

### Stage 4 — Tool calling

- Validate tool schemas and input/output contracts.
- Add mocked orchestration tests: model decision -> tool call -> grounded answer.
- Cover failure behavior:
  - tool error
  - timeout
  - denied high-risk tool action
  - user-facing safe error message

### Stage 5 — Integration and lightweight load testing

- Add end-to-end RAG flow: upload document -> index -> ask -> answer with source boundary.
- Add a lightweight concurrency smoke test with 10-20 parallel requests.
- Keep load testing separate from the normal fast CI path unless it stays reliable and quick.

## Promotion policy

Do not turn every advisory check into a hard gate immediately. A practical order is:

1. Tests must pass.
2. Coverage must stay above the current threshold.
3. Ruff becomes blocking after initial cleanup.
4. pip-audit becomes blocking after dependency policy is stable.
5. mypy strictness grows module by module.

This keeps the project credible without making the CI pipeline brittle.
