from __future__ import annotations

"""Kehittäjän jäljitettävyys: mitä reittiä pyyntö kulki ja miksi."""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


TRACE_FILE = "debug_trace.jsonl"


def _trace_path(project_root: Path) -> Path:
    path = Path(project_root).resolve() / "memory" / TRACE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _redact(item) for key, item in value.items() if str(key).lower() not in {"password", "token", "cookie"}}
    if isinstance(value, list):
        return [_redact(item) for item in value[:30]]
    text = str(value)
    text = re.sub(r"(?i)(password|salasana|token|api[_ -]?key)\s*[:=]\s*\S+", r"\1=[SENSUROITU]", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "[SENSUROITU]", text)
    return text[:2000]


def write_trace(
    project_root: Path,
    *,
    event: str,
    user_message: str = "",
    route: str = "",
    decision: str = "",
    tool: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    created_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    message_hash = hashlib.sha256(str(user_message or "").encode("utf-8", errors="ignore")).hexdigest()[:16]
    entry = {
        "created_at": created_at,
        "event": event,
        "message_hash": message_hash,
        "message_preview": _redact(user_message)[:240],
        "route": route,
        "decision": decision,
        "tool": tool,
        "details": _redact(details or {}),
    }
    with _trace_path(project_root).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return {"ok": True, "entry": entry}


def read_traces(project_root: Path, limit: int = 50) -> Dict[str, Any]:
    path = _trace_path(project_root)
    items: List[Dict[str, Any]] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                items.append(json.loads(line))
            except Exception:
                continue
    return {
        "ok": True,
        "path": str(path),
        "count": len(items),
        "items": items[-max(1, min(int(limit), 200)):],
    }


def summarize_latest_trace(project_root: Path, limit: int = 40) -> Dict[str, Any]:
    """Return a compact operational route summary for developer debugging.

    This is not chain-of-thought. It only exposes routing/tool/source metadata
    already written by the chat pipeline.
    """
    data = read_traces(project_root, limit=limit)
    items = data.get("items") or []
    route_used = ""
    intent = ""
    search_query = ""
    sources_found = 0
    sources_read = 0
    validator_result = ""
    conversation_context: Dict[str, Any] = {}
    grounding: Dict[str, Any] = {}

    for item in items:
        details = item.get("details") or {}
        route_used = str(details.get("route_used") or route_used)
        if item.get("event") == "chat_intent_planned":
            intent = str(details.get("intent") or item.get("decision") or intent)
        if item.get("event") == "chat_grounding_selected":
            grounding = dict(details or {})
        if item.get("event") == "conversation_context_used":
            conversation_context = dict(details.get("conversation_context") or {})
            search_query = str(details.get("search_query") or search_query)
        if item.get("event") == "web_search_executed":
            search_query = str(details.get("query") or search_query)
            try:
                sources_found = int(details.get("sources_found") or sources_found)
            except Exception:
                pass
        if item.get("event") == "web_sources_read":
            try:
                sources_read = int(details.get("sources_read") or sources_read)
            except Exception:
                pass
        if item.get("event") == "output_validated":
            validator_result = str(details.get("result") or validator_result)

    return {
        "ok": True,
        "mode": "sanitized_route_summary",
        "items_seen": len(items),
        "route_used": route_used or "unknown",
        "intent": intent or "unknown",
        "search_query": search_query,
        "sources_found": sources_found,
        "sources_read": sources_read,
        "validator_result": validator_result or "not_recorded",
        "conversation_context": conversation_context,
        "grounding": grounding,
        "target_scope": grounding.get("target_scope") or "unknown",
        "selected_sources": grounding.get("selected_sources") or [],
        "rejected_sources": grounding.get("rejected_sources") or [],
        "grounding_confidence": grounding.get("grounding_confidence") or 0,
        "grounding_reason": grounding.get("grounding_reason") or "",
        "note": "Operational trace only; no hidden reasoning is exposed.",
    }
