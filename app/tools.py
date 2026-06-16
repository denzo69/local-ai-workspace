from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


SAFE_TEXT_EXTENSIONS = {
    ".py", ".html", ".htm", ".md", ".txt", ".json", ".css", ".js",
    ".yml", ".yaml", ".toml", ".ini", ".ps1", ".bat"
}

BLOCKED_DIR_NAMES = {
    ".git", ".venv", "venv", "env", "__pycache__", "node_modules",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "vector_db",
}

MAX_DEFAULT_READ_CHARS = 20_000
MAX_WRITE_CHARS = 200_000


class ToolError(Exception):
    """Työkalukerroksen turvallinen virhe."""
    pass


def _project_root(project_path: Path) -> Path:
    return project_path.resolve()


def _normalize_relative_path(relative_path: Optional[str]) -> str:
    if relative_path is None:
        return ""

    value = str(relative_path).strip().replace("\\", "/")

    if value in {"", ".", "./"}:
        return ""

    return value.lstrip("/")


def _is_inside_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def safe_project_path(project_path: Path, relative_path: Optional[str]) -> Path:
    root = _project_root(project_path)
    normalized = _normalize_relative_path(relative_path)
    target = (root / normalized).resolve()

    if not _is_inside_root(target, root):
        raise ToolError("Polku ei saa osoittaa projektikansion ulkopuolelle.")

    relative = target.relative_to(root)

    for part in relative.parts:
        if part in BLOCKED_DIR_NAMES:
            raise ToolError(f"Kansio on estetty turvallisuussyistä: {part}")

    return target


def _is_safe_text_file(path: Path) -> bool:
    return path.suffix.lower() in SAFE_TEXT_EXTENSIONS


def get_tools_status(project_path: Path) -> Dict[str, Any]:
    root = _project_root(project_path)

    return {
        "ok": True,
        "enabled": True,
        "message": "Työkalukerros on käytettävissä.",
        "project_path": str(root),
        "safe_extensions": sorted(SAFE_TEXT_EXTENSIONS),
        "blocked_dirs": sorted(BLOCKED_DIR_NAMES),
        "tools": [
            "list_tools",
            "list_files",
            "read_file",
            "write_file",
            "append_file",
            "project_status",
        ],
        "time": datetime.now().isoformat(timespec="seconds"),
    }


def list_available_tools() -> Dict[str, Any]:
    return {
        "ok": True,
        "tools": [
            {
                "name": "list_files",
                "description": "Listaa tiedostot ja kansiot projektikansion sisällä.",
                "safe": True,
                "writes": False,
            },
            {
                "name": "read_file",
                "description": "Lukee turvallisen tekstitiedoston projektikansion sisältä.",
                "safe": True,
                "writes": False,
            },
            {
                "name": "write_file",
                "description": "Kirjoittaa uuden tekstitiedoston projektikansion sisälle. Ei ylikirjoita ilman overwrite=true.",
                "safe": True,
                "writes": True,
            },
            {
                "name": "append_file",
                "description": "Lisää tekstiä olemassa olevaan tai uuteen tekstitiedostoon projektikansion sisällä.",
                "safe": True,
                "writes": True,
            },
            {
                "name": "project_status",
                "description": "Palauttaa projektin perustilan ja tärkeimmät polut.",
                "safe": True,
                "writes": False,
            },
        ],
    }


def list_files(
    project_path: Path,
    relative_path: Optional[str] = "",
    max_items: int = 100,
    include_hidden: bool = False,
) -> Dict[str, Any]:
    target = safe_project_path(project_path, relative_path)

    if not target.exists():
        raise ToolError("Kansiota tai tiedostoa ei löytynyt.")

    if target.is_file():
        items = [target]
        base = target.parent
    else:
        items = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        base = target

    result_items: List[Dict[str, Any]] = []
    count = 0

    for item in items:
        if count >= max_items:
            break

        if not include_hidden and item.name.startswith("."):
            continue

        if item.name in BLOCKED_DIR_NAMES:
            continue

        try:
            relative = item.resolve().relative_to(_project_root(project_path))
        except ValueError:
            continue

        info = {
            "name": item.name,
            "relative_path": str(relative).replace("\\", "/"),
            "type": "directory" if item.is_dir() else "file",
            "exists": item.exists(),
            "size_bytes": item.stat().st_size if item.is_file() else None,
            "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat(timespec="seconds"),
        }

        result_items.append(info)
        count += 1

    return {
        "ok": True,
        "path": str(base),
        "relative_path": _normalize_relative_path(relative_path),
        "count": len(result_items),
        "items": result_items,
    }


def read_file(
    project_path: Path,
    relative_path: str,
    max_chars: int = MAX_DEFAULT_READ_CHARS,
) -> Dict[str, Any]:
    target = safe_project_path(project_path, relative_path)

    if not target.exists():
        raise ToolError("Tiedostoa ei löytynyt.")

    if not target.is_file():
        raise ToolError("Polku ei ole tiedosto.")

    if not _is_safe_text_file(target):
        raise ToolError(f"Tiedostotyyppi ei ole sallittu: {target.suffix}")

    content = target.read_text(encoding="utf-8")

    truncated = False
    if max_chars and len(content) > max_chars:
        content = content[:max_chars]
        truncated = True

    return {
        "ok": True,
        "relative_path": str(target.relative_to(_project_root(project_path))).replace("\\", "/"),
        "path": str(target),
        "size_bytes": target.stat().st_size,
        "modified": datetime.fromtimestamp(target.stat().st_mtime).isoformat(timespec="seconds"),
        "truncated": truncated,
        "content": content,
    }


def write_file(
    project_path: Path,
    relative_path: str,
    content: str,
    overwrite: bool = False,
) -> Dict[str, Any]:
    target = safe_project_path(project_path, relative_path)

    if not _is_safe_text_file(target):
        raise ToolError(f"Tiedostotyyppi ei ole sallittu: {target.suffix}")

    if target.exists() and not overwrite:
        raise ToolError("Tiedosto on jo olemassa. Käytä overwrite=true, jos haluat ylikirjoittaa sen.")

    if len(content) > MAX_WRITE_CHARS:
        raise ToolError(f"Sisältö on liian pitkä. Maksimi on {MAX_WRITE_CHARS} merkkiä.")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    return {
        "ok": True,
        "message": "Tiedosto kirjoitettu.",
        "relative_path": str(target.relative_to(_project_root(project_path))).replace("\\", "/"),
        "path": str(target),
        "size_bytes": target.stat().st_size,
        "time": datetime.now().isoformat(timespec="seconds"),
    }


def append_file(
    project_path: Path,
    relative_path: str,
    content: str,
) -> Dict[str, Any]:
    target = safe_project_path(project_path, relative_path)

    if not _is_safe_text_file(target):
        raise ToolError(f"Tiedostotyyppi ei ole sallittu: {target.suffix}")

    if len(content) > MAX_WRITE_CHARS:
        raise ToolError(f"Sisältö on liian pitkä. Maksimi on {MAX_WRITE_CHARS} merkkiä.")

    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("a", encoding="utf-8") as file:
        file.write(content)

    return {
        "ok": True,
        "message": "Teksti lisätty tiedostoon.",
        "relative_path": str(target.relative_to(_project_root(project_path))).replace("\\", "/"),
        "path": str(target),
        "size_bytes": target.stat().st_size,
        "time": datetime.now().isoformat(timespec="seconds"),
    }


def project_status(project_path: Path) -> Dict[str, Any]:
    root = _project_root(project_path)

    important_paths = {
        "project": root,
        "main": root / "main.py",
        "semantic_memory": root / "semantic_memory.py",
        "tools": root / "tools.py",
        "memory": root / "memory",
        "sade_memory": root / "memory" / "sade_memory.md",
        "chat_log": root / "memory" / "chat_log.md",
        "vector_db": root / "memory" / "vector_db",
        "templates": root / "templates",
        "ui": root / "templates" / "ui.html",
        "config": root / "config.json",
        "system_prompt": root / "system_prompt.md",
    }

    def info(path: Path) -> Dict[str, Any]:
        return {
            "path": str(path),
            "exists": path.exists(),
            "type": "directory" if path.exists() and path.is_dir() else "file" if path.exists() else "missing",
            "size_bytes": path.stat().st_size if path.exists() and path.is_file() else None,
        }

    return {
        "ok": True,
        "time": datetime.now().isoformat(timespec="seconds"),
        "paths": {name: info(path) for name, path in important_paths.items()},
    }
