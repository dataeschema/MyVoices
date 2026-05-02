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

    # ── Tools de diagnóstico (para LLMs que ayudan a depurar) ────────────────

    @mcp.tool()
    async def get_logs(limit: int = 50, level: str = "",
                       caller: str = "", contains: str = "") -> list:
        """Devuelve los últimos `limit` logs de la app, opcionalmente filtrados
        por nivel (INFO/WARNING/ERROR/DEBUG), origen (UI/API/MCP) y subcadena.
        Útil para que un LLM pueda diagnosticar errores sin pedir al usuario
        que copie y pegue logs.

        Args:
            limit:    máximo de logs a devolver (default 50, max 500)
            level:    filtra por nivel exacto, vacío = todos
            caller:   filtra por origen, vacío = todos
            contains: solo logs cuyo mensaje contenga esta cadena (case-insensitive)
        """
        params = {"limit": str(min(max(limit, 1), 500))}
        if level:  params["level"]  = level
        if caller: params["caller"] = caller
        rows = await _request("GET", "/api/logs", params=params) or []
        if contains:
            needle = contains.lower()
            rows = [r for r in rows if needle in (r.get("message") or "").lower()]
        return rows

    @mcp.tool()
    async def get_diagnostics() -> dict:
        """Estado completo de la app: motor TTS cargado, errores de import de
        cada motor (con traceback), versiones de paquetes Python clave (torch,
        transformers, TTS, f5-tts, chatterbox), y modo verbose. Llamar antes
        de intentar cargar un motor para saber por qué puede estar fallando."""
        return await _request("GET", "/api/diagnostics")

    @mcp.tool()
    async def load_model(engine: str) -> dict:
        """Intenta cargar el modelo TTS del motor indicado y devuelve el
        resultado. Si falla, el campo `status` contiene el mensaje de error;
        para el traceback completo, llamar después a `get_logs(level='ERROR')`.

        Args:
            engine: 'xtts', 'f5tts' o 'chatterbox'
        """
        return await _request("POST", f"/api/models/load/{engine}")

    @mcp.tool()
    async def set_verbose(enabled: bool) -> dict:
        """Activa/desactiva el modo verbose (logs DEBUG + tracebacks completos).
        Útil para reproducir un error con más contexto. La configuración
        persiste en la DB hasta que se vuelva a llamar a esta tool."""
        return await _request("POST", f"/api/verbose/{'true' if enabled else 'false'}")

    return mcp


def build_mcp_server(name: str = "MyVoices", **kwargs) -> FastMCP:
    """Crea un FastMCP listo para usar (con todas las tools registradas)."""
    mcp = FastMCP(name, **kwargs)
    register_all(mcp)
    return mcp
