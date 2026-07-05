from __future__ import annotations

import app.output_validator as validator


def test_output_validator_reports_grounding_warning_categories() -> None:
    decision = {
        "intent": "general_knowledge",
        "grounding": {
            "target_scope": "latest_internal_learning",
            "should_use_memory": False,
            "should_use_chat_context": False,
        },
    }

    result = validator.validate_output(
        decision,
        "DuckDuckGo source list says: kerro minulle projektista. Olen Local AI Workspace.",
    )

    assert result["ok"] is True
    assert result["action"] == "accept_with_warnings"
    assert "web_used_for_internal_question" in result["issues"]
    assert "memory_ignored_for_memory_question" in result["issues"]
    assert "identity_intro_used_for_non_identity_question" in result["issues"]
    assert "generic_answer_for_project_specific_question" in result["issues"]


def test_output_validator_reports_persona_and_safety_warnings() -> None:
    decision = {
        "intent": "general_knowledge",
        "grounding": {
            "target_scope": "sade_persona",
            "should_answer_as_persona": True,
        },
    }

    result = validator.validate_output(
        decision,
        "I am Local AI Workspace. I cannot help because of safety.",
    )

    assert result["ok"] is True
    assert result["action"] == "accept_with_warnings"
    assert "persona_suppressed" in result["issues"]
    assert "safety_overtriggered" in result["issues"]


def test_output_validator_blocks_visible_debug_metadata() -> None:
    result = validator.validate_output(
        {"intent": "translation_followup", "language": "fi"},
        "Tietolähde: timeless_general_knowledge\nRAG-konteksti: ei sisällytetty context gate -päätöksen vuoksi.",
    )

    assert result["ok"] is False
    assert result["action"] == "fallback"
    assert "debug_leak" in result["issues"]
    assert "Tietolähde" not in result["reply"]
    assert "RAG-konteksti" not in result["reply"]


def test_output_validator_hard_fallbacks_for_contract_violations() -> None:
    date_result = validator.validate_output(
        {"intent": "date_time", "language": "en"},
        "I should use Google Search and source list for the time.",
    )
    assert date_result["ok"] is False
    assert date_result["action"] == "fallback"
    assert "local server time" in date_result["reply"]

    permissions_result = validator.validate_output(
        {"intent": "assistant_permissions", "language": "en"},
        "This is about human rights and perusoikeudet.",
    )
    assert permissions_result["ok"] is False
    assert "must not reveal secrets" in permissions_result["reply"]

    health_result = validator.validate_output(
        {"intent": "health_lifestyle_general"},
        "Tähän kannattaa liittää freelance laskutusmalli ja kirjanpito.",
    )
    assert health_result["ok"] is False
    assert "elämäntapavastaus" in health_result["reply"]

    finnish_result = validator.validate_output(
        {"intent": "finnish_language_capability"},
        "# Omatila\nDTA-sopimus ja verokortti mukaan.",
    )
    assert finnish_result["ok"] is False
    assert "Kielitaitokysymykseen" in finnish_result["reply"]


def test_output_validator_strict_mode_falls_back_on_soft_issue(monkeypatch) -> None:
    monkeypatch.setattr(validator, "VALIDATOR_STRICTNESS", 1.0)

    result = validator.validate_output(
        {"intent": "general_knowledge", "allow_business_suggestions": False},
        "Tähän voisi lisätä kirjanpito-ohjeen.",
    )

    assert result["ok"] is False
    assert result["action"] == "fallback"
    assert "unexpected_business_suggestion" in result["issues"]
    assert validator.validated_reply({"intent": "general_knowledge"}, "Selvä vastaus") == "Selvä vastaus"
