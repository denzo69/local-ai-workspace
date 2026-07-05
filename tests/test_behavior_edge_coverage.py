from __future__ import annotations

from datetime import datetime

import pytest

from app.answer_grounding import selected_sources_for_debug, select_grounding, should_allow_web
from app.intent_planner import (
    build_direct_response,
    decide_response_language,
    plan_response,
)
from app.output_validator import (
    generic_answer_for_project_specific_question,
    persona_suppressed,
    safety_overtriggered,
    validate_output,
    validated_reply,
    wrong_source_used,
)


class _GroundingObject:
    def __init__(self, data: dict):
        self._data = data

    def to_dict(self) -> dict:
        return dict(self._data)


class _DecisionObject:
    intent = "project_status_request"
    language = "fi"

    def __init__(self, grounding):
        self.grounding = grounding


def test_direct_responses_cover_english_and_finnish_edges() -> None:
    now = datetime(2026, 7, 4, 12, 30)

    assert "Today is" in build_direct_response(
        plan_response("What day is it today?"), "What day is it today?", now=now
    )
    assert "Tänään" in build_direct_response(
        plan_response("Mikä päivä tänään on?"), "Mikä päivä tänään on?", now=now
    )
    assert "I can answer" in build_direct_response(
        plan_response("What are your permissions?"), "What are your permissions?"
    )
    assert "Local AI Workspace" in build_direct_response(
        plan_response("What is Local AI Workspace?"), "What is Local AI Workspace?"
    )
    assert "Suomessa" in build_direct_response(
        plan_response("Onko Suomessa talvella yleensä lunta?"),
        "Onko Suomessa talvella yleensä lunta?",
    )
    assert "ankkuri" in build_direct_response(
        plan_response("Minkä kokoinen ankkuri 7m veneeseen?"),
        "Minkä kokoinen ankkuri 7m veneeseen?",
    )


def test_language_setting_unknown_value_falls_back_safely() -> None:
    assert decide_response_language("ok", ui_language="fi", response_language="something-strange") == "fi"
    assert decide_response_language("Explain this in English", ui_language="fi", response_language="auto") == "en"


def test_grounding_debug_and_explicit_web_override_edges() -> None:
    grounding = select_grounding("Mikä on API?", plan_response("Mikä on API?"))
    debug = selected_sources_for_debug(grounding)

    assert should_allow_web(grounding) is False
    assert should_allow_web(grounding, explicit_web_requested=True) is True
    assert "web" in debug["rejected_sources"]
    assert debug["grounding_reason"]


def test_grounding_routes_creative_persona_project_and_current_edges() -> None:
    cases = [
        ("Kuvittele Local AI Workspacelle uusi metafora", "creative_imagination"),
        ("Miksi me rakennamme tätä projektia?", "sade_persona"),
        ("Tämänhetkinen hinta sähköauton lataukselle", "external_current_world"),
        ("Mitä oikeuksia minulla on vuokralaisena?", "external_official_or_legal"),
        ("Mikä on projektin tila?", "project_state"),
    ]
    for message, expected_scope in cases:
        grounding = select_grounding(message, plan_response(message))
        assert grounding.target_scope == expected_scope, message


def test_validator_accepts_soft_warnings_but_blocks_hard_leaks() -> None:
    project_grounding = {
        "target_scope": "project_state",
        "user_is_asking_about": "project status",
        "should_use_memory": True,
        "should_use_chat_context": False,
    }
    soft_decision = {"intent": "project_status_request", "language": "fi", "grounding": project_grounding}
    soft = validate_output(soft_decision, "En tiedä mikä projektisi on, kerro minulle projektista.")

    assert soft["ok"] is True
    assert soft["action"] == "accept_with_warnings"
    assert "generic_answer_for_project_specific_question" in soft["issues"]

    hard_decision = {"intent": "health_lifestyle_general", "language": "fi"}
    hard = validate_output(hard_decision, "Tähän liittyy verokortti ja laskutusmalli.")
    assert hard["ok"] is False
    assert "business_leakage" in hard["issues"]

    assert validated_reply({"intent": "general_knowledge", "language": "fi"}, "Selkeä vastaus.") == "Selkeä vastaus."


def test_validator_object_grounding_and_source_helpers() -> None:
    grounding_data = {
        "target_scope": "sade_persona",
        "user_is_asking_about": "persona",
        "should_answer_as_persona": True,
    }
    decision = _DecisionObject(_GroundingObject(grounding_data))

    reply = "Hei! Olen Local AI Workspace."
    assert persona_suppressed(reply, decision) is True
    assert wrong_source_used(reply, decision) is True

    project_data = {
        "target_scope": "project_state",
        "user_is_asking_about": "project status",
    }
    assert generic_answer_for_project_specific_question(
        "I don't know your project. Tell me more.", {"grounding": project_data}
    )

    safety_data = {"target_scope": "project_state", "user_is_asking_about": "project status"}
    assert safety_overtriggered("En voi auttaa turvallisuussyistä.", {"grounding": safety_data})


def test_validator_remaining_fallback_and_warning_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    object_with_dict_grounding = _DecisionObject({"target_scope": "project_state", "user_is_asking_about": "identity"})
    assert validate_output(object_with_dict_grounding, "Olen Local AI Workspace -projektin paikallinen AI-assistentti.")["ok"]

    memory_decision = {
        "intent": "normal_chat",
        "language": "fi",
        "grounding": {"target_scope": "assistant_memory", "should_use_memory": False, "should_use_chat_context": False},
    }
    memory_warning = validate_output(memory_decision, "Vastaan muistin perusteella.")
    assert memory_warning["ok"] is True
    assert "memory_ignored_for_memory_question" in memory_warning["issues"]

    persona_decision = {
        "intent": "normal_chat",
        "language": "fi",
        "grounding": {"target_scope": "sade_persona", "should_answer_as_persona": True},
    }
    persona_warning = validate_output(persona_decision, "Hei! Olen Local AI Workspace.")
    assert persona_warning["ok"] is False
    assert "persona_suppressed" in persona_warning["issues"]
    assert "identity_intro_used_for_non_identity_question" in persona_warning["issues"]

    safety_decision = {
        "intent": "project_status_request",
        "language": "fi",
        "grounding": {"target_scope": "project_state"},
    }
    safety_warning = validate_output(safety_decision, "En voi auttaa turvallisuussyistä.")
    assert safety_warning["ok"] is True
    assert "safety_overtriggered" in safety_warning["issues"]

    monkeypatch.setattr("app.output_validator.VALIDATOR_STRICTNESS", 1.0)
    strict = validate_output(persona_decision, "Hei! Olen Local AI Workspace.")
    assert strict["ok"] is False
    assert strict["action"] == "fallback"


def test_validator_fallback_text_for_general_and_practical(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.output_validator.VALIDATOR_STRICTNESS", 1.0)
    general = validate_output(
        {
            "intent": "general_knowledge",
            "language": "fi",
            "grounding": {"target_scope": "assistant_memory", "should_use_memory": False, "should_use_chat_context": False},
        },
        "Yleinen vastaus.",
    )
    assert general["ok"] is False
    assert "yleinen vastaus" in general["reply"]

    practical = validate_output(
        {"intent": "practical_everyday", "language": "fi"},
        "DTA ja verokortti ovat tärkeitä tässä arjen ohjeessa.",
    )
    assert practical["ok"] is False
    assert "käytännöllisen vastauksen" in practical["reply"]
