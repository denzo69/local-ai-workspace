from __future__ import annotations

"""Mallikutsujen provider-kerros.

Nykyinen oletus on Ollama, mutta muu sovellus kutsuu tätä kerrosta eikä ole
sidottu suoraan yhteen backend-toteutukseen.
"""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict


class ModelProviderError(RuntimeError):
    pass


@dataclass
class ModelResponse:
    text: str
    provider: str
    model: str
    raw: Dict[str, Any]


class OllamaProvider:
    name = "ollama"

    def __init__(self, *, url: str, model: str, temperature: float = 0.7, num_ctx: int = 8192):
        self.url = url
        self.model = model
        self.temperature = float(temperature)
        self.num_ctx = int(num_ctx)

    def generate(self, prompt: str, *, timeout: int = 180) -> ModelResponse:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_ctx": self.num_ctx,
            },
        }
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ModelProviderError(f"Ollamaan ei saada yhteyttä. Tarkista että Ollama on käynnissä. Virhe: {exc}") from exc
        except Exception as exc:
            raise ModelProviderError(f"Mallikutsu epäonnistui: {exc}") from exc
        return ModelResponse(text=str(raw.get("response", "")).strip(), provider=self.name, model=self.model, raw=raw)


def provider_from_config(config: Dict[str, Any]):
    provider = str(config.get("model_provider", "ollama")).lower()
    if provider != "ollama":
        raise ModelProviderError(f"Tuntematon model_provider: {provider}")
    return OllamaProvider(
        url=config.get("ollama_url", "http://127.0.0.1:11434/api/generate"),
        model=config.get("ollama_model", "llama3:latest"),
        temperature=float(config.get("temperature", 0.7)),
        num_ctx=int(config.get("num_ctx", 8192)),
    )


def model_provider_status(config: Dict[str, Any]) -> Dict[str, Any]:
    provider = str(config.get("model_provider", "ollama")).lower()
    return {
        "ok": provider == "ollama",
        "provider": provider,
        "model": config.get("ollama_model", "llama3:latest"),
        "url": config.get("ollama_url", "http://127.0.0.1:11434/api/generate") if provider == "ollama" else None,
        "supports_streaming": False,
    }
