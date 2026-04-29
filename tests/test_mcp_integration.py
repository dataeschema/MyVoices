"""
Tests del MCP HTTP embebido en la app FastAPI:

  - Endpoints `/api/mcp/*` (status, toggle, regenerate-token, clients,
    config-snippet, test)
  - Gate del mount `/mcp/`: 503 cuando está desactivado, 401 con token
    incorrecto, 200 + handshake con token válido
  - Generación de snippets para los 7 clientes documentados (Claude
    Desktop HTTP/stdio, Claude Code, Cursor, Gemini CLI, ChatGPT,
    genérico HTTP)
"""
import json

# ── /api/mcp/status ───────────────────────────────────────────────────────────

def test_mcp_status_default_off(client):
    r = client.get("/api/mcp/status")
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is False
    assert data["transport"] == "streamable-http"
    assert data["url"].endswith("/mcp/")


def test_mcp_status_after_toggle(client):
    r = client.post("/api/mcp/toggle", json={"enabled": True})
    assert r.status_code == 200
    payload = r.json()
    assert payload["enabled"] is True
    assert payload["token"]   # token autogenerado
    s = client.get("/api/mcp/status").json()
    assert s["enabled"] is True
    assert s["has_token"] is True


# ── /api/mcp/toggle ───────────────────────────────────────────────────────────

def test_mcp_toggle_persists_token_across_calls(client):
    t1 = client.post("/api/mcp/toggle", json={"enabled": True}).json()["token"]
    # Apagar no borra el token
    client.post("/api/mcp/toggle", json={"enabled": False})
    # Encender devuelve el mismo token
    t2 = client.post("/api/mcp/toggle", json={"enabled": True}).json()["token"]
    assert t1 == t2 and t1 != ""


def test_mcp_toggle_off(client):
    client.post("/api/mcp/toggle", json={"enabled": True})
    r = client.post("/api/mcp/toggle", json={"enabled": False})
    assert r.status_code == 200
    assert r.json() == {"enabled": False}


# ── /api/mcp/token + regenerate ───────────────────────────────────────────────

def test_mcp_get_token(client):
    client.post("/api/mcp/toggle", json={"enabled": True})
    r = client.get("/api/mcp/token")
    assert r.status_code == 200
    assert len(r.json()["token"]) >= 32


def test_mcp_regenerate_token_changes_value(client):
    t1 = client.post("/api/mcp/toggle", json={"enabled": True}).json()["token"]
    t2 = client.post("/api/mcp/regenerate-token").json()["token"]
    assert t1 != t2 and t2


# ── /api/mcp/clients + config-snippet ─────────────────────────────────────────

def test_mcp_clients_lists_all_supported(client):
    ids = {c["id"] for c in client.get("/api/mcp/clients").json()}
    assert ids == {
        "claude_desktop_http", "claude_desktop_stdio",
        "claude_code", "cursor", "gemini_cli", "chatgpt", "generic_http",
    }


def test_snippet_unknown_client_404(client):
    r = client.get("/api/mcp/config-snippet?client=netscape")
    assert r.status_code == 404


def test_snippet_claude_desktop_http_includes_url_and_token(client):
    tok = client.post("/api/mcp/toggle", json={"enabled": True}).json()["token"]
    r = client.get("/api/mcp/config-snippet?client=claude_desktop_http").json()
    assert r["transport"] == "http"
    assert r["format"] == "json"
    body = json.loads(r["content"])
    cfg = body["mcpServers"]["myvoices"]
    assert cfg["type"] == "http"
    assert cfg["url"].endswith("/mcp/")
    assert cfg["headers"]["Authorization"] == f"Bearer {tok}"


def test_snippet_claude_desktop_stdio_uses_python_path(client):
    client.post("/api/mcp/toggle", json={"enabled": True})
    r = client.get("/api/mcp/config-snippet?client=claude_desktop_stdio").json()
    body = json.loads(r["content"])
    cfg = body["mcpServers"]["myvoices"]
    assert cfg["command"].endswith(("python.exe", "python", "python3"))
    assert any(arg.endswith("mcp_server.py") for arg in cfg["args"])
    assert "MYVOICES_URL" in cfg["env"]


def test_snippet_claude_code_is_bash(client):
    client.post("/api/mcp/toggle", json={"enabled": True})
    r = client.get("/api/mcp/config-snippet?client=claude_code").json()
    assert r["format"] == "bash"
    assert "claude mcp add myvoices" in r["content"]
    assert "--transport http" in r["content"]
    assert "Authorization: Bearer" in r["content"]


def test_snippet_cursor_uses_mcpServers(client):
    client.post("/api/mcp/toggle", json={"enabled": True})
    r = client.get("/api/mcp/config-snippet?client=cursor").json()
    body = json.loads(r["content"])
    assert "mcpServers" in body
    assert body["mcpServers"]["myvoices"]["url"].endswith("/mcp/")


def test_snippet_gemini_cli_uses_httpUrl(client):
    client.post("/api/mcp/toggle", json={"enabled": True})
    r = client.get("/api/mcp/config-snippet?client=gemini_cli").json()
    body = json.loads(r["content"])
    cfg = body["mcpServers"]["myvoices"]
    assert "httpUrl" in cfg
    assert "httpHeaders" in cfg


def test_snippet_chatgpt_is_text(client):
    client.post("/api/mcp/toggle", json={"enabled": True})
    r = client.get("/api/mcp/config-snippet?client=chatgpt").json()
    assert r["format"] == "text"
    assert "Server URL" in r["content"]
    assert "Authorization: Bearer" in r["content"]


def test_snippet_generic_http_is_curl(client):
    client.post("/api/mcp/toggle", json={"enabled": True})
    r = client.get("/api/mcp/config-snippet?client=generic_http").json()
    assert r["format"] == "bash"
    assert "curl" in r["content"]
    assert "/mcp/" in r["content"]


def test_snippet_omits_authorization_when_no_token(client):
    """Si no hay token (caso edge: token vaciado), el snippet sigue siendo
    válido pero sin header de auth."""
    import database
    database.save_config({"mcp_enabled": True, "mcp_token": ""})
    r = client.get("/api/mcp/config-snippet?client=claude_desktop_http").json()
    body = json.loads(r["content"])
    headers = body["mcpServers"]["myvoices"]["headers"]
    assert headers == {}


# ── Mount /mcp/ con gate ──────────────────────────────────────────────────────

def _mcp_init_payload():
    return {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities":    {},
            "clientInfo":      {"name": "test", "version": "1"},
        },
    }


def test_mcp_mount_503_when_disabled(client):
    """Si el toggle está OFF, /mcp/ devuelve 503 sin importar el token."""
    client.post("/api/mcp/toggle", json={"enabled": False})
    r = client.post(
        "/mcp/",
        json=_mcp_init_payload(),
        headers={"accept": "application/json, text/event-stream"},
    )
    assert r.status_code == 503
    assert "MCP" in r.text


def test_mcp_mount_401_without_token(client):
    client.post("/api/mcp/toggle", json={"enabled": True})
    r = client.post(
        "/mcp/",
        json=_mcp_init_payload(),
        headers={"accept": "application/json, text/event-stream"},
    )
    assert r.status_code == 401


def test_mcp_mount_401_with_wrong_token(client):
    client.post("/api/mcp/toggle", json={"enabled": True})
    r = client.post(
        "/mcp/",
        json=_mcp_init_payload(),
        headers={"accept": "application/json, text/event-stream",
                 "Authorization": "Bearer wrong-token-xyz"},
    )
    assert r.status_code == 401


def test_mcp_mount_handshake_with_valid_token(client):
    tok = client.post("/api/mcp/toggle", json={"enabled": True}).json()["token"]
    r = client.post(
        "/mcp/",
        json=_mcp_init_payload(),
        headers={"accept": "application/json, text/event-stream",
                 "Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    # FastMCP responde el handshake con SSE; el body lleva protocolVersion
    assert "protocolVersion" in r.text


# ── /api/mcp/test ─────────────────────────────────────────────────────────────

def test_mcp_self_test_when_disabled(client):
    client.post("/api/mcp/toggle", json={"enabled": False})
    r = client.post("/api/mcp/test").json()
    assert r["ok"] is False
    assert "desactivado" in r["detail"].lower()
