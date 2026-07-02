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
