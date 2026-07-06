# Local AI Workspace

![CI](https://github.com/denzo69/local-ai-workspace/actions/workflows/tests.yml/badge.svg?branch=master)

**Local-first AI assistant built with FastAPI, Ollama, RAG, memory, safety routing and secure tooling.**

Local AI Workspace is a portfolio-stage AI engineering project. It demonstrates how a local assistant can combine model interaction with retrieval, memory, authentication, safety boundaries, testing and CI/CD hygiene.

## Highlights

- Local-first FastAPI architecture with Ollama support.
- RAG and semantic memory workflows.
- Response Planning and Answer Grounding layers.
- Safety routing and tool risk policies.
- Authentication, CSRF protection and audit logging.
- Project Health Dashboard and developer trace tools.
- Backup/restore workflow for local data.
- 93% coverage, 400+ tests and an extensive eval suite.

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
- [Code Rewrite Protocol](docs/code_rewrite_protocol.md)
- [Authentication Policy](docs/authentication_policy.md)
- [Tool Risk Policy](docs/tool_risk_policy.md)
- [AI Evaluation Policy](docs/ai_evaluation_policy.md)
- [Memory Governance Policy](docs/memory_governance_policy.md)

## License

MIT License. See [LICENSE](LICENSE).
