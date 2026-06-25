# Contributing — Local AI Workspace

This project is still in active portfolio-stage development.

Before making a change:

1. check `git status`
2. avoid modifying personal memory data, local sessions, vector databases, or backups
3. add or update tests for new behavior
4. run `pytest`

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Do not commit local memory files, sessions, vector databases, backups, exports, uploads, or `.env` files.

For larger changes, keep the patch small, explain the reason, and make sure the project still passes CI.
