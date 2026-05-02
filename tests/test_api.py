import io
import wave
from pathlib import Path

# ── Helpers ───────────────────────────────────────────────────────────────────

def _dummy_wav_bytes() -> bytes:
    """Returns a minimal valid WAV file (1-channel, 16-bit, 1 sample)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(b"\x00\x00")
    return buf.getvalue()


def _create_voice(client, name="TestVoz"):
    """Helper: POST a dummy WAV voice and return the response JSON."""
    return client.post(
        "/api/voices/xtts",
        data={"name": name},
        files={"file": (f"{name}.wav", _dummy_wav_bytes(), "audio/wav")},
    )


def _create_preset(client, voice_id, name="TestPreset"):
    """Helper: POST a voice preset and return the response JSON."""
    return client.post(
        "/api/voice-presets",
        data={"name": name, "voice_id": voice_id, "speed": "1.0",
              "pitch": "0.0", "radio_effect": "false", "language": "es"},
    )


# ── Status & Config ───────────────────────────────────────────────────────────

def test_get_status(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    data = r.json()
    assert "model" in data
    assert "device" in data


def test_get_config_defaults(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    assert r.json()["language"] == "es"


def test_post_config(client):
    r = client.post("/api/config", data={"language": "en"})
    assert r.status_code == 200
    assert client.get("/api/config").json()["language"] == "en"


# ── Voices CRUD ───────────────────────────────────────────────────────────────

def test_post_xtts_voice(client):
    r = _create_voice(client)
    assert r.status_code == 200
    data = r.json()
    assert "id" in data
    assert data["engine"] == "xtts"
    assert data["name"] == "TestVoz"


def test_post_xtts_voice_invalid_extension(client):
    r = client.post(
        "/api/voices/xtts",
        data={"name": "Mala"},
        files={"file": ("audio.mp3", b"fake", "audio/mpeg")},
    )
    assert r.status_code == 400


def test_post_xtts_voice_invalid_name(client):
    r = client.post(
        "/api/voices/xtts",
        data={"name": "###"},
        files={"file": ("audio.wav", _dummy_wav_bytes(), "audio/wav")},
    )
    assert r.status_code == 400


def test_get_voice_list(client):
    _create_voice(client, "Lista1")
    r = client.get("/api/voices")
    assert r.status_code == 200
    names = [v["name"] for v in r.json()]
    assert "Lista1" in names


def test_get_single_voice(client):
    vid = _create_voice(client, "Individual").json()["id"]
    r = client.get(f"/api/voices/{vid}")
    assert r.status_code == 200
    assert r.json()["id"] == vid


def test_get_voice_not_found(client):
    assert client.get("/api/voices/9999").status_code == 404


def test_put_voice_rename(client):
    vid = _create_voice(client, "Antes").json()["id"]
    r = client.put(f"/api/voices/{vid}", data={"name": "Despues"})
    assert r.status_code == 200
    assert r.json()["name"] == "Despues"


def test_delete_voice(client):
    vid = _create_voice(client, "ParaBorrar").json()["id"]
    assert client.delete(f"/api/voices/{vid}").status_code == 200
    assert client.get(f"/api/voices/{vid}").status_code == 404


# ── Voice Presets CRUD ────────────────────────────────────────────────────────

def test_post_preset(client):
    vid = _create_voice(client).json()["id"]
    r = _create_preset(client, vid)
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "TestPreset"
    assert data["voice_id"] == vid


def test_post_preset_voice_not_found(client):
    r = client.post(
        "/api/voice-presets",
        data={"name": "OrphanPreset", "voice_id": "9999", "speed": "1.0",
              "pitch": "0.0", "radio_effect": "false", "language": "es"},
    )
    assert r.status_code == 404


def test_get_presets(client):
    vid = _create_voice(client, "VozLista").json()["id"]
    _create_preset(client, vid, "PresetLista")
    r = client.get("/api/voice-presets")
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert "PresetLista" in names


def test_put_preset_updates_speed(client):
    vid = _create_voice(client, "VozUpdate").json()["id"]
    _create_preset(client, vid, "UpdatePreset")
    r = client.put("/api/voice-presets/UpdatePreset", data={"speed": "1.8"})
    assert r.status_code == 200
    assert r.json()["speed"] == 1.8


def test_delete_preset(client):
    vid = _create_voice(client, "VozDel").json()["id"]
    _create_preset(client, vid, "DeletePreset")
    assert client.delete("/api/voice-presets/DeletePreset").status_code == 200
    names = [p["name"] for p in client.get("/api/voice-presets").json()]
    assert "DeletePreset" not in names


def test_delete_preset_not_found(client):
    assert client.delete("/api/voice-presets/NoExiste").status_code == 404


# ── Phrases CRUD ──────────────────────────────────────────────────────────────

def test_post_phrase(client):
    r = client.post("/api/phrases", data={"name": "Saludo", "text": "Hola mundo"})
    assert r.status_code == 200
    data = r.json()
    assert "id" in data
    assert data["text"] == "Hola mundo"


def test_post_phrase_empty_text(client):
    r = client.post("/api/phrases", data={"name": "Vacia", "text": "   "})
    assert r.status_code == 400


def test_post_phrase_empty_name(client):
    r = client.post("/api/phrases", data={"name": "   ", "text": "Texto"})
    assert r.status_code == 400


def test_post_phrase_duplicate_name_updates(client):
    client.post("/api/phrases", data={"name": "Duplicada", "text": "Primera"})
    r = client.post("/api/phrases", data={"name": "Duplicada", "text": "Segunda"})
    assert r.status_code == 200
    assert r.json()["text"] == "Segunda"


def test_get_phrases(client):
    client.post("/api/phrases", data={"name": "FraseLista", "text": "Texto lista"})
    r = client.get("/api/phrases")
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert "FraseLista" in names


def test_put_phrase(client):
    pid = client.post("/api/phrases", data={"name": "Edit", "text": "Original"}).json()["id"]
    r = client.put(f"/api/phrases/{pid}", data={"name": "Edit", "text": "Actualizado"})
    assert r.status_code == 200
    assert r.json()["text"] == "Actualizado"


def test_delete_phrase(client):
    pid = client.post("/api/phrases", data={"name": "Borrar", "text": "Texto"}).json()["id"]
    assert client.delete(f"/api/phrases/{pid}").status_code == 200
    names = [p["name"] for p in client.get("/api/phrases").json()]
    assert "Borrar" not in names


def test_delete_phrase_not_found(client):
    assert client.delete("/api/phrases/9999").status_code == 404


# ── Logs ──────────────────────────────────────────────────────────────────────

def test_get_logs(client):
    r = client.get("/api/logs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_delete_logs(client):
    import database
    database.log_event("INFO", "Entrada para borrar")
    assert client.delete("/api/logs").status_code == 200
    # The DELETE request itself may create new httpx access log entries,
    # so we verify our seeded entry was removed rather than checking for empty list.
    msgs = [l["message"] for l in client.get("/api/logs").json()]
    assert "Entrada para borrar" not in msgs


def test_get_logs_filter_by_level(client):
    import database
    database.log_event("ERROR", "Falla X")
    database.log_event("INFO", "Info Y")
    only_errors = client.get("/api/logs?level=ERROR").json()
    levels = {l["level"] for l in only_errors}
    assert levels <= {"ERROR"}
    assert any(l["message"] == "Falla X" for l in only_errors)


def test_get_logs_with_limit(client):
    import database
    for i in range(5):
        database.log_event("INFO", f"línea {i}")
    res = client.get("/api/logs?limit=2").json()
    assert len(res) <= 2


# ── /api/speak (síntesis mockeada) ────────────────────────────────────────────

def test_speak_requires_text(client):
    r = client.post("/api/speak", json={"voice": "preset", "text": ""})
    assert r.status_code == 400


def test_speak_requires_voice(client):
    r = client.post("/api/speak", json={"voice": "", "text": "hola"})
    assert r.status_code == 400


def test_speak_synthesizes_caches_and_starts_playback(client, monkeypatch, tmp_path):
    """`/api/speak` debe sintetizar un fichero, guardarlo en _last_speak_path
    y arrancar la reproducción en background."""
    import server

    captured = {}

    wav = tmp_path / "speak.wav"
    wav.write_bytes(_dummy_wav_bytes())

    def fake_synth(preset, text):
        captured["preset"] = preset
        captured["text"]   = text
        return str(wav)

    played: list = []
    def fake_play(path):
        played.append(path)

    monkeypatch.setattr(server, "_synth_to_file_sync", fake_synth)
    monkeypatch.setattr(server, "play_audio_keep",     fake_play)
    monkeypatch.setattr(server, "_last_speak_path",    None)

    r = client.post("/api/speak", json={"voice": "MiPreset", "text": "Hola chat"})
    assert r.status_code == 200
    assert r.json()["status"] == "success"
    assert captured == {"preset": "MiPreset", "text": "Hola chat"}
    assert server._last_speak_path == str(wav)


def test_speak_propagates_value_error(client, monkeypatch):
    import server

    def boom(preset, text):
        raise ValueError("preset 'X' no encontrado")

    monkeypatch.setattr(server, "_synth_to_file_sync", boom)
    monkeypatch.setattr(server, "play_audio_keep", lambda p: None)
    r = client.post("/api/speak", json={"voice": "X", "text": "y"})
    assert r.status_code == 400
    assert "no encontrado" in r.json()["detail"]


def test_speak_replaces_previous_cache_file(client, monkeypatch, tmp_path):
    """Una nueva llamada a /api/speak debe borrar el WAV cacheado anterior."""
    import server

    old = tmp_path / "old.wav"; old.write_bytes(_dummy_wav_bytes())
    new = tmp_path / "new.wav"; new.write_bytes(_dummy_wav_bytes())

    monkeypatch.setattr(server, "_last_speak_path", str(old))
    monkeypatch.setattr(server, "_synth_to_file_sync", lambda p, t: str(new))
    monkeypatch.setattr(server, "play_audio_keep", lambda p: None)

    r = client.post("/api/speak", json={"voice": "p", "text": "t"})
    assert r.status_code == 200
    assert server._last_speak_path == str(new)
    assert not old.exists(), "el WAV cacheado anterior debe borrarse"
    assert new.exists()


# ── /api/speak/last ───────────────────────────────────────────────────────────

def test_speak_last_returns_cached_wav(client, monkeypatch, tmp_path):
    import server

    wav = tmp_path / "last.wav"
    wav.write_bytes(_dummy_wav_bytes())
    monkeypatch.setattr(server, "_last_speak_path", str(wav))

    r = client.get("/api/speak/last")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/wav")
    assert r.content[:4] == b"RIFF"


def test_speak_last_404_when_no_cache(client, monkeypatch):
    import server
    monkeypatch.setattr(server, "_last_speak_path", None)

    r = client.get("/api/speak/last")
    assert r.status_code == 404
    assert "Reproduce" in r.json()["detail"]


def test_speak_last_404_when_file_missing(client, monkeypatch, tmp_path):
    """Si el path está cacheado pero el fichero ya no existe, debe ser 404."""
    import server
    monkeypatch.setattr(server, "_last_speak_path", str(tmp_path / "ghost.wav"))

    r = client.get("/api/speak/last")
    assert r.status_code == 404


# ── /api/speak/download ───────────────────────────────────────────────────────

def test_speak_download_requires_text(client):
    r = client.post("/api/speak/download", json={"voice": "p", "text": ""})
    assert r.status_code == 400


def test_speak_download_returns_wav(client, monkeypatch, tmp_path):
    import server

    wav_path = tmp_path / "fake.wav"
    wav_path.write_bytes(_dummy_wav_bytes())

    def fake_synth(preset, text):
        return str(wav_path)

    monkeypatch.setattr(server, "_synth_to_file_sync", fake_synth)
    r = client.post("/api/speak/download",
                    json={"voice": "MiPreset", "text": "Hola"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/wav")
    assert "myvoices_MiPreset.wav" in r.headers.get("content-disposition", "")
    assert r.content[:4] == b"RIFF"


def test_speak_download_propagates_value_error(client, monkeypatch):
    import server

    def boom(preset, text):
        raise ValueError("preset no encontrado")

    monkeypatch.setattr(server, "_synth_to_file_sync", boom)
    r = client.post("/api/speak/download",
                    json={"voice": "X", "text": "y"})
    assert r.status_code == 400
    assert "preset no encontrado" in r.json()["detail"]


# ── /api/phrases/{name}/play ──────────────────────────────────────────────────

def test_play_phrase_by_name(client, monkeypatch):
    import server

    captured = {}

    def fake_synth(preset_name, text):
        captured["preset"] = preset_name
        captured["text"]   = text
        import io
        import tempfile
        import wave as wv
        buf = io.BytesIO()
        with wv.open(buf, "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(22050)
            wf.writeframes(b"\x00\x00")
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        tmp.write(buf.getvalue()); tmp.close()
        return tmp.name

    monkeypatch.setattr(server, "_synth_to_file_sync", fake_synth)

    # Setup: create voice → preset → phrase
    vid = _create_voice(client, "VozPlay").json()["id"]
    _create_preset(client, vid, name="PresetPlay")
    client.post("/api/phrases", data={
        "name":              "saludo",
        "text":              "Hola streamers",
        "voice_preset_name": "PresetPlay",
    })

    r = client.post("/api/phrases/saludo/play")
    assert r.status_code == 200
    assert captured["text"] == "Hola streamers"
    assert captured["preset"] == "PresetPlay"


def test_play_phrase_not_found(client):
    r = client.post("/api/phrases/no-existe/play")
    assert r.status_code == 404


# ── /api/piper/available (catálogo mockeado) ──────────────────────────────────

def test_piper_available_lists_voices(client, monkeypatch):
    import server

    fake_catalog = {
        "es_ES-mls_10246-low": {
            "name":     "mls_10246",
            "language": {"code": "es_ES", "name_english": "Spanish"},
            "quality":  "low",
            "num_speakers": 1,
            "files": {"f.onnx": {"size_bytes": 1_048_576}},
        },
        "en_US-amy-medium": {
            "name":     "amy",
            "language": {"code": "en_US", "name_english": "English"},
            "quality":  "medium",
            "num_speakers": 1,
            "files": {"f.onnx": {"size_bytes": 2_097_152}},
        },
    }

    # Reset the cache and inject our fake
    monkeypatch.setattr(server, "_voices_json_cache", fake_catalog)
    monkeypatch.setattr(server, "_voices_json_time", 9_999_999_999)

    r = client.get("/api/piper/available")
    assert r.status_code == 200
    keys = [v["key"] for v in r.json()]
    assert "es_ES-mls_10246-low" in keys
    assert "en_US-amy-medium" in keys


def test_piper_available_filter_by_language(client, monkeypatch):
    import server
    fake_catalog = {
        "es_ES-x-low": {
            "name": "x", "language": {"code": "es_ES", "name_english": "Spanish"},
            "quality": "low", "num_speakers": 1, "files": {},
        },
        "en_US-y-low": {
            "name": "y", "language": {"code": "en_US", "name_english": "English"},
            "quality": "low", "num_speakers": 1, "files": {},
        },
    }
    monkeypatch.setattr(server, "_voices_json_cache", fake_catalog)
    monkeypatch.setattr(server, "_voices_json_time", 9_999_999_999)

    r = client.get("/api/piper/available?lang=es")
    assert r.status_code == 200
    codes = {v["language_code"] for v in r.json()}
    assert codes == {"es_ES"}


# ── /api/status — nuevos campos de motores ────────────────────────────────────

def test_status_includes_new_engine_fields(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    data = r.json()
    assert "f5tts_available" in data
    assert "f5tts_status" in data
    assert "chatterbox_available" in data
    assert "chatterbox_status" in data
    assert "voices_f5tts" in data
    assert "voices_chatterbox" in data


# ── F5-TTS voices CRUD ────────────────────────────────────────────────────────

def test_post_f5tts_voice(client):
    r = client.post(
        "/api/voices/f5tts",
        data={"name": "VozF5"},
        files={"file": ("ref.wav", _dummy_wav_bytes(), "audio/wav")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["engine"] == "f5tts"
    assert data["name"] == "VozF5"


def test_post_f5tts_voice_invalid_ext(client):
    r = client.post(
        "/api/voices/f5tts",
        data={"name": "Mala"},
        files={"file": ("audio.mp3", b"fake", "audio/mpeg")},
    )
    assert r.status_code == 400


def test_list_f5tts_voices(client):
    client.post(
        "/api/voices/f5tts",
        data={"name": "F5Lista"},
        files={"file": ("ref.wav", _dummy_wav_bytes(), "audio/wav")},
    )
    r = client.get("/api/voices?engine=f5tts")
    assert r.status_code == 200
    names = [v["name"] for v in r.json()]
    assert "F5Lista" in names


def test_delete_f5tts_voice(client):
    vid = client.post(
        "/api/voices/f5tts",
        data={"name": "F5Borrar"},
        files={"file": ("ref.wav", _dummy_wav_bytes(), "audio/wav")},
    ).json()["id"]
    assert client.delete(f"/api/voices/{vid}").status_code == 200
    assert client.get(f"/api/voices/{vid}").status_code == 404


def test_delete_f5tts_voice_cleans_sidecars(client, tmp_path, monkeypatch):
    """DELETE /api/voices/{id} debe borrar también los .lang.txt sidecars."""
    import server
    monkeypatch.setattr(server, "VOICES_DIR", tmp_path)

    vid = client.post(
        "/api/voices/f5tts",
        data={"name": "F5Sidecar"},
        files={"file": ("ref.wav", _dummy_wav_bytes(), "audio/wav")},
    ).json()["id"]

    # Simular que _get_f5_ref_text creó un sidecar
    voice_data = client.get(f"/api/voices/{vid}").json()
    wav_stem = Path(voice_data["filename"]).stem
    sidecar = tmp_path / f"{wav_stem}.es.txt"
    sidecar.write_text("Hola mundo")

    client.delete(f"/api/voices/{vid}")
    assert not sidecar.exists(), "El sidecar .es.txt no fue eliminado"


def test_get_f5_ref_text_uses_cache(tmp_path):
    """_get_f5_ref_text devuelve el contenido del sidecar si ya existe."""
    import server
    wav = tmp_path / "voice.wav"
    wav.write_bytes(_dummy_wav_bytes())
    sidecar = tmp_path / "voice.es.txt"
    sidecar.write_text("texto cacheado", encoding="utf-8")

    result = server._get_f5_ref_text(wav, "es")
    assert result == "texto cacheado"


def test_get_f5_ref_text_fallback_on_error(tmp_path, monkeypatch):
    """Si la transcripción falla, _get_f5_ref_text devuelve '' sin lanzar."""
    import sys

    import server

    wav = tmp_path / "voice.wav"
    wav.write_bytes(_dummy_wav_bytes())

    # Forzar fallo: inyectar un módulo stub cuya `transcribe` lanza
    class _FakeUtils:
        @staticmethod
        def transcribe(*a, **kw):
            raise RuntimeError("whisper no disponible")

    monkeypatch.setitem(sys.modules, "f5_tts.infer.utils_infer", _FakeUtils())

    result = server._get_f5_ref_text(wav, "es")
    assert result == ""


# ── Chatterbox voices CRUD ────────────────────────────────────────────────────

def test_post_chatterbox_voice(client):
    r = client.post(
        "/api/voices/chatterbox",
        data={"name": "VozCB"},
        files={"file": ("ref.wav", _dummy_wav_bytes(), "audio/wav")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["engine"] == "chatterbox"
    assert data["name"] == "VozCB"


def test_post_chatterbox_voice_invalid_ext(client):
    r = client.post(
        "/api/voices/chatterbox",
        data={"name": "Mala"},
        files={"file": ("audio.mp3", b"fake", "audio/mpeg")},
    )
    assert r.status_code == 400


def test_list_chatterbox_voices(client):
    client.post(
        "/api/voices/chatterbox",
        data={"name": "CBLista"},
        files={"file": ("ref.wav", _dummy_wav_bytes(), "audio/wav")},
    )
    r = client.get("/api/voices?engine=chatterbox")
    assert r.status_code == 200
    names = [v["name"] for v in r.json()]
    assert "CBLista" in names


def test_delete_chatterbox_voice(client):
    vid = client.post(
        "/api/voices/chatterbox",
        data={"name": "CBBorrar"},
        files={"file": ("ref.wav", _dummy_wav_bytes(), "audio/wav")},
    ).json()["id"]
    assert client.delete(f"/api/voices/{vid}").status_code == 200
    assert client.get(f"/api/voices/{vid}").status_code == 404


# ── /api/models/load ─────────────────────────────────────────────────────────

def test_load_model_unknown_engine(client):
    r = client.post("/api/models/load/unknown")
    assert r.status_code == 400


def test_load_model_f5tts_not_installed(client, monkeypatch):
    import server
    monkeypatch.setattr(server, "F5TTS_AVAILABLE", False)
    r = client.post("/api/models/load/f5tts")
    assert r.status_code == 503


def test_load_model_chatterbox_not_installed(client, monkeypatch):
    import server
    monkeypatch.setattr(server, "CHATTERBOX_AVAILABLE", False)
    r = client.post("/api/models/load/chatterbox")
    assert r.status_code == 503


# ── /api/diagnostics ──────────────────────────────────────────────────────────

def test_diagnostics_returns_engine_status(client):
    r = client.get("/api/diagnostics")
    assert r.status_code == 200
    data = r.json()
    assert "engines" in data
    assert "package_versions" in data
    assert "verbose" in data
    assert set(data["engines"].keys()) == {"xtts", "piper", "f5tts", "chatterbox"}
    for eng in ("f5tts", "chatterbox"):
        assert "available" in data["engines"][eng]
        assert "import_error" in data["engines"][eng]


def test_diagnostics_includes_package_versions(client):
    r = client.get("/api/diagnostics").json()
    versions = r["package_versions"]
    assert "torch" in versions
    assert "transformers" in versions


# ── /api/verbose ──────────────────────────────────────────────────────────────

def test_set_verbose_true(client):
    r = client.post("/api/verbose/true")
    assert r.status_code == 200
    assert r.json()["verbose"] is True


def test_set_verbose_false(client):
    client.post("/api/verbose/true")
    r = client.post("/api/verbose/false")
    assert r.status_code == 200
    assert r.json()["verbose"] is False


def test_set_verbose_persists_in_config(client):
    client.post("/api/verbose/true")
    cfg = client.get("/api/config").json()
    assert cfg["verbose"] == "true"


# ── Conversión de formato (mp3 / ogg / wav) ──────────────────────────────────

def test_convert_audio_wav_passthrough(tmp_path):
    """fmt='wav' debe devolver el mismo path sin tocar el WAV."""
    import server
    wav = tmp_path / "in.wav"
    wav.write_bytes(_dummy_wav_bytes())
    out = server._convert_audio(str(wav), "wav")
    assert out == str(wav)


def test_convert_audio_invalid_format_raises(tmp_path):
    """Formato no soportado → ValueError."""
    import pytest

    import server
    wav = tmp_path / "in.wav"
    wav.write_bytes(_dummy_wav_bytes())
    with pytest.raises(ValueError, match="no soportado"):
        server._convert_audio(str(wav), "flac")


def test_speak_last_invalid_format(client):
    """Pedir un format no soportado debe responder 400."""
    # Forzamos a que haya algo cacheado para que no sea 404
    import tempfile

    import server
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    tmp.write(_dummy_wav_bytes()); tmp.close()
    server._last_speak_path = tmp.name
    try:
        r = client.get("/api/speak/last?format=flac")
        assert r.status_code == 400
        assert "no soportado" in r.json()["detail"].lower()
    finally:
        import os
        os.remove(tmp.name)
        server._last_speak_path = None


def test_wandb_stub_when_frozen(monkeypatch):
    """El stub de wandb (solo activo en sys.frozen=True) debe registrar
    los módulos con __spec__ válido para que importlib.util.find_spec()
    no lance ValueError. Esto rompía la cadena de imports de transformers
    cuando accelerate llamaba is_wandb_available() en el bundle."""
    import importlib.util as ilu
    import sys

    import server

    # Simular contexto frozen y limpiar sys.modules de cualquier wandb
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    for name in (
        "wandb", "wandb_gql", "wandb_gql.client",
        "wandb_graphql", "wandb_graphql.language",
        "wandb_graphql.language.ast",
    ):
        sys.modules.pop(name, None)

    server._mock_wandb_when_frozen()

    # find_spec debe funcionar sin levantar ValueError
    spec = ilu.find_spec("wandb")
    assert spec is not None
    assert spec.name == "wandb"

    # import también debe funcionar y atributos arbitrarios devolver callables
    import wandb
    assert wandb.__spec__ is not None
    assert callable(wandb.init)  # type: ignore[attr-defined]
    assert callable(wandb.log)   # type: ignore[attr-defined]


def test_speak_last_wav_passthrough(client):
    """Pedir wav devuelve el archivo cacheado."""
    import os
    import tempfile

    import server
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    tmp.write(_dummy_wav_bytes()); tmp.close()
    server._last_speak_path = tmp.name
    try:
        r = client.get("/api/speak/last?format=wav")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("audio/wav")
    finally:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)
        server._last_speak_path = None
