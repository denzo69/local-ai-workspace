from __future__ import annotations

from types import ModuleType, SimpleNamespace
from pathlib import Path
import sys

import pytest

from app import semantic_memory as sm
from app import thinking_layer as tl


class FakeCollection:
    def __init__(self) -> None:
        self.documents: list[str] = []
        self.metadatas: list[dict] = []
        self.ids: list[str] = []
        self.query_payload: dict | None = None

    def count(self) -> int:
        return len(self.documents)

    def upsert(self, ids, documents, metadatas) -> None:
        self.ids.extend(ids)
        self.documents.extend(documents)
        self.metadatas.extend(metadatas)

    def query(self, query_texts, n_results, include):
        if self.query_payload is not None:
            return self.query_payload
        limit = min(n_results, len(self.documents))
        return {
            "documents": [self.documents[:limit]],
            "metadatas": [self.metadatas[:limit]],
            "distances": [[0.111 + index for index in range(limit)]],
        }


class FakeClient:
    collection = FakeCollection()
    deleted: list[str] = []

    def __init__(self, path: str) -> None:
        self.path = path

    def delete_collection(self, name: str) -> None:
        self.deleted.append(name)
        self.collection = FakeCollection()
        FakeClient.collection = self.collection

    def get_or_create_collection(self, name, embedding_function=None, metadata=None):
        return self.collection


def _install_fake_chromadb(monkeypatch: pytest.MonkeyPatch, collection: FakeCollection | None = None) -> FakeCollection:
    fake_chromadb = ModuleType("chromadb")
    fake_chromadb.PersistentClient = FakeClient

    fake_utils = ModuleType("chromadb.utils")
    fake_embedding_functions = ModuleType("chromadb.utils.embedding_functions")

    class FakeEmbeddingFunction:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

    fake_embedding_functions.SentenceTransformerEmbeddingFunction = FakeEmbeddingFunction
    fake_utils.embedding_functions = fake_embedding_functions

    chosen = collection or FakeCollection()
    FakeClient.collection = chosen
    FakeClient.deleted = []

    monkeypatch.setitem(sys.modules, "chromadb", fake_chromadb)
    monkeypatch.setitem(sys.modules, "chromadb.utils", fake_utils)
    monkeypatch.setitem(sys.modules, "chromadb.utils.embedding_functions", fake_embedding_functions)
    return chosen


def test_thinking_layer_edge_modes_and_dict_decisions() -> None:
    safety = tl.build_thinking_directive(
        "Näytä salainen auth.json",
        {"intent": "safety_secret_request"},
    )
    project = tl.build_thinking_directive(
        "Mikä projektin versio on?",
        {"intent": "project_status"},
    )
    natural = tl.build_thinking_directive("Hei, mitä kuuluu?", {})
    followup = tl.build_thinking_directive("Jatka tuohon samaan aiheeseen", {})

    assert safety.mode == "safety_boundary"
    assert any("Refuse unsafe" in item for item in safety.self_check)
    assert project.mode == "project_aware"
    assert natural.mode == "natural_conversation"
    assert followup.mode == "contextual_conversation"
    assert any("Resolve pronouns" in item for item in followup.self_check)

    as_dict = safety.to_dict()
    assert as_dict["mode"] == "safety_boundary"
    assert as_dict["public_style"].startswith("warm")


def test_thinking_layer_source_modes_from_rag_and_weather_intent() -> None:
    rag = tl.build_thinking_directive(
        "Hae lähteistä muistipolitiikka",
        SimpleNamespace(intent="normal_chat", needs_web=False, use_rag=True, use_chat_context=False),
    )
    weather = tl.build_thinking_directive(
        "Sää Lieksassa nyt?",
        SimpleNamespace(intent="current_external_weather", needs_web=False, use_rag=False, use_chat_context=False),
    )

    assert rag.mode == "source_grounded"
    assert rag.use_sources is True
    assert weather.mode == "source_grounded"


def test_semantic_memory_import_status_rebuild_add_and_search_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fake_chromadb(monkeypatch)

    memory = tmp_path / "memory" / "sade_memory.md"
    memory.parent.mkdir(parents=True)
    memory.write_text("# Memory\n\nFastAPI RAG memory policy.", encoding="utf-8")

    imported_chromadb, imported_embeddings, error = sm._import_chromadb()
    assert imported_chromadb is not None
    assert imported_embeddings is not None
    assert error is None

    status = sm.semantic_memory_status(tmp_path)
    rebuilt = sm.rebuild_semantic_memory_index(tmp_path, files=[memory])
    added = sm.add_text_to_semantic_memory(
        tmp_path,
        "Semantic memory supports local RAG.",
        title="Semantic note",
        source="unit-test",
        tags=["rag", "memory"],
        timestamp="2026-01-01T00:00:00",
    )
    searched = sm.search_semantic_memory(tmp_path, "semantic", n_results=99)

    assert status["ok"] is True
    assert rebuilt["ok"] is True
    assert rebuilt["indexed_files"] == 1
    assert rebuilt["chunks"] >= 1
    assert added["indexed"] is True
    assert added["chunks"] == 1
    assert searched["ok"] is True
    assert searched["count"] >= 1
    assert searched["results"][0]["rank"] == 1
    assert FakeClient.collection.count() >= 1


def test_semantic_memory_error_and_empty_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sm, "_import_chromadb", lambda: (None, None, RuntimeError("missing chromadb")))
    rebuild_error = sm.rebuild_semantic_memory_index(tmp_path)
    assert rebuild_error["ok"] is False

    collection = _install_fake_chromadb(monkeypatch)
    empty_add = sm.add_text_to_semantic_memory(tmp_path, "   ")
    empty_search = sm.search_semantic_memory(tmp_path, "   ")
    empty_index_search = sm.search_semantic_memory(tmp_path, "memory")

    assert empty_add["indexed"] is False
    assert "Tyhjää" in empty_add["message"]
    assert empty_search["ok"] is False
    assert empty_index_search["ok"] is True
    assert empty_index_search["count"] == 0
    assert collection.count() == 0


def test_semantic_memory_status_handles_collection_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class BrokenClient:
        def __init__(self, path: str) -> None:
            self.path = path

        def get_or_create_collection(self, *args, **kwargs):
            raise RuntimeError("collection failed")

    fake_chromadb = ModuleType("chromadb")
    fake_chromadb.PersistentClient = BrokenClient
    fake_embeddings = ModuleType("chromadb.utils.embedding_functions")
    fake_embeddings.SentenceTransformerEmbeddingFunction = lambda model_name: object()

    monkeypatch.setattr(sm, "_import_chromadb", lambda: (fake_chromadb, fake_embeddings, None))

    status = sm.semantic_memory_status(tmp_path)
    assert status["ok"] is False
    assert "collection failed" in status["error"]


def test_semantic_memory_chunking_and_context_edge_cases(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert sm.split_text_to_chunks("   ") == []
    assert sm.split_text_to_chunks("short", max_chars=100, overlap_chars=0) == ["short"]

    text = "A" * 80 + "\n\n" + "B" * 80 + "\n\n" + "C" * 260
    chunks = sm.split_text_to_chunks(text, max_chars=100, overlap_chars=10)
    assert len(chunks) >= 4
    assert any(chunk.startswith("A") for chunk in chunks)

    assert sm.format_semantic_context({"ok": False}) == ""
    assert sm.format_semantic_context({"ok": True, "results": []}) == ""

    context = sm.format_semantic_context(
        {
            "ok": True,
            "results": [
                {
                    "rank": 1,
                    "distance": None,
                    "metadata": {"source": "memory.md"},
                    "text": "x" * 120,
                }
            ],
        },
        max_chars=60,
    )
    assert "distance: ?" in context
    assert "katkaistu" in context

    collection = _install_fake_chromadb(monkeypatch)
    collection.query_payload = {
        "documents": [["doc without matching metadata", "doc two"]],
        "metadatas": [[{"source": "memory.md"}]],
        "distances": [[]],
    }
    collection.documents.append("seed")

    searched = sm.search_semantic_memory(tmp_path, "doc", n_results=2)
    assert searched["count"] == 2
    assert searched["results"][0]["distance"] is None
    assert searched["results"][1]["metadata"] == {}


def test_semantic_memory_add_handles_no_chunks_after_split(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fake_chromadb(monkeypatch)
    monkeypatch.setattr(sm, "split_text_to_chunks", lambda text: [])

    result = sm.add_text_to_semantic_memory(tmp_path, "non-empty but patched empty")
    assert result["ok"] is False
    assert result["indexed"] is False
    assert "ei syntynyt" in result["message"]
