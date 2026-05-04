# MyVoices

[Español](README.es.md) · **English**

Desktop TTS app for streaming. Reads text with cloned voices using four engines: **XTTSv2**, **Piper TTS**, **F5-TTS** and **Chatterbox TTS**. Integrates with SAMMI and other systems via REST API and MCP.

## Features

- **Four TTS engines** — pick the right trade-off for each voice:
  - **XTTSv2** — multilingual voice cloning (17 languages), high quality, requires GPU
  - **Piper TTS** — lightweight neural voices from a catalogue, no GPU needed
  - **F5-TTS** — voice cloning from a 3-12 s WAV, optimised for English and Chinese (~3 GB download)
  - **Chatterbox** — multilingual cloning (23 languages), very fast, includes imperceptible watermark
- **Voice presets**: combine a voice with speed, pitch, language and radio effect; save under a name
- **Per-preset language**: XTTS and Chatterbox respect the language set in the preset; F5-TTS works best for English/Chinese regardless of preset language
- **Simple REST API**: just `voice` + `text` — no technical parameters
- **Saved phrases**: library of texts attached to a preset; playable by name via API; saving with an existing name updates the phrase (upsert)
- **Audio export**: synthesize and download in **WAV, MP3 or OGG**; or grab the last played audio without re-synthesis
- **Help tab**: built-in workflow diagram (clone voice → preset → test/save/API)
- **Radio effect**: bandpass 400–3400 Hz + soft clipping + noise
- **Test panel**: pick a preset, listen and download the result
- **Splash screen**: animated progress bar during startup while the model loads
- **Log viewer**: activity log with auto-refresh, level/origin filters, and columns — caller (MCP/API/UI), voice preset, text preview and synthesis duration
- **Priority queue**: TTS requests are serialised through an `asyncio.PriorityQueue`; MCP/API calls take priority over UI and saved-phrase requests
- **Webhook notifications**: register HTTP endpoints to receive `speak_end` events with voice, text, caller and duration; manageable from the UI
- **Verbose mode**: toggle DEBUG logging + full tracebacks via the UI, API or MCP tool; also available at launch via `MYVOICES_VERBOSE=1`
- **Diagnostic endpoint**: `/api/diagnostics` (and MCP tool `get_diagnostics`) returns per-engine availability, import errors, and installed package versions
- **Tests**: 206 unit and integration tests (DB, utils, API CRUD, UI markup, MCP), runnable without GPU
- **CI**: GitHub Actions runs ruff + pytest on every push and PR
- **MCP server (built-in)**: a [Model Context Protocol](https://modelcontextprotocol.io) endpoint mounted at `/mcp/`, **toggleable from the UI**, with Bearer-token auth. Lets an LLM (Claude Desktop, Claude Code, Cursor, Gemini CLI, ChatGPT…) list voices, speak text, and play saved phrases. A legacy `mcp_server.py` (stdio) is also shipped for clients that need it

---

## TTS engines at a glance

| Engine | Voice cloning | Languages | GPU | Notes |
|---|---|---|---|---|
| **XTTSv2** | WAV 10–30 s | 17 | Required for speed | Best multilingual quality |
| **Piper** | No (catalogue voices) | Per-model | Not required | Fastest, lowest VRAM |
| **F5-TTS** | WAV 3–12 s | EN/ZH best | ≥12 GB VRAM | English/Chinese; other languages may sound English-accented |
| **Chatterbox** | WAV 5+ s | 23 | 4–6 GB VRAM | Adds imperceptible watermark (Perth/Resemble AI) |

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

# 4. Install the rest of the dependencies (XTTSv2 + Piper included)
pip install -r requirements.txt
```

### Optional: F5-TTS and Chatterbox

F5-TTS and Chatterbox are not in `requirements.txt` because they have heavy
optional dependencies. Install them only if you intend to use them:

```bash
# F5-TTS — requires >=1.1.20 to avoid pydantic conflict
pip install "f5-tts>=1.1.20"

# Chatterbox — install without deps to avoid torch version conflict
pip install chatterbox-tts --no-deps
pip install resemble-enhance  # audio enhancement used by Chatterbox
```

> **No GPU?** Piper TTS works without a GPU. XTTSv2 is very slow on CPU. F5-TTS and Chatterbox require a CUDA GPU.

---

## Running in development mode

```bash
venv\Scripts\activate
python main.py
```

A **splash screen** with an animated progress bar shows up while the XTTSv2 model loads. Once it's ready, the main window opens.

The first run downloads the XTTSv2 model (~2 GB) — takes several minutes.
F5-TTS (~3 GB) and Chatterbox (~1-2 GB) are downloaded on first use.

The web panel is also available at: `http://localhost:8000`

---

## Tests

```bash
venv\Scripts\activate
pip install -r requirements-dev.txt   # first time only
pytest --cov
```

206 tests across five suites (DB, utils, API CRUD, UI markup, MCP). No GPU and no downloaded models are required (the server boots in test mode without loading TTS).

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
5. Builds with PyInstaller

The final executable lives in `dist\MyVoices\MyVoices.exe`.

> See [BUILD_GUIDE.md](BUILD_GUIDE.md) for details and troubleshooting.

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

### Download synthesized audio (WAV / MP3 / OGG)

```
POST http://localhost:8000/api/speak/download?format=mp3
Content-Type: application/json

{
  "voice": "preset_name",
  "text": "Text to synthesize"
}
```

`format` accepts `wav` (default), `mp3` or `ogg`. WAV is passthrough; MP3/OGG
require `ffmpeg` on PATH (mp3 at 192 kbps, ogg via libvorbis).

To download the last played audio without re-synthesis:

```
GET http://localhost:8000/api/speak/last?format=mp3
```

### Play a saved phrase

```
POST http://localhost:8000/api/phrases/{name}/play
```

### Webhooks

Register an HTTP endpoint to receive events when synthesis completes:

```
GET    http://localhost:8000/api/webhooks           → list registered webhooks
POST   http://localhost:8000/api/webhooks           → add a webhook
DELETE http://localhost:8000/api/webhooks/{id}      → remove a webhook
POST   http://localhost:8000/api/webhooks/test/{id} → fire a test event
```

**Add a webhook:**
```json
POST /api/webhooks
{ "url": "https://your-server/hook", "events": "speak_end" }
```

**Payload sent on `speak_end`:**
```json
{
  "event": "speak_end",
  "job_id": "a1b2c3d4",
  "voice": "preset_name",
  "text": "first 120 chars of the text",
  "caller": "MCP",
  "duration_ms": 1240
}
```

`caller` is one of `MCP`, `API` or `UI`.  
`events` can be `speak_end` or `*` (all events).

---

## MCP server (LLM integration)

MyVoices exposes a [Model Context Protocol](https://modelcontextprotocol.io) endpoint so an LLM (Claude, Cursor, Gemini, ChatGPT…) can list voices, speak text and trigger saved phrases via tool calls.

There are two transports — pick whichever your client supports best:

### HTTP — built into the app (recommended)

1. Open MyVoices, go to the **Main tab → 🤖 Servidor MCP** card and flip the toggle.
2. The card shows the URL (`http://localhost:8000/mcp/`) and a Bearer token (auto-generated on first activation).
3. Open the **Help tab**, pick your client from the buttons, and copy the auto-rendered config snippet — URL, token and absolute paths are filled in for you.

The endpoint is gated by the toggle (returns `503` when off) and by `Authorization: Bearer <token>` (returns `401` on mismatch).

### stdio — legacy, for clients that don't speak HTTP MCP

Run `python mcp_server.py` as a subprocess from your client config. The script just forwards calls to the local REST API, so the MyVoices app must be running.

### Tools exposed

| Tool | What it does |
|---|---|
| `get_status` | Server health: TTS engine, device, voice/preset counts |
| `list_voices` | Registered voices (all engines) |
| `list_presets` | Voice presets (voice + speed/pitch/lang/radio) |
| `list_phrases` | Saved phrases with their attached preset |
| `speak(voice, text)` | Synthesize and play `text` with the named preset |
| `play_phrase(name)` | Play a saved phrase by name |
| `download_last_audio` | Metadata for the last cached WAV |
| `get_logs` | Last N logs filtered by level, caller and substring |
| `get_diagnostics` | Full state: engines, import errors, package versions |
| `load_model` | Lazy-load a TTS engine (`xtts`/`f5tts`/`chatterbox`) |
| `set_verbose` | Toggle verbose mode (DEBUG + full tracebacks) |

### Supported clients

| Client | Transport | Where to put the snippet |
|---|---|---|
| Claude Desktop | HTTP or stdio | `%APPDATA%\Claude\claude_desktop_config.json` |
| Claude Code (CLI) | HTTP | `claude mcp add myvoices --transport http …` |
| Cursor | HTTP | `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global) |
| Gemini CLI | HTTP | `~/.gemini/mcp.json` |
| ChatGPT (Connectors) | HTTP | Settings → Connectors → Add MCP Server (plan-dependent) |
| Cline | stdio | Cline settings UI |
| Generic HTTP | HTTP | URL + `Authorization: Bearer <token>` header |

The Help tab inside MyVoices shows a copy-paste-ready snippet for each client, with URL, token and paths already substituted.

### Smoke test from a terminal

```bash
# Activate MCP from the UI first, then grab the token from the card.
TOKEN="<paste here>"
curl -X POST http://localhost:8000/mcp/ \
     -H "Accept: application/json, text/event-stream" \
     -H "Authorization: Bearer $TOKEN" \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}'
```

---

## Workflow

1. **XTTS2 tab** → upload a reference WAV (10–30 s) → voice registered with an ID
2. **Piper tab** → download a voice from the catalogue → registered automatically
3. **F5-TTS tab** → upload a reference WAV (3–12 s) → voice registered (English/Chinese recommended)
4. **Chatterbox tab** → upload a reference WAV (5+ s) → voice registered (23 languages)
5. **Main tab** → pick a voice, tune speed/pitch/language/radio → save as preset
6. Call the API with `{"voice": "preset_name", "text": "..."}` from SAMMI or any other system
7. (Optional) Register webhooks in the **Webhooks** panel to receive `speak_end` events in external systems (OBS, Home Assistant, n8n…)

The **Help** tab inside the app contains the same workflow as a visual diagram.

---

## Verbose mode and diagnostics

When a TTS engine fails to load or you hit an opaque error:

```bash
# Enable verbose mode (DEBUG level + full tracebacks)
curl -X POST http://localhost:8000/api/verbose/true

# Or from an MCP client:
# tool: set_verbose(enabled=true)

# Inspect the full engine state and any import errors
curl http://localhost:8000/api/diagnostics
# MCP equivalent: tool: get_diagnostics

# Read the last 50 errors
curl 'http://localhost:8000/api/logs?level=ERROR&limit=50'
```

`get_diagnostics` returns per-engine: availability, status, and the
`import_error` (with traceback) if the import failed. Also the installed
versions of torch, transformers, TTS, f5-tts and chatterbox.

You can also enable verbose at launch via env var `MYVOICES_VERBOSE=1`.

---

## User data

Everything persists across upgrades under `%APPDATA%\MyVoices\`:

```
%APPDATA%\MyVoices\
├── myvoices.db        ← DB with voices, presets, phrases and logs
├── voices\            ← WAV files for cloned voices (XTTS, F5-TTS, Chatterbox)
└── piper_voices\      ← Piper models (.onnx + .onnx.json)
```

The XTTSv2 model is stored in:
```
%USERPROFILE%\AppData\Local\tts\tts_models--multilingual--multi-dataset--xtts_v2\
```

F5-TTS and Chatterbox models are cached in the default Hugging Face cache
(`%USERPROFILE%\.cache\huggingface\hub\`).
