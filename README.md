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
- **Tests**: 168 unit and integration tests (DB, utils, API CRUD, UI markup, MCP), runnable without GPU
- **CI**: GitHub Actions runs ruff + pytest on every push and PR
- **MCP server (built-in)**: a [Model Context Protocol](https://modelcontextprotocol.io) endpoint mounted at `/mcp/`, **toggleable from the UI**, with Bearer-token auth. Lets an LLM (Claude Desktop, Claude Code, Cursor, Gemini CLI, ChatGPT…) list voices, speak text, and play saved phrases. A legacy `mcp_server.py` (stdio) is also shipped for clients that need it

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

168 tests across five suites (DB, utils, API CRUD, UI markup, MCP). No GPU and no downloaded models are required (the server boots in test mode without loading TTS).

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
| `list_voices` | Registered voices (XTTS clones + Piper) |
| `list_presets` | Voice presets (voice + speed/pitch/lang/radio) |
| `list_phrases` | Saved phrases with their attached preset |
| `speak(voice, text)` | Synthesize and play `text` with the named preset |
| `play_phrase(name)` | Play a saved phrase by name |
| `download_last_audio` | Metadata for the last cached WAV |

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
