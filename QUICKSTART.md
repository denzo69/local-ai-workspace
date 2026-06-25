# Quickstart — Local AI Workspace

## 1. Open the project folder

```powershell
cd C:\Sade\Sade-v1
```

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

## 4. Start the app

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
