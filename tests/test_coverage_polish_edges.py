from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app import ai_evals
from app import auth as auth_module
from app.audit_log import audit_log_path, read_audit_log, verify_audit_log, write_audit_event
from app.debug_trace import read_traces, summarize_latest_trace, write_trace
from app.intent_planner import IntentDecision, build_direct_response, plan_response
from app.output_validator import validate_output, validated_reply, wrong_source_used


@dataclass
class DummyGrounding:
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload)


@dataclass
class DummyDecision:
    intent: str
    language: str = "fi"
    use_self_state: bool = False
    allow_business_suggestions: bool = False
    grounding: DummyGrounding | None = None


def test_audit_log_sanitizes_edge_values_and_detects_bad_sequence(tmp_path: Path) -> None:
    write_result = write_audit_event(
        tmp_path,
        category="security",
        action="coverage-edge",
        actor="tester",
        reason="x" * 900,
        target="target",
        details={
            "password": "",
            "content": "hidden text",
            "note": "n" * 900,
            "count": 3,
            "nested": {"token": "secret-token"},
        },
    )
    assert write_result["ok"] is True

    data = read_audit_log(tmp_path)
    assert data["valid"] is True
    item = data["items"][-1]
    assert item["details"]["password"] == ""
    assert item["details"]["content"] == "[REDACTED]"
    assert item["details"]["nested"]["token"] == "[REDACTED]"
    assert item["details"]["note"].endswith("…[truncated]")
    assert item["details"]["count"] == 3
    assert item["reason"].endswith("x")

    path = audit_log_path(tmp_path)
    entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    entries[0]["sequence"] = 99
    path.write_text(json.dumps(entries[0], ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    broken = verify_audit_log(tmp_path)
    assert broken["valid"] is False
    assert "sequence" in broken["error"]


def test_auth_edge_paths_for_bad_json_sessions_and_expiry(tmp_path: Path) -> None:
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not-json", encoding="utf-8")
    assert auth_module._read_json(bad_json, {"fallback": True}) == {"fallback": True}

    auth_module._write_private_json(auth_module.sessions_path(tmp_path), {"version": 1, "sessions": "not-a-list"})
    loaded = auth_module._load_sessions(tmp_path)
    assert loaded["sessions"] == []

    future = int(time.time()) + 3600
    auth_module._write_private_json(
        auth_module.sessions_path(tmp_path),
        {
            "version": 1,
            "sessions": [
                {"token_hash": auth_module._token_hash("expired"), "expires_at": 0, "username": "old"},
                {"token_hash": auth_module._token_hash("active"), "expires_at": future, "username": "new"},
            ],
        },
    )

    assert auth_module.get_session(tmp_path, "missing") is None
    remaining = auth_module._load_sessions(tmp_path)["sessions"]
    assert len(remaining) == 1
    assert remaining[0]["username"] == "new"
    assert auth_module.revoke_session(tmp_path, "not-present") is False


def test_debug_trace_skips_corrupt_lines_and_summarizes_source_counts(tmp_path: Path) -> None:
    first = write_trace(
        tmp_path,
        event="web_search_executed",
        user_message="password=supersecret token=abc123",
        route="web",
        decision="search",
        details={"query": "Python release", "sources_found": "5", "token": "drop-me"},
    )
    assert first["ok"] is True
    assert "supersecret" not in first["entry"]["message_preview"]
    assert "token" not in first["entry"]["details"]

    trace_file = tmp_path / "memory" / "debug_trace.jsonl"
    with trace_file.open("a", encoding="utf-8") as handle:
        handle.write("not-json\n")

    write_trace(
        tmp_path,
        event="web_sources_read",
        details={"sources_read": "3"},
    )
    write_trace(
        tmp_path,
        event="output_validated",
        details={"result": "accept"},
    )

    traces = read_traces(tmp_path, limit=10)
    assert traces["count"] == 3

    summary = summarize_latest_trace(tmp_path)
    assert summary["sources_found"] == 5
    assert summary["sources_read"] == 3
    assert summary["validator_result"] == "accept"
    assert summary["note"] == "Operational trace only; no hidden reasoning is exposed."


def test_output_validator_object_grounding_and_warning_paths() -> None:
    identity_decision = DummyDecision(
        intent="project_identity",
        grounding=DummyGrounding(
            {
                "target_scope": "project_state",
                "user_is_asking_about": "identity question",
                "should_use_web": False,
            }
        ),
    )
    identity_result = validate_output(identity_decision, "Olen Local AI Workspace -avustaja.")
    assert identity_result["ok"] is True
    assert identity_result["issues"] == []

    warning_result = validate_output({"intent": "normal_chat", "language": "fi"}, "Freelance laskutus voisi olla yksi sivuhuomio.")
    assert warning_result["ok"] is True
    assert warning_result["action"] == "accept_with_warnings"
    assert warning_result["issues"] == ["unexpected_business_suggestion"]

    memory_decision = {
        "intent": "normal_chat",
        "grounding": {
            "target_scope": "assistant_memory",
            "should_use_memory": False,
            "should_use_chat_context": False,
        },
    }
    memory_result = validate_output(memory_decision, "Muistan tämän.")
    assert wrong_source_used("Muistan tämän.", memory_decision) is True
    assert memory_result["action"] == "accept_with_warnings"
    assert memory_result["issues"] == ["memory_ignored_for_memory_question"]

    debug_decision = {"intent": "normal_chat", "language": "fi"}
    assert "Vastaus ei sopinut" in validated_reply(debug_decision, "target_scope: timeless_general_knowledge")


def test_intent_planner_remaining_safe_edges() -> None:
    tired = plan_response("Mitä teen jos väsyttää", ui_language="fi")
    assert tired.use_chat_context is False

    fastapi = plan_response("What is FastAPI?", ui_language="en")
    assert fastapi.use_chat_context is False

    explicit_google = plan_response("Google Python documentation", ui_language="en")
    assert explicit_google.intent == "current_external_information"
    assert explicit_google.reason == "explicit_web_search_request"

    local_followup = plan_response("Lähimmän apteekki auki", ui_language="fi")
    assert local_followup.intent == "current_external_information"
    assert local_followup.reason == "local_nature_city_transport_or_service_lookup"

    technical = plan_response("What fuel consumption data Volvo Penta engine", ui_language="en")
    assert technical.intent == "current_external_information"
    assert technical.reason == "specific_external_product_or_technical_fact"

    health_decision = IntentDecision(intent="health_lifestyle_general", language="fi")
    assert build_direct_response(health_decision, "Kofeiini ja terveys") is None


def test_static_evals_unknown_case_is_reported_as_not_ok(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(ai_evals, "EVAL_CASES", [{"id": "unknown-case", "kind": "unknown"}])

    result = ai_evals.run_static_evals(tmp_path)

    assert result["ok"] is False
    assert result["passed"] == 0
    assert result["total"] == 1
    assert result["results"] == []
