"""
ChatVoice - Capa de persistencia SQLite.
Gestiona configuración, voces, logs, presets y frases guardadas.
"""
import logging
import os
import sys
import sqlite3
import shutil
from pathlib import Path

_log = logging.getLogger("chatvoice.db")


# ── Rutas de datos ────────────────────────────────────────────────────────────

_app_data_dir: Path | None = None
_voices_dir:   Path | None = None
_piper_dir:    Path | None = None


def get_app_data_dir() -> Path:
    global _app_data_dir
    if _app_data_dir is None:
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", Path.home()))
        else:
            base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        _app_data_dir = base / "ChatVoice"
        _app_data_dir.mkdir(parents=True, exist_ok=True)
    return _app_data_dir


def get_voices_dir() -> Path:
    global _voices_dir
    if _voices_dir is None:
        _voices_dir = get_app_data_dir() / "voices"
        _voices_dir.mkdir(parents=True, exist_ok=True)
    return _voices_dir


def get_piper_dir() -> Path:
    global _piper_dir
    if _piper_dir is None:
        _piper_dir = get_app_data_dir() / "piper_voices"
        _piper_dir.mkdir(parents=True, exist_ok=True)
    return _piper_dir


def get_db_path() -> Path:
    return get_app_data_dir() / "chatvoice.db"


def get_static_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "static"
    return Path(__file__).parent / "static"


# ── Conexión ──────────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(get_db_path(), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys = ON")
    return c


# ── Esquema y defaults ────────────────────────────────────────────────────────

_DEFAULT_CONFIG: dict[str, str] = {
    "active_voice":       "",
    "voice_type":         "wav",
    "language":           "es",
    "radio_effect":       "false",
    "speed":              "1.0",
    "pitch":              "0.0",
    "engine":             "xtts",
    "piper_active_voice": "",
    "piper_speaker_id":   "0",
    "audio_device":       "",
}

_LOG_MAX_ROWS  = 600_000
_LOG_TRIM_ROWS = 1_000


def init_db() -> None:
    """Crea tablas si no existen y aplica migraciones legacy."""
    with _conn() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS voices (
                name       TEXT PRIMARY KEY,
                filename   TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS logs (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                ts      TEXT    NOT NULL DEFAULT (datetime('now')),
                level   TEXT    NOT NULL DEFAULT 'INFO',
                message TEXT    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS presets (
                name             TEXT PRIMARY KEY,
                engine           TEXT NOT NULL DEFAULT 'xtts',
                voice            TEXT,
                voice_type       TEXT,
                speed            REAL NOT NULL DEFAULT 1.0,
                pitch            REAL NOT NULL DEFAULT 0.0,
                language         TEXT NOT NULL DEFAULT 'es',
                radio_effect     TEXT NOT NULL DEFAULT 'false',
                piper_voice      TEXT,
                piper_speaker_id INTEGER DEFAULT 0,
                created_at       TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS phrases (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                label       TEXT NOT NULL,
                text        TEXT NOT NULL,
                preset_name TEXT REFERENCES presets(name) ON DELETE SET NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)

    with _conn() as db:
        if db.execute("SELECT COUNT(*) FROM config").fetchone()[0] == 0:
            db.executemany(
                "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
                _DEFAULT_CONFIG.items(),
            )
        else:
            # Insertar claves nuevas que aún no existan
            for k, v in _DEFAULT_CONFIG.items():
                db.execute(
                    "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (k, v)
                )

    _migrate_json_config()


# ── Migraciones ───────────────────────────────────────────────────────────────

def _migrate_json_config() -> None:
    import json
    with _conn() as db:
        if db.execute(
            "SELECT value FROM config WHERE key = '_migrated_json'"
        ).fetchone():
            return

    candidates = [Path(__file__).parent / "config.json"]
    if getattr(sys, "frozen", False):
        candidates.insert(0, Path(sys.executable).parent / "config.json")

    for json_path in candidates:
        if json_path.exists():
            try:
                with open(json_path, encoding="utf-8") as f:
                    data = json.load(f)
                save_config({
                    "active_voice": data.get("active_voice") or "",
                    "voice_type":   data.get("voice_type", "wav"),
                    "language":     data.get("language", "es"),
                    "radio_effect": data.get("radio_effect", False),
                })
                _log.info(f"Migrado config.json → SQLite desde {json_path}")
            except Exception as e:
                _log.warning(f"No se pudo migrar config.json: {e}")
            break

    with _conn() as db:
        db.execute(
            "INSERT OR IGNORE INTO config (key, value) VALUES ('_migrated_json', '1')"
        )


def migrate_local_voices(local_dir: Path) -> int:
    with _conn() as db:
        if db.execute(
            "SELECT value FROM config WHERE key = '_migrated_voices'"
        ).fetchone():
            return 0

    count = 0
    if local_dir.exists():
        dest = get_voices_dir()
        for wav in local_dir.glob("*.wav"):
            target = dest / wav.name
            if not target.exists():
                shutil.copy2(wav, target)
                register_voice(wav.stem, wav.name)
                count += 1
        if count:
            _log.info(f"Migradas {count} voz/voces de '{local_dir}' a '{dest}'")

    with _conn() as db:
        db.execute(
            "INSERT OR IGNORE INTO config (key, value) VALUES ('_migrated_voices', '1')"
        )
    return count


# ── Config ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    with _conn() as db:
        rows = db.execute(
            "SELECT key, value FROM config WHERE key NOT LIKE '\\_%' ESCAPE '\\'"
        ).fetchall()
    cfg: dict = {row["key"]: row["value"] for row in rows}
    for k, v in _DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    cfg["radio_effect"]       = cfg.get("radio_effect", "false").lower() == "true"
    cfg["active_voice"]       = cfg.get("active_voice") or None
    cfg["speed"]              = float(cfg.get("speed", "1.0"))
    cfg["pitch"]              = float(cfg.get("pitch", "0.0"))
    cfg["engine"]             = cfg.get("engine", "xtts")
    cfg["piper_active_voice"] = cfg.get("piper_active_voice") or None
    cfg["audio_device"]       = cfg.get("audio_device", "")
    try:
        cfg["piper_speaker_id"] = int(cfg.get("piper_speaker_id", "0"))
    except (ValueError, TypeError):
        cfg["piper_speaker_id"] = 0
    return cfg


def save_config(cfg: dict) -> None:
    rows = [
        ("active_voice",       cfg.get("active_voice") or ""),
        ("voice_type",         cfg.get("voice_type", "wav")),
        ("language",           cfg.get("language", "es")),
        ("radio_effect",       "true" if cfg.get("radio_effect") else "false"),
        ("speed",              str(round(float(cfg.get("speed", 1.0)), 2))),
        ("pitch",              str(round(float(cfg.get("pitch", 0.0)), 1))),
        ("engine",             cfg.get("engine", "xtts")),
        ("piper_active_voice", cfg.get("piper_active_voice") or ""),
        ("piper_speaker_id",   str(int(cfg.get("piper_speaker_id", 0)))),
        ("audio_device",       cfg.get("audio_device", "")),
    ]
    with _conn() as db:
        db.executemany(
            """INSERT INTO config (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            rows,
        )


# ── Voces ─────────────────────────────────────────────────────────────────────

def register_voice(name: str, filename: str) -> None:
    with _conn() as db:
        db.execute(
            """INSERT INTO voices (name, filename) VALUES (?, ?)
               ON CONFLICT(name) DO UPDATE SET filename = excluded.filename""",
            (name, filename),
        )


def remove_voice(name: str) -> None:
    with _conn() as db:
        db.execute("DELETE FROM voices WHERE name = ?", (name,))


# ── Logs ──────────────────────────────────────────────────────────────────────

def log_event(level: str, message: str) -> None:
    """Inserta un evento en la tabla logs y aplica rotación si supera el límite."""
    with _conn() as db:
        db.execute(
            "INSERT INTO logs (level, message) VALUES (?, ?)",
            (level.upper(), message),
        )
        count = db.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
        if count > _LOG_MAX_ROWS:
            db.execute(
                "DELETE FROM logs WHERE id IN "
                "(SELECT id FROM logs ORDER BY id ASC LIMIT ?)",
                (_LOG_TRIM_ROWS,),
            )


def get_logs(limit: int = 200, offset: int = 0, level: str = None) -> list[dict]:
    with _conn() as db:
        if level:
            rows = db.execute(
                "SELECT id, ts, level, message FROM logs WHERE level = ? "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (level.upper(), limit, offset),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT id, ts, level, message FROM logs "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
    return [dict(r) for r in rows]


def clear_logs() -> None:
    with _conn() as db:
        db.execute("DELETE FROM logs")


# ── Presets ───────────────────────────────────────────────────────────────────

def list_presets() -> list[dict]:
    with _conn() as db:
        rows = db.execute(
            "SELECT * FROM presets ORDER BY name COLLATE NOCASE"
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["radio_effect"] = d.get("radio_effect", "false").lower() == "true"
        result.append(d)
    return result


def save_preset(name: str, cfg: dict) -> None:
    with _conn() as db:
        db.execute(
            """INSERT INTO presets
               (name, engine, voice, voice_type, speed, pitch, language,
                radio_effect, piper_voice, piper_speaker_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                 engine           = excluded.engine,
                 voice            = excluded.voice,
                 voice_type       = excluded.voice_type,
                 speed            = excluded.speed,
                 pitch            = excluded.pitch,
                 language         = excluded.language,
                 radio_effect     = excluded.radio_effect,
                 piper_voice      = excluded.piper_voice,
                 piper_speaker_id = excluded.piper_speaker_id""",
            (
                name,
                cfg.get("engine", "xtts"),
                cfg.get("active_voice") or cfg.get("voice"),
                cfg.get("voice_type", "wav"),
                round(float(cfg.get("speed", 1.0)), 2),
                round(float(cfg.get("pitch", 0.0)), 1),
                cfg.get("language", "es"),
                "true" if cfg.get("radio_effect") else "false",
                cfg.get("piper_active_voice") or cfg.get("piper_voice"),
                int(cfg.get("piper_speaker_id", 0)),
            ),
        )


def load_preset(name: str) -> dict | None:
    with _conn() as db:
        row = db.execute(
            "SELECT * FROM presets WHERE name = ?", (name,)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["radio_effect"] = d.get("radio_effect", "false").lower() == "true"
    return d


def delete_preset(name: str) -> None:
    with _conn() as db:
        db.execute("DELETE FROM presets WHERE name = ?", (name,))


# ── Frases ────────────────────────────────────────────────────────────────────

def list_phrases() -> list[dict]:
    with _conn() as db:
        rows = db.execute(
            "SELECT id, label, text, preset_name, created_at "
            "FROM phrases ORDER BY id ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def save_phrase(label: str, text: str, preset_name: str | None) -> int:
    with _conn() as db:
        cur = db.execute(
            "INSERT INTO phrases (label, text, preset_name) VALUES (?, ?, ?)",
            (label, text, preset_name or None),
        )
        return cur.lastrowid


def update_phrase(phrase_id: int, label: str, text: str, preset_name: str | None) -> None:
    with _conn() as db:
        db.execute(
            "UPDATE phrases SET label = ?, text = ?, preset_name = ? WHERE id = ?",
            (label, text, preset_name or None, phrase_id),
        )


def delete_phrase(phrase_id: int) -> None:
    with _conn() as db:
        db.execute("DELETE FROM phrases WHERE id = ?", (phrase_id,))


def get_phrase(phrase_id: int) -> dict | None:
    with _conn() as db:
        row = db.execute(
            "SELECT id, label, text, preset_name FROM phrases WHERE id = ?",
            (phrase_id,),
        ).fetchone()
    return dict(row) if row else None
