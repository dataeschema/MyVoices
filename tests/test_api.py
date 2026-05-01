import io
import wave

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
