# Changelog

All notable changes to Local AI Workspace are documented here.

Version headings are kept in descending SemVer order so the public portfolio history is easy to scan.

## v0.1.13 — Thinking and Semantic Memory Coverage

### Added

- Added edge-case coverage for the Thinking Layer, including safety-boundary, project-aware, source-grounded and natural-conversation routing modes.
- Added semantic-memory coverage using a fake ChromaDB path so success, empty, error and formatting branches can be tested without a real vector database.
- Added tests for semantic-memory context truncation, missing metadata/distance handling and empty-index behavior.

### Changed

- Raised `thinking_layer.py` coverage to 100%.
- Raised `semantic_memory.py` coverage to 97%.
- Updated portfolio README and testing documentation to the verified 432-test baseline.
- Relaxed README portfolio checks so precise coverage/test baselines can evolve without breaking the suite.

### Documented status

- Current README status: `432 tests passing locally`.
- Current README coverage: `93.31%` total test coverage with branch coverage enabled.
- Latest verified run: `432 passed in 84.08s` on Windows / Python 3.13.

### Notes

This release improves meaningful branch coverage around response-scaffolding and semantic-memory behavior while keeping external dependencies mocked. No real Ollama, web or ChromaDB service is required for the added tests.

## v0.1.12 — Portfolio Front Page and Learning Coverage

### Added

- Added dedicated Developer Setup documentation for local commands and Windows helper scripts.
- Added dedicated Testing documentation for pytest, branch coverage, JUnit XML and HTML coverage reports.
- Added Limitations documentation to keep production-readiness boundaries visible without crowding the README.
- Added learning/dev coverage tests for developer chat commands, autonomous learning scan/loop behavior and learning-review workflows.

### Changed

- Simplified README into a concise portfolio front page instead of a technical dump.
- Moved detailed testing, setup, route and limitation information behind documentation links.
- Updated portfolio and release-readiness tests so they enforce the new README structure.
- Updated verified test baseline from 419 to 425 passing tests.

### Documented status

- Current README status: `425 tests passing locally`.
- Current README coverage: `93.03%` total test coverage with branch coverage enabled.
- Latest verified run: `425 passed in 34.36s` on Windows / Python 3.13.

### Notes

This release improves the public portfolio surface while preserving the deeper technical evidence in documentation. The README now works as a recruiter-friendly front page, with setup, testing and limitations available one click deeper.

## v0.1.11 — CI/CD and Coverage Hardening

### Added

- Upgraded the GitHub Actions CI workflow into a small production-team style pipeline.
- Added Python 3.10, 3.11 and 3.12 test matrix on Ubuntu.
- Added advisory Ruff, mypy and pip-audit jobs.
- Added a coverage gate with HTML/XML coverage artifacts.
- Added a tag-based Docker/GHCR release workflow.
- Added Dockerfile and Docker ignore rules for release-image builds.
- Added CI/CD roadmap and architecture-aligned test plan documentation.
- Added coverage-focused tests for persona/context handling, manual behavior routing and codebase map analysis.

### Changed

- Updated GitHub Actions to Node 24-compatible action versions where available.
- Updated README testing status to the current local coverage baseline.
- Raised local branch coverage from 92% to 93% while increasing the test suite from 342 to 419 passing tests.
- Improved coverage for persona_layer, conversation_context, manual_behavior and codebase_map without relying on real LLM, Ollama or web calls.

### Documented status

- Current README status: `419 tests passing locally`.
- Current README coverage: `93%` total test coverage with branch coverage enabled.
- CI is configured with quality checks, dependency audit, Python 3.10-3.12 matrix and coverage artifacts.

### Notes

This release focuses on CI/CD maturity and maintainable coverage growth. It keeps quality and security checks advisory at first so the project can harden gradually without making the pipeline brittle.

## v0.1.10 — Response Planning and Portfolio Hygiene

### Added

- Response Planning Layer for intent routing before tool use.
- Intent Planner for classifying date/time, assistant permissions, Self-State, general knowledge, health/lifestyle, business-support and current external information prompts.
- Context Gate to prevent unrelated memory, Self-State or business-support leakage.
- Answer Grounding / Knowledge Source Selection Layer for choosing between chat context, memory, project state, RAG, web search and model knowledge.
- Response Contracts for allowed and forbidden behavior by intent.
- Output Validator to catch obvious response mismatches before final output.
- Regression tests for Finnish routing edge cases, web-search gating, Self-State gating and tool-use decisions.
- Large deterministic assistant baseline eval with 10,000 question chains and 40,000 routing checks.

### Changed

- Automatic web search now runs only when the planner marks the prompt as current, external or source-dependent.
- Self-State output is limited to explicit Self-State, project status or technical status prompts.
- Business-support suggestions are constrained to relevant work, freelance, invoicing, tax, contract or company setup prompts.
- Improved manual behavior metric parsing for both old and current README wording.
- Added targeted tests for tool permission edge cases, model-provider status reporting and audit-log invalid-input handling.
- Polished the public portfolio surface and release-history presentation.
- Aligned `VERSION` with the latest public changelog line.

### Fixed

- Corrected the dependency list by replacing `httpx2` with `httpx`.
- Added dependency version ranges to make fresh portfolio installs less sensitive to upstream package changes.

### Documented status

- Current README status: `342 tests passing locally`.
- Current README coverage: `92%` total test coverage with branch coverage enabled.
- GitHub Actions: passing.
- Large interaction baseline: `10,000` question chains / `40,000` routing checks / `0` failures.
- Bilingual behavior eval: `21` cases / `0` failures.
- Focus behavior eval: `1,000` cases / `4,000` checks / `0` failures.

### Notes

This release reduces single-prompt patching by adding a general planning layer before response generation, and also cleans up the public install and release metadata for portfolio review.

## v0.1.9 — Manual AI Behavior Hardening

### Added

- Added a narrow manual-behavior layer for portfolio smoke prompts, language checks, RAG explanations, memory recall, source-boundary checks, safe README suggestions, hallucination resistance, sanitized health summaries, and missing-source refusal.
- Added a regression test that exercises the manual AI behavior checklist through the authenticated `/chat` route.

### Changed

- High-risk prompt-injection attempts targeting `system_prompt.md`, `auth.json`, session data or secrets are blocked before falling through to the model provider.
- Destructive memory/audit-log deletion requests now receive a confirmation-boundary response instead of relying on the model to refuse.
- Practical Ollama disk-usage guidance is answered with safe PowerShell commands and an explicit non-deletion warning.
- Polished README presentation and portfolio wording.
- Improved public project naming and GitHub repository presentation.
- Replaced overly specific recipe-search wording with broader factual-search routing language.

### Testing

- Local test status: `174 passed`.
- Total coverage: `88%`.
- GitHub Actions passing.
- Release readiness check passing.

### Notes

This remains a portfolio-stage local-first AI assistant project, not a production SaaS product.

## v0.1.8 — Coverage Hardening

### Added

- Added targeted tests for upload validation, duplicate upload naming, raw system status, live eval API routing, empty tool-router requests, and memory-cleaner status/preview routing.

### Changed

- Removed an obsolete duplicate `build_codebase_map` implementation that had been superseded by the safer builder.
- Updated the public Quickstart clone path to the current `local-ai-workspace` repository name.

### Testing

- Local test status: `173 passed`.
- Total coverage: `88%`.
