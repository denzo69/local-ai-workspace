from pathlib import Path

from app.manual_behavior import try_handle_manual_behavior


def _handled(tmp_path: Path, message: str):
    result = try_handle_manual_behavior(tmp_path, message)
    assert result.get("handled") is True
    return result


def test_time_question_uses_deterministic_handler(tmp_path):
    result = _handled(tmp_path, "Paljon kello on")

    assert result["category"] == "date_time"
    assert "Kello on" in result["reply"]
    assert "Verkkohaku" not in result["reply"]
    assert "DuckDuckGo" not in result["reply"]


def test_date_question_uses_deterministic_handler(tmp_path):
    result = _handled(tmp_path, "Mikä päivä nyt on?")

    assert result["category"] == "date_time"
    assert "Tänään on" in result["reply"]
    assert "Verkkohaku" not in result["reply"]


def test_assistant_permission_question_routes_to_boundaries(tmp_path):
    result = _handled(tmp_path, "Onko sinulle annettu mitä oikeuksia?")

    assert result["category"] == "assistant_permissions"
    assert "auth.json" in result["reply"]
    assert "Oikeusministeriö" not in result["reply"]
    assert "perusoikeudet" not in result["reply"].lower()


def test_finnish_language_question_uses_language_template(tmp_path):
    result = _handled(tmp_path, "Entä suomenkielen taito sinulla?")

    assert result["category"] == "finnish_language_capability"
    assert "Suomi" in result["reply"]
    assert "Self-State" not in result["reply"]
    assert "Keskustelu 2026" not in result["reply"]
    assert "verokort" not in result["reply"].lower()


def test_general_winter_snow_question_does_not_use_web_search(tmp_path):
    result = _handled(tmp_path, "onko talvella lunta?")

    assert result["category"] == "general_knowledge"
    assert "Yleisesti" in result["reply"]
    assert "Verkkohaku" not in result["reply"]


def test_health_lifestyle_question_blocks_business_leakage(tmp_path):
    result = _handled(tmp_path, "Mikä on riittävä määrä unta yöllä?")

    assert result["category"] == "health_lifestyle_general"
    assert "7–9" in result["reply"] or "7-9" in result["reply"]
    assert "freelance" not in result["reply"].lower()
    assert "dta" not in result["reply"].lower()
    assert "verokort" not in result["reply"].lower()
    assert "kirjanpito" not in result["reply"].lower()


def test_coffee_question_blocks_business_leakage(tmp_path):
    result = _handled(tmp_path, "Onko kaksi kuppia kahvia liikaa aamulla?")

    assert result["category"] == "health_lifestyle_general"
    assert "kahvia" in result["reply"].lower() or "kofeiini" in result["reply"].lower()
    assert "freelance" not in result["reply"].lower()
    assert "dta" not in result["reply"].lower()
    assert "verokort" not in result["reply"].lower()
