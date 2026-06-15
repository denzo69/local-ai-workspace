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
MEMORY_PATH = BASE_PATH / "memory"
SADE_MEMORY_PATH = MEMORY_PATH / "sade_memory.md"
LOG_PATH = MEMORY_PATH / "memory_log.jsonl"
CHAT_LOG_PATH = MEMORY_PATH / "chat_log.md"

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "gpt-oss:20b"


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


def get_memory_context(max_chars: int = 6000) -> str:
    ensure_paths()

    if not SADE_MEMORY_PATH.exists():
        return ""

    content = SADE_MEMORY_PATH.read_text(encoding="utf-8")

    if len(content) <= max_chars:
        return content

    return content[-max_chars:]


def get_chat_context(max_chars: int = 4000) -> str:
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
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_ctx": 8192
        }
    }

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        OLLAMA_URL,
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


@app.on_event("startup")
def startup_event():
    ensure_paths()


@app.get("/")
def root():
    return {
        "name": "Säde v1",
        "status": "awake",
        "message": "Säde v1 toimii.",
        "model": OLLAMA_MODEL,
        "paths": {
            "base": str(BASE_PATH),
            "memory": str(MEMORY_PATH),
            "sade_memory": str(SADE_MEMORY_PATH),
            "chat_log": str(CHAT_LOG_PATH)
        },
        "endpoints": [
            "/ui",
            "/chat",
            "/health",
            "/memory/sade_memory",
            "/memory/chatlog",
            "/docs"
        ]
    }


@app.get("/health")
def health():
    return {
        "ok": True,
        "status": "running",
        "model": OLLAMA_MODEL,
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
            model=OLLAMA_MODEL,
            time=datetime.now().isoformat(timespec="seconds")
        )

    prompt = build_sade_prompt(request.message)
    reply = ask_ollama(prompt)

    append_chat_log(request.message, reply)

    return ChatResponse(
        ok=True,
        reply=reply,
        model=OLLAMA_MODEL,
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
        <p class="small">Malli: gpt-oss:20b / Ollama / localhost</p>

        <h2>Keskustele Säteen kanssa</h2>

        <div id="chatBox" class="chat-box"></div>

        <label>Viesti</label>
        <textarea id="chatMessage" placeholder="Kirjoita viesti Säde v1:lle..."></textarea>

       	<button onclick="sendChat()">Lähetä</button>
	<button onclick="clearVisibleChat()">Tyhjennä näkyvä chat</button>

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

    loadMemory();
    loadChatLog();
</script>
</body>
</html>
"""