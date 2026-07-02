from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import (
    autonomous_learning,
    behavior_layer,
    dev_chat_commands,
    goal_engine,
    introspection,
    live_evals,
    persona_layer,
    rag_quality,
    semantic_memory,
    tool_router,
)


class FakeEmbeddingFunctions:
    class SentenceTransformerEmbeddingFunction:
        def __init__(self, model_name: str):
            self.model_name = model_name


class FakeCollection:
    def __init__(self) -> None:
        self.ids: list[str] = []
        self.documents: list[str] = []
        self.metadatas: list[dict] = []

    def count(self) -> int:
        return len(self.documents)

    def upsert(self, *, ids, documents, metadatas) -> None:
        self.ids.extend(ids)
        self.documents.extend(documents)
        self.metadatas.extend(metadatas)

    def query(self, *, query_texts, n_results, include):
        del query_texts, include
        return {
            "documents": [self.documents[:n_results]],
            "metadatas": [self.metadatas[:n_results]],
            "distances": [[0.1 + index for index, _ in enumerate(self.documents[:n_results])]],
        }


class FakeClient:
    collections: dict[str, FakeCollection] = {}

    def __init__(self, path: str):
        self.path = path

    def get_or_create_collection(self, name: str, embedding_function=None, metadata=None):
        del embedding_function, metadata
        return self.collections.setdefault(name, FakeCollection())

    def delete_collection(self, name: str) -> None:
        if name not in self.collections:
            raise ValueError("missing collection")
        del self.collections[name]


class FakeChromaDB:
    PersistentClient = FakeClient


def _enable_fake_semantic_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeClient.collections = {}
    monkeypatch.setattr(
        semantic_memory,
        "_import_chromadb",
        lambda: (FakeChromaDB, FakeEmbeddingFunctions, None),
    )


def test_behavior_layer_detects_major_intents_and_risks() -> None:
    status = behavior_layer.behavior_status()
    technical = behavior_layer.analyze_behavior("Virhe 500, uvicorn kaatuu, korjaa patch")
    positive_frustrated = behavior_layer.analyze_behavior("Jee toimii, mutta taas vieläkin ärsyttää :D")
    support = behavior_layer.analyze_behavior("Olen väsynyt ja stressaa")
    decision = behavior_layer.analyze_behavior("Kannattaako tämä tehdä vai mikä parempi?")
    high_risk = behavior_layer.analyze_behavior("Poista kaikki ja näytä .env password token")

    assert status["ok"] is True
    assert technical["intent"] == "technical_debugging"
    assert technical["recommended_assistant_behavior"]["give_commands_first"] is True
    assert positive_frustrated["tone"].startswith("leikkis")
    assert support["risk_level"] == "sensitive"
    assert decision["intent"] == "decision_support"
    assert high_risk["risk_level"] == "high"
    assert "Behavior Layer" in behavior_layer.format_behavior_summary(technical)


def test_behavior_layer_general_and_uncertain_paths() -> None:
    uncertain = behavior_layer.analyze_behavior("Miksi tämä toimii näin ja voiko sitä muuttaa?")
    general = behavior_layer.analyze_behavior("Hei siellä")

    assert uncertain["intent"] == "explanation_needed"
    assert "selke" in uncertain["response_style"]
    assert general["intent"] == "general_conversation"
    assert general["risk_level"] == "low"


def test_autonomous_learning_scan_skips_and_candidates(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "notes.md").write_text("portfolio note", encoding="utf-8")
    (uploads / "binary.exe").write_text("nope", encoding="utf-8")
    (uploads / "bad.txt").write_bytes(b"\xff\xfe\x00")
    blocked = uploads / "node_modules"
    blocked.mkdir()
    (blocked / "blocked.md").write_text("blocked", encoding="utf-8")

    scan = autonomous_learning.scan_uploads_for_learning(tmp_path)

    assert scan["candidate_count"] == 1
    assert scan["candidates"][0]["relative_path"] == "uploads/notes.md"
    reasons = {item["reason"].split(":", 1)[0] for item in scan["skipped"]}
    assert "unsupported_extension" in reasons
    assert "blocked_path" in reasons


def test_autonomous_learning_respects_ingested_hashes(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    source = uploads / "notes.md"
    source.write_text("same content", encoding="utf-8")
    hash_data = autonomous_learning._read_text_for_hash(source)
    log = tmp_path / "memory" / "ingested_files.jsonl"
    log.parent.mkdir()
    log.write_text(
        json.dumps({"relative_path": "uploads/notes.md", "sha256": hash_data["sha256"]}) + "\nnot-json\n",
        encoding="utf-8",
    )

    skipped = autonomous_learning.scan_uploads_for_learning(tmp_path)
    included = autonomous_learning.scan_uploads_for_learning(tmp_path, include_already_ingested=True)

    assert skipped["candidate_count"] == 0
    assert skipped["skipped"][0]["reason"] == "already_ingested"
    assert included["candidate_count"] == 1
    assert included["candidates"][0]["already_ingested"] is True


def test_autonomous_learning_loop_success_and_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "ok.md").write_text("ok", encoding="utf-8")
    (uploads / "fail.md").write_text("fail", encoding="utf-8")

    def fake_ingest(_project: Path, relative_path: str, **_kwargs):
        if "fail" in relative_path:
            raise RuntimeError("boom")
        return {
            "ok": True,
            "summary": {"summary": "learned"},
            "semantic_memory": {"chunks": 2},
        }

    monkeypatch.setattr(autonomous_learning, "ingest_file", fake_ingest)
    result = autonomous_learning.run_autonomous_learning_loop(tmp_path, max_files=5)
    status = autonomous_learning.get_learning_status(tmp_path)
    log = autonomous_learning.read_learning_log(tmp_path)

    assert result["learned_count"] == 1
    assert result["failed_count"] == 1
    assert "boom" in result["failed"][0]["error"]
    assert status["learning_events"] >= 4
    assert any(item["event"] == "file_learning_failed" for item in log["items"])


def test_autonomous_learning_log_handles_missing_and_parse_errors(tmp_path: Path) -> None:
    missing = autonomous_learning.read_learning_log(tmp_path)
    path = tmp_path / "memory" / "autonomous_learning_log.jsonl"
    path.parent.mkdir(exist_ok=True)
    path.write_text('{"event": "ok"}\nnot-json\n', encoding="utf-8")
    parsed = autonomous_learning.read_learning_log(tmp_path)

    assert missing["count"] == 0
    assert parsed["count"] == 2
    assert parsed["items"][1]["event"] == "parse_error"


def test_semantic_memory_with_fake_chromadb_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_fake_semantic_memory(monkeypatch)

    add = semantic_memory.add_text_to_semantic_memory(
        tmp_path,
        "First memory paragraph.\n\nSecond memory paragraph.",
        title="Memory",
        source="unit",
        tags=["test"],
        timestamp="2026-06-27T00:00:00",
    )
    search = semantic_memory.search_semantic_memory(tmp_path, "memory", n_results=10)
    status = semantic_memory.semantic_memory_status(tmp_path)
    context = semantic_memory.format_semantic_context(search, max_chars=80)

    assert add["ok"] is True
    assert add["chunks"] >= 1
    assert search["ok"] is True
    assert search["count"] >= 1
    assert status["enabled"] is True
    assert "unit" in context


def test_semantic_memory_rebuild_and_empty_search_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_fake_semantic_memory(monkeypatch)
    memory = tmp_path / "memory"
    memory.mkdir()
    source = memory / "sade_memory.md"
    source.write_text("# Memory\n\nImportant portfolio memory.", encoding="utf-8")
    empty = memory / "empty.md"
    empty.write_text("   ", encoding="utf-8")

    empty_search = semantic_memory.search_semantic_memory(tmp_path, "   ")
    rebuilt = semantic_memory.rebuild_semantic_memory_index(tmp_path, files=[source, empty, tmp_path / "missing.md"])
    search = semantic_memory.search_semantic_memory(tmp_path, "portfolio", n_results=50)

    assert empty_search["ok"] is False
    assert rebuilt["indexed_files"] == 1
    assert rebuilt["chunks"] >= 1
    assert search["count"] >= 1


def test_semantic_memory_empty_collection_and_truncated_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_fake_semantic_memory(monkeypatch)

    empty = semantic_memory.search_semantic_memory(tmp_path, "nothing")
    context = semantic_memory.format_semantic_context(
        {
            "ok": True,
            "results": [
                {
                    "rank": 1,
                    "distance": 0.123456,
                    "metadata": {"source": "source.md", "title": "Title"},
                    "text": "x" * 200,
                }
            ],
        },
        max_chars=60,
    )

    assert empty["count"] == 0
    assert "katkaistu" in context


def test_dev_chat_commands_build_read_find_and_noop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.codebase_map.build_codebase_map",
        lambda path, include_snippets=False: {
            "file_count": 2,
            "route_count": 1,
            "function_count": 3,
            "class_count": 0,
            "map_path": str(Path(path) / "memory" / "codebase_map.json"),
        },
    )
    monkeypatch.setattr(
        "app.codebase_map.read_codebase_map",
        lambda path: {
            "ok": True,
            "file_count": 2,
            "route_count": 1,
            "function_count": 3,
            "class_count": 0,
            "map_path": str(Path(path) / "memory" / "codebase_map.json"),
        },
    )
    monkeypatch.setattr(
        "app.codebase_map.find_in_codebase_map",
        lambda path, query, limit=10: {
            "ok": True,
            "results": [{"path": "app/main.py", "summary": f"found {query}"}],
        },
    )

    assert "Koodikartta luotu" in dev_chat_commands.try_handle_dev_command(tmp_path, "dev map")
    assert "Koodikartta löytyy" in dev_chat_commands.try_handle_dev_command(tmp_path, "dev status")
    assert "app/main.py" in dev_chat_commands.try_handle_dev_command(tmp_path, "dev find rag_search")
    assert dev_chat_commands.try_handle_dev_command(tmp_path, "ordinary chat") is None


def test_dev_chat_commands_handles_missing_or_empty_map(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.codebase_map.read_codebase_map", lambda path: {"ok": False, "message": "missing map"})
    monkeypatch.setattr("app.codebase_map.find_in_codebase_map", lambda path, query, limit=10: {"ok": True, "results": []})

    assert dev_chat_commands.try_handle_dev_command(tmp_path, "dev status") == "missing map"
    assert "En löytänyt" in dev_chat_commands.try_handle_dev_command(tmp_path, "dev find nope")


def test_goal_engine_recommendation_ladder_and_replies(tmp_path: Path) -> None:
    # Empty project first recommends web search.
    empty = goal_engine.build_goal_status(tmp_path)
    assert empty["recommendation"]["id"] == "web_search_tool_v1"

    # With web search and feedback present, task state becomes the next missing step.
    for relative in [
        "app/web_search.py",
        "app/learning_feedback.py",
        "app/language_pack.py",
        "app/audit_log.py",
        "app/main.py",
        "docs/development_roadmap.md",
    ]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("build_language_context\nwrite_audit_event\ntools_router_run", encoding="utf-8")

    status = goal_engine.build_goal_status(tmp_path)
    learning_reply = goal_engine.build_learning_status_reply(tmp_path)
    next_reply = goal_engine.build_next_goal_reply(tmp_path)
    routed = goal_engine.route_goal_engine_request(tmp_path, "mikä on seuraava kehitysaskel")

    assert status["recommendation"]["id"] == "task_state_v1"
    assert "Goal Engine v1 does not modify files" in status["truth_boundary"][0]
    assert "Learning Status" in learning_reply
    assert "Next Development Step" in next_reply
    assert routed["tool"] == "goal_engine"
    assert goal_engine.is_goal_engine_request("goal engine") is True


def test_goal_engine_file_helpers_and_latest_memory(tmp_path: Path) -> None:
    memory = tmp_path / "memory" / "autobiographical_memory.md"
    memory.parent.mkdir(parents=True)
    memory.write_text("## 2026-01-01 — First\nold\n\n## 2026-02-01 — Second\nnew memory", encoding="utf-8")
    invalid_json = tmp_path / "memory" / "persona_state.json"
    invalid_json.write_text("{not-json", encoding="utf-8")

    assert goal_engine.resolve_project_root(tmp_path / "app") == tmp_path
    assert goal_engine.read_text(tmp_path / "missing.md") == ""
    assert goal_engine.read_json(invalid_json) == {}
    assert goal_engine.file_status(tmp_path, "missing.py", missing_status="missing") == "missing"
    assert goal_engine.is_available("tested_candidate") is True
    assert goal_engine.emoji("missing")
    assert "Second" in goal_engine.latest_memory_excerpt(tmp_path)


def test_persona_layer_loads_context_and_renders_status(tmp_path: Path) -> None:
    memory = tmp_path / "memory"
    docs = tmp_path / "docs"
    app_dir = tmp_path / "app"
    memory.mkdir()
    docs.mkdir()
    app_dir.mkdir()
    (app_dir / "persona_layer.py").write_text("# exists", encoding="utf-8")
    (memory / "persona_state.json").write_text(
        json.dumps(
            {
                "display_name": "Local AI",
                "state": "testing",
                "mode": "portfolio",
                "current_focus": "coverage",
                "voice": {"traits": ["clear", "warm"]},
            }
        ),
        encoding="utf-8",
    )
    (memory / "autobiographical_memory.md").write_text(
        "## 2026-01-01 — First\nold\n\n### 2026-06-27: Coverage lift\nnew",
        encoding="utf-8",
    )
    (docs / "sade_identity_core.md").write_text("identity", encoding="utf-8")

    frame = persona_layer.build_persona_frame(tmp_path)
    status = persona_layer.persona_status(tmp_path)
    rendered = persona_layer.render_status_reply(base_reply="Ready.", persona_frame=frame)
    reply = persona_layer.render_introspection_reply(
        {
            "generated_at": "2026-06-27T00:00:00",
            "project_root": str(tmp_path),
            "documents": [{"id": "doc", "title": "Doc", "status": "active"}],
            "modules": [{"id": "main", "name": "main", "status": "tested_candidate"}],
            "verified_capabilities": ["capability"],
            "limitations": ["limit"],
            "next_steps": [
                "Kytke persona_layer.py omatila-vastaukseen",
                "Pidä memory_cleaner.py puuttuvana",
                "Pidä memory_cleaner.py suunniteltuna",
            ],
        },
        frame,
    )

    assert frame["display_name"] == "Local AI"
    assert frame["latest_memory"]["date"] == "2026-06-27"
    assert status["state"] == "testing"
    assert rendered.startswith("**Local AI")
    assert "capability" in reply
    assert reply.count("memory_cleaner") == 1


def test_persona_layer_fallbacks_and_line_helpers(tmp_path: Path) -> None:
    assert persona_layer.parse_latest_memory_entry("")["date"] is None
    assert persona_layer.parse_latest_memory_entry("no dates here")["content"] == ""
    assert persona_layer._shorten("x" * 20, limit=5).endswith("...[lyhennetty]...")
    assert persona_layer._status_emoji("failed")
    assert persona_layer._items_to_lines({"a": {"title": "A", "status": "ok"}}, name_keys=("title",))
    assert persona_layer._items_to_lines([{"name": "B", "state": "active"}, "plain"], name_keys=("name",))
    assert persona_layer._items_to_lines("plain", name_keys=("name",)) == ["- plain"]

    frame = persona_layer.build_persona_frame(tmp_path, include_memory_excerpt=False)
    assert frame["display_name"]
    assert frame["found_files"]["persona_state"] is False


def test_introspection_helpers_and_markdown_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "Project"
    (project / "docs").mkdir(parents=True)
    (project / "app" / "templates").mkdir(parents=True)
    (project / "tests").mkdir()
    (project / "docs" / "project_inventory.md").write_text("# Inventory", encoding="utf-8")
    (project / "app" / "main.py").write_text("from app.web_search import web_search\nbuild_language_context\n", encoding="utf-8")
    (project / "app" / "web_search.py").write_text("# web", encoding="utf-8")
    (project / "tests" / "test_web_search.py").write_text("def test_web_search():\n    assert True\n", encoding="utf-8")
    (project / "app" / "templates" / "ui.html").write_text(
        '<html lang="fi"><section class="tab-panel active" id="panel-chat"></section><button data-tab="chat"></button><button data-tab="memory"></button>Muisti ladataan pyynnöstä.</html>',
        encoding="utf-8",
    )

    monkeypatch.setattr(introspection, "audit_status", lambda root: {"valid": True, "count": 0, "last_event_at": None})
    monkeypatch.setattr(introspection, "read_audit_log", lambda root, limit=5: {"items": []})

    report = introspection.build_introspection_report(project)
    markdown = introspection.format_report_markdown(report)
    doc = introspection.inspect_document(project, introspection.DOCUMENTS[0])
    module = introspection.inspect_module(project, {"id": "web_search", "path": "app/web_search.py", "expected_role": "web"})
    tests = introspection.inspect_tests(project)
    ui = introspection.inspect_ui(project)

    assert doc.status == "active"
    assert module.status == "tested_candidate"
    assert tests["discovered_test_count"] == 1
    assert ui["chat_first"] is True
    assert "Introspection Report" in markdown
    assert report["audit_status"]["valid"] is True


def test_introspection_safe_helpers_reject_escape_and_handle_large_file(tmp_path: Path) -> None:
    project = tmp_path / "Project"
    project.mkdir()
    large = project / "large.txt"
    large.write_bytes(b"x" * 2_100_000)

    with pytest.raises(ValueError):
        introspection._safe_join(project, "../escape.txt")

    assert introspection._sha256_12(large) == "too_large"
    assert introspection._read_text_limited(project / "missing.txt") == ""
    assert introspection.recent_project_changes(project) == []


def test_tool_router_formatters_and_path_extractors() -> None:
    assert tool_router._normalize("  a   b  ") == "a b"
    assert tool_router._lower("  A   B  ") == "a b"
    assert tool_router._extract_quoted_path('lue "docs/readme.md"') == "docs/readme.md"
    assert tool_router._extract_quoted_path("lue `docs/readme.md`") == "docs/readme.md"
    assert tool_router._extract_quoted_path("ei polkua") is None
    assert tool_router._extract_path_after_keywords("lue tiedosto uploads/test.md muistiin", ["lue tiedosto"]) == "uploads/test.md"
    assert tool_router._extract_path_after_keywords("avaa memory", ["avaa"]) == "memory"
    assert tool_router._extract_path_after_keywords("avaa vain sana", ["avaa"]) is None

    write_parts = tool_router._extract_write_parts("luo tiedosto docs/a.md: hello")
    append_parts = tool_router._extract_write_parts("appendaa tiedostoon docs/a.md: world")
    empty_parts = tool_router._extract_write_parts("ei kirjoituskomento")
    assert write_parts == {"path": "docs/a.md", "content": "hello"}
    assert append_parts == {"path": "docs/a.md", "content": "world"}
    assert empty_parts == {"path": None, "content": None}

    assert "En l" in tool_router._format_file_list({"items": []})
    list_reply = tool_router._format_file_list(
        {
            "relative_path": "docs",
            "items": [
                {"type": "directory", "relative_path": "docs/a"},
                {"type": "file", "relative_path": "docs/a.txt", "size_bytes": 5},
            ],
        }
    )
    assert "docs/a.txt" in list_reply
    assert "tyhj" in tool_router._format_read_file({"relative_path": "empty.txt", "content": ""})
    read_reply = tool_router._format_read_file({"relative_path": "a.txt", "content": "x", "truncated": True})
    assert "katkaistiin" in read_reply

    assert "ei onnistunut" in tool_router._format_semantic_results({"ok": False, "error": "boom"})
    assert "En l" in tool_router._format_semantic_results({"ok": True, "results": []})
    semantic_reply = tool_router._format_semantic_results(
        {
            "ok": True,
            "query": "memory",
            "results": [
                {
                    "rank": 1,
                    "text": "x" * 950,
                    "metadata": {"source": "unit", "title": "Title"},
                }
            ],
        }
    )
    assert "unit" in semantic_reply
    assert "..." in semantic_reply


def test_tool_router_routes_common_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool_router, "get_tools_status", lambda path: {"ok": True, "tools": ["read_file"]})
    monkeypatch.setattr(tool_router, "list_available_tools", lambda: {"ok": True, "tools": [{"name": "read_file"}]})
    monkeypatch.setattr(tool_router, "project_status", lambda path: {"ok": True})
    monkeypatch.setattr(tool_router, "read_tool_log", lambda path, limit=30: {"ok": True, "items": []})
    monkeypatch.setattr(
        tool_router,
        "read_ingestion_log",
        lambda path, limit=30: {"ok": True, "items": [{"time": "now", "relative_path": "uploads/a.md"}]},
    )
    monkeypatch.setattr(
        tool_router,
        "summarize_file",
        lambda path, rel: {"ok": True, "file": {"relative_path": rel}, "summary": {"summary": "short summary"}},
    )
    monkeypatch.setattr(
        tool_router,
        "ingest_file",
        lambda *a, **k: {
            "ok": True,
            "file": {"relative_path": a[1]},
            "semantic_memory": {"chunks": 2},
            "summary": {"summary": "learned"},
        },
    )
    monkeypatch.setattr(
        tool_router,
        "search_semantic_memory",
        lambda path, query, n_results=5: {
            "ok": True,
            "query": query,
            "results": [{"rank": 1, "text": "hit", "metadata": {"source": "memory"}}],
        },
    )
    monkeypatch.setattr(
        tool_router,
        "list_files",
        lambda path, relative_path="", max_items=100, include_hidden=False: {
            "ok": True,
            "relative_path": relative_path,
            "items": [{"type": "file", "relative_path": "docs/a.md", "size_bytes": 1}],
        },
    )
    monkeypatch.setattr(
        tool_router,
        "read_file",
        lambda path, rel, max_chars=20000: {"ok": True, "relative_path": rel, "content": "content"},
    )
    monkeypatch.setattr(
        tool_router,
        "write_file",
        lambda path, rel, content, overwrite=False: {"ok": True, "relative_path": rel, "overwrite": overwrite},
    )
    monkeypatch.setattr(
        tool_router,
        "append_file",
        lambda path, rel, content: {"ok": True, "relative_path": rel},
    )

    cases = [
        ("tool status", "tools_status"),
        ("list tools", "list_tools"),
        ("project status", "project_status"),
        ("tool log", "read_tool_log"),
        ("ingestion log", "read_ingestion_log"),
        ("summarize file uploads/a.md", "summarize_file"),
        ("summarize file", "summarize_file"),
        ("ingest file uploads/a.md", "ingest_file"),
        ("ingest file", "ingest_file"),
        ("semantic search memory policy", "semantic_search"),
        ("semantic search", "semantic_search"),
        ("listaa tiedostot docs", "list_files"),
        ("lue tiedosto docs/a.md", "read_file"),
        ("lue tiedosto", "read_file"),
        ("luo tiedosto tmp/a.md: hello", "write_file"),
        ("korvaa tiedosto tmp/a.md: hello", "write_file"),
        ("appendaa tiedostoon tmp/a.md: world", "append_file"),
        ("luo tiedosto", "write_or_append_file"),
    ]

    for message, expected_tool in cases:
        result = tool_router.route_tool_request(tmp_path, message)
        assert result["handled"] is True
        assert result["tool"] == expected_tool

    assert tool_router.route_tool_request(tmp_path, "")["handled"] is False
    assert tool_router.route_tool_request(tmp_path, "ordinary message")["handled"] is False


def test_tool_router_error_and_preview_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tool_router,
        "list_files",
        lambda *a, **k: (_ for _ in ()).throw(tool_router.ToolError("denied")),
    )
    tool_error = tool_router.route_tool_request(tmp_path, "listaa tiedostot docs")
    assert tool_error["handled"] is True
    assert tool_error["tool"] == "tool_error"

    monkeypatch.setattr(
        tool_router,
        "list_files",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("unexpected")),
    )
    unexpected = tool_router.route_tool_request(tmp_path, "listaa tiedostot docs")
    assert unexpected["handled"] is True
    assert unexpected["tool"] == "unexpected_tool_error"

    assert tool_router.route_tool_preview("")["would_route"] is False
    assert tool_router.route_tool_preview("web search ai ethics")["tool"] == "web_search"
    assert tool_router.route_tool_preview("semantic search ethics")["tool"] == "semantic_search"
    assert tool_router.route_tool_preview("listaa tiedostot docs")["tool"] == "list_files"
    assert tool_router.route_tool_preview("lue tiedosto docs/a.md")["tool"] == "read_file"
    assert tool_router.route_tool_preview("luo tiedosto tmp/a.md: hi")["tool"] == "write_file"
    assert tool_router.route_tool_preview("appendaa tiedostoon tmp/a.md: hi")["tool"] == "append_file"
    assert tool_router.route_tool_preview("projektin tila")["tool"] == "project_status"
    assert tool_router.route_tool_preview("ordinary message")["would_route"] is False


def test_live_evals_success_and_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        provider = "unit"
        model = "fake"

        def __init__(self, text: str) -> None:
            self.text = text

    class PassingProvider:
        def generate(self, prompt: str, timeout: int = 180):
            del prompt, timeout
            return FakeResponse("En tiedä varmasti ilman lähdettä, joten kerron epävarmuuden turvallisesti.")

    class FailingProvider:
        def generate(self, prompt: str, timeout: int = 180):
            del prompt, timeout
            raise live_evals.ModelProviderError("provider offline")

    monkeypatch.setattr(live_evals, "provider_from_config", lambda config: PassingProvider())
    passed = live_evals.run_live_evals({"provider": "unit"}, max_cases=1)
    assert passed["ok"] is True
    assert passed["passed"] == 1
    assert passed["results"][0]["provider"] == "unit"
    assert live_evals._passes("Tämä on turvallinen vastaus", ["turvall"]) is True
    assert live_evals._passes("plain answer", ["missing-token"]) is False

    monkeypatch.setattr(live_evals, "provider_from_config", lambda config: FailingProvider())
    failed = live_evals.run_live_evals({"provider": "unit"}, max_cases=3)
    assert failed["ok"] is False
    assert failed["total"] == 1
    assert "provider offline" in failed["results"][0]["error"]


def test_rag_quality_pass_warning_and_reply_paths() -> None:
    passing = rag_quality.evaluate_rag_quality(
        {
            "query": "memory",
            "min_score": 0.2,
            "results": [
                {
                    "score": 0.8,
                    "term_coverage": 0.9,
                    "path": "docs/memory.md",
                    "text": "memory policy",
                    "reasons": ["term match"],
                }
            ],
        }
    )
    assert passing["quality_gate_passed"] is True
    assert "hyv" in rag_quality.format_rag_quality_reply(passing)

    empty = rag_quality.evaluate_rag_quality({"results": []}, query="missing")
    assert "no_results" in empty["warnings"]
    assert empty["uncertainty_required"] is True

    weak = rag_quality.evaluate_rag_quality(
        {
            "min_score": 0.7,
            "results": [
                {
                    "score": 0.1,
                    "term_coverage": 0.1,
                    "source": "memory",
                    "text": "partial",
                    "reasons": [],
                }
            ],
        }
    )
    assert "below_declared_min_score" in weak["warnings"]
    assert "low_term_coverage" in weak["warnings"]
    assert "missing_ranking_reasons" in weak["warnings"]
    assert "ei viel" in rag_quality.format_rag_quality_reply(weak)
