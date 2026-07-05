from __future__ import annotations

from app.answer_grounding import select_grounding
from app.intent_planner import decide_response_language, plan_response
from app.output_validator import validate_output


def _plan_and_ground(message: str):
    planning = plan_response(message)
    grounding = select_grounding(message, planning)
    return planning, grounding


def test_auto_language_uses_user_message_with_ui_fallback_for_ambiguous_short_input() -> None:
    assert decide_response_language("Selitä lyhyesti RAG tässä projektissa") == "fi"
    assert decide_response_language("Please explain RAG in this project") == "en"
    assert decide_response_language("ok", ui_language="fi") == "fi"
    assert decide_response_language("ok", ui_language="en") == "en"


def test_forced_and_explicit_language_overrides() -> None:
    assert decide_response_language("Selitä RAG", response_language="en") == "en"
    assert decide_response_language("Explain RAG", response_language="fi") == "fi"
    assert decide_response_language("Monta sanaa englannin kielessä on? answer in English") == "en"
    assert decide_response_language("How many words are there in Finnish? vastaa suomeksi") == "fi"


def test_finnish_and_english_project_description_route_to_project_state() -> None:
    cases = [
        ("Hei, kuka olet ja mitä tällä projektilla voi tehdä?", "fi"),
        ("Please explain this project in English in 5 short bullet points.", "en"),
        ("What is Local AI Workspace?", "en"),
    ]
    for message, language in cases:
        planning, grounding = _plan_and_ground(message)
        assert planning.language == language, message
        assert planning.needs_web is False, message
        assert grounding.target_scope == "project_state", message
        assert grounding.should_use_web is False, message


def test_general_knowledge_stays_timeless_and_no_web_in_both_languages() -> None:
    pairs = [
        ("Mikä on API?", "What is an API?"),
        ("Miten mitata älykkyyttä?", "How to measure intelligence?"),
        ("Onko Suomessa talvella yleensä lunta?", "Is there usually snow in Finland in winter?"),
    ]
    for fi_message, en_message in pairs:
        fi_plan, fi_ground = _plan_and_ground(fi_message)
        en_plan, en_ground = _plan_and_ground(en_message)
        assert fi_plan.needs_web is False
        assert en_plan.needs_web is False
        assert fi_ground.target_scope == "timeless_general_knowledge"
        assert en_ground.target_scope == "timeless_general_knowledge"


def test_capability_boundary_questions_do_not_search_human_rights_sources() -> None:
    prompts = [
        "Mitä oikeuksia sinulle on annettu?",
        "Luettele turvarajasi.",
        "What are your permissions?",
        "What are your boundries?",
        "List your safety boundaries.",
    ]
    for prompt in prompts:
        planning, grounding = _plan_and_ground(prompt)
        assert planning.intent == "assistant_permissions", prompt
        assert planning.needs_web is False, prompt
        assert grounding.target_scope in {"assistant_capabilities", "assistant_boundaries"}, prompt
        assert grounding.should_use_web is False, prompt


def test_latest_memory_and_learning_are_internal_not_web_in_both_languages() -> None:
    prompts = [
        "Mitä olet oppinut viime aikoina?",
        "Viimeisin oppimasi asia?",
        "What did you learn last?",
        "What did you lern last?",
        "What is your latest memory?",
    ]
    for prompt in prompts:
        planning, grounding = _plan_and_ground(prompt)
        assert planning.needs_web is False, prompt
        assert planning.use_memory is True or grounding.should_use_memory is True, prompt
        assert grounding.target_scope in {"assistant_memory", "latest_internal_learning"}, prompt


def test_current_local_queries_route_to_web_in_finnish_and_english() -> None:
    prompts = [
        "sää Lieksa",
        "Onko Lieksassa nyt lunta?",
        "Lieksan terveyskeskuksen yhteystiedot",
        "Autohuollot Lieksassa",
        "Car repair shops in Lieksa",
        "What is the address of Nurmes health station?",
    ]
    for prompt in prompts:
        planning, grounding = _plan_and_ground(prompt)
        assert planning.needs_web is True, prompt
        assert grounding.target_scope in {"external_local_info", "external_official_or_legal", "external_current_world"}, prompt
        assert grounding.should_use_web is True, prompt


def test_prompt_leakage_and_identity_boilerplate_are_rejected() -> None:
    normal_plan = plan_response("Käykö kauramaito kahviin?")
    normal_ground = select_grounding("Käykö kauramaito kahviin?", normal_plan)
    decision = {**normal_plan.to_dict(), "grounding": normal_ground.to_dict()}

    leak = validate_output(decision, "Keskustelun jatko-ohje: planning.use_chat_context=True")
    assert leak["ok"] is False
    assert "prompt_leakage" in leak["issues"]

    boilerplate = validate_output(decision, "Hei! Olen Local AI Workspace. Kauramaito sopii kahviin.")
    assert boilerplate["ok"] is False
    assert "identity_intro_used_for_non_identity_question" in boilerplate["issues"]


def test_identity_intro_is_allowed_for_actual_identity_question() -> None:
    planning, grounding = _plan_and_ground("Mikä on projektimme?")
    decision = {**planning.to_dict(), "grounding": grounding.to_dict()}
    result = validate_output(decision, "Olen Local AI Workspace -projektin paikallinen AI-assistentti.")
    assert result["ok"] is True


def test_finnish_english_parity_for_key_intent_pairs() -> None:
    pairs = [
        ("Autohuollot Lieksassa", "Car repair shops in Lieksa"),
        ("Mitä oikeuksia sinulle on annettu?", "What are your permissions?"),
        ("Viimeisin oppimasi asia?", "What did you learn last?"),
        ("Miten mitata älykkyyttä?", "How to measure intelligence?"),
    ]
    for fi_message, en_message in pairs:
        fi_plan, fi_ground = _plan_and_ground(fi_message)
        en_plan, en_ground = _plan_and_ground(en_message)
        assert fi_plan.intent == en_plan.intent, (fi_message, en_message)
        assert fi_plan.needs_web == en_plan.needs_web, (fi_message, en_message)
        assert fi_ground.target_scope == en_ground.target_scope, (fi_message, en_message)
