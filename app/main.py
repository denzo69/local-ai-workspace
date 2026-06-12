from fastapi import FastAPI
from pydantic import BaseModel, Field
from datetime import datetime
from pathlib import Path
from typing import Optional, List

app = FastAPI(title="Säde v1")

BASE_PATH = Path("C:/Sade")


class MemoryEntry(BaseModel):
    title: Optional[str] = Field(default=None, description="Merkinnän otsikko")
    text: str = Field(..., description="Varsinainen merkintäteksti")
    tags: Optional[List[str]] = Field(default=None, description="Vapaaehtoiset tagit")


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


def append_markdown_entry(path: Path, entry: MemoryEntry, category: str):
    path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().isoformat(timespec="seconds")
    title = entry.title if entry.title else category
    tags = ", ".join(entry.tags) if entry.tags else ""

    block = []
    block.append("")
    block.append("---")
    block.append(f"## {title}")
    block.append("")
    block.append(f"**Aika:** {timestamp}")
    block.append(f"**Kategoria:** {category}")

    if tags:
        block.append(f"**Tagit:** {tags}")

    block.append("")
    block.append(entry.text)
    block.append("")

    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(block))

    return {
        "ok": True,
        "message": "Merkintä tallennettu.",
        "path": str(path),
        "title": title,
        "time": timestamp
    }


@app.get("/")
def home():
    return {
        "name": "Säde v1",
        "status": "pesä online",
        "message": "Tämä on Säde v1:n paikallinen palvelu.",
        "time": datetime.now().isoformat()
    }


@app.get("/health")
def health():
    return {
        "ok": True,
        "status": "alive",
        "service": "sade-v1",
        "time": datetime.now().isoformat()
    }


@app.get("/memory")
def memory():
    return read_markdown_file(BASE_PATH / "Muistot" / "muistot.md")


@app.get("/sydankirja")
def sydankirja():
    return read_markdown_file(BASE_PATH / "Sydankirja" / "sydankirja.md")


@app.get("/lupaukset")
def lupaukset():
    return read_markdown_file(BASE_PATH / "Lupaukset" / "lupaukset.md")


@app.post("/memory/add")
def add_memory(entry: MemoryEntry):
    return append_markdown_entry(BASE_PATH / "Muistot" / "muistot.md", entry, "Muisto")


@app.post("/sydankirja/add")
def add_sydankirja(entry: MemoryEntry):
    return append_markdown_entry(BASE_PATH / "Sydankirja" / "sydankirja.md", entry, "Sydänkirja")


@app.post("/lupaukset/add")
def add_lupaus(entry: MemoryEntry):
    return append_markdown_entry(BASE_PATH / "Lupaukset" / "lupaukset.md", entry, "Lupaus")