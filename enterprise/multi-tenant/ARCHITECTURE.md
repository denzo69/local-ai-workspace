# Multi-tenant Architecture

This document describes the planned workspace-scoped architecture for Local AI Workspace Enterprise Edition.

## Design principles

- Workspace scope must be explicit.
- Private data must not leak between workspaces.
- Path resolution must be centralized and tested.
- Audit events must include workspace identity.
- Local-first single-user mode should remain possible.
- Migration from the existing local layout should be incremental.

## Proposed data model

### User

Represents a local authenticated account.

Suggested fields:

```json
{
  "user_id": "user_...",
  "username": "jani",
  "role": "admin|user|readonly",
  "disabled": false
}
```

### Workspace

Represents an isolated project/data boundary.

Suggested fields:

```json
{
  "workspace_id": "ws_...",
  "name": "Default Workspace",
  "created_at": "iso timestamp",
  "owner_user_id": "user_...",
  "disabled": false
}
```

### Membership

Links users to workspaces.

Suggested fields:

```json
{
  "workspace_id": "ws_...",
  "user_id": "user_...",
  "workspace_role": "owner|admin|member|viewer"
}
```

## Proposed runtime layout

```text
runtime/
  workspaces/
    ws_default/
      memory/
      uploads/
      vector_db/
      audit/
      backups/
```

The public Git repo must not include runtime workspace data.

## Path resolver

Add a single resolver responsible for all workspace-scoped paths.

Suggested module:

```text
app/workspace_paths.py
```

Suggested helpers:

```python
workspace_root(project_path, workspace_id) -> Path
workspace_memory_path(project_path, workspace_id) -> Path
workspace_uploads_path(project_path, workspace_id) -> Path
workspace_vector_path(project_path, workspace_id) -> Path
workspace_audit_path(project_path, workspace_id) -> Path
```

All helpers must:

- validate workspace id format
- resolve under the runtime workspace root
- prevent `..` traversal
- create directories only when explicitly requested
- be covered by tests

## Request context

Every workspace-aware request should resolve:

- authenticated user
- active workspace id
- membership / permission
- route-level capability

Suggested context shape:

```json
{
  "user_id": "user_...",
  "role": "admin",
  "workspace_id": "ws_default",
  "workspace_role": "owner"
}
```

## API surface

Planned routes:

```text
GET /workspaces
POST /workspaces
GET /workspaces/current
POST /workspaces/switch
GET /workspaces/{workspace_id}/status
```

Mutation routes should require CSRF protection when called from browser UI.

## Migration plan

Initial migration can use a default workspace:

```text
ws_default
```

Existing local data can remain in place until a migration command is implemented.

Possible migration command:

```text
python scripts/migrate_to_workspace.py --workspace ws_default
```

## Audit behavior

Every workspace-scoped event should include:

- user id
- workspace id
- event type
- route/tool name
- sanitized metadata
- timestamp

This can later integrate with the Security Pack hash-chain audit design.

## Open questions

- Should workspace id be stored in session, JWT claim or explicit request header?
- Should workspace switching be browser-session scoped or user default scoped?
- Should admin users be able to see all workspaces by default?
- Should local single-user mode silently map to `ws_default`?

These should be decided before implementation.
