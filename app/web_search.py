from __future__ import annotations

"""
Säde v1 — Web Search Tool v1

Tarkoitus:
- Antaa Säteelle hallittu verkkohakuominaisuus.
- Ei väitä tietoa todeksi ilman lähdettä.
- Tallentaa hakutuloksen kevyesti välimuistiin.
- Käyttää ensisijaisesti API-provideria, jos avain on määritelty.
- Käyttää DuckDuckGo Lite -hakua best-effort fallbackina ilman API-avainta.

Tärkeä totuusraja:
- Tämä työkalu hakee lähteitä.
- Tämä työkalu ei tee lopullista totuuspäätelmää yksin.
- Vastauksessa pitää näyttää lähteet tai sanoa, jos haku epäonnistui.
"""

import html
import ipaddress
import json
import os
import re
import socket
import time
import unicodedata
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional


USER_AGENT = "Sade-v1-local-web-search/1.0 (+local personal assistant)"
DEFAULT_TIMEOUT = 12
DEFAULT_MAX_RESULTS = 6
PENDING_STATE_FILENAME = "web_search_state.json"
PENDING_TTL_SECONDS = 10 * 60


@dataclass
class WebSearchResult:
    title: str
    url: str
    snippet: str = ""
    source: str = "web"
    rank: int = 0


def resolve_project_root(project_root: Optional[Path] = None) -> Path:
    if project_root is None:
        return Path(__file__).resolve().parent.parent

    root = Path(project_root).resolve()
    if root.name.lower() == "app":
        return root.parent
    return root


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def slugify(text: str, max_len: int = 60) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9åäö]+", "-", text, flags=re.I)
    text = text.strip("-")
    return text[:max_len] or "search"


def cache_dir(project_root: Optional[Path] = None) -> Path:
    root = resolve_project_root(project_root)
    path = root / "memory" / "web_search_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def pending_state_path(project_root: Optional[Path] = None) -> Path:
    root = resolve_project_root(project_root)
    path = root / "app" / "memory" / PENDING_STATE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def start_pending_web_search(project_root: Optional[Path] = None) -> Dict[str, Any]:
    path = pending_state_path(project_root)
    payload = {"pending": True, "created_at": now_iso(), "expires_at_epoch": time.time() + PENDING_TTL_SECONDS}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "pending": True, "expires_in_seconds": PENDING_TTL_SECONDS, "path": str(path)}


def consume_pending_web_search(project_root: Optional[Path], message: str) -> bool:
    path = pending_state_path(project_root)
    if not path.exists():
        return False
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    path.unlink(missing_ok=True)
    if not state.get("pending") or float(state.get("expires_at_epoch", 0)) < time.time():
        return False
    normalized = " ".join(str(message or "").lower().split()).strip(" .!?;:")
    cancellations = {"ei", "ei sittenkään", "peru", "peruuta", "lopeta", "unohda se"}
    return len(normalized) >= 3 and normalized not in cancellations


def write_cache(project_root: Optional[Path], payload: Dict[str, Any]) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    query = payload.get("query", "search")
    path = cache_dir(project_root) / f"{stamp}_{slugify(query)}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _http_get(url: str, timeout: int = DEFAULT_TIMEOUT, headers: Optional[Dict[str, str]] = None) -> str:
    request_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fi,en;q=0.7",
    }
    if headers:
        request_headers.update(headers)

    req = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        data = response.read()
    return data.decode(charset, errors="replace")


class DuckDuckGoLiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: List[WebSearchResult] = []
        self._in_link = False
        self._current_href = ""
        self._current_text: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}

        if tag == "a":
            href = attrs_dict.get("href", "")
            if href and ("uddg=" in href or href.startswith("http")):
                self._in_link = True
                self._current_href = href
                self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._in_link:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_link:
            title = html.unescape(" ".join(" ".join(self._current_text).split())).strip()
            url = normalize_duck_url(self._current_href)

            if title and url and not is_noise_url(url) and not self._already_seen(url):
                result = WebSearchResult(
                    title=title,
                    url=url,
                    rank=len(self.results) + 1,
                    source=domain_from_url(url),
                )
                self.results.append(result)

            self._in_link = False
            self._current_href = ""
            self._current_text = []

    def _already_seen(self, url: str) -> bool:
        return any(item.url == url for item in self.results)


class SourcePageParser(HTMLParser):
    """Kerää sivulta vain tarkistukseen tarvittavan otsikon, kuvauksen ja näkyvän tekstin."""

    def __init__(self) -> None:
        super().__init__()
        self.title_parts: List[str] = []
        self.text_parts: List[str] = []
        self.description = ""
        self._in_title = False
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta" and not self.description:
            name = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
            if name in {"description", "og:description"}:
                self.description = " ".join(attrs_dict.get("content", "").split())

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())
        if not cleaned or self._ignored_depth:
            return
        if self._in_title:
            self.title_parts.append(cleaned)
        if sum(map(len, self.text_parts)) < 1800:
            self.text_parts.append(cleaned)


def _is_public_http_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        if parsed.hostname.lower() in {"localhost", "localhost.localdomain"}:
            return False
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
        return bool(addresses) and all(ipaddress.ip_address(address).is_global for address in addresses)
    except Exception:
        return False


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _is_public_http_url(newurl):
            raise urllib.error.URLError("Uudelleenohjaus ei-julkiseen osoitteeseen estettiin.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def inspect_source(url: str, *, timeout: int = 7) -> Dict[str, Any]:
    """Avaa yhden hakutulos-URL:n ja palauttaa rajatun tarkistusotteen."""
    if not _is_public_http_url(url):
        return {"ok": False, "url": url, "error": "URL ei ole sallittu julkinen HTTP(S)-osoite."}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "fi,en;q=0.7"})
        opener = urllib.request.build_opener(SafeRedirectHandler())
        with opener.open(req, timeout=timeout) as response:
            final_url = response.geturl()
            content_type = response.headers.get_content_type()
            charset = response.headers.get_content_charset() or "utf-8"
            raw = response.read(300_000)
        if not _is_public_http_url(final_url):
            return {"ok": False, "url": url, "error": "Uudelleenohjaus ei-julkiseen osoitteeseen estettiin."}
        if content_type not in {"text/html", "application/xhtml+xml"}:
            return {"ok": False, "url": url, "final_url": final_url, "error": f"Sisältötyyppiä {content_type} ei lueta automaattisesti."}
        parser = SourcePageParser()
        parser.feed(raw.decode(charset, errors="replace"))
        return {
            "ok": True,
            "url": url,
            "final_url": final_url,
            "title": " ".join(parser.title_parts)[:300],
            "description": parser.description[:600],
            "preview": " ".join(parser.text_parts)[:900],
        }
    except Exception as exc:
        return {"ok": False, "url": url, "error": str(exc)}


def normalize_duck_url(href: str) -> str:
    href = html.unescape(href or "")

    if href.startswith("//"):
        href = "https:" + href

    if "uddg=" in href:
        parsed = urllib.parse.urlparse(href)
        query = urllib.parse.parse_qs(parsed.query)
        uddg = query.get("uddg", [""])[0]
        if uddg:
            return urllib.parse.unquote(uddg)

    return href


def is_noise_url(url: str) -> bool:
    if not url:
        return True

    noise = [
        "duckduckgo.com",
        "javascript:",
        "mailto:",
        "/html/",
        "/lite/",
    ]
    lower = url.lower()
    return any(item in lower for item in noise)


def domain_from_url(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.replace("www.", "")
    except Exception:
        return "web"


def duckduckgo_lite_search(query: str, *, max_results: int = DEFAULT_MAX_RESULTS, timeout: int = DEFAULT_TIMEOUT) -> List[WebSearchResult]:
    encoded = urllib.parse.urlencode({"q": query})
    url = f"https://lite.duckduckgo.com/lite/?{encoded}"

    html_text = _http_get(url, timeout=timeout)
    parser = DuckDuckGoLiteParser()
    parser.feed(html_text)

    return parser.results[:max_results]


def brave_search(query: str, *, max_results: int = DEFAULT_MAX_RESULTS, timeout: int = DEFAULT_TIMEOUT) -> List[WebSearchResult]:
    """
    Brave Search API provider.

    Käytössä vain jos ympäristömuuttuja BRAVE_SEARCH_API_KEY löytyy.
    """
    api_key = os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("BRAVE_SEARCH_API_KEY puuttuu.")

    params = urllib.parse.urlencode({
        "q": query,
        "count": str(max_results),
        "search_lang": "fi",
        "country": "FI",
    })
    url = f"https://api.search.brave.com/res/v1/web/search?{params}"
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": api_key,
    }

    raw = _http_get(url, timeout=timeout, headers=headers)
    data = json.loads(raw)

    web = (data or {}).get("web") or {}
    items = web.get("results") or []

    results: List[WebSearchResult] = []
    for index, item in enumerate(items[:max_results], start=1):
        result = WebSearchResult(
            title=(item.get("title") or "").strip(),
            url=(item.get("url") or "").strip(),
            snippet=(item.get("description") or "").strip(),
            source=domain_from_url(item.get("url") or ""),
            rank=index,
        )
        if result.title and result.url:
            results.append(result)

    return results


def google_search(query: str, *, max_results: int = DEFAULT_MAX_RESULTS, timeout: int = DEFAULT_TIMEOUT) -> List[WebSearchResult]:
    """
    Google Programmable Search / Custom Search JSON API provider.

    Requires GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_ENGINE_ID.
    """
    api_key = os.environ.get("GOOGLE_SEARCH_API_KEY", "").strip()
    engine_id = (
        os.environ.get("GOOGLE_SEARCH_ENGINE_ID", "").strip()
        or os.environ.get("GOOGLE_CSE_ID", "").strip()
    )
    if not api_key:
        raise RuntimeError("GOOGLE_SEARCH_API_KEY is missing.")
    if not engine_id:
        raise RuntimeError("GOOGLE_SEARCH_ENGINE_ID is missing.")

    params = urllib.parse.urlencode({
        "key": api_key,
        "cx": engine_id,
        "q": query,
        "num": str(max(1, min(max_results, 10))),
    })
    url = f"https://www.googleapis.com/customsearch/v1?{params}"
    raw = _http_get(url, timeout=timeout, headers={"Accept": "application/json"})
    data = json.loads(raw)

    results: List[WebSearchResult] = []
    for index, item in enumerate((data or {}).get("items") or [], start=1):
        result = WebSearchResult(
            title=(item.get("title") or "").strip(),
            url=(item.get("link") or "").strip(),
            snippet=(item.get("snippet") or "").strip(),
            source=domain_from_url(item.get("link") or ""),
            rank=index,
        )
        if result.title and result.url:
            results.append(result)

    return results[:max_results]


def choose_provider() -> str:
    configured = os.environ.get("SADE_WEB_SEARCH_PROVIDER", "auto").strip().lower()
    aliases = {
        "duckduckgo": "duckduckgo_lite",
        "ddg": "duckduckgo_lite",
        "google_custom_search": "google",
        "google_cse": "google",
    }
    configured = aliases.get(configured, configured)
    if configured and configured != "auto":
        return configured

    if (
        os.environ.get("GOOGLE_SEARCH_API_KEY", "").strip()
        and (os.environ.get("GOOGLE_SEARCH_ENGINE_ID", "").strip() or os.environ.get("GOOGLE_CSE_ID", "").strip())
    ):
        return "google"
    if os.environ.get("BRAVE_SEARCH_API_KEY", "").strip():
        return "brave"
    return "duckduckgo_lite"


def configured_providers() -> Dict[str, Any]:
    return {
        "selected": choose_provider(),
        "available": {
            "duckduckgo_lite": True,
            "brave": bool(os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()),
            "google": bool(
                os.environ.get("GOOGLE_SEARCH_API_KEY", "").strip()
                and (os.environ.get("GOOGLE_SEARCH_ENGINE_ID", "").strip() or os.environ.get("GOOGLE_CSE_ID", "").strip())
            ),
            "bing": False,
        },
        "configured": os.environ.get("SADE_WEB_SEARCH_PROVIDER", "auto").strip().lower() or "auto",
        "notes": {
            "duckduckgo_lite": "No API key required; best-effort fallback.",
            "brave": "Requires BRAVE_SEARCH_API_KEY.",
            "google": "Requires GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_ENGINE_ID.",
            "bing": "Use Azure AI Foundry Grounding with Bing as a future integration; legacy Bing Search APIs are retired.",
        },
    }


def web_search_status(project_root: Optional[Path] = None) -> Dict[str, Any]:
    root = resolve_project_root(project_root)
    caches = sorted((root / "memory" / "web_search_cache").glob("*.json"), reverse=True)
    latest: Dict[str, Any] = {}
    for path in caches[:20]:
        try:
            candidate = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if candidate.get("ok"):
            latest = {
                "time": candidate.get("time"),
                "query": candidate.get("query"),
                "provider": candidate.get("provider"),
                "result_count": len(candidate.get("results") or []),
                "cache_path": str(path),
            }
            break
    return {
        "ok": True,
        "enabled": True,
        "module": "app/web_search.py",
        "provider": choose_provider(),
        "providers": configured_providers(),
        "direct_chat_integration": True,
        "automatic_search": True,
        "rag_integration": False,
        "semantic_memory_integration": False,
        "goal_engine_integration": False,
        "latest_success": latest or None,
        "commands": ["hae verkosta <hakukysely>", "etsi netistä <hakukysely>"],
        "truth_boundary": "Hakutulokset palautetaan lähteinä suoraan käyttäjälle. Niitä ei syötetä automaattisesti RAGiin, goal_engineen tai semanttiseen muistiin.",
    }


def format_web_search_status_reply(status: Dict[str, Any]) -> str:
    latest = status.get("latest_success") or {}
    latest_line = (
        f"Viimeisin onnistunut haku: `{latest.get('query')}` — {latest.get('result_count')} tulosta — {latest.get('time')}"
        if latest else "Onnistunutta hakua ei ole vielä tallennettu välimuistiin."
    )
    return (
        "Kyllä, verkkohaku on käytössä.\n\n"
        f"- Provider: `{status.get('provider')}`\n"
        "- Chat-integraatio: käytössä\n"
        "- Automaattinen verkkohaku: ei käytössä\n"
        "- Automaattinen RAG-/goal_engine-/semanttisen muistin integraatio: ei käytössä\n"
        f"- {latest_line}\n\n"
        "Käytä esimerkiksi: `hae verkosta viimeisimmät tutkimustulokset tekoälyn etiikasta`.\n\n"
        "Totuusraja: haku palauttaa lähteitä suoraan keskusteluun. Se ei yksin todista lähteiden väitteitä oikeiksi."
    )


def web_search(
    project_root: Optional[Path],
    query: str,
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    query = " ".join((query or "").split()).strip()

    if not query:
        return {
            "ok": False,
            "query": query,
            "message": "Hakukysely puuttuu.",
            "results": [],
        }

    selected = provider or choose_provider()
    started = time.time()

    try:
        if selected == "brave":
            results = brave_search(query, max_results=max_results)
        elif selected == "google":
            results = google_search(query, max_results=max_results)
        elif selected == "duckduckgo_lite":
            results = duckduckgo_lite_search(query, max_results=max_results)
        else:
            raise RuntimeError(f"Tuntematon provider: {selected}")

        payload: Dict[str, Any] = {
            "ok": True,
            "time": now_iso(),
            "query": query,
            "provider": selected,
            "duration_seconds": round(time.time() - started, 2),
            "results": [asdict(item) for item in results],
            "truth_boundary": (
                "Nämä ovat verkkohakutuloksia, eivät lopullinen totuus. "
                "Vastaus pitää perustaa lähteisiin ja epävarmuus pitää kertoa."
            ),
        }

        cache_path = write_cache(project_root, payload)
        payload["cache_path"] = str(cache_path)
        return payload

    except Exception as exc:
        payload = {
            "ok": False,
            "time": now_iso(),
            "query": query,
            "provider": selected,
            "duration_seconds": round(time.time() - started, 2),
            "error": str(exc),
            "results": [],
            "truth_boundary": "Verkkohaku epäonnistui. Älä väitä hakeneesi tietoa onnistuneesti.",
        }
        try:
            cache_path = write_cache(project_root, payload)
            payload["cache_path"] = str(cache_path)
        except Exception:
            pass
        return payload


def format_web_search_reply(result: Dict[str, Any]) -> str:
    if not result.get("ok"):
        return (
            "Verkkohaku ei onnistunut.\n\n"
            f"- Hakukysely: `{result.get('query')}`\n"
            f"- Provider: `{result.get('provider')}`\n"
            f"- Virhe: `{result.get('error') or result.get('message') or 'tuntematon virhe'}`\n\n"
            "En väitä tietoa haetuksi, koska haku epäonnistui."
        )

    items = result.get("results") or []

    if not items:
        return (
            "Verkkohaku onnistui teknisesti, mutta tuloksia ei löytynyt.\n\n"
            f"- Hakukysely: `{result.get('query')}`\n"
            f"- Provider: `{result.get('provider')}`"
        )

    lines = [
        "# Verkkohaku",
        "",
        f"Hakukysely: `{result.get('query')}`",
        f"Provider: `{result.get('provider')}`",
        "",
    ]

    if _looks_like_weather_query(str(result.get("query") or "")):
        lines.extend([
            "Löysin ajantasaiset säälähteet. En vielä väitä tarkkaa säälukemaa pelkän hakutuloslistan perusteella.",
            "",
            "Luotettavimmat seuraavat lähteet ovat yleensä Ilmatieteen laitos ja Foreca. Paina **Tarkista lähteet**, niin yritän lukea lähdesivut ja muodostaa lyhyen sääyhteenvedon.",
            "",
        ])

    lines.extend([
        "Löysin nämä lähteet:",
        "",
    ])

    for item in items:
        title = item.get("title") or "Nimetön lähde"
        url = item.get("url") or ""
        source = item.get("source") or domain_from_url(url)
        snippet = (item.get("snippet") or "").strip()

        lines.append(f"{item.get('rank', '-')}. **{title}**")
        lines.append(f"   - Lähde: `{source}`")
        lines.append(f"   - URL: {url}")
        if snippet:
            lines.append(f"   - Katkelma: {snippet[:300]}")
        lines.append("")

    if not _looks_like_weather_query(str(result.get("query") or "")):
        lines.append("Voit pyytää seuraavaksi: **Tarkista lähteet**.")

    return "\n".join(lines).strip()


def latest_successful_search(project_root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    root = resolve_project_root(project_root)
    for path in sorted((root / "memory" / "web_search_cache").glob("*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload.get("ok") and payload.get("results"):
            payload["cache_path"] = str(path)
            return payload
    return None


def review_latest_search_sources(project_root: Optional[Path] = None) -> Dict[str, Any]:
    """Tarkistaa viimeisimmän haun lähteet tekemättä tutkimuksellisia johtopäätöksiä."""
    search = latest_successful_search(project_root)
    if not search:
        return {"ok": False, "error": "Tarkistettavaa onnistunutta verkkohakua ei löytynyt.", "sources": []}
    sources = []
    for item in (search.get("results") or [])[:6]:
        sources.append({**item, **inspect_source(item.get("url") or "")})
    return {
        "ok": True,
        "query": search.get("query"),
        "sources": sources,
        "verified_count": sum(1 for item in sources if item.get("ok")),
        "answer_summary": build_source_based_answer(search.get("query") or "", sources),
        "truth_boundary": "Tarkistus vahvistaa sivun saavutettavuuden ja sivulta luetun otteen, ei kaikkien väitteiden tieteellistä paikkansapitävyyttä.",
    }


def _ascii_finnish(text: str) -> str:
    value = str(text or "").lower()
    try:
        value = value.encode("latin1").decode("utf-8")
    except Exception:
        pass
    value = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return value.replace("?", "a")


def _looks_like_weather_query(query: str) -> bool:
    text = _ascii_finnish(query)
    return any(term in text for term in ("saa", "weather", "foreca", "ilmatieteen", "supersaa"))


def _compact_excerpt(text: str, *, max_chars: int = 260) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rstrip() + "..."


def _extract_weather_observations(sources: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    observations: List[Dict[str, str]] = []
    weather_pattern = re.compile(
        r"(.{0,80}(?:[-+]?\d{1,2}\s*(?:°| astetta| c\b|celsius)|sade|tuuli|pilv|lämp|lamp|pouta|ukkonen).{0,120})",
        flags=re.I,
    )

    for source in sources:
        if not source.get("ok"):
            continue

        combined = " ".join(
            str(source.get(key) or "")
            for key in ("description", "preview", "snippet")
        )
        match = weather_pattern.search(combined)
        if not match:
            continue

        observations.append({
            "title": str(source.get("title") or "Lähde"),
            "url": str(source.get("final_url") or source.get("url") or ""),
            "excerpt": _compact_excerpt(match.group(1), max_chars=240),
        })

    return observations[:3]


def build_source_based_answer(query: str, sources: List[Dict[str, Any]]) -> str:
    verified = [item for item in sources if item.get("ok")]
    if not verified:
        return "En saanut avattua lähdesivuja luotettavasti, joten en muodosta varsinaista vastausta."

    if _looks_like_weather_query(query):
        observations = _extract_weather_observations(sources)
        if observations:
            lines = [
                "Tarkistin säähaun lähteitä ja löysin näistä lähdeotteista sääarvoja tai sääkuvauksia:",
                "",
            ]
            for item in observations:
                lines.append(f"- {item['excerpt']} ({item['title']})")
            lines.extend([
                "",
                "Huom: tämä on lähdesivuilta luettu ote, ei erillinen meteorologinen laskenta. Avaa lähde varmistaaksesi aivan viimeisimmän tilanteen.",
            ])
            return "\n".join(lines).strip()

        best_sources = ", ".join((item.get("source") or item.get("title") or "lähde") for item in verified[:3])
        return (
            "Tarkistin säähaun lähteitä, mutta en saanut sivuilta varmasti poimittua yhtä ajantasaista lämpötila-arvoa. "
            f"Luotettavimmat avattavat lähteet tähän hakuun ovat: {best_sources}. "
            "Avaa Ilmatieteen laitoksen tai Forecan lähde lopullista nykyhetken lukemaa varten."
        )

    excerpts = []
    for item in verified[:3]:
        excerpt = _compact_excerpt(item.get("description") or item.get("preview") or item.get("snippet") or "", max_chars=220)
        if excerpt:
            excerpts.append(f"- {excerpt} ({item.get('title') or 'lähde'})")

    if not excerpts:
        return "Lähteet avautuivat, mutta niistä ei löytynyt selkeää tekstikatkelmaa automaattiseen yhteenvetoon."

    return "Tarkistettujen lähteiden perusteella olennaiset otteet ovat:\n\n" + "\n".join(excerpts)


def format_source_review_reply(result: Dict[str, Any]) -> str:
    if not result.get("ok"):
        return f"Lähteiden tarkistus ei onnistunut: {result.get('error', 'tuntematon virhe')}"
    lines = [
        "# Lähteiden tarkistus", "",
        "## Vastaus lähteiden perusteella",
        "",
        result.get("answer_summary") or "Lähteet tarkistettiin, mutta yhteenvetoa ei voitu muodostaa.",
        "",
        "## Tarkistetut lähteet",
        "",
        f"Hakukysely: `{result.get('query')}`",
        f"Avattavissa: {result.get('verified_count', 0)}/{len(result.get('sources') or [])}", "",
    ]
    for index, item in enumerate(result.get("sources") or [], start=1):
        lines.append(f"{index}. **{item.get('title') or 'Nimetön lähde'}**")
        lines.append(f"   - URL: {item.get('final_url') or item.get('url')}")
        if item.get("ok"):
            excerpt = item.get("description") or item.get("preview") or "Sivulta ei löytynyt selkeää tekstikatkelmaa."
            lines.append(f"   - Sivulta luettu ote: {excerpt[:600]}")
        else:
            lines.append(f"   - Tarkistus epäonnistui: {item.get('error', 'tuntematon virhe')}")
        lines.append("")
    lines.extend([
        "Totuusraja: sivujen saavutettavuus ja yllä olevat otteet on tarkistettu. Väitteitä ei ole vielä arvioitu tutkimusnäytöksi.",
        "Semanttiseen muistiin tallennusta ei tarjota ennen sisällöllistä arviointia.",
    ])
    return "\n".join(lines).strip()


def is_source_review_request(message: str) -> bool:
    text = _ascii_finnish(" ".join((message or "").split()).strip(" .!?;:"))
    return any(phrase in text for phrase in ("tarkista lahteet", "avaa ja tarkista lahteet", "tarkista hakutulokset", "review sources"))


def extract_web_query(message: str) -> str:
    text = " ".join((message or "").strip().split())
    lower = text.lower()

    if re.match(
        r"^(tarkista|tarkasta|katso|selvit[aä])\s+.+\s+(sivulta|verkkosivulta|nettisivulta|website(?:sta)?|site(?:lta)?)\b",
        lower,
        flags=re.I,
    ):
        return text.split(maxsplit=1)[1].strip(" :.-")

    prefixes = [
        "hae verkosta",
        "etsi verkosta",
        "verkkohaku",
        "hae netistä",
        "etsi netistä",
        "tarkista verkosta",
        "tarkista netistä",
        "hae internetistä",
        "etsi internetistä",
        "search web",
        "web search",
    ]

    for prefix in prefixes:
        if lower.startswith(prefix):
            return text[len(prefix):].strip(" :.-")

    for marker in ["hakea verkosta", "etsiä verkosta", "tarkistaa verkosta", "hakea netistä", "etsiä netistä"]:
        index = lower.find(marker)
        if index != -1:
            return text[index + len(marker):].strip(" :.-")

    return text.strip()


def is_explicit_web_search_request(message: str) -> bool:
    text = " ".join((message or "").lower().split())
    if re.match(
        r"^(tarkista|tarkasta|katso|selvit[aä])\s+.+\s+(sivulta|verkkosivulta|nettisivulta|website(?:sta)?|site(?:lta)?)\b",
        text,
        flags=re.I,
    ):
        return True

    triggers = [
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
    ]
    return any(trigger in text for trigger in triggers)


def is_current_info_request(message: str) -> bool:
    """Detect short natural-language requests that need fresh web data.

    Keep this intentionally narrow: weather, lottery/current result, exchange
    rate and schedule prompts should use search instead of stale model memory.
    Ordinary chat should still stay in the normal assistant path.
    """
    text = " ".join((message or "").lower().split()).strip(" .!?;:")
    if not text:
        return False
    ascii_text = _ascii_finnish(text)

    if re.match(r"^(saa|weather)\s+[a-z0-9 .'?_-]{2,80}$", ascii_text, flags=re.I):
        return True

    if re.match(r"^s\?+\s+[a-z0-9 .'?_-]{2,80}$", ascii_text, flags=re.I):
        return True

    current_terms = (
        "lotto",
        "loton",
        "veikkaus",
        "jokeri",
        "eurojackpot",
        "sää",
        "weather",
        "kurssi",
        "exchange rate",
        "tänään",
        "today",
        "huomenna",
        "tomorrow",
        "aikataulu",
        "schedule",
    )
    freshness_terms = (
        "edellinen",
        "viimeisin",
        "uusin",
        "oikea numero",
        "tulos",
        "tulokset",
        "nyt",
        "current",
        "latest",
        "today",
        "tänään",
        "huomenna",
    )

    current_terms_ascii = tuple(_ascii_finnish(term) for term in current_terms)
    freshness_terms_ascii = tuple(_ascii_finnish(term) for term in freshness_terms)

    return (
        any(term in text for term in current_terms)
        or any(term in ascii_text for term in current_terms_ascii)
    ) and (
        any(term in text for term in freshness_terms)
        or any(term in ascii_text for term in freshness_terms_ascii)
    )


def is_automatic_web_search_request(message: str) -> bool:
    """Detect factual questions that should use web search before model memory.

    This is intentionally broader than ``is_current_info_request``. It catches
    practical factual questions such as product specs, fuel consumption, prices,
    model years, technical data, regulations, and "how much / what is" prompts.
    It still avoids routing short greetings or personal/chatty messages to the
    search engine.
    """
    raw = " ".join((message or "").split()).strip(" .!?;:")
    if not raw:
        return False

    text = raw.lower()
    ascii_text = _ascii_finnish(text)

    if len(ascii_text) < 8:
        return False

    blocked_starts = (
        "moi", "hei", "heippa", "kiitos", "ok", "okei", "joo", "kylla", "kyllä",
        "muista ", "tallenna ", "lisaa muisti", "lisää muisti", "kirjoita tiedostoon",
        "luo tiedosto", "appendaa", "poista ",
    )
    if any(ascii_text == item or ascii_text.startswith(item) for item in blocked_starts):
        return False

    question_mark = "?" in message
    interrogatives = (
        "mika", "mikä", "mita", "mitä", "milloin", "missä", "missa", "paljon",
        "kuinka", "montako", "kuka", "kenen", "onko", "voiko", "saako",
        "what", "when", "where", "how much", "how many", "who", "which",
    )
    factual_terms = (
        "kulutus", "polttoaine", "fuel consumption", "hinta", "price", "maksaa",
        "spec", "specs", "tekniset tiedot", "technical data", "moottori", "engine",
        "malli", "model", "vuosimalli", "year", "paino", "weight", "mitta",
        "length", "leveys", "width", "teho", "horsepower", "hp", "kw",
        "varaosa", "part number", "ohjekirja", "manual", "laki", "law",
        "asetus", "regulation", "uutinen", "news", "tutkimus", "research",
        "raportti", "report", "arvostelu", "review", "vertailu", "comparison",
        "resepti", "recipe", "ruokaohje", "ohje", "instructions", "miten tehdään",
        "miten tehdaan", "miten teen", "valmistus", "ainesosat", "ingredients",
        "taikina", "pullataikina", "pulla", "leivonta", "baking", "ruoka", "food",
    )
    recipe_terms = (
        "resepti", "recipe", "ruokaohje", "pullataikina", "taikina",
        "pulla", "leivonta", "baking", "ainesosat", "ingredients",
    )

    has_question_word = any(ascii_text.startswith(term) or f" {term} " in f" {ascii_text} " for term in interrogatives)
    has_factual_term = any(_ascii_finnish(term) in ascii_text for term in factual_terms)
    has_recipe_term = any(_ascii_finnish(term) in ascii_text for term in recipe_terms)
    asks_for_instructions = any(term in ascii_text for term in ("ohje", "miten tehdaan", "miten teen", "valmistus"))
    has_model_like_token = bool(re.search(r"\b[a-z]{2,}\s*[-]?\s*\d{2,}[a-z0-9-]*\b|\b\d{4}[a-z]?\b", ascii_text))

    if is_current_info_request(message):
        return True

    if question_mark and (has_question_word or has_factual_term or has_model_like_token):
        return True

    if has_question_word and (has_factual_term or has_model_like_token):
        return True

    if has_recipe_term and (asks_for_instructions or has_question_word or question_mark):
        return True

    return False


def is_web_search_status_request(message: str) -> bool:
    text = _ascii_finnish(" ".join((message or "").split()).strip(" .!?;:"))
    phrases = (
        "toimiiko haku netista", "toimiiko haku verkosta", "toimiiko verkkohaku",
        "toimii haku netista", "toimii haku verkosta", "sinulla toimii haku netista",
        "onko verkkohaku kaytossa", "onko haku netista kaytossa", "voitko hakea netista",
        "voitko hakea verkosta", "pystytko hakemaan netista", "pystytko hakemaan verkosta",
        "mika on web_search", "mika tama web_search", "web_search-moduuli", "web_search moduuli",
        "web search status", "verkkohakun tila",
    )
    return any(phrase in text for phrase in phrases)


def is_web_search_trial_request(message: str) -> bool:
    text = " ".join((message or "").lower().split()).strip(" .!?;:")
    phrases = (
        "haluan kokeilla hakua", "haluan kokeilla yksinkertaista hakua",
        "kokeillaan hakua", "kokeillaan verkkohakua", "kokeile verkkohakua",
        "joo haluan kokeilla", "testataan verkkohakua",
    )
    return any(phrase in text for phrase in phrases)


if __name__ == "__main__":
    root = resolve_project_root()
    query = "Pielinen kalalajit kuha hauki ahven"
    result = web_search(root, query, max_results=5)
    print(format_web_search_reply(result))

