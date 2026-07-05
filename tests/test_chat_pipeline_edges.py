from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import chat_pipeline
from app.chat_pipeline import ChatPipelineDependencies, handle_chat_message


class _MemoryEntry:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _deps(tmp_path: Path, **overrides):
    logs: list[tuple[str, str]] = []
    events: list[dict] = []

    values = dict(
        project_path=tmp_path,
        sade_memory_path=tmp_path / "memory.md",
        memory_entry_class=_MemoryEntry,
        append_chat_log=lambda message, reply: logs.append((message, reply)),
        load_config=lambda: {"ollama_model": "test-model"},
        append_markdown_entry=lambda path, entry: {"ok": True, "time": "2026-07-04T12:00:00"},
        extract_memory_command=lambda message: None,
        handle_learning_review_chat_command=lambda message: {"handled": False},
        handle_learning_chat_command=lambda message: {"handled": False},
        handle_task_chat_command=lambda message: {"handled": False},
        handle_rag_chat_command=lambda message: {"handled": False},
        route_tool_request=lambda root, message: {"handled": False},
        build_web_search_chat_result=lambda *args, **kwargs: {"tool": "web_search", "result": {"ok": False, "results": []}, "reply": ""},
        get_tool_policy=lambda tool: {"risk_level": "medium"},
        log_tool_event=lambda *args, **kwargs: events.append({"kind": "tool", "args": args, **kwargs}),
        audit=lambda **kwargs: events.append({"kind": "audit", **kwargs}),
        audit_risk=lambda level: f"audit-{level}",
        build_sade_prompt=lambda message, planning: f"PROMPT:{message}:{planning.intent}",
        ask_ollama=lambda prompt: "mallivastaus",
        get_chat_context=lambda max_chars=None: "",
    )
    values.update(overrides)
    deps = ChatPipelineDependencies(**values)
    object.__setattr__(deps, "_test_logs", logs)
    object.__setattr__(deps, "_test_events", events)
    return deps


def test_web_source_formatting_and_links() -> None:
    result = {
        "checked_sources": [
            {"title": "Read source", "final_url": "https://example.test/read", "description": "  read   excerpt  "},
            {"title": "Broken source", "url": "https://example.test/broken", "error": "timeout"},
        ],
        "source_answer_summary": "Summary from source reader.",
        "results": [
            {"title": "Result A", "url": "https://example.test/a", "snippet": "  hello   world  "},
            {"title": "Result B", "snippet": ""},
        ],
    }
    formatted = chat_pipeline._format_web_sources(result)
    assert "Luetut lähdeotteet" in formatted
    assert "Automaattinen lähdeyhteenveto" in formatted
    assert "Hakutuloskatkelmat" in formatted
    assert "Luku epäonnistui" in formatted

    linked = chat_pipeline._append_source_links("Answer", result)
    assert "Lähteet:" in linked
    assert "https://example.test/a" in linked
    assert chat_pipeline._append_source_links("Answer", {"results": []}) == "Answer"


def test_contextual_search_message_handles_no_context_and_exceptions(tmp_path: Path) -> None:
    planning = SimpleNamespace(use_chat_context=False)
    deps = _deps(tmp_path)
    assert chat_pipeline._contextual_search_message("jatka", planning, deps) == "jatka"

    planning = SimpleNamespace(use_chat_context=True)
    deps = _deps(tmp_path, get_chat_context=lambda max_chars=None: (_ for _ in ()).throw(RuntimeError("no log")))
    assert chat_pipeline._contextual_search_message("jatka", planning, deps) == "jatka"

    deps = _deps(tmp_path, get_chat_context=lambda max_chars=None: "User: Kerrotko Lieksan autohuolloista?\nAssistant: Lähteet...")
    enriched = chat_pipeline._contextual_search_message("Onko ne auki viikonloppuna?", planning, deps)
    assert enriched
    assert "viikonloppuna" in enriched.lower()


def test_answer_from_web_search_uses_model_summary_and_source_reader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    search = {
        "tool": "web_search",
        "result": {"ok": True, "query": "Lieksa", "provider": "test", "results": [{"title": "A", "url": "https://a.test"}]},
        "reply": "raw search reply",
    }
    deps = _deps(tmp_path, build_web_search_chat_result=lambda *args, **kwargs: search, ask_ollama=lambda prompt: "Tiivistetty vastaus")
    monkeypatch.setattr(
        "app.web_search.read_search_result_sources",
        lambda result, max_sources=3: {"ok": True, "sources": [{"title": "A", "preview": "p"}], "verified_count": 1, "answer_summary": "source summary"},
    )

    output = chat_pipeline._answer_from_web_search("Lieksan palvelut", SimpleNamespace(use_chat_context=False), deps, reason="test")
    assert output["used_model_summary"] is True
    assert "Tiivistetty vastaus" in output["reply"]
    assert "Lähteet:" in output["reply"]


def test_answer_from_web_search_fallback_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    deps = _deps(
        tmp_path,
        build_web_search_chat_result=lambda *args, **kwargs: {"tool": "web_search", "result": {"ok": False}, "reply": ""},
    )
    no_results = chat_pipeline._answer_from_web_search("x", SimpleNamespace(use_chat_context=False), deps, reason="none")
    assert no_results["used_model_summary"] is False
    assert "ei palauttanut" in no_results["reply"]

    search = {"tool": "web_search", "result": {"ok": True, "results": [{"title": "A", "url": "https://a.test"}]}, "reply": "tool reply"}
    monkeypatch.setattr(
        "app.web_search.read_search_result_sources",
        lambda result, max_sources=3: {"ok": True, "sources": [{"title": "A"}], "verified_count": 1, "answer_summary": "source summary"},
    )
    deps = _deps(
        tmp_path,
        build_web_search_chat_result=lambda *args, **kwargs: search,
        ask_ollama=lambda prompt: (_ for _ in ()).throw(RuntimeError("model down")),
    )
    source_summary = chat_pipeline._answer_from_web_search("x", SimpleNamespace(use_chat_context=False), deps, reason="summary")
    assert source_summary["used_model_summary"] is False
    assert "source summary" in source_summary["reply"]


def test_handle_chat_message_direct_memory_and_command_paths(tmp_path: Path) -> None:
    deps = _deps(tmp_path)
    with pytest.raises(HTTPException):
        handle_chat_message("   ", deps)

    direct = handle_chat_message("Mikä päivä tänään on?", deps)
    assert direct["ok"] is True
    assert "model" in direct
    assert deps._test_logs  # type: ignore[attr-defined]

    deps = _deps(tmp_path, extract_memory_command=lambda message: "muistettava asia")
    memory = handle_chat_message("muista tämä", deps)
    assert "Tallensin" in memory["reply"]

    for key, handler_name, fallback in [
        ("review", "handle_learning_review_chat_command", "Oppimiskatsauskomento"),
        ("learning", "handle_learning_chat_command", "Oppimiskomento"),
        ("task", "handle_task_chat_command", "Tehtäväkomento"),
        ("rag", "handle_rag_chat_command", "RAG-komento"),
    ]:
        deps = _deps(tmp_path, **{handler_name: lambda message, key=key: {"handled": True}})
        response = handle_chat_message(f"{key} command", deps)
        assert fallback in response["reply"]


def test_handle_chat_message_tool_and_llm_fallback_paths(tmp_path: Path) -> None:
    deps = _deps(tmp_path, route_tool_request=lambda root, message: {"handled": True, "tool": "demo_tool", "result": {"ok": True}, "reply": ""})
    tool_response = handle_chat_message("käytä työkalua", deps)
    assert "tool returned no visible reply" in tool_response["reply"]
    assert tool_response["model"] == "test-model"

    deps = _deps(tmp_path, ask_ollama=lambda prompt: "LLM fallback reply")
    fallback = handle_chat_message("Kerro lyhyt tervehdys", deps)
    assert fallback["reply"] == "LLM fallback reply"


def test_handle_chat_message_model_502_can_fallback_to_web(tmp_path: Path) -> None:
    deps = _deps(
        tmp_path,
        ask_ollama=lambda prompt: (_ for _ in ()).throw(HTTPException(status_code=502, detail="down")),
        build_web_search_chat_result=lambda *args, **kwargs: {"tool": "web_search", "result": {"ok": True}, "reply": "web fallback"},
    )
    response = handle_chat_message("Tämänhetkinen hinta sähköauton lataukselle", deps)
    assert response["reply"] == "web fallback"
