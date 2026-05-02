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
- Cambios en deps suelen requerir actualizar `MyVoices.spec` (`hiddenimports` o
  `datas` con `safe_collect("nombre_paquete")`). Si añado un nuevo motor TTS
  opcional, lo dejo fuera del spec para no inflar el bundle (el usuario lo
  instala con `pip` post-build).

### 7. Commits
- Mensaje en inglés, formato corto (1ª línea < 80 chars). Cuerpo opcional con
  el WHY. Footer con `Co-Authored-By: Claude ...`.
- Hago commit y push solo cuando los tests pasan y el ruff está limpio.
- Si toco la rama `main` directamente está OK (es proyecto personal del usuario).

### 8. Comunicación
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

# Leer logs de la app (sin pasar por MCP)
python -c "import sqlite3, os; c = sqlite3.connect(os.path.expandvars(r'$APPDATA\MyVoices\myvoices.db')); c.row_factory = sqlite3.Row; [print(f\"[{r['level']}] {r['ts']}  {r['message'][:300]}\") for r in c.execute('SELECT * FROM logs ORDER BY id DESC LIMIT 50')]"
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
- `mcp_server.py` — Entry point para modo stdio (legacy).
- `main.py` — Lanzador desktop (splash + uvicorn + pywebview).
- `static/index.html` — UI (1 archivo, vanilla JS, no build step).
- `MyVoices.spec` — PyInstaller config.
- `build.bat` — Build script Windows interactivo.
