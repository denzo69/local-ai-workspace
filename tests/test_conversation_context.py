from __future__ import annotations

from pathlib import Path

from app.conversation_context import (
    build_contextual_query,
    extract_conversation_context,
    is_followup_question,
)
from app.debug_trace import summarize_latest_trace, write_trace


def test_extract_conversation_context_from_visible_chat_only() -> None:
    chat = """
User: Kerrotko ohjeen torttutaikinaan
Assistant: Torttutaikina tehdään kylmistä aineksista.
User: Kiitos. Mikä olisi hyvä täyte siihen?
Assistant: Luumu, omena ja suolaiset täytteet sopivat.
"""
    context = extract_conversation_context(chat, latest_message="Entä voiko siihen laittaa omenaa?")

    assert context.domain == "food"
    assert "täyte" in context.topic.lower() or "torttu" in context.summary.lower()
    assert context.confidence >= 0.5


def test_contextual_query_adds_recent_place_and_domain_for_followup() -> None:
    chat = """
User: Autohuollot Lieksassa
Assistant: Löysin lähteitä autohuolloista Lieksassa.
"""
    context = extract_conversation_context(chat, latest_message="Mikä niistä olisi lähin?")
    query = build_contextual_query("Mikä niistä olisi lähin?", context)

    assert "Lieksa" in query
    assert "local services" in query
    assert "Autohuollot" in query or "autohuol" in query.lower()


def test_followup_detection_is_broad_but_small() -> None:
    assert is_followup_question("Entä mikä niistä on lähin?") is True
    assert is_followup_question("Miten se toimii?") is True
    assert is_followup_question("Selitä lyhyesti DNA") is False


def test_debug_trace_summary_exposes_operational_route_without_paths(tmp_path: Path) -> None:
    write_trace(
        tmp_path,
        event="chat_intent_planned",
        user_message="Autohuollot Lieksassa",
        route="intent_planner",
        decision="current_external_information",
        details={"intent": "current_external_information", "needs_web": True},
    )
    write_trace(
        tmp_path,
        event="conversation_context_used",
        user_message="Mikä niistä on lähin?",
        route="conversation_context",
        decision="enriched_query",
        details={
            "route_used": "web_search",
            "search_query": "Mikä niistä on lähin? Lieksa local services Autohuollot Lieksassa",
            "conversation_context": {"location": "Lieksa", "domain": "local_services"},
        },
    )
    write_trace(
        tmp_path,
        event="web_search_executed",
        user_message="Mikä niistä on lähin?",
        route="web_search",
        decision="searched",
        details={"sources_found": 4, "query": "autohuollot lieksa"},
    )

    summary = summarize_latest_trace(tmp_path)

    assert summary["ok"] is True
    assert summary["route_used"] == "web_search"
    assert summary["intent"] == "current_external_information"
    assert summary["sources_found"] == 4
    assert summary["conversation_context"]["location"] == "Lieksa"
    assert "C:\\" not in str(summary)
