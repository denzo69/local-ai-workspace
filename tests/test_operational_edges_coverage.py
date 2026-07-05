from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import urllib.error

from app import memory_cleaner
from app import model_provider
from app.debug_trace import read_traces, summarize_latest_trace, write_trace
from app.language_pack import build_language_context, inspect_text, language_status, preferred_term, resolve_project_root
from app.model_provider import ModelProviderError, model_provider_status, provider_from_config


def test_debug_trace_redacts_limits_and_summarizes_routes(tmp_path: Path) -> None:
    root = tmp_path
    write_trace(
        root,
        event="chat_intent_planned",
        user_message="password: secret-value sk-abcdefghijklmnop",
        route="intent_planner",
        decision="current_external_information",
        details={"intent": "current_external_information", "token": "hidden", "items": list(range(40))},
    )
    write_trace(root, event="chat_grounding_selected", details={"target_scope": "external_local_info", "selected_sources": ["web"]})
    write_trace(
        root,
        event="conversation_context_used",
        details={"conversation_context": {"topic": "Lieksa"}, "search_query": "Lieksa palvelut"},
    )
    write_trace(root, event="web_search_executed", details={"query": "Lieksa palvelut", "sources_found": "not-int"})
    write_trace(root, event="web_sources_read", details={"sources_read": "2"})
    write_trace(root, event="output_validated", details={"result": "passed", "route_used": "web_search"})

    data = read_traces(root, limit=500)
    assert data["count"] == 6
    assert data["items"][0]["details"].get("token") is None
    assert "secret-value" not in data["items"][0]["message_preview"]
    assert "[SENSUROITU]" in data["items"][0]["message_preview"]

    # Invalid JSON lines are ignored rather than breaking diagnostics.
    trace_file = root / "memory" / "debug_trace.jsonl"
    trace_file.write_text(trace_file.read_text(encoding="utf-8") + "\nnot-json\n", encoding="utf-8")
    assert read_traces(root)["count"] == 6

    summary = summarize_latest_trace(root)
    assert summary["mode"] == "sanitized_route_summary"
    assert summary["route_used"] == "web_search"
    assert summary["intent"] == "current_external_information"
    assert summary["search_query"] == "Lieksa palvelut"
    assert summary["sources_found"] == 0
    assert summary["sources_read"] == 2
    assert summary["target_scope"] == "external_local_info"


def test_language_pack_operational_edges(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    app_root.mkdir()
    assert resolve_project_root().name == "Sade-v1"
    assert resolve_project_root(app_root) == tmp_path
    assert preferred_term("guardrails") == "turvarajat"
    assert preferred_term("unknown-term") == "unknown-term"

    assert "Pidä vastaus tiiviinä" in build_language_context("vastaa suomeksi", concise=True)
    inspected = inspect_text("Fastapi ja \ufffd sekä ÃƒÂ¤")
    assert inspected["ok"] is False
    assert inspected["replacement_character_count"] == 1
    assert "FastAPI" in inspected["possibly_changed_technical_forms"]

    status = language_status(tmp_path)
    assert status["enabled"] is True
    assert status["policy_path"].endswith("docs\\finnish_language_pack.md") or status["policy_path"].endswith("docs/finnish_language_pack.md")


def test_model_provider_config_edges() -> None:
    provider = provider_from_config({"model_provider": "ollama", "ollama_model": "llama3:latest", "temperature": "0.2", "num_ctx": "2048"})
    assert provider.name == "ollama"
    assert provider.temperature == 0.2
    assert provider.num_ctx == 2048

    status = model_provider_status({"model_provider": "not-real", "ollama_model": "x"})
    assert status["ok"] is False
    assert status["url"] is None

    with pytest.raises(ModelProviderError):
        provider_from_config({"model_provider": "not-real"})


def test_model_provider_generate_generic_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args, **kwargs):
        raise ValueError("broken response")

    monkeypatch.setattr(model_provider.urllib.request, "urlopen", boom)
    provider = provider_from_config({"model_provider": "ollama", "ollama_model": "llama3:latest"})
    with pytest.raises(ModelProviderError) as error:
        provider.generate("hello", timeout=1)
    assert "Mallikutsu epäonnistui" in str(error.value)


def test_model_provider_generate_url_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args, **kwargs):
        raise urllib.error.URLError("not running")

    monkeypatch.setattr(model_provider.urllib.request, "urlopen", boom)
    provider = provider_from_config({"model_provider": "ollama", "ollama_model": "llama3:latest"})
    with pytest.raises(ModelProviderError) as error:
        provider.generate("hello", timeout=1)
    assert "Ollamaan ei saada yhteyttä" in str(error.value)


class _FakeCollection:
    def __init__(self) -> None:
        old = (datetime.now(timezone.utc) - timedelta(days=500)).isoformat()
        self.deleted: list[str] = []
        self._items = {
            "ids": ["a", "b", "c", "protected", "bad-date"],
            "documents": ["same text", "same text", "old chat", "protected memory", "bad date"],
            "metadatas": [
                {"source": "note.md"},
                {"source": "note.md"},
                {"source": "chat_log.md", "saved_at": old},
                {"source": "sade_memory.md"},
                {"source": "chat_log.md", "saved_at": "not-a-date"},
            ],
        }

    def get(self, include):
        return self._items

    def count(self) -> int:
        return len(self._items["ids"]) - len(self.deleted)

    def delete(self, ids):
        self.deleted.extend(ids)


def test_memory_cleaner_plan_and_apply_edges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeCollection()
    audit_events: list[dict] = []
    monkeypatch.setattr(memory_cleaner, "_open_collection", lambda root: fake)
    monkeypatch.setattr(memory_cleaner, "write_audit_event", lambda *args, **kwargs: audit_events.append(kwargs))

    plan = memory_cleaner.plan_memory_cleanup(tmp_path, older_than_days=1)
    assert plan["ok"] is True
    assert plan["candidate_count"] == 2
    assert {item["reason"] for item in plan["candidates"]} == {"duplicate", "old_chat_log"}
    assert all(item["id"] != "protected" for item in plan["candidates"])

    denied = memory_cleaner.apply_memory_cleanup(tmp_path, ["b"], confirmation="wrong")
    assert denied["ok"] is False

    empty = memory_cleaner.apply_memory_cleanup(tmp_path, ["not-allowed"], confirmation=memory_cleaner.CONFIRMATION_PHRASE)
    assert empty["ok"] is False

    applied = memory_cleaner.apply_memory_cleanup(tmp_path, ["b", "c", "protected"], confirmation=memory_cleaner.CONFIRMATION_PHRASE)
    assert applied["ok"] is True
    assert applied["deleted"] == 2
    assert fake.deleted == ["b", "c"]
    assert len(audit_events) == 2


def test_memory_cleaner_open_failure_returns_dry_run_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory_cleaner, "_open_collection", lambda root: (_ for _ in ()).throw(RuntimeError("no vector db")))
    result = memory_cleaner.plan_memory_cleanup(tmp_path)
    assert result == {"ok": False, "dry_run": True, "error": "no vector db", "candidates": []}


def test_memory_cleaner_open_collection_import_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory_cleaner, "_import_chromadb", lambda: (None, None, "missing chromadb"))
    with pytest.raises(RuntimeError, match="missing chromadb"):
        memory_cleaner._open_collection(tmp_path)
