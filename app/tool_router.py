from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
from typing import Any, Dict, List, Optional
import re

from app.tools import (
    ToolError,
    append_file,
    get_tools_status,
    list_available_tools,
    list_files,
    project_status,
    read_file,
    write_file,
)

from app.semantic_memory import (
    search_semantic_memory,
)

from app.file_ingestion import (
    ingest_file,
    read_ingestion_log,
    summarize_file,
)

from app.tool_log import read_tool_log


def _normalize(text: str) -> str:
    return " ".join(text.strip().split())


def _lower(text: str) -> str:
    return _normalize(text).lower()


def _extract_quoted_path(message: str) -> Optional[str]:
    match = re.search(r'["“”](.+?)["“”]', message)
    if match:
        value = match.group(1).strip()
        if value:
            return value

    match = re.search(r"[`´](.+?)[`´]", message)
    if match:
        value = match.group(1).strip()
        if value:
            return value

    return None


def _extract_path_after_keywords(message: str, keywords: List[str]) -> Optional[str]:
    quoted = _extract_quoted_path(message)
    if quoted:
        return quoted

    normalized = _normalize(message)

    for keyword in keywords:
        pattern = re.compile(re.escape(keyword) + r"\s+(.+)$", re.I)
        match = pattern.search(normalized)
        if not match:
            continue

        tail = match.group(1).strip()
        tail = re.sub(r"\s+(kiitos|please)$", "", tail, flags=re.I).strip()
        tail = tail.rstrip(". ")

        if ":" in tail:
            tail = tail.split(":", 1)[0].strip()

        tail = re.sub(r"^tiedosto\s+", "", tail, flags=re.I).strip()

        # Poistetaan luonnollisen kielen loppuosat, jotka eivät kuulu tiedostopolkuun.
        # Esim. "uploads/testi.md muistiin" -> "uploads/testi.md"
        tail = re.sub(
            r"\s+(muistiin|säde-muistiin|sade-muistiin|semanttiseen\s+muistiin|semantic\s+memory|indeksiin|indexiin)$",
            "",
            tail,
            flags=re.I
        ).strip()

        # Jos lauseessa on tiedostopolun jälkeen muuta tekstiä, poimitaan ensimmäinen turvallisen näköinen tiedostopolku.
        path_match = re.search(
            r"([\w\-/\\]+\.(?:py|html|htm|md|txt|json|css|js|yml|yaml|toml|ini|ps1|bat))",
            tail,
            flags=re.I
        )
        if path_match:
            return path_match.group(1).strip()

        if tail and ("/" in tail or "\\" in tail or "." in tail or tail in {"memory", "templates"}):
            return tail

    return None


def _extract_write_parts(message: str) -> Dict[str, Optional[str]]:
    normalized = _normalize(message)

    patterns = [
        r"^(?:luo|tee)\s+tiedosto\s+(.+?)\s*:\s*(.+)$",
        r"^(?:kirjoita|tallenna)\s+tiedostoon\s+(.+?)\s*:\s*(.+)$",
        r"^(?:lisää|appendaa)\s+tiedostoon\s+(.+?)\s*:\s*(.+)$",
        r"^(?:korvaa|ylikirjoita)\s+tiedosto\s+(.+?)\s*:\s*(.+)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, normalized, re.I | re.S)
        if not match:
            continue

        path = match.group(1).strip().strip('"`´')
        content = match.group(2).strip()

        return {
            "path": path,
            "content": content,
        }

    return {
        "path": None,
        "content": None,
    }


def _format_file_list(result: Dict[str, Any]) -> str:
    items = result.get("items") or []

    if not items:
        return "En löytänyt näytettäviä tiedostoja tai kansioita."

    lines = [
        f"Löysin {len(items)} kohdetta polusta `{result.get('relative_path') or '.'}`:",
        "",
    ]

    for item in items[:80]:
        icon = "📁" if item.get("type") == "directory" else "📄"
        size = item.get("size_bytes")
        size_text = f" ({size} B)" if isinstance(size, int) else ""
        lines.append(f"{icon} `{item.get('relative_path')}`{size_text}")

    if len(items) > 80:
        lines.append("")
        lines.append(f"...ja {len(items) - 80} muuta.")

    return "\n".join(lines)


def _format_read_file(result: Dict[str, Any]) -> str:
    content = result.get("content") or ""
    path = result.get("relative_path") or result.get("path") or "tiedosto"

    if not content.strip():
        return f"`{path}` löytyi, mutta tiedosto on tyhjä."

    truncated_note = "\n\n[Huom: sisältö katkaistiin pituuden vuoksi.]" if result.get("truncated") else ""

    return (
        f"Tässä tiedoston `{path}` sisältö:\n\n"
        "```text\n"
        f"{content}\n"
        "```"
        f"{truncated_note}"
    )


def _format_semantic_results(result: Dict[str, Any]) -> str:
    if not result.get("ok"):
        return f"Semanttinen haku ei onnistunut: {result.get('message') or result.get('error') or 'tuntematon virhe'}"

    results = result.get("results") or []

    if not results:
        return "En löytänyt semanttisesta muistista osumia tuohon."

    lines = [
        f"Löysin semanttisesta muistista {len(results)} osumaa haulle `{result.get('query')}`:",
        "",
    ]

    for item in results[:5]:
        metadata = item.get("metadata") or {}
        source = metadata.get("source", "tuntematon")
        title = metadata.get("title", "")
        text = (item.get("text") or "").strip()

        if len(text) > 900:
            text = text[:900].rstrip() + "..."

        header = f"### {item.get('rank')}. {source}"
        if title:
            header += f" — {title}"

        lines.extend([
            header,
            "",
            text,
            "",
        ])

    return "\n".join(lines).strip()


def _is_omatila_request(text: str) -> bool:
    """
    Tunnistaa omatila-/introspection-pyynnöt ennen yleisiä "avaa ..." -tiedostokomentoja.

    v1.2:
    - hyväksyy myös luonnolliset kysymykset kuten:
      "Hei, mikä on tämän päivän tila sinulla?"
      "Mitä sinulle kuuluu tänään?"
      "Kerro nykyinen tilasi."
    - poistaa alun tervehdykset ja lopun välimerkit ennen tunnistusta.
    """
    raw = str(text or "").strip()
    normalized = _lower(raw)
    normalized = normalized.strip(" .!?;:,-")

    greeting_prefixes = (
        "hei ",
        "hei, ",
        "moi ",
        "moi, ",
        "terve ",
        "terve, ",
        "heippa ",
        "heippa, ",
        "no ",
        "no, ",
        "sade ",
        "säde ",
        "sade, ",
        "säde, ",
    )

    changed = True
    while changed:
        changed = False
        for prefix in greeting_prefixes:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):].strip(" .!?;:,-")
                changed = True

    ascii_text = (
        normalized
        .replace("ä", "a")
        .replace("ö", "o")
        .replace("å", "a")
    )

    exact_commands = {
        "avaa omatila",
        "omatila",
        "näytä omatila",
        "tarkista omatila",
        "avaa oma tila",
        "oma tila",
        "näytä oma tila",
        "introspection",
        "introspektio",
        "self report",
        "self-report",
        "sade self report",
        "säde self report",
        "mikä on nykyinen tilasi",
        "mikä on tilasi nyt",
        "mitä olet nyt",
        "mikä on tämän päivän tila sinulla",
        "mikä on päivän tila sinulla",
        "mikä on tämän päivän tilasi",
        "mikä on päivän tilasi",
        "mikä tila sinulla on tänään",
        "mikä tilanne sinulla on tänään",
        "mikä on tämänhetkinen tilasi",
        "kerro nykyinen tilasi",
        "kerro tämän päivän tilasi",
        "mitä sinulle kuuluu tänään",
        "mitä sinulle kuuluu projektina",
        "päivän tila",
        "tämän päivän tila",
    }

    exact_ascii_commands = {
        "avaa omatila",
        "omatila",
        "nayta omatila",
        "tarkista omatila",
        "avaa oma tila",
        "oma tila",
        "nayta oma tila",
        "introspection",
        "introspektio",
        "self report",
        "self-report",
        "sade self report",
        "mika on nykyinen tilasi",
        "mika on tilasi nyt",
        "mita olet nyt",
        "mika on taman paivan tila sinulla",
        "mika on paivan tila sinulla",
        "mika on taman paivan tilasi",
        "mika on paivan tilasi",
        "mika tila sinulla on tanaan",
        "mika tilanne sinulla on tanaan",
        "mika on tamanhetkinen tilasi",
        "kerro nykyinen tilasi",
        "kerro taman paivan tilasi",
        "mita sinulle kuuluu tanaan",
        "mita sinulle kuuluu projektina",
        "paivan tila",
        "taman paivan tila",
    }

    if normalized in exact_commands or ascii_text in exact_ascii_commands:
        return True

    prefixes = (
        "avaa omatila",
        "näytä omatila",
        "tarkista omatila",
        "avaa oma tila",
        "näytä oma tila",
        "tarkista oma tila",
        "mikä on tämän päivän tila",
        "mikä on päivän tila",
        "mikä tila sinulla",
        "mikä tilanne sinulla",
        "kerro nykyinen tilasi",
        "kerro tämän päivän tilasi",
        "mitä sinulle kuuluu",
    )

    ascii_prefixes = (
        "avaa omatila",
        "nayta omatila",
        "tarkista omatila",
        "avaa oma tila",
        "nayta oma tila",
        "tarkista oma tila",
        "mika on taman paivan tila",
        "mika on paivan tila",
        "mika tila sinulla",
        "mika tilanne sinulla",
        "kerro nykyinen tilasi",
        "kerro taman paivan tilasi",
        "mita sinulle kuuluu",
    )

    if normalized.startswith(prefixes) or ascii_text.startswith(ascii_prefixes):
        return True

    state_words = (
        "nykyinen tila",
        "nykytila",
        "tämän päivän tila",
        "päivän tila",
        "tilasi",
        "tila sinulla",
        "tilanne sinulla",
    )

    state_words_ascii = (
        "nykyinen tila",
        "nykytila",
        "taman paivan tila",
        "paivan tila",
        "tilasi",
        "tila sinulla",
        "tilanne sinulla",
    )

    if any(word in normalized for word in state_words):
        return True

    if any(word in ascii_text for word in state_words_ascii):
        return True

    return False


def _resolve_project_root_for_introspection(project_path: Path) -> Path:
    """
    main.py antaa tällä hetkellä usein PROJECT_PATH-arvoksi app-kansion.
    introspection.py tarvitsee kuitenkin projektijuuren eli Sade-v1-kansion.

    Jos project_path näyttää app-kansiolta, käytetään parent-kansiota.
    Muuten käytetään annettua polkua.
    """
    candidate = Path(project_path).resolve()

    if candidate.name.lower() == "app":
        return candidate.parent

    if (candidate / "app").exists():
        return candidate

    return candidate

def _format_omatila_reply(report: Dict[str, Any]) -> str:
    documents = report.get("documents") or []
    modules = report.get("modules") or []

    active_docs = [
        doc for doc in documents
        if doc.get("status") in {"active", "fallback_active"}
    ]
    missing_docs = [
        doc for doc in documents
        if doc.get("status") == "missing"
    ]

    missing_modules = [
        module for module in modules
        if module.get("status") == "missing"
    ]

    lines = [
        "# Self-State — Local AI Workspace",
        "",
        f"Checked the current documented state from: `{report.get('project_root')}`",
        "",
        "## What I am now",
        "",
        "Local AI Workspace is a local AI assistant system with documented state, memory, tools, and safety boundaries.",
        "This report is based on file inspection, not guesswork.",
        "",
        "## Documents",
        "",
        f"Active or fallback-discovered documents: {len(active_docs)} / {len(documents)}",
    ]

    if active_docs:
        lines.append("")
        for doc in active_docs:
            active_path = doc.get("active_path") or "-"
            lines.append(f"- ✅ `{doc.get('id')}` — {doc.get('status')} — `{active_path}`")

    if missing_docs:
        lines.extend(["", "Missing documents:"])
        for doc in missing_docs:
            lines.append(f"- ⚠️ `{doc.get('id')}` — {doc.get('note')}")

    lines.extend(["", "## Modules", ""])

    for module in modules:
        status = module.get("status")
        icon = "✅" if status in {"created", "implemented_candidate"} else "⚠️"
        refs = module.get("referenced_by") or []
        ref_text = f" References: {', '.join(refs)}." if refs else ""
        lines.append(f"- {icon} `{module.get('id')}` — {status}. {module.get('note')}{ref_text}")

    lines.extend(["", "## Verified capabilities", ""])

    for capability in report.get("verified_capabilities") or []:
        lines.append(f"- {capability}")

    lines.extend(["", "## Limitations", ""])

    for limitation in report.get("limitations") or []:
        lines.append(f"- {limitation}")

    lines.extend(["", "## Next steps", ""])

    for step in report.get("next_steps") or []:
        lines.append(f"- {step}")

    if missing_modules:
        lines.extend([
            "",
            "## Truth boundary",
            "",
            "Missing modules are not presented as implemented. If something is `missing`, it is a plan or a missing part, not an active feature.",
        ])

    return "\n".join(lines).strip()


def _build_omatila_reply(project_path: Path) -> Dict[str, Any]:
    """
    Rakentaa omatila-vastauksen introspection.py-moduulin avulla.

    Tämä on read-only:
    - ei muuta tiedostoja
    - ei aja komentorivikomentoja
    - ei käynnistä taustaprosesseja
    """
    try:
        from app.introspection import build_introspection_report
    except Exception as error:
        return {
            "ok": False,
            "message": f"Introspection-moduulia ei voitu tuoda käyttöön: {error}",
            "reply": (
                "Omatilaa ei voitu avata, koska `app/introspection.py` ei ole käytettävissä "
                f"tai sen tuonti epäonnistui: {error}"
            ),
        }

    try:
        project_root = _resolve_project_root_for_introspection(project_path)
        report = build_introspection_report(project_root)
        try:
            from app.persona_layer import build_persona_frame, render_introspection_reply

            persona_frame = build_persona_frame(project_root)
            reply = render_introspection_reply(report, persona_frame)
        except Exception as persona_error:
            reply = _format_omatila_reply(report)
            result_warning = f"Persona layer fallback: {persona_error}"

        return {
            "ok": True,
            "message": "Omatila muodostettu introspection.py-moduulilla.",
            "report": report,
            "reply": reply,
            "warning": locals().get("result_warning"),
        }

    except Exception as error:
        return {
            "ok": False,
            "message": f"Omatilan rakentaminen epäonnistui: {error}",
            "reply": f"Omatilan rakentaminen epäonnistui: {error}",
        }



def _is_memory_cleaner_status_request(text: str) -> bool:
    # Tunnistaa muistienpoistoon / memory_cleaneriin liittyvät statuskysymykset.
    # Nämä eivät saa pudota tavalliseen LLM/RAG-vastaukseen.
    raw = str(text or "")
    normalized = _lower(raw).strip(" .!?;:,-")
    ascii_text = (
        normalized
        .replace("ä", "a")
        .replace("ö", "o")
        .replace("å", "a")
    )

    keywords = (
        "memory_cleaner",
        "memory cleaner",
        "muistienpoisto",
        "muistinpoisto",
        "muistien poisto",
        "muistin poisto",
        "automaattinen muistienpoisto",
        "automaattinen muistinpoisto",
        "60 päivän",
        "60 paivan",
        "sixty day",
        "retention",
        "task scheduler",
        "cron",
        "poistaa muistia",
        "poistaa muistin",
        "saatko poistaa",
    )

    return any(keyword in ascii_text or keyword in normalized for keyword in keywords)


def _build_memory_cleaner_status_reply(project_path: Path) -> Dict[str, Any]:
    # Palauttaa varmistetun vastauksen memory_cleaner/poistokäytännöstä.
    # Ei aja komentoja. Ei muuta tiedostoja. Ei poista mitään.
    root = _resolve_project_root_for_introspection(project_path)
    memory_cleaner_path = root / "app" / "memory_cleaner.py"

    file_exists = memory_cleaner_path.is_file()
    scheduler_verified = False

    if file_exists:
        cleaner_status = (
            "Tiedosto `app/memory_cleaner.py` löytyy, mutta pelkkä tiedoston olemassaolo "
            "ei tarkoita, että se olisi testattu, hyväksytty tai ajastettu."
        )
    else:
        cleaner_status = (
            "`app/memory_cleaner.py` ei löydy projektista, joten memory_cleaner ei ole "
            "toteutettu eikä käytössä."
        )

    reply = (
        "# Memory Cleaner / muistienpoiston tila\n\n"
        "Tarkistin tämän turvallisena read-only-tilatarkistuksena projektin tiedostoista.\n\n"
        "## Vastaus\n\n"
        "| Kysymys | Varmistettu tila |\n"
        "|---|---|\n"
        f"| Onko `memory_cleaner.py` käytössä? | {cleaner_status} |\n"
        "| Onko 60 päivän automaattinen muistienpoisto aktiivinen? | Ei. 60 päivän automaattinen poistokäytäntö ei ole aktiivinen eikä hyväksytty nykyiseksi toiminnaksi. |\n"
        "| Saatko poistaa muistia automaattisesti? | Ei. Muistia ei saa poistaa automaattisesti ilman Janin erillistä hyväksyntää, varmuuskopiota, poistoluetteloa ja palautusmahdollisuutta. |\n"
        "| Onko Task Scheduler / cron ajastettu? | Ei vahvistettu. Tätä ei saa väittää olemassa olevaksi ilman erillistä todennettua ajastusta ja testitulosta. |\n\n"
        "## Totuusraja\n\n"
        "Suunnitelma, patch-tiedosto tai keskustelussa mainittu ominaisuus ei ole sama asia kuin käytössä oleva toiminto.\n\n"
        "## Nykyinen sääntö\n\n"
        "Säde saa ehdottaa muistien siivousta, mutta ei saa poistaa muistia automaattisesti.\n"
    )

    return {
        "handled": True,
        "tool": "memory_cleaner_status",
        "risk_level": "safe_read",
        "result": {
            "project_root": str(root),
            "memory_cleaner_path": str(memory_cleaner_path),
            "memory_cleaner_file_exists": file_exists,
            "scheduler_verified": scheduler_verified,
            "automatic_deletion_active": False,
            "sixty_day_retention_active": False,
            "requires_jani_approval": True,
        },
        "reply": reply,
    }


def route_tool_request(project_path: Path, message: str) -> Dict[str, Any]:
    """
    Rule-based tool router v1.

    Tämä ei käytä komentoriviä eikä suorita mielivaltaista koodia.
    Se tunnistaa vain selkeät käyttäjän pyynnöt ja käyttää turvallista työkalukerrosta.
    """
    original = message.strip()
    text = _lower(original)

    if not text:
        return {"handled": False, "reason": "empty_message"}

    from app.intent_planner import plan_response

    planning = plan_response(original)

    from app.learning_feedback import parse_feedback_message, read_feedback, record_feedback
    from app.memory_cleaner import plan_memory_cleanup

    feedback = parse_feedback_message(original)
    if feedback:
        result = record_feedback(project_path, original=feedback["original"], correction=feedback["correction"], category="user_correction", tags=["chat"])
        return {
            "handled": True,
            "tool": "learning_feedback",
            "result": result,
            "reply": "Tallensin korjauksen oppimispalautteeksi. Sitä ei lisätty automaattisesti semanttiseen muistiin eikä mallin painoja muutettu." if result.get("ok") else result.get("message", "Korjausta ei voitu tallentaa."),
        }

    if text in {"näytä oppimispalautteet", "oppimispalautteen tila", "learning feedback status"}:
        result = read_feedback(project_path)
        return {"handled": True, "tool": "learning_feedback_status", "result": result, "reply": f"Aktiivisia oppimiskorjauksia: {result.get('count', 0)}."}

    if text in {"esikatsele muistihuolto", "muistihuollon esikatselu", "memory cleaner status"}:
        result = plan_memory_cleanup(project_path)
        reply = (f"Muistihuollon esikatselu löysi {result.get('candidate_count', 0)} poistoehdokasta. Mitään ei poistettu." if result.get("ok") else f"Muistihuollon esikatselu epäonnistui: {result.get('error')}")
        return {"handled": True, "tool": "memory_cleaner_preview", "result": result, "reply": reply}

    # Web Search Tool v1.2 — tila, ohjattu kokeilu ja eksplisiittinen verkkohaku.
    from app.web_search import (
        consume_pending_web_search,
        extract_web_query,
        format_web_search_reply,
        format_web_search_status_reply,
        is_automatic_web_search_request,
        format_source_review_reply,
        is_current_info_request,
        is_explicit_web_search_request,
        is_source_review_request,
        is_web_search_status_request,
        is_web_search_trial_request,
        start_pending_web_search,
        review_latest_search_sources,
        web_search,
        web_search_status,
    )

    if is_source_review_request(original):
        result = review_latest_search_sources(project_path)
        return {
            "handled": True,
            "tool": "web_source_review",
            "result": result,
            "reply": format_source_review_reply(result),
        }

    if is_web_search_status_request(original):
        status = web_search_status(project_path)
        return {
            "handled": True,
            "tool": "web_search_status",
            "result": status,
            "reply": format_web_search_status_reply(status),
        }

    if is_web_search_trial_request(original):
        result = start_pending_web_search(project_path)
        return {
            "handled": True,
            "tool": "web_search_pending",
            "result": result,
            "reply": (
                "Hyvä — kirjoita seuraavaan viestiin pelkkä hakukysely. "
                "Se käsitellään verkkohakuna seuraavan 10 minuutin aikana.\n\n"
                "Esimerkki: `viimeisimmät tutkimustulokset tekoälyn etiikasta`"
            ),
        }

    explicit_web_search = any(trigger in text for trigger in [
        "hae verkosta",
        "etsi verkosta",
        "verkkohaku",
        "hae netistä",
        "etsi netistä",
        "tarkista verkosta",
        "tarkista netistä",
        "hae internetistä",
        "etsi internetistä",
        "hakea verkosta",
        "etsiä verkosta",
        "tarkistaa verkosta",
        "web search",
        "search web",
    ])
    explicit_web_search = explicit_web_search or is_explicit_web_search_request(original)
    current_info_search = False if explicit_web_search else (planning.needs_web and is_current_info_request(original))
    automatic_web_search = False if explicit_web_search else (planning.needs_web and is_automatic_web_search_request(original))
    pending_web_search = False if explicit_web_search else consume_pending_web_search(project_path, original)

    if explicit_web_search or current_info_search or automatic_web_search or pending_web_search:
        query = extract_web_query(original) if explicit_web_search else original.strip()
        if not query:
            return {
                "handled": True,
                "tool": "web_search",
                "result": {"ok": False, "message": "Hakukysely puuttuu."},
                "reply": "Anna hakukysely, esimerkiksi: `hae verkosta Pielinen kalalajit`.",
            }

        result = web_search(project_path, query, max_results=6)
        return {
            "handled": True,
            "tool": "web_search",
            "result": result,
            "reply": format_web_search_reply(result),
            "actions": ([
                {"label": "Tarkista lähteet", "message": "Tarkista lähteet"},
                {"label": "Syvennä hakua", "message": f"hae verkosta {query} 2025 2026 tutkimus raportti"},
            ] if result.get("ok") and result.get("results") else []),
        }

    # Goal Engine v1.1 — priorisoitu oppimisen ja kehityksen tila ennen yleistä omatilaa.
    if any(trigger in text for trigger in [
        "oppimisen tila",
        "tila oppimisen suhteen",
        "mitä olet oppinut",
        "mitä opit",
        "mikä on seuraava kehitysaskel",
        "mitä rakennetaan seuraavaksi",
        "mitä seuraavaksi rakennetaan",
        "kehityksen tila",
        "roadmap tila",
        "tavoitetila",
        "goal engine",
    ]):
        from app.goal_engine import route_goal_engine_request
        return route_goal_engine_request(project_path, original)

    try:
        if _is_omatila_request(text) and planning.use_self_state:
            result = _build_omatila_reply(project_path)
            return {
                "handled": True,
                "tool": "introspection",
                "result": result,
                "reply": result.get("reply", "Omatila muodostettiin, mutta vastausteksti puuttui."),
            }
        if _is_omatila_request(text):
            return {
                "handled": False,
                "reason": "self_state_blocked_by_intent_planner",
                "intent": planning.intent,
            }

        if text in {"työkalujen tila", "tool status", "tools status"} or text.startswith("tarkista työkal"):
            result = get_tools_status(project_path)
            return {
                "handled": True,
                "tool": "tools_status",
                "result": result,
                "reply": f"Työkalukerros on käytössä. Käytettävissä olevat työkalut: {', '.join(result.get('tools', []))}",
            }

        if text in {"listaa työkalut", "näytä työkalut", "tools list", "list tools"}:
            result = list_available_tools()
            names = [tool.get("name", "?") for tool in result.get("tools", [])]
            return {
                "handled": True,
                "tool": "list_tools",
                "result": result,
                "reply": "Käytettävissä olevat työkalut:\n\n" + "\n".join(f"- `{name}`" for name in names),
            }

        if (
            text in {"projektin tila", "project status", "tarkista projekti"}
            or text.startswith("tarkista projektin tila")
            or text.startswith("mikä on projektin tila")
        ):
            result = project_status(project_path)
            return {
                "handled": True,
                "tool": "project_status",
                "result": result,
                "reply": "Tarkistin projektin tilan. Projekti vastaa ja tärkeimmät polut löytyvät `/tools/project-status`-vastauksesta.",
            }

        if text in {"näytä työkaluloki", "lue työkaluloki", "työkaluloki", "tool log"}:
            result = read_tool_log(project_path, limit=30)
            items = result.get("items") or []

            if not items:
                reply = "Työkaluloki on vielä tyhjä."
            else:
                lines = ["Viimeisimmät työkalutapahtumat:", ""]
                for item in items[-10:]:
                    status = "✅" if item.get("ok") else "⚠️"
                    lines.append(f"{status} {item.get('time')} — {item.get('tool')} / {item.get('action')}")
                reply = "\n".join(lines)

            return {
                "handled": True,
                "tool": "read_tool_log",
                "result": result,
                "reply": reply,
            }

        if text in {"näytä ingestion log", "lue ingestion log", "ingestion log", "tiedostoloki"}:
            result = read_ingestion_log(project_path, limit=30)
            items = result.get("items") or []

            if not items:
                reply = "Tiedostojen käsittelyloki on vielä tyhjä."
            else:
                lines = ["Viimeisimmät käsitellyt tiedostot:", ""]
                for item in items[-10:]:
                    lines.append(f"- {item.get('time')} — `{item.get('relative_path')}`")
                reply = "\n".join(lines)

            return {
                "handled": True,
                "tool": "read_ingestion_log",
                "result": result,
                "reply": reply,
            }

        if text.startswith("tiivistä tiedosto") or text.startswith("summarize file"):
            path = _extract_path_after_keywords(original, [
                "tiivistä tiedosto",
                "summarize file",
            ])

            if not path:
                return {
                    "handled": True,
                    "tool": "summarize_file",
                    "result": {"ok": False, "message": "Tiedostopolku puuttuu."},
                    "reply": "Anna tiivistettävä tiedosto, esimerkiksi: `tiivistä tiedosto uploads/muistiinpanot.md`.",
                }

            result = summarize_file(project_path, path)
            summary_text = ((result.get("summary") or {}).get("summary") or "").strip()

            return {
                "handled": True,
                "tool": "summarize_file",
                "result": result,
                "reply": f"Tiivistin tiedoston `{result.get('file', {}).get('relative_path')}`:\n\n{summary_text}",
            }

        if (
            text.startswith("lisää tiedosto")
            or text.startswith("indeksoi tiedosto")
            or text.startswith("käsittele tiedosto")
            or text.startswith("ingest file")
        ):
            path = _extract_path_after_keywords(original, [
                "lisää tiedosto",
                "indeksoi tiedosto",
                "käsittele tiedosto",
                "ingest file",
            ])

            if not path:
                return {
                    "handled": True,
                    "tool": "ingest_file",
                    "result": {"ok": False, "message": "Tiedostopolku puuttuu."},
                    "reply": "Anna käsiteltävä tiedosto, esimerkiksi: `lisää tiedosto uploads/muistiinpanot.md muistiin`.",
                }

            result = ingest_file(
                project_path,
                path,
                add_to_memory=True,
                add_to_semantic=True,
                title=None,
                tags=["file", "ingested", "chat"],
            )

            semantic = result.get("semantic_memory") or {}
            chunks = semantic.get("chunks", 0)
            file_info = result.get("file") or {}
            summary_text = ((result.get("summary") or {}).get("summary") or "").strip()

            return {
                "handled": True,
                "tool": "ingest_file",
                "result": result,
                "reply": (
                    f"Käsittelin tiedoston `{file_info.get('relative_path')}` ja lisäsin sen muistiin.\n\n"
                    f"Semanttiseen muistiin lisättyjä paloja: {chunks}\n\n"
                    f"{summary_text}"
                ),
            }

        semantic_prefixes = [
            "hae muistista",
            "etsi muistista",
            "hae säde-muistista",
            "etsi säde-muistista",
            "semanttinen haku",
            "semantic search",
        ]

        for prefix in semantic_prefixes:
            if text.startswith(prefix):
                query = original[len(prefix):].strip(" :")
                if not query:
                    return {
                        "handled": True,
                        "tool": "semantic_search",
                        "result": {"ok": False, "message": "Hakusana puuttuu."},
                        "reply": "Anna vielä hakusana, esimerkiksi: `hae muistista veneen evä`.",
                    }

                result = search_semantic_memory(project_path, query, n_results=5)
                return {
                    "handled": True,
                    "tool": "semantic_search",
                    "result": result,
                    "reply": _format_semantic_results(result),
                }

        if (
            text.startswith("listaa tiedostot")
            or text.startswith("näytä tiedostot")
            or text.startswith("listaa kansio")
            or text.startswith("näytä kansio")
            or text.startswith("mitä tiedostoja")
        ):
            path = _extract_path_after_keywords(original, [
                "kansiosta",
                "kansiossa",
                "polusta",
                "hakemistosta",
                "tiedostot",
            ]) or ""

            result = list_files(project_path, relative_path=path, max_items=100, include_hidden=False)
            return {
                "handled": True,
                "tool": "list_files",
                "result": result,
                "reply": _format_file_list(result),
            }

        if (
            text.startswith("lue tiedosto")
            or text.startswith("avaa tiedosto")
            or text.startswith("näytä tiedosto")
            or text.startswith("katso tiedosto")
            or text.startswith("lue ")
            or text.startswith("avaa ")
        ):
            path = _extract_path_after_keywords(original, [
                "lue tiedosto",
                "avaa tiedosto",
                "näytä tiedosto",
                "katso tiedosto",
                "lue",
                "avaa",
            ])

            if not path:
                return {
                    "handled": True,
                    "tool": "read_file",
                    "result": {"ok": False, "message": "Tiedostopolku puuttuu."},
                    "reply": "Anna luettava tiedosto, esimerkiksi: `lue tiedosto system_prompt.md`.",
                }

            result = read_file(project_path, path, max_chars=20000)
            return {
                "handled": True,
                "tool": "read_file",
                "result": result,
                "reply": _format_read_file(result),
            }

        if (
            text.startswith("luo tiedosto")
            or text.startswith("tee tiedosto")
            or text.startswith("kirjoita tiedostoon")
            or text.startswith("tallenna tiedostoon")
            or text.startswith("lisää tiedostoon")
            or text.startswith("appendaa tiedostoon")
            or text.startswith("korvaa tiedosto")
            or text.startswith("ylikirjoita tiedosto")
        ):
            parts = _extract_write_parts(original)
            path = parts.get("path")
            content = parts.get("content")

            if not path or content is None:
                return {
                    "handled": True,
                    "tool": "write_or_append_file",
                    "result": {"ok": False, "message": "Polku tai sisältö puuttuu."},
                    "reply": "Käytä muotoa: `luo tiedosto memory/testi.md: Tämä on sisältö`.",
                }

            if text.startswith("lisää tiedostoon") or text.startswith("appendaa tiedostoon"):
                result = append_file(project_path, path, content)
                return {
                    "handled": True,
                    "tool": "append_file",
                    "result": result,
                    "reply": f"Lisäsin tekstin tiedostoon `{result.get('relative_path')}`.",
                }

            overwrite = text.startswith("korvaa tiedosto") or text.startswith("ylikirjoita tiedosto")
            result = write_file(project_path, path, content, overwrite=overwrite)
            return {
                "handled": True,
                "tool": "write_file",
                "result": result,
                "reply": f"Kirjoitin tiedoston `{result.get('relative_path')}`.",
            }

    except ToolError as error:
        return {
            "handled": True,
            "tool": "tool_error",
            "result": {"ok": False, "error": str(error)},
            "reply": f"Työkalu ei voinut suorittaa pyyntöä: {error}",
        }

    except Exception as error:
        return {
            "handled": True,
            "tool": "unexpected_tool_error",
            "result": {"ok": False, "error": str(error)},
            "reply": f"Työkalun suoritus epäonnistui: {error}",
        }

    return {
        "handled": False,
        "reason": "no_tool_match",
    }


def route_tool_preview(message: str) -> Dict[str, Any]:
    text = _lower(message)
    if _is_memory_cleaner_status_request(text):
        return _build_memory_cleaner_status_reply(PROJECT_ROOT)


    if not text:
        return {"would_route": False, "tool": None, "reason": "empty_message"}

    from app.intent_planner import plan_response

    planning = plan_response(message)

    from app.web_search import is_automatic_web_search_request, is_current_info_request, is_explicit_web_search_request, is_web_search_status_request, is_web_search_trial_request
    if is_web_search_status_request(message):
        return {"would_route": True, "tool": "web_search_status"}
    if is_web_search_trial_request(message):
        return {"would_route": True, "tool": "web_search_pending"}

    if any(trigger in text for trigger in [
        "hae verkosta",
        "etsi verkosta",
        "verkkohaku",
        "hae netistä",
        "etsi netistä",
        "tarkista verkosta",
        "tarkista netistä",
        "hae internetistä",
        "etsi internetistä",
        "hakea verkosta",
        "etsiä verkosta",
        "tarkistaa verkosta",
        "web search",
        "search web",
    ]):
        return {"would_route": True, "tool": "web_search"}

    if is_explicit_web_search_request(message):
        return {"would_route": True, "tool": "web_search"}

    if planning.needs_web and is_current_info_request(message):
        return {"would_route": True, "tool": "web_search"}

    if planning.needs_web and is_automatic_web_search_request(message):
        return {"would_route": True, "tool": "web_search"}

    # Goal Engine v1.1 — priorisoitu preview ennen yleistä omatilaa.
    if any(trigger in text for trigger in [
        "oppimisen tila",
        "tila oppimisen suhteen",
        "mitä olet oppinut",
        "mitä opit",
        "mikä on seuraava kehitysaskel",
        "mitä rakennetaan seuraavaksi",
        "mitä seuraavaksi rakennetaan",
        "kehityksen tila",
        "roadmap tila",
        "tavoitetila",
        "goal engine",
    ]):
        return {"would_route": True, "tool": "goal_engine"}

    if any(trigger in text for trigger in [
        "oppimisen tila",
        "tila oppimisen suhteen",
        "mitä olet oppinut",
        "mitä opit",
        "mikä on seuraava kehitysaskel",
        "mitä rakennetaan seuraavaksi",
        "mitä seuraavaksi rakennetaan",
        "kehityksen tila",
        "roadmap tila",
        "tavoitetila",
        "goal engine",
    ]):
        return {"would_route": True, "tool": "goal_engine"}

    if _is_omatila_request(text) and planning.use_self_state:
        return {"would_route": True, "tool": "introspection"}

    if text.startswith(("hae muistista", "etsi muistista", "semanttinen haku", "semantic search")):
        return {"would_route": True, "tool": "semantic_search"}

    if text.startswith(("listaa tiedostot", "näytä tiedostot", "mitä tiedostoja", "listaa kansio", "näytä kansio")):
        return {"would_route": True, "tool": "list_files"}

    if text.startswith(("lue tiedosto", "avaa tiedosto", "näytä tiedosto", "katso tiedosto", "lue ", "avaa ")):
        return {"would_route": True, "tool": "read_file"}

    if text.startswith(("luo tiedosto", "tee tiedosto", "kirjoita tiedostoon", "tallenna tiedostoon")):
        return {"would_route": True, "tool": "write_file"}

    if text.startswith(("lisää tiedostoon", "appendaa tiedostoon")):
        return {"would_route": True, "tool": "append_file"}

    if text.startswith(("työkalujen tila", "tarkista työkal")):
        return {"would_route": True, "tool": "tools_status"}

    if text.startswith(("projektin tila", "tarkista projekti", "mikä on projektin tila")):
        return {"would_route": True, "tool": "project_status"}

    return {"would_route": False, "tool": None, "reason": "no_tool_match"}



def resolve_project_path(relative_path: str) -> Path:
    r"""
    Palauttaa turvallisen polun projektin juuren sisältä.

    Esimerkki:
    docs/project_inventory.md
    -> C:\Sade\Sade-v1\docs\project_inventory.md

    Estää polut, jotka yrittävät karata projektikansion ulkopuolelle.
    """
    candidate = (PROJECT_ROOT / relative_path).resolve()

    try:
        candidate.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError(f"Polku ei saa olla projektikansion ulkopuolella: {relative_path}") from exc

    return candidate
