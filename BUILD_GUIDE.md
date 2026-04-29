# MyVoices — Desktop executable build guide

[Español](GUIA_EJECUTABLE.md) · **English**

How to turn MyVoices into a Windows `.exe` using **PyInstaller** and **pywebview**.

---

## Index

1. [Architecture](#1-architecture)
2. [Prerequisites](#2-prerequisites)
3. [Build the executable](#3-build-the-executable)
4. [Bundle layout](#4-bundle-layout)
5. [Distribution](#5-distribution)
6. [First run](#6-first-run)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Architecture

```
main.py
  │  Shows a splash screen with progress bar
  │  Imports server.py in a daemon thread (torch + TTS model)
  │  Starts uvicorn in a daemon thread
  │  Waits for the server to respond (up to 3 min)
  └─► pywebview (Edge WebView2) ──► http://127.0.0.1:8000
                                           │
                                     server.py (FastAPI)
                                           │
                                     database.py (SQLite)
                                     %APPDATA%\MyVoices\
                                       ├── myvoices.db
                                       ├── voices\
                                       └── piper_voices\
```

**Startup flow:**
1. `main.py` opens a frameless window (splash) immediately
2. In the background: imports `server.py` (torch + TTS model) → animates the progress bar
3. Starts uvicorn → waits for response → creates the main window → closes the splash

**User data** (survives upgrades):
- `%APPDATA%\MyVoices\myvoices.db` — voices, presets, saved phrases, activity logs
- `%APPDATA%\MyVoices\voices\` — WAV files of cloned voices (XTTS2)
- `%APPDATA%\MyVoices\piper_voices\` — Piper TTS models (.onnx + .onnx.json)

---

## 2. Prerequisites

### Python 3.10 or higher
```bash
python --version  # must show 3.10.x or higher
```

### Microsoft C++ Build Tools
Required for native dependencies. Download: [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/).  
Select **"Desktop development with C++"**.

### Edge WebView2 Runtime (target machine)
Bundled with Windows 10 (v1803+) and Windows 11 by default.  
If missing: [Microsoft Edge WebView2](https://developer.microsoft.com/en-us/microsoft-edge/webview2/)

> **PyTorch, CUDA and the rest of the dependencies are installed automatically by `build.bat`** — you don't need to install them manually.

---

## 3. Build the executable

### Option A — Automatic script (recommended)

Double-click `build.bat` from the project folder (or run it from a terminal).

The script does everything on its own:

1. Verifies Python 3.10+ is on the PATH
2. Creates the `venv` virtual environment if it doesn't exist
3. **Asks which GPU you have on the first run** and saves the choice in `.build_config`. Subsequent builds don't ask again:
   ```
   Select your GPU:
     [1] RTX 50xx (Blackwell)        - CUDA 12.8
     [2] RTX 20xx / 30xx / 40xx      - CUDA 12.4  (recommended for most)
     [3] No GPU / CPU only
   ```
4. Detects whether PyTorch is already installed with the right CUDA version and **skips reinstall when it matches** (the full reinstall pulls ~5 GB; skipping cuts incremental builds dramatically)
5. Installs `requirements.txt` (already pins `numpy<2.0` and `networkx<3.0`)
6. Installs `requirements-dev.txt` (includes `pyinstaller>=6.0`, `pytest`, `ruff`)
7. Kills `MyVoices.exe` only if it's actually running
8. Cleans previous builds (`dist\MyVoices\`, `build\`)
9. Compiles using `MyVoices.spec` with `--clean` (avoids stale cache issues)
10. Reports total duration and bundle size on success

```bat
build.bat
```

#### Optional flags

| Flag | What it does |
|---|---|
| `--reset-gpu` | Forget the cached GPU in `.build_config` and ask again |
| `--skip-deps` | Skip PyTorch + `requirements.txt` + `requirements-dev.txt`. Useful when only `static/index.html` or the `.spec` changed |
| `--ci` | Non-interactive mode: no `pause`, no prompts; fails if `.build_config` is missing |

The final executable lives at: `dist\MyVoices\MyVoices.exe`

### Option B — Manual

```bash
# 1. Create and activate the virtual environment
python -m venv venv
venv\Scripts\activate

# 2. Install PyTorch (pick by GPU)
#    RTX 50xx (Blackwell):
pip install --upgrade --force-reinstall torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cu128

#    RTX 40xx and earlier:
pip install --upgrade --force-reinstall torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cu124

# 3. Install dependencies and PyInstaller
pip install -r requirements.txt
pip install "numpy<2.0.0" "networkx<3.0.0"
pip install "pyinstaller>=6.0"

# 4. Clean previous builds (optional)
rmdir /s /q dist\MyVoices build

# 5. Compile
pyinstaller MyVoices.spec --noconfirm
```

---

## 4. Bundle layout

```
dist\MyVoices\
├── MyVoices.exe          ← double-click to launch
└── _internal\
    ├── static\
    │   └── index.html     ← packaged web UI
    ├── torch\             ← PyTorch (~3-5 GB with CUDA)
    ├── TTS\               ← Coqui TTS + XTTSv2
    ├── piper\             ← Piper TTS (ONNX)
    ├── pygame\            ← audio playback
    └── ...
```

> **Important:** to move or distribute the app, copy **the entire `dist\MyVoices\` folder**, never the `.exe` alone.

---

## 5. Distribution

1. Copy the full `dist\MyVoices\` folder to the target machine
2. On the first run the machine needs Internet access to download the XTTSv2 model (~2 GB)
3. Piper voices and cloned WAV voices are saved in `%APPDATA%\MyVoices\` and persist across versions

### Inno Setup installer (optional)

```iss
[Setup]
AppName=MyVoices
AppVersion=2.0
DefaultDirName={autopf}\MyVoices

[Files]
Source: "dist\MyVoices\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{autodesktop}\MyVoices"; Filename: "{app}\MyVoices.exe"
```

---

## 6. First run

1. **Windows Defender SmartScreen** may ask for confirmation. Click **"More info" → "Run anyway"**.

2. The app shows a **splash screen** with an animated progress bar while loading. There is no blank screen.

3. On the first launch the XTTSv2 model is downloaded (~2 GB) before the main window appears. Takes several minutes depending on your connection.

4. The app **does not show a console** — logs are read from the in-app viewer (section "Activity log") or from `%APPDATA%\MyVoices\startup.log`.

5. User data is stored in:
   ```
   %APPDATA%\MyVoices\
   ├── myvoices.db        ← all configuration (voices, presets, phrases)
   ├── voices\            ← uploaded WAV files (XTTS2)
   └── piper_voices\      ← downloaded Piper models
   ```

6. The XTTSv2 model is stored in:
   ```
   %USERPROFILE%\AppData\Local\tts\tts_models--multilingual--multi-dataset--xtts_v2\
   ```

---

## 7. Troubleshooting

### The exe closes immediately / blank screen

The startup log is saved automatically at:
```
%APPDATA%\MyVoices\startup.log
```
Open it with any text editor to see the exact error. You can also run from a terminal to see messages:
```bash
dist\MyVoices\MyVoices.exe
```

### "No module named 'xxx'"

Add the module to `hiddenimports` in `MyVoices.spec`:
```python
hiddenimports=[
    ...
    "module_name",
],
```
Then rebuild with `build.bat`.

### XTTS loads on CPU instead of GPU

Open the **log viewer** in the UI and look for CUDA messages. Most common causes:

**Wrong GPU selected in build.bat**  
Run `build.bat` again and pick the correct option:
- RTX 50xx → option `1` (CUDA 12.8)
- RTX 40xx / 30xx / 20xx → option `2` (CUDA 12.4)

**Outdated driver or CUDA**  
Update NVIDIA drivers from [nvidia.com/drivers](https://www.nvidia.com/drivers).

**Guaranteed fallback:** the model always loads on CPU if the GPU isn't compatible (slower but functional). Piper TTS doesn't require a GPU and works correctly in any case.

### numpy / networkx incompatible with gruut

Symptom: import errors in TTS related to gruut, numpy, or networkx.

```bash
venv\Scripts\activate
pip install "numpy<2.0.0" "networkx<3.0.0"
```

The version constraints (`numpy<2.0.0`, `networkx<3.0.0`) are pinned directly in `requirements.txt`, so `pip install -r requirements.txt` keeps the compatible versions automatically.

### The window doesn't open (server timeout)

The server took longer than 3 minutes. May happen on the first run (model download) or on slow machines.  
Edit `main.py` and increase the timeout:
```python
if not _wait_for_server(status_url, timeout=300.0):  # 5 minutes
```
Then rebuild with `build.bat`.

### Edge WebView2 not found

Install the runtime from:  
https://developer.microsoft.com/en-us/microsoft-edge/webview2/

### PyTorch fails on the manual build

PyTorch must be installed **in the same environment** as PyInstaller.  
Use `build.bat` so everything is done in the same venv automatically.

### XTTSv2 model doesn't download

Check Internet connection. The model is downloaded to:
```
%USERPROFILE%\AppData\Local\tts\tts_models--multilingual--multi-dataset--xtts_v2\
```

### Migrating from a previous version (ChatVoice)

If you had the older version installed, MyVoices automatically detects the old database and renames it to `myvoices_backup.db`. The new install starts with a clean database.  
WAV voices in `%APPDATA%\ChatVoice\voices\` are automatically copied to `%APPDATA%\MyVoices\voices\` on the first launch.

---

## Notes

- **Bundle size:** ~5-8 GB (mostly PyTorch + TTS)
- **No visible console:** `console=False` in `MyVoices.spec`. Logs are read from the UI or from `%APPDATA%\MyVoices\startup.log`.
- **Update without rebuilding:** for changes to `static/index.html`, just replace the file at `dist\MyVoices\_internal\static\`. For Python changes, you must rebuild with `build.bat`.
- **Python version:** the build must use the same Python version as the virtual environment.
- **build.bat is idempotent:** you can run it multiple times safely; it reuses the existing venv and only reinstalls what's needed.
