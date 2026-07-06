# Developer Setup

This page contains local development commands and Windows-specific helper scripts that are intentionally kept out of the README front page.

## Install dependencies

```powershell
python -m pip install -r requirements.txt
```

For CI-quality local checks, install development dependencies:

```powershell
python -m pip install -r requirements-dev.txt
```

## Run the app locally

Use Uvicorn for local development:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080 --reload
```

Open:

```text
http://127.0.0.1:8080/ui
```

## Windows helper scripts

The project includes Windows helper scripts for local use:

```powershell
.\app\create_sade_user.bat
.\app\restart_local_ai_workspace.bat
```

These are useful for the original Windows workstation setup, but they are not required reading for the public README.

## Run tests

The project uses `pytest.ini`, so the full test command is intentionally short:

```powershell
python -m pytest
```

This writes:

- `reports/coverage.xml`
- `reports/junit.xml`
- `reports/htmlcov/`
- terminal coverage output

## Release readiness

```powershell
python scripts\release_readiness.py
```

## Notes

Do not commit local runtime data, personal memory files, auth sessions, uploads, vector DBs, backups or `.env` files. See `SECURITY.md` and `.gitignore` for the public/private boundary.
