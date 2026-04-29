# MyVoices

[Español](README.es.md) · **English**

Desktop TTS app for streaming. Reads text with cloned voices using **XTTSv2** (GPU/CPU) and **Piper TTS** (lightweight, no GPU). Integrates with SAMMI and other systems via REST API.

## Features

- **Two TTS engines**: XTTSv2 (voice cloning, high quality) and Piper TTS (fast, no GPU)
- **Voice presets**: combine a voice with speed, pitch, language and radio effect; save under a name
- **Per-preset language**: XTTS language is configured per preset, not globally
- **Simple REST API**: just `voice` + `text` — no technical parameters
- **Saved phrases**: library of texts attached to a preset; playable by name via API; saving with an existing name updates the phrase (upsert)
- **Audio download**: the *Download audio* button saves **exactly the last played WAV** from a server-side cache — no re-synthesis
- **Help tab**: built-in workflow diagram (clone voice → preset → test/save/API)
- **Radio effect**: bandpass 400–3400 Hz + soft clipping + noise
- **Test panel**: pick a preset, listen and download the result
- **Splash screen**: animated progress bar during startup while the model loads
- **Log viewer**: activity log with auto-refresh, level filter and automatic rotation
- **Tests**: 121 unit and integration tests (DB, utils, API CRUD, UI markup), runnable without GPU
- **CI**: GitHub Actions runs ruff + pytest on every push and PR

---

## Prerequisites

### Microsoft C++ Build Tools
Required to compile native TTS dependencies.

1. Download [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
2. Select **"Desktop development with C++"**
3. Install and reboot if prompted

---

## Installation (development mode)

```bash
# 1. Clone the repository
git clone https://github.com/dataeschema/MyVoices.git
cd MyVoices

# 2. Create a virtual environment
python -m venv venv
venv\Scripts\activate

# 3. Install PyTorch with CUDA support (pick by GPU)
#    RTX 50xx (Blackwell) — CUDA 12.8:
pip install --upgrade --force-reinstall torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cu128

#    RTX 40xx / 30xx / 20xx — CUDA 12.4:
pip install --upgrade --force-reinstall torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cu124

# 4. Install the rest of the dependencies
pip install -r requirements.txt

# 5. Pin numpy and networkx (requirements may upgrade them; gruut needs the older versions)
pip install "numpy<2.0.0" "networkx<3.0.0"
```

> **No GPU?** Piper TTS works without a GPU. XTTSv2 is very slow on CPU.

---

## Running in development mode

```bash
venv\Scripts\activate
python main.py
```

A **splash screen** with an animated progress bar shows up while the XTTSv2 model loads. Once it's ready, the main window opens.

The first run downloads the XTTSv2 model (~2 GB) — takes several minutes.

The web panel is also available at: `http://localhost:8000`

---

## Tests

```bash
venv\Scripts\activate
pip install -r requirements-dev.txt   # first time only
pytest --cov
```

121 tests across four suites. No GPU and no downloaded models are required (the server boots in test mode without loading TTS).

---

## Building the executable (.exe)

`build.bat` is fully self-contained:

```bat
build.bat
```

The script:
1. Verifies Python 3.10+
2. Creates the venv if it doesn't exist
3. **Asks which GPU you have** (menu 1/2/3) and picks the right CUDA build
4. Installs PyTorch, `requirements.txt` and PyInstaller automatically
5. Re-pins `numpy<2.0` and `networkx<3.0` after the deps
6. Builds with PyInstaller

The final executable lives in `dist\MyVoices\MyVoices.exe`.

> See [GUIA_EJECUTABLE.md](GUIA_EJECUTABLE.md) for details and troubleshooting.

---

## REST API

### Speak text with a voice preset

```
POST http://localhost:8000/api/speak
Content-Type: application/json

{
  "voice": "preset_name",
  "text": "Hi chat, welcome to the stream!"
}
```

The synthesized WAV is cached server-side so you can grab the exact audio that played:

```
GET http://localhost:8000/api/speak/last     → returns the last WAV
```

### Download synthesized audio as WAV (re-synthesis)

```
POST http://localhost:8000/api/speak/download
Content-Type: application/json

{
  "voice": "preset_name",
  "text": "Text to synthesize"
}
```

Returns the WAV file directly (Content-Disposition: attachment).

### Play a saved phrase

```
POST http://localhost:8000/api/phrases/{name}/play
```

---

## Workflow

1. **XTTS2 tab** → upload a reference WAV → the voice gets registered with an ID
2. **Piper tab** → download a voice from the catalogue → registered automatically
3. **Main tab** → pick a voice, tune speed/pitch/language/radio → save as preset
4. Call the API with `{"voice": "preset_name", "text": "..."}` from SAMMI or any other system

The **Help** tab inside the app contains the same workflow as a visual diagram.

---

## User data

Everything persists across upgrades under `%APPDATA%\MyVoices\`:

```
%APPDATA%\MyVoices\
├── myvoices.db        ← DB with voices, presets, phrases and logs
├── voices\            ← WAV files for cloned XTTS voices
└── piper_voices\      ← Piper models (.onnx + .onnx.json)
```

The XTTSv2 model is stored in:
```
%USERPROFILE%\AppData\Local\tts\tts_models--multilingual--multi-dataset--xtts_v2\
```
