from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.audit_log import AuditLogError, read_audit_log, verify_audit_log, write_audit_event


def test_audit_log_is_hash_chained_and_redacts_sensitive_values(tmp_path: Path) -> None:
    write_audit_event(
        tmp_path,
        category="configuration",
        action="update",
        actor="test",
        reason="Test event",
        target="app/config.json",
        details={"temperature": 0.7, "password": "secret", "content": "private"},
    )
    write_audit_event(tmp_path, category="tool", action="run", details={"tool": "rag"})

    result = read_audit_log(tmp_path)

    assert result["valid"] is True
    assert result["count"] == 2
    assert result["items"][0]["details"]["password"] == "[REDACTED]"
    assert result["items"][0]["details"]["content"] == "[REDACTED]"
    assert result["items"][1]["previous_hash"] == result["items"][0]["event_hash"]


def test_audit_log_detects_tampering_and_refuses_to_append(tmp_path: Path) -> None:
    write_audit_event(tmp_path, category="tool", action="run")
    path = tmp_path / "app" / "memory" / "audit_log.jsonl"
    entry = json.loads(path.read_text(encoding="utf-8"))
    entry["action"] = "tampered"
    path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    assert verify_audit_log(tmp_path)["valid"] is False
    with pytest.raises(AuditLogError):
        write_audit_event(tmp_path, category="tool", action="second")


def test_audit_log_rejects_invalid_lines_and_invalid_event_metadata(tmp_path: Path) -> None:
    path = tmp_path / "app" / "memory" / "audit_log.jsonl"
    path.parent.mkdir(parents=True)

    path.write_text("not-json\n", encoding="utf-8")
    invalid_json = verify_audit_log(tmp_path)
    assert invalid_json["valid"] is False
    assert "JSON" in invalid_json["error"]
    assert read_audit_log(tmp_path)["items"] == []

    path.write_text("[]\n", encoding="utf-8")
    non_object = verify_audit_log(tmp_path)
    assert non_object["valid"] is False
    assert "objekti" in non_object["error"]

    with pytest.raises(ValueError):
        write_audit_event(tmp_path, category="tool", action="run", outcome="unknown")

    with pytest.raises(ValueError):
        write_audit_event(tmp_path, category="tool", action="run", risk_level="critical")
