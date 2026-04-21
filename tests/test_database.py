import sqlite3
import pytest
import database as db


# ── Config ────────────────────────────────────────────────────────────────────

def test_load_config_defaults(tmp_db):
    cfg = db.load_config()
    assert cfg["language"] == "es"


def test_save_and_load_config(tmp_db):
    db.save_config({"language": "en"})
    assert db.load_config()["language"] == "en"


# ── Voices ────────────────────────────────────────────────────────────────────

def test_add_voice_returns_id(tmp_db):
    vid = db.add_voice("xtts", "Voz Test", "test.wav")
    assert isinstance(vid, int) and vid > 0


def test_add_voice_duplicate_name_raises(tmp_db):
    db.add_voice("xtts", "Duplicada", "a.wav")
    with pytest.raises(sqlite3.IntegrityError):
        db.add_voice("xtts", "Duplicada", "b.wav")


def test_get_voice(tmp_db):
    vid = db.add_voice("xtts", "Test", "test.wav")
    v = db.get_voice(vid)
    assert v is not None
    assert v["name"] == "Test"
    assert v["engine"] == "xtts"
    assert v["filename"] == "test.wav"


def test_get_voice_not_found(tmp_db):
    assert db.get_voice(9999) is None


def test_list_voices_empty(tmp_db):
    assert db.list_voices() == []


def test_list_voices_filter_engine(tmp_db):
    db.add_voice("xtts",  "VozXTTS",  "x.wav")
    db.add_voice("piper", "VozPiper", "p.onnx")
    xtts  = db.list_voices(engine="xtts")
    piper = db.list_voices(engine="piper")
    assert len(xtts) == 1 and xtts[0]["engine"] == "xtts"
    assert len(piper) == 1 and piper[0]["engine"] == "piper"


def test_rename_voice(tmp_db):
    vid = db.add_voice("xtts", "Original", "orig.wav")
    db.rename_voice(vid, "Renombrada")
    assert db.get_voice(vid)["name"] == "Renombrada"


def test_remove_voice(tmp_db):
    vid = db.add_voice("xtts", "Borrar", "del.wav")
    db.remove_voice(vid)
    assert db.get_voice(vid) is None


def test_remove_voice_cascades_preset(tmp_db):
    vid = db.add_voice("xtts", "VozCascade", "c.wav")
    db.save_voice_preset("PresetCascade", vid, 1.0, 0.0, False)
    db.remove_voice(vid)
    assert db.load_voice_preset("PresetCascade") is None


# ── Voice Presets ─────────────────────────────────────────────────────────────

def _voice(name="VozBase"):
    return db.add_voice("xtts", name, f"{name}.wav")


def test_save_preset_basic(tmp_db):
    vid = _voice()
    db.save_voice_preset("MiPreset", vid, 1.0, 0.0, False)
    p = db.load_voice_preset("MiPreset")
    assert p is not None
    assert p["name"] == "MiPreset"
    assert p["voice_id"] == vid


def test_preset_upsert(tmp_db):
    vid = _voice()
    db.save_voice_preset("Upsert", vid, 1.0, 0.0, False)
    db.save_voice_preset("Upsert", vid, 1.5, 2.0, True)
    p = db.load_voice_preset("Upsert")
    assert p["speed"] == 1.5
    assert p["pitch"] == 2.0
    assert p["radio_effect"] is True


def test_preset_radio_effect_bool(tmp_db):
    vid = _voice()
    db.save_voice_preset("Radio", vid, 1.0, 0.0, True)
    assert db.load_voice_preset("Radio")["radio_effect"] is True
    db.save_voice_preset("Radio", vid, 1.0, 0.0, False)
    assert db.load_voice_preset("Radio")["radio_effect"] is False


def test_preset_speed_rounded(tmp_db):
    vid = _voice()
    db.save_voice_preset("SpeedTest", vid, 1.234, 0.0, False)
    assert db.load_voice_preset("SpeedTest")["speed"] == 1.23


def test_preset_pitch_rounded(tmp_db):
    vid = _voice()
    db.save_voice_preset("PitchTest", vid, 1.0, 1.26, False)
    assert db.load_voice_preset("PitchTest")["pitch"] == 1.3


def test_list_presets_join(tmp_db):
    vid = db.add_voice("piper", "VozPiper", "model.onnx")
    db.save_voice_preset("JoinPreset", vid, 1.0, 0.0, False)
    presets = db.list_voice_presets()
    assert len(presets) == 1
    p = presets[0]
    assert p["voice_name"] == "VozPiper"
    assert p["engine"] == "piper"


def test_delete_preset(tmp_db):
    vid = _voice()
    db.save_voice_preset("Borrar", vid, 1.0, 0.0, False)
    db.delete_voice_preset("Borrar")
    assert db.load_voice_preset("Borrar") is None


def test_delete_voice_cascades_preset(tmp_db):
    vid = _voice("VozParaBorrar")
    db.save_voice_preset("PresetVoz", vid, 1.0, 0.0, False)
    db.remove_voice(vid)
    assert db.load_voice_preset("PresetVoz") is None


# ── Phrases ───────────────────────────────────────────────────────────────────

def test_save_phrase_returns_id(tmp_db):
    pid = db.save_phrase("Saludo", "Hola mundo", None)
    assert isinstance(pid, int) and pid > 0


def test_save_phrase_duplicate_name_raises(tmp_db):
    db.save_phrase("Duplicada", "Texto 1", None)
    with pytest.raises(sqlite3.IntegrityError):
        db.save_phrase("Duplicada", "Texto 2", None)


def test_get_phrase_by_name(tmp_db):
    db.save_phrase("BuscarNombre", "Texto", None)
    p = db.get_phrase_by_name("BuscarNombre")
    assert p is not None
    assert p["text"] == "Texto"


def test_get_phrase_not_found(tmp_db):
    assert db.get_phrase(9999) is None
    assert db.get_phrase_by_name("NoExiste") is None


def test_update_phrase(tmp_db):
    pid = db.save_phrase("Actualizar", "Original", None)
    db.update_phrase(pid, "Actualizada", "Nuevo texto", None)
    p = db.get_phrase(pid)
    assert p["name"] == "Actualizada"
    assert p["text"] == "Nuevo texto"


def test_delete_phrase(tmp_db):
    pid = db.save_phrase("Borrar", "Texto", None)
    db.delete_phrase(pid)
    assert db.get_phrase(pid) is None


def test_delete_preset_nullifies_phrase(tmp_db):
    vid = _voice()
    db.save_voice_preset("PresetFrase", vid, 1.0, 0.0, False)
    db.save_phrase("FraseConPreset", "Texto", "PresetFrase")
    db.delete_voice_preset("PresetFrase")
    p = db.get_phrase_by_name("FraseConPreset")
    assert p["voice_preset_name"] is None


def test_list_phrases_order(tmp_db):
    db.save_phrase("Frase B", "Texto B", None)
    db.save_phrase("Frase A", "Texto A", None)
    phrases = db.list_phrases()
    assert len(phrases) == 2
    assert phrases[0]["id"] < phrases[1]["id"]


# ── Logs ──────────────────────────────────────────────────────────────────────

def test_log_event_and_get(tmp_db):
    db.log_event("INFO", "Mensaje de prueba")
    logs = db.get_logs(limit=10)
    assert any(l["message"] == "Mensaje de prueba" for l in logs)


def test_get_logs_filter_level(tmp_db):
    db.log_event("INFO",  "Info msg")
    db.log_event("ERROR", "Error msg")
    errors = db.get_logs(level="ERROR")
    assert all(l["level"] == "ERROR" for l in errors)
    assert any(l["message"] == "Error msg" for l in errors)


def test_clear_logs(tmp_db):
    db.log_event("INFO", "Antes de limpiar")
    db.clear_logs()
    assert db.get_logs() == []
