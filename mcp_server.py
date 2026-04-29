"""
MyVoices MCP server — expone la API REST de MyVoices como herramientas MCP
para que un modelo (Claude Desktop, etc.) pueda hablar con voces clonadas,
listar presets/frases y disparar audio en la app de escritorio que esté
ejecutándose localmente.

Uso típico (Claude Desktop, claude_desktop_config.json):

    {
      "mcpServers": {
        "myvoices": {
          "command": "python",
          "args": ["C:/ruta/a/MyVoices/mcp_server.py"],
          "env": { "MYVOICES_URL": "http://localhost:8000" }
        }
      }
    }

Requisitos:
    pip install -r requirements-mcp.txt

La app de MyVoices debe estar corriendo (la ventana de escritorio o
`python main.py`) en `MYVOICES_URL` antes de que el modelo invoque las
herramientas, ya que este servidor solo redirige peticiones HTTP.
"""
import os

import httpx
from mcp.server.fastmcp import FastMCP

BASE_URL = os.getenv("MYVOICES_URL", "http://localhost:8000").rstrip("/")
TIMEOUT  = float(os.getenv("MYVOICES_TIMEOUT", "60"))

mcp = FastMCP("MyVoices")


def _request(method: str, path: str, **kwargs):
    """Llamada HTTP al servidor MyVoices con manejo uniforme de errores."""
    url = f"{BASE_URL}{path}"
    with httpx.Client(timeout=TIMEOUT) as client:
        try:
            r = client.request(method, url, **kwargs)
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"No se pudo conectar a MyVoices en {BASE_URL}. "
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


# ── Lectura ───────────────────────────────────────────────────────────────────

@mcp.tool()
def get_status() -> dict:
    """Devuelve el estado del servidor MyVoices: motor TTS cargado, dispositivo
    (CPU/GPU), número de voces y presets registrados."""
    return _request("GET", "/api/status")


@mcp.tool()
def list_voices() -> list:
    """Lista todas las voces TTS registradas (clonadas XTTS y voces Piper).
    Cada voz incluye id, name, engine y filename."""
    return _request("GET", "/api/voices")


@mcp.tool()
def list_presets() -> list:
    """Lista todos los presets de voz. Un preset combina una voz con
    parámetros (speed, pitch, language, radio_effect) y se identifica
    por nombre — ese nombre es lo que se pasa a `speak`."""
    return _request("GET", "/api/voice-presets")


@mcp.tool()
def list_phrases() -> list:
    """Lista todas las frases guardadas. Cada frase tiene un nombre,
    un texto y opcionalmente un preset asociado."""
    return _request("GET", "/api/phrases")


# ── Acciones ──────────────────────────────────────────────────────────────────

@mcp.tool()
def speak(voice: str, text: str) -> dict:
    """Sintetiza y reproduce `text` con el preset llamado `voice`.

    El audio sale por los altavoces del equipo donde corre la app de
    MyVoices. Para descargarlo en lugar de reproducirlo, usa
    `download_last_audio` después de esta llamada.

    Args:
        voice: nombre de un preset (ver `list_presets`)
        text:  texto a leer
    """
    return _request("POST", "/api/speak", json={"voice": voice, "text": text})


@mcp.tool()
def play_phrase(name: str) -> dict:
    """Reproduce una frase guardada por nombre (usa el preset asociado a la
    frase). Lanza error si la frase no existe o no tiene preset."""
    return _request("POST", f"/api/phrases/{name}/play")


@mcp.tool()
def download_last_audio() -> dict:
    """Devuelve metadatos del último WAV reproducido por `speak` (cacheado
    en el servidor). Útil para confirmar que hay audio disponible para
    descarga manual desde la UI."""
    url = f"{BASE_URL}/api/speak/last"
    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.head(url)
    if r.status_code == 404:
        return {"available": False, "detail": "No hay audio reciente. Llama a `speak` primero."}
    if r.status_code >= 400:
        raise RuntimeError(f"MyVoices /api/speak/last → {r.status_code}")
    return {
        "available":   True,
        "url":         url,
        "size_bytes":  int(r.headers.get("content-length", 0)),
        "content_type": r.headers.get("content-type", "audio/wav"),
    }


if __name__ == "__main__":
    mcp.run()
