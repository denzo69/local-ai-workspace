# Implementation Plan

This plan breaks Sprint 1 into safe, testable implementation steps.

## Phase 0 — Current-state review

Before changing code:

- inspect current `app/auth.py`
- inspect current `app/main.py` auth/session routes
- inspect current `app/audit_log.py`
- identify existing CSRF/session behavior
- identify routes that require admin-only protection

Output:

- small design note listing what will be reused and what will be replaced

## Phase 1 — JWT access tokens

Tasks:

- add JWT utility module
- load signing secret from environment
- define token lifetime config
- create access-token issue/verify helpers
- add unit tests for valid, expired, malformed and wrong-secret tokens

Suggested module:

```text
app/security_tokens.py
```

Suggested env vars:

```text
SADE_JWT_SECRET
SADE_JWT_ALGORITHM=HS256
SADE_ACCESS_TOKEN_MINUTES=15
SADE_REFRESH_TOKEN_DAYS=7
```

## Phase 2 — Refresh tokens

Tasks:

- add refresh-token store
- implement rotation
- revoke refresh token on logout
- reject reused revoked tokens
- add tests for rotation and replay prevention

Suggested storage:

```text
memory/refresh_tokens.jsonl
```

Runtime file must stay outside Git.

## Phase 3 — Rate limiting

Tasks:

- create rate limiter utility
- support per-IP and per-user keys
- protect login, refresh, chat and admin endpoints
- add deterministic test clock
- add tests for allow, deny, reset-window behavior

Suggested module:

```text
app/rate_limiter.py
```

## Phase 4 — IP allowlist

Tasks:

- parse IPv4/CIDR allowlist from environment
- support disabled mode
- add middleware or dependency check
- log blocked attempts
- add tests for local, CIDR, disallowed and disabled modes

Suggested module:

```text
app/ip_allowlist.py
```

## Phase 5 — Audit hash chain

Tasks:

- extend audit event format with previous/current hash
- canonicalize event payload before hashing
- add hash-chain verification helper
- add route/tool command for verification status
- add tamper-detection tests

Suggested module changes:

```text
app/audit_log.py
```

Potential helper:

```text
verify_audit_chain(project_path) -> dict
```

## Phase 6 — Admin panel

Tasks:

- define admin-only routes
- list users
- create/disable users
- show security status
- show audit-chain verification result
- add UI section behind admin role
- add tests for admin allowed / non-admin denied / unauthenticated denied

Suggested route group:

```text
/admin/security
/admin/users
/admin/audit/verify
```

## Phase 7 — Documentation and release

Tasks:

- update `SECURITY.md`
- update `enterprise/security-pack/SECURITY_OVERVIEW.md`
- add release notes
- add migration notes
- bump version only after tests pass

## Done definition

The sprint can be marked complete when:

- all new modules have unit tests
- API/admin behavior has integration tests
- negative tests cover unauthenticated and unauthorized requests
- audit-chain tampering is detected in tests
- test suite is green
- docs do not overclaim enterprise readiness
