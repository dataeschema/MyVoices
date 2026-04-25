"""
Verifica que los botones de edición (lápiz) están presentes en el HTML
servido y conectados a las funciones JS correctas vía event delegation
con atributos data-*.

Cambios sobre la versión anterior:
- Las filas y botones ya NO usan onclick inline, sino data-action / data-id /
  data-name. Un único listener delegado en cada tbody despacha la acción.
- Esto elimina la inyección por comillas en nombres de preset y la
  necesidad de JSON.stringify dentro de atributos HTML.
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


# ── Presets — markup ───────────────────────────────────────────────────────

def test_render_presets_has_pencil_button():
    body = _section(_read(), "renderPresets")
    assert "✎ Editar" in body, "pencil button missing in renderPresets"


def test_render_presets_uses_data_action():
    body = _section(_read(), "renderPresets")
    assert 'data-action="edit"' in body, "preset edit button must use data-action='edit'"
    assert 'data-action="delete"' in body, "preset delete button must use data-action='delete'"


def test_render_presets_row_has_data_name():
    body = _section(_read(), "renderPresets")
    assert re.search(r'<tr\s+class="preset-row"\s+data-name="', body), \
        "preset row must expose data-name attribute"


def test_render_presets_no_inline_onclick():
    body = _section(_read(), "renderPresets")
    assert "onclick=" not in body, \
        "renderPresets must not contain inline onclick handlers"


def test_render_presets_pencil_uses_edit_style():
    body = _section(_read(), "renderPresets")
    assert re.search(r'class="btn btn-edit btn-sm"\s+data-action="edit"', body), \
        "pencil button must use btn-edit class with data-action='edit'"


def test_render_presets_no_unsafe_json_stringify():
    body = _section(_read(), "renderPresets")
    assert "JSON.stringify" not in body, \
        "renderPresets must not embed JSON.stringify inside HTML attributes"


# ── Phrases — markup ───────────────────────────────────────────────────────

def test_render_phrases_has_pencil_button():
    body = _section(_read(), "renderPhrases")
    assert "✎ Editar" in body, "pencil button missing in renderPhrases"


def test_render_phrases_uses_data_action():
    body = _section(_read(), "renderPhrases")
    assert 'data-action="edit"' in body
    assert 'data-action="delete"' in body


def test_render_phrases_row_has_data_id():
    body = _section(_read(), "renderPhrases")
    assert re.search(r'data-id="\$\{p\.id\}"', body), \
        "phrase row must expose data-id attribute"


def test_render_phrases_no_inline_onclick():
    body = _section(_read(), "renderPhrases")
    assert "onclick=" not in body, \
        "renderPhrases must not contain inline onclick handlers"


def test_render_phrases_pencil_uses_edit_style():
    body = _section(_read(), "renderPhrases")
    assert re.search(r'class="btn btn-edit btn-sm"\s+data-action="edit"', body)


# ── Event delegation ───────────────────────────────────────────────────────

def test_presets_body_event_delegation_present():
    html = _read()
    # Debe existir un addEventListener('click') sobre #presetsBody
    assert re.search(
        r"getElementById\('presetsBody'\)[\s\S]{0,200}addEventListener\('click'",
        html,
    ), "presetsBody must have a delegated click listener"


def test_phrases_body_event_delegation_present():
    html = _read()
    assert re.search(
        r"getElementById\('phrasesBody'\)[\s\S]{0,200}addEventListener\('click'",
        html,
    ), "phrasesBody must have a delegated click listener"


# ── Funciones invocadas por la delegación ──────────────────────────────────

def test_load_preset_to_form_sets_expected_fields():
    body = _section(_read(), "loadPresetToForm")
    for field_id in ("presetVoice", "presetSpeed", "presetPitch",
                     "presetRadio", "presetLang", "presetName"):
        assert f"getElementById('{field_id}')" in body, \
            f"loadPresetToForm must populate #{field_id}"


def test_load_phrase_to_test_sets_expected_fields():
    body = _section(_read(), "loadPhraseToTest")
    for field_id in ("testText", "testPreset", "savePhraseName"):
        assert f"getElementById('{field_id}')" in body, \
            f"loadPhraseToTest must populate #{field_id}"


# ── escAttr helper ─────────────────────────────────────────────────────────

def test_escAttr_helper_defined():
    html = _read()
    assert re.search(r"function\s+escAttr\s*\(", html), \
        "escAttr() helper must be defined for safe JS-attr interpolation"


# ── CSS ────────────────────────────────────────────────────────────────────

def test_btn_edit_class_defined_in_css():
    html = _read()
    assert re.search(r"\.btn-edit\s*\{[^}]*background[^}]*\}", html), \
        "CSS class .btn-edit must be defined"
    assert re.search(r"\.btn-edit:hover\s*\{[^}]*background[^}]*\}", html), \
        "CSS class .btn-edit:hover must be defined"


# ── Estructura general ─────────────────────────────────────────────────────

def test_pencil_buttons_appear_before_delete_in_presets():
    body = _section(_read(), "renderPresets")
    assert body.index("✎") < body.index("✕"), \
        "pencil button should appear before delete in preset row"


def test_pencil_buttons_appear_before_delete_in_phrases():
    body = _section(_read(), "renderPhrases")
    assert body.index("✎") < body.index("✕"), \
        "pencil button should appear before delete in phrase row"
