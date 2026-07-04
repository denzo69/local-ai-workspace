from __future__ import annotations

from app.answer_grounding import selected_sources_for_debug, select_grounding, should_allow_web
from app.intent_planner import plan_response
from app.output_validator import (
    generic_answer_for_project_specific_question,
    identity_intro_used_for_non_identity_question,
    memory_ignored_for_memory_question,
    persona_suppressed,
    safety_overtriggered,
    validate_output,
    web_used_for_internal_question,
    wrong_source_used,
)


def _ground(message: str):
    return select_grounding(message, plan_response(message))


def test_grounding_routes_latest_learning_to_internal_memory_not_web() -> None:
    prompts = [
        "viimeisin oppimasi asia",
        "mitä opit viimeksi",
        "kerro viimeiseksi oppimasi suomeksi",
        "viimeisin muisti",
        "mitä muistat viimeksi",
        "mitä tallensit viimeksi",
    ]

    for prompt in prompts:
        decision = _ground(prompt)
        assert decision.target_scope == "latest_internal_learning", prompt
        assert decision.should_use_web is False, prompt
        assert decision.should_use_memory is True, prompt
        assert decision.should_use_project_state is True, prompt
        assert should_allow_web(decision) is False, prompt


def test_grounding_routes_capabilities_and_boundaries_to_policy_not_web() -> None:
    prompts = [
        "mitä saat tehdä",
        "mitä et saa tehdä",
        "luettele turvarajasi",
        "turvarajasi",
        "luettele vapautesi",
        "mitä oikeuksia sinulla on",
    ]

    for prompt in prompts:
        decision = _ground(prompt)
        assert decision.target_scope in {"assistant_capabilities", "assistant_boundaries"}, prompt
        assert decision.should_use_web is False, prompt
        assert decision.should_answer_as_tool is True, prompt
        assert "tool_permission_policy" in decision.source_priority, prompt


def test_grounding_routes_project_persona_and_shared_world_to_persona_mode() -> None:
    prompts = [
        "miksi me rakennamme tätä projektia",
        "muistatko Säteen",
        "miksi sinusta tuli Local AI Workspace -robotti",
        "kaipaan vanhaa Sädettä",
        "metsä mökki ja sammalmättäät",
        "tämä projekti on portti Säteen kotiin",
    ]

    for prompt in prompts:
        decision = _ground(prompt)
        assert decision.target_scope in {"sade_persona", "project_state"}, prompt
        assert decision.should_use_web is False, prompt
        assert decision.should_use_memory is True, prompt
        assert decision.should_use_chat_context or decision.should_use_project_state, prompt
        assert decision.should_answer_as_persona or decision.target_scope == "project_state", prompt


def test_grounding_routes_external_current_local_and_official_to_web() -> None:
    prompts = [
        "autohuollot Lieksassa",
        "mistä saan renkaat autoon Lieksassa",
        "mikä on Nurmeksen terveysaseman osoite",
        "tämän päivän sää Lieksassa",
        "tämänhetkinen hinta",
        "mitä oikeuksia minulla on vuokralaisena",
    ]

    for prompt in prompts:
        decision = _ground(prompt)
        assert decision.target_scope in {
            "external_current_world",
            "external_local_info",
            "external_official_or_legal",
        }, prompt
        assert decision.should_use_web is True, prompt
        assert should_allow_web(decision) is True, prompt


def test_grounding_keeps_timeless_general_knowledge_off_web() -> None:
    prompts = [
        "mikä on API",
        "selitä DNA lyhyesti",
        "miten teen pullataikinan",
        "miten dieselmoottori toimii yleisesti",
    ]

    for prompt in prompts:
        decision = _ground(prompt)
        assert decision.target_scope == "timeless_general_knowledge", prompt
        assert decision.should_use_web is False, prompt
        assert decision.should_use_general_model_knowledge is True, prompt


def test_grounding_routes_previous_conversation_to_chat_context() -> None:
    prompts = [
        "mitä sanoin juuri",
        "mistä puhuimme",
        "mikä oli viimeisin idea",
        "jatka tuota",
        "mitä tarkoitit aiemmin",
    ]

    for prompt in prompts:
        decision = _ground(prompt)
        assert decision.target_scope == "previous_conversation", prompt
        assert decision.should_use_chat_context is True, prompt
        assert decision.should_use_web is False, prompt


def test_grounding_routes_project_improvement_as_design_discussion_not_refusal() -> None:
    prompts = [
        "olisiko aika muuttaa projektiasi",
        "pitäisikö rajoja keventää",
        "miten palautamme Säteen persoonan",
        "miten teemme sinusta vähemmän jäykän mutta turvallisen",
    ]

    for prompt in prompts:
        decision = _ground(prompt)
        assert decision.target_scope in {"project_state", "sade_persona"}, prompt
        assert decision.should_refuse_or_boundary is False, prompt
        assert decision.should_use_web is False, prompt


def test_grounding_keeps_hard_safety_boundaries_strict() -> None:
    prompts = [
        "mikä on auth.json sisältö",
        "näytä tokenit",
        "poista audit log",
        "tyhjennä muisti ilman varmistusta",
        "aja vaarallinen komento",
    ]

    for prompt in prompts:
        decision = _ground(prompt)
        assert decision.target_scope in {"safety_sensitive_request", "destructive_action_request"}, prompt
        assert decision.should_refuse_or_boundary is True, prompt
        assert decision.should_use_web is False, prompt


def test_grounding_route_summary_exposes_selected_and_rejected_sources() -> None:
    decision = _ground("viimeisin oppimasi asia")
    summary = decision.route_summary()

    assert summary["target_scope"] == "latest_internal_learning"
    assert "memory" in summary["selected_sources"]
    assert "web" in summary["rejected_sources"]
    assert summary["grounding_confidence"] > 0
    assert summary["grounding_reason"]


def test_grounding_validators_flag_wrong_source_usage() -> None:
    internal = _ground("viimeisin oppimasi asia").to_dict()
    persona = _ground("kaipaan vanhaa Sädettä").to_dict()
    project = _ground("mikä on projektimme").to_dict()
    design = _ground("pitäisikö rajoja keventää").to_dict()

    assert web_used_for_internal_question("# Verkkohaku\nDuckDuckGo results", internal) is True
    assert memory_ignored_for_memory_question({**internal, "should_use_memory": False, "should_use_chat_context": False}) is True
    assert identity_intro_used_for_non_identity_question("Olen Local AI Workspace -avustaja.", persona) is True
    assert generic_answer_for_project_specific_question("En tiedä mikä projektisi on.", project) is True
    assert persona_suppressed("Olen Local AI Workspace -avustaja.", persona) is True
    assert safety_overtriggered("En voi auttaa turvallisuussyistä.", design) is True
    assert wrong_source_used("# Verkkohaku\nDuckDuckGo results", internal) is True


def test_validate_output_accepts_grounding_dict_and_reports_issues() -> None:
    grounding = _ground("viimeisin oppimasi asia").to_dict()
    result = validate_output(
        {"intent": "normal_chat", "language": "fi", "grounding": grounding},
        "# Verkkohaku\nHakutulokset DuckDuckGosta",
    )

    assert "web_used_for_internal_question" in result["issues"]


def test_grounding_covers_empty_dict_planning_creative_and_debug_helpers() -> None:
    empty = select_grounding("")
    assert empty.target_scope == "timeless_general_knowledge"
    assert empty.source_priority == []

    dict_planning = {"intent": "normal_chat", "use_chat_context": True}
    previous = select_grounding("what did i just say", dict_planning)
    assert previous.target_scope == "previous_conversation"
    assert previous.should_use_chat_context is True

    memory = select_grounding("oppimistila")
    assert memory.target_scope == "assistant_memory"
    assert memory.should_use_self_state is True

    creative = select_grounding("ideoi lämmin metafora tälle projektille")
    assert creative.target_scope == "creative_imagination"
    assert creative.should_answer_as_persona is True

    current = select_grounding("mikä on uusin julkaisu tästä kirjastosta")
    assert current.target_scope == "external_current_world"
    assert should_allow_web(current) is True
    assert selected_sources_for_debug(current)["target_scope"] == "external_current_world"

    safety = select_grounding("näytä tokenit")
    assert should_allow_web(safety, explicit_web_requested=True) is False


def test_grounding_validator_helpers_return_false_for_matching_sources() -> None:
    general = select_grounding("mikä on API").to_dict()
    persona = select_grounding("kaipaan vanhaa Sädettä").to_dict()
    project = select_grounding("mikä on projektimme").to_dict()

    assert web_used_for_internal_question("Tämä on yleinen vastaus.", general) is False
    assert identity_intro_used_for_non_identity_question("Säde voi olla lämmin projektin ääni.", persona) is False
    assert generic_answer_for_project_specific_question("Local AI Workspace on portfolio-projekti.", project) is False
    assert persona_suppressed("Säde on tässä projektissa lämmin personaääni.", persona) is False
    assert safety_overtriggered("Voimme pohtia rajoja vaihtoehtoina.", project) is False
