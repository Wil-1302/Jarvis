"""Vocabulario del señor para Whisper (D-025). Privado: ~/.config/jarvis/vocabulario.txt (600), nunca en el repo.

Secciones: "# propios" (a mano; se conserva siempre), "# artistas" y "# aplicaciones" (automáticas, locales).
Whisper recibe un `initial_prompt` con el vocabulario (lo más reciente/usado primero, ~200 tokens como máximo).
"""
from __future__ import annotations

import collections
import json
import os
import re
import sys
from pathlib import Path

ARCHIVO = Path(os.environ.get("JARVIS_VOCABULARIO", Path.home() / ".config" / "jarvis" / "vocabulario.txt"))
LETRAS = Path.home() / ".local/state/caelestia/lyrics/lyrics_map.json"
BASE = "Jarvis, Spotify, YouTube, Chrome, LibreOffice, Writer, Calc, Steam, Hyprland, Arch Linux."
_APPS_IGNORAR = re.compile(r"^(avahi|bvnc|bssh|qv4l2|qvidcap|uxterm|xterm|lstopo|nvidia|electron|java|jconsole|"
                           r"jshell|htop|btop|vim|nvim|cmake|assistant|designer|linguist|qdbus|kvantum)", re.I)


def _secciones() -> dict[str, list[str]]:
    out: dict[str, list[str]] = collections.OrderedDict(propios=[], artistas=[], aplicaciones=[])
    if ARCHIVO.exists():
        actual = None
        for linea in ARCHIVO.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea.startswith("#"):
                actual = linea.lstrip("# ").lower()
                out.setdefault(actual, [])
            elif linea and actual:
                out[actual].append(linea)
    return out


def _artistas() -> list[str]:
    try:
        d = json.loads(LETRAS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    c = collections.Counter()
    for k in d:
        a = k.split(" - ")[0]
        for x in re.split(r",|&| feat\.? | ft\.? | x ", a):
            x = re.sub(r"[=*()\[\]]", " ", x).strip()
            if 2 <= len(x) <= 40:
                c[x] += 1
    return [a for a, _ in c.most_common(120)]


def _aplicaciones() -> list[str]:
    nombres = set()
    for d in (Path("/usr/share/applications"), Path.home() / ".local/share/applications"):
        for f in d.glob("*.desktop"):
            try:
                t = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if re.search(r"^NoDisplay=true", t, re.M):
                continue
            m = re.search(r"^Name=(.+)$", t, re.M)
            if m and not _APPS_IGNORAR.match(m.group(1)) and len(m.group(1)) <= 30:
                nombres.add(m.group(1).strip())
    return sorted(nombres)


def regenerar() -> dict[str, list[str]]:
    s = _secciones()
    s["artistas"], s["aplicaciones"] = _artistas(), _aplicaciones()
    ARCHIVO.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    texto = "".join(f"# {k}\n" + "".join(f"{x}\n" for x in v) + "\n" for k, v in s.items())
    tmp = ARCHIVO.with_suffix(".tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(ARCHIVO)
    return s


_cache: tuple[float, str] | None = None


def prompt(max_caracteres: int = 700) -> str:
    """Prompt inicial de Whisper: base + propios + artistas + aplicaciones, hasta ~200 tokens."""
    global _cache
    try:
        mt = ARCHIVO.stat().st_mtime
    except OSError:
        return BASE
    if _cache and _cache[0] == mt:
        return _cache[1]
    s = _secciones()
    palabras: list[str] = []
    for k in ("propios", "artistas", "aplicaciones"):
        palabras += [w for w in s.get(k, []) if w not in palabras]
    texto = BASE
    for w in palabras:
        if len(texto) + len(w) + 2 > max_caracteres:
            break
        texto += " " + w + ","
    texto = texto.rstrip(",") + "."
    _cache = (mt, texto)
    return texto


if __name__ == "__main__":
    if sys.argv[1:2] == ["ver"]:
        for k, v in _secciones().items():
            print(f"{k}: {len(v)}")
        print(f"prompt: {len(prompt())} caracteres")
    else:
        s = regenerar()
        print(f"{ARCHIVO}: " + ", ".join(f"{k} {len(v)}" for k, v in s.items()))
