import os
import sys
import pytest

# Must be set before any import of server.py to skip TTS model loading
os.environ["SKIP_MODEL_LOAD"] = "1"

# Ensure project root is on sys.path so `import database` and `import server` work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Isolated SQLite DB in a temp directory for each test."""
    # Reset cached path globals so init_db() uses the tmp_path
    monkeypatch.setattr(database, "_app_data_dir", None)
    monkeypatch.setattr(database, "_voices_dir", None)
    monkeypatch.setattr(database, "_piper_dir", None)
    monkeypatch.setattr(
        database,
        "get_app_data_dir",
        lambda: _mk(tmp_path / "MyVoices"),
    )
    database.init_db()
    yield tmp_path / "MyVoices"
    # Cleanup: reset globals so next test starts fresh
    database._app_data_dir = None
    database._voices_dir   = None
    database._piper_dir    = None


def _mk(p):
    p.mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture()
def client(tmp_db, monkeypatch):
    """FastAPI TestClient with isolated DB and no TTS model loaded."""
    import server
    from starlette.testclient import TestClient

    # Point server's cached directory globals to the temp path
    monkeypatch.setattr(server, "VOICES_DIR", tmp_db / "voices")
    monkeypatch.setattr(server, "PIPER_DIR",  tmp_db / "piper_voices")
    (tmp_db / "voices").mkdir(exist_ok=True)
    (tmp_db / "piper_voices").mkdir(exist_ok=True)

    with TestClient(server.app) as c:
        yield c
