# Changelog

All notable changes to Local AI Workspace are documented here.

## [0.1.5-recipe-search-routing] - 2026-06-28

### Added

- Added automatic web-search routing for recipe and practical instruction questions, including prompts such as `Hae pullataikinan ohje`.
- Added regression tests to prevent recipe/instruction prompts from falling through to unrelated model answers such as Git pull instructions.

### Testing

- Local test status: `161 passed`.
- Total coverage: `85%`.

## [0.1.4-automatic-factual-search] - 2026-06-28

### Added

- Added automatic web-search routing for broad factual questions, including product/specification questions such as fuel consumption, model data, prices, weights, dimensions, manuals, and technical details.
- Added model-provider fallback behavior: if the local model returns an empty/502 response, chat can fall back to web search instead of showing a raw provider error to the user.
- Added tests for Volvo Penta 2003T style factual questions through both the tool router and the full `/chat` endpoint.

### Changed

- Web search status now reports automatic search as enabled.
- Chat no longer relies only on narrow weather/lottery/current-info detection before using search.

### Testing

- Local test status: `159 passed`.
- Total coverage: `85%`.

## [0.1.3-coverage-lift] - 2026-06-27

### Added

- Added targeted coverage tests for API routes, memory endpoints, tool file operations, config updates, Ollama status handling, and chat routing fallbacks.
- Added tool-router command coverage for common user-facing commands, file operations, semantic search, preview routing, and guarded error paths.
- Added live eval runner tests for passing model responses and provider-error handling.
- Added RAG quality gate tests for passing, empty-result, weak-score, low-coverage, and missing-ranking-reason cases.

### Testing

- Local test status: `156 passed`.
- Total coverage: `85%`.
- Key coverage improvements:
  - `app/main.py`: `77%` -> `84%`.
  - `app/tool_router.py`: `69%` -> `77%`.
  - `app/live_evals.py`: `29%` -> `100%`.
  - `app/rag_quality.py`: `70%` -> `100%`.

## [0.1.2-reliability-hardening] - 2026-06-27

### Added

- Added targeted reliability tests for the highest-risk AI integration paths:
  - RAG retrieval ranking, source filtering, strict document intent, chat-log exclusion, and curated upload selection.
  - Web search provider failures, Google/Brave provider parsing, cache behavior, source review, and weather-source summarization.
  - Ollama/model provider response handling, unknown provider rejection, and connection-error wrapping.
  - Tool-router routing for guarded file tools, semantic search, status/log routes, and tool-error handling.

### Testing

- Local test status: `125 passed`.
- Total coverage: `71%`.
- Key coverage improvements:
  - `app/rag_engine.py`: `52%` -> `80%`.
  - `app/web_search.py`: `61%` -> `81%`.
  - `app/model_provider.py`: `72%` -> `95%`.
  - `app/tool_router.py`: `47%` -> `69%`.

## [0.1.1-portfolio-polish] - 2026-06-27

### Added

- Added backend build metadata: version, git build, and backend start time.
- Added a visible UI version/build chip to make stale browser/backend states easier to spot.
- Added `app/restart_local_ai_workspace.bat` for a clean local restart workflow.

### Changed

- Updated Quickstart and README paths to use clone-friendly public repository commands.
- Updated the legacy start script wording from Säde v1 to Local AI Workspace.
- Removed `--reload` from the simple start script to reduce confusion during portfolio demos.

### Testing

- Current local test status: `96 passed`.
- Release readiness check: `ok: true`.

## [0.1.0-portfolio-beta] - 2026-06-25

### Changed

- Renamed the public portfolio surface to Local AI Workspace.
- Updated README, screenshots, SECURITY, CONTRIBUTING, and issue templates for an English-speaking GitHub audience.
- Clarified desktop and mobile browser access to the same local AI workspace.

### Testing

- Historical local test status: `85 passed`.
- GitHub Actions passes on Python 3.11 and 3.12.

## [0.1.0] - 2026-06-24

### Added

- Local FastAPI-based AI workspace UI.
- Chat, memory, source upload, and settings views.
- Finnish/English UI language switch.
- Authentication, CSRF protection, and session handling.
- Audit log, debug trace, and tool risk policy.
- Static AI evals and live eval entrypoint.
- RAG quality checks and source-aware retrieval flow.
- Backup/restore and memory governance APIs.
- GitHub Actions test workflow.
- Portfolio-ready README, QUICKSTART, SECURITY, and CONTRIBUTING files.

### Security

- Local-first usage model documented.
- Personal memory data, sessions, vector DB, backups, and uploads excluded from Git tracking.

### Testing

- Historical local test status: `51 passed`.
