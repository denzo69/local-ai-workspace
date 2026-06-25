# Security Policy — Local AI Workspace

Local AI Workspace is a local-first AI assistant project. It handles memory, files, audit logs, and login sessions, so it should not be exposed directly to the public internet.

## Do not publish these files

- `app/memory/auth.json`
- `app/memory/auth_sessions.json`
- `app/memory/chat_log.md`
- `app/memory/*.jsonl`
- `app/memory/vector_db/`
- `app/memory/backups/`
- `app/memory/exports/`
- personal uploads
- `.env`

## Recommended use

- bind to `127.0.0.1`
- keep authentication enabled
- use a strong password
- do not port-forward the app to the public internet
- use VPN/Tailscale and HTTPS if remote access is needed

## High-risk actions

High-risk actions include:

- writing files
- writing to memory
- deleting memory entries
- rebuilding the semantic index
- editing the system prompt
- restoring a backup

These actions should be audited and, when appropriate, explicitly confirmed by the user.
