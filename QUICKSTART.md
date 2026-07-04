# Quickstart — Local AI Workspace

## 1. Clone or open the project folder

```powershell
git clone https://github.com/denzo69/local-ai-workspace.git
cd local-ai-workspace
```

If you already cloned the repository, open your existing local project folder instead.

## 2. Create the virtual environment if needed

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 3. Create a local login user

```powershell
.\app\create_sade_user.bat
```

## 4. Start or restart the app

```powershell
.\app\restart_local_ai_workspace.bat
```

The script stops an old local backend if one is still running, starts a fresh backend, and prints the current version/build.

Manual alternative:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

## 5. Open the browser UI

```text
http://127.0.0.1:8080/ui
```

## 6. Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
