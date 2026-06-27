# Changelog

All notable changes to Local AI Workspace are documented here.

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
