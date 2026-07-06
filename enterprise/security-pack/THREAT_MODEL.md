# Threat Model

This threat model defines the first security concerns for the Enterprise Security Pack.

## Assets

Important assets:

- local user accounts
- auth tokens and refresh tokens
- session cookies
- CSRF tokens
- personal memory data
- uploaded source documents
- audit logs
- backup archives
- tool execution boundaries
- local model configuration and secrets

## Trust boundaries

| Boundary | Description |
|---|---|
| Browser → FastAPI | user-controlled input enters the backend |
| Unauthenticated → authenticated | login and token refresh boundary |
| User → admin | privileged action boundary |
| Chat → tool router | natural language may trigger actions |
| Tool router → filesystem | highest-risk local boundary |
| Web search → answer grounding | external content is untrusted source data |
| Runtime files → Git repo | private data must not cross into public repo |

## Threats and controls

| Threat | Control |
|---|---|
| Brute-force login attempts | per-IP rate limiting |
| Token theft | short-lived access tokens, refresh rotation, logout revocation |
| Refresh-token replay | refresh token IDs and rotation tracking |
| Unauthorized admin access | admin role checks and CSRF protection |
| Prompt injection into tools | tool risk policies and explicit permission boundaries |
| Audit log tampering | hash-chained audit events and verification |
| Path traversal | guarded file access and tests |
| Secret leakage | `.gitignore`, env vars, sanitized logs |
| Public exposure of local app | IP allowlist and deployment warnings |
| External source poisoning | answer grounding and source-boundary checks |

## Security assumptions

- The default project remains local-first.
- The app may be accessed over a trusted private network.
- Local machine compromise is out of scope for Sprint 1.
- Public internet exposure is not recommended without additional hardening.
- Enterprise identity federation is future scope.

## Abuse cases to test

- repeated failed logins from same IP
- refresh token replay after rotation
- non-admin calling admin route
- unauthenticated admin route access
- disallowed IP hitting sensitive route
- edited audit log line
- deleted audit log line
- reordered audit log lines
- path traversal attempt through tool route
- prompt asking to reveal secrets or auth files

## Review checklist

Before release:

- all new security routes have negative tests
- all mutations are audited
- logs are sanitized
- secrets are loaded from environment or local runtime files
- docs state limitations clearly
- README remains concise and does not overclaim production readiness
