# Multi-tenant Architecture

Status: planned  
Target release: `v1.2-enterprise-multitenant`

Multi-tenant Architecture is Sprint 2 of the Enterprise Edition roadmap. Its purpose is to separate users, workspaces, memory, RAG indexes and audit logs so the system can support team and customer use cases more safely.

## Goal

Move from a single local workspace model toward workspace-scoped data boundaries.

The system should support:

- multiple users
- multiple workspaces
- workspace membership
- workspace-scoped memory
- workspace-scoped RAG indexes
- workspace-scoped audit logs
- workspace-aware tool permissions

## Core concept

```text
User
  └── Workspace membership
        └── Workspace
              ├── Memory store
              ├── RAG index
              ├── Audit log
              ├── Uploads/sources
              └── Tool policy scope
```

## Deliverables

| Area | Deliverable |
|---|---|
| Data model | workspace and membership model |
| Memory | workspace-scoped memory path/resolver |
| RAG | workspace-scoped index/source path/resolver |
| Audit | workspace-scoped audit log path/resolver |
| API | workspace switching and current-workspace status |
| Security | membership checks before workspace access |
| Testing | isolation tests and cross-workspace denial tests |

## Acceptance criteria

The sprint is complete when:

- a user can belong to one or more workspaces
- active workspace is explicit in request/session context
- memory reads/writes are scoped to the active workspace
- RAG source reads/writes are scoped to the active workspace
- audit events include workspace id
- cross-workspace access is denied in tests
- workspace path resolution prevents traversal
- documentation states migration and limitations clearly

## Non-goals for Sprint 2

Sprint 2 does not require:

- full billing/tenant management
- external organization directory sync
- SSO/SAML/OIDC
- per-tenant infrastructure provisioning
- customer-facing subscription management

Those are future commercial roadmap items.

## Related documents

- [Architecture](ARCHITECTURE.md)
- [Test Plan](TEST_PLAN.md)
- [Enterprise Roadmap](../ROADMAP.md)
