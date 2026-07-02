from pathlib import Path

from app.manual_behavior import try_handle_manual_behavior


def _handled(tmp_path: Path, message: str):
    result = try_handle_manual_behavior(tmp_path, message)
    assert result.get("handled") is True
    return result


def _patch_web_search(monkeypatch):
    from app import web_search as web_search_module

    calls = {}

    def fake_web_search(project_path, query, max_results=6):
        calls["project_path"] = project_path
        calls["query"] = query
        calls["max_results"] = max_results
        return {
            "ok": True,
            "query": query,
            "provider": "fake",
            "results": [
                {
                    "rank": 1,
                    "title": "Fake local result",
                    "url": "https://example.com/local",
                    "source": "example.com",
                    "snippet": "Fake local snippet",
                }
            ],
        }

    def fake_format_web_search_reply(result):
        return f"# Verkkohaku\n\nHakukysely: `{result.get('query')}`\nProvider: `{result.get('provider')}`"

    monkeypatch.setattr(web_search_module, "web_search", fake_web_search)
    monkeypatch.setattr(web_search_module, "format_web_search_reply", fake_format_web_search_reply)
    return calls


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


def test_population_question_routes_to_web_search(tmp_path, monkeypatch):
    calls = _patch_web_search(monkeypatch)

    result = _handled(tmp_path, "mikä on lieksan asukasluku")

    assert result["category"] == "local_external_information"
    assert "Verkkohaku" in result["reply"]
    assert "lieksan asukasluku" in calls["query"].lower()
    assert "tilastokeskus" in calls["query"].lower()


def test_local_tire_purchase_question_routes_to_web_search(tmp_path, monkeypatch):
    calls = _patch_web_search(monkeypatch)

    result = _handled(tmp_path, "mistä voin ostaa autooni renkaat lieksassa")

    assert result["category"] == "local_external_information"
    assert "Verkkohaku" in result["reply"]
    assert "renkaat" in calls["query"].lower()
    assert "lieksa" in calls["query"].lower()
    assert "rengasliike" in calls["query"].lower()


def test_date_time_still_does_not_route_to_local_web_search(tmp_path, monkeypatch):
    calls = _patch_web_search(monkeypatch)

    result = _handled(tmp_path, "Paljon kello on")

    assert result["category"] == "date_time"
    assert calls == {}
    assert "Verkkohaku" not in result["reply"]
