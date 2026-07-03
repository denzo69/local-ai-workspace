from __future__ import annotations

from pathlib import Path

import pytest

from app import rag_engine, semantic_memory, tool_router, web_search


def test_web_search_parses_duckduckgo_lite_results_without_network() -> None:
    html = """
    <html><body>
      <a href="/l/?kh=-1&uddg=https%3A%2F%2Fexample.com%2Farticle">Example Article</a>
      <a href="https://duckduckgo.com/html/">Noise</a>
      <a href="https://www.python.org/doc/">Python Docs</a>
    </body></html>
    """

    parser = web_search.DuckDuckGoLiteParser()
    parser.feed(html)

    assert [item.title for item in parser.results] == ["Example Article", "Python Docs"]
    assert parser.results[0].url == "https://example.com/article"
    assert parser.results[0].source == "example.com"
    assert parser.results[1].rank == 2


def test_web_search_intent_helpers_and_truthful_failure_reply() -> None:
    assert web_search.slugify("AI ethics 2026!") == "ai-ethics-2026"
    assert web_search.extract_web_query("hae verkosta Pielinen kalalajit") == "Pielinen kalalajit"
    assert web_search.is_explicit_web_search_request("Voitko hakea verkosta tämän?")
    assert web_search.is_web_search_status_request("toimiiko verkkohaku")
    assert web_search.is_web_search_trial_request("kokeillaan verkkohakua")
    assert web_search.is_source_review_request("tarkista lähteet")
    assert web_search.is_automatic_web_search_request("Nurmeksen terveyskeskuksen yhteystiedot")
    assert not web_search.is_automatic_web_search_request("Mika on riittava maara unta yolla?")

    reply = web_search.format_web_search_reply(
        {"ok": False, "query": "testi", "provider": "duckduckgo_lite", "error": "offline"}
    )

    assert "Verkkohaku ei onnistunut" in reply
    assert "En väitä tietoa haetuksi" in reply


def test_web_search_pending_state_roundtrip(tmp_path: Path) -> None:
    started = web_search.start_pending_web_search(tmp_path)

    assert started["ok"] is True
    assert web_search.consume_pending_web_search(tmp_path, "tekoälyn etiikka") is True
    assert web_search.consume_pending_web_search(tmp_path, "toinen haku") is False


def test_rag_candidate_scoring_deduping_and_formatting() -> None:
    candidate = rag_engine.RagCandidate(
        source_type="operating_manual",
        source="sade_operating_manual.md",
        path="docs/sade_operating_manual.md",
        title="Sade Operating Manual",
        text="Operating manual explains memory policy and tool permission boundaries.",
    )

    scored = rag_engine._score_candidate(candidate, "operating manual memory policy")

    assert scored.score >= 90
    assert scored.term_coverage >= 0.75
    assert any(reason.startswith("source_priority") for reason in scored.reasons)
    assert rag_engine._passes_relevance_gate(scored, "operating manual memory policy")

    duplicate = rag_engine.RagCandidate(
        source_type="project_doc",
        source="copy.md",
        path="docs/copy.md",
        title="Sade Operating Manual",
        text=candidate.text,
    )
    assert len(rag_engine._dedupe_candidates([candidate, duplicate])) == 1

    result = {
        "ok": True,
        "query": "operating manual memory policy",
        "version": "test",
        "query_terms": ["operating", "manual", "memory", "policy"],
        "results": [scored.to_dict(1)],
    }
    reply = rag_engine.format_rag_search_reply(result, max_item_chars=80)

    assert "Löysin RAG-haulla" in reply
    assert "Sade Operating Manual" in reply


def test_rag_blocks_legacy_paths_and_handles_empty_context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(rag_engine, "_semantic_candidates", lambda *args, **kwargs: [])
    project = tmp_path
    safe = project / "docs" / "manual.md"
    blocked = project / "app" / "patch_old_fix.py"
    outside = tmp_path.parent / "outside.md"

    assert rag_engine._safe_relative(project, safe) == "docs/manual.md"
    assert rag_engine._is_blocked_path(blocked, project) is True
    assert rag_engine._is_blocked_path(outside, project) is True
    assert "RAG-haku ei" in rag_engine.build_rag_context(project, "no matches", min_score=101)


def test_semantic_memory_fallbacks_without_chromadb(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        semantic_memory,
        "_import_chromadb",
        lambda: (None, None, RuntimeError("chromadb missing")),
    )

    status = semantic_memory.semantic_memory_status(tmp_path)
    search = semantic_memory.search_semantic_memory(tmp_path, "muisti")
    add = semantic_memory.add_text_to_semantic_memory(tmp_path, "muistettava asia")

    assert status["ok"] is False
    assert status["enabled"] is False
    assert search["results"] == []
    assert add["indexed"] is False


def test_semantic_memory_chunking_ids_and_context_formatting() -> None:
    text = "Ensimmäinen kappale.\n\n" + ("Pitkä muistiteksti " * 80)
    chunks = semantic_memory.split_text_to_chunks(text, max_chars=120, overlap_chars=20)

    assert len(chunks) > 2
    assert semantic_memory._stable_id("source", "text", 1) == semantic_memory._stable_id("source", "text", 1)

    context = semantic_memory.format_semantic_context(
        {
            "ok": True,
            "results": [
                {
                    "rank": 1,
                    "distance": 0.12345,
                    "metadata": {"source": "memory.md", "title": "Muisto"},
                    "text": "Tämä on semanttisen muistin sisältö.",
                }
            ],
        },
        max_chars=500,
    )

    assert "memory.md" in context
    assert "0.1235" in context
    assert "semanttisen muistin sisältö" in context


def test_tool_router_preview_and_path_helpers() -> None:
    assert tool_router._extract_quoted_path('lue tiedosto "docs/architecture.md"') == "docs/architecture.md"
    assert tool_router._extract_path_after_keywords("avaa tiedosto docs/architecture.md kiitos", ["avaa tiedosto"]) == "docs/architecture.md"

    write_parts = tool_router._extract_write_parts("kirjoita tiedostoon docs/test.md: Hei Säde")
    assert write_parts == {"path": "docs/test.md", "content": "Hei Säde"}

    assert tool_router.route_tool_preview("web search tekoälyn etiikka")["tool"] == "web_search"
    assert tool_router.route_tool_preview("semantic search muistot")["tool"] == "semantic_search"
    assert tool_router.route_tool_preview("listaa tiedostot docs")["tool"] == "list_files"
    assert tool_router.route_tool_preview("projektin tila")["tool"] == "project_status"
    assert tool_router.route_tool_preview("")["reason"] == "empty_message"


def test_tool_router_resolve_project_path_rejects_escape() -> None:
    inside = tool_router.resolve_project_path("docs/architecture.md")
    assert str(inside).endswith("docs\\architecture.md") or str(inside).endswith("docs/architecture.md")

    with pytest.raises(ValueError):
        tool_router.resolve_project_path("..\\secret.txt")
