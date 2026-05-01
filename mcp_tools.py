"""
Definición compartida de las tools MCP de MyVoices.

Las mismas tools se exponen por dos transportes:

  * **stdio** (`mcp_server.py`) — para clientes que lanzan el servidor como
    subprocess (Claude Desktop con la config legacy, Cline, etc.).
  * **HTTP/SSE** — montado dentro de la propia FastAPI app de MyVoices
    en `/mcp/`. Activable/desactivable desde la UI.

Ambos modos llaman a la misma API REST local (`MYVOICES_URL`) vía httpx,
así que toda la lógica de negocio sigue viviendo en `server.py`.
"""
from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

DEFAULT_BASE_URL = "http://localhost:8000"


def _base_url() -> str:
    return os.getenv("MYVOICES_URL", DEFAULT_BASE_URL).rstrip("/")


def _timeout() -> float:
    return float(os.getenv("MYVOICES_TIMEOUT", "60"))


async def _request(method: str, path: str, **kwargs):
    """Llamada HTTP async a la API de MyVoices con manejo uniforme de errores."""
    url = f"{_base_url()}{path}"
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        try:
            r = await client.request(method, url, **kwargs)
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"No se pudo conectar a MyVoices en {_base_url()}. "
                "¿Está la app abierta? "
                f"({exc})"
            ) from exc
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        raise RuntimeError(f"MyVoices {method} {path} → {r.status_code}: {detail}")
    if not r.content:
        return None
    try:
        return r.json()
    except Exception:
        return r.text


async def _head(path: str):
    url = f"{_base_url()}{path}"
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        return await client.head(url)


def register_all(mcp: FastMCP) -> FastMCP:
    """Registra las 7 tools de MyVoices en la instancia FastMCP indicada."""

    @mcp.tool()
    async def get_status() -> dict:
        """Devuelve el estado del servidor MyVoices: motor TTS cargado,
        dispositivo (CPU/GPU), número de voces y presets registrados."""
        return await _request("GET", "/api/status")

    @mcp.tool()
    async def list_voices() -> list:
        """Lista todas las voces TTS registradas (clonadas XTTS y voces
        Piper). Cada voz incluye id, name, engine y filename."""
        return await _request("GET", "/api/voices")

    @mcp.tool()
    async def list_presets() -> list:
        """Lista todos los presets de voz. Un preset combina una voz con
        parámetros (speed, pitch, language, radio_effect) y se identifica
        por nombre — ese nombre es lo que se pasa a `speak`."""
        return await _request("GET", "/api/voice-presets")

    @mcp.tool()
    async def list_phrases() -> list:
        """Lista todas las frases guardadas. Cada frase tiene un nombre,
        un texto y opcionalmente un preset asociado."""
        return await _request("GET", "/api/phrases")

    @mcp.tool()
    async def speak(voice: str, text: str) -> dict:
        """Sintetiza y reproduce `text` con el preset llamado `voice`.

        El audio sale por los altavoces del equipo donde corre la app de
        MyVoices. Para descargarlo en lugar de reproducirlo, usa
        `download_last_audio` después de esta llamada.

        Args:
            voice: nombre de un preset (ver `list_presets`)
            text:  texto a leer
        """
        return await _request("POST", "/api/speak", json={"voice": voice, "text": text})

    @mcp.tool()
    async def play_phrase(name: str) -> dict:
        """Reproduce una frase guardada por nombre (usa el preset asociado a
        la frase). Lanza error si la frase no existe o no tiene preset."""
        return await _request("POST", f"/api/phrases/{name}/play")

    @mcp.tool()
    async def download_last_audio() -> dict:
        """Devuelve metadatos del último WAV reproducido por `speak` (cacheado
        en el servidor). Útil para confirmar que hay audio disponible para
        descarga manual desde la UI."""
        r = await _head("/api/speak/last")
        if r.status_code == 404:
            return {"available": False,
                    "detail": "No hay audio reciente. Llama a `speak` primero."}
        if r.status_code >= 400:
            raise RuntimeError(f"MyVoices /api/speak/last → {r.status_code}")
        return {
            "available":    True,
            "url":          f"{_base_url()}/api/speak/last",
            "size_bytes":   int(r.headers.get("content-length", 0)),
            "content_type": r.headers.get("content-type", "audio/wav"),
        }

    return mcp


def build_mcp_server(name: str = "MyVoices", **kwargs) -> FastMCP:
    """Crea un FastMCP listo para usar (con todas las tools registradas)."""
    mcp = FastMCP(name, **kwargs)
    register_all(mcp)
    return mcp
