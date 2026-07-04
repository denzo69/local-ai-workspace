from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

TEXT_EXTENSIONS = {
    ".py", ".md", ".txt", ".json", ".yml", ".yaml", ".toml",
    ".ini", ".html", ".css", ".js", ".ps1", ".bat"
}

SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "htmlcov",
    "memory",
    "uploads",
}


DANGER_PATTERNS = {
    "merge_conflict_start": "<<<<<<<",
    "merge_conflict_middle": "=======",
    "merge_conflict_end": ">>>>>>>",
    "raw_validator_block": "The answer was blocked because it did not match the planned response path",
    "business_leak_dta": "DTA-sopimus",
    "business_leak_tax_card": "verokortti",
}


REQUIRED_FILES = [
    "README.md",
    "CHANGELOG.md",
    "VERSION",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "QUICKSTART.md",
    "LICENSE",
    "app/main.py",
    "app/chat_pipeline.py",
    "app/manual_behavior.py",
    "app/web_search.py",
    "app/tool_router.py",
    "app/config.json",
    "tests",
]


def run_git_ls_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        print("ERROR: git ls-files failed")
        print(result.stderr)
        sys.exit(1)

    return [ROOT / line.strip() for line in result.stdout.splitlines() if line.strip()]


def is_skipped(path: Path) -> bool:
    parts = set(path.relative_to(ROOT).parts)
    return bool(parts & SKIP_DIRS)


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
    except Exception as error:
        return f"__READ_ERROR__: {error}"


def check_required_files(errors: list[str]) -> None:
    for item in REQUIRED_FILES:
        path = ROOT / item
        if not path.exists():
            errors.append(f"Missing required file/path: {item}")


def check_python_file(path: Path, errors: list[str]) -> None:
    relative = path.relative_to(ROOT)

    try:
        source = path.read_text(encoding="utf-8")
    except Exception as error:
        errors.append(f"{relative}: cannot read Python file: {error}")
        return

    try:
        ast.parse(source, filename=str(relative))
    except SyntaxError as error:
        errors.append(f"{relative}: SyntaxError line {error.lineno}: {error.msg}")

    if "\t" in source:
        errors.append(f"{relative}: contains tab characters")

    if path.name == "main.py":
        required_main_markers = [
            "handle_chat_message",
            "ChatPipelineDependencies",
            "build_sade_prompt",
            "ask_ollama",
        ]

        for marker in required_main_markers:
            if marker not in source:
                errors.append(f"{relative}: missing expected chat endpoint dependency marker: {marker}")

    if path.name == "chat_pipeline.py":
        required_chat_pipeline_markers = [
            "try_handle_manual_behavior",
            "build_direct_response",
            "extract_memory_command",
            "handle_learning_review_chat_command",
            "handle_learning_chat_command",
            "handle_task_chat_command",
            "handle_rag_chat_command",
            "route_tool_request",
            "is_current_info_request",
            "is_automatic_web_search_request",
            "build_sade_prompt",
            "ask_ollama",
        ]

        for marker in required_chat_pipeline_markers:
            if marker not in source:
                errors.append(f"{relative}: missing expected chat pipeline marker: {marker}")

    if path.name == "manual_behavior.py":
        required_manual_markers = [
            "date_time",
            "assistant_permissions",
            "finnish_language_capability",
            "health_lifestyle_general",
            "local_external_information",
        ]

        for marker in required_manual_markers:
            if marker not in source:
                errors.append(f"{relative}: missing expected manual behavior marker: {marker}")


def check_json_file(path: Path, errors: list[str]) -> None:
    relative = path.relative_to(ROOT)

    try:
        json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        errors.append(f"{relative}: invalid JSON: {error}")


def check_text_patterns(path: Path, warnings: list[str], errors: list[str]) -> None:
    relative = path.relative_to(ROOT)
    text = read_text(path)

    if text is None:
        return

    if text.startswith("__READ_ERROR__"):
        errors.append(f"{relative}: {text}")
        return

    for name, pattern in DANGER_PATTERNS.items():
        if name.startswith("merge_conflict"):
            if re.search(rf"(?m)^{re.escape(pattern)}(?:\s|$)", text):
                errors.append(f"{relative}: contains merge conflict marker: {pattern}")
            continue

        if relative == Path("scripts/repo_integrity_audit.py"):
            continue

        if pattern in text:
            warnings.append(f"{relative}: contains suspicious pattern `{pattern}`")

    if path.suffix == ".py" and len(text) > 120_000:
        warnings.append(f"{relative}: Python file is very large ({len(text)} chars)")


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    files = run_git_ls_files()
    checked_files = 0
    python_files = 0
    json_files = 0

    check_required_files(errors)

    for path in files:
        if is_skipped(path):
            continue

        if not path.exists():
            errors.append(f"{path.relative_to(ROOT)}: tracked file missing from working tree")
            continue

        checked_files += 1

        if path.suffix == ".py":
            python_files += 1
            check_python_file(path, errors)

        if path.suffix == ".json":
            json_files += 1
            check_json_file(path, errors)

        if path.suffix in TEXT_EXTENSIONS:
            check_text_patterns(path, warnings, errors)

    print("# Repo integrity audit")
    print()
    print(f"Root: {ROOT}")
    print(f"Checked files: {checked_files}")
    print(f"Python files: {python_files}")
    print(f"JSON files: {json_files}")
    print(f"Warnings: {len(warnings)}")
    print(f"Errors: {len(errors)}")
    print()

    if warnings:
        print("## Warnings")
        for warning in warnings:
            print(f"- {warning}")
        print()

    if errors:
        print("## Errors")
        for error in errors:
            print(f"- {error}")
        print()
        return 1

    print("OK: no integrity errors found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
