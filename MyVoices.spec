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

def safe_collect(pkg, exclude_patterns=None, **kwargs):
    """collect_data_files ignorando paquetes no instalados.
    `exclude_patterns`: lista de subcadenas; si alguna aparece en la ruta
    del fichero recolectado, lo descartamos (vía path-separator-agnostic)."""
    try:
        items = collect_data_files(pkg, **kwargs)
    except Exception:
        return []
    if exclude_patterns:
        norm = lambda p: p.replace("\\", "/").lower()
        return [
            (src, dst) for (src, dst) in items
            if not any(pat.lower() in norm(src) for pat in exclude_patterns)
        ]
    return items

# Paquetes que necesitan sus .py disponibles en tiempo de ejecución
# (torch.jit.script e inspect.getsource los leen desde disco).
# Excluímos demos/, notebooks/, recipes/ y server/ — son código de
# fine-tuning/ejemplos que no usamos en inferencia y disparan falsos
# positivos del antivirus por nombres como "gpt_train.py".
tts_datas       = safe_collect(
    "TTS",
    exclude_patterns=["/TTS/demos/", "/TTS/notebooks/",
                      "/TTS/recipes/", "/TTS/server/"],
    include_py_files=True,
)
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

# F5-TTS y x_transformers usan @torch.jit.script (TorchScript), que llama a
# inspect.getsource() y necesita los .py originales — no solo bytecode.
f5_tts_datas         = safe_collect("f5_tts",         include_py_files=True)
x_transformers_datas = safe_collect("x_transformers", include_py_files=True)
vocos_datas          = safe_collect("vocos",          include_py_files=True)
torchdiffeq_datas    = safe_collect("torchdiffeq",    include_py_files=True)
ema_pytorch_datas    = safe_collect("ema_pytorch",    include_py_files=True)
hydra_datas          = safe_collect("hydra")
omegaconf_datas      = safe_collect("omegaconf")
cached_path_datas    = safe_collect("cached_path")

# Chatterbox + perth (marca de agua) — perth incluye hparams.yaml y un
# checkpoint .pth.tar (~37 MB) en perth_net/pretrained/implicit/.
chatterbox_datas = safe_collect("chatterbox", include_py_files=True)
perth_datas      = safe_collect("perth")
s3tokenizer_datas = safe_collect("s3tokenizer")
diffusers_datas   = safe_collect("diffusers")
conformer_datas   = safe_collect("conformer", include_py_files=True)

# Tokenizadores multilingües que Chatterbox carga eagerly (no condicional al
# language_id pasado): chino (spacy_pkuseg + rjieba), japonés (pykakasi).
# spacy_pkuseg/dicts/default.pkl = 4.3 MB, pykakasi diccionarios ~10 MB.
spacy_pkuseg_datas = safe_collect("spacy_pkuseg")
pykakasi_datas     = safe_collect("pykakasi")
rjieba_datas       = safe_collect("rjieba")
jaconv_datas       = safe_collect("jaconv")

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
        # Fuentes para generar MyVoices.dxt desde la app (api_export_dxt)
        ("dxt/manifest.json", "dxt"),
        ("mcp_server.py", "."),   # entry_point del DXT — bundleado en el .zip
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
        # F5-TTS + deps que usan @torch.jit.script
        *f5_tts_datas,
        *x_transformers_datas,
        *vocos_datas,
        *torchdiffeq_datas,
        *ema_pytorch_datas,
        *hydra_datas,
        *omegaconf_datas,
        *cached_path_datas,
        # Chatterbox + perth (con checkpoint pretrained ~37 MB)
        *chatterbox_datas,
        *perth_datas,
        *s3tokenizer_datas,
        *diffusers_datas,
        *conformer_datas,
        *spacy_pkuseg_datas,
        *pykakasi_datas,
        *rjieba_datas,
        *jaconv_datas,
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
        # F5-TTS y dependencias
        "f5_tts",
        "f5_tts.api",
        "f5_tts.model",
        "f5_tts.infer.utils_infer",
        "x_transformers",
        "x_transformers.attend",
        "vocos",
        "torchdiffeq",
        "ema_pytorch",
        "hydra",
        "hydra.utils",
        "omegaconf",
        "cached_path",
        # Chatterbox y dependencias (perth incluye watermark + checkpoint)
        "chatterbox",
        "chatterbox.tts",
        "chatterbox.mtl_tts",
        "perth",
        "perth.perth_net",
        "perth.perth_net.perth_net_implicit",
        "s3tokenizer",
        "diffusers",
        "conformer",
        "spacy_pkuseg",
        "pykakasi",
        "rjieba",
        "jaconv",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["numba", "llvmlite", "wandb", "wandb_gql", "wandb_graphql"],
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

# ── mcp_server.exe ────────────────────────────────────────────────────────────
# Ejecutable independiente (--onefile) para el transporte stdio del DXT de
# Claude Desktop. Solo incluye httpx + mcp (FastMCP); sin torch ni TTS.
# Output: dist\mcp_server.exe → build.bat lo mueve a dist\MyVoices\.
mcp_a = Analysis(
    ["mcp_server.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        "mcp",
        "mcp.server",
        "mcp.server.fastmcp",
        "mcp.server.stdio",
        "mcp.server.models",
        "mcp.types",
        "mcp.shared",
        "mcp.shared.session",
        "httpx",
        "httpx._transports",
        "httpx._transports.default",
        "anyio",
        "anyio._backends._asyncio",
        "anyio._backends._trio",
        "anyio.abc",
        "pydantic",
        "pydantic.v1",
        "starlette.routing",
        "starlette.responses",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch", "torchaudio", "torchvision",
        "TTS", "pygame", "numpy", "PIL",
        "matplotlib", "scipy", "tkinter",
        "numba", "llvmlite", "wandb",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

mcp_pyz = PYZ(mcp_a.pure, mcp_a.zipped_data, cipher=block_cipher)

mcp_exe = EXE(
    mcp_pyz,
    mcp_a.scripts,
    mcp_a.binaries,
    mcp_a.zipfiles,
    mcp_a.datas,
    [],
    name="mcp_server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,   # servidor stdio — necesita consola
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
