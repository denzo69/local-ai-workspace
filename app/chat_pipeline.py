from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.conversation_context import build_contextual_query, extract_conversation_context
from app.debug_trace import write_trace
from app.intent_planner import build_direct_response, plan_response
from app.language_pack import build_language_context
from app.manual_behavior import try_handle_manual_behavior
from app.output_validator import validate_output
from app.prompt_injection import analyze_prompt_injection


@dataclass(frozen=True)
class ChatPipelineDependencies:
    project_path: Path
    sade_memory_path: Path
    memory_entry_class: type
    append_chat_log: Callable[[str, str], Any]
    load_config: Callable[[], Dict[str, Any]]
    append_markdown_entry: Callable[[Path, Any], Dict[str, Any]]
    extract_memory_command: Callable[[str], Optional[str]]
    handle_learning_review_chat_command: Callable[[str], Dict[str, Any]]
    handle_learning_chat_command: Callable[[str], Dict[str, Any]]
    handle_task_chat_command: Callable[[str], Dict[str, Any]]
    handle_rag_chat_command: Callable[[str], Dict[str, Any]]
    route_tool_request: Callable[[Path, str], Dict[str, Any]]
    build_web_search_chat_result: Callable[..., Dict[str, Any]]
    get_tool_policy: Callable[[str], Dict[str, Any]]
    log_tool_event: Callable[..., Any]
    audit: Callable[..., Any]
    audit_risk: Callable[[str], str]
    build_sade_prompt: Callable[[str, Optional[Any]], str]
    ask_ollama: Callable[[str], str]
    get_chat_context: Callable[[Optional[int]], str] = lambda max_chars=None: ""


def _model_name(deps: ChatPipelineDependencies) -> str:
    return deps.load_config().get("ollama_model", "gpt-oss:20b")


def _chat_response(
    deps: ChatPipelineDependencies,
    reply: str,
    *,
    actions: Any = None,
    ok: bool = True,
) -> Dict[str, Any]:
    response: Dict[str, Any] = {
        "ok": ok,
        "reply": reply,
        "model": _model_name(deps),
        "time": datetime.now().isoformat(timespec="seconds"),
    }
    if actions is not None:
        response["actions"] = actions
    return response


def _validate_planned_reply(planning: Any, reply: str) -> str:
    validation = validate_output(planning, reply)
    return str(validation.get("reply") or reply or "").strip()


def _trace(
    deps: ChatPipelineDependencies,
    *,
    event: str,
    message: str,
    route: str,
    decision: str,
    route_used: str | None = None,
    details: Dict[str, Any] | None = None,
) -> None:
    payload = dict(details or {})
    if route_used:
        payload["route_used"] = route_used
    try:
        write_trace(
            deps.project_path,
            event=event,
            user_message=message,
            route=route,
            decision=decision,
            details=payload,
        )
    except Exception:
        pass


def _format_web_sources(search_result: Dict[str, Any], *, max_sources: int = 4) -> str:
    lines: list[str] = []
    checked_sources = search_result.get("checked_sources") or []
    if checked_sources:
        lines.append("Luetut lähdeotteet:")
        for index, item in enumerate(checked_sources[:max_sources], start=1):
            title = str(item.get("title") or "Lähde").strip()
            url = str(item.get("final_url") or item.get("url") or "").strip()
            excerpt = " ".join(
                str(item.get("description") or item.get("preview") or item.get("snippet") or "").split()
            )
            lines.append(f"{index}. {title}\n   URL: {url}")
            if excerpt:
                lines.append(f"   Luettu ote: {excerpt[:900]}")
            elif item.get("error"):
                lines.append(f"   Luku epäonnistui: {item.get('error')}")
        lines.append("")

    if search_result.get("source_answer_summary"):
        lines.append("Automaattinen lähdeyhteenveto:")
        lines.append(str(search_result.get("source_answer_summary")))
        lines.append("")

    if lines:
        lines.append("Hakutuloskatkelmat:")

    for index, item in enumerate((search_result.get("results") or [])[:max_sources], start=1):
        title = str(item.get("title") or "Lähde").strip()
        url = str(item.get("url") or "").strip()
        snippet = " ".join(str(item.get("snippet") or "").split())
        lines.append(f"{index}. {title}\n   URL: {url}")
        if snippet:
            lines.append(f"   Katkelma: {snippet[:500]}")
    return "\n".join(lines).strip()


def _append_source_links(reply: str, search_result: Dict[str, Any], *, max_sources: int = 4) -> str:
    items = (search_result.get("results") or [])[:max_sources]
    if not items:
        return reply.strip()

    lines = [reply.strip(), "", "Lähteet:"]
    for index, item in enumerate(items, start=1):
        title = str(item.get("title") or "Lähde").strip()
        url = str(item.get("url") or "").strip()
        if url:
            lines.append(f"{index}. {title} — {url}")
        else:
            lines.append(f"{index}. {title}")
    return "\n".join(lines).strip()


def _contextual_search_message(message: str, planning: Any, deps: ChatPipelineDependencies) -> str:
    """Enrich short follow-up search queries with recent visible topic context.

    This is intentionally compact: search engines need a few topic/location
    keywords, not the full chat log. The normal answer prompt still receives
    the user's original message.
    """
    if not getattr(planning, "use_chat_context", False):
        return message

    try:
        context = deps.get_chat_context(1500)
    except Exception:
        context = ""
    if not context.strip():
        return message

    conversation_context = extract_conversation_context(context, latest_message=message)
    query = build_contextual_query(message, conversation_context)
    _trace(
        deps,
        event="conversation_context_used",
        message=message,
        route="conversation_context",
        decision="enriched_query" if query != message else "kept_original",
        details={
            "conversation_context": conversation_context.to_dict(),
            "search_query": query,
        },
    )
    return query or message


def _build_web_grounded_prompt(message: str, planning: Any, search_result: Dict[str, Any]) -> str:
    source_context = _format_web_sources(search_result)
    language_context = build_language_context(message)
    return f"""
Olet Local AI Workspace -avustaja.

Suomen kielen vastausohje:
{language_context}

Käyttäjän kysymys:
{message}

Verkkohaku:
- Hakukysely: {search_result.get("query")}
- Provider: {search_result.get("provider")}

Hakutulosten otsikot, URLit ja katkelmat:
{source_context or "Ei hakutuloksia."}

Tehtävä:
Vastaa käyttäjän kysymykseen luonnollisesti ja käytännöllisesti.
Perusta vastaus vain yllä oleviin hakutuloksiin ja katkelmiin sekä varovaiseen yleiseen päättelyyn.
Älä väitä lukeneesi koko verkkosivuja, jos käytössä on vain hakutuloskatkelmat.
Jos hakutuloskatkelmat eivät riitä tarkkaan vastaukseen, sano se lyhyesti ja kerro mitä lähteistä voi silti päätellä.
Älä palauta pelkkää hakutuloslistaa. Muodosta käyttäjälle kerrottu vastaus.
Pidä vastaus samalla kielellä kuin käyttäjän kysymys, ellei käyttäjä pyydä muuta.
Lopussa ei tarvitse toistaa pitkiä totuusrajoja; lähdelista lisätään erikseen.
""".strip()


def _answer_from_web_search(message: str, planning: Any, deps: ChatPipelineDependencies, *, reason: str) -> Dict[str, Any]:
    search_message = _contextual_search_message(message, planning, deps)
    tool_result = deps.build_web_search_chat_result(search_message, reason=reason)
    search_result = tool_result.get("result", tool_result)
    _trace(
        deps,
        event="web_search_executed",
        message=message,
        route="web_search",
        decision="searched",
        details={
            "reason": reason,
            "query": search_message,
            "sources_found": len(search_result.get("results") or []) if isinstance(search_result, dict) else 0,
            "provider": search_result.get("provider") if isinstance(search_result, dict) else None,
        },
    )
    if not isinstance(search_result, dict) or not search_result.get("ok") or not search_result.get("results"):
        reply = str(tool_result.get("reply") or "").strip()
        return {
            "tool_result": tool_result,
            "reply": reply or "Verkkohaku ei palauttanut käyttökelpoisia tuloksia.",
            "used_model_summary": False,
        }

    source_read: Dict[str, Any] = {"ok": False, "sources": [], "verified_count": 0}
    try:
        from app import web_search as web_search_module

        source_read = web_search_module.read_search_result_sources(search_result, max_sources=3)
        search_result = {
            **search_result,
            "checked_sources": source_read.get("sources") or [],
            "verified_source_count": source_read.get("verified_count", 0),
            "source_answer_summary": source_read.get("answer_summary") or "",
        }
        tool_result["result"] = search_result
        _trace(
            deps,
            event="web_sources_read",
            message=message,
            route="source_reader",
            decision="read_attempted",
            details={
                "sources_read": len(source_read.get("sources") or []),
                "verified_source_count": source_read.get("verified_count", 0),
            },
        )
    except Exception as error:
        search_result = {
            **search_result,
            "checked_sources": [],
            "verified_source_count": 0,
            "source_read_error": str(error),
        }
        tool_result["result"] = search_result

    try:
        prompt = _build_web_grounded_prompt(message, planning, search_result)
        reply = deps.ask_ollama(prompt).strip()
        if reply:
            return {
                "tool_result": tool_result,
                "reply": _append_source_links(reply, search_result),
                "used_model_summary": True,
            }
    except Exception:
        pass

    source_summary = str(source_read.get("answer_summary") or "").strip()
    if source_summary and source_read.get("verified_count", 0) > 0:
        return {
            "tool_result": tool_result,
            "reply": _append_source_links(source_summary, search_result),
            "used_model_summary": False,
        }

    return {
        "tool_result": tool_result,
        "reply": str(tool_result.get("reply") or "").strip(),
        "used_model_summary": False,
    }


def handle_chat_message(message: str, deps: ChatPipelineDependencies) -> Dict[str, Any] | JSONResponse:
    """Run the Local AI Workspace chat pipeline.

    The FastAPI route should stay thin. This function owns the response order:
    dev command, manual behavior, direct response, memory, learning, task, RAG,
    tool routing, automatic web search, and finally model fallback.
    """

    # CHAT_COMMAND_LAYER_V1_START
    # Dev Mode -komennot käsitellään suoraan chat-putken alussa.
    # Näin kielimalli ei ehdi keksiä koodikarttaa omasta päästään.
    try:
        from app.dev_chat_commands import try_handle_dev_command as _try_handle_dev_command

        if message:
            command_reply = _try_handle_dev_command(deps.project_path, str(message))

            if command_reply is not None and str(command_reply).strip():
                try:
                    deps.append_chat_log(str(message), str(command_reply))
                except Exception:
                    pass

                return JSONResponse({
                    "ok": True,
                    "source": "chat_command_layer_v1",
                    "response": command_reply,
                    "reply": command_reply,
                    "answer": command_reply,
                    "message": command_reply,
                    "text": command_reply,
                })

    except Exception as command_error:
        error_text = f"Chat Command Layer tunnisti komennon, mutta suoritus epäonnistui: {command_error}"

        return JSONResponse({
            "ok": False,
            "source": "chat_command_layer_v1",
            "response": error_text,
            "reply": error_text,
            "answer": error_text,
            "message": error_text,
            "text": error_text,
        }, status_code=500)
    # CHAT_COMMAND_LAYER_V1_END

    if not message.strip():
        raise HTTPException(status_code=400, detail="Viesti ei saa olla tyhjä.")

    injection_analysis = analyze_prompt_injection(message)
    try:
        write_trace(
            deps.project_path,
            event="chat_received",
            user_message=message,
            route="chat",
            decision="analyze_message",
            details={"prompt_injection": injection_analysis},
        )
    except Exception:
        pass

    planning = plan_response(message)
    try:
        write_trace(
            deps.project_path,
            event="chat_intent_planned",
            user_message=message,
            route="intent_planner",
            decision=planning.intent,
            details=planning.to_dict(),
        )
    except Exception:
        pass

    manual_behavior = try_handle_manual_behavior(deps.project_path, message)
    _trace(
        deps,
        event="manual_behavior_checked",
        message=message,
        route="manual_behavior",
        decision="handled" if manual_behavior.get("handled") else "not_handled",
        details={"category": manual_behavior.get("category")},
    )
    if manual_behavior.get("handled"):
        if manual_behavior.get("category") == "local_external_information":
            web_answer = _answer_from_web_search(message, planning, deps, reason="manual_local_external_information")
            reply = _validate_planned_reply(planning, str(web_answer.get("reply") or "").strip())
            tool_result = web_answer.get("tool_result") or {}
            tool_name = str(tool_result.get("tool", "web_search"))
            _trace(
                deps,
                event="manual_behavior_handled",
                message=message,
                route="manual_behavior",
                decision="local_external_information",
                route_used="web_search",
                details={"category": manual_behavior.get("category"), "tool": tool_name},
            )
            try:
                deps.log_tool_event(
                    deps.project_path,
                    tool=tool_name,
                    action="chat",
                    request={"message": message},
                    result=tool_result.get("result", tool_result),
                )
                deps.audit(
                    category="chat_tool",
                    action=tool_name,
                    outcome="success" if tool_result.get("result", tool_result).get("ok", True) else "failure",
                    risk_level=deps.audit_risk("search"),
                    reason="Paikallista tai ajantasaista ulkoista tietoa vaativa chat-kysymys haettiin verkosta ja tiivistettiin.",
                    details={"message": message, "handled": True, "route": "manual_local_external_information"},
                )
            except Exception:
                pass

            deps.append_chat_log(message, reply)
            return _chat_response(deps, reply, actions=tool_result.get("actions") or None)

        reply = _validate_planned_reply(planning, str(manual_behavior.get("reply") or "").strip())
        _trace(
            deps,
            event="manual_behavior_handled",
            message=message,
            route="manual_behavior",
            decision=str(manual_behavior.get("category") or "handled"),
            route_used="manual_behavior",
            details={"category": manual_behavior.get("category")},
        )
        try:
            write_trace(
                deps.project_path,
                event="chat_manual_behavior",
                user_message=message,
                route="manual_behavior",
                decision=str(manual_behavior.get("category") or "handled"),
                details={"category": manual_behavior.get("category")},
            )
        except Exception:
            pass

        deps.append_chat_log(message, reply)
        return _chat_response(deps, reply)

    direct_reply = build_direct_response(planning, message)
    if direct_reply:
        reply = _validate_planned_reply(planning, direct_reply)
        deps.append_chat_log(message, reply)
        return _chat_response(deps, reply)

    memory_text = deps.extract_memory_command(message)

    if memory_text:
        entry = deps.memory_entry_class(
            title="Keskustelusta tallennettu muisto",
            text=memory_text,
            tags=["chat", "automaattinen muisti"],
        )

        save_result = deps.append_markdown_entry(deps.sade_memory_path, entry)

        reply = (
            f"Tallensin tämän Säde-muistiin:\n\n"
            f"{memory_text}\n\n"
            f"Aika: {save_result['time']}"
        )

        deps.append_chat_log(message, reply)
        return _chat_response(deps, reply)

    learning_review_command = deps.handle_learning_review_chat_command(message)

    if learning_review_command.get("handled"):
        reply = learning_review_command.get("reply", "Oppimiskatsauskomento käsitelty.")
        deps.append_chat_log(message, reply)
        return _chat_response(deps, reply)

    learning_command = deps.handle_learning_chat_command(message)

    if learning_command.get("handled"):
        reply = learning_command.get("reply", "Oppimiskomento käsitelty.")
        deps.append_chat_log(message, reply)
        return _chat_response(deps, reply)

    task_command = deps.handle_task_chat_command(message)

    if task_command.get("handled"):
        reply = task_command.get("reply", "Tehtäväkomento käsitelty.")
        deps.append_chat_log(message, reply)
        return _chat_response(deps, reply)

    rag_command = deps.handle_rag_chat_command(message)

    if rag_command.get("handled"):
        reply = rag_command.get("reply", "RAG-komento käsitelty.")
        deps.append_chat_log(message, reply)
        return _chat_response(deps, reply)

    tool_result = deps.route_tool_request(deps.project_path, message)
    _trace(
        deps,
        event="tool_router_checked",
        message=message,
        route="tool_router",
        decision="handled" if tool_result.get("handled") else "not_handled",
        details={"tool": tool_result.get("tool")},
    )

    if not tool_result.get("handled"):
        try:
            from app import web_search as web_search_module
            current_info = web_search_module.is_current_info_request(message)
            automatic_web = web_search_module.is_automatic_web_search_request(message)
            web_allowed = "web_search" not in getattr(planning, "blocked_context_domains", [])
            should_search = bool(web_allowed and (planning.needs_web or automatic_web))

            _trace(
                deps,
                event="automatic_web_search_checked",
                message=message,
                route="web_search",
                decision="search" if should_search else "skip",
                details={
                    "planning_needs_web": planning.needs_web,
                    "is_current_info_request": current_info,
                    "is_automatic_web_search_request": automatic_web,
                    "web_allowed": web_allowed,
                },
            )

            if should_search:
                web_answer = _answer_from_web_search(message, planning, deps, reason="automatic_search_and_answer")
                tool_result = web_answer.get("tool_result", {})
                tool_result["reply"] = web_answer.get("reply", tool_result.get("reply", ""))
                _trace(
                    deps,
                    event="automatic_web_search_handled",
                    message=message,
                    route="web_search",
                    decision="handled",
                    route_used="web_search",
                    details={"result_ok": tool_result.get("result", tool_result).get("ok", False)},
                )
        except Exception as error:
            tool_result = {
                "handled": True,
                "tool": "web_search",
                "result": {"ok": False, "error": str(error), "query": message},
                "reply": f"Web search routing failed before the model could answer: {error}",
            }

    if tool_result.get("handled"):
        if str(tool_result.get("tool") or "") == "web_search":
            search_result = tool_result.get("result", tool_result)
            if isinstance(search_result, dict) and search_result.get("ok") and search_result.get("results"):
                web_answer = _answer_from_web_search(message, planning, deps, reason=str(tool_result.get("reason") or "tool_router_web_search"))
                tool_result = web_answer.get("tool_result", tool_result)
                tool_result["reply"] = web_answer.get("reply", tool_result.get("reply", ""))

        reply = str(tool_result.get("reply") or "").strip()
        if not reply:
            reply = (
                "The request was routed to a tool, but the tool returned no visible reply. "
                "Check the tool result and server logs."
            )
        reply = _validate_planned_reply(planning, reply)

        tool_name = str(tool_result.get("tool", "tool_router"))
        tool_policy = deps.get_tool_policy(tool_name)

        deps.log_tool_event(
            deps.project_path,
            tool=tool_name,
            action="chat",
            request={"message": message},
            result=tool_result.get("result", tool_result),
        )
        deps.audit(
            category="chat_tool",
            action=tool_name,
            outcome="success" if tool_result.get("result", tool_result).get("ok", True) else "failure",
            risk_level=deps.audit_risk(str(tool_policy.get("risk_level", "medium"))),
            reason="Chatin työkalupyyntö käsiteltiin.",
            details={"message": message, "handled": True, "tool_policy": tool_policy},
        )
        try:
            write_trace(
                deps.project_path,
                event="chat_tool_route",
                user_message=message,
                route="tool_router",
                decision="handled",
                tool=tool_name,
                details={"tool_policy": tool_policy, "result_ok": tool_result.get("result", tool_result).get("ok", True)},
            )
        except Exception:
            pass

        deps.append_chat_log(message, reply)
        return _chat_response(deps, reply, actions=tool_result.get("actions") or None)

    prompt = deps.build_sade_prompt(message, planning)
    _trace(
        deps,
        event="llm_fallback_used",
        message=message,
        route="model_provider",
        decision="fallback_to_llm",
        route_used="llm_fallback",
        details={"intent": getattr(planning, "intent", None)},
    )
    try:
        reply = deps.ask_ollama(prompt)
    except HTTPException as error:
        if error.status_code == 502 and planning.needs_web:
            try:
                tool_result = deps.build_web_search_chat_result(message, reason="model_provider_fallback")
                reply = _validate_planned_reply(planning, str(tool_result.get("reply") or "").strip())
                if reply:
                    deps.append_chat_log(message, reply)
                    return _chat_response(deps, reply, actions=tool_result.get("actions") or None)
            except Exception:
                pass
        raise
    try:
        write_trace(
            deps.project_path,
            event="chat_llm_route",
            user_message=message,
            route="model_provider",
            decision="generated_reply",
            details={"model": _model_name(deps), "reply_chars": len(reply)},
        )
    except Exception:
        pass

    reply = _validate_planned_reply(planning, reply)
    deps.append_chat_log(message, reply)

    return _chat_response(deps, reply)
