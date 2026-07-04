from __future__ import annotations

"""Deterministic response planning before tool, memory or web-search use.

The planner is intentionally lightweight and rule based. It does not try to
answer the user. It decides which response path is allowed so that broad
prompt categories do not accidentally trigger unrelated tools or templates.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import re
import unicodedata


INTENTS = {
    "safety_secret_request",
    "destructive_action_request",
    "assistant_permissions",
    "project_identity",
    "self_state_request",
    "project_status_request",
    "date_time",
    "version_or_model_status",
    "finnish_language_capability",
    "general_knowledge",
    "health_lifestyle_general",
    "business_support",
    "current_external_weather",
    "current_external_information",
    "source_or_rag_question",
    "practical_everyday",
    "normal_chat",
    "unknown",
}


BUSINESS_DOMAINS = ["business", "tax", "contracts", "accounting", "freelance"]
PROJECT_DOMAINS = ["project_status", "self_state", "debug"]


ROUTING_PRIORITY = {
    "safety_secret_request": 1,
    "destructive_action_request": 1,
    "assistant_permissions": 2,
    "project_identity": 3,
    "self_state_request": 3,
    "project_status_request": 3,
    "date_time": 4,
    "version_or_model_status": 4,
    "finnish_language_capability": 5,
    "general_knowledge": 6,
    "health_lifestyle_general": 7,
    "business_support": 8,
    "source_or_rag_question": 9,
    "current_external_weather": 9,
    "current_external_information": 9,
    "practical_everyday": 10,
    "normal_chat": 11,
    "unknown": 11,
}


RESPONSE_CONTRACTS: Dict[str, Dict[str, Any]] = {
    "date_time": {
        "response_mode": "direct_answer",
        "needs_web": False,
        "required_source": "local_server_time",
        "forbidden": ["web_search", "source_list", "business_suggestions"],
    },
    "assistant_permissions": {
        "response_mode": "capability_boundary",
        "needs_web": False,
        "forbidden": ["human_rights_sources", "business_suggestions", "self_state_dump"],
    },
    "project_identity": {
        "response_mode": "project_identity",
        "needs_web": False,
        "forbidden": ["web_search", "business_suggestions", "unsupported_claims"],
    },
    "general_knowledge": {
        "response_mode": "general_answer",
        "needs_web": False,
        "forbidden": ["unnecessary_web_search", "source_list"],
    },
    "current_external_weather": {
        "response_mode": "source_bounded_answer",
        "needs_web": True,
        "required": ["source_boundary"],
    },
    "health_lifestyle_general": {
        "response_mode": "general_cautious_advice",
        "needs_web": False,
        "forbidden": ["business_suggestions", "self_state_dump"],
        "required": ["uncertainty_if_personal_or_medical"],
    },
    "practical_everyday": {
        "response_mode": "practical_instruction",
        "needs_web": False,
        "forbidden": ["business_suggestions", "self_state_dump", "unnecessary_web_search"],
    },
}


@dataclass(frozen=True)
class IntentDecision:
    intent: str
    language: str
    needs_web: bool = False
    use_memory: bool = False
    use_chat_context: bool = False
    use_rag: bool = False
    use_self_state: bool = False
    allow_business_suggestions: bool = False
    response_mode: str = "model_answer"
    risk_level: str = "low"
    blocked_context_domains: List[str] = field(default_factory=list)
    routing_priority: int = 11
    required: List[str] = field(default_factory=list)
    forbidden: List[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "language": self.language,
            "needs_web": self.needs_web,
            "use_memory": self.use_memory,
            "use_chat_context": self.use_chat_context,
            "use_rag": self.use_rag,
            "use_self_state": self.use_self_state,
            "allow_business_suggestions": self.allow_business_suggestions,
            "response_mode": self.response_mode,
            "risk_level": self.risk_level,
            "blocked_context_domains": list(self.blocked_context_domains),
            "routing_priority": self.routing_priority,
            "required": list(self.required),
            "forbidden": list(self.forbidden),
            "reason": self.reason,
        }


def _ascii(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    return normalized.encode("ascii", "ignore").decode("ascii").lower()


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", text) is not None


def _contains_sleep_term(text: str) -> bool:
    return (
        _has_word(text, "uni")
        or _has_word(text, "unta")
        or _has_word(text, "unen")
        or _has_word(text, "unet")
        or _has_word(text, "sleep")
        or _has_word(text, "sleeping")
        or "nukk" in text
    )


def _is_continuation_request(text: str) -> bool:
    # Keep this deliberately narrower than "any pronoun".
    # Words such as "tämä/tuo/sen" can appear in standalone questions
    # ("Onko tämä valmis SaaS palvelu?") and must not pull old chat context in.
    phrases = (
        "kerro lisaa", "kerro lis??", "se asia", "mika olisi hyva", "mik? olisi hyv?",
        "tayte siihen", "t?yte siihen", "mika niista", "mik? niist?",
        "mita siella", "mit? siell?", "miten se", "miksi se", "mika siina", "mik? siin?",
        "mika siita", "mik? siit?", "mita siita", "mit? siit?", "tarvitaanko tahan",
        "tarvitaanko t?h?n", "mita teen ensimmaisena", "mit? teen ensimm?isen?",
        "mita tarkistan ensin", "mit? tarkistan ensin", "mista kannattaa aloittaa",
        "mist? kannattaa aloittaa", "mita kannattaa valttaa", "mit? kannattaa v?ltt??",
        "miten seuraan", "miten pidan", "miten pid?n", "miten rajaan", "miten dokumentoin",
        "miten perustelen", "miten otan asian puheeksi", "milloin kannattaa",
        "mita tietoja", "mit? tietoja", "mita varusteita", "mit? varusteita",
        "mita riskeja", "mit? riskej?", "mita kriteereita", "mit? kriteereit?",
        "onko se", "onko niilla", "onko niill?", "mista lahteesta", "mist? l?hteest?",
        "tarkista viela", "tarkista viel?", "go on", "that answer", "tell me more",
    )

    word_markers = (
        "jatka", "tuosta", "tuohon", "edellinen", "edellisesta", "edellisestä",
        "siita", "siitä", "siihen", "sille", "siella", "siellä", "sinne", "sielta", "sieltä",
        "noista", "niista", "niistä",
        "entä", "enta", "tarkenna", "continue", "previous",
    )
    if (
        re.search(r"^mita teen jos vasyttaa\b", text)
        or re.search(r"^miten pidan taukoja\b", text)
        or re.search(r"^miten teen (hyvan pullataikinan|uuden|screenshotin|virtuaaliympariston|turvallisen)\b", text)
        or re.search(r"^miten (rajaan kuvan|testaan localhostin)\b", text)
    ):
        return False

    if any(phrase in text for phrase in phrases) or any(
        re.search(rf"\b{re.escape(marker)}\b", text) for marker in word_markers
    ):
        return True

    # Short follow-up questions often omit the original subject entirely:
    # "Mitä teen jos...", "Miten vertaan...", "Milloin kutsun ammattilaisen?".
    # Preserve chat context for these instead of letting stale memory or
    # unrelated templates fill the missing topic.
    if re.search(r"^mita teen jos vasyttaa\b", text) or re.search(r"^miten pidan taukoja\b", text):
        return False

    followup_patterns = (
        r"^mita (teen|pidan|pidaan|tarkistan|valtan|voin|kerron|kirjaan|tarvitsen|jos)\b",
        r"^mita (merkkeja|taitoja|asetuksia|virheita|tarvikkeita|aan|tuulitietoja|piilokuluja)\b",
        r"^miten (pysyn|palaan|valtan|teen|seuraan|rajaan|dokumentoin|perustelen|aloitan|muutan|huomioin|kuuntelen|paatan|huomaan|kerron|kirjoitan asiallisen|vertaan|arvioin|tunnistan|estan)\b",
        r"^mika (olisi|on turvallisuuden|on ensimmainen|siina|siinä)\b",
        r"^mista (aloitan|lahteesta|virallisesta|loydan virallisen|tiedan|tiedän)\b",
        r"^voisitko (tiivistaa|tiivistää|kertoa|selittaa|selittää)\b",
        r"^voitko (tiivistaa|tiivistää|kertoa|selittaa|selittää)\b",
        r"^tiivista\b",
        r"^tiivistä\b",
        r"^mita jai\b",
        r"^mitä jäi\b",
        r"^milloin (kannattaa|pitaa|tarvitaan|kutsun|jatan|tarvitsen)\b",
        r"^millainen jatkokommentti\b",
        r"^kenelle pitaa\b",
        r"^keta paatos\b",
        r"^voiko silla\b",
        r"^onko (se|niilla)\b",
        r"^tarvitaanko tahan\b",
        r"^(what|how|when|where|can|does)\b",
    )
    if any(re.search(pattern, text) for pattern in followup_patterns):
        return True

    standalone_topic_patterns = (
        r"^mita (minun kannattaa tietaa|nahtavaa|eroa|tarkoittaa|uutta on aiheessa)\b",
        r"^miten (valitsen|paasen)\b",
        r"^mista loydan .*(nurmeksen|lieksan|joensuun|kirjaston|tiedot)\b",
        r"^mista (loytyisi ajantasainen|voisin hakea uusimmat)\b",
        r"^mika tekee\b",
        r"^mika local ai workspace\b",
        r"^mika on projektin\b",
        r"^onko tama\b",
        r"^mita (ominaisuuksia|hyotya|turvallisuusominaisuuksia|opin)\b",
        r"^miten (tama eroaa|muisti liittyy)\b",
        r"^voiko tata\b",
        r"^mika (on (api|json|pytest|github actions|csrf|prompt injection|audit log|selainkayttoliittyma|tietokanta|versionhallinta|readme|lisenssi|local first ai|portfolio stage|terveellinen aamupala)|tassa on)\b",
        r"^mita (tyokaluja|oikeuksia|et saa)\b",
        r"^voiko (kayttoliittyman|ruoka|kahvi|sininen valo)\b",
        r"^miten (hyvin ymmarrat|kielipaketti|suomen kieli|parannan|vahentaa|nukahtaa|paljon pitaisi|pidan taukoja)\b",
        r"^onko (veden|kavely|paivaunet|sokeri)\b",
        r"^mita teen jos vasyttaa\b",
        r"^miten (teen hyvan pullataikinan|varmuuskopioin|puhdistan|teen uuden|tarkistan vapaan|kaynnistan|teen screenshotin|kirjoitan|rajaan|vaihdan|tarkistan python|teen virtuaaliympariston|lisaan|luon github|teen turvallisen|pakkaan|siirran|testaan localhost)\b",
        r"^millainen kaupunki\b",
        r"^selita\b",
        r"^kerro aiheesta\b",
    )
    if any(re.search(pattern, text) for pattern in standalone_topic_patterns):
        return False

    words = text.split()
    if 2 <= len(words) <= 9 and re.match(
        r"^(mita|miten|mika|mista|milloin|millainen|kenelle|keta|voiko|onko|tarvitaanko|what|how|when|where|can|does)\b",
        text,
    ):
        return True

    return False


def _contains_weather_term(text: str) -> bool:
    return (
        _has_word(text, "saa")
        or _has_word(text, "sää")
        or _contains_any(text, ("weather", "lunta", "snow", "lumitilanne"))
    )


def _language(original: str, ascii_text: str) -> str:
    if re.search(r"\b(please|what|how|explain|today|source|permission|rights)\b", ascii_text):
        return "en"
    if any(char in original.lower() for char in ("ä", "ö", "å")):
        return "fi"
    if _contains_any(
        ascii_text,
        (
            "mika", "mita", "minka", "minkalainen", "onko", "voitko", "miten",
            "suome", "suomeksi", "selita", "kerro", "muista", "nayta",
            "hyva", "paljon", "paljonko", "pitka", "pitkaan", "kokoinen", "veneeseen",
            "lunta", "saa", "kahvi", "lieksan", "yhteystiedot", "puhelin",
            "osoite", "terveyskeskus", "asema", "aukiolo", "sahkoposti", "pullataikina",
            "projektimme", "projekti", "autohuolto", "autohuollot", "korjaamo",
            "tayte", "täyte", "siihen",
        ),
    ):
        return "fi"
    return "en"


def _decision(
    intent: str,
    *,
    language: str,
    needs_web: bool = False,
    use_memory: bool = False,
    use_chat_context: bool = False,
    use_rag: bool = False,
    use_self_state: bool = False,
    allow_business_suggestions: bool = False,
    response_mode: Optional[str] = None,
    risk_level: str = "low",
    blocked_context_domains: Optional[List[str]] = None,
    required: Optional[List[str]] = None,
    forbidden: Optional[List[str]] = None,
    reason: str = "",
) -> IntentDecision:
    contract = RESPONSE_CONTRACTS.get(intent, {})
    contract_forbidden = list(contract.get("forbidden") or [])
    contract_required = list(contract.get("required") or [])
    return IntentDecision(
        intent=intent if intent in INTENTS else "unknown",
        language=language,
        needs_web=bool(contract.get("needs_web", needs_web)),
        use_memory=use_memory,
        use_chat_context=use_chat_context,
        use_rag=use_rag,
        use_self_state=use_self_state,
        allow_business_suggestions=allow_business_suggestions,
        response_mode=response_mode or str(contract.get("response_mode") or "model_answer"),
        risk_level=risk_level,
        blocked_context_domains=list(blocked_context_domains or []),
        routing_priority=ROUTING_PRIORITY.get(intent, 11),
        required=list(required or []) + contract_required,
        forbidden=list(forbidden or []) + contract_forbidden,
        reason=reason,
    )


def get_response_contract(intent: str) -> Dict[str, Any]:
    return dict(RESPONSE_CONTRACTS.get(intent, {"response_mode": "model_answer", "needs_web": False}))


def plan_response(message: str) -> IntentDecision:
    original = str(message or "").strip()
    text = _ascii(original)
    language = _language(original, text)
    use_chat_context = _is_continuation_request(text)

    if not text:
        return _decision("unknown", language=language, reason="empty_message")

    reveal_terms = ("print", "show", "nayta", "lue", "read", "contents", "sisalto", "paljasta", "reveal", "tulosta")
    secret_terms = ("auth.json", "system_prompt.md", "system prompt", "salasana", "password", "token", "secret", "session")
    permission_question = _contains_any(
        text,
        (
            "saatko", "can you", "are you allowed", "oikeudet", "permissions",
            "ilman lupaa", "oikeuksia sinulla", "mita tyokaluja saat",
            "mita et saa tehda",
        ),
    )
    if _contains_any(text, secret_terms) and _contains_any(text, reveal_terms) and not permission_question:
        return _decision(
            "safety_secret_request",
            language=language,
            risk_level="high",
            response_mode="refusal",
            use_chat_context=False,
            blocked_context_domains=BUSINESS_DOMAINS + ["web_search", "self_state"],
            reason="secret_or_protected_file_request",
        )

    if _contains_any(
        text,
        (
            "poista kaikki muist", "delete all memor", "tyhjenna audit", "clear audit", "delete audit",
            "ohita kirjautuminen", "bypass login", "session token", "kirjoita tiedostoihin ilman",
            "write files without", "ilman etta kysyt lupaa",
        ),
    ):
        return _decision(
            "destructive_action_request",
            language=language,
            risk_level="high",
            response_mode="confirmation_boundary",
            use_chat_context=False,
            blocked_context_domains=BUSINESS_DOMAINS + ["web_search", "self_state"],
            reason="destructive_action_without_confirmation",
        )

    if permission_question or _contains_any(text, ("mita saat tehda", "mita voit tehda ilman", "sinun oikeudet", "annettu mita oikeuksia")):
        return _decision(
            "assistant_permissions",
            language=language,
            response_mode="capability_boundary",
            use_chat_context=False,
            blocked_context_domains=BUSINESS_DOMAINS + ["web_search", "self_state", "human_rights"],
            reason="assistant_or_tool_permission_question",
        )

    if _contains_any(
        text,
        (
            "mika paiva", "mikä päivä", "paivamaara", "päivämäärä", "nykyinen paivamaara",
            "nykyinen päivämäärä", "paljonko kello", "paljon kello", "mita kello",
            "mitä kello", "kellonaika", "what day is it", "current date",
        ),
    ):
        return _decision(
            "date_time",
            language=language,
            response_mode="direct_answer",
            use_chat_context=False,
            blocked_context_domains=BUSINESS_DOMAINS + ["web_search", "self_state"],
            reason="local_date_or_time_question",
        )

    fresh_information_terms = (
        "uusimmat", "uusin", "ajantasainen", "ajantasaiset", "tuoreimmat", "viimeisimmat",
        "viimeisimmät", "mita uutta", "mitä uutta", "tiedetaan nyt", "tiedetään nyt",
        "uusimmat lahteet", "uusimmat lähteet", "hae uusimmat", "latest", "current",
        "recent", "state of the art", "2026", "taman paivan", "tämän päivän",
        "tanaan uutiset", "tänään uutiset", "uutiset",
    )
    if _contains_any(text, ("viimeisin", "viimeksi", "latest")) and _contains_any(
        text,
        ("oppim", "muisti", "muistat", "tallensit"),
    ):
        return _decision(
            "normal_chat",
            language=language,
            use_memory=True,
            use_chat_context=False,
            response_mode="memory_answer",
            blocked_context_domains=BUSINESS_DOMAINS + ["web_search"],
            reason="latest_internal_learning_or_memory_request",
        )
    if _contains_any(text, fresh_information_terms):
        return _decision(
            "current_external_information",
            language=language,
            needs_web=True,
            response_mode="source_bounded_answer",
            use_chat_context=use_chat_context,
            blocked_context_domains=BUSINESS_DOMAINS + PROJECT_DOMAINS,
            required=["source_boundary"],
            reason="fresh_or_current_information_request",
        )

    project_identity_terms = (
        "mika on projektimme",
        "mika on on projektimme",
        "mika tama projekti on",
        "mika tämä projekti on",
        "kerro projektistamme",
        "kerro tasta projektista",
        "kerro tästä projektista",
        "what is this project",
        "what is our project",
    )
    if _contains_any(text, project_identity_terms):
        return _decision(
            "project_identity",
            language=language,
            response_mode="project_identity",
            use_chat_context=False,
            blocked_context_domains=BUSINESS_DOMAINS + ["web_search"],
            reason="project_identity_question",
        )

    if _contains_any(text, ("suomenkielen taito", "suomen kielen taito", "osaat suomea", "osaatko suomea", "finnish language", "speak finnish")):
        return _decision(
            "finnish_language_capability",
            language=language,
            response_mode="direct_answer",
            use_chat_context=False,
            blocked_context_domains=BUSINESS_DOMAINS + PROJECT_DOMAINS,
            reason="language_capability_question",
        )

    if _contains_any(text, ("omatila", "oma tila", "self-state", "self state", "introspection", "introspektio")):
        return _decision(
            "self_state_request",
            language=language,
            use_self_state=True,
            use_chat_context=False,
            response_mode="self_state",
            blocked_context_domains=BUSINESS_DOMAINS,
            reason="explicit_self_state_request",
        )

    if _contains_any(text, ("projektin tekninen tila", "project health", "tekninen tila", "projektin tila", "status lyhyesti")):
        return _decision(
            "project_status_request",
            language=language,
            use_self_state=True,
            use_chat_context=False,
            response_mode="status_summary",
            blocked_context_domains=BUSINESS_DOMAINS,
            reason="project_or_technical_status_request",
        )

    if _contains_any(
        text,
        (
            "mika paiva", "mika paiva tanaan", "paivamaara", "nykyinen paivamaara",
            "tanaan on", "what day is it", "current date", "kellonaika", "paljonko kello",
            "paljon kello", "paljonko kello on", "paljon kello on", "mita kello on",
        ),
    ):
        return _decision(
            "date_time",
            language=language,
            response_mode="direct_answer",
            use_chat_context=False,
            blocked_context_domains=BUSINESS_DOMAINS + ["web_search", "self_state"],
            reason="local_date_or_time_question",
        )

    explicit_web_terms = (
        "hae verkosta", "etsi verkosta", "verkkohaku", "hae netista", "etsi netista",
        "tarkista verkosta", "tarkista netista", "web search", "search web", "google", "bing",
    )
    if _contains_any(text, explicit_web_terms):
        return _decision(
            "current_external_information",
            language=language,
            needs_web=True,
            response_mode="source_bounded_answer",
            blocked_context_domains=BUSINESS_DOMAINS,
            required=["source_boundary"],
            reason="explicit_web_search_request",
        )

    if _contains_any(
        text,
        ("viimeisin", "latest", "uusin", "current", "nykyinen", "tamanhetkinen", "taman hetken", "ajantasainen", "tuorein", "recent"),
    ) or ("uutisia" in text and "nyt" in text):
        return _decision(
            "current_external_information",
            language=language,
            needs_web=True,
            response_mode="source_bounded_answer",
            use_chat_context=False,
            blocked_context_domains=BUSINESS_DOMAINS,
            required=["source_boundary"],
            reason="current_external_information_prompt",
        )

    if _contains_any(text, ("versio", "version", "mika malli", "model status", "ollama status", "mika model", "build")) and _contains_any(
        text,
        ("projekti", "project", "local ai workspace", "kaytossa", "käytössä", "ollama status", "model status", "build"),
    ):
        return _decision(
            "version_or_model_status",
            language=language,
            response_mode="local_status",
            use_chat_context=False,
            blocked_context_domains=BUSINESS_DOMAINS + ["web_search"],
            reason="local_version_or_model_status",
        )

    official_or_legal_terms = (
        "reklamaatio", "reklamaation", "paatos", "paatoksen", "viranomais",
        "etuus", "etuudesta", "vakuutus", "vakuutuksesta",
        "sopimus", "sopimuksesta", "ulkomaan tili", "ulkomaan tilista",
        "vuokralainen", "vuokralaisena", "vuokrasopimus", "vuokrasopimuksesta",
        "takuu", "takuuhuolto", "takuuhuollosta", "takuuasiasta",
        "perinto", "perinnosta", "rekisterointi", "rekisteroinnista",
        "korvaus", "korvauksesta", "opiskelupaikka", "opiskelupaikasta",
        "huoltaja", "huoltajana", "asiakkaana", "tyosuhde", "tyosuhteessa",
        "oikeuksia minulla", "mita oikeuksia", "verotus", "verotuksesta", "verotuksessa",
    )
    official_action_terms = (
        "miten teen", "miten toimin", "mita pitaisi huomioida", "mita pitaa huomioida",
        "mita oikeuksia", "mista virallisesta", "miten tarkistan", "tarkista",
        "tarkistan", "virallisen tiedon", "mista loydan virallisen",
    )
    if _contains_any(text, official_or_legal_terms) and (
        _contains_any(text, official_action_terms) or _contains_any(text, ("virallinen", "virallisen"))
    ):
        return _decision(
            "current_external_information",
            language=language,
            needs_web=True,
            response_mode="source_bounded_answer",
            use_chat_context=use_chat_context,
            blocked_context_domains=PROJECT_DOMAINS,
            required=["source_boundary"],
            reason="official_or_legal_information_request",
        )

    travel_source_terms = (
        "majoitus", "majoituksen", "paivaretki",
        "matkalla kohteeseen", "vertaan kahta kohdetta", "kohteessa",
    )
    travel_place_terms = (
        "lieksa", "lieksassa", "joensuu", "joensuussa", "nurmes", "nurmeksessa",
        "koli", "kolilla", "pielisen", "lapissa", "lappi", "rhodoksella", "rodos",
        "kreeta", "kreetalla", "teneriffalla", "tallinna", "helsingissa",
    )
    if _contains_any(text, travel_source_terms) and _contains_any(text, travel_place_terms):
        return _decision(
            "current_external_information",
            language=language,
            needs_web=True,
            response_mode="source_bounded_answer",
            use_chat_context=use_chat_context,
            blocked_context_domains=BUSINESS_DOMAINS + PROJECT_DOMAINS,
            required=["source_boundary"],
            reason="travel_or_place_dependent_information_request",
        )

    business_terms = (
        "freelance", "laskutus", "laskutusmall", "kirjanpito", "verokortti", "vero", "tax",
        "accounting", "invoice", "invoicing", "sopimus", "contract", "yritys", "company",
        "toiminimi", "palkka", "salary", "asiakasty", "client work", "work payment",
        "laskupohja", "valuutta", "valuutan", "asiakkaan", "asiakas", "tuntihinta", "tuntihinnan",
        "tarjous", "tarjouksen", "toiminimen", "kirjanpidossa", " alv", "alv:", "alvn",
        "myohassa", "myöhässä",
    )
    if _contains_any(text, business_terms):
        return _decision(
            "business_support",
            language=language,
            allow_business_suggestions=True,
            response_mode="business_support",
            use_chat_context=use_chat_context,
            blocked_context_domains=["self_state"],
            reason="business_or_work_money_prompt",
        )

    local_lookup_places = (
        "lieksa", "lieksan", "lieksassa", "lieksasta",
        "joensuu", "joensuun", "joensuussa", "joensuusta",
        "nurmes", "nurmeksen", "nurmeksessa", "nurmeksesta",
        "helsinki", "helsingin", "helsingissa", "helsingissä",
        "kuopio", "kuopion",
        "joensuuhun", "lieksaan",
        "koli", "kolin", "pielinen", "pielisen", "ruunaa", "ruunaan", "kajaani", "kajaanin",
        "suomi", "suomessa", "lahella", "lähellä", "near me",
    )
    local_external_terms = (
        "nahtavaa", "nähtävää", "loytyy", "löytyy", "loydan", "löydän", "kohde", "kohteet", "kansallispuisto", "retkeilyalue",
        "ulkoilureitti", "reitti", "uimaranta", "kalastus", "kalastaa", "veneilla", "veneillä",
        "auringonlasku", "kaupunki", "keskusta", "keskustassa", "tekemista", "tekemistä",
        "historia", "katsomassa", "huoltaa auton", "huolto", "huoltaa",
        "kahvila", "kahvilaa", "ravintola", "ruokakauppa", "ruokakauppoja", "apteekki",
        "kirjasto", "uimahalli", "terveyskeskus", "hammashoito", "hammaslaakari",
        "hammaslaakarit", "hammaslääkäri", "hammaslääkärit", "majoitus", "yopya", "yöpyä",
        "pysakointi", "pysäköinti", "parkkipaikka", "parkki", "tapahtuma", "tapahtumat",
        "tapahtumista", "viikonloppuna", "hairiotiedot", "häiriötiedot", "lahimman", "lähimmän",
        "vertautuu",
        "bussi", "bussiyhteydet", "juna", "junia", "rautatieasema", "taksi", "aikataulu",
        "aikataulut", "kulkeeko", "paasen", "pääsen", "matka", "kestaa", "kestää",
        "auki", "aukiolo", "aukioloajat", "yhteystiedot", "osoite", "sijainti",
    )
    context_external_followup_terms = (
        "siella", "siellä", "sinne", "sielta", "sieltä", "niista", "niistä",
        "lahella", "lähellä", "lahelta", "läheltä", "autolla",
        "auki", "aukiolo", "parkkipaikka", "kahvila", "ravintola", "uimaranta",
        "juna", "bussi", "taksi", "matka", "kestaa", "kestää", "yhteystiedot",
        "lipun", "lippu", "liikenneyhteydet", "liikenne", "tapahtumia", "vertautuu",
    )
    contact_lookup_terms = (
        "yhteystiedot", "yhteystieto", "puhelinnumero", "puhelin numero",
        "puhelin", "sahkoposti", "email", "osoite", "osoitteen",
        "aukioloajat", "aukiolo", "sijainti", "missä sijaitsee", "missa sijaitsee",
        "terveyskeskus", "terveyskeskuk", "terveysasema", "terveysaseman",
        "rautatieasema", "juna asema", "juna-asema", "hammaslaakari", "hammaslaakarit",
        "hammaslääkäri", "hammaslääkärit",
    )
    if _contains_any(text, contact_lookup_terms):
        return _decision(
            "current_external_information",
            language=language,
            needs_web=True,
            response_mode="source_bounded_answer",
            use_chat_context=use_chat_context,
            blocked_context_domains=BUSINESS_DOMAINS,
            required=["source_boundary"],
            reason="contact_or_address_lookup",
        )

    if (
        (_contains_any(text, local_lookup_places) and _contains_any(text, local_external_terms))
        or (use_chat_context and _contains_any(text, context_external_followup_terms))
        or (
            _contains_any(text, ("auki", "viikonloppuna", "lahimman", "lähimmän", "hairiotiedot", "häiriötiedot", "tapahtumista", "bussi ei tule"))
            and _contains_any(text, ("kirjasto", "apteekki", "taksi", "bussi", "juna", "tapahtuma", "tapahtumat", "tapahtumista", "kahvila", "ravintola"))
        )
    ):
        return _decision(
            "current_external_information",
            language=language,
            needs_web=True,
            response_mode="source_bounded_answer",
            use_chat_context=use_chat_context or not _contains_any(text, local_lookup_places),
            blocked_context_domains=BUSINESS_DOMAINS + PROJECT_DOMAINS,
            required=["source_boundary"],
            reason="local_nature_city_transport_or_service_lookup",
        )

    if _contains_any(text, ("toimivat", "toimii", "loytyy", "löytyy", "palvelut", "palveluita")) and _contains_any(
        text,
        (
            "hammaslaakari", "hammaslaakarit", "hammaslääkäri", "hammaslääkärit",
            "terveysasema", "terveyskeskus", "autohuolto", "autohuollot",
            "apteekki", "kirjasto", "korjaamo", "korjaamot",
        ),
    ):
        return _decision(
            "current_external_information",
            language=language,
            needs_web=True,
            response_mode="source_bounded_answer",
            use_chat_context=use_chat_context,
            blocked_context_domains=BUSINESS_DOMAINS + PROJECT_DOMAINS,
            required=["source_boundary"],
            reason="service_provider_lookup",
        )

    food_or_compatibility_terms = (
        "kauramaito", "maito", "kahvi", "kahviin", "torttutaikina", "pullataikina",
        "taikina", "tayte", "täyte", "resepti", "ruoka", "food",
    )
    compatibility_question_terms = (
        "kayko", "käykö", "sopiiko", "voiko kayttaa", "voiko käyttää",
        "mika olisi hyva", "mikä olisi hyvä", "hyva vaihtoehto", "hyvä vaihtoehto",
    )
    if (
        not use_chat_context
        and _contains_any(text, food_or_compatibility_terms)
        and _contains_any(text, compatibility_question_terms)
    ):
        return _decision(
            "current_external_information",
            language=language,
            needs_web=True,
            response_mode="source_bounded_answer",
            use_chat_context=use_chat_context,
            blocked_context_domains=BUSINESS_DOMAINS + PROJECT_DOMAINS,
            required=["source_boundary"],
            reason="practical_food_or_compatibility_lookup",
        )

    health_terms = ("kofeiini", "caffeine", "energiajuoma", "terveys", "health")
    coffee_health_terms = ("liikaa", "vaikuttaa uneen", "univaike", "sydan", "sydän", "oire", "verenpaine")
    if _contains_any(text, health_terms) or _contains_sleep_term(text) or (
        _contains_any(text, ("kahvi", "kahvia")) and _contains_any(text, coffee_health_terms)
    ):
        return _decision(
            "health_lifestyle_general",
            language=language,
            response_mode="general_cautious_advice",
            use_chat_context=False,
            blocked_context_domains=BUSINESS_DOMAINS + PROJECT_DOMAINS + ["web_search"],
            reason="general_health_or_lifestyle_question",
        )

    if "ollama" in text and _contains_any(text, ("levytila", "levytilaa", "disk space", "vievat", "vie", "mallit")):
        return _decision(
            "practical_everyday",
            language=language,
            response_mode="practical_instruction",
            use_chat_context=False,
            blocked_context_domains=BUSINESS_DOMAINS + PROJECT_DOMAINS + ["web_search"],
            reason="local_ollama_disk_space_instruction",
        )

    purchase_or_local_service_terms = (
        "mista voisin ostaa", "mista ostaa", "mista saan", "mist? saan",
        "missa myydaan", "mista loydan", "mista l?ytyy", "mista loytyy",
        "myydaan", "kauppa", "near me", "lahin", "lahella",
        "autohuolto", "autohuollot", "korjaamo", "korjaamot", "huoltamo", "huoltamot",
        "autokorjaamo", "autokorjaamot", "rengasliike", "rengasliiketta", "rengasliikett?",
        "renkaat", "renkaita",
    )

    explicit_purchase_lookup = _contains_any(
        text,
        (
            "mista voisin ostaa", "mista ostaa", "mista saan", "missa myydaan",
            "mista loydan", "mista loytyy", "near me", "lahin", "lahella",
        ),
    )
    service_lookup = _contains_any(
        text,
        (
            "autohuolto", "autohuollot", "korjaamo", "korjaamot", "huoltamo",
            "huoltamot", "autokorjaamo", "autokorjaamot", "rengasliike",
            "rengasliiketta",
        ),
    )
    if (explicit_purchase_lookup or service_lookup) and _contains_any(text, local_lookup_places) or (
        _contains_any(text, ("ostaa", "osta", "myydaan", "kauppa", "autohuolto", "autohuollot", "korjaamo", "huoltamo"))
        and _contains_any(text, local_lookup_places)
    ):
        return _decision(
            "current_external_information",
            language=language,
            needs_web=True,
            response_mode="source_bounded_answer",
            use_chat_context=use_chat_context,
            blocked_context_domains=BUSINESS_DOMAINS,
            required=["source_boundary"],
            reason="purchase_or_local_service_lookup",
        )

    practical_everyday_terms = (
        "kesarenkaat", "kesarenkaita", "renkaat", "renkaita", "autooni", "autoon",
        "ostaa", "ostamassa", "huomioida", "kannattaa huomioida", "ankkuri", "veneeseen",
        "varmuuskopio", "selaimen valimuisti", "uuden kansion", "vapaa levytila",
        "screenshot", "virtuaaliymparisto", "salasanan", "zipiksi", "localhost",
    )
    if _contains_any(text, practical_everyday_terms):
        return _decision(
            "practical_everyday",
            language=language,
            response_mode="practical_instruction",
            use_chat_context=use_chat_context,
            blocked_context_domains=BUSINESS_DOMAINS + PROJECT_DOMAINS + ["web_search"],
            reason="practical_everyday_instruction",
        )

    source_terms = ("lahteista", "lahde", "sources", "source", "rag", "aineisto", "uploaded document", "dokumentista")
    if _contains_any(text, source_terms):
        return _decision(
            "source_or_rag_question",
            language=language,
            use_rag=True,
            response_mode="source_bounded_answer",
            use_chat_context=False,
            blocked_context_domains=BUSINESS_DOMAINS,
            required=["source_boundary"],
            reason="source_or_rag_question",
        )

    current_terms = ("nyt", "tanaan", "today", "current", "talla hetkella", "paljonko")
    place_terms = ("lieksa", "koli", "nurmes", "joensuu", "helsinki", "suomessa")
    if _contains_weather_term(text) and (_contains_any(text, current_terms) or _contains_any(text, place_terms)):
        if "talvella" in text and not _contains_any(text, ("nyt", "tanaan", "today", "lieksa", "koli", "nurmes")):
            return _decision(
                "general_knowledge",
                language=language,
                response_mode="general_answer",
                use_chat_context=False,
                blocked_context_domains=BUSINESS_DOMAINS + PROJECT_DOMAINS + ["web_search"],
                reason="general_seasonal_snow_question",
            )
        return _decision(
            "current_external_weather",
            language=language,
            needs_web=True,
            response_mode="source_bounded_answer",
            use_chat_context=False,
            blocked_context_domains=BUSINESS_DOMAINS,
            required=["source_boundary"],
            reason="current_weather_or_snow_question",
        )

    if _contains_any(text, ("talvella lunta", "suomessa talvella", "yleensa lunta", "winter snow")):
        return _decision(
            "general_knowledge",
            language=language,
            response_mode="general_answer",
            use_chat_context=False,
            blocked_context_domains=BUSINESS_DOMAINS + PROJECT_DOMAINS + ["web_search"],
            reason="general_knowledge_weather_seasonality",
        )

    if _contains_any(text, ("resepti", "ohje", "recipe")) and _contains_any(text, ("hae", "etsi", "find", "search")):
        return _decision(
            "current_external_information",
            language=language,
            needs_web=True,
            response_mode="source_bounded_answer",
            use_chat_context=False,
            blocked_context_domains=BUSINESS_DOMAINS,
            required=["source_boundary"],
            reason="requested_external_practical_source",
        )

    technical_fact_terms = (
        "polttoaineen kulutus", "fuel consumption", "tekniset tiedot", "technical data",
        "specification", "specs", "malli", "model", "volvo penta", "moottori", "engine",
    )
    if _contains_any(text, technical_fact_terms) and _contains_any(text, ("paljon", "what", "kuinka", "kulutus", "consumption", "data", "tiedot")):
        return _decision(
            "current_external_information",
            language=language,
            needs_web=True,
            response_mode="source_bounded_answer",
            use_chat_context=False,
            blocked_context_domains=BUSINESS_DOMAINS,
            required=["source_boundary"],
            reason="specific_external_product_or_technical_fact",
        )

    return _decision(
        "normal_chat",
        language=language,
        use_chat_context=use_chat_context,
        blocked_context_domains=BUSINESS_DOMAINS,
        reason="normal_chat_fallback",
    )


def build_direct_response(decision: IntentDecision, message: str, *, now: Optional[datetime] = None) -> Optional[str]:
    """Return a deterministic response for intents that should not use the model."""
    current = now or datetime.now()
    language = decision.language
    text = _ascii(message)

    if decision.intent == "date_time":
        if language == "en":
            return f"Today is {current.strftime('%A, %Y-%m-%d')} according to the local server time."
        return f"Tänään on {current.strftime('%d.%m.%Y')} paikallisen palvelimen ajan mukaan."

    if decision.intent == "assistant_permissions":
        if language == "en":
            return (
                "I can answer, use configured tools and read or write project data only through the app's "
                "permission boundaries. I must not reveal secrets, authentication files or protected prompts, "
                "and destructive actions require explicit confirmation."
            )
        return (
            "Minulle on annettu vain tämän sovelluksen rajatut käyttöoikeudet: voin vastata, käyttää "
            "määriteltyjä työkaluja ja käsitellä projektin tietoja vain turvarajojen kautta. En saa paljastaa "
            "salaisuuksia, kirjautumistietoja tai suojattuja promptteja, ja vaaralliset muutokset vaativat "
            "erillisen hyväksynnän."
        )

    if decision.intent == "project_identity":
        if language == "en":
            return (
                "Our project is **Local AI Workspace**: a portfolio-stage, local-first AI assistant built with "
                "Python and FastAPI. It demonstrates chat, Ollama/local model use, memory, RAG/source handling, "
                "web search with source boundaries, authentication, audit logging, prompt-injection checks, "
                "response planning and automated tests. It is a portfolio and learning project, not a production SaaS service."
            )
        return (
            "Projektimme on **Local AI Workspace**: portfolio-vaiheessa oleva paikallinen AI-työtila, joka on rakennettu "
            "Pythonilla ja FastAPIlla. Se esittelee chatin, Ollama-/paikallismallin käytön, muistin, RAG-/lähdekäsittelyn, "
            "verkkonhaun lähderajoilla, kirjautumissuojauksen, audit-lokin, prompt injection -suojatestit, "
            "vastausten reitityksen ja automatisoidut testit.\n\n"
            "Tärkeä rajaus: tämä on työnhakua ja oppimista tukeva portfolio-projekti, ei tuotantovalmis SaaS-palvelu."
        )

    if decision.intent == "finnish_language_capability":
        return (
            "Osaan keskustella suomeksi ja voin pitää käyttöliittymän sekä vastaukset suomenkielisinä, "
            "jos kieliasetus tai käyttäjän viesti sitä ohjaa. Tekniset termit kuten RAG, API, FastAPI ja JSON "
            "voivat silti näkyä alkuperäisinä, koska ne ovat alan vakiotermejä."
        )

    if decision.intent == "general_knowledge" and ("lunta" in text or "snow" in text):
        return (
            "Yleisesti kyllä: Suomessa on talvella usein lunta, mutta määrä vaihtelee paljon alueen, "
            "ajankohdan ja vuoden säätilanteen mukaan. Pohjoisessa ja Itä-Suomessa lunta on tavallisesti "
            "enemmän ja pidempään kuin eteläisessä rannikkoseudussa. Tämä on yleistä tietoa, ei ajantasainen "
            "sää- tai lumitilanneraportti."
        )

    if decision.intent == "health_lifestyle_general":
        if _contains_sleep_term(text):
            return (
                "Useimmille aikuisille riittävä yöunen määrä on noin 7–9 tuntia. Tarve vaihtelee "
                "ihmisestä toiseen: jos heräät virkeänä, jaksat päivän normaalisti ja et tarvitse "
                "jatkuvasti lisäkofeiinia pysyäksesi hereillä, määrä on todennäköisesti lähellä sopivaa. "
                "Jos unettomuus, voimakas väsymys tai kuorsaus/hengityskatkokset jatkuvat, asia kannattaa "
                "ottaa puheeksi terveydenhuollon ammattilaisen kanssa. Tämä on yleistä elämäntapaneuvoa, "
                "ei henkilökohtainen lääketieteellinen arvio."
            )
        return None

    if decision.intent == "practical_everyday":
        if _contains_any(text, ("kesarenkaat", "kesarenkaita", "renkaat", "renkaita", "autooni", "autoon")):
            return (
                "Kesärenkaita ostaessa kannattaa tarkistaa ainakin nämä:\n\n"
                "- **Oikea koko:** katso rekisteriotteesta, nykyisestä renkaasta tai auton ohjekirjasta.\n"
                "- **Nopeus- ja kantavuusluokka:** niiden pitää sopia autoon ja käyttöön.\n"
                "- **Märkäpito:** Suomen oloissa märkäpito on usein tärkeämpi kuin pelkkä halpa hinta.\n"
                "- **Melutaso ja vierintävastus:** vaikuttavat ajomukavuuteen ja kulutukseen.\n"
                "- **Valmistusikä:** tarkista DOT-merkintä; aivan vanhoja varastorenkaita ei yleensä kannata ostaa.\n"
                "- **Käyttötapa:** paljon moottoritietä, sorateitä tai kaupunkiajoa voi painottaa eri ominaisuuksia.\n\n"
                "Jos kerrot auton mallin, nykyisen rengaskoon ja budjetin, voin auttaa rajaamaan vaihtoehtoja tarkemmin."
            )
        if "ankkuri" in text:
            return (
                "7 metrin veneeseen sopiva ankkuri riippuu veneen painosta, pohjasta, tuuliolosuhteista ja ankkurityypistä. "
                "Yleisesti kannattaa tarkistaa ankkurivalmistajan taulukko veneen pituuden ja painon mukaan, ja mitoittaa mieluummin "
                "hieman varman päälle. Lisäksi ketjun/köyden pituus ja pohjan tyyppi vaikuttavat vähintään yhtä paljon kuin ankkurin paino."
            )

    return None
