"""
Tests del módulo `mcp_tools` (compartido entre stdio y HTTP).

Verifican:
  - las 7 herramientas están registradas con sus nombres
  - cada una llama al endpoint correcto de la API REST
  - errores HTTP y de conexión se traducen a mensajes claros
  - la URL base respeta las variables de entorno

Mockeamos `httpx.AsyncClient` con un MockTransport para no necesitar el servidor.
"""
import asyncio
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture()
def tools_module(monkeypatch):
    """Reimporta mcp_tools con BASE_URL fijo."""
    monkeypatch.setenv("MYVOICES_URL", "http://test.local")
    sys.modules.pop("mcp_tools", None)
    sys.modules.pop("mcp_server", None)
    import mcp_tools
    return mcp_tools


@pytest.fixture()
def mcp(tools_module):
    """FastMCP con todas las tools registradas."""
    return tools_module.build_mcp_server()


def _patch_transport(monkeypatch, tools_module, handler):
    """Sustituye httpx.AsyncClient en mcp_tools por uno con MockTransport."""
    original_async_client = httpx.AsyncClient

    def fake_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(tools_module.httpx, "AsyncClient", fake_async_client)


def _ok(payload):
    return httpx.Response(200, json=payload)


def _tool(mcp, name):
    """Devuelve la función Python registrada como tool MCP `name`."""
    fn = mcp._tool_manager._tools[name].fn
    # Las tools son async; envolver para que los tests síncronos puedan llamarlas
    import inspect
    if inspect.iscoroutinefunction(fn):
        def sync_wrapper(*args, **kwargs):
            return asyncio.run(fn(*args, **kwargs))
        return sync_wrapper
    return fn


# ── Registro de herramientas ──────────────────────────────────────────────────

def test_all_tools_registered(mcp):
    assert set(mcp._tool_manager._tools.keys()) == {
        "get_status", "list_voices", "list_presets", "list_phrases",
        "speak", "play_phrase", "download_last_audio",
        # Diagnóstico
        "get_logs", "get_diagnostics", "load_model", "set_verbose",
    }


def test_mcp_server_module_reexports_built_instance(tools_module):
    """`mcp_server` debe usar `build_mcp_server` y exponer la instancia."""
    import mcp_server
    assert mcp_server.mcp is not None
    assert "speak" in mcp_server.mcp._tool_manager._tools


# ── Lectura ───────────────────────────────────────────────────────────────────

def test_get_status_calls_correct_endpoint(tools_module, mcp, monkeypatch):
    seen = {}
    def handler(req):
        seen["method"] = req.method
        seen["url"]    = str(req.url)
        return _ok({"model": "xtts", "device": "cuda"})

    _patch_transport(monkeypatch, tools_module, handler)
    result = _tool(mcp, "get_status")()
    assert seen == {"method": "GET", "url": "http://test.local/api/status"}
    assert result == {"model": "xtts", "device": "cuda"}


def test_list_voices_calls_correct_endpoint(tools_module, mcp, monkeypatch):
    seen = {}
    def handler(req):
        seen["url"] = str(req.url)
        return _ok([{"id": 1, "name": "Voz1", "engine": "xtts"}])

    _patch_transport(monkeypatch, tools_module, handler)
    result = _tool(mcp, "list_voices")()
    assert seen["url"] == "http://test.local/api/voices"
    assert result[0]["name"] == "Voz1"


def test_list_presets_calls_correct_endpoint(tools_module, mcp, monkeypatch):
    seen = {}
    def handler(req):
        seen["url"] = str(req.url)
        return _ok([{"name": "MiPreset", "speed": 1.0}])

    _patch_transport(monkeypatch, tools_module, handler)
    _tool(mcp, "list_presets")()
    assert seen["url"] == "http://test.local/api/voice-presets"


def test_list_phrases_calls_correct_endpoint(tools_module, mcp, monkeypatch):
    seen = {}
    def handler(req):
        seen["url"] = str(req.url)
        return _ok([{"id": 1, "name": "saludo", "text": "Hola"}])

    _patch_transport(monkeypatch, tools_module, handler)
    _tool(mcp, "list_phrases")()
    assert seen["url"] == "http://test.local/api/phrases"


# ── Acciones ──────────────────────────────────────────────────────────────────

def test_speak_posts_voice_and_text(tools_module, mcp, monkeypatch):
    seen = {}
    def handler(req):
        seen["method"] = req.method
        seen["url"]    = str(req.url)
        seen["body"]   = req.read()
        return _ok({"status": "success"})

    _patch_transport(monkeypatch, tools_module, handler)
    result = _tool(mcp, "speak")(voice="MiPreset", text="Hola chat")
    assert seen["method"] == "POST"
    assert seen["url"] == "http://test.local/api/speak"
    assert b'"voice"' in seen["body"] and b'MiPreset' in seen["body"]
    assert b'"text"' in seen["body"] and b'Hola chat' in seen["body"]
    assert result == {"status": "success"}


def test_play_phrase_uses_url_path(tools_module, mcp, monkeypatch):
    seen = {}
    def handler(req):
        seen["method"] = req.method
        seen["url"]    = str(req.url)
        return _ok({"status": "success"})

    _patch_transport(monkeypatch, tools_module, handler)
    _tool(mcp, "play_phrase")(name="bienvenida")
    assert seen["method"] == "POST"
    assert seen["url"] == "http://test.local/api/phrases/bienvenida/play"


def test_download_last_audio_returns_metadata_when_available(tools_module, mcp, monkeypatch):
    def handler(req):
        return httpx.Response(
            200,
            headers={"content-length": "12345", "content-type": "audio/wav"},
        )

    _patch_transport(monkeypatch, tools_module, handler)
    result = _tool(mcp, "download_last_audio")()
    assert result["available"] is True
    assert result["size_bytes"] == 12345
    assert result["content_type"] == "audio/wav"
    assert result["url"].endswith("/api/speak/last")


def test_download_last_audio_returns_unavailable_on_404(tools_module, mcp, monkeypatch):
    def handler(req):
        return httpx.Response(404)

    _patch_transport(monkeypatch, tools_module, handler)
    result = _tool(mcp, "download_last_audio")()
    assert result == {"available": False,
                      "detail": "No hay audio reciente. Llama a `speak` primero."}


# ── Errores ───────────────────────────────────────────────────────────────────

def test_http_error_raises_runtime_error_with_detail(tools_module, mcp, monkeypatch):
    def handler(req):
        return httpx.Response(404, json={"detail": "Preset 'X' no encontrado"})

    _patch_transport(monkeypatch, tools_module, handler)
    with pytest.raises(RuntimeError, match="Preset 'X' no encontrado"):
        _tool(mcp, "speak")(voice="X", text="hola")


def test_connection_error_message_mentions_app(tools_module, mcp, monkeypatch):
    def handler(req):
        raise httpx.ConnectError("connection refused")

    _patch_transport(monkeypatch, tools_module, handler)
    with pytest.raises(RuntimeError, match="No se pudo conectar"):
        _tool(mcp, "list_voices")()


def test_500_without_json_body_is_propagated(tools_module, mcp, monkeypatch):
    def handler(req):
        return httpx.Response(500, text="Internal Server Error")

    _patch_transport(monkeypatch, tools_module, handler)
    with pytest.raises(RuntimeError, match="500"):
        _tool(mcp, "get_status")()


# ── Configuración por env vars ────────────────────────────────────────────────

def test_base_url_respects_env_var(monkeypatch):
    monkeypatch.setenv("MYVOICES_URL", "http://custom-host:9000/")
    sys.modules.pop("mcp_tools", None)
    import mcp_tools
    # Trailing slash debe eliminarse para evitar dobles barras en las URLs
    assert mcp_tools._base_url() == "http://custom-host:9000"


def test_default_base_url(monkeypatch):
    monkeypatch.delenv("MYVOICES_URL", raising=False)
    sys.modules.pop("mcp_tools", None)
    import mcp_tools
    assert mcp_tools._base_url() == "http://localhost:8000"


def test_register_all_idempotent_on_separate_instances(tools_module):
    """Llamar a register_all sobre dos instancias separadas no rompe nada."""
    a = tools_module.build_mcp_server(name="A")
    b = tools_module.build_mcp_server(name="B")
    assert "speak" in a._tool_manager._tools
    assert "speak" in b._tool_manager._tools


# ── Tools de diagnóstico ──────────────────────────────────────────────────────

def test_get_logs_calls_correct_endpoint(tools_module, mcp, monkeypatch):
    seen = {}
    def handler(req):
        seen["url"]    = str(req.url)
        seen["method"] = req.method
        return _ok([{"id": 1, "ts": "now", "level": "INFO",
                     "message": "hola", "caller": "API"}])
    _patch_transport(monkeypatch, tools_module, handler)
    out = _tool(mcp, "get_logs")(limit=10)
    assert seen["method"] == "GET"
    assert "/api/logs" in seen["url"]
    assert "limit=10" in seen["url"]
    assert isinstance(out, list)
    assert out[0]["message"] == "hola"


def test_get_logs_filters_by_contains(tools_module, mcp, monkeypatch):
    rows = [
        {"id": 1, "level": "ERROR", "message": "Chatterbox falló"},
        {"id": 2, "level": "INFO",  "message": "todo bien"},
        {"id": 3, "level": "ERROR", "message": "F5 error"},
    ]
    _patch_transport(monkeypatch, tools_module, lambda req: _ok(rows))
    out = _tool(mcp, "get_logs")(contains="chatterbox")
    assert len(out) == 1
    assert out[0]["id"] == 1


def test_get_diagnostics_calls_endpoint(tools_module, mcp, monkeypatch):
    seen = {}
    def handler(req):
        seen["url"] = str(req.url)
        return _ok({"engines": {}, "package_versions": {}, "verbose": False})
    _patch_transport(monkeypatch, tools_module, handler)
    out = _tool(mcp, "get_diagnostics")()
    assert "/api/diagnostics" in seen["url"]
    assert "engines" in out


def test_load_model_calls_endpoint(tools_module, mcp, monkeypatch):
    seen = {}
    def handler(req):
        seen["url"]    = str(req.url)
        seen["method"] = req.method
        return _ok({"engine": "xtts", "loaded": True, "status": "ok"})
    _patch_transport(monkeypatch, tools_module, handler)
    out = _tool(mcp, "load_model")(engine="xtts")
    assert seen["method"] == "POST"
    assert "/api/models/load/xtts" in seen["url"]
    assert out["loaded"] is True


def test_set_verbose_true_calls_endpoint(tools_module, mcp, monkeypatch):
    seen = {}
    def handler(req):
        seen["url"] = str(req.url)
        return _ok({"verbose": True})
    _patch_transport(monkeypatch, tools_module, handler)
    out = _tool(mcp, "set_verbose")(enabled=True)
    assert "/api/verbose/true" in seen["url"]
    assert out["verbose"] is True


def test_set_verbose_false_calls_endpoint(tools_module, mcp, monkeypatch):
    seen = {}
    def handler(req):
        seen["url"] = str(req.url)
        return _ok({"verbose": False})
    _patch_transport(monkeypatch, tools_module, handler)
    _tool(mcp, "set_verbose")(enabled=False)
    assert "/api/verbose/false" in seen["url"]
