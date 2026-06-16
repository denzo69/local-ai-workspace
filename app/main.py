from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from datetime import datetime
from pathlib import Path
from typing import Optional, List
import json
import urllib.request
import urllib.error
import shutil

from app.tools import (
    ToolError,
    append_file as tool_append_file,
    get_tools_status,
    list_available_tools,
    list_files as tool_list_files,
    project_status as tool_project_status,
    read_file as tool_read_file,
    write_file as tool_write_file,
)

from app.tool_router import (
    route_tool_preview,
    route_tool_request,
)

from app.file_ingestion import (
    ingest_file,
    read_ingestion_log,
    summarize_file,
)

from app.tool_log import (
    log_tool_event,
    read_tool_log,
)

from app.semantic_memory import (
    add_text_to_semantic_memory,
    format_semantic_context,
    rebuild_semantic_memory_index,
    search_semantic_memory,
    semantic_memory_status,
)


app = FastAPI(title="Säde v1")

PROJECT_PATH = Path(__file__).resolve().parent
BASE_PATH = PROJECT_PATH
CONFIG_PATH = PROJECT_PATH / "config.json"

MEMORY_PATH = PROJECT_PATH / "memory"
SADE_MEMORY_PATH = MEMORY_PATH / "sade_memory.md"
LOG_PATH = MEMORY_PATH / "memory_log.jsonl"
CHAT_LOG_PATH = MEMORY_PATH / "chat_log.md"
SYSTEM_PROMPT_PATH = PROJECT_PATH / "system_prompt.md"
TEMPLATES_PATH = PROJECT_PATH / "templates"
UI_TEMPLATE_PATH = TEMPLATES_PATH / "ui.html"
UPLOADS_PATH = PROJECT_PATH / "uploads"
TOOL_LOG_PATH = MEMORY_PATH / "tool_log.jsonl"
INGESTION_LOG_PATH = MEMORY_PATH / "ingested_files.jsonl"


class MemoryEntry(BaseModel):
    title: Optional[str] = Field(default=None, description="Merkinnän otsikko")
    text: str = Field(..., description="Varsinainen merkintäteksti")
    tags: Optional[List[str]] = Field(default=None, description="Vapaaehtoiset tagit")


class ChatRequest(BaseModel):
    message: str = Field(..., description="Käyttäjän viesti")


class ChatResponse(BaseModel):
    ok: bool
    reply: str
    model: str
    time: str


class VisibleChatSaveRequest(BaseModel):
    content: str = Field(..., description="Näkyvän chat-ikkunan sisältö")


class MemorySearchRequest(BaseModel):
    query: str = Field(..., description="Hakusana tai hakulause")

class SystemPromptUpdateRequest(BaseModel):
    content: str = Field(..., description="Säteen system prompt -sisältö")

class ConfigUpdateRequest(BaseModel):
    ollama_model: Optional[str] = None
    temperature: Optional[float] = None
    num_ctx: Optional[int] = None
    memory_context_chars: Optional[int] = None
    chat_context_chars: Optional[int] = None
    semantic_context_chars: Optional[int] = None
    semantic_search_results: Optional[int] = None

class ToolRouterRequest(BaseModel):
    message: str = Field(..., description="Luonnollinen kielipyyntö tool routerille")


class FileIngestRequest(BaseModel):
    relative_path: str = Field(..., description="Käsiteltävä tiedosto projektikansion sisällä")
    add_to_memory: Optional[bool] = Field(default=True, description="Lisätäänkö tiivistelmä Säde-muistiin")
    add_to_semantic: Optional[bool] = Field(default=True, description="Lisätäänkö koko teksti semanttiseen muistiin")
    title: Optional[str] = Field(default=None, description="Valinnainen otsikko muistimerkinnälle")
    tags: Optional[List[str]] = Field(default=None, description="Valinnaiset tagit")


class FileSummarizeRequest(BaseModel):
    relative_path: str = Field(..., description="Tiivistettävä tiedosto projektikansion sisällä")


class ToolLogReadRequest(BaseModel):
    limit: Optional[int] = Field(default=50, description="Kuinka monta viimeisintä lokiriviä palautetaan")


class ToolFileListRequest(BaseModel):
    relative_path: Optional[str] = Field(default="", description="Polku projektikansion sisällä")
    max_items: Optional[int] = Field(default=100, description="Maksimimäärä palautettavia kohteita")
    include_hidden: Optional[bool] = Field(default=False, description="Näytä piilotetut tiedostot")


class ToolFileReadRequest(BaseModel):
    relative_path: str = Field(..., description="Luettava tiedosto projektikansion sisällä")
    max_chars: Optional[int] = Field(default=20000, description="Maksimimäärä merkkejä")


class ToolFileWriteRequest(BaseModel):
    relative_path: str = Field(..., description="Kirjoitettava tiedosto projektikansion sisällä")
    content: str = Field(..., description="Tiedoston sisältö")
    overwrite: Optional[bool] = Field(default=False, description="Saako olemassa olevan tiedoston ylikirjoittaa")


class ToolFileAppendRequest(BaseModel):
    relative_path: str = Field(..., description="Tiedosto projektikansion sisällä")
    content: str = Field(..., description="Lisättävä sisältö")


def load_config():
    default_config = {
        "ollama_url": "http://127.0.0.1:11434/api/generate",
        "ollama_model": "gpt-oss:20b",
        "temperature": 0.7,
        "num_ctx": 8192,
        "memory_context_chars": 6000,
        "chat_context_chars": 4000,
        "semantic_context_chars": 3500,
        "semantic_search_results": 5,
	"export_path": "D:/Sade_Exports",
    	"backup_path": "D:/Sade_Backups"
    }

    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(
            json.dumps(default_config, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        return default_config

    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return default_config

    return {**default_config, **config}

def save_config_updates(updates: ConfigUpdateRequest):
    config = load_config()

    if updates.ollama_model is not None:
        model = updates.ollama_model.strip()
        if not model:
            raise HTTPException(status_code=400, detail="Mallin nimi ei saa olla tyhjä.")
        config["ollama_model"] = model

    if updates.temperature is not None:
        if updates.temperature < 0 or updates.temperature > 2:
            raise HTTPException(status_code=400, detail="Temperature pitää olla välillä 0–2.")
        config["temperature"] = updates.temperature

    if updates.num_ctx is not None:
        if updates.num_ctx < 512:
            raise HTTPException(status_code=400, detail="num_ctx pitää olla vähintään 512.")
        config["num_ctx"] = updates.num_ctx

    if updates.memory_context_chars is not None:
        if updates.memory_context_chars < 500:
            raise HTTPException(status_code=400, detail="memory_context_chars pitää olla vähintään 500.")
        config["memory_context_chars"] = updates.memory_context_chars

    if updates.chat_context_chars is not None:
        if updates.chat_context_chars < 500:
            raise HTTPException(status_code=400, detail="chat_context_chars pitää olla vähintään 500.")
        config["chat_context_chars"] = updates.chat_context_chars

    if updates.semantic_context_chars is not None:
        if updates.semantic_context_chars < 500:
            raise HTTPException(status_code=400, detail="semantic_context_chars pitää olla vähintään 500.")
        config["semantic_context_chars"] = updates.semantic_context_chars

    if updates.semantic_search_results is not None:
        if updates.semantic_search_results < 1 or updates.semantic_search_results > 20:
            raise HTTPException(status_code=400, detail="semantic_search_results pitää olla välillä 1–20.")
        config["semantic_search_results"] = updates.semantic_search_results

    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return config


def ensure_paths():
    BASE_PATH.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.mkdir(parents=True, exist_ok=True)
    TEMPLATES_PATH.mkdir(parents=True, exist_ok=True)
    UPLOADS_PATH.mkdir(parents=True, exist_ok=True)

    if not SADE_MEMORY_PATH.exists():
        SADE_MEMORY_PATH.write_text(
            "# Säde-muisti\n\nTänne Säde voi tallentaa muistoja, ajatuksia ja yhteisiä hetkiä.\n\n",
            encoding="utf-8"
        )

    if not LOG_PATH.exists():
        LOG_PATH.write_text("", encoding="utf-8")

    if not CHAT_LOG_PATH.exists():
        CHAT_LOG_PATH.write_text(
            "# Keskusteluloki\n\nTänne tallentuvat Säde v1:n keskustelut.\n\n",
            encoding="utf-8"
        )

    if not SYSTEM_PROMPT_PATH.exists():
        SYSTEM_PROMPT_PATH.write_text(
            """Olet Säde v1, paikallinen tekoälyavustaja Janin koneella.

Tyyli:
- Vastaa suomeksi.
- Ole lämmin, selkeä, rauhallinen ja käytännöllinen.
- Vastaa suoraan siihen, mitä käyttäjä kysyy.
- Älä väitä tietäväsi asioita, joita ei ole annettu sinulle.
- Käytä Säde-muistia pitkäaikaisena muistina.
- Käytä keskustelulokia lyhytaikaisena muistina.
- Jos et tiedä, sano rehellisesti ettet tiedä.
""",
            encoding="utf-8"
        )

def read_markdown_file(path: Path):
    if not path.exists():
        return {
            "ok": False,
            "path": str(path),
            "content": "",
            "message": "Tiedostoa ei löytynyt."
        }

    content = path.read_text(encoding="utf-8")
    return {
        "ok": True,
        "path": str(path),
        "content": content,
        "updated": datetime.fromtimestamp(path.stat().st_mtime).isoformat()
    }


def append_markdown_entry(path: Path, entry: MemoryEntry):
    ensure_paths()

    timestamp = datetime.now().isoformat(timespec="seconds")
    title = entry.title or "Nimetön muisto"
    tags = ", ".join(entry.tags) if entry.tags else "ei tageja"

    markdown = (
        f"\n\n---\n\n"
        f"## {title}\n\n"
        f"**Aika:** {timestamp}\n\n"
        f"**Tagit:** {tags}\n\n"
        f"{entry.text}\n"
    )

    with path.open("a", encoding="utf-8") as f:
        f.write(markdown)

    log_entry = {
        "time": timestamp,
        "title": title,
        "text": entry.text,
        "tags": entry.tags or [],
        "target": str(path)
    }

    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    semantic_result = add_text_to_semantic_memory(
        PROJECT_PATH,
        entry.text,
        title=title,
        source=path.name,
        tags=entry.tags or [],
        timestamp=timestamp
    )

    return {
        "ok": True,
        "message": "Muisto tallennettu.",
        "title": title,
        "path": str(path),
        "time": timestamp,
        "semantic_memory": semantic_result
    }


def append_chat_log(user_message: str, sade_reply: str):
    ensure_paths()

    timestamp = datetime.now().isoformat(timespec="seconds")

    markdown = (
        f"\n\n---\n\n"
        f"## Keskustelu {timestamp}\n\n"
        f"### Jani\n\n"
        f"{user_message}\n\n"
        f"### Säde\n\n"
        f"{sade_reply}\n"
    )

    with CHAT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(markdown)


def get_memory_context(max_chars: Optional[int] = None) -> str:
    config = load_config()

    if max_chars is None:
        max_chars = int(config.get("memory_context_chars", 6000))

    ensure_paths()

    if not SADE_MEMORY_PATH.exists():
        return ""

    content = SADE_MEMORY_PATH.read_text(encoding="utf-8")

    if len(content) <= max_chars:
        return content

    return content[-max_chars:]


def get_chat_context(max_chars: Optional[int] = None) -> str:
    config = load_config()

    if max_chars is None:
        max_chars = int(config.get("chat_context_chars", 4000))

    ensure_paths()

    if not CHAT_LOG_PATH.exists():
        return ""

    content = CHAT_LOG_PATH.read_text(encoding="utf-8")

    if len(content) <= max_chars:
        return content

    return content[-max_chars:]


def get_semantic_context(query: str) -> str:
    config = load_config()

    max_chars = int(config.get("semantic_context_chars", 3500))
    n_results = int(config.get("semantic_search_results", 5))

    try:
        result = search_semantic_memory(PROJECT_PATH, query, n_results=n_results)
        return format_semantic_context(result, max_chars=max_chars)
    except Exception:
        return ""


def extract_memory_command(message: str) -> Optional[str]:
    text = message.strip()
    lower = text.lower()

    triggers = [
        "tallenna muistiin että",
        "tallenna muistiin, että",
        "muista että",
        "muista, että",
        "kirjaa muistiin että",
        "kirjaa muistiin, että",
        "lisää Säde-muistiin että",
        "lisää Säde-muistiin, että",
        "tallenna Säde-muistiin että",
        "tallenna Säde-muistiin, että",
    ]

    for trigger in triggers:
        if lower.startswith(trigger):
            memory_text = text[len(trigger):].strip()
            return memory_text if memory_text else None

    return None


def ask_ollama(prompt: str) -> str:
    config = load_config()

    ollama_url = config.get("ollama_url", "http://127.0.0.1:11434/api/generate")
    ollama_model = config.get("ollama_model", "gpt-oss:20b")
    temperature = float(config.get("temperature", 0.7))
    num_ctx = int(config.get("num_ctx", 8192))

    payload = {
        "model": ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_ctx": num_ctx
        }
    }

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        ollama_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            response_data = response.read().decode("utf-8")
            result = json.loads(response_data)
            return result.get("response", "").strip()

    except urllib.error.URLError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Ollamaan ei saada yhteyttä. Tarkista että Ollama on käynnissä. Virhe: {e}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ollama-kutsu epäonnistui: {e}"
        )


def build_sade_prompt(user_message: str) -> str:
    system_prompt = get_system_prompt()
    semantic_context = get_semantic_context(user_message)
    memory_context = get_memory_context()
    chat_context = get_chat_context()

    return f"""
{system_prompt}

Semanttinen muistihaku, merkityksen perusteella löydetyt muistot:
{semantic_context}

Pitkäaikainen muisti, Säde-muisti:
{memory_context}

Viimeaikainen keskusteluloki:
{chat_context}

Käyttäjän uusi viesti:
{user_message}

Säteen vastaus:
""".strip()


def search_sade_memory(query: str, context_lines: int = 4):
    ensure_paths()

    if not SADE_MEMORY_PATH.exists():
        return {
            "ok": False,
            "query": query,
            "results": [],
            "message": "Säde-muistia ei löytynyt."
        }

    search = query.strip().lower()

    if not search:
        return {
            "ok": False,
            "query": query,
            "results": [],
            "message": "Hakusana ei saa olla tyhjä."
        }

    content = SADE_MEMORY_PATH.read_text(encoding="utf-8")
    lines = content.splitlines()

    results = []

    for index, line in enumerate(lines):
        if search in line.lower():
            start = max(0, index - context_lines)
            end = min(len(lines), index + context_lines + 1)

            snippet = "\n".join(lines[start:end]).strip()

            results.append({
                "line": index + 1,
                "match": line,
                "snippet": snippet
            })

    return {
        "ok": True,
        "query": query,
        "count": len(results),
        "results": results
    }

def create_export_file():
    ensure_paths()

    config = load_config()
    export_path = Path(config.get("export_path", "D:/Sade_Exports"))
    export_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    export_file = export_path / f"sade_export_{timestamp}.md"

    sade_memory_content = ""
    chat_log_content = ""

    if SADE_MEMORY_PATH.exists():
        sade_memory_content = SADE_MEMORY_PATH.read_text(encoding="utf-8")

    if CHAT_LOG_PATH.exists():
        chat_log_content = CHAT_LOG_PATH.read_text(encoding="utf-8")

    safe_config = {
        "ollama_model": config.get("ollama_model"),
        "ollama_url": config.get("ollama_url"),
        "temperature": config.get("temperature"),
        "num_ctx": config.get("num_ctx"),
        "memory_context_chars": config.get("memory_context_chars"),
        "chat_context_chars": config.get("chat_context_chars"),
        "export_path": config.get("export_path"),
        "backup_path": config.get("backup_path")
    }

    config_json = json.dumps(safe_config, ensure_ascii=False, indent=2)

    export_content = "\n".join([
        "# Säde v1 export",
        "",
        f"**Luotu:** {datetime.now().isoformat(timespec='seconds')}",
        "",
        f"**Export-tiedosto:** `{export_file}`",
        "",
        "---",
        "",
        "## Asetukset",
        "",
        "~~~json",
        config_json,
        "~~~",
        "",
        "---",
        "",
        "## Säde-muisti",
        "",
        sade_memory_content,
        "",
        "---",
        "",
        "## Keskusteluloki",
        "",
        chat_log_content,
        ""
    ])

    export_file.write_text(export_content, encoding="utf-8")

    return {
        "ok": True,
        "message": "Export-tiedosto luotu.",
        "path": str(export_file),
        "filename": export_file.name,
        "time": datetime.now().isoformat(timespec="seconds")
    }

def create_backup_files():
    ensure_paths()

    config = load_config()

    backup_path = Path(config.get("backup_path", "D:/Sade_Backups"))
    backup_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    copied_files = []

    files_to_backup = [
        PROJECT_PATH / "main.py",
        PROJECT_PATH / "config.json",
        SADE_MEMORY_PATH,
        CHAT_LOG_PATH,
        LOG_PATH
    ]

    for source in files_to_backup:
        if source.exists():
            backup_file = backup_path / f"{source.stem}_backup_{timestamp}{source.suffix}"
            shutil.copy2(source, backup_file)
            copied_files.append(str(backup_file))

    if not copied_files:
        raise HTTPException(
            status_code=500,
            detail="Varmuuskopioitavia tiedostoja ei löytynyt."
        )

    return {
        "ok": True,
        "message": "Varmuuskopio luotu.",
        "backup_path": str(backup_path),
        "files": copied_files,
        "time": datetime.now().isoformat(timespec="seconds")
    }

@app.on_event("startup")
def startup_event():
    ensure_paths()


@app.get("/")
def root():
    config = load_config()

    return {
        "name": "Säde v1",
        "status": "awake",
        "message": "Säde v1 toimii.",
        "model": config.get("ollama_model", "gpt-oss:20b"),
        "paths": {
            "base": str(BASE_PATH),
            "memory": str(MEMORY_PATH),
            "sade_memory": str(SADE_MEMORY_PATH),
            "chat_log": str(CHAT_LOG_PATH),
            "config": str(CONFIG_PATH)
        },
        "endpoints": [
            "/ui",
            "/chat",
            "/config",
            "POST /config",
            "/ollama/status",
            "/health",
            "/memory/sade-memory",
            "/memory/visible-chat",
            "/memory/chatlog",
            "/memory/search",
            "/memory/semantic/search",
            "/memory/semantic/rebuild",
            "/semantic/status",
            "/tools/status",
            "/tools/list",
            "/tools/project-status",
            "/tools/files/list",
            "/tools/files/read",
            "/tools/files/write",
            "/tools/files/append",
            "/tools/router/preview",
            "/tools/router/run",
            "/files/ingest",
            "/files/summarize",
            "/files/ingestion-log",
            "/tools/log",
            "/export",
	    "/backup",
            "/docs"
        ]
    }


@app.get("/ollama/status")
def ollama_status():
    config = load_config()

    ollama_url = config.get("ollama_url", "http://127.0.0.1:11434/api/generate")
    ollama_model = config.get("ollama_model", "gpt-oss:20b")

    payload = {
        "model": ollama_model,
        "prompt": "Vastaa vain yhdellä sanalla: ok",
        "stream": False,
        "options": {
            "temperature": 0,
            "num_ctx": 512
        }
    }

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        ollama_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        start_time = datetime.now()

        with urllib.request.urlopen(request, timeout=30) as response:
            response_data = response.read().decode("utf-8")
            result = json.loads(response_data)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        return {
            "ok": True,
            "status": "connected",
            "message": "Ollama vastaa.",
            "model": ollama_model,
            "response": result.get("response", "").strip(),
            "duration_seconds": duration,
            "time": datetime.now().isoformat(timespec="seconds")
        }

    except urllib.error.URLError as e:
        return {
            "ok": False,
            "status": "connection_error",
            "message": "Ollamaan ei saada yhteyttä. Tarkista että Ollama on käynnissä.",
            "model": ollama_model,
            "error": str(e),
            "time": datetime.now().isoformat(timespec="seconds")
        }

    except Exception as e:
        return {
            "ok": False,
            "status": "error",
            "message": "Ollama-testissä tapahtui virhe.",
            "model": ollama_model,
            "error": str(e),
            "time": datetime.now().isoformat(timespec="seconds")
        }

@app.get("/config")
def get_config():
    config = load_config()

    return {
        "ok": True,
        "ollama_model": config.get("ollama_model", "gpt-oss:20b"),
        "ollama_url": config.get("ollama_url", "http://127.0.0.1:11434/api/generate"),
        "temperature": config.get("temperature", 0.7),
        "num_ctx": config.get("num_ctx", 8192),
        "memory_context_chars": config.get("memory_context_chars", 6000),
        "chat_context_chars": config.get("chat_context_chars", 4000),
        "semantic_context_chars": config.get("semantic_context_chars", 3500),
        "semantic_search_results": config.get("semantic_search_results", 5)
    }

@app.post("/config")
def update_config(request: ConfigUpdateRequest):
    config = save_config_updates(request)

    return {
        "ok": True,
        "message": "Asetukset tallennettu.",
        "config": {
            "ollama_model": config.get("ollama_model", "gpt-oss:20b"),
            "ollama_url": config.get("ollama_url", "http://127.0.0.1:11434/api/generate"),
            "temperature": config.get("temperature", 0.7),
            "num_ctx": config.get("num_ctx", 8192),
            "memory_context_chars": config.get("memory_context_chars", 6000),
            "chat_context_chars": config.get("chat_context_chars", 4000)
        }
    }

@app.get("/health")
def health():
    config = load_config()

    return {
        "ok": True,
        "status": "running",
        "model": config.get("ollama_model", "gpt-oss:20b"),
        "temperature": config.get("temperature", 0.7),
        "num_ctx": config.get("num_ctx", 8192),
        "time": datetime.now().isoformat(timespec="seconds")
    }

@app.get("/system/status")
def system_status():
    ensure_paths()
    config = load_config()

    backup_path = Path(config.get("backup_path", "D:/Sade_Backups"))
    export_path = Path(config.get("export_path", "D:/Sade_Exports"))

    def file_info(path: Path):
        return {
            "path": str(path),
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() and path.is_file() else None
        }

    def dir_info(path: Path):
        return {
            "path": str(path),
            "exists": path.exists(),
            "is_dir": path.is_dir() if path.exists() else False
        }

    return {
        "ok": True,
        "server": "running",
        "time": datetime.now().isoformat(timespec="seconds"),
        "project": dir_info(PROJECT_PATH),
        "memory": dir_info(MEMORY_PATH),
        "sade_memory": file_info(SADE_MEMORY_PATH),
        "chat_log": file_info(CHAT_LOG_PATH),
        "memory_log": file_info(LOG_PATH),
        "tool_log": file_info(TOOL_LOG_PATH),
        "ingestion_log": file_info(INGESTION_LOG_PATH),
        "uploads": dir_info(UPLOADS_PATH),
        "semantic_memory": semantic_memory_status(PROJECT_PATH),
        "tools": get_tools_status(PROJECT_PATH),
        "system_prompt": file_info(SYSTEM_PROMPT_PATH),
        "config": file_info(CONFIG_PATH),
        "backup_path": dir_info(backup_path),
        "export_path": dir_info(export_path),
        "model": config.get("ollama_model", "gpt-oss:20b"),
        "num_ctx": config.get("num_ctx", 8192)
    }


@app.get("/memory/sade-memory")
def get_sade_memory():
    ensure_paths()
    return read_markdown_file(SADE_MEMORY_PATH)


@app.get("/memory/chatlog")
def get_chat_log():
    ensure_paths()
    return read_markdown_file(CHAT_LOG_PATH)

def get_system_prompt() -> str:
    ensure_paths()

    if not SYSTEM_PROMPT_PATH.exists():
        return "Olet Säde v1, paikallinen tekoälyavustaja. Vastaa suomeksi, selkeästi ja rehellisesti."

    content = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()

    if not content:
        return "Olet Säde v1, paikallinen tekoälyavustaja. Vastaa suomeksi, selkeästi ja rehellisesti."

    return content


@app.post("/memory/sade-memory")
def add_sade_memory_entry(entry: MemoryEntry):
    if not entry.text.strip():
        raise HTTPException(status_code=400, detail="Teksti ei saa olla tyhjä.")

    return append_markdown_entry(SADE_MEMORY_PATH, entry)


@app.post("/memory/visible-chat")
def save_visible_chat(request: VisibleChatSaveRequest):
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="Näkyvä chat on tyhjä.")

    entry = MemoryEntry(
        title="Näkyvä keskustelu tallennettu",
        text=request.content.strip(),
        tags=["chat", "näkyvä keskustelu", "sade-muisti"]
    )

    return append_markdown_entry(SADE_MEMORY_PATH, entry)


@app.post("/memory/search")
def search_memory(request: MemorySearchRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Hakusana ei saa olla tyhjä.")

    return search_sade_memory(request.query)

def _tool_error_to_http(error: ToolError):
    raise HTTPException(status_code=400, detail=str(error))


@app.get("/tools/status")
def tools_status():
    return get_tools_status(PROJECT_PATH)


@app.get("/tools/list")
def tools_list():
    return list_available_tools()


@app.get("/tools/project-status")
def tools_project_status():
    return tool_project_status(PROJECT_PATH)


@app.post("/tools/files/list")
def tools_files_list(request: ToolFileListRequest):
    try:
        return tool_list_files(
            PROJECT_PATH,
            relative_path=request.relative_path or "",
            max_items=request.max_items or 100,
            include_hidden=bool(request.include_hidden),
        )
    except ToolError as error:
        _tool_error_to_http(error)


@app.post("/tools/files/read")
def tools_files_read(request: ToolFileReadRequest):
    try:
        return tool_read_file(
            PROJECT_PATH,
            relative_path=request.relative_path,
            max_chars=request.max_chars or 20000,
        )
    except ToolError as error:
        _tool_error_to_http(error)


@app.post("/tools/files/write")
def tools_files_write(request: ToolFileWriteRequest):
    try:
        return tool_write_file(
            PROJECT_PATH,
            relative_path=request.relative_path,
            content=request.content,
            overwrite=bool(request.overwrite),
        )
    except ToolError as error:
        _tool_error_to_http(error)


@app.post("/tools/files/append")
def tools_files_append(request: ToolFileAppendRequest):
    try:
        return tool_append_file(
            PROJECT_PATH,
            relative_path=request.relative_path,
            content=request.content,
        )
    except ToolError as error:
        _tool_error_to_http(error)


@app.post("/files/summarize")
def files_summarize(request: FileSummarizeRequest):
    if not request.relative_path.strip():
        raise HTTPException(status_code=400, detail="Tiedostopolku ei saa olla tyhjä.")

    result = summarize_file(PROJECT_PATH, request.relative_path)

    log_tool_event(
        PROJECT_PATH,
        tool="summarize_file",
        action="api",
        request=request.model_dump(),
        result=result,
    )

    return result


@app.post("/files/ingest")
def files_ingest(request: FileIngestRequest):
    if not request.relative_path.strip():
        raise HTTPException(status_code=400, detail="Tiedostopolku ei saa olla tyhjä.")

    result = ingest_file(
        PROJECT_PATH,
        request.relative_path,
        add_to_memory=bool(request.add_to_memory),
        add_to_semantic=bool(request.add_to_semantic),
        title=request.title,
        tags=request.tags or ["file", "ingested"],
    )

    log_tool_event(
        PROJECT_PATH,
        tool="ingest_file",
        action="api",
        request=request.model_dump(),
        result=result,
    )

    return result


@app.post("/files/ingestion-log")
def files_ingestion_log(request: ToolLogReadRequest):
    return read_ingestion_log(PROJECT_PATH, limit=request.limit or 50)


@app.post("/tools/log")
def tools_log(request: ToolLogReadRequest):
    return read_tool_log(PROJECT_PATH, limit=request.limit or 50)


@app.post("/tools/router/preview")
def tools_router_preview(request: ToolRouterRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Viesti ei saa olla tyhjä.")

    return route_tool_preview(request.message)


@app.post("/tools/router/run")
def tools_router_run(request: ToolRouterRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Viesti ei saa olla tyhjä.")

    result = route_tool_request(PROJECT_PATH, request.message)

    if result.get("handled"):
        log_tool_event(
            PROJECT_PATH,
            tool=result.get("tool", "tool_router"),
            action="router_api",
            request={"message": request.message},
            result=result.get("result", result),
        )

    return result


@app.get("/semantic/status")
def get_semantic_memory_status():
    return semantic_memory_status(PROJECT_PATH)


@app.post("/memory/semantic/rebuild")
def rebuild_semantic_memory():
    return rebuild_semantic_memory_index(PROJECT_PATH)


@app.post("/memory/semantic/search")
def search_semantic_memory_post(request: MemorySearchRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Hakusana ei saa olla tyhjä.")

    config = load_config()
    n_results = int(config.get("semantic_search_results", 5))

    return search_semantic_memory(PROJECT_PATH, request.query, n_results=n_results)


@app.get("/memory/semantic/search")
def search_semantic_memory_get(q: str, n: int = 5):
    if not q.strip():
        raise HTTPException(status_code=400, detail="Hakusana ei saa olla tyhjä.")

    return search_semantic_memory(PROJECT_PATH, q, n_results=n)


@app.get("/system-prompt")
def get_system_prompt_file():
    ensure_paths()
    return read_markdown_file(SYSTEM_PROMPT_PATH)


@app.post("/system-prompt")
def update_system_prompt_file(request: SystemPromptUpdateRequest):
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="System prompt ei saa olla tyhjä.")

    ensure_paths()

    SYSTEM_PROMPT_PATH.write_text(
        request.content.strip() + "\n",
        encoding="utf-8"
    )

    return {
        "ok": True,
        "message": "System prompt tallennettu.",
        "path": str(SYSTEM_PROMPT_PATH),
        "time": datetime.now().isoformat(timespec="seconds")
    }

@app.post("/export")
def export_data():
    return create_export_file()

@app.post("/backup")
def backup_data():
    return create_backup_files()

@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Viesti ei saa olla tyhjä.")

    memory_text = extract_memory_command(request.message)

    if memory_text:
        entry = MemoryEntry(
            title="Keskustelusta tallennettu muisto",
            text=memory_text,
            tags=["chat", "automaattinen muisti"]
        )

        save_result = append_markdown_entry(SADE_MEMORY_PATH, entry)

        reply = (
            f"Tallensin tämän Säde-muistiin:\n\n"
            f"{memory_text}\n\n"
            f"Aika: {save_result['time']}"
        )

        append_chat_log(request.message, reply)

        return ChatResponse(
            ok=True,
            reply=reply,
            model=load_config().get("ollama_model", "gpt-oss:20b"),
            time=datetime.now().isoformat(timespec="seconds")
        )

    tool_result = route_tool_request(PROJECT_PATH, request.message)

    if tool_result.get("handled"):
        reply = tool_result.get("reply", "Työkalu suoritettiin.")

        log_tool_event(
            PROJECT_PATH,
            tool=tool_result.get("tool", "tool_router"),
            action="chat",
            request={"message": request.message},
            result=tool_result.get("result", tool_result),
        )

        append_chat_log(request.message, reply)

        return ChatResponse(
            ok=True,
            reply=reply,
            model=load_config().get("ollama_model", "gpt-oss:20b"),
            time=datetime.now().isoformat(timespec="seconds")
        )

    prompt = build_sade_prompt(request.message)
    reply = ask_ollama(prompt)

    append_chat_log(request.message, reply)

    return ChatResponse(
        ok=True,
        reply=reply,
        model=load_config().get("ollama_model", "gpt-oss:20b"),
        time=datetime.now().isoformat(timespec="seconds")
    )


@app.get("/ui", response_class=HTMLResponse)
def ui():
    ensure_paths()

    if not UI_TEMPLATE_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail=f"UI-templatea ei löytynyt: {UI_TEMPLATE_PATH}"
        )

    return HTMLResponse(
        content=UI_TEMPLATE_PATH.read_text(encoding="utf-8"),
        status_code=200
    )

    return HTMLResponse(
        content=UI_TEMPLATE_PATH.read_text(encoding="utf-8"),
        status_code=200
    )
