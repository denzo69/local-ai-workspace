# Test Plan

This test plan defines the expected test coverage for the Enterprise Security Pack.

## Test categories

| Area | Tests |
|---|---|
| JWT access tokens | valid token, expired token, malformed token, wrong secret, missing claims |
| Refresh tokens | issue, rotate, revoke, replay rejected, expired refresh token |
| Rate limiting | per-IP limit, per-user limit, reset window, exempt static assets, stricter login limits |
| IP allowlist | disabled mode, localhost allowed, CIDR allowed, disallowed IP rejected, malformed config safe failure |
| Admin panel | admin allowed, user denied, unauthenticated denied, CSRF required for mutation |
| Audit hash chain | valid chain, edited line detected, deleted line detected, reordered line detected, invalid JSON detected |
| Tool boundaries | high-risk tool requires policy/permission, path traversal rejected, secret-file request refused |
| Docs/release | README does not overclaim, security docs exist, release notes describe implemented controls |

## Suggested test files

```text
tests/test_security_tokens.py
tests/test_refresh_tokens.py
tests/test_rate_limiter.py
tests/test_ip_allowlist.py
tests/test_admin_security_routes.py
tests/test_audit_hash_chain.py
tests/test_enterprise_security_pack_docs.py
```

## Minimum done criteria

The pack should not be marked complete unless:

- every new security module has unit tests
- every new route has positive and negative integration tests
- every sensitive route has unauthorized tests
- admin-only features have non-admin denial tests
- audit tampering detection has explicit mutation tests
- coverage does not decrease from the current baseline without a documented reason

## Local command

```powershell
python -m pytest
```

The repo uses `pytest.ini`; coverage, JUnit and HTML reports are generated automatically.

## CI expectations

GitHub Actions should:

- run the full pytest suite on Python 3.10, 3.11 and 3.12
- upload coverage XML, JUnit XML and HTML coverage artifacts
- keep Ruff, mypy and pip-audit checks visible
- fail only on mandatory test/coverage gates while advisory checks remain documented
