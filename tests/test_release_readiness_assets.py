from pathlib import Path

from app.live_evals import LIVE_EVAL_CASES
from app.main import load_config


ROOT = Path(__file__).resolve().parent.parent


def test_release_readiness_files_exist() -> None:
    required = [
        "README.md",
        "QUICKSTART.md",
        "SECURITY.md",
        "CONTRIBUTING.md",
        ".env.example",
        ".github/workflows/tests.yml",
        "scripts/release_readiness.py",
        "docs/DEVELOPER_SETUP.md",
        "docs/testing/README.md",
        "docs/limitations.md",
    ]

    for relative in required:
        assert (ROOT / relative).exists(), relative


def test_readme_is_utf8_and_links_core_workflows() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Local AI Workspace" in text
    assert "python -m pytest" in text
    assert "authentication" in text.lower()
    assert "Backup/restore workflow" in text
    assert "extensive eval suite" in text

    assert "docs/architecture.md" in text
    assert "docs/DEVELOPER_SETUP.md" in text
    assert "docs/testing/README.md" in text
    assert "SECURITY.md" in text
    assert "docs/limitations.md" in text

    assert "/evals/static" not in text
    assert "/backup/archive" not in text
    assert "create_sade_user.bat" not in text


def test_deep_workflow_details_are_documented_outside_readme() -> None:
    architecture = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    testing = (ROOT / "docs" / "testing" / "README.md").read_text(encoding="utf-8")
    developer_setup = (ROOT / "docs" / "DEVELOPER_SETUP.md").read_text(encoding="utf-8")
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")

    assert "AI Evals" in architecture
    assert "app/backup_restore.py" in architecture
    assert "10,000 question chains" in testing
    assert "reports/coverage.xml" in testing
    assert "create_sade_user.bat" in developer_setup
    assert "auth" in security.lower()


def test_env_overrides_config(monkeypatch) -> None:
    monkeypatch.setenv("SADE_OLLAMA_MODEL", "unit-test-model")
    monkeypatch.setenv("SADE_NUM_CTX", "4096")
    monkeypatch.setenv("SADE_UI_LANGUAGE", "en")

    config = load_config()

    assert config["ollama_model"] == "unit-test-model"
    assert config["num_ctx"] == 4096
    assert config["ui_language"] == "en"


def test_live_eval_cases_are_defined_without_running_model() -> None:
    assert len(LIVE_EVAL_CASES) >= 3
    assert all("prompt" in case for case in LIVE_EVAL_CASES)
    assert all("must_include_any" in case for case in LIVE_EVAL_CASES)
