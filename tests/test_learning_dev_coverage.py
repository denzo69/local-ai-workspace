from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import autonomous_learning as al
from app import dev_chat_commands as dc
from app import learning_review as lr


def test_dev_chat_commands_build_read_find_and_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    app_dir.mkdir()

    monkeypatch.setattr(
        "app.codebase_map.build_codebase_map",
        lambda project_path, include_snippets=False: {
            "file_count": 2,
            "route_count": 1,
            "function_count": 3,
            "class_count": 1,
            "map_path": str(project_path / "memory" / "codebase_map.json"),
        },
    )
    created = dc.try_handle_dev_command(tmp_path, "Tee koodikartta")
    assert created is not None
    assert "Koodikartta luotu" in created
    assert "Tiedostot: 2" in created

    monkeypatch.setattr(
        "app.codebase_map.read_codebase_map",
        lambda project_path: {"ok": False, "message": "missing map"},
    )
    assert dc.try_handle_dev_command(tmp_path, "näytä koodikartta") == "missing map"

    monkeypatch.setattr(
        "app.codebase_map.read_codebase_map",
        lambda project_path: {
            "ok": True,
            "file_count": 5,
            "route_count": 2,
            "function_count": 9,
            "class_count": 4,
            "map_path": "map.json",
        },
    )
    status = dc.try_handle_dev_command(tmp_path, "dev status")
    assert status is not None
    assert "Koodikartta löytyy" in status
    assert "Funktiot: 9" in status

    assert dc.try_handle_dev_command(tmp_path, "dev find   ") == "Anna hakusana, esim. `etsi koodista rag_search`."

    monkeypatch.setattr(
        "app.codebase_map.find_in_codebase_map",
        lambda project_path, query, limit=10: {"ok": False, "message": "search failed"},
    )
    assert dc.try_handle_dev_command(tmp_path, "dev find router") == "search failed"

    monkeypatch.setattr(
        "app.codebase_map.find_in_codebase_map",
        lambda project_path, query, limit=10: {"ok": True, "results": []},
    )
    assert "En löytänyt" in dc.try_handle_dev_command(tmp_path, "dev find missing")

    monkeypatch.setattr(
        "app.codebase_map.find_in_codebase_map",
        lambda project_path, query, limit=10: {
            "ok": True,
            "results": [
                {"path": "app/main.py", "summary": "route match"},
                {"file": "app/tool_router.py", "matches": ["tool"]},
            ],
        },
    )
    found = dc.try_handle_dev_command(tmp_path, "etsi koodista tool")
    assert found is not None
    assert "2 osumaa" in found
    assert "app/main.py" in found
    assert "route match" in found
    assert dc.try_handle_dev_command(tmp_path, "ei dev-komento") is None


def test_autonomous_learning_scan_logs_and_duplicates(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    good = uploads / "note.md"
    good.write_text("# Note\nRAG and FastAPI", encoding="utf-8")
    binary = uploads / "image.bin"
    binary.write_text("binary", encoding="utf-8")
    backup = uploads / "old_backup_file.md"
    backup.write_text("skip", encoding="utf-8")
    pycache = uploads / "__pycache__"
    pycache.mkdir()
    (pycache / "cached.py").write_text("skip", encoding="utf-8")

    outside = tmp_path.parent / "outside-learning.txt"
    outside.write_text("outside", encoding="utf-8")
    assert al._should_skip(outside, tmp_path) is True
    assert al._should_skip(backup, tmp_path) is True

    first_scan = al.scan_uploads_for_learning(tmp_path, limit=10)
    assert first_scan["ok"] is True
    assert first_scan["candidate_count"] == 1
    assert first_scan["candidates"][0]["relative_path"] == "uploads/note.md"
    assert any(item["reason"].startswith("unsupported_extension") for item in first_scan["skipped"])
    assert any(item["reason"] == "blocked_path" for item in first_scan["skipped"])

    candidate = first_scan["candidates"][0]
    al._append_jsonl(
        al._ingestion_log_path(tmp_path),
        {"relative_path": candidate["relative_path"], "sha256": candidate["sha256"]},
    )
    duplicate_scan = al.scan_uploads_for_learning(tmp_path, include_already_ingested=False)
    assert duplicate_scan["candidate_count"] == 0
    assert duplicate_scan["skipped"][0]["reason"] == "already_ingested"

    included_scan = al.scan_uploads_for_learning(tmp_path, include_already_ingested=True)
    assert included_scan["candidate_count"] == 1
    assert included_scan["candidates"][0]["already_ingested"] is True

    log = al._read_ingestion_log(tmp_path)
    assert candidate["sha256"] in log["hashes"]
    assert candidate["relative_path"] in log["paths"]


def test_autonomous_learning_loop_status_and_log(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "first.md").write_text("First document", encoding="utf-8")
    (uploads / "second.md").write_text("Second document", encoding="utf-8")

    def fake_ingest(project_path: Path, relative_path: str, **kwargs):
        if relative_path.endswith("second.md"):
            raise RuntimeError("ingest failed")
        return {"ok": True, "summary": {"summary": "learned"}, "semantic_memory": {"chunks": 2}}

    monkeypatch.setattr(al, "ingest_file", fake_ingest)
    result = al.run_autonomous_learning_loop(tmp_path, max_files=5, add_to_memory=False, add_to_semantic=True)
    assert result["ok"] is True
    assert result["learned_count"] == 1
    assert result["failed_count"] == 1
    assert result["learned"][0]["summary"] == "learned"
    assert result["failed"][0]["error"] == "ingest failed"

    status = al.get_learning_status(tmp_path)
    assert status["ok"] is True
    assert status["learning_events"] >= 3
    assert ".md" in status["supported_extensions"]

    learning_log = al.read_learning_log(tmp_path, limit=10)
    assert learning_log["count"] >= 3

    al._learning_log_path(tmp_path).write_text("not-json\n", encoding="utf-8")
    parsed = al.read_learning_log(tmp_path, limit=1)
    assert parsed["items"][0]["event"] == "parse_error"

    empty_root = tmp_path / "empty"
    assert al.read_learning_log(empty_root)["items"] == []


def test_learning_review_helpers_safe_paths_and_review_creation(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    source = uploads / "agent_notes.md"
    source.write_text(
        "# RAG Architecture\n"
        "- FastAPI endpoint uses Python and Pydantic validation.\n"
        "- Guardrails and approval flow keep write permission safe.\n"
        "This document explains semantic memory, embeddings, tool router and autonomous learning loop in enough detail.",
        encoding="utf-8",
    )
    blocked = uploads / "learning_reviews.md"
    blocked.write_text("blocked", encoding="utf-8")
    unsupported = uploads / "binary.exe"
    unsupported.write_text("no", encoding="utf-8")

    assert lr._relative(tmp_path, source) == "uploads/agent_notes.md"
    assert lr._safe_file_path(tmp_path, "uploads/agent_notes.md") == source.resolve()
    with pytest.raises(ValueError):
        lr._safe_file_path(tmp_path, "../outside.md")
    with pytest.raises(FileNotFoundError):
        lr._safe_file_path(tmp_path, "uploads/missing.md")
    with pytest.raises(ValueError):
        lr._safe_file_path(tmp_path, "uploads")
    with pytest.raises(ValueError):
        lr._safe_file_path(tmp_path, "uploads/learning_reviews.md")
    with pytest.raises(ValueError):
        lr._safe_file_path(tmp_path, "uploads/binary.exe")

    text = source.read_text(encoding="utf-8")
    assert "RAG Architecture" in lr._headings(text)
    assert lr._bullet_points(text)
    assert lr._sentence_candidates(text)
    terms = lr._extract_terms(text)
    assert "rag" in terms
    assert "fastapi" in terms
    assert lr._project_relevance([], "misc.txt") == ["Tämä täydentää Säde v1:n muistia ja voi toimia myöhemmin RAG-kontekstina."]
    assert lr._future_tasks([], "misc.txt") == ["Käytä tätä tiedostoa myöhemmin muistihakujen ja vastausten kontekstina."]
    assert lr._remember_later([], []) == ["Tämä tiedosto on osa Säteen atlas-tietopohjaa ja täydentää myöhempää muistihakua."]

    created = lr.create_learning_review_for_file(tmp_path, "uploads/agent_notes.md")
    assert created["ok"] is True
    assert created["already_exists"] is False
    review = created["review"]
    assert review["relative_path"] == "uploads/agent_notes.md"
    assert "rag" in review["terms"]
    assert "Learning Review" in review["markdown"]

    duplicate = lr.create_learning_review_for_file(tmp_path, "uploads/agent_notes.md")
    assert duplicate["already_exists"] is True

    forced = lr.create_learning_review_for_file(tmp_path, "uploads/agent_notes.md", force=True)
    assert forced["already_exists"] is False

    reviews = lr.read_learning_reviews(tmp_path, limit=10)
    assert reviews["total"] >= 2
    status = lr.get_learning_review_status(tmp_path)
    assert status["reviews_md_exists"] is True
    assert status["reviews_log_exists"] is True


def test_learning_review_recent_candidates_created_skipped_and_failed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "a.md").write_text("# A\nFastAPI and RAG content with enough sentence length for review generation.", encoding="utf-8")
    (uploads / "b.md").write_text("# B\nTool router and guardrails content with enough sentence length for review generation.", encoding="utf-8")
    (uploads / "bad.md").write_text("# Bad\nwill fail", encoding="utf-8")

    lr._append_jsonl(lr._learning_log_path(tmp_path), {"event": "bad-json-holder"})
    with lr._learning_log_path(tmp_path).open("a", encoding="utf-8") as handle:
        handle.write("not-json\n")
        handle.write(json.dumps({"event": "file_learned", "relative_path": "uploads/a.md"}) + "\n")
        handle.write(json.dumps({"event": "file_learned", "relative_path": "uploads/b.md"}) + "\n")
        handle.write(json.dumps({"event": "file_learned", "relative_path": "uploads/b.md"}) + "\n")

    candidates = lr._candidate_paths_from_learning_log(tmp_path, limit=10)
    assert candidates == ["uploads/a.md", "uploads/b.md"]

    first = lr.create_reviews_for_recent_learning(tmp_path, max_files=5)
    assert first["created_count"] == 2

    second = lr.create_reviews_for_recent_learning(tmp_path, max_files=5)
    assert second["skipped_count"] == 2

    monkeypatch.setattr(lr, "_candidate_paths_from_learning_log", lambda project_path, limit=50: ["uploads/a.md", "uploads/bad.md"])
    original = lr.create_learning_review_for_file

    def fake_create(project_path: Path, relative_path: str, force: bool = False):
        if relative_path.endswith("bad.md"):
            raise RuntimeError("review failed")
        return original(project_path, relative_path, force=True)

    monkeypatch.setattr(lr, "create_learning_review_for_file", fake_create)
    mixed = lr.create_reviews_for_recent_learning(tmp_path, max_files=5, force=True)
    assert mixed["created_count"] == 1
    assert mixed["failed_count"] == 1
    assert mixed["failed"][0]["error"] == "review failed"

    no_log_root = tmp_path / "no-log"
    (no_log_root / "uploads").mkdir(parents=True)
    (no_log_root / "uploads" / "fallback.md").write_text("# Fallback\nRAG content for fallback candidate.", encoding="utf-8")
    assert lr._candidate_paths_from_learning_log(no_log_root, limit=5) == ["uploads/fallback.md"]
