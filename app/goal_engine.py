from __future__ import annotations

"""Local AI Workspace — Goal Engine v1.

Read-only module for checking learning and development status.
Does not modify files or grant permission for changes.
"""

import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ComponentStatus:
    id: str
    label: str
    path: str
    status: str
    role: str


@dataclass
class GoalRecommendation:
    id: str
    title: str
    reason: str
    risk_level: str
    status: str
    suggested_files: List[str]
    test_commands: List[str]
    requires_jani_approval: bool


def resolve_project_root(project_root: Optional[Path] = None) -> Path:
    if project_root is None:
        return Path(__file__).resolve().parent.parent
    root = Path(project_root).resolve()
    return root.parent if root.name.lower() == "app" else root


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_text(path: Path, tail: int | None = None) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-tail:] if tail and len(text) > tail else text


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def file_status(root: Path, rel: str, missing_status: str = "planned", test_rel: Optional[str] = None) -> str:
    if not (root / rel).exists():
        return missing_status
    return "tested_candidate" if test_rel and (root / test_rel).exists() else "implemented_candidate"


def is_available(status: str) -> bool:
    return status in {"implemented_candidate", "tested_candidate", "tested", "active"}


def collect_components(root: Path) -> List[ComponentStatus]:
    return [
        ComponentStatus("development_roadmap", "Development Roadmap", "docs/development_roadmap.md", file_status(root, "docs/development_roadmap.md"), "Development roadmap and phased planning."),
        ComponentStatus("code_rewrite_protocol", "Code Rewrite Protocol", "docs/code_rewrite_protocol.md", file_status(root, "docs/code_rewrite_protocol.md"), "Safe code-change process."),
        ComponentStatus("audit_log", "Audit Log", "app/audit_log.py", file_status(root, "app/audit_log.py", test_rel="tests/test_audit_log.py"), "Technical event log."),
        ComponentStatus("web_search", "Web Search Tool", "app/web_search.py", file_status(root, "app/web_search.py", test_rel="tests/test_web_search.py"), "Controlled web search for factual questions."),
        ComponentStatus("finnish_language_pack", "Finnish Language Pack", "app/language_pack.py", file_status(root, "app/language_pack.py", test_rel="tests/test_language_pack.py"), "Finnish language and vocabulary context."),
        ComponentStatus("learning_feedback", "Learning Feedback Memory", "app/learning_feedback.py", file_status(root, "app/learning_feedback.py", test_rel="tests/test_learning_feedback.py"), "Stores user corrections as learning examples."),
        ComponentStatus("goal_engine", "Goal Engine", "app/goal_engine.py", file_status(root, "app/goal_engine.py", test_rel="tests/test_goal_engine.py"), "Read-only controller for development and learning status."),
        ComponentStatus("task_state", "Task State", "memory/task_state.json", file_status(root, "memory/task_state.json"), "State for unfinished tasks."),
        ComponentStatus("tests", "Automated Tests", "tests", "implemented_candidate" if (root / "tests").exists() else "planned", "Automated pytest test suite."),
        ComponentStatus("memory_cleaner", "Memory Cleaner", "app/memory_cleaner.py", file_status(root, "app/memory_cleaner.py", "missing", "tests/test_memory_cleaner.py"), "Memory cleanup; not active without permission."),
    ]


def by_id(components: List[ComponentStatus]) -> Dict[str, ComponentStatus]:
    return {item.id: item for item in components}


def emoji(status: str) -> str:
    return {"implemented_candidate": "✅", "tested_candidate": "🧪", "tested": "✅", "active": "✅", "planned": "⚪", "missing": "⚪", "prepared": "🟡", "in_progress": "🟡"}.get(status, "•")


def latest_memory_excerpt(root: Path) -> str:
    for rel in ["memory/autobiographical_memory.md", "uploads/autobiographical_memory.md"]:
        text = read_text(root / rel, 14000)
        if text:
            headings = list(re.finditer(r"^##\s+(.+)$", text, flags=re.MULTILINE))
            if headings:
                return text[headings[-1].start():].strip()[:1600]
            return text.strip()[-1600:]
    return "No recent autobiographical memory entry was found."


def learning_findings(root: Path, components: List[ComponentStatus]) -> List[str]:
    c = by_id(components)
    findings: List[str] = []
    findings.append("The development roadmap exists and guides the project in phases." if c["development_roadmap"].status == "implemented_candidate" else "The development roadmap is not yet visible as an implemented document.")
    findings.append("The web search tool exists and has an automated test." if is_available(c["web_search"].status) else "The web search tool is still missing or not installed in this project.")
    if is_available(c["finnish_language_pack"].status):
        findings.append("The Finnish language pack appears to be connected to main reply generation." if "build_language_context" in read_text(root / "app/main.py") else "The Finnish language pack exists, but it does not yet appear to be connected to main reply generation.")
    else:
        findings.append("The Finnish language pack is missing or not installed in this project.")
    findings.append("Learning feedback storage exists and has an automated test." if is_available(c["learning_feedback"].status) else "The feedback memory that learns from user corrections is still missing. This is an important next layer for adaptive behavior.")
    if is_available(c["audit_log"].status):
        main_text = read_text(root / "app/main.py")
        findings.append("Audit Log v1 exists and core API, write, task, and tool actions are connected to centralized auditing." if "write_audit_event" in main_text and "tools_router_run" in main_text else "The audit log exists, but centralized integration was not detected yet.")
    else:
        findings.append("The audit log is missing or not installed in this project.")
    if c["memory_cleaner"].status == "missing":
        findings.append("The memory cleaner is missing and automatic memory deletion is not active. This is the safer current state.")
    return findings


def next_recommendation(root: Path, components: List[ComponentStatus]) -> GoalRecommendation:
    c = by_id(components)
    if not is_available(c["web_search"].status):
        return GoalRecommendation("web_search_tool_v1", "Web Search Tool v1", "Factual questions need sources so the assistant does not guess or invent information.", "controlled_write", "recommended", ["app/web_search.py", "docs/web_search_policy.md", "data/web_source_registry_fi.json", "app/tool_router.py"], ["python app\\web_search.py"], True)
    if not is_available(c["learning_feedback"].status):
        return GoalRecommendation("learning_feedback_memory_v1", "Learning Feedback Memory v1", "The assistant needs a mechanism that turns user corrections into learning examples instead of repeating the same mistakes.", "controlled_write", "recommended", ["app/learning_feedback.py", "data/language_incidents.jsonl", "data/correction_examples.jsonl", "docs/learning_feedback_policy.md", "app/tool_router.py"], ["python app\\learning_feedback.py"], True)
    if is_available(c["finnish_language_pack"].status) and "build_language_context" not in read_text(root / "app/main.py"):
        return GoalRecommendation("language_pack_llm_integration_v1", "Finnish Language Pack LLM Integration v1", "The language pack exists, but it does not yet appear to be passed to the model before replies.", "controlled_write", "recommended", ["app/main.py", "app/language_pack.py"], ["python app\\language_pack.py"], True)
    if is_available(c["audit_log"].status) and "write_audit_event" not in read_text(root / "app/main.py"):
        return GoalRecommendation("audit_log_tool_router_integration_v1", "Audit Log Tool Router Integration v1", "The audit log exists, but tool routes may not yet be recorded automatically.", "controlled_write", "recommended", ["app/tool_router.py", "app/audit_log.py"], ["python app\\audit_log.py"], True)
    if c["task_state"].status != "implemented_candidate":
        return GoalRecommendation("task_state_v1", "Task State v1", "The assistant needs task-state awareness: what is currently unfinished and what should happen next.", "controlled_write", "recommended", ["memory/task_state.json", "app/task_state.py", "docs/task_state_policy.md"], ["python app\\task_state.py"], True)
    return GoalRecommendation("automated_tests_v1", "Automated Tests v1", "Once the core modules exist, the next quality step is to test them automatically.", "controlled_write", "recommended", ["tests/test_tool_router.py", "tests/test_goal_engine.py", "tests/test_language_pack.py"], ["python -m pytest"], True)


def build_goal_status(project_root: Optional[Path] = None) -> Dict[str, Any]:
    root = resolve_project_root(project_root)
    comps = collect_components(root)
    rec = next_recommendation(root, comps)
    persona = read_json(root / "memory/persona_state.json") or read_json(root / "uploads/persona_state.json")
    return {"ok": True, "time": now_iso(), "project_root": str(root), "mode": "read_only_goal_status", "components": [asdict(i) for i in comps], "learning_findings": learning_findings(root, comps), "recent_memory": latest_memory_excerpt(root), "recommendation": asdict(rec), "persona_development": persona.get("development", {}), "truth_boundary": ["Goal Engine v1 does not modify files.", "File existence does not mean a feature is tested.", "A recommendation is not approval or implementation."]}


def build_learning_status_reply(project_root: Optional[Path] = None) -> str:
    status = build_goal_status(project_root)
    comps = [ComponentStatus(**i) for i in status["components"]]
    rec = status["recommendation"]
    lines = ["# Learning Status — Local AI Workspace", "", "I checked the documented development and learning status. This is a read-only report and does not modify files. 🙂", "", "## Current learning status", ""]
    lines += [f"- {x}" for x in status["learning_findings"]]
    lines += ["", "## Key components", ""]
    lines += [f"- {emoji(i.status)} **{i.label}** — `{i.status}` — `{i.path}`" for i in comps]
    lines += ["", "## Next recommended development step", "", f"**{rec['title']}**", "", f"- **ID:** `{rec['id']}`", f"- **Reason:** {rec['reason']}", f"- **Risk level:** `{rec['risk_level']}`", f"- **Requires user approval:** {'yes' if rec['requires_jani_approval'] else 'no'}", "", "### Possible files"]
    lines += [f"- `{x}`" for x in rec.get("suggested_files", [])]
    lines += ["", "### Tests"]
    lines += [f"- `{x}`" for x in rec.get("test_commands", [])]
    lines += ["", "## Most recent learning-related memory entry", "", status["recent_memory"], "", "## Truth boundary", ""]
    lines += [f"- {x}" for x in status["truth_boundary"]]
    return "\n".join(lines).strip()


def build_next_goal_reply(project_root: Optional[Path] = None) -> str:
    status = build_goal_status(project_root)
    rec = status["recommendation"]
    lines = ["# Next Development Step — Local AI Workspace", "", f"Next recommendation: **{rec['title']}**", "", f"**Why:** {rec['reason']}", "", f"- ID: `{rec['id']}`", f"- Status: `{rec['status']}`", f"- Risk level: `{rec['risk_level']}`", f"- Requires user approval: {'yes' if rec['requires_jani_approval'] else 'no'}", "", "## Files"]
    lines += [f"- `{x}`" for x in rec.get("suggested_files", [])]
    lines += ["", "## Tests"]
    lines += [f"- `{x}`" for x in rec.get("test_commands", [])]
    lines += ["", "## Truth boundary", "", "This is a recommendation, not an implementation. No changes are made without user approval."]
    return "\n".join(lines).strip()


def is_goal_engine_request(message: str) -> bool:
    text = " ".join((message or "").lower().split())
    return any(t in text for t in ["oppimisen tila", "tila oppimisen suhteen", "mitä olet oppinut", "mitä opit", "mikä on seuraava kehitysaskel", "mitä rakennetaan seuraavaksi", "mitä seuraavaksi rakennetaan", "kehityksen tila", "roadmap tila", "tavoitetila", "goal engine"])


def route_goal_engine_request(project_root: Optional[Path], message: str) -> Dict[str, Any]:
    text = " ".join((message or "").lower().split())
    reply = build_next_goal_reply(project_root) if any(t in text for t in ["mikä on seuraava", "mitä rakennetaan seuraavaksi", "mitä seuraavaksi rakennetaan"]) else build_learning_status_reply(project_root)
    return {"handled": True, "tool": "goal_engine", "result": build_goal_status(project_root), "reply": reply}


if __name__ == "__main__":
    print(build_learning_status_reply())
