"""
Verifica que los botones de edición (icono lápiz) están presentes en el
HTML servido y conectados a las funciones JS correctas.

Es un test estático sobre static/index.html: busca patrones en
renderPresets() y renderPhrases() para confirmar que:
  - Cada fila tiene un botón con el icono ✎
  - El botón invoca loadPresetToForm / loadPhraseToTest
  - Lleva event.stopPropagation() para no chocar con el click de la fila
  - Las funciones destino existen y modifican los campos esperados
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(ROOT, "static", "index.html")


def _read():
    with open(INDEX_HTML, encoding="utf-8") as f:
        return f.read()


def _section(html: str, fn_name: str) -> str:
    """Extrae el cuerpo de una función JS top-level por nombre."""
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


# ── Presets ────────────────────────────────────────────────────────────────

def test_render_presets_has_pencil_button():
    body = _section(_read(), "renderPresets")
    assert "✎" in body, "no pencil icon in renderPresets"


def test_render_presets_pencil_calls_load_preset_to_form():
    body = _section(_read(), "renderPresets")
    # El botón con ✎ debe invocar loadPresetToForm con el nombre y la fila
    assert re.search(
        r"loadPresetToForm\(\s*\$\{JSON\.stringify\(p\.name\)\}\s*,\s*this\.closest\('tr'\)\s*\)",
        body,
    ), "pencil button must call loadPresetToForm(name, this.closest('tr'))"


def test_render_presets_pencil_stops_propagation():
    body = _section(_read(), "renderPresets")
    # Antes del botón de eliminar (✕) debe haber un stopPropagation para el lápiz
    pencil_idx = body.index("✎")
    snippet = body[max(0, pencil_idx - 200):pencil_idx]
    assert "event.stopPropagation()" in snippet, \
        "pencil button must call event.stopPropagation()"


def test_load_preset_to_form_sets_expected_fields():
    body = _section(_read(), "loadPresetToForm")
    for field_id in ("presetVoice", "presetSpeed", "presetPitch",
                     "presetRadio", "presetLang", "presetName"):
        assert f"getElementById('{field_id}')" in body, \
            f"loadPresetToForm must populate #{field_id}"


# ── Phrases ────────────────────────────────────────────────────────────────

def test_render_phrases_has_pencil_button():
    body = _section(_read(), "renderPhrases")
    assert "✎" in body, "no pencil icon in renderPhrases"


def test_render_phrases_pencil_calls_load_phrase_to_test():
    body = _section(_read(), "renderPhrases")
    assert re.search(r"loadPhraseToTest\(\$\{p\.id\}\)", body), \
        "pencil button must call loadPhraseToTest(p.id)"


def test_render_phrases_pencil_stops_propagation():
    body = _section(_read(), "renderPhrases")
    pencil_idx = body.index("✎")
    snippet = body[max(0, pencil_idx - 200):pencil_idx]
    assert "event.stopPropagation()" in snippet, \
        "pencil button must call event.stopPropagation()"


def test_load_phrase_to_test_sets_expected_fields():
    body = _section(_read(), "loadPhraseToTest")
    for field_id in ("testText", "testPreset", "savePhraseName"):
        assert f"getElementById('{field_id}')" in body, \
            f"loadPhraseToTest must populate #{field_id}"


# ── Estructura general ─────────────────────────────────────────────────────

def test_pencil_buttons_appear_before_delete_in_presets():
    body = _section(_read(), "renderPresets")
    assert body.index("✎") < body.index("✕"), \
        "pencil button should appear before delete in preset row"


def test_pencil_buttons_appear_before_delete_in_phrases():
    body = _section(_read(), "renderPhrases")
    assert body.index("✎") < body.index("✕"), \
        "pencil button should appear before delete in phrase row"
