from __future__ import annotations

import json
from pathlib import Path

from app.memory_governance import (
    DELETE_CONFIRMATION,
    delete_memory_entry,
    export_memory_json,
    list_memory_entries,
)


def _memory_path(root: Path) -> Path:
    path = root / "memory" / "sade_memory.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def test_list_memory_entries_handles_missing_file_and_limit_bounds(tmp_path: Path) -> None:
    missing = list_memory_entries(tmp_path)
    assert missing["ok"] is True
    assert missing["count"] == 0
    assert missing["entries"] == []

    _memory_path(tmp_path).write_text(
        "## First\n**Aika:** 2026-01-01\nFirst body\n---\nSecond body without title",
        encoding="utf-8",
    )

    limited = list_memory_entries(tmp_path, limit=0)
    assert limited["count"] == 2
    assert len(limited["entries"]) == 1
    assert limited["entries"][0]["title"] == "Säde-muisti"
    assert limited["entries"][0]["time"] is None

    all_entries = list_memory_entries(tmp_path, limit=5000)
    assert [entry["title"] for entry in all_entries["entries"]] == ["First", "Säde-muisti"]
    assert all_entries["entries"][0]["time"] == "2026-01-01"


def test_export_memory_json_writes_export_and_audit_event(tmp_path: Path) -> None:
    _memory_path(tmp_path).write_text("## Exported\nExport body", encoding="utf-8")

    result = export_memory_json(tmp_path)

    assert result["ok"] is True
    assert result["count"] == 1
    export_path = Path(result["path"])
    assert export_path.exists()
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload["entries"][0]["title"] == "Exported"
    assert "exported_at" in payload

    audit_path = tmp_path / "app" / "memory" / "audit_log.jsonl"
    assert audit_path.exists()
    assert "export_memory_json" in audit_path.read_text(encoding="utf-8")


def test_delete_memory_entry_requires_confirmation_and_existing_memory(tmp_path: Path) -> None:
    denied = delete_memory_entry(tmp_path, "missing", confirmation="wrong")
    assert denied == {
        "ok": False,
        "deleted": False,
        "message": "Poisto vaatii täsmällisen vahvistuslauseen.",
    }

    missing = delete_memory_entry(tmp_path, "missing", confirmation=DELETE_CONFIRMATION)
    assert missing["ok"] is False
    assert missing["deleted"] is False
    assert "ei löytynyt" in missing["message"]


def test_delete_memory_entry_removes_target_and_keeps_backup(tmp_path: Path) -> None:
    _memory_path(tmp_path).write_text(
        "## Keep\nKeep body\n---\n## Remove\nRemove body\n",
        encoding="utf-8",
    )
    entries = list_memory_entries(tmp_path)["entries"]
    remove_id = next(entry["id"] for entry in entries if entry["title"] == "Remove")

    result = delete_memory_entry(tmp_path, remove_id, confirmation=DELETE_CONFIRMATION)

    assert result["ok"] is True
    assert result["deleted"] is True
    assert Path(result["backup"]).exists()
    remaining = _memory_path(tmp_path).read_text(encoding="utf-8")
    assert "Keep body" in remaining
    assert "Remove body" not in remaining

    unknown = delete_memory_entry(tmp_path, "not-a-real-id", confirmation=DELETE_CONFIRMATION)
    assert unknown["ok"] is False
    assert unknown["deleted"] is False
    assert "id:llä" in unknown["message"]
