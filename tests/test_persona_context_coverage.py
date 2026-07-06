from __future__ import annotations

import json
from pathlib import Path

from app import conversation_context as cc
from app import persona_layer as pl


def test_persona_file_helpers_and_memory_parser(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    assert pl.resolve_project_root(app_dir) == tmp_path

    missing = tmp_path / "missing.md"
    assert pl._read_text(missing) == ""
    assert pl._read_json(missing) == {}

    text_file = tmp_path / "long.md"
    text_file.write_text("abcdefg", encoding="utf-8")
    assert pl._read_text(text_file, max_chars=3).startswith("abc")
    assert "[katkaistu]" in pl._read_text(text_file, max_chars=3)

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not-json", encoding="utf-8")
    assert pl._read_json(bad_json) == {}

    good_json = tmp_path / "good.json"
    good_json.write_text(json.dumps({"name": "Säde"}), encoding="utf-8")
    assert pl._load_first_json(tmp_path, ["missing.json", "good.json"])["data"]["name"] == "Säde"
    assert pl._load_first_text(tmp_path, ["missing.md"])["found"] is False

    memory = """
## 2026-01-01 — First
old content
### 2026-02-03: Latest title
latest content
"""
    latest = pl.parse_latest_memory_entry(memory)
    assert latest["date"] == "2026-02-03"
    assert latest["title"] == "Latest title"
    assert latest["content"] == "latest content"
    assert pl.parse_latest_memory_entry("") == {"date": None, "title": None, "content": ""}
    assert pl.parse_latest_memory_entry("no dated heading") == {"date": None, "title": None, "content": ""}


def test_persona_public_labels_status_lines_and_cleanup(tmp_path: Path) -> None:
    assert pl._public_label("Säde v1 Document Registry") == "Local AI Workspace Document Registry"
    assert pl._public_sentence("Tämä raportti on lukutoiminto eikä muuta tiedostoja.") == "This report is read-only and does not modify files."
    assert pl._shorten("abc", 10) == "abc"
    assert pl._shorten("abcdef", 3).endswith("...[truncated]...")

    assert pl._status_emoji("tested_candidate") == "🧪"
    assert pl._status_emoji("active") == "✅"
    assert pl._status_emoji("missing") == "⚪"
    assert pl._status_emoji("failed") == "⚠️"
    assert pl._status_emoji("other") == "•"

    dict_lines = pl._items_to_lines({"Säde Guardrails": {"status": "active"}}, name_keys=("name",))
    assert "Guardrails" in dict_lines[0]

    list_lines = pl._items_to_lines([{"id": "mod", "state": "tested"}, "plain item"], name_keys=("name", "id"))
    assert "mod" in list_lines[0]
    assert list_lines[1] == "- plain item"
    assert pl._items_to_lines(None, name_keys=("name",)) == []
    assert pl._items_to_lines("raw", name_keys=("name",)) == ["- raw"]

    steps = pl._clean_next_steps([
        "Kytke persona_layer.py omatila-vastaukseen",
        "memory_cleaner next",
        "memory_cleaner next",
        "Keep this",
    ])
    assert steps == ["memory_cleaner next", "Keep this"]

    missing_frame = {"found_files": {}, "project_root": str(tmp_path)}
    assert "missing" in "\n".join(pl._persona_document_lines(missing_frame))
    assert pl._persona_module_lines(missing_frame) == ["- ⚪ **persona_layer** — `missing`"]

    (tmp_path / "app").mkdir(exist_ok=True)
    (tmp_path / "app" / "persona_layer.py").write_text("# placeholder", encoding="utf-8")
    assert pl._persona_module_lines({"project_root": str(tmp_path)}) == ["- ✅ **persona_layer** — `implemented_candidate`"]


def test_persona_frame_rendering_and_status(tmp_path: Path) -> None:
    (tmp_path / "memory").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "persona_layer.py").write_text("# placeholder", encoding="utf-8")
    (tmp_path / "memory" / "persona_state.json").write_text(
        json.dumps(
            {
                "display_name": "Säde",
                "state": "documented",
                "mode": "building",
                "current_focus": "Rakentaa Local AI Workspace:stä muistava, omaääninen ja turvallinen AI-persoonajärjestelmä.",
                "voice": {"traits": ["warm", "careful"]},
                "truth_rules": {"no_overclaiming": True},
                "relationship_to_jani": {"tone": "trusted"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "docs" / "sade_identity_core.md").write_text("identity", encoding="utf-8")
    (tmp_path / "docs" / "self_model_policy.md").write_text("policy", encoding="utf-8")
    (tmp_path / "memory" / "autobiographical_memory.md").write_text(
        "## 2026-07-06 — Säde v1\nMemory excerpt",
        encoding="utf-8",
    )

    frame = pl.build_persona_frame(tmp_path, include_memory_excerpt=True, max_memory_chars=20)
    assert frame["display_name"] == "Local AI Workspace"
    assert frame["voice_traits"] == ["warm", "careful"]
    assert frame["current_focus"].startswith("Build Local AI Workspace")
    assert frame["latest_memory"]["title"] == "Säde v1"
    assert frame["found_files"]["persona_state"] is True

    report = {
        "generated_at": "2026-07-06T12:00:00",
        "project_root": str(tmp_path),
        "documents": [{"title": "Säde Guardrails", "status": "active"}],
        "modules": [{"id": "existing", "name": "module", "status": "ok"}],
        "verified_capabilities": ["Tämä raportti on lukutoiminto eikä muuta tiedostoja."],
        "limitations": ["implemented_candidate ei tarkoita testattua ominaisuutta."],
        "next_steps": ["Keep documenting"],
    }
    reply = pl.render_introspection_reply(report, frame)
    assert "# Self-State — Local AI Workspace" in reply
    assert "Guardrails" in reply
    assert "Autobiographical Memory" in reply
    assert "persona_layer" in reply
    assert "Keep documenting" in reply
    assert "Truth boundary" in reply

    status_reply = pl.render_status_reply(base_reply="Base", persona_frame=frame)
    assert status_reply.startswith("**Local AI Workspace / tila `documented`**")

    status = pl.persona_status(tmp_path)
    assert status["ok"] is True
    assert status["display_name"] == "Local AI Workspace"


def test_persona_frame_handles_list_and_invalid_voice(tmp_path: Path) -> None:
    (tmp_path / "memory").mkdir()
    state_file = tmp_path / "memory" / "persona_state.json"

    state_file.write_text(json.dumps({"name": "Assistant", "voice": ["direct"]}), encoding="utf-8")
    assert pl.build_persona_frame(tmp_path)["voice_traits"] == ["direct"]

    state_file.write_text(json.dumps({"name": "Assistant", "voice": "plain"}), encoding="utf-8")
    assert pl.build_persona_frame(tmp_path)["voice_traits"] == []


def test_conversation_context_parsing_and_query_building() -> None:
    markdown_chat = """
### Jani
Missä on Lieksan apteekki?
### Säde
Vastaan.
### Jani
Entä aukiolo?
"""
    messages = cc._latest_user_messages(markdown_chat)
    assert messages == ["Missä on Lieksan apteekki?", "Entä aukiolo?"]

    plain_chat = "User: Autohuolto Joensuussa Assistant: ok User: Entä lähin? Assistant: ok"
    assert cc._latest_user_messages(plain_chat) == ["Autohuolto Joensuussa", "Entä lähin?"]

    assert cc._canonical_location("Lieksasta") == "Lieksa"
    assert cc._canonical_location("Nurmeksessa") == "Nurmes"
    assert cc._canonical_location("Joensuussa") == "Joensuu"
    assert cc._canonical_location("Kolilla") == "Koli"
    assert cc._canonical_location("Suomessa") == "Suomi"
    assert cc._canonical_location("Kuu") == "Kuu"

    assert cc._keyword_matches("ai development", "ai") is True
    assert cc._keyword_matches("said", "ai") is False
    assert cc._keyword_matches("fastapi project", "fastapi") is True

    context = cc.extract_conversation_context(plain_chat, latest_message="Mikä niistä olisi paras?")
    assert context.location == "Joensuu"
    assert context.domain == "local_services"
    assert context.confidence > 0.9
    assert "Joensuu" in context.summary
    assert context.to_dict()["source"] == "visible_chat"

    assert cc.is_followup_question("Mikä niistä olisi paras?") is True
    assert cc.is_followup_question("Selitä FastAPI") is False

    weak_context = cc.ConversationContext(confidence=0.1, location="Lieksa", domain="project", topic="coverage")
    assert cc.build_contextual_query("Mitä seuraavaksi?", weak_context) == "Mitä seuraavaksi?"

    enriched = cc.build_contextual_query("Entä seuraavaksi?", context)
    assert "Joensuu" in enriched
    assert "local services" in enriched
    assert "Entä lähin" in enriched
