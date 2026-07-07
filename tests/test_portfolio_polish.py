import re
from pathlib import Path


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
        "docs/DEVELOPER_SETUP.md",
        "docs/testing/README.md",
        "docs/limitations.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/pull_request_template.md",
        ".github/CODEOWNERS",
    ]
    for relative in required:
        assert (ROOT / relative).exists(), relative


def test_readme_is_concise_portfolio_front_page() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    lower = readme.lower()

    assert "local-first ai" in lower
    assert "fastapi" in lower
    assert "ollama" in lower
    assert "rag" in lower
    assert "portfolio-stage" in lower
    assert "What it does" in readme
    assert "Highlights" in readme
    assert "Quickstart" in readme
    assert "Architecture" in readme
    assert "Screenshots" in readme
    assert "Testing" in readme
    assert "Security" in readme
    assert "Limitations" in readme
    assert "MIT License" in readme

    assert "docs/architecture.md" in readme
    assert "docs/DEVELOPER_SETUP.md" in readme
    assert "docs/testing/README.md" in readme
    assert "SECURITY.md" in readme
    assert "docs/limitations.md" in readme

    assert re.search(r"93(?:\.\d+)?% coverage, \d+ tests", readme)
    assert "python -m pytest" in readme
    assert "reports/coverage.xml" not in readme
    assert "10,000 question chains" not in readme
    assert "40,000 routing checks" not in readme
    assert "create_sade_user.bat" not in readme
    assert "restart_local_ai_workspace.bat" not in readme


def test_code_rewrite_protocol_enforces_truth_boundary() -> None:
    protocol = (ROOT / "docs" / "code_rewrite_protocol.md").read_text(encoding="utf-8")
    assert "Do not claim a change is complete" in protocol
    assert "tests" in protocol.lower()
    assert "rollback" in protocol.lower()
    assert "audit" in protocol.lower()
