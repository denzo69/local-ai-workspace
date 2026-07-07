# Enterprise Edition

Status: roadmap / implementation planning

Enterprise Edition is a planned technical hardening path for Local AI Workspace. It extends the current local-first portfolio project with security planning, workspace data separation, plugins, observability and deployment documentation.

The current public project remains a portfolio-stage local-first AI workspace. Enterprise Edition documents describe planned, testable hardening work and should not be interpreted as a production-readiness claim until the features are implemented, tested and reviewed.

## Roadmap

See [Enterprise Edition Roadmap](ROADMAP.md).

## Sprint packages

| Sprint | Package | Status |
|---|---|---|
| 1 | [Security Pack](security-pack/README.md) | planned / implementation-ready |
| 2 | [Multi-tenant Architecture](multi-tenant/README.md) | planned |
| 3 | [Plugin Interface](plugins/README.md) | planned |
| 4 | [Observability Pack](observability/README.md) | planned |
| 5 | [Deployment Pack](deployment/README.md) | planned |
| 6 | [Enterprise Docs](docs/README.md) | planned |

## Repository layout

```text
enterprise/
  security-pack/
  multi-tenant/
  plugins/
  observability/
  deployment/
  docs/
```

Related top-level planning areas:

```text
charts/   # Helm planning
docker/   # container and compose planning
pitch/    # presentation placeholder
```

## Positioning

Use:

> Enterprise-style hardening roadmap for a local-first AI workspace.

Avoid until implementation and review are complete:

> Enterprise-ready production platform.

## Current verified baseline

The current verified test and coverage baseline is tracked in [Testing](../docs/testing/README.md).

Current public README positioning is tracked in [README Positioning Notes](../docs/readme_positioning_notes.md).
