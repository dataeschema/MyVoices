import os
import sys
import types


# ── Workaround: llvmlite.dll bloqueado por Windows App Control ────────────────
def _mock_numba_and_llvmlite():
    def _noop(*args, **kwargs):
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]
        return lambda fn: fn

    class _AutoMod(types.ModuleType):
        def __init__(self, name):
            super().__init__(name)
            self.__dict__['__file__']    = None
            self.__dict__['__path__']    = []
            self.__dict__['__spec__']    = None
            self.__dict__['__loader__']  = None
            self.__dict__['__package__'] = name.split('.')[0]
        def __getattr__(self, name):
            return _noop

    numba             = _AutoMod('numba')
    numba.jit         = _noop
    numba.njit        = _noop
    numba.stencil     = _noop
    numba.vectorize   = _noop
    numba.guvectorize = _noop
    numba.prange      = range
    numba.typed       = _AutoMod('numba.typed')
    numba.core        = _AutoMod('numba.core')

    for mod_name, mod in {
        'numba':                  numba,
        'numba.core':             numba.core,
        'numba.core.config':      _AutoMod('numba.core.config'),
        'numba.core.types':       _AutoMod('numba.core.types'),
        'numba.typed':            numba.typed,
        'numba.np':               _AutoMod('numba.np'),
        'numba.np.numpy_support': _AutoMod('numba.np.numpy_support'),
        'llvmlite':               _AutoMod('llvmlite'),
        'llvmlite.binding':       _AutoMod('llvmlite.binding'),
    }.items():
        sys.modules[mod_name] = mod

_mock_numba_and_llvmlite()


def _shim_transformers_beam_search():
    """BeamSearchScorer fue eliminado en transformers 5.x.
    TTS==0.22.0 lo importa en stream_generator.py pero solo lo usa en rutas de
    beam search que no se invocan durante tts_to_file(). Inyectamos clases dummy
    para que el import no falle."""
    try:
        import transformers as _tr
        if not hasattr(_tr, "BeamSearchScorer"):
            class _BeamSearchScorer:
                pass
            class _ConstrainedBeamSearchScorer:
                pass
            _tr.BeamSearchScorer             = _BeamSearchScorer
            _tr.ConstrainedBeamSearchScorer  = _ConstrainedBeamSearchScorer
    except Exception:
        pass

_shim_transformers_beam_search()

if getattr(sys, "frozen", False):
    # console=False → stdin/stdout/stderr son None; TTS llama input() para los ToS.
    import builtins
    import io
    if sys.stdin  is None: sys.stdin  = io.StringIO("y\n")
    if sys.stdout is None: sys.stdout = io.StringIO()
    if sys.stderr is None: sys.stderr = io.StringIO()
    builtins.input = lambda prompt="": "y"

    _torch_lib = os.path.join(sys._MEIPASS, "torch", "lib")
    if os.path.isdir(_torch_lib):
        try:
            os.add_dll_directory(_torch_lib)
        except Exception:
            pass
        os.environ["PATH"] = _torch_lib + os.pathsep + os.environ.get("PATH", "")

import asyncio
import json
import logging
import urllib.request
import wave as wave_module

import torch
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.background import BackgroundTask

_log = logging.getLogger("myvoices")

from database import (
    add_voice,
    add_webhook,
    clear_logs,
    delete_phrase,
    delete_voice_preset,
    delete_webhook,
    get_active_webhooks,
    get_logs,
    get_phrase,
    get_phrase_by_name,
    get_piper_dir,
    get_static_dir,
    get_voice,
    get_voices_dir,
    init_db,
    list_phrases,
    list_voice_presets,
    list_voices,
    list_webhooks,
    load_config,
    load_voice_preset,
    log_event,
    remove_voice,
    rename_voice,
    save_config,
    save_phrase,
    save_voice_preset,
    update_phrase,
)

# ── Soporte Piper TTS ─────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    _espeak_data = os.path.join(sys._MEIPASS, "piper_phonemize", "espeak-ng-data")
    if os.path.isdir(_espeak_data):
        os.environ.setdefault("ESPEAK_DATA_PATH", _espeak_data)

try:
    from piper import PiperVoice
    from piper.voice import SynthesisConfig as PiperSynthConfig
    PIPER_AVAILABLE = True
except Exception:
    PIPER_AVAILABLE = False

# ── Compatibilidad torch.load ─────────────────────────────────────────────────
_torch_load_orig = torch.load
def _torch_load_compat(*args, **kwargs):
    kwargs.setdefault("weights_only", False)
    return _torch_load_orig(*args, **kwargs)
torch.load = _torch_load_compat

# ── Compatibilidad torchaudio ─────────────────────────────────────────────────
import torchaudio as _ta

try:
    _ta.set_audio_backend("soundfile")
except Exception:
    pass

def _load_audio_compat(uri, frame_offset=0, num_frames=-1,
                       normalize=True, channels_first=True, format=None, **_kw):
    try:
        import soundfile as _sf
        data, sr = _sf.read(str(uri), dtype="float32", always_2d=True,
                            start=frame_offset,
                            frames=num_frames if num_frames > 0 else -1)
        return torch.from_numpy(data.T.copy()), int(sr)
    except Exception:
        pass
    import numpy as _np
    from scipy.io import wavfile as _swav
    sr, data = _swav.read(str(uri))
    if data.dtype == _np.int16:
        data = data.astype(_np.float32) / 32768.0
    elif data.dtype == _np.int32:
        data = data.astype(_np.float32) / 2147483648.0
    else:
        data = data.astype(_np.float32)
    if data.ndim == 1:
        data = data.reshape(1, -1)
    else:
        data = data.T
    if frame_offset > 0:
        data = data[:, frame_offset:]
    if num_frames > 0:
        data = data[:, :num_frames]
    return torch.from_numpy(data.copy()), int(sr)

_ta.load = _load_audio_compat
try:
    import torchaudio._backend as _tba
    _tba.load = _load_audio_compat
except Exception:
    pass
try:
    import torchaudio._backend.utils as _tba_utils
    _tba_utils.load_with_torchcodec = _load_audio_compat
except Exception:
    pass

import queue
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
import pygame
from scipy import signal as scipy_signal
from scipy.io import wavfile as scipy_wavfile
from TTS.api import TTS

# ── F5-TTS y Chatterbox: importar DESPUÉS de los parches de torchaudio ───────
# f5_tts.api causa segfault si torchaudio no está parcheado primero.

_F5TTS_IMPORT_ERROR     = ""
_CHATTERBOX_IMPORT_ERROR = ""

try:
    from f5_tts.api import F5TTS
    F5TTS_AVAILABLE = True
except Exception as _e:
    import traceback as _tb_f5
    F5TTS_AVAILABLE = False
    _F5TTS_IMPORT_ERROR = f"{type(_e).__name__}: {_e}\n{_tb_f5.format_exc()}"

try:
    from chatterbox.tts import ChatterboxTTS
    CHATTERBOX_AVAILABLE = True
except Exception as _e:
    import traceback as _tb_cb
    CHATTERBOX_AVAILABLE = False
    _CHATTERBOX_IMPORT_ERROR = f"{type(_e).__name__}: {_e}\n{_tb_cb.format_exc()}"


# ── Logging handler → SQLite ──────────────────────────────────────────────────
# Modo verbose: env MYVOICES_VERBOSE=1 o config DB key "verbose"=true.
# En verbose: nivel DEBUG y se incluye exc_info en el mensaje.

def _verbose_enabled() -> bool:
    if os.getenv("MYVOICES_VERBOSE", "").lower() in ("1", "true", "yes"):
        return True
    try:
        return load_config().get("verbose", "false").lower() == "true"
    except Exception:
        return False

VERBOSE = _verbose_enabled()


class _DBLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            if record.exc_info:
                import traceback as _tb
                msg += "\n" + "".join(_tb.format_exception(*record.exc_info))
            log_event(record.levelname, msg)
        except Exception:
            pass

_db_handler = _DBLogHandler()
_db_handler.setLevel(logging.DEBUG if VERBOSE else logging.INFO)
_db_handler.setFormatter(logging.Formatter("%(name)s — %(message)s"))

logging.getLogger().addHandler(_db_handler)
logging.getLogger().setLevel(logging.DEBUG if VERBOSE else logging.INFO)
if VERBOSE:
    logging.getLogger("myvoices").info("VERBOSE mode enabled (DEBUG level + tracebacks)")

class _SilenceProactorReset(logging.Filter):
    """Silencia el traceback ConnectionResetError de _ProactorBasePipeTransport
    que asyncio en Windows emite cuando un cliente MCP cierra el stream SSE.
    Es ruido cosmético: la sesión MCP funciona, solo molesta en el visor."""
    def filter(self, record: logging.LogRecord) -> bool:
        if "_ProactorBasePipeTransport._call_connection_lost" not in record.getMessage():
            return True
        exc = record.exc_info
        if exc and exc[0] is ConnectionResetError:
            return False
        return "ConnectionResetError" not in (record.exc_text or "")

logging.getLogger("asyncio").addFilter(_SilenceProactorReset())

_uv_access = logging.getLogger("uvicorn.access")
if not _uv_access.propagate:
    _uv_access.addHandler(_db_handler)

# ── Inicialización (antes de crear el app para que el lifespan vea la config)
init_db()

# ── MCP embebido (HTTP) ───────────────────────────────────────────────────────
# Se monta en /mcp/ pero queda gateado por flag (config.mcp_enabled) y
# por Bearer token. Se puede activar/desactivar desde la UI sin reiniciar.
import secrets
from contextlib import asynccontextmanager

from mcp_tools import build_mcp_server

# Hosts permitidos por la transport security de FastMCP. El validador solo
# acepta `host:port` si el patrón termina en `:*`; con `host` a secas
# rechaza `host:port` y devuelve 421 Misdirected Request. Por eso listamos
# tanto la version sin puerto como la wildcarded.
_MCP_ALLOWED_HOSTS = [
    "127.0.0.1", "127.0.0.1:*",
    "localhost",  "localhost:*",
    "testserver",  # TestClient envia Host=testserver sin puerto
]

# `_mcp` y `_mcp_inner_asgi` se (re)crean en cada lifespan startup.
# StreamableHTTPSessionManager solo permite una llamada a `.run()` por
# instancia, así que cada arranque del servidor estrena una FastMCP nueva.
_mcp = None
_mcp_inner_asgi = None


def _build_mcp():
    mcp = build_mcp_server(
        name="MyVoices",
        streamable_http_path="/",
        host="127.0.0.1",
    )
    try:
        mcp.settings.transport_security.allowed_hosts = _MCP_ALLOWED_HOSTS
    except Exception:
        pass
    return mcp, mcp.streamable_http_app()


def _mcp_state() -> dict:
    """Lee el estado MCP desde la DB. Se llama en cada request al mount —
    barato (una fila en SQLite local) y permite que el toggle se aplique
    al instante sin reiniciar el servidor."""
    cfg = load_config()
    enabled = str(cfg.get("mcp_enabled", "false")).lower() == "true"
    token = cfg.get("mcp_token", "") or ""
    return {"enabled": enabled, "token": token}


def _ensure_mcp_token() -> str:
    """Genera y persiste un Bearer token si no existe."""
    cfg = load_config()
    token = cfg.get("mcp_token", "") or ""
    if not token:
        token = secrets.token_urlsafe(32)
        save_config({"mcp_token": token})
    return token


async def _mcp_mount_dispatch(scope, receive, send):
    """ASGI app montado en /mcp/. Aplica el gate (toggle + auth) y delega
    en la instancia FastMCP actual creada por el lifespan."""
    async def _send_json(status: int, payload: dict):
        body = json.dumps(payload).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    if scope["type"] != "http":
        if _mcp_inner_asgi:
            await _mcp_inner_asgi(scope, receive, send)
        return

    st = _mcp_state()
    if not st["enabled"]:
        await _send_json(503,
                         {"error": "MCP disabled. Activate it in the MyVoices UI."})
        return
    if st["token"]:
        headers = dict(scope.get("headers", []))
        auth = headers.get(b"authorization", b"").decode()
        if auth != f"Bearer {st['token']}":
            await _send_json(401, {"error": "Missing or invalid Bearer token."})
            return
    if _mcp_inner_asgi is None:
        await _send_json(503, {"error": "MCP not initialised yet."})
        return
    await _mcp_inner_asgi(scope, receive, send)


# ── Cola de prioridad TTS ─────────────────────────────────────────────────────
# Cada item: (priority, job_id, voice, text, caller, future)
# priority: 0=alta (MCP/API externa), 1=normal (UI), 2=baja (frases automáticas)

_tts_queue: asyncio.PriorityQueue | None = None
_tts_jobs: dict[str, dict] = {}  # job_id → {status, result, error}
_tts_jobs_lock = threading.Lock()


async def _tts_worker():
    while True:
        priority, job_id, voice, text, caller, fut = await _tts_queue.get()
        with _tts_jobs_lock:
            if job_id in _tts_jobs:
                _tts_jobs[job_id]["status"] = "running"
        t0 = time.monotonic()
        try:
            path = await asyncio.to_thread(_synth_to_file_sync, voice, text)
            global _last_speak_path
            with _last_speak_lock:
                old = _last_speak_path
                _last_speak_path = path
            if old and old != path:
                try: os.remove(old)
                except Exception: pass
            threading.Thread(target=play_audio_keep, args=(path,), daemon=True).start()
            duration_ms = int((time.monotonic() - t0) * 1000)
            result = {"status": "success", "message": "Reproduciendo audio..."}
            with _tts_jobs_lock:
                _tts_jobs[job_id] = {"status": "success", "result": result}
            log_event("INFO", f"speak: voice={voice!r} text={text[:60]!r}",
                      caller=caller, voice_preset=voice,
                      text_preview=text[:120], duration_ms=duration_ms)
            asyncio.create_task(_fire_webhooks("speak_end", {
                "job_id": job_id, "voice": voice,
                "text": text[:120], "caller": caller, "duration_ms": duration_ms,
            }))
            if not fut.done():
                fut.set_result(result)
        except Exception as exc:
            err = str(exc)
            with _tts_jobs_lock:
                _tts_jobs[job_id] = {"status": "error", "error": err}
            log_event("ERROR", f"speak error: {err}",
                      caller=caller, voice_preset=voice, text_preview=text[:120])
            if not fut.done():
                fut.set_exception(exc)
        finally:
            _tts_queue.task_done()


async def _fire_webhooks(event: str, payload: dict) -> None:
    urls = await asyncio.to_thread(get_active_webhooks, event)
    if not urls:
        return
    import httpx as _httpx
    async with _httpx.AsyncClient(timeout=5) as client:
        for url in urls:
            try:
                await client.post(url, json={"event": event, **payload})
            except Exception as exc:
                _log.warning(f"Webhook {url} falló: {exc}")


@asynccontextmanager
async def _lifespan(_app):
    """En cada arranque (re)creamos el FastMCP server y su session_manager
    (que solo admite una llamada a `.run()` por instancia)."""
    global _mcp, _mcp_inner_asgi, _tts_queue
    _tts_queue = asyncio.PriorityQueue()  # create fresh per event loop
    _mcp, _mcp_inner_asgi = _build_mcp()
    worker_task = asyncio.create_task(_tts_worker())
    async with _mcp.session_manager.run():
        yield
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="MyVoices Service", lifespan=_lifespan)
app.mount("/mcp", _mcp_mount_dispatch)

VOICES_DIR = get_voices_dir()
PIPER_DIR  = get_piper_dir()

# ── Cache Piper ───────────────────────────────────────────────────────────────
_piper_cache:      dict       = {}
_voices_json_cache: dict      = {}
_voices_json_time:  float     = 0.0
_download_status:  dict[str, str] = {}


def _list_piper_files() -> list[dict]:
    """Lista modelos Piper instalados en disco (para catálogo HF y gestión interna)."""
    result = []
    for onnx in sorted(PIPER_DIR.glob("*.onnx"), key=lambda f: f.stem.lower()):
        info: dict = {"filename": onnx.stem}
        json_path = onnx.with_suffix(".onnx.json")
        if json_path.exists():
            try:
                with open(json_path, encoding="utf-8") as f:
                    meta = json.load(f)
                info["sample_rate"]   = meta.get("sample_rate", 22050)
                info["num_speakers"]  = meta.get("num_speakers", 1)
                info["speaker_names"] = list(meta.get("speaker_id_map", {}).keys())
                lang = meta.get("espeak", {})
                info["language"]      = lang.get("lang", "")
            except Exception:
                pass
        result.append(info)
    return result


def _get_piper_voice(model_name: str) -> "PiperVoice":
    if model_name not in _piper_cache:
        onnx_path = PIPER_DIR / f"{model_name}.onnx"
        if not onnx_path.exists():
            raise HTTPException(400, f"Modelo Piper '{model_name}.onnx' no encontrado")
        try:
            _piper_cache[model_name] = PiperVoice.load(str(onnx_path))
        except Exception as exc:
            raise HTTPException(500, f"Error cargando modelo Piper '{model_name}': {exc}")
    return _piper_cache[model_name]


# ── Carga del modelo XTTS ─────────────────────────────────────────────────────
def _cuda_kernels_work() -> bool:
    try:
        a = torch.zeros(8, 8, device="cuda")
        torch.mm(a, a)
        torch.cuda.synchronize()
        return True
    except Exception as e:
        gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "?"
        _log.warning(
            f"CUDA no disponible para '{gpu_name}': {e}. "
            f"PyTorch {torch.__version__} puede no tener kernels para esta GPU. "
            f"GPUs Blackwell (RTX 5xxx) requieren: "
            f"pip install torch --index-url https://download.pytorch.org/whl/cu128"
        )
        return False


def _load_tts_model():
    global device
    cuda_ok    = torch.cuda.is_available() and _cuda_kernels_work()
    candidates = ["cuda", "cpu"] if cuda_ok else ["cpu"]
    if not cuda_ok and torch.cuda.is_available():
        _log.warning("GPU detectada pero kernels incompatibles → cargando en CPU.")
    for dev in candidates:
        try:
            _log.info(f"Cargando XTTSv2 en {dev}...")
            model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(dev)
            device = dev
            _log.info(f"Modelo XTTSv2 listo en {dev}.")
            return model, "ok"
        except Exception as e:
            _log.error(f"Error cargando modelo en {dev}: {e}")
            if dev == "cpu":
                return None, str(e)
    return None, "No se pudo cargar el modelo."


if os.getenv("SKIP_MODEL_LOAD") == "1":
    device       = "cpu"
    tts          = None
    model_status = "skipped"
else:
    device          = "cuda" if torch.cuda.is_available() else "cpu"
    tts, model_status = _load_tts_model()

# ── F5-TTS (lazy) ─────────────────────────────────────────────────────────────
_f5tts_model:   "F5TTS | None"        = None
_f5tts_status:  str                   = "not_loaded"


def _load_f5tts_model():
    global _f5tts_model, _f5tts_status
    if _f5tts_model is not None:
        return _f5tts_model, _f5tts_status
    if not F5TTS_AVAILABLE:
        return None, "f5-tts no instalado"
    try:
        _log.info("Cargando F5-TTS (primera vez, descarga ~3 GB si no está en caché)…")
        _f5tts_model = F5TTS()
        _f5tts_status = "ok"
        _log.info("F5-TTS listo.")
    except Exception as e:
        import traceback as _tb
        tb = _tb.format_exc()
        msg = f"{type(e).__name__}: {e}" if str(e) else f"{type(e).__name__} (sin mensaje)"
        _f5tts_status = msg
        _log.error(f"Error cargando F5-TTS: {msg}\n{tb}")
    return _f5tts_model, _f5tts_status


# ── Chatterbox TTS (lazy) ─────────────────────────────────────────────────────
_chatterbox_model:  "ChatterboxTTS | None" = None
_chatterbox_status: str                    = "not_loaded"


def _load_chatterbox_model():
    global _chatterbox_model, _chatterbox_status
    if _chatterbox_model is not None:
        return _chatterbox_model, _chatterbox_status
    if not CHATTERBOX_AVAILABLE:
        return None, "chatterbox-tts no instalado"
    try:
        _log.info("Cargando Chatterbox TTS…")
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        _chatterbox_model = ChatterboxTTS.from_pretrained(device=dev)
        _chatterbox_status = "ok"
        _log.info(f"Chatterbox TTS listo en {dev}.")
    except Exception as e:
        import traceback as _tb
        tb = _tb.format_exc()
        msg = f"{type(e).__name__}: {e}" if str(e) else f"{type(e).__name__} (sin mensaje)"
        _chatterbox_status = msg
        _log.error(f"Error cargando Chatterbox: {msg}\n{tb}")
    return _chatterbox_model, _chatterbox_status

# ── Audio ─────────────────────────────────────────────────────────────────────
_audio_lock = threading.Lock()
if os.getenv("SKIP_MODEL_LOAD") != "1":
    pygame.mixer.init()

# Última síntesis cacheada por /api/speak para que /api/speak/last devuelva
# exactamente el mismo audio que se reprodujo (sin re-sintetizar).
_last_speak_path: str | None = None
_last_speak_lock = threading.Lock()

app.mount("/static", StaticFiles(directory=str(get_static_dir())), name="static")

# ── Helpers de síntesis ───────────────────────────────────────────────────────
def split_into_chunks(text: str, max_chars: int = 200) -> list[str]:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.!?;:])\s+", text):
        if not sentence:
            continue
        parts = [sentence] if len(sentence) <= max_chars else re.split(r"(?<=,)\s+", sentence)
        for part in parts:
            if not part:
                continue
            if len(current) + len(part) + 1 <= max_chars:
                current = (current + " " + part).strip() if current else part
            else:
                if current:
                    chunks.append(current)
                current = part
    if current:
        chunks.append(current)
    return chunks or [text]


def apply_speed(wav_path: str, speed: float) -> None:
    if abs(speed - 1.0) < 0.05:
        return
    sr, data = scipy_wavfile.read(wav_path)
    if data.dtype == np.int16:
        audio = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        audio = data.astype(np.float32) / 2147483648.0
    else:
        audio = data.astype(np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    new_length = max(1, int(len(audio) / speed))
    resampled  = scipy_signal.resample(audio, new_length)
    peak = np.max(np.abs(resampled))
    if peak > 0:
        resampled = resampled / peak * 0.95
    scipy_wavfile.write(wav_path, sr, (resampled * 32767).astype(np.int16))


def apply_pitch(wav_path: str, semitones: float) -> None:
    if abs(semitones) < 0.1:
        return
    import torchaudio
    sr, data = scipy_wavfile.read(wav_path)
    if data.dtype == np.int16:
        audio = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        audio = data.astype(np.float32) / 2147483648.0
    else:
        audio = data.astype(np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    waveform = torch.from_numpy(audio).unsqueeze(0)
    shifted  = torchaudio.functional.pitch_shift(
        waveform, sample_rate=sr, n_steps=float(semitones)
    )
    result = shifted.squeeze(0).numpy()
    peak = np.max(np.abs(result))
    if peak > 0:
        result = result / peak * 0.95
    scipy_wavfile.write(wav_path, sr, (result * 32767).astype(np.int16))


def apply_radio_effect(wav_path: str) -> None:
    sr, data = scipy_wavfile.read(wav_path)
    if data.dtype == np.int16:
        audio = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        audio = data.astype(np.float32) / 2147483648.0
    else:
        audio = data.astype(np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    nyq = sr / 2.0
    b_hi, a_hi = scipy_signal.butter(2, 200 / nyq, btype='high')
    audio = scipy_signal.lfilter(b_hi, a_hi, audio)
    b_bp, a_bp = scipy_signal.butter(5, [400 / nyq, 3400 / nyq], btype='band')
    audio = scipy_signal.lfilter(b_bp, a_bp, audio)
    drive = 3.5
    audio = np.tanh(audio * drive) / np.tanh(np.array(drive, dtype=np.float32))
    noise = np.random.normal(0, 0.004, size=audio.shape).astype(np.float32)
    audio = audio + noise
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.88
    scipy_wavfile.write(wav_path, sr, (audio * 32767).astype(np.int16))


def play_audio(file_path: str) -> None:
    with _audio_lock:
        pygame.mixer.music.load(file_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        pygame.mixer.music.unload()
    try:
        os.remove(file_path)
    except Exception:
        pass


def play_audio_keep(file_path: str) -> None:
    """Reproduce sin borrar el fichero (para que /api/speak/last pueda servirlo)."""
    with _audio_lock:
        pygame.mixer.music.load(file_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        pygame.mixer.music.unload()


def _sanitize_name(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()


# ── Síntesis con preset ───────────────────────────────────────────────────────
async def _speak_with_preset(preset_name: str, text: str) -> dict:
    preset = load_voice_preset(preset_name)
    if not preset:
        raise HTTPException(404, f"Preset de voz '{preset_name}' no encontrado")

    engine     = preset["engine"]
    filename   = preset["filename"]
    speaker_id = preset["speaker_id"]
    speed      = float(preset.get("speed", 1.0))
    pitch      = float(preset.get("pitch", 0.0))
    radio      = bool(preset.get("radio_effect", False))
    language   = preset.get("language") or "es"

    if engine == "piper":
        return await _synth_piper(text, filename, speaker_id, speed, pitch, radio)
    elif engine == "f5tts":
        return await _synth_f5tts(text, filename, speed, pitch, radio)
    elif engine == "chatterbox":
        return await _synth_chatterbox(text, filename, speed, pitch, radio)
    else:
        return await _synth_xtts(text, filename, speed, pitch, radio, language)





async def _synth_piper(text: str, model_name: str, speaker_id: int,
                       speed: float, pitch: float, radio: bool) -> dict:
    if not PIPER_AVAILABLE:
        raise HTTPException(500, "piper-tts no está instalado")
    if not model_name:
        raise HTTPException(400, "El preset no tiene modelo Piper asignado")

    voice   = _get_piper_voice(model_name)
    syn_cfg = PiperSynthConfig(
        length_scale=1.0 / max(0.1, speed),
        speaker_id=speaker_id,
    )
    chunks  = split_into_chunks(text)
    audio_q: queue.Queue = queue.Queue()

    def _synth_worker():
        for chunk in chunks:
            if not chunk.strip():
                continue
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            path = tmp.name; tmp.close()
            try:
                with wave_module.open(path, "wb") as wf:
                    voice.synthesize_wav(chunk, wf, syn_config=syn_cfg)
                if radio:
                    apply_radio_effect(path)
                if abs(pitch) >= 0.1:
                    apply_pitch(path, pitch)
                audio_q.put(path)
            except Exception as exc:
                _log.error(f"[Piper] Error en fragmento: {exc}")
                try: os.remove(path)
                except Exception: pass
        audio_q.put(None)

    def _play_worker():
        while True:
            path = audio_q.get()
            if path is None:
                break
            play_audio(path)

    threading.Thread(target=_synth_worker, daemon=True).start()
    threading.Thread(target=_play_worker,  daemon=True).start()
    n = len(chunks)
    return {"status": "success", "engine": "piper",
            "message": f"Reproduciendo {n} fragmento{'s' if n > 1 else ''}..."}


async def _synth_xtts(text: str, wav_filename: str, speed: float,
                      pitch: float, radio: bool, language: str) -> dict:
    global tts
    if tts is None:
        tts, status = _load_tts_model()
        if tts is None:
            raise HTTPException(500, f"No se pudo cargar el modelo TTS: {status}")

    if not wav_filename:
        raise HTTPException(400, "El preset no tiene archivo WAV de referencia asignado")

    ref_wav = VOICES_DIR / wav_filename
    if not ref_wav.exists():
        raise HTTPException(400, f"Archivo de voz '{wav_filename}' no encontrado")

    chunks  = split_into_chunks(text)
    audio_q: queue.Queue = queue.Queue()

    def _synth_worker():
        for chunk in chunks:
            if not chunk.strip():
                continue
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            path = tmp.name; tmp.close()
            try:
                tts.tts_to_file(
                    text=chunk,
                    speaker_wav=str(ref_wav),
                    language=language,
                    file_path=path,
                )
                if radio:
                    apply_radio_effect(path)
                if abs(speed - 1.0) >= 0.05:
                    apply_speed(path, speed)
                if abs(pitch) >= 0.1:
                    apply_pitch(path, pitch)
                audio_q.put(path)
            except Exception as e:
                _log.error(f"[XTTS] Error en fragmento: {e}")
                try: os.remove(path)
                except Exception: pass
        audio_q.put(None)

    def _play_worker():
        while True:
            path = audio_q.get()
            if path is None:
                break
            play_audio(path)

    threading.Thread(target=_synth_worker, daemon=True).start()
    threading.Thread(target=_play_worker,  daemon=True).start()
    n = len(chunks)
    return {"status": "success", "engine": "xtts",
            "message": f"Reproduciendo {n} fragmento{'s' if n > 1 else ''}..."}


async def _synth_f5tts(text: str, wav_filename: str, speed: float,
                       pitch: float, radio: bool) -> dict:
    model, status = _load_f5tts_model()
    if model is None:
        raise HTTPException(500, f"F5-TTS no disponible: {status}")
    if not wav_filename:
        raise HTTPException(400, "El preset no tiene archivo WAV de referencia")
    ref_wav = VOICES_DIR / wav_filename
    if not ref_wav.exists():
        raise HTTPException(400, f"Archivo de voz '{wav_filename}' no encontrado")

    chunks  = split_into_chunks(text)
    audio_q: queue.Queue = queue.Queue()

    def _synth_worker():
        for chunk in chunks:
            if not chunk.strip():
                continue
            tmp  = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            path = tmp.name; tmp.close()
            try:
                model.infer(ref_file=str(ref_wav), ref_text="",
                            gen_text=chunk, output_file=path)
                if radio:                     apply_radio_effect(path)
                if abs(speed - 1.0) >= 0.05: apply_speed(path, speed)
                if abs(pitch) >= 0.1:         apply_pitch(path, pitch)
                audio_q.put(path)
            except Exception as exc:
                _log.error(f"[F5-TTS] Error en fragmento: {exc}")
                try: os.remove(path)
                except Exception: pass
        audio_q.put(None)

    def _play_worker():
        while True:
            p = audio_q.get()
            if p is None:
                break
            play_audio_keep(p)

    threading.Thread(target=_synth_worker, daemon=True).start()
    threading.Thread(target=_play_worker,  daemon=True).start()
    n = len(chunks)
    return {"status": "success", "engine": "f5tts",
            "message": f"Reproduciendo {n} fragmento{'s' if n > 1 else ''}..."}


async def _synth_chatterbox(text: str, wav_filename: str, speed: float,
                            pitch: float, radio: bool) -> dict:
    model, status = _load_chatterbox_model()
    if model is None:
        raise HTTPException(500, f"Chatterbox TTS no disponible: {status}")
    if not wav_filename:
        raise HTTPException(400, "El preset no tiene archivo WAV de referencia")
    ref_wav = VOICES_DIR / wav_filename
    if not ref_wav.exists():
        raise HTTPException(400, f"Archivo de voz '{wav_filename}' no encontrado")

    chunks  = split_into_chunks(text)
    audio_q: queue.Queue = queue.Queue()

    def _synth_worker():
        for chunk in chunks:
            if not chunk.strip():
                continue
            tmp  = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            path = tmp.name; tmp.close()
            try:
                wav_tensor = model.generate(chunk, audio_prompt_path=str(ref_wav))
                audio_np = wav_tensor.squeeze().cpu().numpy()
                scipy_wavfile.write(path, 24000,
                                    (audio_np * 32767).astype(np.int16))
                if radio:                     apply_radio_effect(path)
                if abs(speed - 1.0) >= 0.05: apply_speed(path, speed)
                if abs(pitch) >= 0.1:         apply_pitch(path, pitch)
                audio_q.put(path)
            except Exception as exc:
                _log.error(f"[Chatterbox] Error en fragmento: {exc}")
                try: os.remove(path)
                except Exception: pass
        audio_q.put(None)

    def _play_worker():
        while True:
            p = audio_q.get()
            if p is None:
                break
            play_audio_keep(p)

    threading.Thread(target=_synth_worker, daemon=True).start()
    threading.Thread(target=_play_worker,  daemon=True).start()
    n = len(chunks)
    return {"status": "success", "engine": "chatterbox",
            "message": f"Reproduciendo {n} fragmento{'s' if n > 1 else ''}..."}


# ── Síntesis a fichero (para descarga) ───────────────────────────────────────
def _synth_to_file_sync(preset_name: str, text: str) -> str:
    """Sintetiza texto con el preset indicado y devuelve la ruta de un fichero WAV."""
    preset = load_voice_preset(preset_name)
    if not preset:
        raise ValueError(f"Preset '{preset_name}' no encontrado")

    engine     = preset["engine"]
    filename   = preset["filename"]
    speaker_id = preset["speaker_id"]
    speed      = float(preset.get("speed", 1.0))
    pitch      = float(preset.get("pitch", 0.0))
    radio      = bool(preset.get("radio_effect", False))
    language   = preset.get("language") or "es"

    chunks      = split_into_chunks(text)
    chunk_files: list[str] = []

    if engine == "piper":
        if not PIPER_AVAILABLE:
            raise ValueError("Piper TTS no disponible")
        voice   = _get_piper_voice(filename)
        syn_cfg = PiperSynthConfig(
            length_scale=1.0 / max(0.1, speed),
            speaker_id=speaker_id,
        )
        for chunk in chunks:
            if not chunk.strip():
                continue
            tmp  = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            path = tmp.name; tmp.close()
            with wave_module.open(path, "wb") as wf:
                voice.synthesize_wav(chunk, wf, syn_config=syn_cfg)
            if radio:              apply_radio_effect(path)
            if abs(pitch) >= 0.1:  apply_pitch(path, pitch)
            chunk_files.append(path)
    elif engine == "f5tts":
        model, status = _load_f5tts_model()
        if model is None:
            raise ValueError(f"F5-TTS no disponible: {status}")
        ref_wav = VOICES_DIR / filename
        if not ref_wav.exists():
            raise ValueError(f"Archivo de voz '{filename}' no encontrado")
        for chunk in chunks:
            if not chunk.strip():
                continue
            tmp  = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            path = tmp.name; tmp.close()
            model.infer(ref_file=str(ref_wav), ref_text="",
                        gen_text=chunk, output_file=path)
            if radio:                     apply_radio_effect(path)
            if abs(speed - 1.0) >= 0.05: apply_speed(path, speed)
            if abs(pitch) >= 0.1:         apply_pitch(path, pitch)
            chunk_files.append(path)
    elif engine == "chatterbox":
        model, status = _load_chatterbox_model()
        if model is None:
            raise ValueError(f"Chatterbox TTS no disponible: {status}")
        ref_wav = VOICES_DIR / filename
        if not ref_wav.exists():
            raise ValueError(f"Archivo de voz '{filename}' no encontrado")
        for chunk in chunks:
            if not chunk.strip():
                continue
            tmp  = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            path = tmp.name; tmp.close()
            wav_tensor = model.generate(chunk, audio_prompt_path=str(ref_wav))
            audio_np = wav_tensor.squeeze().cpu().numpy()
            scipy_wavfile.write(path, 24000, (audio_np * 32767).astype(np.int16))
            if radio:                     apply_radio_effect(path)
            if abs(speed - 1.0) >= 0.05: apply_speed(path, speed)
            if abs(pitch) >= 0.1:         apply_pitch(path, pitch)
            chunk_files.append(path)
    else:
        global tts
        if tts is None:
            tts, _status = _load_tts_model()
            if tts is None:
                raise ValueError(f"Modelo XTTS no cargado: {_status}")
        ref_wav = VOICES_DIR / filename
        if not ref_wav.exists():
            raise ValueError(f"Archivo de voz '{filename}' no encontrado")
        for chunk in chunks:
            if not chunk.strip():
                continue
            tmp  = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            path = tmp.name; tmp.close()
            tts.tts_to_file(
                text=chunk, speaker_wav=str(ref_wav),
                language=language, file_path=path,
            )
            if radio:                    apply_radio_effect(path)
            if abs(speed - 1.0) >= 0.05: apply_speed(path, speed)
            if abs(pitch) >= 0.1:        apply_pitch(path, pitch)
            chunk_files.append(path)

    if not chunk_files:
        raise ValueError("No se generó audio")

    if len(chunk_files) == 1:
        return chunk_files[0]

    # Concatenar fragmentos en un solo WAV
    segments: list[np.ndarray] = []
    sr = 22050
    for f in chunk_files:
        _sr, data = scipy_wavfile.read(f)
        sr = _sr
        if data.ndim > 1:
            data = data.mean(axis=1)
        if data.dtype != np.int16:
            data = data.astype(np.float32)
            peak = float(np.max(np.abs(data))) or 1.0
            data = (data / peak * 32767).astype(np.int16)
        segments.append(data.astype(np.int16))
        os.remove(f)

    out      = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    out_path = out.name; out.close()
    scipy_wavfile.write(out_path, sr, np.concatenate(segments))
    return out_path


# ── Modelos de request ────────────────────────────────────────────────────────
class SpeakRequest(BaseModel):
    voice: str
    text:  str


# ── Rutas principales ─────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    with open(get_static_dir() / "index.html", encoding="utf-8") as f:
        return f.read()


@app.get("/api/status")
async def api_status():
    installed_piper       = len(list(PIPER_DIR.glob("*.onnx")))
    installed_xtts        = len(list_voices(engine="xtts"))
    installed_f5tts       = len(list_voices(engine="f5tts"))
    installed_chatterbox  = len(list_voices(engine="chatterbox"))
    return {
        "model":                model_status,
        "device":               device,
        "gpu_name":             torch.cuda.get_device_name(0) if device == "cuda" else None,
        "piper_available":      PIPER_AVAILABLE,
        "f5tts_available":      F5TTS_AVAILABLE,
        "f5tts_status":         _f5tts_status,
        "chatterbox_available": CHATTERBOX_AVAILABLE,
        "chatterbox_status":    _chatterbox_status,
        "voices_xtts":          installed_xtts,
        "voices_piper":         installed_piper,
        "voices_f5tts":         installed_f5tts,
        "voices_chatterbox":    installed_chatterbox,
        "presets":              len(list_voice_presets()),
    }


@app.post("/api/models/load/{engine}")
async def api_load_model(engine: str):
    """Carga bajo demanda el modelo TTS del motor indicado.
    Útil para precalentar desde la UI antes de la primera síntesis."""
    if engine == "xtts":
        m, st = await asyncio.to_thread(_load_tts_model)
        return {"engine": "xtts", "status": st, "loaded": m is not None}
    if engine == "f5tts":
        if not F5TTS_AVAILABLE:
            raise HTTPException(503, _F5TTS_IMPORT_ERROR or "f5-tts no instalado")
        m, st = await asyncio.to_thread(_load_f5tts_model)
        return {"engine": "f5tts", "status": st, "loaded": m is not None}
    if engine == "chatterbox":
        if not CHATTERBOX_AVAILABLE:
            raise HTTPException(503, _CHATTERBOX_IMPORT_ERROR or "chatterbox-tts no instalado")
        m, st = await asyncio.to_thread(_load_chatterbox_model)
        return {"engine": "chatterbox", "status": st, "loaded": m is not None}
    raise HTTPException(400, f"Motor desconocido: {engine}")


@app.get("/api/diagnostics")
async def api_diagnostics():
    """Estado completo de la app para diagnóstico: import errors, status de cada
    motor, versión de paquetes clave, y modo verbose. Pensado para que un cliente
    MCP/LLM pueda investigar errores sin que el usuario tenga que copiar logs."""
    pkg_versions = {}
    for pkg in ("torch", "torchaudio", "transformers", "TTS",
                "f5_tts", "chatterbox", "piper", "fastapi", "pydantic"):
        try:
            mod = __import__(pkg)
            pkg_versions[pkg] = getattr(mod, "__version__", "unknown")
        except Exception as e:
            pkg_versions[pkg] = f"NOT_INSTALLED ({type(e).__name__})"
    return {
        "verbose":              VERBOSE,
        "device":               device,
        "gpu_name":             torch.cuda.get_device_name(0) if device == "cuda" else None,
        "engines": {
            "xtts": {
                "available": tts is not None or model_status == "skipped",
                "status":    model_status,
            },
            "piper":      {"available": PIPER_AVAILABLE, "import_error": ""},
            "f5tts":      {"available": F5TTS_AVAILABLE,
                           "status":    _f5tts_status,
                           "import_error": _F5TTS_IMPORT_ERROR},
            "chatterbox": {"available": CHATTERBOX_AVAILABLE,
                           "status":    _chatterbox_status,
                           "import_error": _CHATTERBOX_IMPORT_ERROR},
        },
        "package_versions": pkg_versions,
    }


@app.post("/api/verbose/{enabled}")
async def api_set_verbose(enabled: str):
    """Activa/desactiva modo verbose en runtime (afecta nuevos logs).
    enabled: 'true' o 'false'. Persiste en la config DB."""
    val = enabled.lower() in ("true", "1", "yes", "on")
    cfg = load_config()
    cfg["verbose"] = "true" if val else "false"
    save_config(cfg)
    new_level = logging.DEBUG if val else logging.INFO
    logging.getLogger().setLevel(new_level)
    _db_handler.setLevel(new_level)
    global VERBOSE
    VERBOSE = val
    _log.info(f"Verbose mode {'enabled' if val else 'disabled'}")
    return {"verbose": val}


@app.get("/api/config")
async def api_get_config():
    return load_config()


@app.post("/api/config")
async def api_update_config(language: str = Form(...)):
    save_config({"language": language})
    return load_config()


# ── Voces ─────────────────────────────────────────────────────────────────────

@app.get("/api/voices")
async def api_list_voices(engine: str = None):
    return list_voices(engine=engine)


# ── Rutas específicas de motor ANTES del parámetro genérico {voice_id} ────────
# FastAPI resuelve en orden de definición: las rutas literales deben ir primero
# para que "f5tts"/"chatterbox" no sean tratadas como un voice_id entero.

@app.post("/api/voices/xtts")
async def api_upload_xtts_voice(file: UploadFile = File(...), name: str = Form(...)):
    if not file.filename.lower().endswith(".wav"):
        raise HTTPException(400, "Solo se aceptan archivos .wav")
    safe = _sanitize_name(name)
    if not safe:
        raise HTTPException(400, "Nombre inválido")
    filename = f"{safe}.wav"
    dest = VOICES_DIR / filename
    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)
    voice_id = add_voice("xtts", safe, filename)
    return get_voice(voice_id)


# ── Rutas genéricas con {voice_id} ────────────────────────────────────────────

@app.get("/api/voices/{voice_id}")
async def api_get_voice(voice_id: int):
    v = get_voice(voice_id)
    if not v:
        raise HTTPException(404, "Voz no encontrada")
    return v


@app.put("/api/voices/{voice_id}")
async def api_rename_voice(voice_id: int, name: str = Form(...)):
    if not get_voice(voice_id):
        raise HTTPException(404, "Voz no encontrada")
    safe = _sanitize_name(name)
    if not safe:
        raise HTTPException(400, "Nombre inválido")
    rename_voice(voice_id, safe)
    return get_voice(voice_id)


@app.delete("/api/voices/{voice_id}")
async def api_delete_voice(voice_id: int):
    voice = get_voice(voice_id)
    if not voice:
        raise HTTPException(404, "Voz no encontrada")
    if voice["engine"] in ("xtts", "f5tts", "chatterbox") and voice["filename"]:
        wav = VOICES_DIR / voice["filename"]
        if wav.exists():
            wav.unlink()
    remove_voice(voice_id)
    return {"status": "deleted"}


# ── Piper: gestión de voces instaladas ───────────────────────────────────────

@app.get("/api/piper/voices")
async def api_list_piper_voices():
    """Lista voces Piper registradas en la DB (con metadatos del disco)."""
    db_voices = list_voices(engine="piper")
    file_meta = {f["filename"]: f for f in _list_piper_files()}
    for v in db_voices:
        meta = file_meta.get(v.get("filename"), {})
        v["language"]     = meta.get("language", "")
        v["num_speakers"] = meta.get("num_speakers", 1)
    return db_voices


@app.post("/api/piper/register")
async def api_register_piper_voice(
    name:       str = Form(...),
    filename:   str = Form(...),
    speaker_id: int = Form(0),
):
    """Registra en la DB una voz Piper ya descargada en disco."""
    safe = _sanitize_name(name)
    if not safe:
        raise HTTPException(400, "Nombre inválido")
    if not (PIPER_DIR / f"{filename}.onnx").exists():
        raise HTTPException(400, f"Modelo '{filename}.onnx' no encontrado en piper_voices/")
    voice_id = add_voice("piper", safe, filename, speaker_id)
    return get_voice(voice_id)


@app.delete("/api/piper/voices/{voice_id}")
async def api_delete_piper_voice(voice_id: int):
    voice = get_voice(voice_id)
    if not voice or voice["engine"] != "piper":
        raise HTTPException(404, "Voz Piper no encontrada")
    filename = voice.get("filename", "")
    deleted  = []
    for suffix in (".onnx", ".onnx.json"):
        p = PIPER_DIR / f"{filename}{suffix}"
        if p.exists():
            p.unlink()
            deleted.append(p.name)
    _piper_cache.pop(filename, None)
    remove_voice(voice_id)
    return {"status": "deleted", "files": deleted}


# ── F5-TTS: registro de voces ─────────────────────────────────────────────────
# GET /api/voices?engine=f5tts  →  usa el endpoint genérico de arriba
# DELETE /api/voices/{id}       →  usa el endpoint genérico de arriba

@app.post("/api/voices/f5tts")
async def api_upload_f5tts_voice(file: UploadFile = File(...), name: str = Form(...)):
    if not file.filename.lower().endswith(".wav"):
        raise HTTPException(400, "Solo se aceptan archivos .wav")
    safe = _sanitize_name(name)
    if not safe:
        raise HTTPException(400, "Nombre inválido")
    filename = f"{safe}.wav"
    dest = VOICES_DIR / filename
    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)
    voice_id = add_voice("f5tts", safe, filename)
    return get_voice(voice_id)


# ── Chatterbox: registro de voces ─────────────────────────────────────────────
# GET /api/voices?engine=chatterbox  →  usa el endpoint genérico de arriba
# DELETE /api/voices/{id}            →  usa el endpoint genérico de arriba

@app.post("/api/voices/chatterbox")
async def api_upload_chatterbox_voice(file: UploadFile = File(...), name: str = Form(...)):
    if not file.filename.lower().endswith(".wav"):
        raise HTTPException(400, "Solo se aceptan archivos .wav")
    safe = _sanitize_name(name)
    if not safe:
        raise HTTPException(400, "Nombre inválido")
    filename = f"{safe}.wav"
    dest = VOICES_DIR / filename
    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)
    voice_id = add_voice("chatterbox", safe, filename)
    return get_voice(voice_id)


# ── Piper: catálogo HuggingFace ───────────────────────────────────────────────

@app.get("/api/piper/available")
async def api_piper_available(lang: str = None):
    global _voices_json_cache, _voices_json_time
    now = time.time()
    if not _voices_json_cache or now - _voices_json_time > 3600:
        hf_url = "https://huggingface.co/rhasspy/piper-voices/raw/main/voices.json"
        try:
            def _fetch():
                req = urllib.request.Request(hf_url, headers={"User-Agent": "MyVoices/2.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return json.loads(resp.read())
            _voices_json_cache = await asyncio.to_thread(_fetch)
            _voices_json_time  = now
        except Exception as exc:
            raise HTTPException(502, f"No se pudo obtener catálogo HuggingFace: {exc}")

    installed = {f.stem for f in PIPER_DIR.glob("*.onnx")}
    result = []
    for key, info in _voices_json_cache.items():
        lc = info.get("language", {}).get("code", "")
        if lang and not lc.lower().startswith(lang.lower()):
            continue
        size_mb = sum(
            v.get("size_bytes", 0) for v in info.get("files", {}).values()
        ) / 1_048_576
        result.append({
            "key":           key,
            "name":          info.get("name", key),
            "language_code": lc,
            "language_name": info.get("language", {}).get("name_english", ""),
            "quality":       info.get("quality", ""),
            "num_speakers":  info.get("num_speakers", 1),
            "size_mb":       round(size_mb, 1),
            "installed":     key in installed,
            "dl_status":     _download_status.get(key, "idle"),
        })
    return sorted(result, key=lambda x: (x["language_code"], x["name"]))


@app.post("/api/piper/download")
async def api_piper_download(key: str = Form(...)):
    if not _voices_json_cache:
        raise HTTPException(400, "Carga primero el catálogo (/api/piper/available)")
    if key not in _voices_json_cache:
        raise HTTPException(404, f"Voz '{key}' no encontrada en el catálogo")
    if _download_status.get(key) == "downloading":
        return {"status": "already_downloading", "key": key}

    info  = _voices_json_cache[key]
    files = list(info.get("files", {}).keys())
    base  = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"

    def _dl():
        _download_status[key] = "downloading"
        try:
            for fp in files:
                url  = base + fp
                dest = PIPER_DIR / Path(fp).name
                req  = urllib.request.Request(url, headers={"User-Agent": "MyVoices/2.0"})
                with urllib.request.urlopen(req, timeout=300) as resp:
                    with open(dest, "wb") as f:
                        while True:
                            chunk = resp.read(65_536)
                            if not chunk:
                                break
                            f.write(chunk)
            _download_status[key] = "done"
            _log.info(f"[Piper] Descarga completada: {key}")
        except Exception as exc:
            _download_status[key] = f"error: {exc}"
            _log.error(f"[Piper] Error descargando '{key}': {exc}")

    threading.Thread(target=_dl, daemon=True, name=f"piper-dl-{key}").start()
    return {"status": "downloading", "key": key}


@app.get("/api/piper/download/{key}/status")
async def api_piper_dl_status(key: str):
    return {"key": key, "status": _download_status.get(key, "idle")}


# ── Presets de voz ────────────────────────────────────────────────────────────

@app.get("/api/voice-presets")
async def api_list_voice_presets():
    return list_voice_presets()


@app.post("/api/voice-presets")
async def api_save_voice_preset(
    name:         str   = Form(...),
    voice_id:     int   = Form(...),
    speed:        float = Form(1.0),
    pitch:        float = Form(0.0),
    radio_effect: str   = Form("false"),
    language:     str   = Form("es"),
):
    safe = _sanitize_name(name)
    if not safe:
        raise HTTPException(400, "Nombre de preset inválido")
    if not get_voice(voice_id):
        raise HTTPException(404, f"Voz con ID {voice_id} no encontrada")
    speed = max(0.5, min(2.0, speed))
    pitch = max(-12.0, min(12.0, pitch))
    radio = radio_effect.lower() == "true"
    save_voice_preset(safe, voice_id, speed, pitch, radio, language or "es")
    return load_voice_preset(safe)


@app.put("/api/voice-presets/{name}")
async def api_update_voice_preset(
    name:         str,
    voice_id:     int   = Form(None),
    speed:        float = Form(None),
    pitch:        float = Form(None),
    radio_effect: str   = Form(None),
    language:     str   = Form(None),
):
    preset = load_voice_preset(name)
    if not preset:
        raise HTTPException(404, f"Preset '{name}' no encontrado")
    new_vid   = voice_id     if voice_id     is not None else preset["voice_id"]
    new_speed = max(0.5, min(2.0, speed))    if speed        is not None else preset["speed"]
    new_pitch = max(-12.0, min(12.0, pitch)) if pitch        is not None else preset["pitch"]
    new_radio = (radio_effect.lower() == "true") if radio_effect is not None else preset["radio_effect"]
    new_lang  = language if language is not None else preset.get("language", "es")
    if not get_voice(new_vid):
        raise HTTPException(404, f"Voz con ID {new_vid} no encontrada")
    save_voice_preset(name, new_vid, new_speed, new_pitch, new_radio, new_lang)
    return load_voice_preset(name)


@app.delete("/api/voice-presets/{name}")
async def api_delete_voice_preset(name: str):
    if not load_voice_preset(name):
        raise HTTPException(404, f"Preset '{name}' no encontrado")
    delete_voice_preset(name)
    return {"status": "deleted"}


# ── Frases guardadas ──────────────────────────────────────────────────────────

@app.get("/api/phrases")
async def api_list_phrases():
    return list_phrases()


@app.post("/api/phrases")
async def api_save_phrase(
    name:              str = Form(...),
    text:              str = Form(...),
    voice_preset_name: str = Form(None),
):
    if not name.strip() or not text.strip():
        raise HTTPException(400, "name y text son obligatorios")
    if voice_preset_name and not load_voice_preset(voice_preset_name):
        raise HTTPException(404, f"Preset '{voice_preset_name}' no encontrado")
    phrase_id = save_phrase(name.strip(), text.strip(), voice_preset_name or None)
    return get_phrase(phrase_id)


@app.put("/api/phrases/{phrase_id}")
async def api_update_phrase(
    phrase_id:         int,
    name:              str = Form(...),
    text:              str = Form(...),
    voice_preset_name: str = Form(None),
):
    if not get_phrase(phrase_id):
        raise HTTPException(404, "Frase no encontrada")
    if voice_preset_name and not load_voice_preset(voice_preset_name):
        raise HTTPException(404, f"Preset '{voice_preset_name}' no encontrado")
    update_phrase(phrase_id, name.strip(), text.strip(), voice_preset_name or None)
    return get_phrase(phrase_id)


@app.delete("/api/phrases/{phrase_id}")
async def api_delete_phrase(phrase_id: int):
    if not get_phrase(phrase_id):
        raise HTTPException(404, "Frase no encontrada")
    delete_phrase(phrase_id)
    return {"status": "deleted"}


@app.post("/api/phrases/{phrase_name}/play")
async def api_play_phrase(phrase_name: str, request: Request):
    phrase = get_phrase_by_name(phrase_name)
    if not phrase:
        raise HTTPException(404, f"Frase '{phrase_name}' no encontrada")
    preset_name = phrase.get("voice_preset_name")
    if not preset_name:
        raise HTTPException(400, "La frase no tiene preset de voz asignado")
    caller = _detect_caller(request)
    priority = 2  # frases = baja prioridad
    job_id = str(_uuid.uuid4())[:8]
    fut: asyncio.Future = asyncio.get_event_loop().create_future()
    with _tts_jobs_lock:
        _tts_jobs[job_id] = {"status": "queued"}
    await _tts_queue.put((priority, job_id, preset_name, phrase["text"], caller, fut))
    try:
        return await asyncio.wait_for(asyncio.shield(fut), timeout=120)
    except asyncio.TimeoutError:
        raise HTTPException(504, "Timeout esperando síntesis TTS")


# ── Síntesis principal ────────────────────────────────────────────────────────

import uuid as _uuid


def _detect_caller(request: Request) -> str:
    ua = request.headers.get("user-agent", "").lower()
    if "python-httpx" in ua or "mcp" in ua:
        return "MCP"
    if "mozilla" in ua or "webkit" in ua or "chrome" in ua:
        return "UI"
    return "API"


@app.post("/api/speak")
async def api_speak(req: SpeakRequest, request: Request):
    if not req.text.strip():
        raise HTTPException(400, "El campo 'text' no puede estar vacío")
    if not req.voice.strip():
        raise HTTPException(400, "El campo 'voice' (nombre del preset) no puede estar vacío")

    voice  = req.voice.strip()
    text   = req.text.strip()
    caller = _detect_caller(request)
    priority = 0 if caller in ("MCP", "API") else 1

    job_id = str(_uuid.uuid4())[:8]
    fut: asyncio.Future = asyncio.get_event_loop().create_future()

    with _tts_jobs_lock:
        _tts_jobs[job_id] = {"status": "queued"}

    await _tts_queue.put((priority, job_id, voice, text, caller, fut))

    try:
        result = await asyncio.wait_for(asyncio.shield(fut), timeout=120)
    except asyncio.TimeoutError:
        raise HTTPException(504, "Timeout esperando síntesis TTS")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return result


@app.get("/api/speak/last")
async def api_speak_last():
    """Devuelve el último audio sintetizado por /api/speak."""
    with _last_speak_lock:
        path = _last_speak_path
    if not path or not os.path.exists(path):
        raise HTTPException(404, "No hay audio reciente. Reproduce primero un texto.")
    return FileResponse(path, media_type="audio/wav", filename="myvoices_last.wav")


@app.post("/api/speak/download")
async def api_speak_download(req: SpeakRequest):
    """Sintetiza texto con el preset y devuelve el WAV para descarga."""
    if not req.text.strip() or not req.voice.strip():
        raise HTTPException(400, "voice y text son obligatorios")
    try:
        path = await asyncio.to_thread(
            _synth_to_file_sync, req.voice.strip(), req.text.strip()
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", req.voice.strip())
    return FileResponse(
        path,
        media_type="audio/wav",
        filename=f"myvoices_{safe_name}.wav",
        background=BackgroundTask(os.remove, path),
    )


# ── Logs ──────────────────────────────────────────────────────────────────────

@app.get("/api/logs")
async def api_get_logs(limit: int = 200, offset: int = 0,
                       level: str = None, caller: str = None):
    return get_logs(limit=limit, offset=offset,
                    level=level or None, caller=caller or None)


@app.delete("/api/logs")
async def api_clear_logs():
    clear_logs()
    return {"status": "cleared"}


# ── Webhooks ──────────────────────────────────────────────────────────────────

class WebhookRequest(BaseModel):
    url: str
    events: str = "speak_end"


@app.get("/api/webhooks")
async def api_list_webhooks():
    return list_webhooks()


@app.post("/api/webhooks")
async def api_add_webhook(req: WebhookRequest):
    wid = add_webhook(req.url, req.events)
    return {"id": wid, "url": req.url, "events": req.events}


@app.delete("/api/webhooks/{webhook_id}")
async def api_delete_webhook(webhook_id: int):
    delete_webhook(webhook_id)
    return {"status": "deleted"}


@app.post("/api/webhooks/test/{webhook_id}")
async def api_test_webhook(webhook_id: int):
    hooks = list_webhooks()
    hook = next((h for h in hooks if h["id"] == webhook_id), None)
    if not hook:
        raise HTTPException(404, "Webhook no encontrado")
    import httpx as _httpx
    try:
        async with _httpx.AsyncClient(timeout=5) as client:
            r = await client.post(hook["url"], json={
                "event": "test", "message": "MyVoices webhook test"
            })
        return {"status": "ok", "http_status": r.status_code}
    except Exception as exc:
        raise HTTPException(502, f"No se pudo contactar con el webhook: {exc}")


# ── MCP control ───────────────────────────────────────────────────────────────

_MCP_CLIENT_TEMPLATES = {
    # Cliente / etiqueta visible / transport / cómo se configura
    "claude_desktop_http": {
        "label":      "Claude Desktop (HTTP)",
        "transport":  "http",
        "config_path": "%APPDATA%\\Claude\\claude_desktop_config.json",
        "instructions": (
            "Pega este bloque dentro de la sección \"mcpServers\" del JSON. "
            "Si no existe el campo, créalo. Reinicia Claude Desktop tras guardar."
        ),
    },
    "claude_desktop_stdio": {
        "label":      "Claude Desktop (stdio, legacy)",
        "transport":  "stdio",
        "config_path": "%APPDATA%\\Claude\\claude_desktop_config.json",
        "instructions": (
            "Modo stdio: lanza mcp_server.py como subprocess. La app de "
            "MyVoices debe estar abierta para que el script pueda llamar a "
            "su REST API."
        ),
    },
    "claude_code": {
        "label":      "Claude Code (CLI)",
        "transport":  "http",
        "config_path": "Comando en terminal — no edita ficheros",
        "instructions": (
            "Ejecuta el comando en una terminal. `claude mcp list` debe "
            "mostrar 'myvoices' tras añadirlo."
        ),
    },
    "cursor": {
        "label":      "Cursor",
        "transport":  "http",
        "config_path": ".cursor/mcp.json (proyecto) o ~/.cursor/mcp.json (global)",
        "instructions": (
            "Crea o edita el fichero. Reinicia Cursor tras guardar."
        ),
    },
    "gemini_cli": {
        "label":      "Gemini CLI",
        "transport":  "http",
        "config_path": "~/.gemini/mcp.json",
        "instructions": (
            "Crea el fichero si no existe. Compatible con Gemini CLI ≥ 0.4."
        ),
    },
    "chatgpt": {
        "label":      "ChatGPT (Connectors)",
        "transport":  "http",
        "config_path": "Settings → Connectors → Add MCP Server",
        "instructions": (
            "Disponibilidad varía por plan (Team/Enterprise). En la UI de "
            "Connectors pega la URL y añade un header Authorization."
        ),
    },
    "generic_http": {
        "label":      "Genérico (HTTP)",
        "transport":  "http",
        "config_path": "—",
        "instructions": (
            "URL + header Authorization Bearer. Útil para cualquier cliente "
            "MCP que soporte streamable HTTP."
        ),
    },
}


def _mcp_url(request) -> str:
    """URL pública del endpoint MCP a partir de la request entrante."""
    host = request.headers.get("host", "localhost:8000")
    scheme = request.url.scheme or "http"
    return f"{scheme}://{host}/mcp/"


def _render_snippet(client_id: str, url: str, token: str) -> dict:
    """Devuelve {format, content} para el cliente indicado."""
    auth_header = f"Bearer {token}" if token else ""
    if client_id == "claude_desktop_http":
        body = {
            "mcpServers": {
                "myvoices": {
                    "type":    "http",
                    "url":     url,
                    "headers": {"Authorization": auth_header} if token else {},
                }
            }
        }
        return {"format": "json", "content": json.dumps(body, indent=2)}
    if client_id == "claude_desktop_stdio":
        body = {
            "mcpServers": {
                "myvoices": {
                    "command": sys.executable,
                    "args":    [os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                              "mcp_server.py")],
                    "env":     {"MYVOICES_URL": url.rsplit("/mcp/", 1)[0]},
                }
            }
        }
        return {"format": "json", "content": json.dumps(body, indent=2)}
    if client_id == "claude_code":
        cmd = f'claude mcp add myvoices --transport http {url}'
        if token:
            cmd += f' --header "Authorization: {auth_header}"'
        return {"format": "bash", "content": cmd}
    if client_id == "cursor":
        body = {
            "mcpServers": {
                "myvoices": {
                    "url":     url,
                    "headers": {"Authorization": auth_header} if token else {},
                }
            }
        }
        return {"format": "json", "content": json.dumps(body, indent=2)}
    if client_id == "gemini_cli":
        body = {
            "mcpServers": {
                "myvoices": {
                    "httpUrl":     url,
                    "httpHeaders": {"Authorization": auth_header} if token else {},
                }
            }
        }
        return {"format": "json", "content": json.dumps(body, indent=2)}
    if client_id == "chatgpt":
        return {
            "format":  "text",
            "content": (
                f"Server URL:\n  {url}\n\n"
                f"Authentication header:\n  Authorization: {auth_header}\n\n"
                "(Solo Connectors / planes que soporten servidores MCP HTTP.)"
            ),
        }
    if client_id == "generic_http":
        curl = f'curl -X POST {url} \\\n     -H "Accept: application/json, text/event-stream"'
        if token:
            curl += f' \\\n     -H "Authorization: {auth_header}"'
        return {"format": "bash", "content": curl}
    raise HTTPException(404, f"client '{client_id}' not supported")


@app.get("/api/mcp/status")
async def api_mcp_status(request: Request):
    st = _mcp_state()
    return {
        "enabled":     st["enabled"],
        "has_token":   bool(st["token"]),
        "url":         _mcp_url(request),
        "transport":   "streamable-http",
    }


class _McpToggleReq(BaseModel):
    enabled: bool


@app.post("/api/mcp/toggle")
async def api_mcp_toggle(req: _McpToggleReq):
    if req.enabled:
        token = _ensure_mcp_token()
        save_config({"mcp_enabled": True})
        return {"enabled": True, "token": token}
    save_config({"mcp_enabled": False})
    return {"enabled": False}


@app.get("/api/mcp/token")
async def api_mcp_token():
    """Devuelve el Bearer token actual (o cadena vacía si nunca se generó)."""
    return {"token": load_config().get("mcp_token", "") or ""}


@app.post("/api/mcp/regenerate-token")
async def api_mcp_regenerate_token():
    token = secrets.token_urlsafe(32)
    save_config({"mcp_token": token})
    return {"token": token}


@app.get("/api/mcp/clients")
async def api_mcp_clients():
    """Lista los clientes con plantilla disponible (para la UI de ayuda)."""
    return [
        {"id": cid, "label": meta["label"], "transport": meta["transport"]}
        for cid, meta in _MCP_CLIENT_TEMPLATES.items()
    ]


@app.get("/api/mcp/config-snippet")
async def api_mcp_config_snippet(client: str, request: Request):
    if client not in _MCP_CLIENT_TEMPLATES:
        raise HTTPException(404, f"client '{client}' not supported")
    meta  = _MCP_CLIENT_TEMPLATES[client]
    state = _mcp_state()
    snippet = _render_snippet(client, _mcp_url(request), state["token"])
    return {
        "client":       client,
        "label":        meta["label"],
        "transport":    meta["transport"],
        "config_path":  meta["config_path"],
        "instructions": meta["instructions"],
        "format":       snippet["format"],
        "content":      snippet["content"],
    }


@app.post("/api/mcp/test")
async def api_mcp_test(request: Request):
    """Auto-test: lanza una request HTTP MCP sobre el propio mount con auth.
    Útil para verificar que la cadena de gate + session manager funciona."""
    state = _mcp_state()
    if not state["enabled"]:
        return {"ok": False, "detail": "MCP está desactivado"}
    import httpx
    headers = {"Accept": "application/json, text/event-stream"}
    if state["token"]:
        headers["Authorization"] = f"Bearer {state['token']}"
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "myvoices-self-test", "version": "1"}},
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(_mcp_url(request), json=payload, headers=headers)
        ok = r.status_code == 200 and "protocolVersion" in r.text
        return {"ok": ok, "status": r.status_code, "body_excerpt": r.text[:200]}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}
