# -*- mode: python ; coding: utf-8 -*-
# ChatVoice.spec — Configuración de PyInstaller
#
# Genera un bundle en modo --onedir (carpeta).
# El ejecutable final queda en: dist/ChatVoice/ChatVoice.exe
#
# Para compilar:  pyinstaller ChatVoice.spec --noconfirm
# O simplemente: build.bat

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

# Recolectar archivos de datos de todos los paquetes que los necesitan.
#
# include_py_files=True → paquetes que usan inspect.getsource() o
#   torch.jit.script en tiempo de ejecución (necesitan el .py original).
# Sin include_py_files → solo datos no-Python (VERSION, configs, lexicons…).

def safe_collect(pkg, **kwargs):
    """collect_data_files ignorando paquetes no instalados."""
    try:
        return collect_data_files(pkg, **kwargs)
    except Exception:
        return []

# Paquetes que necesitan sus .py disponibles en tiempo de ejecución
tts_datas       = safe_collect("TTS",       include_py_files=True)
trainer_datas   = safe_collect("trainer",   include_py_files=True)
typeguard_datas = safe_collect("typeguard", include_py_files=True)
inflect_datas   = safe_collect("inflect",   include_py_files=True)

# Paquetes con archivos de datos (VERSION, lexicons, tablas de idioma, etc.)
transformers_datas  = safe_collect("transformers")
tokenizers_datas    = safe_collect("tokenizers")
coqpit_datas        = safe_collect("coqpit")
gruut_datas         = safe_collect("gruut")
gruut_ipa_datas     = safe_collect("gruut_ipa")
gruut_lang_de_datas = safe_collect("gruut_lang_de")
gruut_lang_en_datas = safe_collect("gruut_lang_en")
gruut_lang_es_datas = safe_collect("gruut_lang_es")
gruut_lang_fr_datas = safe_collect("gruut_lang_fr")
nltk_datas          = safe_collect("nltk")
unidecode_datas     = safe_collect("unidecode")
jamo_datas          = safe_collect("jamo")
anyascii_datas      = safe_collect("anyascii")
jieba_datas         = safe_collect("jieba")
pypinyin_datas      = safe_collect("pypinyin")

# soundfile: necesita libsndfile-1.dll en Windows para cargar audio en el exe
soundfile_datas = safe_collect("soundfile")
soundfile_libs  = collect_dynamic_libs("soundfile")

# torch: incluir DLLs CUDA (torch_cuda.dll, c10_cuda.dll, caffe2_nvrtc.dll…)
# Necesario para que torch.cuda.is_available() devuelva True en el exe.
torch_libs = collect_dynamic_libs("torch")

# Piper TTS — piper_phonemize incluye los datos de espeak-ng (phontab, etc.)
piper_phonemize_datas = safe_collect("piper_phonemize")
piper_datas           = safe_collect("piper")
onnxruntime_datas     = safe_collect("onnxruntime")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[
        *soundfile_libs,   # libsndfile-1.dll (backend de audio torchaudio)
        *torch_libs,       # torch_cuda.dll, c10_cuda.dll, caffe2_nvrtc.dll… (GPU)
    ],
    datas=[
        # Archivos estáticos del frontend (HTML/CSS/JS)
        ("static", "static"),
        # Archivos de datos de los paquetes
        *tts_datas,
        *trainer_datas,
        *typeguard_datas,
        *inflect_datas,
        *transformers_datas,
        *tokenizers_datas,
        *coqpit_datas,
        *gruut_datas,
        *gruut_ipa_datas,
        *gruut_lang_de_datas,
        *gruut_lang_en_datas,
        *gruut_lang_es_datas,
        *gruut_lang_fr_datas,
        *nltk_datas,
        *unidecode_datas,
        *jamo_datas,
        *anyascii_datas,
        *jieba_datas,
        *pypinyin_datas,
        # soundfile + Piper TTS
        *soundfile_datas,
        *piper_phonemize_datas,
        *piper_datas,
        *onnxruntime_datas,
    ],
    hiddenimports=[
        # ── uvicorn ──────────────────────────────────────────────────────────
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.http.httptools_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.websockets_impl",
        "uvicorn.protocols.websockets.wsproto_impl",
        "uvicorn.lifespan",
        "uvicorn.lifespan.off",
        "uvicorn.lifespan.on",
        # ── starlette / fastapi ───────────────────────────────────────────────
        "starlette.routing",
        "starlette.staticfiles",
        "starlette.responses",
        "starlette.middleware",
        "starlette.middleware.cors",
        "starlette.background",
        "anyio",
        "anyio._backends._asyncio",
        "anyio._backends._trio",
        "anyio.abc",
        # ── multipart ─────────────────────────────────────────────────────────
        "multipart",
        "multipart.multipart",
        # ── PyTorch ───────────────────────────────────────────────────────────
        "torch",
        "torch.nn",
        "torch.nn.functional",
        "torch.utils",
        "torch.utils.data",
        "torchaudio",
        "torchaudio.transforms",
        # ── Coqui TTS ─────────────────────────────────────────────────────────
        "TTS",
        "TTS.api",
        "TTS.tts",
        "TTS.tts.configs",
        "TTS.tts.configs.xtts_config",
        "TTS.tts.models",
        "TTS.tts.models.xtts",
        "TTS.tts.utils",
        "TTS.tts.utils.speakers",
        "TTS.utils",
        "TTS.utils.audio",
        "TTS.utils.audio.processor",
        "TTS.config",
        "TTS.config.shared_configs",
        # ── transformers ──────────────────────────────────────────────────────
        "transformers",
        "transformers.models",
        "transformers.models.auto",
        # ── scipy ─────────────────────────────────────────────────────────────
        "scipy",
        "scipy.signal",
        "scipy.io",
        "scipy.io.wavfile",
        "scipy.special._ufuncs",
        "scipy.linalg.blas",
        "scipy.linalg.lapack",
        "scipy.linalg._fblas",
        "scipy.linalg._flapack",
        # ── pygame ────────────────────────────────────────────────────────────
        "pygame",
        "pygame.mixer",
        # ── otros ─────────────────────────────────────────────────────────────
        "numpy",
        "pydantic",
        "pydantic.v1",
        "requests",
        "charset_normalizer",
        "aiofiles",
        "h11",
        "httptools",
        "websockets",
        "database",  # módulo propio ChatVoice
        # ── soundfile (backend torchaudio, requerido por TTS y Piper) ─────────
        "soundfile",
        "_soundfile",
        # ── Piper TTS ─────────────────────────────────────────────────────────
        "piper",
        "piper.voice",
        "piper_phonemize",
        "onnxruntime",
        "onnxruntime.capi._pybind_state",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Excluir módulos mockeados en server.py — no deben estar en el bundle
    excludes=["numba", "llvmlite"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    # noarchive=True es necesario para que torch.jit.script pueda leer
    # los .py de TTS en tiempo de ejecución. Con False, los módulos se
    # cargan desde un zip y __file__ no apunta a una ruta real en disco.
    noarchive=True,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ChatVoice",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,      # UPX puede conflictuar con PyTorch — desactivado por seguridad
    console=False,  # Consola oculta — los logs se consultan desde el visor en la UI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="icon.ico",  # Descomentar si tienes un icono .ico
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ChatVoice",
)
