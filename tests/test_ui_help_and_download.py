"""
Tests estáticos sobre static/index.html para las dos features nuevas:

1. **Cached audio download**: el botón "Descargar audio" descarga el WAV
   cacheado en el servidor (/api/speak/last) en vez de re-sintetizar; está
   deshabilitado hasta la primera reproducción exitosa, y testSpeak()
   activa el botón cuando obtiene 200.

2. **Pestaña Ayuda**: tab "help" añadida con un flujo de trabajo en pasos
   1 → 2 → 3.1-3.5 (clonar voz, crear preset, probar/guardar/llamar API).
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(ROOT, "static", "index.html")


def _read():
    with open(INDEX_HTML, encoding="utf-8") as f:
        return f.read()


def _section(html: str, fn_name: str) -> str:
    m = re.search(rf"function\s+{re.escape(fn_name)}\s*\([^)]*\)\s*\{{", html)
    assert m, f"function {fn_name} not found"
    depth = 0
    start = m.end() - 1
    for i in range(start, len(html)):
        if html[i] == "{":
            depth += 1
        elif html[i] == "}":
            depth -= 1
            if depth == 0:
                return html[m.start():i + 1]
    raise AssertionError(f"unterminated function {fn_name}")


# ── 1. Cached audio download ───────────────────────────────────────────────

def test_download_button_starts_disabled():
    html = _read()
    # El botón Descargar debe nacer disabled (no hay audio aún)
    m = re.search(
        r'<button[^>]*id="downloadBtn"[^>]*>',
        html,
    )
    assert m, "downloadBtn not found"
    assert "disabled" in m.group(0), "downloadBtn must start disabled"


def test_download_button_has_helper_title_when_disabled():
    html = _read()
    m = re.search(r'<button[^>]*id="downloadBtn"[^>]*>', html)
    assert m and "title=" in m.group(0), \
        "downloadBtn must show a title hint when disabled"


def test_test_download_uses_speak_last_endpoint():
    body = _section(_read(), "testDownload")
    assert "/api/speak/last" in body, \
        "testDownload must fetch /api/speak/last (cached audio)"
    # Y NO debe re-sintetizar
    assert "/api/speak/download" not in body, \
        "testDownload must not call /api/speak/download anymore"


def test_test_download_does_not_resynthesize():
    body = _section(_read(), "testDownload")
    # No debe enviar voice/text en POST — solo GET al endpoint cacheado
    assert "method: 'POST'" not in body, \
        "testDownload must use GET to /api/speak/last"


def test_test_speak_enables_download_on_success():
    body = _section(_read(), "testSpeak")
    # Debe habilitar el botón de descarga tras éxito
    assert re.search(r"dl\.disabled\s*=\s*false", body) or \
           re.search(r"downloadBtn'\)\.disabled\s*=\s*false", body), \
        "testSpeak must enable downloadBtn on success"


def test_test_speak_records_last_played_preset():
    body = _section(_read(), "testSpeak")
    assert "_lastPlayedPreset" in body, \
        "testSpeak must record _lastPlayedPreset for the download filename"


def test_last_played_preset_state_declared():
    html = _read()
    assert re.search(r"let\s+_lastPlayedPreset\s*=", html), \
        "_lastPlayedPreset state variable must be declared"


# ── 2. Pestaña Ayuda ───────────────────────────────────────────────────────

def test_help_tab_button_exists():
    html = _read()
    assert re.search(r'<button[^>]*data-tab="help"[^>]*>[^<]*Ayuda[^<]*</button>', html), \
        "❓ Ayuda tab button must exist in <nav>"


def test_help_tab_panel_exists():
    html = _read()
    assert re.search(r'<div[^>]*class="tab-panel"[^>]*id="tab-help"', html), \
        "tab-help panel must exist"


def test_help_tab_has_main_steps():
    html = _read()
    panel = re.search(r'id="tab-help"[\s\S]*?</div><!-- /content', html)
    assert panel, "could not isolate help tab panel"
    body = panel.group(0)
    nums = re.findall(r'class="help-step-num">(\d)</div>', body)
    # Pasos 1 (clonar voz), 2 (preset) y 4 (MCP) tienen card con numeral.
    # El paso 3 (usar el preset) se renderiza con un título + 5 branches.
    assert nums == ["1", "2", "4"], f"expected steps 1, 2 and 4, got {nums}"
    assert "help-step-title-3" in body, "missing 3rd step title"


def test_help_tab_lists_step_3_branches():
    html = _read()
    for label in ("3.1", "3.2", "3.3", "3.4", "3.5"):
        assert f'>{label}<' in html, f"branch {label} missing in help tab"


def test_help_tab_contains_workflow_keywords():
    html = _read()
    panel_match = re.search(r'id="tab-help"[\s\S]*?</div><!-- /content', html)
    assert panel_match
    body = panel_match.group(0)
    for keyword in (
        "Clonar",          # paso 1
        "preset",          # paso 2
        "Velocidad", "Tono", "Idioma", "radio",   # parámetros
        "Reproducir",      # 3.1
        "Descargar audio", # 3.2
        "frase",           # 3.3
        "/api/phrases/",   # 3.4
        "/api/speak",      # 3.5
    ):
        assert keyword in body, f"help tab missing keyword: {keyword}"


def test_help_tab_shows_api_examples():
    html = _read()
    panel_match = re.search(r'id="tab-help"[\s\S]*?</div><!-- /content', html)
    body = panel_match.group(0)
    # Debe haber al menos 2 code-blocks (uno por endpoint)
    code_blocks = re.findall(r'<pre[^>]*class="code-block"', body)
    assert len(code_blocks) >= 2, \
        f"help tab should show at least 2 API code examples, found {len(code_blocks)}"


def test_help_tab_has_dedicated_css():
    html = _read()
    for cls in (".help-flow", ".help-step", ".help-step-num", ".help-branches",
                ".help-branch"):
        assert re.search(rf"{re.escape(cls)}\s*\{{", html), \
            f"CSS rule {cls} must be defined"


# ── 3. MCP section in help tab ─────────────────────────────────────────────

def test_help_tab_has_mcp_section():
    html = _read()
    panel_match = re.search(r'id="tab-help"[\s\S]*?</div><!-- /content', html)
    assert panel_match
    body = panel_match.group(0)
    assert "MCP" in body, "help tab must mention MCP"
    assert "Model Context Protocol" in body, \
        "help tab must explain Model Context Protocol"


def test_help_mcp_lists_main_tools():
    html = _read()
    panel = re.search(r'id="tab-help"[\s\S]*?</div><!-- /content', html).group(0)
    for tool in ("speak", "play_phrase", "list_voices", "list_presets",
                 "list_phrases", "download_last_audio", "get_status"):
        assert f"<code>{tool}" in panel or f">{tool}<" in panel, \
            f"MCP tool {tool!r} missing in help tab"


def test_help_mcp_shows_install_command():
    html = _read()
    panel = re.search(r'id="tab-help"[\s\S]*?</div><!-- /content', html).group(0)
    assert "requirements-mcp.txt" in panel, \
        "help tab must show MCP install command"


def test_help_mcp_shows_claude_desktop_config():
    html = _read()
    panel = re.search(r'id="tab-help"[\s\S]*?</div><!-- /content', html).group(0)
    assert "claude_desktop_config.json" in panel, \
        "help tab must show Claude Desktop config path"
    assert "mcpServers" in panel, \
        "help tab must show mcpServers JSON key"
    assert "MYVOICES_URL" in panel, \
        "help tab must mention MYVOICES_URL env var"
