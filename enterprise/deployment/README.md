# Deployment Pack

Status: planned  
Target release: `v1.5-enterprise-deployment`

Deployment Pack is Sprint 5 of the Enterprise Edition roadmap. Its goal is to make Local AI Workspace repeatable to run, review and package for internal pilots.

## Goal

Provide deployment paths for local, containerized, production-like and offline environments.

The pack should cover:

- Docker Compose deployment
- production-like environment configuration
- runtime directory boundaries
- backup/restore deployment notes
- Kubernetes/Helm plan
- air-gapped/offline deployment notes
- release checklist

## Deliverables

| Area | Deliverable |
|---|---|
| Docker Compose | local/pilot deployment guide |
| Environment | production-like env var guide |
| Runtime data | volume and backup path plan |
| Kubernetes | Helm chart design plan |
| Offline | air-gapped deployment notes |
| Release | deployment release checklist |
| Testing | container/deployment smoke test plan |

## Acceptance criteria

The sprint is complete when:

- Docker Compose path is documented
- runtime data volumes are documented
- secrets are environment-based and not committed
- backup/restore expectations are documented
- Kubernetes/Helm scope is defined
- offline deployment limitations are documented
- smoke tests are defined for deployment validation

## Non-goals for Sprint 5

Sprint 5 does not require:

- managed cloud deployment
- multi-region architecture
- autoscaling production cluster
- enterprise support contract
- compliance certification

Those are future commercial packaging items.

## Related documents

- [Deployment Architecture](ARCHITECTURE.md)
- [Deployment Test Plan](TEST_PLAN.md)
- [Enterprise Roadmap](../ROADMAP.md)
