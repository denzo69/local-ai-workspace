from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_readme_positioning_notes_exist_and_keep_scope_realistic() -> None:
    notes = (ROOT / "docs" / "readme_positioning_notes.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "local-first AI workspace" in notes
    assert "not only as a chatbot" in notes
    assert "portfolio-stage project" in notes
    assert "not production-ready" in notes
    assert "README Positioning Notes" in readme
