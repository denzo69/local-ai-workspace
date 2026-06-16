from __future__ import annotations

from pathlib import Path
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

    try:
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

    if not text:
        return {"would_route": False, "tool": None, "reason": "empty_message"}

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
