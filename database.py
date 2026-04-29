"""
MyVoices — Capa de persistencia SQLite.
Gestiona configuración, voces (XTTS + Piper), presets de voz, frases y logs.
"""
import logging
import os
import shutil
import sqlite3
import sys
from pathlib import Path

_log = logging.getLogger("myvoices.db")


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
        _app_data_dir = base / "MyVoices"
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
    return get_app_data_dir() / "myvoices.db"


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


# ── Configuración por defecto ─────────────────────────────────────────────────

_DEFAULT_CONFIG: dict[str, str] = {
    "language":    "es",
    "mcp_enabled": "false",  # MCP HTTP endpoint disabled by default
    "mcp_token":   "",       # Bearer token, generated on first enable
}

_LOG_MAX_ROWS  = 600_000
_LOG_TRIM_ROWS = 1_000


# ── Inicialización ────────────────────────────────────────────────────────────

def init_db() -> None:
    """
    Crea la base de datos nueva si no existe.
    Si detecta una DB legacy (tabla 'presets' del esquema anterior),
    hace backup y arranca limpio.
    """
    db_path = get_db_path()

    # Migrar ficheros WAV del directorio legacy ChatVoice
    _migrate_old_appdata()

    # Si existe nuestra DB pero con el schema viejo → backup + reset
    if db_path.exists():
        try:
            with sqlite3.connect(db_path) as chk:
                tables = {r[0] for r in chk.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()}
            if "presets" in tables or (
                "voices" in tables and "voice_presets" not in tables
            ):
                backup = db_path.with_name("myvoices_backup.db")
                shutil.copy2(db_path, backup)
                db_path.unlink()
                _log.info(f"DB legacy detectada → backup en {backup}")
        except Exception as e:
            _log.warning(f"No se pudo comprobar schema legacy: {e}")

    with _conn() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS voices (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                engine     TEXT NOT NULL,
                name       TEXT NOT NULL UNIQUE,
                filename   TEXT,
                speaker_id INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS voice_presets (
                name         TEXT PRIMARY KEY,
                voice_id     INTEGER NOT NULL REFERENCES voices(id) ON DELETE CASCADE,
                speed        REAL NOT NULL DEFAULT 1.0,
                pitch        REAL NOT NULL DEFAULT 0.0,
                radio_effect TEXT NOT NULL DEFAULT 'false',
                language     TEXT NOT NULL DEFAULT 'es',
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS phrases (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                name              TEXT NOT NULL UNIQUE,
                text              TEXT NOT NULL,
                voice_preset_name TEXT REFERENCES voice_presets(name) ON DELETE SET NULL,
                created_at        TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS logs (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                ts      TEXT NOT NULL DEFAULT (datetime('now')),
                level   TEXT NOT NULL DEFAULT 'INFO',
                message TEXT NOT NULL
            );
        """)

        for k, v in _DEFAULT_CONFIG.items():
            db.execute(
                "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (k, v)
            )

    # Migration: add language column to voice_presets if it was created without it
    try:
        with _conn() as db:
            db.execute(
                "ALTER TABLE voice_presets ADD COLUMN language TEXT NOT NULL DEFAULT 'es'"
            )
    except sqlite3.OperationalError:
        pass  # column already exists


def _migrate_old_appdata() -> None:
    """Copia voces WAV del directorio legacy %APPDATA%/ChatVoice si existen."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    old_voices = base / "ChatVoice" / "voices"
    new_voices  = get_voices_dir()

    if old_voices.exists():
        copied = 0
        for wav in old_voices.glob("*.wav"):
            dest = new_voices / wav.name
            if not dest.exists():
                shutil.copy2(wav, dest)
                copied += 1
        if copied:
            _log.info(f"Migradas {copied} voces WAV desde {old_voices}")


# ── Config ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    with _conn() as db:
        rows = db.execute("SELECT key, value FROM config").fetchall()
    cfg = {row["key"]: row["value"] for row in rows}
    for k, v in _DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg


def save_config(cfg: dict) -> None:
    rows = []
    for k in _DEFAULT_CONFIG:
        if k not in cfg:
            continue
        v = cfg[k]
        if isinstance(v, bool):
            v = "true" if v else "false"
        rows.append((k, str(v)))
    with _conn() as db:
        db.executemany(
            "INSERT INTO config (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            rows,
        )


# ── Voces ─────────────────────────────────────────────────────────────────────

def list_voices(engine: str | None = None) -> list[dict]:
    with _conn() as db:
        if engine:
            rows = db.execute(
                "SELECT id, engine, name, filename, speaker_id, created_at "
                "FROM voices WHERE engine = ? ORDER BY id ASC",
                (engine,),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT id, engine, name, filename, speaker_id, created_at "
                "FROM voices ORDER BY engine ASC, id ASC"
            ).fetchall()
    return [dict(r) for r in rows]


def get_voice(voice_id: int) -> dict | None:
    with _conn() as db:
        row = db.execute(
            "SELECT id, engine, name, filename, speaker_id, created_at "
            "FROM voices WHERE id = ?",
            (voice_id,),
        ).fetchone()
    return dict(row) if row else None


def add_voice(engine: str, name: str, filename: str, speaker_id: int = 0) -> int:
    with _conn() as db:
        cur = db.execute(
            "INSERT INTO voices (engine, name, filename, speaker_id) VALUES (?, ?, ?, ?)",
            (engine, name, filename, speaker_id),
        )
        return cur.lastrowid


def rename_voice(voice_id: int, new_name: str) -> None:
    with _conn() as db:
        db.execute("UPDATE voices SET name = ? WHERE id = ?", (new_name, voice_id))


def remove_voice(voice_id: int) -> None:
    with _conn() as db:
        db.execute("DELETE FROM voices WHERE id = ?", (voice_id,))


# ── Presets de voz ────────────────────────────────────────────────────────────

def list_voice_presets() -> list[dict]:
    with _conn() as db:
        rows = db.execute(
            """SELECT vp.name, vp.voice_id, v.name AS voice_name, v.engine,
                      v.filename, v.speaker_id,
                      vp.speed, vp.pitch, vp.radio_effect, vp.language, vp.created_at
               FROM voice_presets vp
               JOIN voices v ON v.id = vp.voice_id
               ORDER BY vp.name COLLATE NOCASE"""
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["radio_effect"] = d.get("radio_effect", "false").lower() == "true"
        d.setdefault("language", "es")
        result.append(d)
    return result


def save_voice_preset(name: str, voice_id: int, speed: float,
                      pitch: float, radio_effect: bool, language: str = "es") -> None:
    with _conn() as db:
        db.execute(
            """INSERT INTO voice_presets (name, voice_id, speed, pitch, radio_effect, language)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                 voice_id     = excluded.voice_id,
                 speed        = excluded.speed,
                 pitch        = excluded.pitch,
                 radio_effect = excluded.radio_effect,
                 language     = excluded.language""",
            (name, voice_id,
             round(float(speed), 2),
             round(float(pitch), 1),
             "true" if radio_effect else "false",
             language or "es"),
        )


def load_voice_preset(name: str) -> dict | None:
    with _conn() as db:
        row = db.execute(
            """SELECT vp.name, vp.voice_id, v.name AS voice_name, v.engine,
                      v.filename, v.speaker_id,
                      vp.speed, vp.pitch, vp.radio_effect, vp.language, vp.created_at
               FROM voice_presets vp
               JOIN voices v ON v.id = vp.voice_id
               WHERE vp.name = ?""",
            (name,),
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["radio_effect"] = d.get("radio_effect", "false").lower() == "true"
    d.setdefault("language", "es")
    return d


def delete_voice_preset(name: str) -> None:
    with _conn() as db:
        db.execute("DELETE FROM voice_presets WHERE name = ?", (name,))


# ── Frases ────────────────────────────────────────────────────────────────────

def list_phrases() -> list[dict]:
    with _conn() as db:
        rows = db.execute(
            "SELECT id, name, text, voice_preset_name, created_at "
            "FROM phrases ORDER BY id ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def save_phrase(name: str, text: str, voice_preset_name: str | None) -> int:
    with _conn() as db:
        cur = db.execute(
            """INSERT INTO phrases (name, text, voice_preset_name) VALUES (?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                 text              = excluded.text,
                 voice_preset_name = excluded.voice_preset_name""",
            (name, text, voice_preset_name or None),
        )
        return cur.lastrowid or db.execute(
            "SELECT id FROM phrases WHERE name = ?", (name,)
        ).fetchone()[0]


def update_phrase(phrase_id: int, name: str, text: str,
                  voice_preset_name: str | None) -> None:
    with _conn() as db:
        db.execute(
            "UPDATE phrases SET name = ?, text = ?, voice_preset_name = ? WHERE id = ?",
            (name, text, voice_preset_name or None, phrase_id),
        )


def delete_phrase(phrase_id: int) -> None:
    with _conn() as db:
        db.execute("DELETE FROM phrases WHERE id = ?", (phrase_id,))


def get_phrase(phrase_id: int) -> dict | None:
    with _conn() as db:
        row = db.execute(
            "SELECT id, name, text, voice_preset_name FROM phrases WHERE id = ?",
            (phrase_id,),
        ).fetchone()
    return dict(row) if row else None


def get_phrase_by_name(name: str) -> dict | None:
    with _conn() as db:
        row = db.execute(
            "SELECT id, name, text, voice_preset_name FROM phrases WHERE name = ?",
            (name,),
        ).fetchone()
    return dict(row) if row else None


# ── Logs ──────────────────────────────────────────────────────────────────────

def log_event(level: str, message: str) -> None:
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


def get_logs(limit: int = 200, offset: int = 0,
             level: str | None = None) -> list[dict]:
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
