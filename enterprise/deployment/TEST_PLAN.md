# Deployment Test Plan

This test plan defines validation for deployment packaging.

## Test categories

| Area | Tests |
|---|---|
| Docker image | image builds, app imports, default command valid |
| Docker Compose | compose config validates, service starts in smoke mode |
| Runtime volumes | memory/uploads/audit/backup paths mounted outside image |
| Environment | required env vars documented, missing secret handled safely |
| Health checks | live/ready endpoints respond in deployment mode |
| Backup/restore | backup archive can be created from mounted runtime data |
| Offline mode | web search disabled or documented, model endpoint configurable |
| Secrets | no `.env`, token, session or private runtime data included in image |
| CI release | tag-based build path documented and testable |

## Suggested test files

```text
tests/test_deployment_docs.py
tests/test_dockerfile_metadata.py
tests/test_runtime_volume_boundaries.py
tests/test_release_readiness_deployment.py
```

## Smoke checklist

1. build image
2. start container with empty runtime volume
3. open `/ui` or health endpoint
4. create/login local user in safe test mode
5. send mocked chat request
6. create backup archive
7. confirm runtime data stayed in mounted volume

## Done criteria

Sprint 5 is done when:

- deployment docs exist
- Docker Compose path is documented
- runtime volume boundaries are clear
- smoke validation is documented
- secret handling is explicit
- offline limitations are documented
- deployment packaging does not overclaim production readiness
