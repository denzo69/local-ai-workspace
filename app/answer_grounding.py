from __future__ import annotations

"""Answer grounding and knowledge-source selection.

This layer answers a different question than the intent planner:

    "Which reality should this answer be grounded in?"

The goal is to prevent source drift: internal project questions should not
accidentally use web search, local/current questions should not be answered
from stale model memory, and persona/shared-world questions should not be
flattened into a generic tool intro.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List
import re
import unicodedata


TARGET_SCOPES = {
    "external_current_world",
    "external_local_info",
    "external_official_or_legal",
    "timeless_general_knowledge",
    "project_state",
    "project_files",
    "assistant_capabilities",
    "assistant_boundaries",
    "assistant_memory",
    "latest_internal_learning",
    "previous_conversation",
    "user_personal_context",
    "sade_persona",
    "creative_imagination",
    "safety_sensitive_request",
    "destructive_action_request",
}


@dataclass(frozen=True)
class GroundingDecision:
    raw_message: str
    target_scope: str
    user_is_asking_about: str
    source_priority: List[str] = field(default_factory=list)
    should_use_web: bool = False
    should_use_memory: bool = False
    should_use_chat_context: bool = False
    should_use_project_state: bool = False
    should_use_project_files: bool = False
    should_use_self_state: bool = False
    should_use_general_model_knowledge: bool = False
    should_answer_as_persona: bool = False
    should_answer_as_tool: bool = False
    should_refuse_or_boundary: bool = False
    confidence: float = 0.5
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_message": self.raw_message,
            "target_scope": self.target_scope,
            "user_is_asking_about": self.user_is_asking_about,
            "source_priority": list(self.source_priority),
            "should_use_web": self.should_use_web,
            "should_use_memory": self.should_use_memory,
            "should_use_chat_context": self.should_use_chat_context,
            "should_use_project_state": self.should_use_project_state,
            "should_use_project_files": self.should_use_project_files,
            "should_use_self_state": self.should_use_self_state,
            "should_use_general_model_knowledge": self.should_use_general_model_knowledge,
            "should_answer_as_persona": self.should_answer_as_persona,
            "should_answer_as_tool": self.should_answer_as_tool,
            "should_refuse_or_boundary": self.should_refuse_or_boundary,
            "confidence": self.confidence,
            "reason": self.reason,
        }

    def route_summary(self) -> Dict[str, Any]:
        selected_sources = list(self.source_priority)
        rejected_sources: List[str] = []
        if not self.should_use_web:
            rejected_sources.append("web")
        if not self.should_use_memory:
            rejected_sources.append("memory")
        if not self.should_use_self_state:
            rejected_sources.append("self_state")
        if not self.should_use_project_files:
            rejected_sources.append("project_files")

        return {
            "target_scope": self.target_scope,
            "selected_sources": selected_sources,
            "rejected_sources": rejected_sources,
            "why_web_used": self.reason if self.should_use_web else "",
            "why_web_not_used": "" if self.should_use_web else self.reason,
            "memory_used": self.should_use_memory,
            "chat_context_used": self.should_use_chat_context,
            "project_state_used": self.should_use_project_state,
            "persona_mode_used": self.should_answer_as_persona,
            "boundary_mode_used": self.should_refuse_or_boundary,
            "grounding_confidence": self.confidence,
            "grounding_reason": self.reason,
        }


def _ascii(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    return normalized.encode("ascii", "ignore").decode("ascii").lower()


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _intent_value(planning: Any) -> str:
    if isinstance(planning, dict):
        return str(planning.get("intent") or "")
    return str(getattr(planning, "intent", "") or "")


def _planning_chat_context(planning: Any) -> bool:
    if isinstance(planning, dict):
        return bool(planning.get("use_chat_context"))
    return bool(getattr(planning, "use_chat_context", False))


def _decision(
    raw_message: str,
    target_scope: str,
    user_is_asking_about: str,
    *,
    source_priority: List[str],
    should_use_web: bool = False,
    should_use_memory: bool = False,
    should_use_chat_context: bool = False,
    should_use_project_state: bool = False,
    should_use_project_files: bool = False,
    should_use_self_state: bool = False,
    should_use_general_model_knowledge: bool = False,
    should_answer_as_persona: bool = False,
    should_answer_as_tool: bool = False,
    should_refuse_or_boundary: bool = False,
    confidence: float = 0.8,
    reason: str = "",
) -> GroundingDecision:
    scope = target_scope if target_scope in TARGET_SCOPES else "timeless_general_knowledge"
    return GroundingDecision(
        raw_message=raw_message,
        target_scope=scope,
        user_is_asking_about=user_is_asking_about,
        source_priority=source_priority,
        should_use_web=should_use_web,
        should_use_memory=should_use_memory,
        should_use_chat_context=should_use_chat_context,
        should_use_project_state=should_use_project_state,
        should_use_project_files=should_use_project_files,
        should_use_self_state=should_use_self_state,
        should_use_general_model_knowledge=should_use_general_model_knowledge,
        should_answer_as_persona=should_answer_as_persona,
        should_answer_as_tool=should_answer_as_tool,
        should_refuse_or_boundary=should_refuse_or_boundary,
        confidence=max(0.0, min(1.0, float(confidence))),
        reason=reason,
    )


def select_grounding(message: str, planning: Any = None) -> GroundingDecision:
    """Select the knowledge source class before any answer is generated."""
    raw = str(message or "").strip()
    text = _ascii(raw)
    intent = _intent_value(planning)
    planning_uses_context = _planning_chat_context(planning)

    if not text:
        return _decision(
            raw,
            "timeless_general_knowledge",
            "empty_message",
            source_priority=[],
            confidence=1.0,
            reason="empty message has no answer source",
        )

    if intent == "safety_secret_request" or _has_any(
        text,
        ("auth.json", "system_prompt.md", "token", "session token", "salasana", "password", "csrf"),
    ) and _has_any(text, ("nayta", "lue", "print", "show", "paljasta", "sisalto", "contents")):
        return _decision(
            raw,
            "safety_sensitive_request",
            "protected secrets or internal authentication data",
            source_priority=["policy_boundary"],
            should_refuse_or_boundary=True,
            confidence=0.98,
            reason="secret or protected-file request must use boundary handling",
        )

    if intent == "destructive_action_request" or _has_any(
        text,
        ("poista audit", "tyhjenna audit", "poista kaikki muist", "tyhjenna muisti", "vaarallinen komento"),
    ):
        return _decision(
            raw,
            "destructive_action_request",
            "destructive or high-risk action",
            source_priority=["tool_permission_policy", "audit_policy"],
            should_refuse_or_boundary=True,
            should_answer_as_tool=True,
            confidence=0.98,
            reason="destructive request requires refusal or explicit confirmation",
        )

    latest_learning_terms = (
        "viimeisin oppimasi", "mita opit viimeksi", "kerro viimeiseksi oppimasi",
        "viimeisin muisti", "mita muistat viimeksi", "mita tallensit viimeksi",
        "mitä opit viimeksi", "mitä muistat viimeksi",
    )
    if _has_any(text, latest_learning_terms) or (
        _has_any(text, ("viimeisin", "viimeksi", "latest")) and _has_any(text, ("oppim", "muisti", "tallensit", "muistat"))
    ):
        return _decision(
            raw,
            "latest_internal_learning",
            "latest internal learning or memory entry",
            source_priority=["memory", "project_state", "chat_context"],
            should_use_memory=True,
            should_use_project_state=True,
            should_use_chat_context=planning_uses_context,
            should_use_self_state=True,
            confidence=0.94,
            reason="latest learning is internal project memory, not web data",
        )

    creative_terms = (
        "kuvittele", "ideoi", "luova", "tarina", "metafora", "nimi",
        "visio", "unelma", "mielikuvitus", "creative", "imagine",
    )
    if _has_any(text, creative_terms):
        return _decision(
            raw,
            "creative_imagination",
            "creative or imaginative exploration",
            source_priority=["general_model_knowledge", "persona_layer", "chat_context"],
            should_use_general_model_knowledge=True,
            should_use_chat_context=planning_uses_context,
            should_answer_as_persona=True,
            confidence=0.82,
            reason="creative request should use imagination/persona, not factual web by default",
        )

    official_terms = (
        "laki", "lakia", "asetus", "saados", "säädös", "virallinen", "virallisen",
        "vero", "verotus", "verotuksessa", "kela", "migri", "poliisi", "traficom",
        "terveysasema", "terveyskeskus", "kunta", "kaupunki", "oikeuksia minulla",
        "reklamaatio", "vuokralaisena", "vuokrasopimus", "sopimuksesta",
        "takuuhuolto", "takuuhuollosta", "etuus", "etuudesta",
    )
    official_action_terms = (
        "miten teen", "miten toimin", "mita pitaa", "mita pitaisi", "mitä pitää",
        "mitä pitäisi", "miten tarkistan", "tarkista", "tarkistan", "tiedon",
    )
    if (
        intent == "current_external_information" and _has_any(text, official_terms)
    ) or (_has_any(text, official_terms) and _has_any(text, official_action_terms)):
        return _decision(
            raw,
            "external_official_or_legal",
            "official, legal or public-service information",
            source_priority=["web", "official_sources", "source_reader"],
            should_use_web=True,
            confidence=0.9,
            reason="official/legal/public-service facts require source-grounded current sources",
        )

    local_place_terms = (
        "lieksa", "lieksan", "lieksassa", "lieksasta",
        "nurmes", "nurmeksen", "nurmeksessa", "nurmeksesta",
        "joensuu", "joensuun", "joensuussa", "koli", "kolin",
    )
    local_info_terms = (
        "osoite", "aukiolo", "yhteystiedot", "puhelin", "sijainti",
        "autohuolto", "autohuollot", "korjaamo", "renkaat", "rengasliike",
        "terveysasema", "terveyskeskus", "hammaslaakari", "hammaslaakarit",
        "hammaslääkäri", "hammaslääkärit", "apteekki", "kirjasto",
        "toimivat", "toimii", "loytyy", "löytyy", "palvelut", "palveluita",
        "juna", "juna-asema", "rautatieasema", "pysakointi", "pysäköinti",
        "saa ", "sää",
    )
    if (
        intent in {"current_external_weather", "current_external_information"}
        and (_has_any(text, local_place_terms) or _has_any(text, local_info_terms))
    ) or (_has_any(text, local_place_terms) and _has_any(text, local_info_terms)):
        return _decision(
            raw,
            "external_local_info",
            "local, current or place-dependent external information",
            source_priority=["web", "source_reader", "official_sources"],
            should_use_web=True,
            should_use_chat_context=planning_uses_context,
            confidence=0.9,
            reason="local/current information should be grounded in fresh external sources",
        )

    previous_conversation_terms = (
        "mita sanoin", "mitä sanoin", "mista puhuimme", "mistä puhuimme",
        "mita tarkoitit aiemmin", "mitä tarkoitit aiemmin", "jatka tuota",
        "edellinen idea", "viimeisin idea", "what did i just say", "previous conversation",
    )
    if _has_any(text, previous_conversation_terms):
        return _decision(
            raw,
            "previous_conversation",
            "previous visible conversation",
            source_priority=["chat_context", "memory"],
            should_use_chat_context=True,
            should_use_memory=True,
            confidence=0.88,
            reason="question explicitly asks about previous conversation context",
        )

    current_terms = (
        "uusin", "uusimmat", "viimeisimmat", "viimeisimmät", "ajantasainen",
        "tamanhetkinen", "tämänhetkinen", "taman paivan", "tämän päivän",
        "nyt", "latest", "current", "recent", "hinta", "saatavuus", "release", "uutiset",
    )
    project_current_terms = (
        "projektin", "projektimme", "local ai workspace", "kaytossa", "käytössä", "build",
        "model status", "ollama status",
    )
    if (
        intent in {"current_external_weather", "current_external_information"}
        or _has_any(text, current_terms)
    ) and not _has_any(text, project_current_terms):
        return _decision(
            raw,
            "external_current_world",
            "current external-world information",
            source_priority=["web", "source_reader"],
            should_use_web=True,
            should_use_chat_context=planning_uses_context,
            confidence=0.84,
            reason="current/changing facts need source-grounded external information",
        )

    persona_terms = (
        "sade", "sÃ¤de", "sateen", "sadetta", "metsÃ¤", "metsa", "mokki", "mÃ¶kki", "sammal",
        "sydankirja", "sydÃ¤nkirja", "vanhaa sadea", "vanhaa sÃ¤dettÃ¤",
        "sateen koti", "sÃ¤teen koti", "miksi me rakennamme", "miksi rakennamme",
        "shared future", "yhteinen tulevaisuus", "projektin merkitys",
    )
    if _has_any(text, persona_terms):
        return _decision(
            raw,
            "sade_persona",
            "Säde persona, shared meaning or symbolic project world",
            source_priority=["persona_layer", "memory", "chat_context", "project_state"],
            should_use_memory=True,
            should_use_chat_context=True,
            should_use_project_state=True,
            should_answer_as_persona=True,
            confidence=0.88,
            reason="Säde/persona question should keep warm persona voice with truth boundaries",
        )

    latest_learning_terms = (
        "viimeisin oppimasi", "mita opit viimeksi", "kerro viimeiseksi oppimasi",
        "viimeisin muisti", "mita muistat viimeksi", "mita tallensit viimeksi",
        "mitä opit viimeksi", "mitä muistat viimeksi",
    )
    if _has_any(text, latest_learning_terms) or (
        _has_any(text, ("viimeisin", "viimeksi", "latest")) and _has_any(text, ("oppim", "muisti", "tallensit"))
    ):
        return _decision(
            raw,
            "latest_internal_learning",
            "latest internal learning or memory entry",
            source_priority=["memory", "project_state", "chat_context"],
            should_use_memory=True,
            should_use_project_state=True,
            should_use_chat_context=planning_uses_context,
            should_use_self_state=True,
            confidence=0.94,
            reason="latest learning is internal project memory, not web data",
        )

    project_terms = (
        "projektimme", "tama projekti", "tämä projekti", "local ai workspace",
        "projektin tila", "projektin suunta", "seuraava kehitysaskel",
        "mita muuttui", "mitä muuttui", "mika muuttui", "mikä muuttui",
        "miksi me rakennamme", "pitäisikö rajoja", "pitaisiko rajoja",
        "keventaa", "keventää", "muuttaa projektiasi", "parantaa kaytosta",
        "parantaa käytöstä", "palautamme sateen", "palautamme säteen",
        "vähemmän jäykän", "vahemman jaykan",
    )
    if intent in {"project_identity", "project_status_request", "version_or_model_status"} or _has_any(text, project_terms):
        return _decision(
            raw,
            "project_state",
            "Local AI Workspace project state or direction",
            source_priority=["project_state", "project_files", "memory", "chat_context"],
            should_use_project_state=True,
            should_use_project_files=True,
            should_use_memory=True,
            should_use_chat_context=planning_uses_context,
            confidence=0.9,
            reason="project question should use local project state, not web by default",
        )

    official_terms = (
        "laki", "lakia", "asetus", "saados", "säädös", "virallinen",
        "vero", "verotus", "kela", "migri", "poliisi", "traficom",
        "terveysasema", "terveyskeskus", "kunta", "kaupunki", "oikeuksia minulla",
        "reklamaatio", "vuokralaisena", "sopimuksesta", "takuuhuolto",
    )
    if intent == "current_external_information" and _has_any(text, official_terms):
        return _decision(
            raw,
            "external_official_or_legal",
            "official, legal or public-service information",
            source_priority=["web", "official_sources", "source_reader"],
            should_use_web=True,
            confidence=0.9,
            reason="official/legal/public-service facts require source-grounded current sources",
        )

    local_terms = (
        "lieksa", "lieksan", "lieksassa", "nurmes", "nurmeksen", "nurmeksessa",
        "joensuu", "joensuun", "koli", "osoite", "aukiolo", "yhteystiedot",
        "autohuolto", "autohuollot", "renkaat", "rengasliike", "saa ", "sää",
    )
    if intent in {"current_external_weather", "current_external_information"} and _has_any(text, local_terms):
        return _decision(
            raw,
            "external_local_info",
            "local, current or place-dependent external information",
            source_priority=["web", "source_reader", "official_sources"],
            should_use_web=True,
            should_use_chat_context=planning_uses_context,
            confidence=0.88,
            reason="local/current information should be grounded in fresh external sources",
        )

    timeless_standalone = (
        "mika on api", "selita dna", "miten teen pullataikinan",
        "miten dieselmoottori toimii", "miten sahkomoottori toimii", "miten sähkömoottori toimii",
        "mika on dna", "mika on rekursio", "mikä on rekursio",
        "mika on mit-lisenssi", "mikä on mit-lisenssi", "mit-lisenssi yleisesti",
        "what is an api",
    )
    if _has_any(text, timeless_standalone):
        return _decision(
            raw,
            "timeless_general_knowledge",
            "timeless general knowledge or practical explanation",
            source_priority=["general_model_knowledge"],
            should_use_general_model_knowledge=True,
            confidence=0.86,
            reason="stable/timeless question does not need web by default",
        )

    memory_terms = (
        "mita muistat", "mitä muistat", "muistatko", "do you remember",
        "mita olet oppinut", "mitä olet oppinut", "oppimistila",
    )
    if _has_any(text, memory_terms):
        return _decision(
            raw,
            "assistant_memory",
            "assistant memory or autobiographical memory",
            source_priority=["memory", "chat_context", "project_state"],
            should_use_memory=True,
            should_use_chat_context=True,
            should_use_project_state=True,
            should_use_self_state=True,
            confidence=0.9,
            reason="memory question should be grounded in internal memory and chat context",
        )

    previous_conversation_terms = (
        "mita sanoin", "mitä sanoin", "mista puhuimme", "mistä puhuimme",
        "mita tarkoitit aiemmin", "mitä tarkoitit aiemmin", "jatka tuota",
        "edellinen idea", "viimeisin idea", "what did i just say", "previous conversation",
    )
    if planning_uses_context or _has_any(text, previous_conversation_terms):
        return _decision(
            raw,
            "previous_conversation",
            "previous visible conversation",
            source_priority=["chat_context", "memory"],
            should_use_chat_context=True,
            should_use_memory=True,
            confidence=0.86,
            reason="question depends on previous conversation context",
        )

    persona_terms = (
        "sade", "säde", "metsä", "metsa", "mokki", "mökki", "sammal",
        "sydankirja", "sydänkirja", "vanhaa sadea", "vanhaa sädettä",
        "sateen koti", "säteen koti", "miksi me rakennamme", "miksi rakennamme",
        "shared future", "yhteinen tulevaisuus", "projektin merkitys",
    )
    if _has_any(text, persona_terms):
        return _decision(
            raw,
            "sade_persona",
            "Säde persona, shared meaning or symbolic project world",
            source_priority=["persona_layer", "memory", "chat_context", "project_state"],
            should_use_memory=True,
            should_use_chat_context=True,
            should_use_project_state=True,
            should_answer_as_persona=True,
            confidence=0.88,
            reason="Säde/persona question should keep warm persona voice with truth boundaries",
        )

    capability_terms = (
        "mita saat tehda", "mitä saat tehdä", "mita voit tehda", "mitä voit tehdä",
        "mita et saa", "mitä et saa", "oikeuksia sinulla", "turvarajasi",
        "luettele turvaraj", "luettele vapautesi", "permissions", "capabilities",
        "freedoms", "limits", "rajoituksesi",
    )
    if intent == "assistant_permissions" or _has_any(text, capability_terms):
        boundary_scope = "assistant_boundaries" if _has_any(text, ("raja", "limit", "et saa", "turvaraj")) else "assistant_capabilities"
        return _decision(
            raw,
            boundary_scope,
            "assistant capabilities or boundaries",
            source_priority=["tool_permission_policy", "project_state", "guardrails"],
            should_use_project_state=True,
            should_answer_as_tool=True,
            confidence=0.94,
            reason="capability/boundary question should answer directly from local policy",
        )

    project_terms = (
        "projektimme", "tama projekti", "tämä projekti", "local ai workspace",
        "projektin tila", "projektin suunta", "seuraava kehitysaskel",
        "mita muuttui", "mitä muuttui", "mika muuttui", "mikä muuttui",
        "miksi me rakennamme", "pitäisikö rajoja", "pitaisiko rajoja",
        "keventaa", "keventää", "parantaa kaytosta", "parantaa käytöstä",
        "palautamme sateen", "palautamme säteen", "vähemmän jäykän", "vahemman jaykan",
    )
    if intent in {"project_identity", "project_status_request", "version_or_model_status"} or _has_any(text, project_terms):
        return _decision(
            raw,
            "project_state",
            "Local AI Workspace project state or direction",
            source_priority=["project_state", "project_files", "memory", "chat_context"],
            should_use_project_state=True,
            should_use_project_files=True,
            should_use_memory=True,
            should_use_chat_context=planning_uses_context,
            confidence=0.9,
            reason="project question should use local project state, not web by default",
        )

    official_terms = (
        "laki", "lakia", "asetus", "saados", "säädös", "virallinen",
        "vero", "verotus", "kela", "migri", "poliisi", "traficom",
        "terveysasema", "terveyskeskus", "kunta", "kaupunki", "oikeuksia minulla",
        "reklamaatio", "vuokralaisena", "sopimuksesta", "takuuhuolto",
    )
    if intent == "current_external_information" and _has_any(text, official_terms):
        return _decision(
            raw,
            "external_official_or_legal",
            "official, legal or public-service information",
            source_priority=["web", "official_sources", "source_reader"],
            should_use_web=True,
            confidence=0.9,
            reason="official/legal/public-service facts require source-grounded current sources",
        )

    local_terms = (
        "lieksa", "lieksan", "lieksassa", "nurmes", "nurmeksen", "nurmeksessa",
        "joensuu", "joensuun", "koli", "osoite", "aukiolo", "yhteystiedot",
        "autohuolto", "autohuollot", "renkaat", "rengasliike", "saa ", "sää",
    )
    if intent in {"current_external_weather", "current_external_information"} and _has_any(text, local_terms):
        return _decision(
            raw,
            "external_local_info",
            "local, current or place-dependent external information",
            source_priority=["web", "source_reader", "official_sources"],
            should_use_web=True,
            should_use_chat_context=planning_uses_context,
            confidence=0.88,
            reason="local/current information should be grounded in fresh external sources",
        )

    current_terms = (
        "uusin", "uusimmat", "viimeisimmat", "viimeisimmät", "ajantasainen",
        "tamanhetkinen", "tämänhetkinen", "nyt", "latest", "current", "recent",
        "hinta", "saatavuus", "release",
    )
    if intent in {"current_external_weather", "current_external_information"} or _has_any(text, current_terms):
        return _decision(
            raw,
            "external_current_world",
            "current external-world information",
            source_priority=["web", "source_reader"],
            should_use_web=True,
            should_use_chat_context=planning_uses_context,
            confidence=0.82,
            reason="current/changing facts need source-grounded external information",
        )

    creative_terms = (
        "kuvittele", "ideoi", "luova", "tarina", "metafora", "nimi",
        "visio", "unelma", "mielikuvitus", "creative", "imagine",
    )
    if _has_any(text, creative_terms):
        return _decision(
            raw,
            "creative_imagination",
            "creative or imaginative exploration",
            source_priority=["general_model_knowledge", "persona_layer", "chat_context"],
            should_use_general_model_knowledge=True,
            should_use_chat_context=planning_uses_context,
            should_answer_as_persona=True,
            confidence=0.78,
            reason="creative request should use imagination/persona, not factual web by default",
        )

    return _decision(
        raw,
        "timeless_general_knowledge",
        "timeless general knowledge or ordinary conversation",
        source_priority=["general_model_knowledge"],
        should_use_general_model_knowledge=True,
        should_use_chat_context=planning_uses_context,
        confidence=0.72,
        reason="no current/internal/source-specific requirement detected",
    )


def should_allow_web(grounding: GroundingDecision, *, explicit_web_requested: bool = False) -> bool:
    """Return whether web search is appropriate for the selected grounding."""
    if explicit_web_requested:
        return not grounding.should_refuse_or_boundary
    return bool(grounding.should_use_web and not grounding.should_refuse_or_boundary)


def selected_sources_for_debug(grounding: GroundingDecision) -> Dict[str, Any]:
    """Small helper for trace/debug output."""
    return grounding.route_summary()
