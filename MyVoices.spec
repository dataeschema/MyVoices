# -*- mode: python ; coding: utf-8 -*-
# MyVoices.spec — Configuración de PyInstaller
#
# Genera un bundle en modo --onedir (carpeta).
# El ejecutable final queda en: dist/MyVoices/MyVoices.exe
#
# Para compilar:  pyinstaller MyVoices.spec --noconfirm
# O simplemente: build.bat

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

def safe_collect(pkg, **kwargs):
    """collect_data_files ignorando paquetes no instalados."""
    try:
        return collect_data_files(pkg, **kwargs)
    except Exception:
        return []

# Paquetes que necesitan sus .py disponibles en tiempo de ejecución
# (torch.jit.script e inspect.getsource los leen desde disco)
tts_datas       = safe_collect("TTS",       include_py_files=True)
trainer_datas   = safe_collect("trainer",   include_py_files=True)
typeguard_datas = safe_collect("typeguard", include_py_files=True)
inflect_datas   = safe_collect("inflect",   include_py_files=True)

# Paquetes con archivos de datos (lexicons, tablas de idioma, configs…)
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

# soundfile: necesita libsndfile-1.dll en Windows
soundfile_datas = safe_collect("soundfile")
soundfile_libs  = collect_dynamic_libs("soundfile")

# torch: incluir DLLs CUDA para que torch.cuda.is_available() funcione en el exe
torch_libs = collect_dynamic_libs("torch")

# Piper TTS — piper_phonemize incluye espeak-ng data (phontab, etc.)
piper_phonemize_datas = safe_collect("piper_phonemize")
piper_datas           = safe_collect("piper")
onnxruntime_datas     = safe_collect("onnxruntime")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[
        *soundfile_libs,   # libsndfile-1.dll
        *torch_libs,       # torch_cuda.dll, c10_cuda.dll, caffe2_nvrtc.dll…
    ],
    datas=[
        ("static", "static"),
        ("appicon.ico", "."),   # icono disponible en _MEIPASS
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
        *soundfile_datas,
        *piper_phonemize_datas,
        *piper_datas,
        *onnxruntime_datas,
    ],
    hiddenimports=[
        # uvicorn
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
        # starlette / fastapi
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
        "multipart",
        "multipart.multipart",
        # PyTorch
        "torch",
        "torch.nn",
        "torch.nn.functional",
        "torch.utils",
        "torch.utils.data",
        "torchaudio",
        "torchaudio.transforms",
        # Coqui TTS
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
        # transformers
        "transformers",
        "transformers.models",
        "transformers.models.auto",
        # scipy
        "scipy",
        "scipy.signal",
        "scipy.io",
        "scipy.io.wavfile",
        "scipy.special._ufuncs",
        "scipy.linalg.blas",
        "scipy.linalg.lapack",
        "scipy.linalg._fblas",
        "scipy.linalg._flapack",
        # pygame
        "pygame",
        "pygame.mixer",
        # utilidades
        "numpy",
        "pydantic",
        "pydantic.v1",
        "requests",
        "charset_normalizer",
        "aiofiles",
        "h11",
        "httptools",
        "websockets",
        "database",
        # soundfile
        "soundfile",
        "_soundfile",
        # Piper TTS
        "piper",
        "piper.voice",
        "piper_phonemize",
        "onnxruntime",
        "onnxruntime.capi._pybind_state",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["numba", "llvmlite"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=True,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MyVoices",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="appicon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MyVoices",
)
