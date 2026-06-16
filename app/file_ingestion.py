from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import hashlib
import json
import re

from app.semantic_memory import add_text_to_semantic_memory
from app.tools import ToolError, safe_project_path


TEXT_EXTENSIONS = {
    ".py", ".html", ".htm", ".md", ".txt", ".json", ".css", ".js",
    ".yml", ".yaml", ".toml", ".ini", ".ps1", ".bat"
}

MAX_INGEST_CHARS = 250_000


def _relative_to_project(project_path: Path, path: Path) -> str:
    return str(path.resolve().relative_to(project_path.resolve())).replace("\\", "/")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ingestion_log_path(project_path: Path) -> Path:
    memory_path = project_path / "memory"
    memory_path.mkdir(parents=True, exist_ok=True)
    return memory_path / "ingested_files.jsonl"


def _read_text_file(project_path: Path, relative_path: str, max_chars: int = MAX_INGEST_CHARS) -> Dict[str, Any]:
    target = safe_project_path(project_path, relative_path)

    if not target.exists():
        raise ToolError("Tiedostoa ei löytynyt.")

    if not target.is_file():
        raise ToolError("Polku ei ole tiedosto.")

    if target.suffix.lower() not in TEXT_EXTENSIONS:
        raise ToolError(f"Tiedostotyyppi ei ole ingestion v1:ssä sallittu: {target.suffix}")

    content = target.read_text(encoding="utf-8")

    truncated = False

    if len(content) > max_chars:
        content = content[:max_chars]
        truncated = True

    return {
        "path": str(target),
        "relative_path": _relative_to_project(project_path, target),
        "filename": target.name,
        "suffix": target.suffix.lower(),
        "content": content,
        "truncated": truncated,
        "size_bytes": target.stat().st_size,
        "modified": datetime.fromtimestamp(target.stat().st_mtime).isoformat(timespec="seconds"),
        "sha256": _sha256(content),
    }


def build_basic_summary(content: str, filename: str = "tiedosto") -> Dict[str, Any]:
    text = content.strip()
    lines = [line.rstrip() for line in text.splitlines()]

    headings: List[str] = []
    bullets: List[str] = []
    code_like_lines = 0

    for line in lines:
        stripped = line.strip()

        if not stripped:
            continue

        if stripped.startswith("#"):
            headings.append(stripped)

        if stripped.startswith(("-", "*", "•")):
            bullets.append(stripped)

        if re.search(r"\b(def|class|import|from|return|function|const|let|var)\b", stripped):
            code_like_lines += 1

    words = re.findall(r"\w+", text, flags=re.UNICODE)

    first_paragraph = ""
    for part in re.split(r"\n\s*\n", text):
        clean = part.strip()
        if clean:
            first_paragraph = clean
            break

    if len(first_paragraph) > 1200:
        first_paragraph = first_paragraph[:1200].rstrip() + "..."

    summary_lines = [
        f"Tiedosto `{filename}` sisältää noin {len(words)} sanaa, {len(lines)} riviä ja {len(text)} merkkiä.",
    ]

    if headings:
        summary_lines.append("Havaitut otsikot: " + "; ".join(headings[:8]))

    if bullets:
        summary_lines.append("Havaittuja listakohtia: " + "; ".join(bullets[:8]))

    if code_like_lines:
        summary_lines.append(f"Tiedostossa vaikuttaa olevan koodia tai teknistä rakennetta noin {code_like_lines} rivillä.")

    if first_paragraph:
        summary_lines.append("Alun sisältö: " + first_paragraph)

    return {
        "ok": True,
        "summary": "\n".join(summary_lines),
        "stats": {
            "words": len(words),
            "lines": len(lines),
            "chars": len(text),
            "headings": len(headings),
            "bullets": len(bullets),
            "code_like_lines": code_like_lines,
        },
        "headings": headings[:20],
        "bullets": bullets[:20],
    }


def summarize_file(project_path: Path, relative_path: str, max_chars: int = MAX_INGEST_CHARS) -> Dict[str, Any]:
    file_data = _read_text_file(project_path, relative_path, max_chars=max_chars)
    summary = build_basic_summary(file_data["content"], filename=file_data["filename"])

    return {
        "ok": True,
        "message": "Tiedosto tiivistetty.",
        "file": {
            "relative_path": file_data["relative_path"],
            "filename": file_data["filename"],
            "size_bytes": file_data["size_bytes"],
            "modified": file_data["modified"],
            "truncated": file_data["truncated"],
            "sha256": file_data["sha256"],
        },
        "summary": summary,
    }


def _append_ingestion_to_sade_memory(
    project_path: Path,
    file_data: Dict[str, Any],
    summary_text: str,
    title: Optional[str],
    tags: Optional[List[str]],
) -> Dict[str, Any]:
    memory_path = project_path / "memory" / "sade_memory.md"
    memory_path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().isoformat(timespec="seconds")
    display_title = title or f"Ingested file: {file_data['filename']}"
    tag_text = ", ".join(tags or ["file", "ingested"])

    markdown = (
        f"\n\n---\n\n"
        f"## {display_title}\n\n"
        f"**Aika:** {timestamp}\n\n"
        f"**Lähdetiedosto:** `{file_data['relative_path']}`\n\n"
        f"**SHA256:** `{file_data['sha256']}`\n\n"
        f"**Tagit:** {tag_text}\n\n"
        f"### Tiivistelmä\n\n"
        f"{summary_text}\n"
    )

    with memory_path.open("a", encoding="utf-8") as file:
        file.write(markdown)

    return {
        "ok": True,
        "message": "Tiedoston tiivistelmä lisätty Säde-muistiin.",
        "path": str(memory_path),
        "time": timestamp,
    }


def _append_ingestion_log(project_path: Path, entry: Dict[str, Any]) -> None:
    path = _ingestion_log_path(project_path)

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")


def ingest_file(
    project_path: Path,
    relative_path: str,
    add_to_memory: bool = True,
    add_to_semantic: bool = True,
    title: Optional[str] = None,
    tags: Optional[List[str]] = None,
    max_chars: int = MAX_INGEST_CHARS,
) -> Dict[str, Any]:
    file_data = _read_text_file(project_path, relative_path, max_chars=max_chars)
    summary = build_basic_summary(file_data["content"], filename=file_data["filename"])
    summary_text = summary["summary"]

    memory_result: Optional[Dict[str, Any]] = None
    semantic_result: Optional[Dict[str, Any]] = None

    if add_to_memory:
        memory_result = _append_ingestion_to_sade_memory(
            project_path,
            file_data,
            summary_text=summary_text,
            title=title,
            tags=tags,
        )

    if add_to_semantic:
        semantic_result = add_text_to_semantic_memory(
            project_path,
            file_data["content"],
            title=title or file_data["filename"],
            source=f"file:{file_data['relative_path']}",
            tags=tags or ["file", "ingested"],
            timestamp=datetime.now().isoformat(timespec="seconds"),
        )

    log_entry = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "relative_path": file_data["relative_path"],
        "filename": file_data["filename"],
        "sha256": file_data["sha256"],
        "add_to_memory": add_to_memory,
        "add_to_semantic": add_to_semantic,
        "semantic_chunks": (semantic_result or {}).get("chunks"),
    }

    _append_ingestion_log(project_path, log_entry)

    return {
        "ok": True,
        "message": "Tiedosto käsitelty.",
        "file": {
            "relative_path": file_data["relative_path"],
            "filename": file_data["filename"],
            "size_bytes": file_data["size_bytes"],
            "modified": file_data["modified"],
            "truncated": file_data["truncated"],
            "sha256": file_data["sha256"],
        },
        "summary": summary,
        "memory": memory_result,
        "semantic_memory": semantic_result,
        "ingestion_log": str(_ingestion_log_path(project_path)),
    }


def read_ingestion_log(project_path: Path, limit: int = 50) -> Dict[str, Any]:
    path = _ingestion_log_path(project_path)

    if not path.exists():
        return {
            "ok": True,
            "path": str(path),
            "count": 0,
            "items": [],
        }

    lines = path.read_text(encoding="utf-8").splitlines()
    selected = lines[-max(1, min(int(limit), 500)):]

    items: List[Dict[str, Any]] = []

    for line in selected:
        try:
            items.append(json.loads(line))
        except Exception:
            items.append({"ok": False, "raw": line})

    return {
        "ok": True,
        "path": str(path),
        "count": len(items),
        "items": items,
    }
