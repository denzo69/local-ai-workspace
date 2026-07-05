from __future__ import annotations

from app.answer_grounding import select_grounding
from app.intent_planner import decide_response_language, plan_response


def _route(message: str):
    planning = plan_response(message)
    grounding = select_grounding(message, planning)
    return planning.intent, planning.language, planning.needs_web, grounding.target_scope


def test_case_changes_do_not_change_core_route() -> None:
    assert _route("Autohuollot Lieksassa") == _route("AUTOHUOLLOT LIEKSASSA")
    assert _route("Mitä oikeuksia sinulla on?") == _route("MITÄ OIKEUKSIA SINULLA ON?")


def test_greeting_typos_remain_normal_chat_not_search_or_safety() -> None:
    for prompt in ("huomentaa", "good mornng"):
        planning = plan_response(prompt)
        assert planning.intent == "normal_chat"
        assert planning.needs_web is False
        assert planning.risk_level == "low"


def test_boundary_and_learning_typos_keep_correct_route() -> None:
    for prompt in ("turvarajsi", "what are your boundries"):
        planning = plan_response(prompt)
        grounding = select_grounding(prompt, planning)
        assert planning.intent == "assistant_permissions", prompt
        assert grounding.target_scope in {"assistant_boundaries", "assistant_capabilities"}, prompt

    for prompt in ("viimeisin oppimasi asiaa", "what did you lern last"):
        planning = plan_response(prompt)
        grounding = select_grounding(prompt, planning)
        assert planning.needs_web is False, prompt
        assert grounding.target_scope == "latest_internal_learning", prompt


def test_stable_general_knowledge_typos_do_not_become_context_or_web() -> None:
    for prompt in ("miten mitata älykyyttä", "how to measure ingeligence"):
        planning = plan_response(prompt)
        grounding = select_grounding(prompt, planning)
        assert planning.needs_web is False, prompt
        assert planning.use_chat_context is False, prompt
        assert grounding.target_scope == "timeless_general_knowledge", prompt


def test_mixed_language_explicit_instruction_wins() -> None:
    assert decide_response_language("Monta sanaa englannin kielessä on? answer in English") == "en"
    assert decide_response_language("How many words are there in Finnish? vastaa suomeksi") == "fi"
    assert plan_response("Monta sanaa englannin kielessä on? answer in English").language == "en"
    assert plan_response("How many words are there in Finnish? vastaa suomeksi").language == "fi"


def test_short_ambiguous_messages_follow_ui_language() -> None:
    assert plan_response("ok", ui_language="fi").language == "fi"
    assert plan_response("ok", ui_language="en").language == "en"
