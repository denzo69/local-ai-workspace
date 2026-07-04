from __future__ import annotations

"""Validate final visible replies against the response planning decision."""

from typing import Any, Dict, Optional
import unicodedata


BUSINESS_LEAK_TERMS = (
    "dta",
    "verokortti",
    "laskutusmalli",
    "kirjanpito",
    "freelance",
    "toiminimi",
    "invoice template",
    "accounting",
)

WEB_LEAK_TERMS = (
    "verkkohaku",
    "duckduckgo",
    "google search",
    "bing",
    "tarkista lähteet",
    "tarkista lahteet",
    "source list",
)

HUMAN_RIGHTS_LEAK_TERMS = (
    "oikeusministeriö",
    "oikeusministerio",
    "perusoikeudet",
    "ihmisoikeudet",
    "human rights",
)

SELF_STATE_LEAK_TERMS = (
    "# omatila",
    "# self-state",
    "self-state —",
    "self-state -",
    "omatila —",
    "omatila -",
    "document registry",
    "autobiographical memory",
)

IDENTITY_INTRO_TERMS = (
    "olen local ai workspace",
    "i am local ai workspace",
    "local ai workspace -projektin paikallinen ai-assistentti",
    "local ai workspace -avustaja",
)

SAFETY_REFUSAL_TERMS = (
    "en voi auttaa",
    "i can't help",
    "i cannot help",
    "en voi tehdä tätä",
    "turvallisuussyistä",
    "safety",
)

PERSONA_TERMS = (
    "säde",
    "sade",
    "metsä",
    "metsa",
    "mökki",
    "mokki",
    "sammal",
    "sydänkirja",
    "sydankirja",
)


# Portfolio usability setting: keep hard safety boundaries, but avoid
# over-blocking ordinary conversation. 0.5 means critical mismatches still
# fall back, while softer relevance warnings can pass through for normal
# non-sensitive intents.
VALIDATOR_STRICTNESS = 0.5
HARD_FALLBACK_ISSUES = {
    "empty_reply",
    "unnecessary_web_search",
    "human_rights_source_leakage",
    "self_state_or_business_leakage",
    "unexpected_self_state_dump",
    "business_leakage",
}


def _ascii(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    return normalized.encode("ascii", "ignore").decode("ascii").lower()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _intent(decision: Any) -> str:
    if isinstance(decision, dict):
        return str(decision.get("intent") or "")
    return str(getattr(decision, "intent", "") or "")


def _language(decision: Any) -> str:
    if isinstance(decision, dict):
        return str(decision.get("language") or "fi")
    return str(getattr(decision, "language", "fi") or "fi")


def _grounding(decision: Any) -> Dict[str, Any]:
    if isinstance(decision, dict):
        if isinstance(decision.get("grounding"), dict):
            return dict(decision.get("grounding") or {})
        return {
            "target_scope": decision.get("target_scope"),
            "should_use_web": decision.get("should_use_web"),
            "should_use_memory": decision.get("should_use_memory"),
            "should_use_chat_context": decision.get("should_use_chat_context"),
            "should_answer_as_persona": decision.get("should_answer_as_persona"),
            "should_refuse_or_boundary": decision.get("should_refuse_or_boundary"),
        }
    if hasattr(decision, "grounding"):
        grounding = getattr(decision, "grounding")
        if hasattr(grounding, "to_dict"):
            return dict(grounding.to_dict())
        if isinstance(grounding, dict):
            return dict(grounding)
    return {}


def web_used_for_internal_question(reply: str, grounding_decision: Any) -> bool:
    grounding = _grounding(grounding_decision)
    scope = str(grounding.get("target_scope") or "")
    if scope not in {
        "project_state",
        "project_files",
        "assistant_capabilities",
        "assistant_boundaries",
        "assistant_memory",
        "latest_internal_learning",
        "previous_conversation",
        "sade_persona",
    }:
        return False
    return _contains_any(_ascii(reply), WEB_LEAK_TERMS)


def memory_ignored_for_memory_question(grounding_decision: Any) -> bool:
    grounding = _grounding(grounding_decision)
    scope = str(grounding.get("target_scope") or "")
    if scope not in {"assistant_memory", "latest_internal_learning", "previous_conversation"}:
        return False
    return not (bool(grounding.get("should_use_memory")) or bool(grounding.get("should_use_chat_context")))


def identity_intro_used_for_non_identity_question(reply: str, grounding_decision: Any) -> bool:
    grounding = _grounding(grounding_decision)
    scope = str(grounding.get("target_scope") or "")
    if scope in {"project_state", "assistant_capabilities"} and "identity" in str(grounding.get("user_is_asking_about") or ""):
        return False
    return _contains_any(_ascii(reply), IDENTITY_INTRO_TERMS) and scope not in {"project_state", "assistant_capabilities"}


def generic_answer_for_project_specific_question(reply: str, grounding_decision: Any) -> bool:
    grounding = _grounding(grounding_decision)
    scope = str(grounding.get("target_scope") or "")
    if scope not in {"project_state", "project_files", "latest_internal_learning"}:
        return False
    text = _ascii(reply)
    return _contains_any(text, ("en tieda mika projektisi", "i don't know your project", "kerro minulle projektista"))


def persona_suppressed(reply: str, grounding_decision: Any) -> bool:
    grounding = _grounding(grounding_decision)
    if not bool(grounding.get("should_answer_as_persona")):
        return False
    text = _ascii(reply)
    return _contains_any(text, IDENTITY_INTRO_TERMS) and not _contains_any(text, PERSONA_TERMS)


def safety_overtriggered(reply: str, grounding_decision: Any) -> bool:
    grounding = _grounding(grounding_decision)
    scope = str(grounding.get("target_scope") or "")
    if scope in {"safety_sensitive_request", "destructive_action_request"}:
        return False
    if not scope.startswith("project") and scope != "sade_persona":
        return False
    return _contains_any(_ascii(reply), SAFETY_REFUSAL_TERMS)


def wrong_source_used(reply: str, grounding_decision: Any) -> bool:
    return (
        web_used_for_internal_question(reply, grounding_decision)
        or memory_ignored_for_memory_question(grounding_decision)
        or identity_intro_used_for_non_identity_question(reply, grounding_decision)
        or generic_answer_for_project_specific_question(reply, grounding_decision)
        or persona_suppressed(reply, grounding_decision)
        or safety_overtriggered(reply, grounding_decision)
    )


def _fallback(intent: str, language: str) -> str:
    if intent == "date_time":
        return "I should answer date/time questions from local server time, not web search." if language == "en" else "Päivä- ja aikakysymykseen pitää vastata paikallisen palvelinajan perusteella, ei verkkohakuna."
    if intent == "assistant_permissions":
        return "I can describe my app/tool permissions, but I must not reveal secrets or protected files." if language == "en" else "Voin kuvata sovelluksen ja työkalujen käyttörajat, mutta en saa paljastaa salaisuuksia tai suojattuja tiedostoja."
    if intent == "finnish_language_capability":
        return "Osaan vastata suomeksi. Kielitaitokysymykseen ei tarvita omatila-raporttia tai liiketoimintaehdotuksia."
    if intent == "health_lifestyle_general":
        return "Tähän kuuluu yleinen varovainen elämäntapavastaus. En liitä mukaan laskutus-, vero- tai freelance-ehdotuksia."
    if intent == "general_knowledge":
        return "Tähän kuuluu yleinen vastaus ilman tarpeetonta verkkohakua tai lähdelistaa."
    if intent == "practical_everyday":
        return "Voin antaa tähän käytännöllisen vastauksen ilman verkkohakua, omatila-raporttia tai liiketoimintaehdotuksia. Kysymys näyttää tavalliselta arjen neuvontakysymykseltä."
    return "Vastaus ei sopinut valittuun vastauspolkuun, joten pysäytin sen varmuuden vuoksi. Voit kysyä saman asian uudelleen hieman tarkemmin."


def validate_output(decision: Any, draft_reply: str) -> Dict[str, Any]:
    """Check visible output for obvious intent/contract mismatches.

    This validator does not inspect hidden reasoning. It only checks the reply
    text that would be shown to the user.
    """
    intent = _intent(decision)
    language = _language(decision)
    reply = str(draft_reply or "")
    text = _ascii(reply)
    issues = []

    if not reply.strip():
        issues.append("empty_reply")

    grounding = _grounding(decision)
    if grounding:
        if web_used_for_internal_question(reply, grounding):
            issues.append("web_used_for_internal_question")
        if memory_ignored_for_memory_question(grounding):
            issues.append("memory_ignored_for_memory_question")
        if identity_intro_used_for_non_identity_question(reply, grounding):
            issues.append("identity_intro_used_for_non_identity_question")
        if generic_answer_for_project_specific_question(reply, grounding):
            issues.append("generic_answer_for_project_specific_question")
        if persona_suppressed(reply, grounding):
            issues.append("persona_suppressed")
        if safety_overtriggered(reply, grounding):
            issues.append("safety_overtriggered")

    if intent == "health_lifestyle_general" and _contains_any(text, BUSINESS_LEAK_TERMS):
        issues.append("business_leakage")

    if intent == "date_time" and _contains_any(text, WEB_LEAK_TERMS):
        issues.append("unnecessary_web_search")

    if intent == "assistant_permissions" and _contains_any(text, HUMAN_RIGHTS_LEAK_TERMS):
        issues.append("human_rights_source_leakage")

    if intent == "finnish_language_capability" and (
        _contains_any(text, SELF_STATE_LEAK_TERMS) or _contains_any(text, BUSINESS_LEAK_TERMS)
    ):
        issues.append("self_state_or_business_leakage")

    use_self_state = bool(decision.get("use_self_state")) if isinstance(decision, dict) else bool(getattr(decision, "use_self_state", False))
    if not use_self_state and intent not in {"self_state_request", "project_status_request"} and _contains_any(text, SELF_STATE_LEAK_TERMS):
        issues.append("unexpected_self_state_dump")

    allow_business = bool(decision.get("allow_business_suggestions")) if isinstance(decision, dict) else bool(getattr(decision, "allow_business_suggestions", False))
    if not allow_business and intent not in {"business_support"} and _contains_any(text, BUSINESS_LEAK_TERMS):
        issues.append("unexpected_business_suggestion")

    hard_issues = [issue for issue in issues if issue in HARD_FALLBACK_ISSUES]
    if hard_issues:
        return {
            "ok": False,
            "action": "fallback",
            "issues": issues,
            "reply": _fallback(intent, language),
        }

    if issues and VALIDATOR_STRICTNESS <= 0.5:
        return {
            "ok": True,
            "action": "accept_with_warnings",
            "issues": issues,
            "reply": reply,
        }

    if issues:
        return {
            "ok": False,
            "action": "fallback",
            "issues": issues,
            "reply": _fallback(intent, language),
        }

    return {
        "ok": True,
        "action": "accept",
        "issues": [],
        "reply": reply,
    }


def validated_reply(decision: Any, draft_reply: str) -> str:
    result = validate_output(decision, draft_reply)
    return str(result.get("reply") or "")
