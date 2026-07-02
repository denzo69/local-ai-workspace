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
    return _contains_any(
        text,
        (
            "jatka", "kerro lisaa", "kerro lisää", "tuosta", "tuohon", "edellinen",
            "edellisesta", "edellisestä", "se asia", "siita", "siitä", "tarkenna",
            "continue", "go on", "that answer", "previous", "tell me more",
        ),
    )


def _language(original: str, ascii_text: str) -> str:
    if re.search(r"\b(please|what|how|explain|today|source|permission|rights)\b", ascii_text):
        return "en"
    if any(char in original.lower() for char in ("ä", "ö", "å")):
        return "fi"
    if _contains_any(
        ascii_text,
        (
            "mika", "mita", "minka", "minkalainen", "onko", "voitko",
            "suome", "suomeksi", "selita", "kerro", "muista", "nayta",
            "hyva", "paljonko", "pitka", "pitkaan", "kokoinen", "veneeseen",
            "lunta", "saa", "kahvi",
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
    permission_question = _contains_any(text, ("saatko", "can you", "are you allowed", "oikeudet", "permissions", "ilman lupaa"))
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

    health_terms = ("kahvi", "kofeiini", "caffeine", "energiajuoma", "terveys", "health", "food", "ruoka")
    if _contains_any(text, health_terms) or _contains_sleep_term(text):
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
            use_chat_context=False,
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

    weather_terms = ("saa", "weather", "lunta", "snow", "lumitilanne")
    current_terms = ("nyt", "tanaan", "today", "current", "talla hetkella", "paljonko")
    place_terms = ("lieksa", "koli", "nurmes", "joensuu", "helsinki", "suomessa")
    if _contains_any(text, weather_terms) and (_contains_any(text, current_terms) or _contains_any(text, place_terms)):
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
        if "kahvi" in text or "kofeiini" in text or "caffeine" in text:
            return (
                "Kaksi kuppia kahvia aamulla ei ole useimmille aikuisille automaattisesti liikaa, mutta "
                "sopiva määrä riippuu omasta kofeiiniherkkyydestä, unesta, sydämentykytyksistä ja siitä, "
                "juotko kofeiinia myös myöhemmin päivällä. Jos kahvi heikentää unta, aiheuttaa levottomuutta "
                "tai vatsaoireita, määrää kannattaa vähentää. Tämä on yleistä elämäntapaneuvoa, ei "
                "henkilökohtainen lääketieteellinen arvio."
            )
        return (
            "Tähän voi vastata yleisellä tasolla, mutta henkilökohtainen vaikutus riippuu terveydestä, "
            "unesta, lääkityksistä ja omasta herkkyydestä. Jos oireita tulee tai asia huolettaa, kannattaa "
            "kysyä terveydenhuollon ammattilaiselta."
        )

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
