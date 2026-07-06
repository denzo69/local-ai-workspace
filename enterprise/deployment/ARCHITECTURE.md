# Deployment Architecture

This document describes the planned deployment architecture for Local AI Workspace Enterprise Edition.

## Deployment modes

| Mode | Purpose |
|---|---|
| Local development | single developer workstation |
| Docker Compose | internal pilot or small team deployment |
| Kubernetes/Helm | production-like enterprise deployment path |
| Offline/air-gapped | privacy-sensitive or disconnected environment |

## Container layout

Suggested Docker Compose services:

```text
local-ai-workspace
  ├── FastAPI app
  ├── mounted runtime data
  ├── environment config
  └── optional local model endpoint
```

Ollama can run:

- on the host machine
- as a separate service
- on dedicated local hardware

## Runtime volumes

Runtime data should be mounted outside the image:

```text
runtime/
  memory/
  uploads/
  vector_db/
  audit/
  backups/
  workspaces/
```

Never bake runtime data into a Docker image.

## Environment configuration

Suggested config groups:

```text
SADE_ENV=development|pilot|production
SADE_HOST=0.0.0.0
SADE_PORT=8080
SADE_OLLAMA_BASE_URL=http://ollama:11434
SADE_JWT_SECRET=...
SADE_IP_ALLOWLIST=...
SADE_METRICS_ENABLED=false
```

Secrets should be injected through environment variables or a secret manager.

## Kubernetes/Helm plan

Future Helm chart should define:

- Deployment
- Service
- ConfigMap
- Secret
- PersistentVolumeClaim
- optional Ingress
- health/readiness probes

## Offline deployment

Offline deployment should document:

- required Python/container artifacts
- model download/preload steps
- no external web-search provider mode
- local package cache or image tar export
- backup and restore procedure

## Release checklist

Before shipping a deployment package:

- image builds locally
- app starts from clean volume
- health endpoint responds
- auth works
- audit log is writable
- backup archive can be created
- no secrets are included in image or repo
- README limitations remain accurate

## Open questions

- Should Ollama be bundled in the same Compose file?
- Should web search be disabled by default in enterprise/offline mode?
- Should metrics endpoint require admin auth in Docker Compose mode?
- Should Helm chart be included before real customer need?
