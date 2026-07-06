# Security Overview

This document defines the intended enterprise-style security controls for the Security Pack.

## Security objectives

The Security Pack should protect:

- authenticated access to the local AI workspace
- administrative user-management actions
- security-sensitive tool execution
- audit-log integrity
- public/private data boundaries
- local runtime secrets and tokens

## Authentication model

Planned design:

- short-lived JWT access tokens
- refresh tokens with rotation
- refresh-token revocation on logout
- token secrets loaded from environment variables
- token claims limited to required identity and role data
- no tokens committed to Git or written to public logs

Recommended token claim shape:

```json
{
  "sub": "user-id",
  "username": "local-user",
  "role": "admin|user",
  "iat": 0,
  "exp": 0,
  "jti": "token-id"
}
```

## Authorization model

Planned roles:

| Role | Purpose |
|---|---|
| `admin` | user management, security settings, audit verification |
| `user` | normal chat, memory and source workflows |
| `readonly` | optional future role for viewing status without mutation |

High-risk operations should require admin role or explicit confirmation.

## Rate limiting

Rate limiting should support:

- per-user limits after authentication
- per-IP limits before authentication
- stricter limits for login and token-refresh endpoints
- test-mode overrides for deterministic tests

Suggested first baseline:

| Endpoint group | Limit |
|---|---|
| Login | strict per IP |
| Refresh token | moderate per user/IP |
| Chat | moderate per user |
| Admin actions | strict per admin user |
| Static UI/assets | relaxed |

## IP allowlist

The IP allowlist should be optional and off by default for local development.

Configuration should support:

```text
SADE_IP_ALLOWLIST=127.0.0.1,192.168.0.0/16,10.0.0.0/8
```

Behavior:

- allow local loopback by default
- reject disallowed clients before sensitive route handling
- log blocked attempts without leaking secrets
- include tests for IPv4, CIDR and disabled allowlist mode

## Audit integrity

Audit log tamper-proofing should use a hash chain.

Each audit event should include:

- event timestamp
- event type
- actor/user id
- route or tool name
- sanitized metadata
- previous event hash
- current event hash

Hash chain input should use canonical JSON so verification is deterministic.

Verification should detect:

- deleted lines
- edited lines
- reordered lines
- invalid JSON
- missing previous hash

## Admin panel

The admin panel should support:

- list users
- create local user
- disable local user
- rotate/reset user credentials through a safe workflow
- view rate-limit/audit status
- verify audit hash chain

Admin routes must require:

- authenticated user
- admin role
- CSRF protection for browser-initiated mutations
- audit logging for all state-changing actions

## Non-goals for Sprint 1

Sprint 1 does not claim to provide:

- SSO/SAML/OIDC federation
- full enterprise IAM integration
- external SIEM integration
- SOC2/ISO27001 compliance
- public internet production deployment readiness

Those can be future roadmap items.
