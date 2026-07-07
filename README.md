# Local AI Workspace

![CI](https://github.com/denzo69/local-ai-workspace/actions/workflows/tests.yml/badge.svg?branch=master)

**Local-first AI workspace for building, testing and understanding private AI assistant workflows.**

Local AI Workspace is a portfolio-stage AI engineering project built around a FastAPI backend, Ollama/local models, RAG, persistent memory, safety routing and secure tooling.

It shows how a local AI assistant can become more than a chat box: a small, testable workspace where private memory, source documents, tool boundaries, audit logs, evaluations, health checks and backup/export workflows are handled together.

## What it does

- Runs a local assistant UI backed by FastAPI and Ollama.
- Stores and searches persistent assistant memory.
- Adds document/source material for retrieval-augmented answers.
- Routes prompts through response-planning, grounding and safety checks.
- Tracks security-relevant actions through audit logs.
- Provides eval, trace and tool-risk views for AI behavior review.
- Includes health, settings, backup and export workflows for daily use.

## Highlights

- Local-first FastAPI architecture with Ollama support.
- RAG and semantic memory workflows.
- Response Planning and Answer Grounding layers.
- Safety routing and tool risk policies.
- Authentication, CSRF protection and audit logging.
- Project Health Dashboard and developer trace tools.
- Backup/restore workflow for local data.
- 93.31% coverage, 434 tests and an extensive eval suite.

## Quickstart

```bash
git clone https://github.com/denzo69/local-ai-workspace
cd local-ai-workspace
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Open:

```text
http://127.0.0.1:8080/ui
```

Windows helper scripts and local development details are in [Developer Setup](docs/DEVELOPER_SETUP.md).

## Architecture

Local AI Workspace is structured around a FastAPI backend, local model-provider layer, memory/RAG workflows, tool routing, audit logging and safety checks.

See [Architecture](docs/architecture.md).

## Screenshots

**Focused desktop app view**

![Local AI Workspace desktop app-only view](docs/screenshots/desktop-clean.png)

**Mobile app-style preview**

![Local AI Workspace mobile app-only preview](docs/screenshots/mobile-clean.jpg)

More screenshots: [docs/screenshots/](docs/screenshots/README.md)

## Testing

```bash
python -m pytest
```

The test suite writes coverage XML, JUnit XML and HTML coverage reports under `reports/`.

See [Testing](docs/testing/README.md).

## Security

The project includes authentication, CSRF protection, audit logging, prompt-injection checks and guarded tool boundaries.

See [Security](SECURITY.md).

## Limitations

This is a portfolio-stage project, not production-ready without additional enterprise hardening.

See [Limitations](docs/limitations.md).

## Documentation

- [Architecture](docs/architecture.md)
- [Developer Setup](docs/DEVELOPER_SETUP.md)
- [Testing](docs/testing/README.md)
- [CI/CD Roadmap](docs/ci_cd_roadmap.md)
- [Security](SECURITY.md)
- [Limitations](docs/limitations.md)
- [README Positioning Notes](docs/readme_positioning_notes.md)
- [Code Rewrite Protocol](docs/code_rewrite_protocol.md)
- [Authentication Policy](docs/authentication_policy.md)
- [Tool Risk Policy](docs/tool_risk_policy.md)
- [AI Evaluation Policy](docs/ai_evaluation_policy.md)
- [Memory Governance Policy](docs/memory_governance_policy.md)

## License

MIT License. See [LICENSE](LICENSE).
