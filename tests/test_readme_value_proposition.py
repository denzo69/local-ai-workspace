from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_readme_explains_workspace_value_without_overclaiming() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Local-first AI workspace" in readme
    assert "more than a chat box" in readme
    assert "## What it does" in readme
    assert "persistent assistant memory" in readme
    assert "document/source material" in readme
    assert "audit logs" in readme
    assert "backup/export workflows" in readme
    assert "portfolio-stage project" in readme
    assert "not production-ready" in readme
