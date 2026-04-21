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
