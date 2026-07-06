# Enterprise Edition

Status: roadmap / implementation planning

Enterprise Edition is the planned commercial hardening path for Local AI Workspace. It extends the current local-first portfolio project with security, multi-tenant data separation, plugins, observability and deployability.

The current public project remains a portfolio-stage local-first AI workspace. Enterprise Edition documents describe planned, testable hardening work and should not be interpreted as a production-readiness claim until the features are implemented, tested and reviewed.

## Roadmap

See [Enterprise Edition Roadmap](ROADMAP.md).

## Sprint packages

| Sprint | Package | Status |
|---|---|---|
| 1 | [Security Pack](security-pack/README.md) | planned / implementation-ready |
| 2 | [Multi-tenant Architecture](multi-tenant/README.md) | planned |
| 3 | Plugin Interface | planned |
| 4 | Observability Pack | planned |
| 5 | Deployment Pack | planned |
| 6 | Enterprise Sales Pack | planned |

## Positioning

Use:

> Enterprise-style hardening roadmap for a local-first AI workspace.

Avoid until implementation and review are complete:

> Enterprise-ready production platform.

## Current verified baseline

- 425 tests passing locally
- 93.03% total test coverage with branch coverage enabled
- Local-first FastAPI + Ollama + RAG + memory + safety routing architecture

## Commercial direction

Enterprise Edition is intended to make the project easier to package for:

- internal AI assistant pilots
- local-first RAG deployments
- air-gapped or privacy-sensitive environments
- AI platform engineering portfolio review
- consulting and implementation work
