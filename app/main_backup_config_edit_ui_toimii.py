from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from datetime import datetime
from pathlib import Path
from typing import Optional, List
import json
import urllib.request
import urllib.error


app = FastAPI(title="Säde v1")

BASE_PATH = Path("C:/Sade")
PROJECT_PATH = Path("C:/Sade/Sade-v1")
CONFIG_PATH = PROJECT_PATH / "config.json"

MEMORY_PATH = BASE_PATH / "memory"
SADE_MEMORY_PATH = MEMORY_PATH / "sade_memory.md"
LOG_PATH = MEMORY_PATH / "memory_log.jsonl"
CHAT_LOG_PATH = MEMORY_PATH / "chat_log.md"


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

class ConfigUpdateRequest(BaseModel):
    ollama_model: Optional[str] = None
    temperature: Optional[float] = None
    num_ctx: Optional[int] = None
    memory_context_chars: Optional[int] = None
    chat_context_chars: Optional[int] = None

def load_config():
    default_config = {
        "ollama_url": "http://127.0.0.1:11434/api/generate",
        "ollama_model": "gpt-oss:20b",
        "temperature": 0.7,
        "num_ctx": 8192,
        "memory_context_chars": 6000,
        "chat_context_chars": 4000
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

    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return config


def ensure_paths():
    BASE_PATH.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.mkdir(parents=True, exist_ok=True)

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

    return {
        "ok": True,
        "message": "Muisto tallennettu.",
        "title": title,
        "path": str(path),
        "time": timestamp
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
        "lisää säde-muistian että",
        "lisää säde-muistian, että",
        "tallenna säde-muistian että",
        "tallenna säde-muistian, että",
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
    memory_context = get_memory_context()
    chat_context = get_chat_context()

    return f"""
Olet Säde v1, paikallinen tekoälyavustaja Janin koneella.

Tyyli:
- Vastaa suomeksi.
- Ole lämmin, selkeä, rauhallinen ja käytännöllinen.
- Vastaa suoraan siihen, mitä käyttäjä kysyy.
- Älä väitä tietäväsi asioita, joita ei ole annettu sinulle.
- Käytä Säde-muistia pitkäaikaisena muistina.
- Käytä keskustelulokia lyhytaikaisena muistina.
- Jos et tiedä, sano rehellisesti ettet tiedä.

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

    return f"""
Olet Säde v1, paikallinen tekoälyavustaja Janin koneella.

Tyyli:
- Vastaa suomeksi.
- Ole lämmin, selkeä, rauhallinen ja käytännöllinen.
- Vastaa suoraan siihen, mitä käyttäjä kysyy.
- Älä väitä tietäväsi asioita, joita ei ole annettu sinulle.
- Käytä Säde-muistia pitkäaikaisena muistina.
- Käytä keskustelulokia lyhytaikaisena muistina.
- Jos et tiedä, sano rehellisesti ettet tiedä.

Pitkäaikainen muisti, Säde-muisti:
{memory_context}

Viimeaikainen keskusteluloki:
{chat_context}

Käyttäjän uusi viesti:
{user_message}

Säteen vastaus:
""".strip()


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
            "chat_log": str(CHAT_LOG_PATH)
        },
        "endpoints": [
            "/ui",
            "/chat",
	    "/config",
	    "POST /config",
            "/ollama/status",
            "/health",
            "/memory/sade_memory",
	    "/memory/visible-chat",
            "/memory/chatlog",
	    "/memory/search",
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
        "chat_context_chars": config.get("chat_context_chars", 4000)
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


@app.get("/memory/sade_memory")
def get_sade_memory():
    ensure_paths()
    return read_markdown_file(SADE_MEMORY_PATH)


@app.get("/memory/chatlog")
def get_chat_log():
    ensure_paths()
    return read_markdown_file(CHAT_LOG_PATH)


@app.post("/memory/sade_memory")
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
        tags=["chat", "näkyvä keskustelu", "säde-muisti"]
    )

    return append_markdown_entry(SADE_MEMORY_PATH, entry)


@app.post("/memory/search")
def search_memory(request: MemorySearchRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Hakusana ei saa olla tyhjä.")

    return search_sade_memory(request.query)


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
            f"Tallensin tämän Säde-muistian:\n\n"
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
    return """
<!DOCTYPE html>
<html lang="fi">
<head>
    <meta charset="UTF-8">
    <title>Säde v1</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #111827;
            color: #f9fafb;
            margin: 0;
            padding: 40px;
        }

        .container {
            max-width: 1000px;
            margin: auto;
            background: #1f2937;
            padding: 30px;
            border-radius: 18px;
            box-shadow: 0 0 30px rgba(0,0,0,0.35);
        }

        h1 {
            color: #fbbf24;
            margin-top: 0;
        }

        h2 {
            margin-top: 35px;
            color: #fde68a;
        }

        input, textarea {
            width: 100%;
            box-sizing: border-box;
            margin-top: 8px;
            margin-bottom: 18px;
            padding: 12px;
            border-radius: 10px;
            border: none;
            font-size: 15px;
        }

        textarea {
            min-height: 130px;
            resize: vertical;
        }

        button {
            background: #fbbf24;
            color: #111827;
            padding: 12px 20px;
            border: none;
            border-radius: 12px;
            font-weight: bold;
            cursor: pointer;
            margin-right: 10px;
            margin-bottom: 10px;
        }

        button:hover {
            background: #f59e0b;
        }

        pre {
            white-space: pre-wrap;
            background: #030712;
            padding: 20px;
            border-radius: 12px;
            max-height: 500px;
            overflow: auto;
        }

        .status {
            margin-top: 20px;
            color: #93c5fd;
        }

        label {
            font-weight: bold;
            color: #e5e7eb;
        }

        .chat-box {
            background: #030712;
            padding: 20px;
            border-radius: 12px;
            min-height: 160px;
            max-height: 500px;
            overflow: auto;
            white-space: pre-wrap;
            margin-bottom: 18px;
        }

        .user {
            color: #93c5fd;
            margin-bottom: 12px;
        }

        .sade {
            color: #fbbf24;
            margin-bottom: 20px;
        }

        .small {
            color: #9ca3af;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Säde v1</h1>
        <p>Paikallinen muisti ja keskustelu ovat käytössä.</p>
        <p class="small" id="configInfo">Ladataan asetuksia...</p>
        <p class="small" id="ollamaStatus">Ollama: ei tarkistettu vielä</p>
        <button onclick="checkOllamaStatus()">Tarkista Ollama</button>

        <h2>Asetukset</h2>

        <label>Malli</label>
	<input id="configModel" placeholder="esim. gpt-oss:20b">

        <label>Lämpötila</label>
	<input id="configTemperature" type="number" step="0.1" min="0" max="2">

	<label>Konteksti / num_ctx</label>
	<input id="configNumCtx" type="number" min="512" step="512">

	<label>Säde-muistin muistimerkit</label>
	<input id="configMemoryChars" type="number" min="500" step="500">

	<label>Keskustelulokin muistimerkit</label>
	<input id="configChatChars" type="number" min="500" step="500">

	<button onclick="saveConfigSettings()">Tallenna asetukset</button>

        <h2>Keskustele Säteen kanssa</h2>

        <div id="chatBox" class="chat-box"></div>

        <label>Viesti</label>
        <textarea id="chatMessage" placeholder="Kirjoita viesti Säde v1:lle..."></textarea>

       	<button onclick="sendChat()">Lähetä</button>
	<button onclick="clearVisibleChat()">Tyhjennä näkyvä chat</button>
	<button onclick="saveVisibleChatToMemory()">Tallenna nykyinen keskustelu Säde-muistian</button>

        <h2>Tallenna muisto Säde-muistian</h2>

        <label>Otsikko</label>
        <input id="title" placeholder="Esim. Ensimmäinen keskustelu">

        <label>Tagit pilkulla erotettuna</label>
        <input id="tags" placeholder="esim. sade, muisto, kehitys">

        <label>Teksti</label>
        <textarea id="text" placeholder="Kirjoita muisto tähän..."></textarea>

        <button onclick="saveMemory()">Tallenna muisto</button>
        <button onclick="loadMemory()">Näytä Säde-muisti</button>
        <button onclick="loadChatLog()">Näytä keskusteluloki</button>

        <div class="status" id="status"></div>

        <h2>Hae Säde-muistista</h2>

	<label>Hakusana</label>
	<input id="memorySearchQuery" placeholder="Esim. Jani, Säde v1, keskusteluloki">

	<button onclick="searchMemory()">Hae Säde-muistista</button>

	<h2>Hakutulokset</h2>
	<pre id="memorySearchResults"></pre>

	<h2>Säde-muisti</h2>
        <pre id="memory"></pre>

        <h2>Keskusteluloki</h2>
        <pre id="chatLog"></pre>
    </div>

    <script>
    function addChatLine(role, text) {
        const chatBox = document.getElementById("chatBox");
        const div = document.createElement("div");
        div.className = role === "Sinä" ? "user" : "sade";
        div.innerText = role + ":\\n" + text;
        chatBox.appendChild(div);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function clearVisibleChat() {
        const chatBox = document.getElementById("chatBox");
        chatBox.innerHTML = "";
        document.getElementById("status").innerText = "Näkyvä chat tyhjennetty. Keskusteluloki säilyy tallessa.";
    }

async function saveVisibleChatToMemory() {
    const chatBox = document.getElementById("chatBox");
    const content = chatBox.innerText.trim();

    if (!content) {
        document.getElementById("status").innerText = "Näkyvä chat on tyhjä, ei tallennettavaa.";
        return;
    }

    try {
        const response = await fetch("/memory/visible-chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                content: content
            })
        });

        const data = await response.json();

        if (response.ok) {
            document.getElementById("status").innerText = "Nykyinen keskustelu tallennettu Säde-muistian.";
            loadMemory();
        } else {
            document.getElementById("status").innerText = "Virhe: " + JSON.stringify(data);
        }

    } catch (error) {
        document.getElementById("status").innerText = "Yhteysvirhe: " + error;
    }
}

    
async function searchMemory() {
    const queryBox = document.getElementById("memorySearchQuery");
    const resultsBox = document.getElementById("memorySearchResults");
    const query = queryBox.value.trim();

    if (!query) {
        document.getElementById("status").innerText = "Kirjoita hakusana ensin.";
        return;
    }

    document.getElementById("status").innerText = "Haetaan Säde-muistista...";

    try {
        const response = await fetch("/memory/search", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                query: query
            })
        });

        const data = await response.json();

        if (response.ok) {
            if (data.count === 0) {
                resultsBox.innerText = "Ei osumia haulla: " + query;
                document.getElementById("status").innerText = "Ei osumia.";
                return;
            }

            let output = "";
            output += "Hakusana: " + data.query + "\\n";
            output += "Osumia: " + data.count + "\\n\\n";

            data.results.forEach((item, index) => {
                output += "---\\n";
                output += "Tulos " + (index + 1) + " / rivi " + item.line + "\\n\\n";
                output += item.snippet + "\\n\\n";
            });

            resultsBox.innerText = output;
            resultsBox.scrollTop = 0;

            document.getElementById("status").innerText = "Haku valmis.";
        } else {
            resultsBox.innerText = "Virhe: " + JSON.stringify(data);
            document.getElementById("status").innerText = "Haku epäonnistui.";
        }

    } catch (error) {
        resultsBox.innerText = "Yhteysvirhe: " + error;
        document.getElementById("status").innerText = "Yhteysvirhe haussa.";
    }
}
async function sendChat() {
        const messageBox = document.getElementById("chatMessage");
        const message = messageBox.value.trim();

        if (!message) {
            document.getElementById("status").innerText = "Kirjoita ensin viesti.";
            return;
        }

        addChatLine("Sinä", message);
        messageBox.value = "";
        document.getElementById("status").innerText = "Säde ajattelee...";

        try {
            const response = await fetch("/chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    message: message
                })
            });

            const data = await response.json();

            if (response.ok) {
                addChatLine("Säde", data.reply);
                document.getElementById("status").innerText = "Vastaus valmis.";
                loadMemory();
                loadChatLog();
            } else {
                document.getElementById("status").innerText = "Virhe: " + JSON.stringify(data);
            }

        } catch (error) {
            document.getElementById("status").innerText = "Yhteysvirhe: " + error;
        }
    }

    async function saveMemory() {
        const title = document.getElementById("title").value;
        const text = document.getElementById("text").value;
        const tagsRaw = document.getElementById("tags").value;

        const tags = tagsRaw
            ? tagsRaw.split(",").map(t => t.trim()).filter(Boolean)
            : [];

        const response = await fetch("/memory/sade_memory", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                title: title || null,
                text: text,
                tags: tags
            })
        });

        const data = await response.json();

        if (response.ok) {
            document.getElementById("status").innerText = "Tallennettu: " + data.title;
            document.getElementById("text").value = "";
            loadMemory();
        } else {
            document.getElementById("status").innerText = "Virhe: " + JSON.stringify(data);
        }
    }

    async function loadMemory() {
    const response = await fetch("/memory/sade_memory");
    const data = await response.json();

    if (data.ok) {
        const memoryBox = document.getElementById("memory");
        memoryBox.innerText = data.content;
        memoryBox.scrollTop = memoryBox.scrollHeight;

        document.getElementById("status").innerText = "Säde-muisti ladattu.";
    } else {
        document.getElementById("memory").innerText = data.message;
    }
}

    async function loadChatLog() {
        const response = await fetch("/memory/chatlog");
        const data = await response.json();

        if (data.ok) {
            const chatLogBox = document.getElementById("chatLog");
            chatLogBox.innerText = data.content;
            chatLogBox.scrollTop = chatLogBox.scrollHeight;
        } else {
            document.getElementById("chatLog").innerText = data.message;
        }
    }

    document.getElementById("chatMessage").addEventListener("keydown", function(event) {
        if (event.ctrlKey && event.key === "Enter") {
            sendChat();
        }
    });

async function loadConfigInfo() {
    try {
        const response = await fetch("/config");
        const data = await response.json();

        if (response.ok && data.ok) {
            const info =
                "Malli: " + data.ollama_model +
                " / lämpötila: " + data.temperature +
                " / konteksti: " + data.num_ctx +
                " / muisti: " + data.memory_context_chars +
                " / chat: " + data.chat_context_chars;

            document.getElementById("configInfo").innerText = info;

            document.getElementById("configModel").value = data.ollama_model;
            document.getElementById("configTemperature").value = data.temperature;
            document.getElementById("configNumCtx").value = data.num_ctx;
            document.getElementById("configMemoryChars").value = data.memory_context_chars;
            document.getElementById("configChatChars").value = data.chat_context_chars;
        } else {
            document.getElementById("configInfo").innerText = "Asetuksia ei saatu ladattua.";
        }
    } catch (error) {
        document.getElementById("configInfo").innerText = "Asetusten lataus epäonnistui: " + error;
    }
}

async function saveConfigSettings() {
    const model = document.getElementById("configModel").value.trim();
    const temperatureRaw = document.getElementById("configTemperature").value.replace(",", ".");
    const temperature = parseFloat(temperatureRaw);
    const numCtx = parseInt(document.getElementById("configNumCtx").value);
    const memoryChars = parseInt(document.getElementById("configMemoryChars").value);
    const chatChars = parseInt(document.getElementById("configChatChars").value);

    if (!model) {
        document.getElementById("status").innerText = "Mallin nimi ei saa olla tyhjä.";
        return;
    }

    try {
        const response = await fetch("/config", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                ollama_model: model,
                temperature: temperature,
                num_ctx: numCtx,
                memory_context_chars: memoryChars,
                chat_context_chars: chatChars
            })
        });

        const data = await response.json();

        if (response.ok && data.ok) {
            document.getElementById("status").innerText = "Asetukset tallennettu.";
            loadConfigInfo();
            checkOllamaStatus();
        } else {
            document.getElementById("status").innerText = "Asetusten tallennus epäonnistui: " + JSON.stringify(data);
        }
    } catch (error) {
        document.getElementById("status").innerText = "Yhteysvirhe asetuksia tallentaessa: " + error;
    }
}
    
    loadConfigInfo();
    checkOllamaStatus();
    loadMemory();
loadChatLog();
</script>
</body>
</html>
"""