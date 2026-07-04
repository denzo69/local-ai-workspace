from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent.parent


def test_portfolio_files_exist() -> None:
    required = [
        "LICENSE",
        "CHANGELOG.md",
        "VERSION",
        ".coveragerc",
        "docs/code_rewrite_protocol.md",
        "docs/architecture.md",
        "docs/repo_cleanup_plan.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/pull_request_template.md",
        ".github/CODEOWNERS",
    ]
    for relative in required:
        assert (ROOT / relative).exists(), relative


def test_readme_has_portfolio_sections() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "What this project demonstrates" in readme
    assert "Architecture" in readme
    assert "Suggested demo flow" in readme
    assert re.search(r"\d+ tests passing locally", readme)
    assert re.search(r"\d+% total test coverage", readme)
    assert "Known limitations" in readme
    assert "MIT License" in readme


def test_code_rewrite_protocol_enforces_truth_boundary() -> None:
    protocol = (ROOT / "docs" / "code_rewrite_protocol.md").read_text(encoding="utf-8")
    assert "Do not claim a change is complete" in protocol
    assert "tests" in protocol.lower()
    assert "rollback" in protocol.lower()
    assert "audit" in protocol.lower()
