from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, List
import json
import hmac
import os
import re
import subprocess
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

from app.audit_log import (
    AuditLogError,
    audit_status,
    read_audit_log,
    write_audit_event,
)
from app.learning_feedback import build_feedback_context
from app.ai_evals import run_static_evals
from app.backup_restore import (
    RESTORE_CONFIRMATION,
    create_backup_archive,
    list_backup_archives,
    restore_backup_archive,
)
from app.debug_trace import read_traces, summarize_latest_trace, write_trace
from app.memory_governance import (
    DELETE_CONFIRMATION,
    delete_memory_entry,
    export_memory_json,
    list_memory_entries,
)
from app.chat_pipeline import ChatPipelineDependencies, handle_chat_message
from app.intent_planner import plan_response
from app.live_evals import run_live_evals
from app.model_provider import ModelProviderError, model_provider_status, provider_from_config
from app.prompt_injection import analyze_prompt_injection, build_prompt_injection_guardrail
from app.rag_quality import evaluate_rag_quality
from app.tool_permissions import annotate_tool_result, get_tool_policy, list_tool_policies

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from app.task_queue import (
    add_task,
    cancel_task,
    get_task_queue_status,
    list_tasks,
    read_task_history,
    run_next_task,
    run_task_by_id,
)

from app.codebase_map import (
    build_codebase_map,
    find_in_codebase_map,
    read_codebase_map,
)

from app.autonomous_learning import (
    get_learning_status,
    read_learning_log,
    run_autonomous_learning_loop,
    scan_uploads_for_learning,
)

from app.learning_review import (
    create_learning_review_for_file,
    create_reviews_for_recent_learning,
    get_learning_review_status,
    read_learning_reviews,
)

from app.rag_engine import (
    build_rag_context,
    format_rag_search_reply,
    rag_search,
    rag_status,
)

from app.semantic_memory import (
    add_text_to_semantic_memory,
    format_semantic_context,
    rebuild_semantic_memory_index,
    search_semantic_memory,
    semantic_memory_status,
)

from app.language_pack import (
    build_language_context,
    language_status,
)

from app.web_search import web_search_status as get_web_search_status
from app.auth import (
    SESSION_COOKIE,
    SESSION_TTL_SECONDS,
    auth_configured,
    create_session,
    get_session,
    revoke_session,
    verify_credentials,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_paths()
    yield


app = FastAPI(title="Local AI Workspace", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

PROJECT_PATH = Path(__file__).resolve().parent
REPO_ROOT = PROJECT_PATH.parent
BASE_PATH = PROJECT_PATH
CONFIG_PATH = PROJECT_PATH / "config.json"
VERSION_PATH = REPO_ROOT / "VERSION"
README_PATH = REPO_ROOT / "README.md"

MEMORY_PATH = PROJECT_PATH / "memory"
SADE_MEMORY_PATH = MEMORY_PATH / "sade_memory.md"
LOG_PATH = MEMORY_PATH / "memory_log.jsonl"
CHAT_LOG_PATH = MEMORY_PATH / "chat_log.md"
SYSTEM_PROMPT_PATH = PROJECT_PATH / "system_prompt.md"
TEMPLATES_PATH = PROJECT_PATH / "templates"
UI_TEMPLATE_PATH = TEMPLATES_PATH / "ui.html"
LOGIN_TEMPLATE_PATH = TEMPLATES_PATH / "login.html"
UPLOADS_PATH = PROJECT_PATH / "uploads"
TASKS_PATH = MEMORY_PATH / "tasks.json"
TASK_HISTORY_PATH = MEMORY_PATH / "task_history.jsonl"
CODEBASE_MAP_PATH = MEMORY_PATH / "codebase_map.json"
AUTONOMOUS_LEARNING_LOG_PATH = MEMORY_PATH / "autonomous_learning_log.jsonl"
LEARNING_REVIEWS_MD_PATH = MEMORY_PATH / "learning_reviews.md"
LEARNING_REVIEWS_LOG_PATH = MEMORY_PATH / "learning_reviews.jsonl"

UPLOAD_ALLOWED_EXTENSIONS = {
    ".txt", ".md", ".json", ".py", ".html", ".htm", ".css", ".js",
    ".yml", ".yaml", ".toml", ".ini", ".ps1", ".bat"
}
UPLOAD_MAX_BYTES = 25 * 1024 * 1024
TOOL_LOG_PATH = MEMORY_PATH / "tool_log.jsonl"
INGESTION_LOG_PATH = MEMORY_PATH / "ingested_files.jsonl"


def _audit(
    *,
    category: str,
    action: str,
    outcome: str,
    risk_level: str = "low",
    reason: str = "",
    target: Optional[str] = None,
    details: Optional[dict] = None,
    required: bool = False,
):
    try:
        return write_audit_event(
            PROJECT_PATH,
            category=category,
            action=action,
            outcome=outcome,
            risk_level=risk_level,
            reason=reason,
            target=target,
            details=details,
        )
    except (AuditLogError, OSError, ValueError) as error:
        if required:
            raise HTTPException(status_code=503, detail=f"Audit-lokia ei voitu kirjoittaa: {error}") from error
        return {"ok": False, "error": str(error)}


def _audit_risk(policy_risk: str) -> str:
    if policy_risk in {"file_write", "memory_write", "system", "critical", "high"}:
        return "high"
    if policy_risk in {"search", "medium"}:
        return "medium"
    return "low"


class MemoryEntry(BaseModel):
    title: Optional[str] = Field(default=None, description="Merkinnän otsikko")
    text: str = Field(..., description="Varsinainen merkintäteksti")
    tags: Optional[List[str]] = Field(default=None, description="Vapaaehtoiset tagit")


class ChatRequest(BaseModel):
    message: str = Field(..., description="Käyttäjän viesti")


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class ChatResponse(BaseModel):
    ok: bool
    reply: str
    model: str
    time: str
    actions: Optional[List[Dict[str, str]]] = None


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
    ui_language: Optional[str] = None

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


class TaskAddRequest(BaseModel):
    prompt: str = Field(..., description="Tehtävän sisältö")
    title: Optional[str] = Field(default=None, description="Tehtävän otsikko")
    tags: Optional[List[str]] = Field(default=None, description="Tagit")
    priority: Optional[int] = Field(default=3, description="Prioriteetti, suurempi suoritetaan ensin")


class TaskListRequest(BaseModel):
    status: Optional[str] = Field(default=None, description="queued, running, done, failed tai cancelled")
    limit: Optional[int] = Field(default=50, description="Kuinka monta tehtävää palautetaan")


class TaskRunRequest(BaseModel):
    task_id: str = Field(..., description="Suoritettavan tehtävän ID")


class TaskCancelRequest(BaseModel):
    task_id: str = Field(..., description="Peruttavan tehtävän ID")


class TaskHistoryRequest(BaseModel):
    limit: Optional[int] = Field(default=50, description="Kuinka monta lokiriviä palautetaan")


class DevMapRequest(BaseModel):
    include_snippets: Optional[bool] = Field(default=False, description="Tallennetaanko lyhyet koodikatkelmat mapin mukaan")


class DevFindRequest(BaseModel):
    query: str = Field(..., description="Hakusana codebase mapista")
    limit: Optional[int] = Field(default=20, description="Maksimimäärä tuloksia")


class LearningScanRequest(BaseModel):
    include_already_ingested: Optional[bool] = Field(default=False, description="Näytetäänkö myös jo opitut tiedostot")
    limit: Optional[int] = Field(default=100, description="Maksimimäärä skannattavia tuloksia")


class LearningRunRequest(BaseModel):
    max_files: Optional[int] = Field(default=10, description="Maksimi tiedostomäärä yhdellä oppimiskierroksella")
    add_to_memory: Optional[bool] = Field(default=True, description="Lisätäänkö tiivistelmä Säde-muistiin")
    add_to_semantic: Optional[bool] = Field(default=True, description="Lisätäänkö sisältö semanttiseen muistiin")


class LearningLogRequest(BaseModel):
    limit: Optional[int] = Field(default=50, description="Kuinka monta lokimerkintää palautetaan")


class LearningReviewFileRequest(BaseModel):
    relative_path: str = Field(..., description="Tiedostopolku projektin sisältä, esimerkiksi uploads/ai_agent_terms_atlas.md")
    force: Optional[bool] = Field(default=False, description="Luodaanko uusi katsaus vaikka samasta tiedostoversiosta on jo katsaus")


class LearningReviewRecentRequest(BaseModel):
    max_files: Optional[int] = Field(default=10, description="Montako viimeksi opittua tiedostoa katselmoidaan")
    force: Optional[bool] = Field(default=False, description="Luodaanko katsaukset uudelleen myös jo katselmoiduille tiedostoille")


class LearningReviewLogRequest(BaseModel):
    limit: Optional[int] = Field(default=50, description="Kuinka monta katsausta palautetaan")


class RagSearchRequest(BaseModel):
    query: str = Field(..., description="RAG-haku")
    n_results: Optional[int] = Field(default=8, description="Palautettavien osumien määrä")
    include_chat_log: Optional[bool] = Field(default=False, description="Sisällytetäänkö chat_log.md hakutuloksiin")


class MemoryDeleteRequest(BaseModel):
    entry_id: str = Field(..., description="Poistettavan muistimerkinnän id")
    confirmation: str = Field(..., description="Täsmällinen poistovahvistus")


class BackupRestoreRequest(BaseModel):
    backup_name: str = Field(..., description="Palautettavan zip-varmuuskopion tiedostonimi")
    confirmation: str = Field(..., description="Täsmällinen palautusvahvistus")


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
        "rag_context_chars": 4500,
        "rag_search_results": 8,
        "rag_include_chat_log": False,
        "ui_language": "fi",
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

    merged = {**default_config, **config}

    env_overrides = {
        "ollama_url": os.getenv("SADE_OLLAMA_URL"),
        "ollama_model": os.getenv("SADE_OLLAMA_MODEL"),
        "temperature": os.getenv("SADE_TEMPERATURE"),
        "num_ctx": os.getenv("SADE_NUM_CTX"),
        "memory_context_chars": os.getenv("SADE_MEMORY_CONTEXT_CHARS"),
        "chat_context_chars": os.getenv("SADE_CHAT_CONTEXT_CHARS"),
        "semantic_context_chars": os.getenv("SADE_SEMANTIC_CONTEXT_CHARS"),
        "semantic_search_results": os.getenv("SADE_SEMANTIC_SEARCH_RESULTS"),
        "rag_context_chars": os.getenv("SADE_RAG_CONTEXT_CHARS"),
        "rag_search_results": os.getenv("SADE_RAG_SEARCH_RESULTS"),
        "ui_language": os.getenv("SADE_UI_LANGUAGE"),
    }

    for key, value in env_overrides.items():
        if value is None or str(value).strip() == "":
            continue
        if key in {"temperature"}:
            merged[key] = float(value)
        elif key in {
            "num_ctx",
            "memory_context_chars",
            "chat_context_chars",
            "semantic_context_chars",
            "semantic_search_results",
            "rag_context_chars",
            "rag_search_results",
        }:
            merged[key] = int(value)
        else:
            merged[key] = value

    return merged

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

    if updates.ui_language is not None:
        language = updates.ui_language.strip().lower()
        if language not in {"fi", "en"}:
            raise HTTPException(status_code=400, detail="ui_language pitää olla fi tai en.")
        config["ui_language"] = language

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

def get_version() -> str:
    if not VERSION_PATH.exists():
        return "0.0.0-dev"

    version = VERSION_PATH.read_text(encoding="utf-8").strip()
    return version or "0.0.0-dev"


def get_git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return "unknown"

    commit = result.stdout.strip()
    return commit or "unknown"


SERVER_STARTED_AT = datetime.now().isoformat(timespec="seconds")


def build_info() -> Dict[str, str]:
    return {
        "version": get_version(),
        "build": get_git_commit(),
        "backend_started": SERVER_STARTED_AT,
    }


def _component_state(*, ok: bool, status: str = "configured", detail: str = "") -> Dict[str, Any]:
    return {
        "ok": bool(ok),
        "status": status,
        "detail": detail,
    }


def _configured_path_state(path: Path) -> Dict[str, Any]:
    return {
        "configured": True,
        "exists": path.exists(),
        "kind": "directory" if path.exists() and path.is_dir() else "file" if path.exists() and path.is_file() else "unknown",
    }


def _latest_known_quality_status() -> Dict[str, Any]:
    text = ""
    try:
        text = README_PATH.read_text(encoding="utf-8", errors="replace")
    except Exception:
        text = ""

    tests_match = re.search(r"(?P<count>\d+)\s+passed\s+locally", text, flags=re.IGNORECASE)
    coverage_match = re.search(r"coverage:\s*(?P<coverage>\d+)%", text, flags=re.IGNORECASE)
    actions_passing = "GitHub Actions: passing" in text

    return {
        "tests": f"{tests_match.group('count')} passed locally" if tests_match else "unknown",
        "coverage": f"{coverage_match.group('coverage')}%" if coverage_match else "unknown",
        "github_actions": "passing" if actions_passing else "unknown",
        "source": "README.md",
    }


def _release_readiness_status() -> Dict[str, Any]:
    required = [
        "README.md",
        "QUICKSTART.md",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "VERSION",
        ".github/workflows/tests.yml",
        "scripts/release_readiness.py",
    ]
    missing = [item for item in required if not (REPO_ROOT / item).exists()]
    return {
        "ok": not missing,
        "status": "OK" if not missing else "attention",
        "missing": missing,
    }


def build_health_summary() -> Dict[str, Any]:
    ensure_paths()
    config = load_config()
    info = build_info()
    quality = _latest_known_quality_status()
    release = _release_readiness_status()

    try:
        audit = audit_status(PROJECT_PATH)
    except Exception as error:
        audit = {"valid": False, "error": str(error)}

    try:
        web = get_web_search_status(PROJECT_PATH)
    except Exception as error:
        web = {"ok": False, "enabled": False, "error": str(error)}

    rag_engine_path = PROJECT_PATH / "rag_engine.py"
    semantic_vector_path = PROJECT_PATH / "memory" / "vector_db"
    rag_ok = rag_engine_path.exists() and SADE_MEMORY_PATH.exists()

    backup_path = Path(config.get("backup_path", "D:/Sade_Backups"))
    export_path = Path(config.get("export_path", "D:/Sade_Exports"))
    model_store = os.environ.get("OLLAMA_MODELS", "")
    known_external_model_store = Path("D:/Ollama/models")
    model_store_configured = bool(model_store) or known_external_model_store.exists()
    model_store_exists = Path(model_store).exists() if model_store else known_external_model_store.exists()
    disk_warnings: List[str] = []

    try:
        usage = shutil.disk_usage(str(REPO_ROOT.anchor or REPO_ROOT))
        free_gb = round(usage.free / (1024 ** 3), 1)
        if free_gb < 10:
            disk_warnings.append("System drive has less than 10 GB free.")
    except Exception:
        free_gb = None

    return {
        "ok": True,
        "mode": "sanitized_health_summary",
        "time": datetime.now().isoformat(timespec="seconds"),
        "server": _component_state(ok=True, status="running", detail="FastAPI backend is responding."),
        "version": {
            "version": info["version"],
            "build": info["build"],
            "backend_started": info["backend_started"],
        },
        "model": {
            "ok": True,
            "provider": str(config.get("model_provider", "ollama")),
            "model": config.get("ollama_model", "gpt-oss:20b"),
            "num_ctx": config.get("num_ctx", 8192),
        },
        "memory": {
            "configured": True,
            "assistant_memory": _configured_path_state(SADE_MEMORY_PATH),
            "chat_log": _configured_path_state(CHAT_LOG_PATH),
            "semantic_memory": {
                "ok": semantic_vector_path.exists(),
                "enabled": semantic_vector_path.exists(),
                "count": None,
            },
        },
        "rag": {
            "ok": rag_ok,
            "version": "configured" if rag_ok else "attention",
            "default_n_results": config.get("semantic_search_results", 5),
        },
        "web_search": {
            "ok": bool(web.get("ok")),
            "enabled": bool(web.get("enabled")),
            "provider": web.get("provider", "unknown"),
            "automatic_search": bool(web.get("automatic_search")),
            "latest_success": {
                "time": (web.get("latest_success") or {}).get("time"),
                "query": (web.get("latest_success") or {}).get("query"),
                "result_count": (web.get("latest_success") or {}).get("result_count"),
            } if web.get("latest_success") else None,
        },
        "audit_log": {
            "ok": bool(audit.get("valid", audit.get("ok", False))),
            "valid": bool(audit.get("valid", False)),
            "count": audit.get("count"),
            "last_event_at": audit.get("last_event_at"),
        },
        "quality": {
            "tests": quality["tests"],
            "coverage": quality["coverage"],
            "github_actions": quality["github_actions"],
            "release_readiness": release["status"],
        },
        "storage": {
            "backup_path": _configured_path_state(backup_path),
            "export_path": _configured_path_state(export_path),
            "model_store": {
                "configured": model_store_configured,
                "exists": model_store_exists,
                "location": "configured" if model_store_configured else "default",
            },
            "system_drive_free_gb": free_gb,
            "warnings": disk_warnings,
        },
        "privacy": {
            "local_paths_hidden": True,
            "raw_debug_available_separately": True,
        },
    }


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

    try:
        semantic_result = add_text_to_semantic_memory(
            PROJECT_PATH,
            entry.text,
            title=title,
            source=path.name,
            tags=entry.tags or [],
            timestamp=timestamp
        )
    except Exception as error:
        semantic_result = {
            "ok": False,
            "indexed": False,
            "error": str(error),
            "message": "Memory was written, but semantic indexing failed.",
        }

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



def get_rag_context(query: str) -> str:
    config = load_config()

    max_chars = int(config.get("rag_context_chars", 4500))
    n_results = int(config.get("rag_search_results", 8))
    include_chat_log = bool(config.get("rag_include_chat_log", False))

    try:
        return build_rag_context(
            PROJECT_PATH,
            query,
            n_results=n_results,
            max_chars=max_chars,
            include_chat_log=include_chat_log,
            min_score=35.0,
        )
    except Exception as error:
        return f"RAG-kontekstia ei voitu rakentaa: {error}"


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
    try:
        text = str(provider_from_config(config).generate(prompt).text or "").strip()
    except ModelProviderError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if not text:
        raise HTTPException(
            status_code=502,
            detail="Model provider returned an empty response. Check the selected model, Ollama logs, and model availability.",
        )
    return text


def build_sade_prompt(user_message: str, planning: Optional[Any] = None) -> str:
    planning = planning or plan_response(user_message)
    system_prompt = get_system_prompt()
    language_context = build_language_context(user_message)
    injection_guardrail = build_prompt_injection_guardrail(user_message)
    rag_context = get_rag_context(user_message) if getattr(planning, "use_rag", False) else ""
    memory_context = get_memory_context() if getattr(planning, "use_memory", False) else ""
    chat_context = get_chat_context() if getattr(planning, "use_chat_context", False) else ""
    feedback_context = build_feedback_context(PROJECT_PATH)

    return f"""
{system_prompt}

Suomen kielen vastausohje:
{language_context}

Prompt injection -suoja:
{injection_guardrail}

RAG-konteksti, laadun mukaan priorisoidut muistot ja dokumentit:
{rag_context or 'Ei sisällytetty tähän vastaukseen context gate -päätöksen vuoksi.'}

Ohje: Käytä ensisijaisesti RAG-kontekstin learning_review-, atlas-, operating_manual- ja sade_memory-lähteitä. Älä nojaa chat_log-osumiin, ellei niitä ole erikseen annettu ja ne ole selvästi relevantteja.

Pitkäaikainen muisti, Säde-muisti:
{memory_context or 'Ei sisällytetty tähän vastaukseen context gate -päätöksen vuoksi.'}

Viimeaikainen keskusteluloki:
{chat_context or 'Ei sisällytetty tähän vastaukseen context gate -päätöksen vuoksi.'}

Keskustelun jatko-ohje:
Jos viimeaikainen keskusteluloki on sisällytetty ja käyttäjän uusi viesti viittaa aiempaan aiheeseen
sanoilla kuten "siihen", "siitä", "sille", "tuohon", "entä", "mikä olisi hyvä" tai vastaavilla,
ratkaise viittaus ensisijaisesti viimeisimmästä käyttäjän ja avustajan aiheesta. Älä vaihda aihetta
Local AI Workspace -projektiesittelyyn, ellei käyttäjä nimenomaan kysy projektista.

Käyttäjän eksplisiittiset oppimiskorjaukset:
{feedback_context or 'Ei tallennettuja korjauksia.'}

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

@app.get("/")
def root():
    config = load_config()

    return {
        "name": "Local AI Workspace",
        "status": "awake",
        "message": "Local AI Workspace is running.",
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
            "/rag/status",
            "/rag/search",
            "/semantic/status",
            "/language/status",
            "/web-search/status",
            "/tools/status",
            "/tools/list",
            "/tools/project-status",
            "/tools/files/list",
            "/tools/files/read",
            "/tools/files/write",
            "/tools/files/append",
            "/tools/router/preview",
            "/tools/router/run",
            "/files/upload",
            "/learning/review/status",
            "/learning/review/file",
            "/learning/review/recent",
            "/learning/review/log",
            "/learning/status",
            "/learning/scan",
            "/learning/run",
            "/learning/log",
            "/dev/status",
            "/dev/map",
            "/dev/find",
            "/tasks/status",
            "/tasks/add",
            "/tasks/list",
            "/tasks/run-next",
            "/tasks/run",
            "/tasks/cancel",
            "/tasks/history",
            "/files/ingest",
            "/files/summarize",
            "/files/ingestion-log",
            "/tools/log",
            "/audit/status",
            "/audit/log",
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
        "semantic_search_results": config.get("semantic_search_results", 5),
        "ui_language": config.get("ui_language", "fi")
    }

@app.post("/config")
def update_config(request: ConfigUpdateRequest):
    _audit(
        category="configuration",
        action="update_config",
        outcome="attempt",
        risk_level="medium",
        reason="Käyttäjä pyysi malliasetusten tallennusta.",
        target="app/config.json",
        details=request.model_dump(exclude_none=True),
        required=True,
    )
    config = save_config_updates(request)
    _audit(
        category="configuration",
        action="update_config",
        outcome="success",
        risk_level="medium",
        reason="Malliasetukset tallennettiin.",
        target="app/config.json",
        details={"updated_fields": sorted(request.model_dump(exclude_none=True))},
    )

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
    info = build_info()

    return {
        "ok": True,
        "status": "running",
        "model": config.get("ollama_model", "gpt-oss:20b"),
        "temperature": config.get("temperature", 0.7),
        "num_ctx": config.get("num_ctx", 8192),
        "time": datetime.now().isoformat(timespec="seconds"),
        "version": info["version"],
        "build": info["build"],
        "backend_started": info["backend_started"],
        "build_info": info,
    }


@app.get("/health/summary")
def health_summary():
    return build_health_summary()

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
        "build_info": build_info(),
        "project": dir_info(PROJECT_PATH),
        "memory": dir_info(MEMORY_PATH),
        "sade_memory": file_info(SADE_MEMORY_PATH),
        "chat_log": file_info(CHAT_LOG_PATH),
        "memory_log": file_info(LOG_PATH),
        "tasks": file_info(TASKS_PATH),
        "task_history": file_info(TASK_HISTORY_PATH),
        "task_queue": get_task_queue_status(PROJECT_PATH),
        "codebase_map": file_info(CODEBASE_MAP_PATH),
        "autonomous_learning": file_info(AUTONOMOUS_LEARNING_LOG_PATH),
        "learning_reviews": file_info(LEARNING_REVIEWS_MD_PATH),
        "learning_reviews_log": file_info(LEARNING_REVIEWS_LOG_PATH),
        "learning_review_status": get_learning_review_status(PROJECT_PATH),
        "learning_status": get_learning_status(PROJECT_PATH),
        "tool_log": file_info(TOOL_LOG_PATH),
        "audit_log": audit_status(PROJECT_PATH),
        "ingestion_log": file_info(INGESTION_LOG_PATH),
        "uploads": dir_info(UPLOADS_PATH),
        "semantic_memory": semantic_memory_status(PROJECT_PATH),
        "language_pack": language_status(PROJECT_PATH),
        "web_search": get_web_search_status(PROJECT_PATH),
        "tools": get_tools_status(PROJECT_PATH),
        "system_prompt": file_info(SYSTEM_PROMPT_PATH),
        "config": file_info(CONFIG_PATH),
        "backup_path": dir_info(backup_path),
        "export_path": dir_info(export_path),
        "model": config.get("ollama_model", "gpt-oss:20b"),
        "num_ctx": config.get("num_ctx", 8192)
    }


@app.get("/model/status")
def get_model_status():
    return model_provider_status(load_config())


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


@app.get("/memory/entries")
def memory_entries(limit: int = 100):
    return list_memory_entries(PROJECT_PATH, limit=limit)


@app.post("/memory/export")
def memory_export():
    _audit(category="data", action="export_memory_json", outcome="attempt", risk_level="medium", reason="Käyttäjä pyysi muistin vientiä.", required=True)
    return export_memory_json(PROJECT_PATH)


@app.post("/memory/delete-entry")
def memory_delete_entry(request: MemoryDeleteRequest):
    _audit(category="memory", action="delete_memory_entry", outcome="attempt", risk_level="high", reason="Käyttäjä pyysi yksittäisen muistimerkinnän poistoa.", target=request.entry_id, required=True)
    result = delete_memory_entry(PROJECT_PATH, request.entry_id, confirmation=request.confirmation)
    if not result.get("ok"):
        _audit(category="memory", action="delete_memory_entry", outcome="denied", risk_level="high", reason=result.get("message", "Poisto estettiin."), target=request.entry_id)
    return result

def _tool_error_to_http(error: ToolError):
    raise HTTPException(status_code=400, detail=str(error))


@app.get("/tools/status")
def tools_status():
    return get_tools_status(PROJECT_PATH)


@app.get("/tools/list")
def tools_list():
    return list_available_tools()


@app.get("/tools/policies")
def tools_policies():
    return list_tool_policies()


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
    _audit(category="filesystem", action="write_file", outcome="attempt", risk_level="high", reason="Työkalurajapinnan kirjoituspyyntö.", target=request.relative_path, details={"overwrite": bool(request.overwrite)}, required=True)
    try:
        result = tool_write_file(
            PROJECT_PATH,
            relative_path=request.relative_path,
            content=request.content,
            overwrite=bool(request.overwrite),
        )
        _audit(category="filesystem", action="write_file", outcome="success", risk_level="high", reason="Tiedosto kirjoitettiin työkalurajapinnalla.", target=request.relative_path, details={"overwrite": bool(request.overwrite)})
        return result
    except ToolError as error:
        _audit(category="filesystem", action="write_file", outcome="denied", risk_level="high", reason=str(error), target=request.relative_path)
        _tool_error_to_http(error)


@app.post("/tools/files/append")
def tools_files_append(request: ToolFileAppendRequest):
    _audit(category="filesystem", action="append_file", outcome="attempt", risk_level="medium", reason="Työkalurajapinnan append-pyyntö.", target=request.relative_path, required=True)
    try:
        result = tool_append_file(
            PROJECT_PATH,
            relative_path=request.relative_path,
            content=request.content,
        )
        _audit(category="filesystem", action="append_file", outcome="success", risk_level="medium", reason="Sisältö lisättiin tiedostoon.", target=request.relative_path)
        return result
    except ToolError as error:
        _audit(category="filesystem", action="append_file", outcome="denied", risk_level="medium", reason=str(error), target=request.relative_path)
        _tool_error_to_http(error)



@app.post("/files/upload")
async def upload_file(file: UploadFile = File(...)):
    ensure_paths()

    original_name = Path(file.filename or "").name.strip()

    if not original_name:
        raise HTTPException(status_code=400, detail="Tiedostonimi puuttuu.")

    suffix = Path(original_name).suffix.lower()

    if suffix not in UPLOAD_ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Tiedostotyyppi ei ole sallittu upload v1:ssä: {suffix}"
        )

    data = await file.read()

    if not data:
        raise HTTPException(status_code=400, detail="Tiedosto on tyhjä.")

    if len(data) > UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Tiedosto on liian suuri. Maksimi on {UPLOAD_MAX_BYTES} tavua."
        )

    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Upload v1 tukee vain UTF-8-tekstitiedostoja."
        )

    target = UPLOADS_PATH / original_name

    if target.exists():
        stem = target.stem
        ext = target.suffix
        counter = 1

        while True:
            candidate = UPLOADS_PATH / f"{stem}_{counter}{ext}"
            if not candidate.exists():
                target = candidate
                break
            counter += 1

    _audit(
        category="filesystem",
        action="upload_file",
        outcome="attempt",
        risk_level="medium",
        reason="Käyttäjä lähetti tiedoston uploads-kansioon.",
        target=str(target.relative_to(PROJECT_PATH)).replace("\\", "/"),
        details={"filename": original_name, "size_bytes": len(data)},
        required=True,
    )
    target.write_bytes(data)

    relative_path = str(target.relative_to(PROJECT_PATH)).replace("\\", "/")

    result = {
        "ok": True,
        "message": "Tiedosto ladattu Säteelle.",
        "filename": target.name,
        "relative_path": relative_path,
        "path": str(target),
        "size_bytes": target.stat().st_size,
        "time": datetime.now().isoformat(timespec="seconds"),
        "next_steps": [
            f"tiivistä tiedosto {relative_path}",
            f"lisää tiedosto {relative_path} muistiin"
        ]
    }

    _audit(
        category="filesystem",
        action="upload_file",
        outcome="success",
        risk_level="medium",
        reason="Tiedosto tallennettiin uploads-kansioon.",
        target=relative_path,
        details={"filename": target.name, "size_bytes": target.stat().st_size},
    )

    try:
        log_tool_event(
            PROJECT_PATH,
            tool="upload_file",
            action="api",
            request={"filename": original_name, "size_bytes": len(data)},
            result=result,
        )
    except Exception:
        pass

    return result

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


@app.get("/audit/status")
def get_audit_status():
    return audit_status(PROJECT_PATH)


@app.post("/audit/log")
def get_audit_log(request: ToolLogReadRequest):
    return read_audit_log(PROJECT_PATH, limit=request.limit or 50)


@app.get("/debug/trace")
def debug_trace(limit: int = 50):
    return read_traces(PROJECT_PATH, limit=limit)


@app.get("/debug/trace/summary")
def debug_trace_summary(limit: int = 40):
    return summarize_latest_trace(PROJECT_PATH, limit=limit)


@app.get("/evals/static")
def static_evals():
    return run_static_evals(PROJECT_PATH)


@app.post("/evals/live")
def live_evals(max_cases: int = 3):
    _audit(category="evaluation", action="run_live_evals", outcome="attempt", risk_level="medium", reason="Käyttäjä pyysi live-mallin eval-ajon.", details={"max_cases": max_cases}, required=True)
    result = run_live_evals(load_config(), max_cases=max_cases)
    _audit(category="evaluation", action="run_live_evals", outcome="success" if result.get("ok") else "failure", risk_level="medium", reason="Live-eval-ajo päättyi.", details={"passed": result.get("passed"), "total": result.get("total")})
    return result


@app.post("/security/prompt-injection/analyze")
def prompt_injection_analyze(request: ChatRequest):
    return analyze_prompt_injection(request.message)


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
        _audit(
            category="tool_router",
            action=str(result.get("tool", "unknown")),
            outcome="success" if result.get("result", result).get("ok", True) else "failure",
            risk_level="medium",
            reason="Työkalupyyntö käsiteltiin API-reitillä.",
            details={"handled": True, "message": request.message},
        )

    return result


@app.get("/semantic/status")
def get_semantic_memory_status():
    return semantic_memory_status(PROJECT_PATH)


@app.get("/language/status")
def get_language_status():
    return language_status(PROJECT_PATH)


@app.get("/web-search/status")
def get_web_search_status_endpoint():
    return get_web_search_status(PROJECT_PATH)


@app.post("/memory/semantic/rebuild")
def rebuild_semantic_memory():
    _audit(category="memory", action="rebuild_semantic_index", outcome="attempt", risk_level="high", reason="Käyttäjä pyysi semanttisen indeksin uudelleenrakennusta.", target="app/memory/vector_db", required=True)
    result = rebuild_semantic_memory_index(PROJECT_PATH)
    _audit(category="memory", action="rebuild_semantic_index", outcome="success" if result.get("ok") else "failure", risk_level="high", reason=result.get("message", "Semanttisen indeksin uudelleenrakennus valmis."), target="app/memory/vector_db", details={"count": result.get("count"), "chunks": result.get("chunks")})
    return result


@app.post("/memory/semantic/search")
def search_semantic_memory_post(request: MemorySearchRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Hakusana ei saa olla tyhjä.")

    config = load_config()
    n_results = int(config.get("semantic_search_results", 5))

    return search_semantic_memory(PROJECT_PATH, request.query, n_results=n_results)



@app.get("/rag/status")
def rag_engine_status():
    return rag_status(PROJECT_PATH)


@app.post("/rag/search")
def rag_engine_search(request: RagSearchRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Hakusana ei saa olla tyhjä.")

    result = rag_search(
        PROJECT_PATH,
        request.query,
        n_results=request.n_results or 8,
        include_chat_log=bool(request.include_chat_log),
        min_score=35.0,
    )

    try:
        log_tool_event(
            PROJECT_PATH,
            tool="rag_engine",
            action="search",
            request=request.model_dump(),
            result={
                "ok": result.get("ok"),
                "count": result.get("count"),
                "total_candidates": result.get("total_candidates"),
            },
        )
    except Exception:
        pass

    return result


@app.post("/rag/quality")
def rag_engine_quality(request: RagSearchRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Hakusana ei saa olla tyhjÃ¤.")
    result = rag_search(
        PROJECT_PATH,
        request.query,
        n_results=request.n_results or 8,
        include_chat_log=bool(request.include_chat_log),
        min_score=35.0,
    )
    return evaluate_rag_quality(result, query=request.query)


@app.get("/rag/search")
def rag_engine_search_get(q: str, n: int = 8, include_chat_log: bool = False):
    if not q.strip():
        raise HTTPException(status_code=400, detail="Hakusana ei saa olla tyhjä.")

    return rag_search(
        PROJECT_PATH,
        q,
        n_results=n,
        include_chat_log=include_chat_log,
        min_score=35.0,
    )


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

    _audit(category="configuration", action="update_system_prompt", outcome="attempt", risk_level="high", reason="Käyttäjä pyysi ydinpromptin tallennusta.", target="app/system_prompt.md", required=True)
    ensure_paths()

    SYSTEM_PROMPT_PATH.write_text(
        request.content.strip() + "\n",
        encoding="utf-8"
    )
    _audit(category="configuration", action="update_system_prompt", outcome="success", risk_level="high", reason="Ydinprompti tallennettiin.", target="app/system_prompt.md", details={"characters": len(request.content)})

    return {
        "ok": True,
        "message": "System prompt tallennettu.",
        "path": str(SYSTEM_PROMPT_PATH),
        "time": datetime.now().isoformat(timespec="seconds")
    }

@app.post("/export")
def export_data():
    _audit(category="data", action="create_export", outcome="attempt", risk_level="medium", reason="Käyttäjä pyysi vientitiedostoa.", required=True)
    result = create_export_file()
    _audit(category="data", action="create_export", outcome="success" if result.get("ok", True) else "failure", risk_level="medium", reason=result.get("message", "Vienti valmis."), target=result.get("export_path"))
    return result

@app.post("/backup")
def backup_data():
    _audit(category="data", action="create_backup", outcome="attempt", risk_level="medium", reason="Käyttäjä pyysi varmuuskopiota.", required=True)
    result = create_backup_files()
    _audit(category="data", action="create_backup", outcome="success" if result.get("ok", True) else "failure", risk_level="medium", reason=result.get("message", "Varmuuskopio valmis."), target=result.get("backup_path"))
    return result

@app.get("/backup/list")
def backup_list():
    return list_backup_archives(PROJECT_PATH)


@app.post("/backup/archive")
def backup_archive():
    _audit(category="data", action="create_backup_archive", outcome="attempt", risk_level="medium", reason="Käyttäjä pyysi zip-varmuuskopiota.", required=True)
    return create_backup_archive(PROJECT_PATH)


@app.post("/backup/restore")
def backup_restore(request: BackupRestoreRequest):
    return restore_backup_archive(PROJECT_PATH, request.backup_name, confirmation=request.confirmation)


def _execute_task_prompt(task_prompt: str):
    tool_result = route_tool_request(PROJECT_PATH, task_prompt)

    if tool_result.get("handled"):
        return {
            "ok": True,
            "type": "tool",
            "tool": tool_result.get("tool"),
            "reply": tool_result.get("reply", "Työkalu suoritettu."),
            "result": tool_result.get("result", tool_result)
        }

    prompt = build_sade_prompt(task_prompt)
    reply = ask_ollama(prompt)

    return {
        "ok": True,
        "type": "llm",
        "reply": reply
    }


def _format_task_list_for_chat(result):
    tasks = result.get("tasks") or []

    if not tasks:
        return "Tehtäväjono on tyhjä."

    lines = [f"Tehtäväjonossa on {len(tasks)} tehtävää:", ""]

    for task in tasks[:20]:
        status = task.get("status", "?")
        task_id = task.get("id", "?")
        title = task.get("title", "Nimetön tehtävä")
        priority = task.get("priority", 3)
        lines.append(f"- `{task_id}` [{status}] p{priority}: {title}")

    if len(tasks) > 20:
        lines.append("")
        lines.append(f"...ja {len(tasks) - 20} muuta.")

    return "\n".join(lines)


def _handle_task_chat_command(message: str):
    text = message.strip()
    lower = text.lower()

    add_prefixes = [
        "lisää tehtävä:",
        "uusi tehtävä:",
        "lisää tehtävä",
        "uusi tehtävä",
    ]

    for prefix in add_prefixes:
        if lower.startswith(prefix):
            prompt = text[len(prefix):].strip(" :")

            if not prompt:
                return {
                    "handled": True,
                    "reply": "Anna tehtävän sisältö, esimerkiksi: `lisää tehtävä: tiivistä tiedosto uploads/testi.md`."
                }

            result = add_task(
                PROJECT_PATH,
                prompt=prompt,
                title=prompt[:80],
                tags=["chat"],
                priority=3
            )

            task = result.get("task") or {}

            return {
                "handled": True,
                "reply": f"Lisäsin tehtävän jonoon. ID: `{task.get('id')}`\n\n{task.get('title')}"
            }

    if lower in {"näytä tehtävät", "listaa tehtävät", "tehtäväjono", "näytä tehtäväjono"}:
        result = list_tasks(PROJECT_PATH, status=None, limit=50)
        return {
            "handled": True,
            "reply": _format_task_list_for_chat(result)
        }

    if lower in {"näytä avoimet tehtävät", "listaa avoimet tehtävät"}:
        result = list_tasks(PROJECT_PATH, status="queued", limit=50)
        return {
            "handled": True,
            "reply": _format_task_list_for_chat(result)
        }

    if lower in {"suorita seuraava tehtävä", "aja seuraava tehtävä", "run next task"}:
        result = run_next_task(PROJECT_PATH, _execute_task_prompt)
        task = result.get("task")

        if not task:
            return {
                "handled": True,
                "reply": result.get("message", "Jonossa ei ole suoritettavia tehtäviä.")
            }

        task_result = result.get("result") or {}
        reply = task_result.get("reply") or result.get("message")

        return {
            "handled": True,
            "reply": f"Suoritin tehtävän `{task.get('id')}`: {task.get('title')}\n\n{reply}"
        }

    if lower in {"näytä tehtäväloki", "tehtäväloki", "task history"}:
        result = read_task_history(PROJECT_PATH, limit=30)
        items = result.get("items") or []

        if not items:
            return {
                "handled": True,
                "reply": "Tehtäväloki on vielä tyhjä."
            }

        lines = ["Viimeisimmät tehtävätapahtumat:", ""]

        for item in items[-15:]:
            lines.append(f"- {item.get('time')} — {item.get('event')} — {item.get('task_id', '')}")

        return {
            "handled": True,
            "reply": "\n".join(lines)
        }

    return {
        "handled": False
    }






@app.get("/learning/review/status")
def learning_review_status():
    return get_learning_review_status(PROJECT_PATH)


@app.post("/learning/review/file")
def learning_review_file(request: LearningReviewFileRequest):
    if not request.relative_path.strip():
        raise HTTPException(status_code=400, detail="relative_path ei saa olla tyhjä.")

    return create_learning_review_for_file(
        PROJECT_PATH,
        request.relative_path,
        force=bool(request.force)
    )


@app.post("/learning/review/recent")
def learning_review_recent(request: LearningReviewRecentRequest):
    result = create_reviews_for_recent_learning(
        PROJECT_PATH,
        max_files=request.max_files or 10,
        force=bool(request.force)
    )

    try:
        log_tool_event(
            PROJECT_PATH,
            tool="learning_review",
            action="recent",
            request=request.model_dump(),
            result={
                "ok": result.get("ok"),
                "created_count": result.get("created_count"),
                "skipped_count": result.get("skipped_count"),
                "failed_count": result.get("failed_count"),
            },
        )
    except Exception:
        pass

    return result


@app.post("/learning/review/log")
def learning_review_log(request: LearningReviewLogRequest):
    return read_learning_reviews(PROJECT_PATH, limit=request.limit or 50)


@app.get("/learning/status")
def learning_status():
    return get_learning_status(PROJECT_PATH)


@app.post("/learning/scan")
def learning_scan(request: LearningScanRequest):
    return scan_uploads_for_learning(
        PROJECT_PATH,
        include_already_ingested=bool(request.include_already_ingested),
        limit=request.limit or 100
    )


@app.post("/learning/run")
def learning_run(request: LearningRunRequest):
    result = run_autonomous_learning_loop(
        PROJECT_PATH,
        max_files=request.max_files or 10,
        add_to_memory=bool(request.add_to_memory),
        add_to_semantic=bool(request.add_to_semantic)
    )

    try:
        log_tool_event(
            PROJECT_PATH,
            tool="autonomous_learning_loop",
            action="run",
            request=request.model_dump(),
            result={
                "ok": result.get("ok"),
                "learned_count": result.get("learned_count"),
                "failed_count": result.get("failed_count"),
            },
        )
    except Exception:
        pass

    return result


@app.post("/learning/log")
def learning_log(request: LearningLogRequest):
    return read_learning_log(PROJECT_PATH, limit=request.limit or 50)


@app.get("/dev/status")
def dev_status():
    data = read_codebase_map(PROJECT_PATH)

    return {
        "ok": True,
        "message": "Dev Mode on käytettävissä.",
        "map_exists": bool(data.get("ok")),
        "map_path": str(CODEBASE_MAP_PATH),
        "file_count": data.get("file_count"),
        "route_count": data.get("route_count"),
        "function_count": data.get("function_count"),
        "class_count": data.get("class_count"),
    }


@app.post("/dev/map")
def dev_build_map(request: DevMapRequest):
    result = build_codebase_map(
        PROJECT_PATH,
        include_snippets=bool(request.include_snippets)
    )

    try:
        log_tool_event(
            PROJECT_PATH,
            tool="codebase_map",
            action="build",
            request=request.model_dump(),
            result={
                "ok": result.get("ok"),
                "file_count": result.get("file_count"),
                "route_count": result.get("route_count"),
                "function_count": result.get("function_count"),
                "class_count": result.get("class_count"),
            },
        )
    except Exception:
        pass

    return result


@app.get("/dev/map")
def dev_read_map():
    return read_codebase_map(PROJECT_PATH)


@app.post("/dev/find")
def dev_find(request: DevFindRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Hakusana ei saa olla tyhjä.")

    return find_in_codebase_map(
        PROJECT_PATH,
        request.query,
        limit=request.limit or 20
    )


@app.get("/tasks/status")
def tasks_status():
    return get_task_queue_status(PROJECT_PATH)


@app.post("/tasks/add")
def tasks_add(request: TaskAddRequest):
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Tehtävä ei saa olla tyhjä.")

    _audit(category="task", action="add", outcome="attempt", risk_level="low", reason="Käyttäjä lisäsi tehtävän jonoon.", details={"title": request.title, "priority": request.priority}, required=True)
    result = add_task(
        PROJECT_PATH,
        prompt=request.prompt,
        title=request.title,
        tags=request.tags or ["api"],
        priority=request.priority or 3
    )
    _audit(category="task", action="add", outcome="success", risk_level="low", reason="Tehtävä lisättiin jonoon.", target=str((result.get("task") or {}).get("id", "")), details={"title": request.title})
    return result


@app.post("/tasks/list")
def tasks_list(request: TaskListRequest):
    return list_tasks(
        PROJECT_PATH,
        status=request.status,
        limit=request.limit or 50
    )


@app.post("/tasks/run-next")
def tasks_run_next():
    _audit(category="task", action="run_next", outcome="attempt", risk_level="medium", reason="Käyttäjä käynnisti seuraavan tehtävän.", required=True)
    result = run_next_task(PROJECT_PATH, _execute_task_prompt)
    _audit(category="task", action="run_next", outcome="success" if result.get("ok", True) else "failure", risk_level="medium", reason=result.get("message", "Tehtäväajo valmis."), target=str((result.get("task") or {}).get("id", "")))
    return result


@app.post("/tasks/run")
def tasks_run(request: TaskRunRequest):
    if not request.task_id.strip():
        raise HTTPException(status_code=400, detail="task_id ei saa olla tyhjä.")

    _audit(category="task", action="run", outcome="attempt", risk_level="medium", reason="Käyttäjä käynnisti yksittäisen tehtävän.", target=request.task_id, required=True)
    result = run_task_by_id(PROJECT_PATH, request.task_id, _execute_task_prompt)
    _audit(category="task", action="run", outcome="success" if result.get("ok", True) else "failure", risk_level="medium", reason=result.get("message", "Tehtäväajo valmis."), target=request.task_id)
    return result


@app.post("/tasks/cancel")
def tasks_cancel(request: TaskCancelRequest):
    if not request.task_id.strip():
        raise HTTPException(status_code=400, detail="task_id ei saa olla tyhjä.")

    _audit(category="task", action="cancel", outcome="attempt", risk_level="medium", reason="Käyttäjä pyysi tehtävän perumista.", target=request.task_id, required=True)
    result = cancel_task(PROJECT_PATH, request.task_id)
    _audit(category="task", action="cancel", outcome="success" if result.get("ok", True) else "failure", risk_level="medium", reason=result.get("message", "Tehtävä peruttu."), target=request.task_id)
    return result


@app.post("/tasks/history")
def tasks_history(request: TaskHistoryRequest):
    return read_task_history(PROJECT_PATH, limit=request.limit or 50)



def _format_learning_scan_for_chat(result):
    candidates = result.get("candidates") or []

    if not candidates:
        return f"Uusia opittavia tiedostoja ei löytynyt. Ohitettuja: {result.get('skipped_count', 0)}"

    lines = [f"Löysin {len(candidates)} uutta opittavaa tiedostoa:", ""]

    for item in candidates[:20]:
        lines.append(f"- `{item.get('relative_path')}` ({item.get('size_bytes')} tavua)")

    if len(candidates) > 20:
        lines.append("")
        lines.append(f"...ja {len(candidates) - 20} muuta.")

    return "\n".join(lines)


def _format_learning_run_for_chat(result):
    learned = result.get("learned") or []
    failed = result.get("failed") or []

    if not learned and not failed:
        return "Oppimiskierros suoritettu, mutta uusia tiedostoja ei ollut."

    lines = [
        "Oppimiskierros valmis.",
        "",
        f"Opittu: {len(learned)}",
        f"Epäonnistui: {len(failed)}",
        "",
    ]

    for item in learned[:15]:
        lines.append(f"✅ `{item.get('relative_path')}`")

    for item in failed[:10]:
        lines.append(f"⚠️ `{item.get('relative_path')}` — {item.get('error')}")

    return "\n".join(lines)


def _handle_learning_chat_command(message: str):
    lower = message.strip().lower()

    if lower in {
        "oppimistila",
        "näytä oppimistila",
        "autonomous learning status",
        "learning status",
    }:
        status = get_learning_status(PROJECT_PATH)
        return {
            "handled": True,
            "reply": (
                "Autonomous Learning Loop on käytössä.\n\n"
                f"Odottavia tiedostoja: {status.get('pending_files')}\n"
                f"Oppimistapahtumia: {status.get('learning_events')}\n"
                f"Uploads: `{status.get('uploads_path')}`"
            )
        }

    if lower in {
        "skannaa uudet tiedostot",
        "etsi uudet tiedostot",
        "skannaa opittavat tiedostot",
        "learning scan",
    }:
        result = scan_uploads_for_learning(
            PROJECT_PATH,
            include_already_ingested=False,
            limit=100
        )
        return {
            "handled": True,
            "reply": _format_learning_scan_for_chat(result)
        }

    if lower in {
        "opi uudet tiedostot",
        "oppimiskierros",
        "suorita oppimiskierros",
        "autonomous learning loop",
        "learning loop",
    }:
        result = run_autonomous_learning_loop(
            PROJECT_PATH,
            max_files=10,
            add_to_memory=True,
            add_to_semantic=True
        )
        return {
            "handled": True,
            "reply": _format_learning_run_for_chat(result)
        }

    if lower in {
        "näytä oppimisloki",
        "oppimisloki",
        "learning log",
    }:
        result = read_learning_log(PROJECT_PATH, limit=30)
        items = result.get("items") or []

        if not items:
            return {
                "handled": True,
                "reply": "Oppimisloki on vielä tyhjä."
            }

        lines = ["Viimeisimmät oppimistapahtumat:", ""]

        for item in items[-15:]:
            lines.append(f"- {item.get('time')} — {item.get('event')} — {item.get('relative_path', '')}")

        return {
            "handled": True,
            "reply": "\n".join(lines)
        }

    return {
        "handled": False
    }




def _format_learning_review_result_for_chat(result):
    if result.get("already_exists"):
        review = result.get("review") or {}
        return (
            "Tästä tiedostoversiosta oli jo oppimiskatsaus.\n\n"
            f"Review ID: `{review.get('review_id')}`\n"
            f"Lähde: `{review.get('relative_path')}`"
        )

    review = result.get("review") or {}

    lines = [
        "Oppimiskatsaus luotu.",
        "",
        f"Review ID: `{review.get('review_id')}`",
        f"Lähde: `{review.get('relative_path')}`",
        "",
        "Tärkeät käsitteet:",
    ]

    for term in (review.get("terms") or [])[:12]:
        lines.append(f"- {term}")

    future_tasks = review.get("future_tasks") or []

    if future_tasks:
        lines.extend(["", "Mahdolliset jatkotehtävät:"])
        for task in future_tasks[:8]:
            lines.append(f"- {task}")

    return "\n".join(lines)


def _format_recent_learning_reviews_for_chat(result):
    created = result.get("created") or []
    skipped = result.get("skipped") or []
    failed = result.get("failed") or []

    lines = [
        "Oppimiskatsausajo valmis.",
        "",
        f"Luotu: {len(created)}",
        f"Ohitettu: {len(skipped)}",
        f"Epäonnistui: {len(failed)}",
        "",
    ]

    for item in created[:15]:
        lines.append(f"✅ `{item.get('relative_path')}` — {item.get('title')}")

    for item in skipped[:10]:
        lines.append(f"⏭️ `{item.get('relative_path')}` — {item.get('reason')}")

    for item in failed[:10]:
        lines.append(f"⚠️ `{item.get('relative_path')}` — {item.get('error')}")

    return "\n".join(lines).strip()


def _handle_learning_review_chat_command(message: str):
    text = message.strip()
    lower = text.lower()

    prefixes = [
        "tee oppimiskatsaus tiedostosta",
        "luo oppimiskatsaus tiedostosta",
        "learning review file",
    ]

    for prefix in prefixes:
        if lower.startswith(prefix):
            relative_path = text[len(prefix):].strip(" :")

            if not relative_path:
                return {
                    "handled": True,
                    "reply": "Anna tiedostopolku, esimerkiksi: `tee oppimiskatsaus tiedostosta uploads/ai_agent_terms_atlas.md`."
                }

            try:
                result = create_learning_review_for_file(
                    PROJECT_PATH,
                    relative_path,
                    force=False
                )
                reply = _format_learning_review_result_for_chat(result)
            except Exception as error:
                reply = f"Oppimiskatsauksen luonti epäonnistui: {error}"

            return {
                "handled": True,
                "reply": reply
            }

    if lower in {
        "tee oppimiskatsaus",
        "tee oppimiskatsaukset",
        "tee oppimiskatsaukset viimeksi opituista",
        "learning review",
        "learning reviews",
    }:
        result = create_reviews_for_recent_learning(
            PROJECT_PATH,
            max_files=10,
            force=False
        )
        return {
            "handled": True,
            "reply": _format_recent_learning_reviews_for_chat(result)
        }

    if lower in {
        "näytä oppimiskatsaukset",
        "oppimiskatsaukset",
        "learning review log",
        "learning reviews log",
    }:
        result = read_learning_reviews(PROJECT_PATH, limit=20)
        items = result.get("items") or []

        if not items:
            return {
                "handled": True,
                "reply": "Oppimiskatsauksia ei ole vielä."
            }

        lines = ["Viimeisimmät oppimiskatsaukset:", ""]

        for item in items[-15:]:
            lines.append(f"- `{item.get('review_id')}` — {item.get('title')} — `{item.get('relative_path')}`")

        return {
            "handled": True,
            "reply": "\n".join(lines)
        }

    if lower in {
        "oppimiskatsaus tila",
        "näytä oppimiskatsaus tila",
        "learning review status",
    }:
        status = get_learning_review_status(PROJECT_PATH)
        return {
            "handled": True,
            "reply": (
                "Learning Review v1 on käytössä.\n\n"
                f"Katsauksia: {status.get('reviews_count')}\n"
                f"Markdown: `{status.get('reviews_md')}`\n"
                f"Log: `{status.get('reviews_log')}`"
            )
        }

    return {
        "handled": False
    }




def _extract_rag_query_from_chat(message: str):
    text = message.strip()
    lower = text.lower()

    prefixes = [
        "hae muistista",
        "etsi muistista",
        "hae ragista",
        "rag haku",
        "rag search",
    ]

    for prefix in prefixes:
        if lower.startswith(prefix):
            query = text[len(prefix):].strip(" :")

            if query:
                return query

    return None


def _handle_rag_chat_command(message: str):
    lower = message.strip().lower()

    if lower in {"rag tila", "näytä rag tila", "rag status", "rag engine tila"}:
        status = rag_status(PROJECT_PATH)

        return {
            "handled": True,
            "reply": (
                "RAG Engine v1 on käytössä.\n\n"
                f"Chat-logi oletuksena: {status.get('chat_log_default')}\n"
                f"Oletustuloksia: {status.get('default_n_results')}\n"
                f"Semanttinen muisti OK: {(status.get('semantic_memory') or {}).get('ok')}"
            )
        }

    query = _extract_rag_query_from_chat(message)

    if not query:
        return {"handled": False}

    result = rag_search(
        PROJECT_PATH,
        query,
        n_results=8,
        include_chat_log=False,
        min_score=35.0,
    )

    return {
        "handled": True,
        "reply": format_rag_search_reply(result)
    }


def _build_web_search_chat_result(message: str, *, reason: str = "automatic_factual_search") -> Dict[str, object]:
    from app import web_search as web_search_module

    query = web_search_module.extract_web_query(message)
    search_result = web_search_module.web_search(PROJECT_PATH, query, max_results=6)
    return {
        "handled": True,
        "tool": "web_search",
        "reason": reason,
        "result": search_result,
        "reply": web_search_module.format_web_search_reply(search_result),
        "actions": ([
            {"label": "Review sources", "message": "Review sources"},
            {"label": "Deepen search", "message": f"web search {message} 2025 2026 report"},
        ] if search_result.get("ok") and search_result.get("results") else []),
    }


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    result = handle_chat_message(
        request.message,
        ChatPipelineDependencies(
            project_path=PROJECT_PATH,
            sade_memory_path=SADE_MEMORY_PATH,
            memory_entry_class=MemoryEntry,
            append_chat_log=append_chat_log,
            load_config=load_config,
            append_markdown_entry=append_markdown_entry,
            extract_memory_command=extract_memory_command,
            handle_learning_review_chat_command=_handle_learning_review_chat_command,
            handle_learning_chat_command=_handle_learning_chat_command,
            handle_task_chat_command=_handle_task_chat_command,
            handle_rag_chat_command=_handle_rag_chat_command,
            route_tool_request=route_tool_request,
            build_web_search_chat_result=_build_web_search_chat_result,
            get_tool_policy=get_tool_policy,
            log_tool_event=log_tool_event,
            audit=_audit,
            audit_risk=_audit_risk,
            build_sade_prompt=build_sade_prompt,
            ask_ollama=ask_ollama,
            get_chat_context=get_chat_context,
        ),
    )
    if isinstance(result, JSONResponse):
        return result
    return ChatResponse(**result)


@app.get("/login", response_class=HTMLResponse)
def login_page():
    if not LOGIN_TEMPLATE_PATH.exists():
        raise HTTPException(status_code=500, detail="Kirjautumissivu puuttuu.")
    return HTMLResponse(LOGIN_TEMPLATE_PATH.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})


@app.get("/auth/status")
def auth_status_endpoint(request: Request):
    token = request.cookies.get(SESSION_COOKIE, "")
    session = get_session(PROJECT_PATH, token)
    return {
        "ok": True,
        "configured": auth_configured(PROJECT_PATH),
        "authenticated": session is not None,
        "username": session.get("username") if session else None,
        "csrf_token": session.get("csrf") if session else None,
    }


@app.post("/auth/login")
def auth_login(request: Request, credentials: LoginRequest):
    if not auth_configured(PROJECT_PATH):
        raise HTTPException(status_code=503, detail="Kirjautumiskäyttäjää ei ole vielä luotu paikallisella komentorivillä.")
    client_ip = request.client.host if request.client else "unknown"
    verification = verify_credentials(PROJECT_PATH, credentials.username, credentials.password, client_ip)
    if not verification.get("ok"):
        import hashlib as _auth_hashlib
        _audit(category="authentication", action="login", outcome="denied", risk_level="medium", reason="Kirjautuminen epäonnistui.", details={"username": credentials.username, "client_ip_hash": _auth_hashlib.sha256(client_ip.encode()).hexdigest()[:16], "rate_limited": verification.get("rate_limited", False)})
        if verification.get("rate_limited"):
            retry_after = int(verification.get("retry_after", 900))
            return JSONResponse({"ok": False, "message": "Liian monta yritystä. Odota ennen uutta yritystä.", "retry_after": retry_after}, status_code=429, headers={"Retry-After": str(retry_after)})
        raise HTTPException(status_code=401, detail="Virheellinen käyttäjänimi tai salasana.")
    session = create_session(PROJECT_PATH, credentials.username, client_ip, request.headers.get("user-agent", ""))
    _audit(category="authentication", action="login", outcome="success", risk_level="low", reason="Käyttäjä kirjautui Säde v1:een.", details={"username": credentials.username})
    response = JSONResponse({"ok": True, "username": credentials.username, "csrf_token": session["csrf"]})
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    secure = request.url.scheme == "https" or forwarded_proto == "https"
    response.set_cookie(SESSION_COOKIE, session["token"], max_age=SESSION_TTL_SECONDS, httponly=True, secure=secure, samesite="strict", path="/")
    return response


@app.post("/auth/logout")
def auth_logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE, "")
    session = getattr(request.state, "auth_session", {})
    revoke_session(PROJECT_PATH, token)
    _audit(category="authentication", action="logout", outcome="success", risk_level="low", reason="Käyttäjä kirjautui ulos.", details={"username": session.get("username", "unknown")})
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="strict")
    return response


@app.get("/ui", response_class=HTMLResponse)
def ui(request: Request):
    ensure_paths()

    if not UI_TEMPLATE_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail=f"UI-templatea ei löytynyt: {UI_TEMPLATE_PATH}"
        )

    session = getattr(request.state, "auth_session", {})
    content = UI_TEMPLATE_PATH.read_text(encoding="utf-8").replace("__SADE_CSRF_TOKEN__", str(session.get("csrf", "")))
    return HTMLResponse(
        content=content,
        status_code=200,
        headers={"Cache-Control": "no-store, max-age=0"}
    )

    return HTMLResponse(
        content=UI_TEMPLATE_PATH.read_text(encoding="utf-8"),
        status_code=200
    )


# DIRECT_DEV_COMMAND_MIDDLEWARE_START
try:
    import json as _direct_json
    import re as _direct_re
    from pathlib import Path as _DirectPath
    from fastapi import Request as _DirectRequest
    from fastapi.responses import JSONResponse as _DirectJSONResponse
    from app.codebase_map import build_codebase_map as _direct_build_map
    from app.codebase_map import read_codebase_map as _direct_read_map
    from app.codebase_map import find_in_codebase_map as _direct_find_map

    def _direct_norm(text: str) -> str:
        text = str(text or "").strip().lower()
        text = text.replace("ä", "a").replace("ö", "o")
        return _direct_re.sub(r"\s+", " ", text)

    def _direct_app_path():
        path = _DirectPath(globals().get("PROJECT_PATH") or globals().get("BASE_PATH") or ".").resolve()

        if path.name.lower() == "app":
            return path

        candidate = path / "app"

        if candidate.exists() and candidate.is_dir():
            return candidate

        return path

    def _direct_payload(text: str):
        return {
            "ok": True,
            "source": "dev_mode_direct",
            "response": text,
            "reply": text,
            "answer": text,
            "message": text,
            "text": text,
        }

    def _direct_extract_message(data):
        if isinstance(data, dict):
            for key in ["message", "user_message", "text", "prompt", "query", "content"]:
                value = data.get(key)

                if isinstance(value, str) and value.strip():
                    return value

            messages = data.get("messages")

            if isinstance(messages, list) and messages:
                last = messages[-1]

                if isinstance(last, dict):
                    value = last.get("content")

                    if isinstance(value, str) and value.strip():
                        return value

        return None

    def _direct_format_map(result):
        return "\n".join([
            "Koodikartta luotu Dev Modella. ✅",
            "",
            f"Tiedostot: {result.get('file_count', 0)}",
            f"Reitit: {result.get('route_count', 0)}",
            f"Funktiot: {result.get('function_count', 0)}",
            f"Luokat: {result.get('class_count', 0)}",
            f"Polku: `{result.get('map_path', '')}`",
        ])

    def _direct_format_status(result):
        if not result.get("ok"):
            return result.get("message", "Koodikarttaa ei löytynyt.")

        return "\n".join([
            "Koodikartta löytyy. ✅",
            "",
            f"Tiedostot: {result.get('file_count', 0)}",
            f"Reitit: {result.get('route_count', 0)}",
            f"Funktiot: {result.get('function_count', 0)}",
            f"Luokat: {result.get('class_count', 0)}",
            f"Polku: `{result.get('map_path', '')}`",
        ])

    def _direct_handle_dev_command(message: str):
        msg = _direct_norm(message)
        app_path = _direct_app_path()

        map_commands = {
            "tee koodikartta",
            "luo koodikartta",
            "paivita koodikartta",
            "dev map",
            "codebase map",
            "koodikartta",
        }

        status_commands = {
            "nayta koodikartta",
            "lue koodikartta",
            "koodikartan tila",
            "dev status",
            "dev tila",
        }

        if msg in map_commands:
            result = _direct_build_map(app_path, include_snippets=False)
            return _direct_format_map(result)

        if msg in status_commands:
            result = _direct_read_map(app_path)
            return _direct_format_status(result)

        prefixes = [
            "etsi koodista ",
            "hae koodista ",
            "etsi koodikartasta ",
            "hae koodikartasta ",
            "dev find ",
        ]

        for prefix in prefixes:
            if msg.startswith(prefix):
                query = msg[len(prefix):].strip()

                if not query:
                    return "Anna hakusana, esim. `etsi koodista rag_search`."

                result = _direct_find_map(app_path, query, limit=10)

                if not result.get("ok"):
                    return result.get("message", "Koodikarttahaku epäonnistui.")

                items = result.get("results") or []

                if not items:
                    return f"En löytänyt koodikartasta osumia haulle `{query}`."

                lines = [f"Löysin koodikartasta {len(items)} osumaa haulle `{query}`:", ""]

                for i, item in enumerate(items[:10], 1):
                    path = item.get("path") or item.get("file") or "tuntematon"
                    lines.append(f"{i}. `{path}`")

                    summary = item.get("summary") or item.get("matched") or item.get("matches")

                    if summary:
                        lines.append(str(summary)[:500])

                    lines.append("")

                return "\n".join(lines).strip()

        return None

    async def _direct_rebuild_request(request, body: bytes):
        async def receive():
            return {
                "type": "http.request",
                "body": body,
                "more_body": False,
            }

        return _DirectRequest(request.scope, receive)

    @app.middleware("http")
    async def _direct_dev_command_middleware(request: _DirectRequest, call_next):
        method = str(request.method or "").upper()
        content_type = str(request.headers.get("content-type", "")).lower()

        if method == "POST" and "application/json" in content_type:
            body = await request.body()

            try:
                data = _direct_json.loads(body.decode("utf-8")) if body else {}
            except Exception:
                data = {}

            message = _direct_extract_message(data)

            if message:
                try:
                    result = _direct_handle_dev_command(message)

                    if result is not None:
                        return _DirectJSONResponse(_direct_payload(result))

                except Exception as error:
                    text = f"Dev Mode -komento tunnistettiin, mutta suoritus epäonnistui: {error}"
                    return _DirectJSONResponse(_direct_payload(text), status_code=500)

            request = await _direct_rebuild_request(request, body)

        return await call_next(request)

except Exception as error:
    DIRECT_DEV_COMMAND_MIDDLEWARE_ERROR = str(error)
# DIRECT_DEV_COMMAND_MIDDLEWARE_END

# BEHAVIOR_LAYER_V1_START
try:
    from typing import Dict as _BehaviorDict, Any as _BehaviorAny
    from app.behavior_layer import behavior_status as _behavior_status
    from app.behavior_layer import analyze_behavior as _behavior_analyze
    from app.behavior_layer import format_behavior_summary as _behavior_summary

    @app.get("/behavior/status")
    def behavior_status_endpoint():
        return _behavior_status()

    @app.post("/behavior/analyze")
    def behavior_analyze_endpoint(payload: _BehaviorDict[str, _BehaviorAny]):
        text = (
            payload.get("text")
            or payload.get("message")
            or payload.get("query")
            or payload.get("prompt")
            or ""
        )

        result = _behavior_analyze(str(text), context=payload.get("context"))
        result["summary"] = _behavior_summary(result)
        return result

except Exception as _behavior_layer_error:
    BEHAVIOR_LAYER_V1_ERROR = str(_behavior_layer_error)
# BEHAVIOR_LAYER_V1_END


# AUTHENTICATION_MIDDLEWARE_V1_START
_AUTH_PUBLIC_PATHS = {"/login", "/auth/login", "/auth/status"}
_AUTH_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def authentication_middleware(request: Request, call_next):
    path = request.url.path.rstrip("/") or "/"
    is_public = path in _AUTH_PUBLIC_PATHS
    session = None

    if not is_public:
        token = request.cookies.get(SESSION_COOKIE, "")
        session = get_session(PROJECT_PATH, token)
        if session is None:
            accepts_html = "text/html" in request.headers.get("accept", "")
            if request.method == "GET" and accepts_html:
                return RedirectResponse(url="/login", status_code=303)
            status_code = 503 if not auth_configured(PROJECT_PATH) else 401
            return JSONResponse(
                {
                    "ok": False,
                    "error": "auth_not_configured" if status_code == 503 else "authentication_required",
                    "message": "Luo kirjautumiskäyttäjä paikallisella komentorivillä." if status_code == 503 else "Kirjautuminen vaaditaan.",
                },
                status_code=status_code,
            )

        request.state.auth_session = session
        if request.method.upper() in _AUTH_UNSAFE_METHODS:
            supplied_csrf = request.headers.get("x-csrf-token", "")
            if not hmac.compare_digest(str(supplied_csrf), str(session.get("csrf", ""))):
                return JSONResponse({"ok": False, "error": "csrf_failed", "message": "Pyynnön CSRF-tunniste puuttuu tai on virheellinen."}, status_code=403)

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    if request.url.scheme == "https" or forwarded_proto == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    if path.startswith("/auth") or path in {"/login", "/ui"}:
        response.headers["Cache-Control"] = "no-store"
    return response
# AUTHENTICATION_MIDDLEWARE_V1_END
