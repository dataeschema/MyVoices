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

    for name, mod in {
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
        sys.modules[name] = mod

_mock_numba_and_llvmlite()

# En el exe (PyInstaller), añadir torch/lib al path de búsqueda de DLLs ANTES
# de que torch se importe — necesario para que Windows encuentre torch_cuda.dll,
# c10_cuda.dll y las DLLs CUDA empaquetadas con el wheel de PyTorch.
if getattr(sys, "frozen", False):
    # console=False → stdin/stdout/stderr son None; TTS llama input() para los ToS.
    import io
    if sys.stdin  is None: sys.stdin  = io.StringIO()
    if sys.stdout is None: sys.stdout = io.StringIO()
    if sys.stderr is None: sys.stderr = io.StringIO()

    _torch_lib = os.path.join(sys._MEIPASS, "torch", "lib")
    if os.path.isdir(_torch_lib):
        try:
            os.add_dll_directory(_torch_lib)          # Python 3.8+
        except Exception:
            pass
        os.environ["PATH"] = _torch_lib + os.pathsep + os.environ.get("PATH", "")

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import asyncio
import json
import urllib.request
import wave as wave_module
import torch
import logging

_log = logging.getLogger("chatvoice")
from database import (
    init_db, load_config, save_config,
    get_voices_dir, get_static_dir, get_piper_dir,
    register_voice, remove_voice, migrate_local_voices,
    log_event, get_logs, clear_logs,
    list_presets, save_preset, load_preset, delete_preset,
    list_phrases, save_phrase, update_phrase, delete_phrase, get_phrase,
)

# ── Soporte Piper TTS (opcional) ──────────────────────────────────────────────
# En el exe (PyInstaller), los datos de espeak-ng están en _MEIPASS/piper_phonemize/
# La variable ESPEAK_DATA_PATH debe apuntar a ellos ANTES de importar piper.
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

# PyTorch 2.6 cambió weights_only=True; XTTSv2 usa clases personalizadas
_torch_load_orig = torch.load
def _torch_load_compat(*args, **kwargs):
    kwargs.setdefault("weights_only", False)
    return _torch_load_orig(*args, **kwargs)
torch.load = _torch_load_compat

# torchaudio 2.5+ usa un dispatcher que puede intentar torchcodec aunque no esté
# instalado (cuando soundfile no está en el bundle del exe).
# Reemplazamos torchaudio.load con una implementación propia que usa soundfile
# primero y scipy.io.wavfile como fallback garantizado — sin tocar torchcodec.
import torchaudio as _ta
try:
    _ta.set_audio_backend("soundfile")
except Exception:
    pass


def _load_audio_compat(uri, frame_offset: int = 0, num_frames: int = -1,
                        normalize: bool = True, channels_first: bool = True,
                        format=None, **_kw):
    """Carga WAV con soundfile o scipy sin depender de torchcodec."""
    # 1. Intentar soundfile (si está en el bundle o instalado)
    try:
        import soundfile as _sf
        data, sr = _sf.read(
            str(uri), dtype="float32", always_2d=True,
            start=frame_offset,
            frames=num_frames if num_frames > 0 else -1,
        )
        return torch.from_numpy(data.T.copy()), int(sr)
    except Exception:
        pass
    # 2. Fallback garantizado: scipy.io.wavfile (siempre en el bundle)
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


# Parchear en todos los niveles donde TTS pueda acceder al loader
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

from TTS.api import TTS
import pygame
import threading
import tempfile
import time
import shutil
import queue
import re
import numpy as np
from pathlib import Path
from scipy import signal as scipy_signal
from scipy.io import wavfile as scipy_wavfile

# ── Logging handler → SQLite ──────────────────────────────────────────────────
class _DBLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            lvl = record.levelname
            msg = self.format(record)
            log_event(lvl, msg)
        except Exception:
            pass

_db_handler = _DBLogHandler()
_db_handler.setLevel(logging.INFO)
_db_handler.setFormatter(logging.Formatter("%(name)s — %(message)s"))

# Solo root logger; los uvicorn.*  tienen propagate=True y llegarán aquí.
# uvicorn.access es la excepción: en algunas versiones tiene propagate=False.
logging.getLogger().addHandler(_db_handler)
logging.getLogger().setLevel(logging.INFO)
_uv_access = logging.getLogger("uvicorn.access")
if not _uv_access.propagate:
    _uv_access.addHandler(_db_handler)

app = FastAPI(title="SAMMI XTTSv2 Service")

# ── Directorios y configuración ───────────────────────────────────────────────
# Inicializar base de datos SQLite y migrar datos legacy
init_db()

VOICES_DIR = get_voices_dir()
PIPER_DIR  = get_piper_dir()

# ── Cache Piper ───────────────────────────────────────────────────────────────
_piper_cache: dict           = {}   # model_name → PiperVoice
_voices_json_cache: dict     = {}   # voces disponibles en HuggingFace
_voices_json_time: float     = 0.0
_download_status: dict[str, str] = {}  # voice_key → "idle"|"downloading"|"done"|"error:..."


def _list_piper_voices() -> list[dict]:
    """Lista modelos Piper instalados localmente (ordenados por nombre)."""
    result = []
    for onnx in sorted(PIPER_DIR.glob("*.onnx"), key=lambda f: f.stem.lower()):
        info: dict = {"name": onnx.stem, "filename": onnx.name}
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
    """Carga y cachea un modelo Piper por nombre (sin extensión)."""
    if model_name not in _piper_cache:
        onnx_path = PIPER_DIR / f"{model_name}.onnx"
        if not onnx_path.exists():
            raise HTTPException(400, f"Modelo Piper '{model_name}.onnx' no encontrado en {PIPER_DIR}")
        try:
            _piper_cache[model_name] = PiperVoice.load(str(onnx_path))
        except Exception as exc:
            raise HTTPException(500, f"Error cargando modelo Piper '{model_name}': {exc}")
    return _piper_cache[model_name]


# Migrar voces de directorio local voices/ a APPDATA (primera ejecución)
migrate_local_voices(Path("voices"))

# Migrar referencia.wav legacy al directorio de voces
_legacy = Path("referencia.wav")
if _legacy.exists() and not (VOICES_DIR / "referencia.wav").exists():
    shutil.copy(_legacy, VOICES_DIR / "referencia.wav")
    register_voice("referencia", "referencia.wav")
    cfg = load_config()
    if cfg.get("active_voice") is None:
        cfg["active_voice"] = "referencia"
        cfg["voice_type"]   = "wav"
        save_config(cfg)
    _log.info("Migrado referencia.wav → voices/referencia.wav")

# ── Carga del modelo ──────────────────────────────────────────────────────────
def _cuda_kernels_work() -> bool:
    try:
        a = torch.zeros(8, 8, device="cuda")
        torch.mm(a, a)
        torch.cuda.synchronize()
        return True
    except RuntimeError as e:
        _log.warning(f"CUDA incompatible: {e}")
        return False

def _load_tts_model():
    global device
    cuda_ok   = torch.cuda.is_available() and _cuda_kernels_work()
    candidates = ["cuda", "cpu"] if cuda_ok else ["cpu"]
    if not cuda_ok and torch.cuda.is_available():
        _log.warning("GPU detectada pero kernels incompatibles → usando CPU.")
    for dev in candidates:
        try:
            _log.info(f"Cargando XTTSv2 en {dev}...")
            model = TTS("tts_models/multilingual/multi-dataset/xtts_v2",
                        agree_to_terms=True).to(dev)
            device = dev
            _log.info(f"Modelo XTTSv2 listo en {dev}.")
            return model, "ok"
        except Exception as e:
            _log.error(f"Error cargando modelo en {dev}: {e}")
            if dev == "cpu":
                return None, str(e)
    return None, "No se pudo cargar el modelo."

device   = "cuda" if torch.cuda.is_available() else "cpu"
tts, model_status = _load_tts_model()

# Voces predefinidas disponibles (se llena tras cargar el modelo)
BUILTIN_VOICES: list[str] = sorted(tts.speakers) if tts and hasattr(tts, "speakers") and tts.speakers else []

# Voces femeninas recomendadas para español/streaming (subconjunto curado)
RECOMMENDED_FEMALE = {
    "Ana Florence", "Daisy Studious", "Gracie Wise", "Tammie Ema",
    "Alison Dietlinde", "Annmarie Nele", "Asya Anara", "Brenda Stern",
    "Gitta Nikolina", "Henriette Uente", "Maja Ruoho", "Uta Obando",
    "Lidiya Morozova", "Camilla Holmström", "Lilya Stainthorpe",
    "Zofija Kendrick", "Barbora MacLean", "Alexandra Hisakawa",
    "Alma María", "Rosemary Okafor",
}

_audio_lock = threading.Lock()

def _reinit_audio(devicename: str = "") -> None:
    with _audio_lock:
        pygame.mixer.quit()
        if devicename:
            try:
                pygame.mixer.init(devicename=devicename)
                return
            except Exception as exc:
                _log.warning(f"[Audio] No se pudo inicializar '{devicename}': {exc}. Usando dispositivo por defecto.")
        pygame.mixer.init()

_cfg_init = load_config()
_reinit_audio(_cfg_init.get("audio_device", ""))

# ── Archivos estáticos ────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=str(get_static_dir())), name="static")

# ── Modelos ───────────────────────────────────────────────────────────────────
class SpeakRequest(BaseModel):
    text:         str
    language:     str   = None   # None = usar el de config
    radio_effect: bool  = None   # None = usar el de config
    speed:        float = None   # None = usar el de config; rango 0.5–2.0
    pitch:        float = None   # None = usar el de config; semítonos -12 a +12
    voice_index:  int   = None   # None = usar voz activa; índice dentro del motor activo
    engine:       str   = None   # "xtts" | "piper" | None (usa config global)
    speaker_id:   int   = None   # índice de hablante en modelos Piper multi-speaker

# ── Chunking de texto ────────────────────────────────────────────────────────
def split_into_chunks(text: str, max_chars: int = 200) -> list[str]:
    """
    Divide el texto en fragmentos aptos para XTTSv2.
    - Fragmentos largos producen alucinaciones; <= 200 chars es seguro.
    - Divide por puntuación de final de frase; si una frase sigue siendo
      larga, subdivide por comas.
    """
    text = " ".join(text.split())          # normalizar espacios
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current = ""

    for sentence in re.split(r"(?<=[.!?;:])\s+", text):
        if not sentence:
            continue
        # Si la frase sola supera el límite, romper por comas
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


# ── Velocidad de reproducción ─────────────────────────────────────────────────
def apply_speed(wav_path: str, speed: float) -> None:
    """
    Cambia la velocidad de reproducción remuestreando el audio.
    speed > 1.0 → más rápido; speed < 1.0 → más lento.
    """
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
    resampled = scipy_signal.resample(audio, new_length)

    peak = np.max(np.abs(resampled))
    if peak > 0:
        resampled = resampled / peak * 0.95
    scipy_wavfile.write(wav_path, sr, (resampled * 32767).astype(np.int16))


# ── Tono (pitch) ─────────────────────────────────────────────────────────────
def apply_pitch(wav_path: str, semitones: float) -> None:
    """
    Cambia el tono sin alterar la duración usando torchaudio phase vocoder.
    semitones > 0 → más agudo;  semitones < 0 → más grave.
    Rango recomendado: -12 a +12.
    """
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

    # pitch_shift espera tensor (channels, time)
    waveform = torch.from_numpy(audio).unsqueeze(0)
    shifted  = torchaudio.functional.pitch_shift(
        waveform, sample_rate=sr, n_steps=float(semitones)
    )
    result = shifted.squeeze(0).numpy()

    peak = np.max(np.abs(result))
    if peak > 0:
        result = result / peak * 0.95
    scipy_wavfile.write(wav_path, sr, (result * 32767).astype(np.int16))


# ── Efecto de radio ───────────────────────────────────────────────────────────
def apply_radio_effect(wav_path: str) -> None:
    """Aplica efecto de radio/walkie-talkie in-place sobre un fichero WAV."""
    sr, data = scipy_wavfile.read(wav_path)

    # Convertir a float32 normalizado
    if data.dtype == np.int16:
        audio = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        audio = data.astype(np.float32) / 2147483648.0
    else:
        audio = data.astype(np.float32)

    # Mezclar a mono si es estéreo
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    nyq = sr / 2.0

    # 1. Paso-alto suave para quitar rumble de baja frecuencia
    b_hi, a_hi = scipy_signal.butter(2, 200 / nyq, btype='high')
    audio = scipy_signal.lfilter(b_hi, a_hi, audio)

    # 2. Bandpass de radio: 400 – 3400 Hz
    b_bp, a_bp = scipy_signal.butter(5, [400 / nyq, 3400 / nyq], btype='band')
    audio = scipy_signal.lfilter(b_bp, a_bp, audio)

    # 3. Distorsión suave (soft clipping)
    drive = 3.5
    audio = np.tanh(audio * drive) / np.tanh(np.array(drive, dtype=np.float32))

    # 4. Ruido de fondo muy sutil (crepitar de radio)
    noise = np.random.normal(0, 0.004, size=audio.shape).astype(np.float32)
    audio = audio + noise

    # 5. Normalizar y convertir a int16
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.88
    out = (audio * 32767).astype(np.int16)

    scipy_wavfile.write(wav_path, sr, out)

# ── Helpers ───────────────────────────────────────────────────────────────────
def play_audio(file_path: str):
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

def _sanitize_name(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()

async def _do_speak_piper(text: str, radio: bool, speed: float, pitch: float,
                          model_name: str, speaker_id: int = 0) -> dict:
    """Síntesis con Piper TTS. Speed nativo via length_scale; pitch via torchaudio."""
    voice = _get_piper_voice(model_name)
    # length_scale es la inversa de speed: 0.5 = 2× más rápido, 2.0 = 2× más lento
    syn_cfg = PiperSynthConfig(
        length_scale = 1.0 / max(0.1, speed),
        speaker_id   = speaker_id,
    )

    chunks = split_into_chunks(text)
    audio_q: queue.Queue = queue.Queue()

    def _synth_worker():
        for chunk in chunks:
            if not chunk.strip():
                continue
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            path = tmp.name
            tmp.close()
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
    threading.Thread(target=_play_worker, daemon=True).start()

    n = len(chunks)
    return {"status": "success", "engine": "piper",
            "message": f"Piper: reproduciendo {n} fragmento{'s' if n > 1 else ''}..."}


async def _do_speak(text: str, language: str = None, radio: bool = None,
                    speed: float = None, pitch: float = None,
                    voice_index: int = None, engine: str = None,
                    speaker_id: int = None,
                    active_voice: str = None, voice_type: str = None,
                    piper_voice: str = None) -> dict:
    cfg        = load_config()
    use_engine = engine or cfg.get("engine", "xtts")
    use_radio  = radio if radio is not None else cfg.get("radio_effect", False)
    use_speed  = max(0.5, min(2.0, speed if speed is not None else float(cfg.get("speed", 1.0))))
    use_pitch  = max(-12.0, min(12.0, pitch if pitch is not None else float(cfg.get("pitch", 0.0))))

    # ── Piper ─────────────────────────────────────────────────────────────────
    if use_engine == "piper":
        if not PIPER_AVAILABLE:
            raise HTTPException(500, "piper-tts no está instalado. Ejecuta: pip install piper-tts")

        if voice_index is not None:
            pvoices = _list_piper_voices()
            if voice_index >= len(pvoices):
                raise HTTPException(400, f"voice_index {voice_index} fuera de rango Piper (0-{len(pvoices)-1})")
            model_name = pvoices[voice_index]["name"]
        else:
            model_name = piper_voice or cfg.get("piper_active_voice")

        if not model_name:
            raise HTTPException(400, "No hay modelo Piper activo. Selecciona uno en el panel Piper.")

        use_spk = speaker_id if speaker_id is not None else int(cfg.get("piper_speaker_id", 0))
        return await _do_speak_piper(text, use_radio, use_speed, use_pitch, model_name, use_spk)

    # ── XTTSv2 ───────────────────────────────────────────────────────────────
    global tts
    if tts is None:
        tts, status = _load_tts_model()
        if tts is None:
            raise HTTPException(500, f"No se pudo cargar el modelo TTS: {status}")

    lang = language or cfg.get("language", "es")

    if voice_index is not None:
        uploaded_files = sorted(VOICES_DIR.glob("*.wav"), key=lambda f: f.stem.lower())
        n_up = len(uploaded_files)
        n_bi = len(BUILTIN_VOICES)
        if voice_index < n_up:
            active     = uploaded_files[voice_index].stem
            voice_type = "wav"
        elif voice_index < n_up + n_bi:
            active     = BUILTIN_VOICES[voice_index - n_up]
            voice_type = "builtin"
        else:
            raise HTTPException(400, f"voice_index {voice_index} fuera de rango XTTS (0-{n_up+n_bi-1})")
    else:
        active     = active_voice or cfg.get("active_voice")
        voice_type = voice_type   or cfg.get("voice_type", "wav")

    if not active:
        raise HTTPException(400, "No hay ninguna voz XTTS activa. Selecciona una en el panel.")

    ref_wav = None
    if voice_type != "builtin":
        ref_wav = VOICES_DIR / f"{active}.wav"
        if not ref_wav.exists():
            raise HTTPException(400, f"Archivo '{active}.wav' no encontrado.")

    chunks = split_into_chunks(text)
    audio_q: queue.Queue = queue.Queue()

    def _synth_worker():
        for chunk in chunks:
            if not chunk.strip():
                continue
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            path = tmp.name
            tmp.close()
            try:
                if voice_type == "builtin":
                    tts.tts_to_file(text=chunk, speaker=active, language=lang, file_path=path)
                else:
                    tts.tts_to_file(text=chunk, speaker_wav=str(ref_wav), language=lang, file_path=path)
                if use_radio:
                    apply_radio_effect(path)
                if abs(use_speed - 1.0) >= 0.05:
                    apply_speed(path, use_speed)
                if abs(use_pitch) >= 0.1:
                    apply_pitch(path, use_pitch)
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
    threading.Thread(target=_play_worker, daemon=True).start()

    n = len(chunks)
    return {"status": "success", "engine": "xtts",
            "message": f"Reproduciendo {n} fragmento{'s' if n > 1 else ''}..."}

# ── Rutas ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    with open(get_static_dir() / "index.html", encoding="utf-8") as f:
        return f.read()

@app.get("/api/status")
async def status():
    return {
        "model":    model_status,
        "device":   device,
        "gpu_name": torch.cuda.get_device_name(0) if device == "cuda" else None,
    }

@app.get("/api/config")
async def get_config():
    return load_config()

@app.post("/api/config")
async def update_config(
    language:           str   = Form(...),
    radio_effect:       str   = Form("false"),
    active_voice:       str   = Form(None),
    voice_type:         str   = Form(None),
    speed:              float = Form(1.0),
    pitch:              float = Form(0.0),
    engine:             str   = Form(None),
    piper_active_voice: str   = Form(None),
    piper_speaker_id:   int   = Form(0),
    audio_device:       str   = Form(""),
):
    cfg = load_config()
    cfg["language"]     = language
    cfg["radio_effect"] = radio_effect.lower() == "true"
    cfg["speed"]        = max(0.5, min(2.0, speed))
    cfg["pitch"]        = max(-12.0, min(12.0, pitch))
    if active_voice is not None:
        cfg["active_voice"] = active_voice or None
    if voice_type in ("wav", "builtin"):
        cfg["voice_type"] = voice_type
    if engine in ("xtts", "piper"):
        cfg["engine"] = engine
    if piper_active_voice is not None:
        cfg["piper_active_voice"] = piper_active_voice or None
    cfg["piper_speaker_id"] = piper_speaker_id
    prev_device = cfg.get("audio_device", "")
    cfg["audio_device"] = audio_device
    save_config(cfg)
    if audio_device != prev_device:
        _reinit_audio(audio_device)
    return cfg

# ── Voces subidas ─────────────────────────────────────────────────────────────
@app.get("/api/voices")
async def list_voices():
    cfg = load_config()
    uploaded_files = sorted(VOICES_DIR.glob("*.wav"), key=lambda f: f.stem.lower())
    uploaded = [{"index": i, "name": f.stem, "filename": f.name} for i, f in enumerate(uploaded_files)]
    offset   = len(uploaded)
    builtin  = [
        {"index": offset + i, "name": n, "recommended": n in RECOMMENDED_FEMALE}
        for i, n in enumerate(BUILTIN_VOICES)
    ]
    return {
        "uploaded":    uploaded,
        "builtin":     builtin,
        "active":      cfg.get("active_voice"),
        "active_type": cfg.get("voice_type", "wav"),
    }

@app.post("/api/voices/upload")
async def upload_voice(file: UploadFile = File(...), name: str = Form(...)):
    if not file.filename.lower().endswith(".wav"):
        raise HTTPException(400, "Solo se aceptan archivos .wav")
    safe_name = _sanitize_name(name)
    if not safe_name:
        raise HTTPException(400, "Nombre inválido")
    dest = VOICES_DIR / f"{safe_name}.wav"
    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)
    register_voice(safe_name, f"{safe_name}.wav")
    cfg = load_config()
    if cfg.get("active_voice") is None:
        cfg["active_voice"] = safe_name
        cfg["voice_type"]   = "wav"
        save_config(cfg)
    return {"name": safe_name}

@app.post("/api/voices/wav/{name}/select")
async def select_wav_voice(name: str):
    if not (VOICES_DIR / f"{name}.wav").exists():
        raise HTTPException(404, "Voz no encontrada")
    cfg = load_config()
    cfg["active_voice"] = name
    cfg["voice_type"]   = "wav"
    save_config(cfg)
    return {"active_voice": name, "voice_type": "wav"}

@app.post("/api/voices/builtin/{name}/select")
async def select_builtin_voice(name: str):
    if name not in BUILTIN_VOICES:
        raise HTTPException(404, "Voz predefinida no encontrada")
    cfg = load_config()
    cfg["active_voice"] = name
    cfg["voice_type"]   = "builtin"
    save_config(cfg)
    return {"active_voice": name, "voice_type": "builtin"}

@app.delete("/api/voices/{name}")
async def delete_voice(name: str):
    voice_file = VOICES_DIR / f"{name}.wav"
    if not voice_file.exists():
        raise HTTPException(404, "Voz no encontrada")
    voice_file.unlink()
    remove_voice(name)
    cfg = load_config()
    if cfg.get("active_voice") == name and cfg.get("voice_type") == "wav":
        cfg["active_voice"] = None
        save_config(cfg)
    return {"status": "deleted"}

# ── Piper: voces instaladas ───────────────────────────────────────────────────

@app.get("/api/piper/voices")
async def list_piper_voices():
    cfg    = load_config()
    voices = _list_piper_voices()
    for i, v in enumerate(voices):
        v["index"] = i
    return {
        "voices":            voices,
        "active":            cfg.get("piper_active_voice"),
        "active_speaker_id": cfg.get("piper_speaker_id", 0),
        "piper_available":   PIPER_AVAILABLE,
        "piper_dir":         str(PIPER_DIR),
    }


@app.post("/api/piper/voices/{name}/select")
async def select_piper_voice(name: str, speaker_id: int = 0):
    installed = {v["name"] for v in _list_piper_voices()}
    if name not in installed:
        raise HTTPException(404, f"Modelo Piper '{name}' no encontrado en {PIPER_DIR}")
    cfg = load_config()
    cfg["piper_active_voice"] = name
    cfg["piper_speaker_id"]   = speaker_id
    cfg["engine"]             = "piper"
    save_config(cfg)
    return {"piper_active_voice": name, "speaker_id": speaker_id, "engine": "piper"}


@app.post("/api/piper/upload")
async def upload_piper_model(
    onnx_file: UploadFile = File(...),
    json_file: UploadFile = File(None),
):
    if not onnx_file.filename.lower().endswith(".onnx"):
        raise HTTPException(400, "El archivo principal debe tener extensión .onnx")
    dest_onnx = PIPER_DIR / onnx_file.filename
    with open(dest_onnx, "wb") as f:
        shutil.copyfileobj(onnx_file.file, f)
    if json_file:
        dest_json = PIPER_DIR / json_file.filename
        with open(dest_json, "wb") as f:
            shutil.copyfileobj(json_file.file, f)
    name = Path(onnx_file.filename).stem
    return {"name": name, "filename": onnx_file.filename}


@app.delete("/api/piper/voices/{name}")
async def delete_piper_voice(name: str):
    deleted = []
    for suffix in (".onnx", ".onnx.json"):
        p = PIPER_DIR / f"{name}{suffix}"
        if p.exists():
            p.unlink()
            deleted.append(p.name)
    if not deleted:
        raise HTTPException(404, "Modelo Piper no encontrado")
    _piper_cache.pop(name, None)
    cfg = load_config()
    if cfg.get("piper_active_voice") == name:
        cfg["piper_active_voice"] = None
        save_config(cfg)
    return {"status": "deleted", "files": deleted}


# ── Piper: catálogo HuggingFace ───────────────────────────────────────────────

@app.get("/api/piper/available")
async def list_available_piper_voices(lang: str = None):
    global _voices_json_cache, _voices_json_time
    now = time.time()
    if not _voices_json_cache or now - _voices_json_time > 3600:
        hf_url = "https://huggingface.co/rhasspy/piper-voices/raw/main/voices.json"
        try:
            def _fetch_catalog():
                req = urllib.request.Request(hf_url, headers={"User-Agent": "ChatVoice/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return json.loads(resp.read())
            _voices_json_cache = await asyncio.to_thread(_fetch_catalog)
            _voices_json_time = now
        except Exception as exc:
            raise HTTPException(502, f"No se pudo obtener la lista de voces de HuggingFace: {exc}")

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
    return sorted(result, key=lambda x: (x["language_code"], x["name"], x["quality"]))


@app.post("/api/piper/download")
async def download_piper_voice(key: str = Form(...)):
    if not _voices_json_cache:
        raise HTTPException(400, "Carga primero el catálogo de voces (/api/piper/available).")
    if key not in _voices_json_cache:
        raise HTTPException(404, f"Voz '{key}' no encontrada en el catálogo.")
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
                req  = urllib.request.Request(url, headers={"User-Agent": "ChatVoice/1.0"})
                with urllib.request.urlopen(req, timeout=300) as resp:
                    with open(dest, "wb") as f:
                        while True:
                            chunk = resp.read(65_536)
                            if not chunk:
                                break
                            f.write(chunk)
            _download_status[key] = "done"
        except Exception as exc:
            _download_status[key] = f"error: {exc}"
            _log.error(f"[Piper] Error descargando '{key}': {exc}")

    threading.Thread(target=_dl, daemon=True, name=f"piper-dl-{key}").start()
    return {"status": "downloading", "key": key}


@app.get("/api/piper/download/{key}/status")
async def piper_download_status(key: str):
    return {"key": key, "status": _download_status.get(key, "idle")}


# ── Logs ─────────────────────────────────────────────────────────────────────
@app.get("/api/logs")
async def api_get_logs(limit: int = 200, offset: int = 0, level: str = None):
    return get_logs(limit=limit, offset=offset, level=level or None)


@app.delete("/api/logs")
async def api_clear_logs():
    clear_logs()
    return {"status": "cleared"}


# ── Presets ───────────────────────────────────────────────────────────────────
@app.get("/api/presets")
async def api_list_presets():
    return list_presets()


@app.post("/api/presets")
async def api_save_preset(name: str = Form(...)):
    cfg = load_config()
    safe = _sanitize_name(name)
    if not safe:
        raise HTTPException(400, "Nombre de preset inválido")
    save_preset(safe, cfg)
    return load_preset(safe)


@app.post("/api/presets/{name}/apply")
async def api_apply_preset(name: str):
    preset = load_preset(name)
    if not preset:
        raise HTTPException(404, f"Preset '{name}' no encontrado")
    cfg = load_config()
    cfg.update({
        "engine":             preset.get("engine", "xtts"),
        "active_voice":       preset.get("voice"),
        "voice_type":         preset.get("voice_type", "wav"),
        "speed":              preset.get("speed", 1.0),
        "pitch":              preset.get("pitch", 0.0),
        "language":           preset.get("language", "es"),
        "radio_effect":       preset.get("radio_effect", False),
        "piper_active_voice": preset.get("piper_voice"),
        "piper_speaker_id":   preset.get("piper_speaker_id", 0),
    })
    save_config(cfg)
    return cfg


@app.delete("/api/presets/{name}")
async def api_delete_preset(name: str):
    if not load_preset(name):
        raise HTTPException(404, f"Preset '{name}' no encontrado")
    delete_preset(name)
    return {"status": "deleted"}


# ── Frases guardadas ──────────────────────────────────────────────────────────
@app.get("/api/phrases")
async def api_list_phrases():
    return list_phrases()


@app.post("/api/phrases")
async def api_save_phrase(
    label:       str = Form(...),
    text:        str = Form(...),
    preset_name: str = Form(None),
):
    if not label.strip() or not text.strip():
        raise HTTPException(400, "label y text son obligatorios")
    phrase_id = save_phrase(label.strip(), text.strip(), preset_name or None)
    return get_phrase(phrase_id)


@app.put("/api/phrases/{phrase_id}")
async def api_update_phrase(
    phrase_id:   int,
    label:       str = Form(...),
    text:        str = Form(...),
    preset_name: str = Form(None),
):
    if not get_phrase(phrase_id):
        raise HTTPException(404, "Frase no encontrada")
    update_phrase(phrase_id, label.strip(), text.strip(), preset_name or None)
    return get_phrase(phrase_id)


@app.delete("/api/phrases/{phrase_id}")
async def api_delete_phrase(phrase_id: int):
    if not get_phrase(phrase_id):
        raise HTTPException(404, "Frase no encontrada")
    delete_phrase(phrase_id)
    return {"status": "deleted"}


@app.post("/api/phrases/{phrase_id}/play")
async def api_play_phrase(phrase_id: int):
    phrase = get_phrase(phrase_id)
    if not phrase:
        raise HTTPException(404, "Frase no encontrada")
    cfg = load_config()
    if phrase.get("preset_name"):
        preset = load_preset(phrase["preset_name"])
        if preset:
            cfg.update({
                "engine":             preset.get("engine", "xtts"),
                "active_voice":       preset.get("voice"),
                "voice_type":         preset.get("voice_type", "wav"),
                "speed":              preset.get("speed", 1.0),
                "pitch":              preset.get("pitch", 0.0),
                "language":           preset.get("language", "es"),
                "radio_effect":       preset.get("radio_effect", False),
                "piper_active_voice": preset.get("piper_voice"),
                "piper_speaker_id":   preset.get("piper_speaker_id", 0),
            })
    return await _do_speak(
        text=phrase["text"],
        language=cfg.get("language"),
        radio=cfg.get("radio_effect"),
        speed=cfg.get("speed"),
        pitch=cfg.get("pitch"),
        engine=cfg.get("engine"),
        active_voice=cfg.get("active_voice"),
        voice_type=cfg.get("voice_type"),
        piper_voice=cfg.get("piper_active_voice"),
        speaker_id=int(cfg.get("piper_speaker_id", 0)),
    )


# ── Dispositivos de audio ─────────────────────────────────────────────────────
@app.get("/api/audio/devices")
async def api_audio_devices():
    cfg = load_config()
    try:
        devices = list(pygame._sdl2.audio.get_audio_device_names(capture=False))
    except Exception:
        devices = []
    return {"devices": devices, "active": cfg.get("audio_device", "")}


# ── Hablar ────────────────────────────────────────────────────────────────────
@app.post("/api/speak")
async def speak_api(req: SpeakRequest):
    return await _do_speak(req.text, req.language, req.radio_effect, req.speed,
                           req.pitch, req.voice_index, req.engine, req.speaker_id)

@app.post("/speak")   # compatibilidad SAMMI
async def speak_legacy(req: SpeakRequest):
    return await _do_speak(req.text, req.language, req.radio_effect, req.speed,
                           req.pitch, req.voice_index, req.engine, req.speaker_id)

# ── Entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    print("Panel de control: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
