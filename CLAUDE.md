# MyVoices — Notas para Claude

Proyecto: app de escritorio TTS Windows (Python + FastAPI + pywebview), con
servidor MCP integrado, motores **XTTSv2** (Coqui), **Piper**, **F5-TTS** y
**Chatterbox**. Los datos del usuario viven en `%APPDATA%/MyVoices/`.

## Reglas de trabajo (no necesito recordatorios)

Estas reglas aplican **siempre**, sin que el usuario las tenga que pedir.

### 1. Tests unitarios
- Si toco código en `server.py`, `database.py`, `mcp_tools.py` o `static/index.html`,
  añado o actualizo tests en `tests/`.
- Los tests corren con `venv/Scripts/python.exe -m pytest -q`. No requieren GPU
  ni modelos descargados (el servidor arranca con `SKIP_MODEL_LOAD=1`).
- Antes de hacer commit corro toda la suite. Si fallan, no commiteo.
- Suite actual: ~214 tests en `tests/test_api.py` y `tests/test_mcp_integration.py`.

### 2. Linting
- Ruff debe pasar limpio. Antes de commit corro `venv/Scripts/python.exe -m ruff check .`
  (lo arregla `--fix`). El CI falla si ruff no pasa.

### 3. Documentación
- Cambios en API REST, MCP tools, motores TTS o flujo de UI requieren actualizar
  **los dos READMEs** (`README.md` y `README.es.md`) y la pestaña **Ayuda** en
  `static/index.html` (la sección con `id="tab-help"`).
- Cambios en build o setup requieren actualizar `BUILD_GUIDE.md` y
  `GUIA_EJECUTABLE.md`.

### 4. Diagnóstico de errores
- **Tengo tools MCP** (`get_logs`, `get_diagnostics`, `load_model`, `set_verbose`)
  que me permiten ver el estado real de la app. Las uso ANTES de pedir al
  usuario que copie logs.
- Si la herramienta MCP no está conectada (porque la app está cerrada o el
  build fresco), leo la DB directamente con sqlite3 desde `%APPDATA%/MyVoices/myvoices.db`.
- Para errores nuevos, activo verbose: `set_verbose(true)`, reproduzco, leo
  `get_logs(level="ERROR")`, restauro `set_verbose(false)`.

### 5. Compatibilidad de paquetes (zona caliente)
- `transformers==4.46.3` es el punto dulce: tiene `BeamSearchScorer` +
  `GPT2PreTrainedModel` (TTS) Y `MinPLogitsWarper` (Chatterbox). NO subir.
- `numpy<2.0` y `networkx<3.0` son requisitos de gruut. NO subir.
- Imports de `f5_tts.api` y `chatterbox.tts` van **DESPUÉS** del parche de
  torchaudio en `server.py` — antes causa segfault.
- F5-TTS necesita `>=1.1.20` (versiones anteriores requieren `pydantic<=2.10.6`
  que rompe MCP).

### 6. PyInstaller
- Cambios en deps suelen requerir actualizar `MyVoices.spec` (`hiddenimports` y
  `datas` con `safe_collect("nombre_paquete")`).
- **Paquetes que usan `@torch.jit.script`** (F5-TTS / `x_transformers` /
  `vocos` / `torchdiffeq` / `ema_pytorch` / `conformer` / `chatterbox`) **DEBEN**
  declararse con `include_py_files=True`. TorchScript hace `inspect.getsource()`
  en runtime y necesita los `.py` originales — no solo bytecode.
- **Paquetes con datos pretrained** (perth: `perth_net_250000.pth.tar` +
  `hparams.yaml`; gruut_lang_*: lexicons; piper_phonemize: espeak-ng data) deben
  estar en `datas` para que PyInstaller los copie a `_internal/`.
- Si el .exe falla con `OSError: Can't get source for <function X>` o
  `AssertionError` opaco al cargar un motor → casi siempre falta un paquete en
  `datas` o falta `include_py_files=True`.
- **`mcp_server.exe`** es un segundo target en el spec (onefile, sin torch/TTS).
  `build.bat` lo mueve a `dist\MyVoices\` tras la compilación. Si se añaden
  dependencias a `mcp_tools.py`, actualizar `hiddenimports` del bloque `mcp_a`
  en el spec.
- **Para el DXT**: `dxt/manifest.json` y `mcp_server.py` están en `datas` del
  target principal porque `api_export_dxt` los lee en tiempo de ejecución.

### 7. DXT (Claude Desktop Extension) — zona delicada
- El `.dxt` se genera desde la app con `GET /api/export/dxt` o desde CLI con
  `python make_dxt.py`. Contiene `manifest.json` + `mcp_server.py`.
- **`type: "binary"` en el manifest FALLA validación** si el binario no está
  bundleado dentro del ZIP. Usar `type: "python"` + `entry_point: "mcp_server.py"`
  (archivo sí incluido) y sobreescribir el comando en `mcp_config.command` con
  `${user_config.myvoices_dir}\\mcp_server.exe`. Claude Desktop ejecuta el
  `command`, no el `entry_point` como script Python.
- Si Claude Desktop da "server: Required" → el bloque `server` es inválido
  (falta `entry_point` o la estructura no pasa el schema 0.3).
- El usuario configura la carpeta `dist\MyVoices\` al instalar el `.dxt`.

### 8. F5-TTS — comportamiento de ref_text
- F5-TTS recorta el audio de referencia a **12 s** internamente
  (`preprocess_ref_audio_text`). `_get_f5_ref_text()` transcribe los primeros
  12 s con Whisper + hint de idioma y cachea el resultado en
  `VOICES_DIR/<stem>.<lang>.txt`.
- Si el sidecar no corresponde al audio real → salida ininteligible. El sistema
  de versiones en `.f5_cache_version` invalida los sidecars automáticamente
  al arrancar si cambia la lógica de transcripción.
- **El acento inglés de F5-TTS no es un bug**: `F5TTS_v1_Base` fue entrenado
  principalmente en inglés/chino. Para español de calidad usar XTTSv2 o
  Chatterbox. Hay un aviso en la UI del tab F5-TTS.

### 9. Clientes MCP — diferencias de formato
- `_MCP_CLIENT_TEMPLATES` (server.py) define 10 clientes. `_render_snippet()`
  genera el JSON/bash para cada uno.
- **VS Code Copilot** usa clave raíz `"servers"` (no `"mcpServers"`) y requiere
  `"type": "http"` explícito dentro de la entrada. Es diferente de todos los
  demás clientes HTTP.
- **Cline y Windsurf** usan el mismo formato que Cursor (`"mcpServers"`, sin
  `"type"`).
- El test `test_mcp_clients_lists_all_supported` mantiene el set exacto de IDs.
  Al añadir un cliente nuevo, actualizar ese test.

### 10. Commits
- Mensaje en inglés, formato corto (1ª línea < 80 chars). Cuerpo opcional con
  el WHY. Footer con `Co-Authored-By: Claude ...`.
- Hago commit y push solo cuando los tests pasan y el ruff está limpio.
- Si toco la rama `main` directamente está OK (es proyecto personal del usuario).

### 11. Comunicación
- Respuestas concisas en español. Sin emojis a menos que el usuario los use.
- No narro lo que estoy a punto de hacer en exceso. Reporto cambios y resultado.
- Cuando termino una tarea con un follow-up natural (ej: añadir tests para una
  nueva feature ya está incluido en mi flujo), no lo ofrezco — lo hago.

## Comandos rápidos del proyecto

```bash
# Ejecutar app en modo dev
venv/Scripts/python.exe main.py

# Tests
venv/Scripts/python.exe -m pytest -q

# Lint
venv/Scripts/python.exe -m ruff check . --fix

# Build .exe (interactivo)
build.bat

# Generar MyVoices.dxt (sin compilar el bundle completo)
venv/Scripts/python.exe make_dxt.py

# Leer logs de la app (sin pasar por MCP)
python -c "import sqlite3, os; c = sqlite3.connect(os.path.expandvars(r'%APPDATA%\MyVoices\myvoices.db')); c.row_factory = sqlite3.Row; [print(f\"[{r['level']}] {r['ts']}  {r['message'][:300]}\") for r in c.execute('SELECT * FROM logs ORDER BY id DESC LIMIT 50')]"
```

## Hooks de validación automática (opcional pero recomendado)

El proyecto incluye scripts en `.claude/hooks/` que ejecutan ruff + pytest:
- En cada **Stop** (fin de turno) si hay `.py` modificados → bloquea con feedback si falla.
- Antes de cualquier `git commit *` → bloquea el commit si falla.

Para activarlos en una máquina nueva, añade este bloque a `.claude/settings.json`
(merge con tus permisos existentes):

```json
{
  "hooks": {
    "Stop": [{
      "hooks": [{
        "type": "command",
        "shell": "bash",
        "command": "bash .claude/hooks/validate_hook.sh stop",
        "timeout": 90,
        "statusMessage": "Validando con ruff + pytest"
      }]
    }],
    "PreToolUse": [{
      "matcher": "Bash",
      "hooks": [{
        "type": "command",
        "shell": "bash",
        "if": "Bash(git commit*)",
        "command": "bash .claude/hooks/validate_hook.sh pretool",
        "timeout": 90,
        "statusMessage": "Validando antes del commit (ruff + pytest)"
      }]
    }]
  }
}
```

Tras añadirlo, abre `/hooks` una vez en Claude Code (o reinicia) para que los
detecte. El `.claude/settings.json` está gitignored (es personal). Los scripts
en `.claude/hooks/` sí se versionan.

## Glosario de archivos

- `server.py` — FastAPI app + lógica TTS + MCP HTTP. Punto de entrada del backend.
- `database.py` — SQLite (config, voces, presets, frases, logs, webhooks).
- `mcp_tools.py` — Definición compartida de tools MCP (stdio + HTTP).
- `mcp_server.py` — Entry point para modo stdio. También se bundlea en el `.dxt`
  como `entry_point` para pasar validación del schema DXT.
- `main.py` — Lanzador desktop (splash + uvicorn + pywebview).
- `static/index.html` — UI (1 archivo, vanilla JS, no build step).
- `MyVoices.spec` — PyInstaller config. Incluye dos targets: `MyVoices` (onedir)
  y `mcp_server` (onefile). `build.bat` mueve el segundo a `dist\MyVoices\`.
- `build.bat` — Build script Windows interactivo.
- `dxt/manifest.json` — Manifest del DXT para Claude Desktop. Versionado;
  incluir en `datas` del spec para que `api_export_dxt` lo encuentre en el bundle.
- `make_dxt.py` — Genera `MyVoices.dxt` (ZIP con manifest + mcp_server.py).
- `tests/test_api.py` — Tests de API REST, DB y features generales.
- `tests/test_mcp_integration.py` — Tests del sistema MCP (toggle, snippets,
  clientes, test de conexión).
