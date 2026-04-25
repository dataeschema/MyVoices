import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import _sanitize_name, split_into_chunks

# ── split_into_chunks ─────────────────────────────────────────────────────────

def test_short_text_single_chunk():
    result = split_into_chunks("Hola mundo.", max_chars=200)
    assert result == ["Hola mundo."]


def test_empty_string_returns_nonempty_list():
    result = split_into_chunks("", max_chars=200)
    assert isinstance(result, list) and len(result) >= 1


def test_long_text_splits_by_sentence():
    sentence = "Esta es una frase de prueba."
    # 8 repetitions will exceed 200 chars
    text = " ".join([sentence] * 8)
    result = split_into_chunks(text, max_chars=200)
    assert len(result) > 1
    for chunk in result:
        assert len(chunk) <= 200


def test_splits_by_comma_when_no_period():
    # A single long sentence with commas but no period
    words = ["palabra"] * 5
    long_sentence = ", ".join(words) + ", " + ", ".join(words)
    text = " ".join([long_sentence] * 5)
    result = split_into_chunks(text, max_chars=50)
    assert len(result) > 1


def test_chunk_max_chars_respected():
    sentence = "Frase corta. "
    text = sentence * 30
    result = split_into_chunks(text, max_chars=100)
    for chunk in result:
        assert len(chunk) <= 100


def test_single_long_word_not_cut():
    long_word = "a" * 300
    result = split_into_chunks(long_word, max_chars=200)
    # Cannot split a single word — must return it intact
    assert "".join(result).replace(" ", "") == long_word


def test_normalizes_whitespace():
    result = split_into_chunks("Hola   mundo   con   espacios.", max_chars=200)
    assert result == ["Hola mundo con espacios."]


def test_multiple_sentences_grouped_under_limit():
    # Two short sentences should be grouped into one chunk
    result = split_into_chunks("Hola. Mundo.", max_chars=200)
    assert len(result) == 1
    assert "Hola." in result[0]
    assert "Mundo." in result[0]


# ── _sanitize_name ────────────────────────────────────────────────────────────

def test_sanitize_removes_special_chars():
    assert _sanitize_name("Voz#1!") == "Voz1"


def test_sanitize_keeps_allowed_chars():
    assert _sanitize_name("Mi-Voz_01") == "Mi-Voz_01"


def test_sanitize_keeps_spaces():
    assert _sanitize_name("Mi Voz") == "Mi Voz"


def test_sanitize_strips_leading_trailing():
    assert _sanitize_name("  Voz  ") == "Voz"


def test_sanitize_empty_string():
    assert _sanitize_name("") == ""


def test_sanitize_only_special_chars():
    assert _sanitize_name("###!!!") == ""
