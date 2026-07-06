# Multi-tenant Test Plan

This test plan defines the first validation layer for workspace-scoped behavior.

## Test categories

| Area | Tests |
|---|---|
| Workspace id validation | valid id, empty id, traversal attempt, invalid characters |
| Workspace paths | memory/uploads/vector/audit paths stay under workspace root |
| Workspace membership | user can access own workspace, cannot access another workspace |
| Workspace switching | switch to allowed workspace, reject disallowed workspace |
| Memory isolation | workspace A memory not visible in workspace B |
| RAG isolation | workspace A sources/index not visible in workspace B |
| Audit isolation | events include workspace id and are written to correct workspace log |
| Admin behavior | admin can list managed workspaces, normal user cannot manage all |
| Migration | default workspace can be resolved without breaking existing local mode |
| API safety | unauthenticated and unauthorized workspace calls are denied |

## Suggested test files

```text
tests/test_workspace_paths.py
tests/test_workspace_membership.py
tests/test_workspace_memory_isolation.py
tests/test_workspace_rag_isolation.py
tests/test_workspace_audit_isolation.py
tests/test_workspace_api.py
```

## Golden isolation test

The most important test:

1. create workspace A
2. create workspace B
3. add memory/source to workspace A
4. query/list memory/source from workspace B
5. assert workspace A data is not visible
6. assert audit logs include the correct workspace id

## Negative tests

The sprint must include tests for:

- `../` traversal in workspace id
- user without membership accessing workspace
- disabled workspace access
- disabled user access
- missing workspace id when route requires one
- invalid workspace id format
- cross-workspace RAG/source lookup

## Coverage expectation

Adding multi-tenant support should not reduce the current baseline unless documented.

Current verified baseline before Sprint 2 implementation:

- 425 tests passing locally
- 93.03% total test coverage with branch coverage enabled

## Done criteria

Sprint 2 is done when:

- workspace path resolver has unit tests
- membership checks have unit tests
- memory/RAG/audit isolation has integration tests
- workspace API routes have positive and negative tests
- local single-user default workspace behavior is preserved
- documentation states what is implemented and what remains planned
