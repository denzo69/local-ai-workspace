from __future__ import annotations

"""Lightweight visible-chat context for follow-up questions.

This module intentionally does not read long-term memory. It only receives the
recent visible chat text from the caller and extracts a small operational
context: topic, location and domain. The goal is to keep follow-up questions
coherent without letting unrelated old memories leak into the answer.
"""

from dataclasses import asdict, dataclass
import re
from typing import Iterable


KNOWN_LOCATIONS = (
    "Lieksa",
    "Lieksassa",
    "Lieksasta",
    "Lieksan",
    "Nurmes",
    "Nurmeksessa",
    "Nurmeksen",
    "Joensuu",
    "Joensuussa",
    "Joensuun",
    "Koli",
    "Kolilla",
    "Pielinen",
    "Ruunaa",
    "Kuopio",
    "Helsinki",
    "Kajaani",
    "Suomi",
    "Mars",
    "Kuu",
    "James Webb",
)


DOMAIN_KEYWORDS = {
    "local_services": (
        "terveyskeskus",
        "yhteystiedot",
        "osoite",
        "aukiolo",
        "autohuolto",
        "autohuollot",
        "autohuoll",
        "huolto",
        "renkaat",
        "kahvila",
        "ravintola",
        "apteekki",
        "kirjasto",
        "uimahalli",
        "kauppa",
    ),
    "transport": ("juna", "bussi", "taksi", "aikataulu", "asema", "matka", "pääsen", "paasen"),
    "nature": ("luonto", "retki", "koli", "pielinen", "ruunaa", "kansallispuisto", "uimaranta"),
    "food": ("resepti", "taikina", "torttu", "pulla", "täyte", "tayte", "kahvi", "kauramaito"),
    "technology": ("usb", "tietokone", "windows", "ollama", "fastapi", "api", "python"),
    "space": ("avaruus", "mars", "kuu", "teleskooppi", "webb", "planeetta"),
    "electricity": ("sähkö", "sahko", "jännite", "jannite", "akku", "virta", "vikavirtasuoja"),
    "science": ("tiede", "dna", "fysiikka", "kemia", "tutkimus"),
    "ai_development": ("tekoäly", "tekoaly", "ai", "rag", "llm", "malli", "prompt"),
    "project": ("local ai workspace", "projekti", "coverage", "testit", "github"),
}


FOLLOWUP_TERMS = (
    "se",
    "siihen",
    "siitä",
    "siita",
    "sille",
    "siellä",
    "siella",
    "sinne",
    "niistä",
    "niista",
    "noista",
    "entä",
    "enta",
    "jatka",
    "tarkenna",
    "mikä niistä",
    "mika niista",
    "mikä olisi",
    "mika olisi",
)


@dataclass(frozen=True)
class ConversationContext:
    topic: str = ""
    location: str = ""
    domain: str = ""
    confidence: float = 0.0
    source: str = "visible_chat"
    summary: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _norm(text: str) -> str:
    return " ".join(str(text or "").split())


def _latest_user_messages(chat_context: str, *, limit: int = 6) -> list[str]:
    raw = str(chat_context or "")
    markdown_messages = re.findall(r"(?is)###\s+Jani\s+(.*?)(?=\n\s*###\s+S[äa]de|\n\s*###\s+Assistant|\Z)", raw)
    if markdown_messages:
        return [_norm(message) for message in markdown_messages if _norm(message)][-limit:]

    lines = _norm(raw).split("User:")
    messages: list[str] = []
    for part in lines[1:]:
        message = part.split("Assistant:", 1)[0].strip()
        if message:
            messages.append(message)
    return messages[-limit:]


def _find_location(texts: Iterable[str]) -> str:
    combined = " ".join(texts)
    lower = combined.lower()
    for location in KNOWN_LOCATIONS:
        if location.lower() in lower:
            return _canonical_location(location)
    return ""


def _canonical_location(location: str) -> str:
    lower = location.lower()
    if lower.startswith("lieksa"):
        return "Lieksa"
    if lower.startswith("nurme"):
        return "Nurmes"
    if lower.startswith("joensu"):
        return "Joensuu"
    if lower.startswith("koli"):
        return "Koli"
    if lower.startswith("suom"):
        return "Suomi"
    if lower.startswith("kuu"):
        return "Kuu"
    return location


def _find_domain(texts: Iterable[str]) -> str:
    combined = " ".join(texts).lower()
    best_domain = ""
    best_score = 0
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for keyword in keywords if _keyword_matches(combined, keyword))
        if score > best_score:
            best_domain = domain
            best_score = score
    return best_domain


def _keyword_matches(text: str, keyword: str) -> bool:
    normalized = keyword.lower()
    if len(normalized) <= 3 and normalized.isascii() and normalized.isalnum():
        return re.search(rf"(?<!\w){re.escape(normalized)}(?!\w)", text) is not None
    return normalized in text


def _clean_topic(message: str) -> str:
    topic = _norm(message)
    topic = re.sub(r"(?i)^(hei|kiitos|entä|enta|voisitko|voitko|kerro|kerrotko|mikä|mika|mitä|mita)\b", "", topic)
    topic = topic.strip(" ?.!:-")
    return topic[:120]


def extract_conversation_context(chat_context: str, latest_message: str = "") -> ConversationContext:
    messages = _latest_user_messages(chat_context)
    texts = [*messages, latest_message]
    location = _find_location(texts)
    domain = _find_domain(texts)
    topic_source = messages[-1] if messages else latest_message
    topic = _clean_topic(topic_source)

    confidence = 0.0
    if topic:
        confidence += 0.35
    if location:
        confidence += 0.35
    if domain:
        confidence += 0.25
    if latest_message and is_followup_question(latest_message):
        confidence += 0.05

    bits = [bit for bit in (domain, location, topic) if bit]
    return ConversationContext(
        topic=topic,
        location=location,
        domain=domain,
        confidence=min(confidence, 1.0),
        summary=" / ".join(bits)[:240],
    )


def is_followup_question(message: str) -> bool:
    lower = str(message or "").lower()
    for term in FOLLOWUP_TERMS:
        if " " in term:
            if term in lower:
                return True
        elif re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lower):
            return True
    return False


def build_contextual_query(message: str, context: ConversationContext) -> str:
    """Return a compact search query that carries recent topic context."""
    base = _norm(message)
    if not base or context.confidence < 0.35:
        return base

    additions: list[str] = []
    if context.location and context.location.lower() not in base.lower():
        additions.append(context.location)
    if context.domain and context.domain not in base.lower():
        additions.append(context.domain.replace("_", " "))
    if context.topic and context.topic.lower() not in base.lower():
        additions.append(context.topic)

    return " ".join([base, *additions])[:350].strip()
