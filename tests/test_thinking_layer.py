from __future__ import annotations

from types import SimpleNamespace

from app.thinking_layer import build_thinking_context, build_thinking_directive


def decision(**kwargs):
    defaults = {
        "intent": "normal_chat",
        "needs_web": False,
        "use_rag": False,
        "use_chat_context": False,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_thinking_layer_selects_source_grounded_mode_for_web() -> None:
    directive = build_thinking_directive(
        "Mitkä ovat uusimmat tekoälyn kehityssuunnat?",
        decision(intent="current_external_information", needs_web=True),
    )

    assert directive.mode == "source_grounded"
    assert directive.use_sources is True
    assert any("source-supported" in item for item in directive.self_check)


def test_thinking_layer_selects_creative_and_deliberative_modes() -> None:
    creative = build_thinking_directive("Ideoi kolme nimeä projektille", decision())
    deliberative = build_thinking_directive("Kumpi ratkaisu kannattaa valita ja miksi?", decision())

    assert creative.mode == "creative_exploration"
    assert creative.creativity == "high"
    assert creative.use_alternatives is True
    assert deliberative.mode == "deliberative_comparison"
    assert deliberative.use_alternatives is True


def test_thinking_layer_selects_contextual_conversation_for_followup() -> None:
    directive = build_thinking_directive(
        "Entä mikä niistä olisi lähin?",
        decision(use_chat_context=True),
    )

    assert directive.mode == "contextual_conversation"
    assert directive.use_conversation_context is True


def test_thinking_context_forbids_hidden_chain_of_thought() -> None:
    context = build_thinking_context("Suunnittele luova ratkaisu", decision())

    assert "Do not show hidden chain-of-thought" in context
    assert "Response thinking layer" in context
    assert "Internal final-answer check" in context
