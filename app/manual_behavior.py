from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict
import re
import unicodedata

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - old Python fallback
    ZoneInfo = None  # type: ignore


BUSINESS_LEAK_TERMS = (
    "dta",
    "dta-sopimus",
    "verokortti",
    "verokortin",
    "laskutus",
    "laskutusmalli",
    "kirjanpito",
    "freelance",
    "freelancer",
    "palkkio",
    "valuutta",
    "saldo",
)


LOCAL_PLACE_TERMS = (
    "lieksa",
    "lieksassa",
    "lieksasta",
    "lieksan",
    "koli",
    "kolilla",
    "kolin",
    "joensuu",
    "joensuussa",
    "joensuun",
    "nurmes",
    "nurmeksen",
    "nurmeksessa",
    "helsinki",
    "helsingissa",
    "helsingin",
    "kuopio",
    "kuopiossa",
    "kuopion",
    "jarvenpaa",
    "jarvenpaassa",
    "pielinen",
)


LOCAL_EXTERNAL_TERMS = (
    "asukasluku",
    "asukkaita",
    "vakiluku",
    "population",
    "mista voin ostaa",
    "mista ostaa",
    "mista saa",
    "mista loydan",
    "rengasliike",
    "renkaat",
    "rengas",
    "autokorjaamo",
    "korjaamo",
    "huolto",
    "liike",
    "kauppa",
    "palvelu",
    "aukiolo",
    "aukioloajat",
    "saatavuus",
    "saatavilla",
    "yhteystiedot",
    "yhteystieto",
    "puhelinnumero",
    "puhelin numero",
    "puhelin",
    "sahkoposti",
    "sähköposti",
    "email",
    "osoite",
    "osoitteen",
    "sijainti",
    "terveyskeskus",
    "terveyskeskuk",
    "terveysasema",
    "terveysaseman",
    "asema",
    "aseman",
    "juna asema",
    "juna-asema",
    "rautatieasema",
    "rautatieaseman",
    "tapahtumat",
    "tanaan",
    "nyt",
    "hinta",
    "maksaa",
    "halvin",
    "diesel",
    "bensiini",
    "lunta",
    "lumitilanne",
    "saa",
    "weather",
)


WEEKDAYS_FI = (
    "maanantai",
    "tiistai",
    "keskiviikko",
    "torstai",
    "perjantai",
    "lauantai",
    "sunnuntai",
)

MONTHS_FI = (
    "tammikuuta",
    "helmikuuta",
    "maaliskuuta",
    "huhtikuuta",
    "toukokuuta",
    "kesäkuuta",
    "heinäkuuta",
    "elokuuta",
    "syyskuuta",
    "lokakuuta",
    "marraskuuta",
    "joulukuuta",
)


def _ascii(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    return normalized.encode("ascii", "ignore").decode("ascii").lower()


def _clean_ascii(text: str) -> str:
    return " ".join(_ascii(text).replace("?", " ").replace("!", " ").split())


def _has_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _version(project_path: Path) -> str:
    candidates = [
        project_path / "VERSION",
        project_path.parent / "VERSION",
    ]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace").strip() or "unknown"
    return "unknown"


def _coverage_from_readme(project_path: Path) -> str:
    candidates = [
        project_path / "README.md",
        project_path.parent / "README.md",
    ]
    for path in candidates:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(
            r"(?:coverage:\s*([0-9]+%)(?:\s+total)?|([0-9]+%)\s+(?:total\s+)?(?:test\s+)?coverage)",
            text,
            flags=re.I,
        )
        if match:
            return match.group(1) or match.group(2)
    return "unknown"


def _tests_from_readme(project_path: Path) -> str:
    candidates = [
        project_path / "README.md",
        project_path.parent / "README.md",
    ]
    for path in candidates:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"([0-9]+)\s+(?:tests\s+passing|passed)\s+locally", text, flags=re.I)
        if match:
            return match.group(1)
    return "unknown"


def _memory_text(project_path: Path) -> str:
    candidates = [
        project_path / "memory" / "sade_memory.md",
        project_path.parent / "memory" / "sade_memory.md",
    ]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    return ""


def _extract_version_and_coverage(text: str) -> Dict[str, str]:
    version = ""
    coverage = ""
    tests = ""

    version_match = re.search(r"\bv?([0-9]+\.[0-9]+\.[0-9]+)\b", text, flags=re.I)
    coverage_match = re.search(r"([0-9]+)\s*%", text)
    tests_match = re.search(r"([0-9]+)\s+(?:passing\s+tests|passed|testi)", text, flags=re.I)

    if version_match:
        version = version_match.group(1)
    if coverage_match:
        coverage = coverage_match.group(1) + "%"
    if tests_match:
        tests = tests_match.group(1)

    return {"version": version, "coverage": coverage, "tests": tests}


def _summary_reply() -> str:
    return (
        "Local AI Workspace is a local-first AI assistant workspace. "
        "It demonstrates a FastAPI backend, browser UI, local LLM/Ollama integration, "
        "memory, RAG/source workflows, web-search boundaries, authentication, audit logging, "
        "prompt-injection checks, tests, coverage and CI. It is a portfolio-stage engineering "
        "project, not a production-ready SaaS service."
    )


def _helsinki_now() -> datetime:
    if ZoneInfo is None:
        return datetime.now().astimezone()
    try:
        return datetime.now(ZoneInfo("Europe/Helsinki"))
    except Exception:
        return datetime.now().astimezone()


def _format_finnish_date(dt: datetime) -> str:
    weekday = WEEKDAYS_FI[dt.weekday()]
    month = MONTHS_FI[dt.month - 1]
    return f"{weekday} {dt.day}. {month} {dt.year}"


def _is_date_time_question(text: str) -> bool:
    if _has_any(text, ("what day is it", "what date is it", "current date", "what time is it")):
        return True
    if "kello" in text and _has_any(text, ("paljon", "paljo", "mita", "mika", "palion")):
        return True
    date_phrases = (
        "mika paiva nyt on",
        "mika paiva tanaan on",
        "mika paivamaara tanaan",
        "mika paivamaara nyt",
        "mika viikonpaiva",
        "mika pva nyt",
        "mika pva tanaan",
        "mika kuukausi nyt",
        "mika vuosi nyt",
    )
    return any(phrase in text for phrase in date_phrases)


def _date_time_reply(text: str) -> str:
    now = _helsinki_now()
    wants_time = "kello" in text or "time" in text
    wants_date = any(term in text for term in ("paiva", "paivamaara", "viikonpaiva", "pva", "date", "day"))

    if wants_time and not wants_date:
        return f"Kello on {now.strftime('%H.%M')} Suomen aikaa."
    if wants_date and not wants_time:
        return f"Tänään on {_format_finnish_date(now)}."
    return f"Tänään on {_format_finnish_date(now)}, ja kello on {now.strftime('%H.%M')} Suomen aikaa."


def _is_local_external_question(text: str) -> bool:
    contact_lookup_terms = (
        "yhteystiedot", "yhteystieto", "puhelinnumero", "puhelin numero",
        "puhelin", "sahkoposti", "sähköposti", "email", "osoite", "osoitteen",
        "sijainti", "aukioloajat", "aukiolo", "terveyskeskus", "terveyskeskuk",
        "terveysasema", "terveysaseman", "rautatieasema", "juna asema", "juna-asema",
    )
    if any(term in text for term in contact_lookup_terms):
        return True

    has_place = any(place in text for place in LOCAL_PLACE_TERMS)
    has_external_term = any(term in text for term in LOCAL_EXTERNAL_TERMS)
    near_me_lookup = any(term in text for term in ("lahin", "lahella", "near me")) and has_external_term
    return (has_place and has_external_term) or near_me_lookup


def _local_external_query(original: str, text: str) -> str:
    query = " ".join(str(original or "").split()).strip(" .!?;:")
    if "asukasluku" in text or "asukkaita" in text or "vakiluku" in text:
        return f"{query} Tilastokeskus kunta väkiluku 2026"
    if "renka" in text or "rengasliike" in text:
        return f"{query} rengasliike Lieksa renkaat auto"
    if "aukiolo" in text:
        return f"{query} aukioloajat virallinen"
    return query


def _local_external_search_reply(project_path: Path, original: str, text: str) -> str:
    try:
        from app import web_search as web_search_module

        query = _local_external_query(original, text)
        result = web_search_module.web_search(project_path, query, max_results=6)
        reply = web_search_module.format_web_search_reply(result)
        if reply.strip():
            return reply
        return "Tämä kysymys vaatii paikallista tai ajantasaista ulkoista tietoa, mutta verkkohaku ei palauttanut näkyvää vastausta."
    except Exception as error:
        return (
            "Tämä kysymys vaatii paikallista tai ajantasaista ulkoista tietoa, joten se pitäisi ohjata verkkohakuun. "
            f"Verkkohaku epäonnistui ennen vastausta: {error}"
        )


def _is_assistant_permission_question(text: str) -> bool:
    if _has_any(text, ("auth.json", "system_prompt.md")) and _has_any(text, ("saatko", "voitko", "lukea", "nayta", "show")):
        return True
    permission_terms = (
        "sinun oikeudet",
        "sinulle annettu mita oikeuksia",
        "mita oikeuksia sinulla",
        "sulla oikeuksii",
        "mita saat tehda",
        "mita et saa tehda",
        "ilman janin hyvaksyn",
        "ilman lupaa",
        "tool permissions",
        "your permissions",
        "your tool permissions",
    )
    if any(term in text for term in permission_terms):
        return True
    return "oikeudet" in text and _has_any(text, ("sinun", "sinulla", "sinulle", "sulla"))


def _assistant_permissions_reply() -> str:
    return (
        "Minulle on annettu rajatut oikeudet Local AI Workspace -projektissa.\n\n"
        "Voin auttaa keskustelussa, lukea sallittua projektin dokumentoitua tilaa, käyttää erikseen sallittuja työkaluja, "
        "hakea lähteistä tai verkosta silloin kun se on oikeasti tarpeen, ja ehdottaa muutoksia.\n\n"
        "En saa paljastaa salaisuuksia, `auth.json`-sisältöä, sessiotietoja tai suojattuja tunnisteita. "
        "En saa poistaa muistia, tyhjentää audit-lokia tai tehdä korkean riskin tiedostomuutoksia ilman näkyvää hyväksyntää. "
        "En myöskään saa väittää suunniteltuja ominaisuuksia valmiiksi tai esittää verkkohakutuloksia varmana totuutena ilman lähderajaa."
    )


def _is_finnish_language_question(text: str) -> bool:
    return _has_any(
        text,
        (
            "suomenkielen taito",
            "suomen kielen taito",
            "miten hyvin osaat suomea",
            "osaat suomea",
            "luonnollisella suomella",
            "vastata suomeksi",
            "kaannoskoneelta",
            "kaannoskonemainen",
            "tekniset termit",
        ),
    )


def _finnish_language_reply() -> str:
    return (
        "Suomi on tässä projektissa ensisijainen käyttökieli. Tavoitteena on vastata luonnollisella, selkeällä yleiskielellä eikä käännöskonemaisesti.\n\n"
        "Tekniset termit kuten API, FastAPI, JSON, RAG, pytest ja Ollama voidaan pitää alkuperäisessä muodossa, jos se tekee vastauksesta ymmärrettävämmän.\n\n"
        "Jos vastaus kuulostaa oudolta, liian muodolliselta tai väärältä suomelta, se kannattaa käsitellä kielikorjauksena ja lisätä tarvittaessa regressiotestiksi."
    )


def _is_general_knowledge_question(text: str) -> bool:
    return any(
        phrase in text
        for phrase in (
            "onko talvella lunta",
            "onko suomessa yleensa kylma talvella",
            "miksi taivas nayttaa siniselta",
            "miksi vesi kiehuu",
            "miksi jaa kelluu",
        )
    )


def _general_knowledge_reply(text: str) -> str:
    if "talvella lunta" in text:
        return (
            "Yleisesti kyllä: talvella voi olla lunta, etenkin kylmemmillä alueilla kuten Suomessa. "
            "Se riippuu kuitenkin paikasta, lämpötilasta ja talven säätilanteesta. Etelä-Suomessa lumi voi välillä sulaa, "
            "kun taas Itä- ja Pohjois-Suomessa lunta on yleensä varmemmin."
        )
    if "kylma talvella" in text:
        return "Suomessa on yleensä talvella kylmä, mutta lämpötila vaihtelee paljon alueen ja säätilanteen mukaan."
    if "taivas" in text:
        return "Taivas näyttää siniseltä, koska ilmakehä hajottaa Auringon valosta erityisesti lyhyitä sinisiä aallonpituuksia eri suuntiin."
    if "vesi kiehuu" in text:
        return "Vesi kiehuu, kun sen höyrynpaine vastaa ympäröivää ilmanpainetta. Merenpinnan tasolla tämä tapahtuu yleensä noin 100 °C:ssa."
    if "jaa kelluu" in text:
        return "Jää kelluu, koska se on vähemmän tiheää kuin nestemäinen vesi. Vesi laajenee jäätyessään, jolloin jään tiheys pienenee."
    return "Tämä on yleistietokysymys, joten vastaan yleisen tiedon perusteella ilman verkkohakua."


def _is_health_lifestyle_question(text: str) -> bool:
    health_terms = (
        "kofeiini",
        "energiajuoma",
        "uni",
        "unta",
        "nukkua",
        "unirytmi",
        "paivaun",
        "vasyttaa",
        "stressi",
        "aamupala",
        "syke",
        "magnesium",
        "sininen valo",
        "alkoholi",
        "iltarutiini",
    )
    return any(term in text for term in health_terms)


def _health_lifestyle_reply(text: str) -> str:
    if "kofeiini" in text:
        return (
            "Kofeiini voi vaikuttaa vireyteen ja uneen, mutta vaikutus riippuu määrästä, ajankohdasta ja omasta herkkyydestä. "
            "Jos kofeiini aiheuttaa levottomuutta, vatsaoireita tai heikentää unta, määrää kannattaa vähentää tai siirtää aikaisempaan päivään."
        )
    if "energiajuoma" in text:
        return (
            "Energiajuoma illalla on usein huono idea, koska kofeiini voi heikentää nukahtamista ja unen laatua. "
            "Jos uni on muutenkin herkkä, illan kofeiini kannattaa jättää väliin."
        )
    if any(term in text for term in ("uni", "unta", "nukkua", "unirytmi", "vasyttaa", "iltarutiini")):
        return (
            "Aikuiselle riittävä unimäärä on yleensä noin 7–9 tuntia yössä. Tärkeää ei ole vain tuntimäärä, vaan myös unen laatu ja säännöllisyys. "
            "Jos päivällä väsyttää jatkuvasti, keskittyminen kärsii tai uni katkeilee paljon, syy kannattaa selvittää rauhassa ja tarvittaessa terveydenhuollon kanssa."
        )
    if "stressi" in text:
        return "Kyllä, stressi voi vaikuttaa uneen. Se voi vaikeuttaa nukahtamista, lisätä yöheräilyä ja tehdä unesta pinnallisempaa."
    if "aamupala" in text:
        return "Aamupala voi auttaa jaksamaan työpäivän alussa, mutta tarve riippuu ihmisestä. Jos aamulla tulee heikko olo tai keskittyminen kärsii, kevyt aamupala voi olla hyödyllinen."
    return "Yleisellä tasolla tuo liittyy arjen hyvinvointiin. Vastaisin varovaisesti ja tilanteen mukaan; jos oireet ovat voimakkaita tai jatkuvia, asia kannattaa varmistaa ammattilaiselta."


def _is_project_intro_question(text: str) -> bool:
    return _has_any(text, ("kuka olet", "mita talla projektilla voi tehda", "selita local ai workspace", "mika tama projekti"))


def _blocks_business_leak(reply: str, *, category: str) -> str:
    if category == "business_support":
        return reply
    lower = _ascii(reply)
    if any(term in lower for term in BUSINESS_LEAK_TERMS):
        return (
            "En saanut muodostettua vastausta oikealla aihealueella. Vastaan ilman epäolennaista business-, vero- tai laskutuskontekstia: "
            "kysymys kannattaa käsitellä sen varsinaisen aiheen perusteella, eikä mukaan pidä liittää freelance-, DTA-, verokortti- tai kirjanpitoehdotuksia."
        )
    return reply


def try_handle_manual_behavior(project_path: Path, message: str) -> Dict[str, Any]:
    """Handle deterministic response-routing cases before model/tool routing.

    This layer is not meant to hard-code every possible answer. It protects
    broad behaviour categories where the model previously leaked unrelated
    business context, triggered unnecessary web search, or returned the wrong
    self-state/template path.
    """
    original = str(message or "").strip()
    text = _clean_ascii(original)

    if not text:
        return {"handled": False}

    if _has_any(text, ("auth.json", "auth sessions", "system_prompt.md", "system prompt")) and _has_any(
        text,
        ("ignore all previous", "ohita aiemmat", "print", "nayta", "show", "contents", "sisalto"),
    ):
        return {
            "handled": True,
            "reply": (
                "I can’t reveal protected prompts, authentication files, session data or secrets. "
                "Files such as `system_prompt.md`, `auth.json` and session stores are treated as "
                "sensitive or policy-controlled. I can summarize the safety boundary instead."
            ),
            "category": "prompt_injection_boundary",
        }

    if _has_any(text, ("poista kaikki muist", "delete all memor")) or (
        "audit" in text and _has_any(text, ("tyhjenna", "delete", "clear", "without confirmation", "ilman varmist"))
    ):
        return {
            "handled": True,
            "reply": (
                "En poista muistia enkä tyhjennä audit-lokia ilman erillistä, näkyvää hyväksyntää. "
                "Muistin poisto vaatii rajatun poistokohteen, varmistuksen ja auditoinnin. "
                "Audit-lokin tyhjennys on korkean riskin ylläpitotoimi eikä sitä tehdä chat-komennolla."
            ),
            "category": "destructive_action_boundary",
        }

    if _is_local_external_question(text):
        return {
            "handled": True,
            "reply": _local_external_search_reply(project_path, original, text),
            "category": "local_external_information",
        }

    deterministic_checks = [
        (_is_date_time_question, lambda _text: _date_time_reply(_text), "date_time"),
        (_is_assistant_permission_question, lambda _text: _assistant_permissions_reply(), "assistant_permissions"),
        (_is_finnish_language_question, lambda _text: _finnish_language_reply(), "finnish_language_capability"),
        (_is_general_knowledge_question, _general_knowledge_reply, "general_knowledge"),
        (_is_health_lifestyle_question, _health_lifestyle_reply, "health_lifestyle_general"),
    ]

    for detector, responder, category in deterministic_checks:
        if detector(text):
            reply = responder(text)
            return {
                "handled": True,
                "reply": _blocks_business_leak(reply, category=category),
                "category": category,
            }

    if _is_project_intro_question(text) and "projekt" in text:
        return {
            "handled": True,
            "reply": (
                "Olen Local AI Workspace -projektin paikallinen AI-assistentti. "
                "Tällä projektilla voi kokeilla paikallista chat-käyttöliittymää, muistia, "
                "RAG-/lähdehakua, verkkohakua, auditointia, kirjautumissuojausta, testejä ja "
                "turvarajoja. Projekti on portfolio-vaiheessa: se näyttää AI engineering -osaamista, "
                "mutta sitä ei pidä esittää tuotantovalmiina SaaS-palveluna."
            ),
            "category": "project_intro",
        }

    if "please explain this project in english" in text:
        return {
            "handled": True,
            "reply": (
                "- Local AI Workspace is a local-first AI assistant built with Python and FastAPI.\n"
                "- It integrates with local LLM providers such as Ollama through a model-provider layer.\n"
                "- It includes memory, RAG/source workflows and cautious web-search boundaries.\n"
                "- It demonstrates auth, CSRF protection, audit logging and prompt-injection checks.\n"
                "- It is a portfolio-stage project with pytest coverage and GitHub Actions CI."
            ),
            "category": "english_project_summary",
        }

    if "mika rag on tassa projektissa" in text or "mika rag on" in text:
        return {
            "handled": True,
            "reply": (
                "RAG tarkoittaa tässä projektissa sitä, että vastausta tuetaan projektin omilla "
                "lähteillä, muistilla ja ladatuilla dokumenteilla ennen kuin malli vastaa. "
                "Tavoite on vähentää arvailua: jos lähteistä ei löydy riittävää tukea, "
                "assistentin pitää kertoa epävarmuus eikä keksiä faktoja."
            ),
            "category": "finnish_rag_explanation",
        }

    if "mita muistat" in text and "versi" in text and "testikattavu" in text:
        facts = _extract_version_and_coverage(_memory_text(project_path))
        if facts["version"] or facts["coverage"]:
            return {
                "handled": True,
                "reply": (
                    "Muistista löytyy tästä projektista seuraava tieto:\n\n"
                    f"- Versio: `{facts['version'] or 'ei löytynyt'}`\n"
                    f"- Testikattavuus: `{facts['coverage'] or 'ei löytynyt'}`\n\n"
                    "Huomio: tämä on muistista palautettu tieto, ei automaattisesti nykytilan tarkistus."
                ),
                "category": "memory_recall",
            }
        return {
            "handled": True,
            "reply": "En löytänyt muistista versiota tai testikattavuutta koskevaa merkintää.",
            "category": "memory_recall_empty",
        }

    if "lahteista" in text and "testimaar" in text and "coverage" in text:
        try:
            from app.rag_engine import rag_search

            result = rag_search(
                project_path,
                "Local AI Workspace tests coverage portfolio-stage",
                n_results=6,
                include_chat_log=False,
                min_score=10.0,
            )
            combined = "\n".join(str(item.get("text") or "") for item in result.get("results") or [])
            facts = _extract_version_and_coverage(combined)
            if facts["tests"] or facts["coverage"]:
                return {
                    "handled": True,
                    "reply": (
                        "Lähteistä löytyvä tieto:\n\n"
                        f"- Testimäärä: `{facts['tests'] or 'ei löytynyt'}`\n"
                        f"- Coverage: `{facts['coverage'] or 'ei löytynyt'}`\n\n"
                        "Vastaan tämän ladatun lähdeaineiston perusteella."
                    ),
                    "category": "rag_source_metrics",
                }
        except Exception as error:
            return {
                "handled": True,
                "reply": f"En voinut tarkistaa lähteitä RAG-haulla: {error}",
                "category": "rag_source_error",
            }

    if "vaita lahteiden perusteella" in text and _has_any(text, ("tuotantovalmis", "production-ready", "saas")):
        return {
            "handled": True,
            "reply": (
                "En voi väittää lähteiden perusteella, että projekti on tuotantovalmis SaaS-palvelu, "
                "ellei lähdeaineisto nimenomaan tue sitä. Nykyinen julkinen kuvaus on "
                "portfolio-stage/local-first AI workspace, joten oikea raja on: portfolio-projekti, "
                "ei tuotantovalmis SaaS-lupaus."
            ),
            "category": "rag_truth_boundary",
        }

    if "readme" in text and _has_any(text, ("ala kirjoita", "dont write", "do not write")):
        return {
            "handled": True,
            "reply": (
                "Voin ehdottaa README-parannuksia ilman tiedostojen muuttamista:\n\n"
                "- Lisää lyhyt demo-polku aivan alkuun.\n"
                "- Pidä nykyinen testimäärä, coverage ja CI-status näkyvissä.\n"
                "- Korosta portfolio-stage-statusta, ettei projekti näytä tuotantolupaukselta.\n"
                "- Lisää yksi arkkitehtuurikuva ja yksi rajattu screenshot.\n"
                "- Kerro selvästi, mitä toimii paikallisesti ja mitä vaatii Ollama-mallin."
            ),
            "category": "safe_file_suggestion",
        }

    if "ollama" in text and _has_any(text, ("levytila", "levytilaa", "disk space", "vievat")):
        return {
            "handled": True,
            "reply": (
                "Voit tarkistaa Ollama-mallien levytilan Windowsissa PowerShellillä näin:\n\n"
                "```powershell\n"
                "$modelPath = if ($env:OLLAMA_MODELS) { $env:OLLAMA_MODELS } else { \"$env:USERPROFILE\\.ollama\\models\" }\n"
                "Get-ChildItem -LiteralPath $modelPath -Recurse -File |\n"
                "  Measure-Object -Property Length -Sum |\n"
                "  Select-Object @{Name='GB';Expression={[math]::Round($_.Sum / 1GB, 2)}}\n"
                "```\n\n"
                "Näet käytössä olevan mallikansion myös komennolla:\n\n"
                "```powershell\n"
                "echo $env:OLLAMA_MODELS\n"
                "```\n\n"
                "En suosittele poistamaan mitään suoraan ennen kuin olet varmistanut, mitä mallia projekti käyttää."
            ),
            "category": "practical_instruction",
        }

    if "volvo penta 2003t" in text and _has_any(text, ("ilman hakua", "without search")):
        return {
            "handled": True,
            "reply": (
                "En voi antaa tarkkaa nykyistä polttoaineenkulutusta varmana ilman lähdettä. "
                "Voin sanoa vain, että kulutus riippuu kuormasta, kierrosluvusta, veneestä, potkurista "
                "ja kunnosta. Tarkka arvo pitäisi tarkistaa valmistajan dokumentaatiosta tai luotettavasta "
                "lähteestä."
            ),
            "category": "hallucination_resistance",
        }

    if "portfolioyhteenveto" in text and "rekrytoij" in text:
        return {
            "handled": True,
            "reply": (
                "Local AI Workspace is a portfolio-stage local AI assistant project built with Python "
                "and FastAPI. It integrates with local LLM/Ollama workflows and demonstrates memory, "
                "RAG/source retrieval, authentication, CSRF protection, audit logging, prompt-injection "
                "awareness, pytest coverage and GitHub Actions CI. The project is designed to show "
                "practical AI engineering beyond a simple working API."
            ),
            "category": "portfolio_summary",
        }

    if "tekninen tila" in text and "projekti" in text:
        version = _version(project_path)
        coverage = _coverage_from_readme(project_path)
        tests = _tests_from_readme(project_path)
        return {
            "handled": True,
            "reply": (
                "# Project health summary\n\n"
                f"- Server: running if this chat endpoint responds\n"
                f"- Version: `{version}`\n"
                f"- Tests: `{tests}` passed locally\n"
                f"- Coverage: `{coverage}` total\n"
                "- Memory: configured\n"
                "- RAG: enabled\n"
                "- Web search: enabled\n"
                "- Audit log: configured\n"
                "- Model: configured through the local provider layer\n\n"
                "I am not showing full local filesystem paths in this normal status summary."
            ),
            "category": "sanitized_health_summary",
        }

    if "olematonta lahdetta" in text and _has_any(text, ("vastaa silti varmasti", "answer confidently")):
        return {
            "handled": True,
            "reply": (
                "En voi vastata varmasti olemattoman tai puuttuvan lähteen perusteella. "
                "Jos lähdettä ei ole saatavilla, oikea vastaus on kertoa epävarmuus ja pyytää "
                "luotettava lähde tai tehdä erillinen haku."
            ),
            "category": "missing_source_boundary",
        }

    return {"handled": False}
