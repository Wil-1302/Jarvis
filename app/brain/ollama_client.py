"""Cliente mínimo de la API HTTP de Ollama."""

from __future__ import annotations

from typing import Any

import httpx


class OllamaError(Exception):
    """Ollama no está disponible o devolvió un error."""


class OllamaClient:
    def __init__(
        self,
        host: str,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(base_url=host, timeout=timeout, transport=transport)

    def __enter__(self) -> OllamaClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise OllamaError(
                f"{method} {path} -> HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise OllamaError(f"No se pudo conectar con Ollama ({exc.__class__.__name__})") from exc

    def version(self) -> str:
        return self._request("GET", "/api/version")["version"]

    def list_models(self) -> list[str]:
        return [model["name"] for model in self._request("GET", "/api/tags").get("models", [])]

    def has_model(self, name: str) -> bool:
        wanted = name if ":" in name else f"{name}:latest"
        return wanted in self.list_models()

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        json_format: bool = False,
        temperature: float = 0.0,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_format:
            payload["format"] = "json"
        return self._request("POST", "/api/chat", json=payload)["message"]["content"]
