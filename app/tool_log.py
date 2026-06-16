from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import json


TOOL_LOG_FILENAME = "tool_log.jsonl"


def _tool_log_path(project_path: Path) -> Path:
    memory_path = project_path / "memory"
    memory_path.mkdir(parents=True, exist_ok=True)
    return memory_path / TOOL_LOG_FILENAME


def _safe_preview(value: Any, max_chars: int = 1200) -> Any:
    """
    Pienentää lokiin menevää dataa niin, ettei suuri tiedostosisältö täytä lokia.
    """
    if isinstance(value, str):
        if len(value) <= max_chars:
            return value
        return value[:max_chars].rstrip() + f"... [katkaistu, alkuperäinen pituus {len(value)} merkkiä]"

    if isinstance(value, dict):
        safe: Dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in {"content", "text", "reply"}:
                safe[key] = _safe_preview(item, max_chars=500)
            else:
                safe[key] = _safe_preview(item, max_chars=max_chars)
        return safe

    if isinstance(value, list):
        return [_safe_preview(item, max_chars=max_chars) for item in value[:50]]

    return value


def log_tool_event(
    project_path: Path,
    tool: str,
    action: str,
    request: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    ok: Optional[bool] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    path = _tool_log_path(project_path)

    if ok is None:
        ok = bool(result.get("ok", True)) if isinstance(result, dict) else error is None

    entry = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "tool": tool,
        "action": action,
        "ok": ok,
        "request": _safe_preview(request or {}),
        "result": _safe_preview(result or {}),
        "error": error,
    }

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return {
        "ok": True,
        "message": "Työkalutapahtuma kirjattu.",
        "path": str(path),
        "time": entry["time"],
    }


def read_tool_log(project_path: Path, limit: int = 50) -> Dict[str, Any]:
    path = _tool_log_path(project_path)

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
            items.append({
                "time": None,
                "tool": "unknown",
                "action": "parse_error",
                "ok": False,
                "raw": line,
            })

    return {
        "ok": True,
        "path": str(path),
        "count": len(items),
        "items": items,
    }


def clear_tool_log(project_path: Path) -> Dict[str, Any]:
    path = _tool_log_path(project_path)
    path.write_text("", encoding="utf-8")

    return {
        "ok": True,
        "message": "Työkaluloki tyhjennetty.",
        "path": str(path),
        "time": datetime.now().isoformat(timespec="seconds"),
    }
