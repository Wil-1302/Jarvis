"""Puente face → OpenClaw (cerebro). Ver CLAUDE.md y docs/DECISIONES.md (D-004 opción A, D-008).

face no decide nada: manda el texto del usuario al agente `jarvis` del Gateway de OpenClaw por su
endpoint compatible con OpenAI. El historial vive en OpenClaw (un `user` estable = misma sesión),
así que aquí solo se envía el mensaje nuevo.

Failover en dos niveles:
1. OpenClaw: `agents.defaults.model.fallbacks` (Claude → GPT) salta solo con límites, auth o timeouts.
2. face: si la petición aun así falla, reintenta UNA vez forzando el cerebro de respaldo con
   `x-openclaw-model` y avisa por voz ("Cambio al cerebro de respaldo").
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

_REPO_ENV = Path(__file__).resolve().parents[2] / ".env"   # antiguo (solo compatibilidad)
# Refuerzo a: secretos de face fuera del repo y fuera del alcance del gateway (InaccessiblePaths).
SECRETS = Path(os.environ.get("JARVIS_SECRETS", Path.home() / ".config" / "jarvis" / "secrets.env"))
AVISO_RESPALDO = "Cambio al cerebro de respaldo."
# Va como mensaje `system` en cada petición: OpenClaw lo añade a las instrucciones del agente en ese turno
# (extraSystemPrompt), así vale igual para Claude y para GPT, que tiende a contestar en listas.
ESTILO_VOZ = ("Tu respuesta se leerá en voz alta. Responde en prosa hablada, con frases corridas: nada de listas, "
              "viñetas, numeraciones, encabezados, tablas, negritas ni ningún otro Markdown, y sin emojis ni URLs. "
              "Si hay varios elementos, enlázalos en una o dos frases (por ejemplo: «primero…, después… y por "
              "último…»). Lo normal: de una a tres frases.")

# Errores que justifican cambiar de cerebro (límites, cuotas, auth del proveedor, caídas).
_PATRON_FALLO_MODELO = re.compile(
    r"all models failed|usage|limit|quota|credits|rate|overload|capacity|unavailable|timed? ?out|"
    r"authentication|no route-compatible",
    re.I,
)


class BrainError(RuntimeError):
    """El cerebro no respondió (ni el principal ni el de respaldo)."""


def _leer_env(nombre: str) -> str:
    """Variable de entorno, o de ~/.config/jarvis/secrets.env (600), o del .env antiguo. Nunca se imprime."""
    valor = os.environ.get(nombre, "")
    if valor:
        return valor
    for f in (SECRETS, _REPO_ENV):
        try:
            for linea in f.read_text(encoding="utf-8").splitlines():
                if linea.startswith(f"{nombre}="):
                    return linea.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            pass
    return ""


@dataclass
class Brain:
    base_url: str = "http://127.0.0.1:18789/v1"
    agent: str = "openclaw/jarvis"
    user: str = "face:jarvis"
    timeout: float = 180.0
    model_override: str | None = None        # cerebro elegido por voz (x-openclaw-model); None = el de OpenClaw
    backup_model: str = "openai/gpt-5.6-terra"
    on_backup: Callable[[str], None] | None = None   # se llama con AVISO_RESPALDO antes de reintentar
    estilo: str = ESTILO_VOZ                  # instrucción de estilo hablado ("" = no enviar)

    @classmethod
    def from_config(cls, cfg: dict, on_backup: Callable[[str], None] | None = None) -> "Brain":
        oc = (cfg.get("llm") or {}).get("openclaw") or {}
        return cls(
            base_url=oc.get("base_url", cls.base_url),
            agent=oc.get("agent", cls.agent),
            user=oc.get("user", cls.user),
            timeout=float(oc.get("timeout", cls.timeout)),
            # Sin cerebro elegido por voz se pide el principal EXPLÍCITO (selección estricta): así el salto
            # al respaldo lo hace face y lo anuncia por voz (el fallback nativo de OpenClaw es silencioso
            # para el endpoint HTTP: no indica qué modelo respondió). D-014.
            model_override=oc.get("model") or oc.get("primary_model") or None,
            backup_model=oc.get("backup_model", cls.backup_model),
            on_backup=on_backup,
            estilo=oc.get("estilo", ESTILO_VOZ) or "",
        )

    def _mensajes(self, text: str) -> list[dict]:
        m = [{"role": "user", "content": text}]
        return [{"role": "system", "content": self.estilo}, *m] if self.estilo else m

    def _post(self, text: str, model: str | None) -> str:
        token = _leer_env("OPENCLAW_GATEWAY_TOKEN")
        if not token:
            raise BrainError("Falta OPENCLAW_GATEWAY_TOKEN en ~/.config/jarvis/secrets.env (scripts/sync-brain.sh).")
        headers = {"Authorization": f"Bearer {token}"}
        if model:
            headers["x-openclaw-model"] = model
        body = {"model": self.agent, "user": self.user,
                "messages": self._mensajes(text)}
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", json=body, headers=headers,
                           timeout=httpx.Timeout(self.timeout, connect=5.0))
        except httpx.ConnectError as e:
            raise ConnectionError("El gateway de OpenClaw no responde en 127.0.0.1:18789.") from e
        except httpx.TimeoutException as e:
            raise TimeoutError(f"El cerebro tardó más de {self.timeout:.0f} s.") from e
        try:
            data = r.json()
        except ValueError:
            data = {}
        if r.status_code >= 400 or data.get("error"):
            err = data.get("error") or {}
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise BrainError(f"HTTP {r.status_code}: {msg or r.text[:300]}")
        content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        return content or "Hecho."

    def _stream(self, text: str, model: str | None, on_delta: Callable[[str], None]) -> str:
        """Igual que _post pero con stream=true (SSE): llama on_delta con cada fragmento de texto."""
        import json as _json
        token = _leer_env("OPENCLAW_GATEWAY_TOKEN")
        if not token:
            raise BrainError("Falta OPENCLAW_GATEWAY_TOKEN en ~/.config/jarvis/secrets.env (scripts/sync-brain.sh).")
        headers = {"Authorization": f"Bearer {token}"}
        if model:
            headers["x-openclaw-model"] = model
        body = {"model": self.agent, "user": self.user, "stream": True,
                "messages": self._mensajes(text)}
        full = ""
        try:
            with httpx.stream("POST", f"{self.base_url}/chat/completions", json=body, headers=headers,
                              timeout=httpx.Timeout(self.timeout, connect=5.0)) as r:
                if r.status_code >= 400:
                    raw = r.read().decode(errors="ignore")
                    try:
                        err = _json.loads(raw).get("error") or {}
                        msg = err.get("message") if isinstance(err, dict) else str(err)
                    except ValueError:
                        msg = raw[:300]
                    raise BrainError(f"HTTP {r.status_code}: {msg}")
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        d = _json.loads(payload)
                    except ValueError:
                        continue
                    if d.get("error"):
                        err = d["error"]
                        raise BrainError(f"stream: {err.get('message') if isinstance(err, dict) else err}")
                    delta = (((d.get("choices") or [{}])[0].get("delta") or {}).get("content")) or ""
                    if delta:
                        full += delta
                        on_delta(delta)
        except httpx.ConnectError as e:
            raise ConnectionError("El gateway de OpenClaw no responde en 127.0.0.1:18789.") from e
        except httpx.TimeoutException as e:
            raise TimeoutError(f"El cerebro tardó más de {self.timeout:.0f} s.") from e
        if not full.strip():
            full = "Hecho."
            on_delta(full)
        return full

    def ask_stream(self, text: str, on_delta: Callable[[str], None]) -> tuple[str, bool]:
        """Como ask(), en streaming. Solo cambia al respaldo si el principal falla ANTES del primer
        fragmento (si ya empezó, el turno pudo ejecutar acciones y repetirlo las duplicaría)."""
        started = [False]

        def _d(x: str) -> None:
            started[0] = True
            on_delta(x)
        try:
            try:
                return self._stream(text, self.model_override, _d), False
            except BrainError as e:
                # Gateway reiniciándose (runtime aún en preparación / drenando): un reintento, mismo modelo.
                if started[0] or not re.search(r"HTTP 50[03]", str(e)):
                    raise
                import time as _t
                _t.sleep(2.0)
                return self._stream(text, self.model_override, _d), False
        except (ConnectionError, TimeoutError):
            raise
        except BrainError as e:
            if started[0] or self.model_override == self.backup_model or not _PATRON_FALLO_MODELO.search(str(e)):
                raise BrainError(str(e)) from e
            print(f"[Brain] Fallo del cerebro principal ({e}); reintento con {self.backup_model}")
            if self.on_backup:
                self.on_backup(AVISO_RESPALDO)
            try:
                return self._stream(text, self.backup_model, on_delta), True
            except Exception as e2:
                raise BrainError(f"Principal: {e} | Respaldo: {e2}") from e2

    def ask(self, text: str) -> tuple[str, bool]:
        """Devuelve (respuesta, usó_respaldo_forzado)."""
        try:
            return self._post(text, self.model_override), False
        except (ConnectionError, TimeoutError):
            # Gateway caído: cambiar de modelo no sirve. Timeout: el turno pudo ejecutar acciones
            # (p. ej. crear un documento) y repetirlo con otro modelo las duplicaría.
            raise
        except BrainError as e:
            if self.model_override == self.backup_model or not _PATRON_FALLO_MODELO.search(str(e)):
                raise BrainError(str(e)) from e
            print(f"[Brain] Fallo del cerebro principal ({e}); reintento con {self.backup_model}")
            if self.on_backup:
                self.on_backup(AVISO_RESPALDO)
            try:
                return self._post(text, self.backup_model), True
            except Exception as e2:
                raise BrainError(f"Principal: {e} | Respaldo: {e2}") from e2
