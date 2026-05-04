# MyVoices

**Español** · [English](README.md)

Aplicación de escritorio TTS para streaming. Lee texto con voces clonadas usando cuatro motores: **XTTSv2**, **Piper TTS**, **F5-TTS** y **Chatterbox TTS**. Se integra con SAMMI y otros sistemas vía API REST y MCP.

## Características

- **Cuatro motores TTS** — elige el equilibrio adecuado para cada voz:
  - **XTTSv2** — clonación de voz multilingüe (17 idiomas), alta calidad, requiere GPU
  - **Piper TTS** — voces neuronales de catálogo, sin GPU
  - **F5-TTS** — clonación desde un WAV de 3-12 s, optimizado para inglés y chino (~3 GB de descarga)
  - **Chatterbox** — clonación multilingüe (23 idiomas), muy rápido, incluye marca de agua imperceptible
- **Presets de voz**: combina una voz con velocidad, tono, idioma y efecto de radio; guárdala con un nombre
- **Idioma por preset**: XTTS y Chatterbox respetan el idioma del preset; F5-TTS funciona mejor en inglés/chino independientemente del preset
- **API REST simple**: solo `voice` + `text` — sin parámetros técnicos
- **Frases guardadas**: biblioteca de textos asociados a un preset; reproducibles por nombre vía API; guardar con un nombre ya existente actualiza la frase (upsert)
- **Exportar audio**: sintetiza y descarga en **WAV, MP3 u OGG**; o descarga el último audio reproducido sin re-sintetizar
- **Pestaña de Ayuda**: diagrama del flujo de trabajo integrado en la app (clonar voz → preset → probar/guardar/API)
- **Efecto de radio**: bandpass 400–3400 Hz + soft clipping + ruido
- **Panel de prueba**: selecciona un preset, escucha y descarga el resultado
- **Splash screen**: barra de progreso animada durante el arranque mientras carga el modelo
- **Visor de logs**: registro de actividad con auto-refresco, filtros por nivel y origen, y columnas — caller (MCP/API/UI), preset, vista previa del texto y duración de síntesis
- **Cola de prioridad**: las peticiones TTS pasan por un `asyncio.PriorityQueue`; las llamadas de MCP/API tienen prioridad sobre las de UI y frases
- **Notificaciones por webhook**: registra endpoints HTTP para recibir eventos `speak_end` con voz, texto, caller y duración; gestionables desde la UI
- **Modo verbose**: activa logging DEBUG + tracebacks completos desde la UI, API o tool MCP; también disponible al arrancar con `MYVOICES_VERBOSE=1`
- **Endpoint de diagnóstico**: `/api/diagnostics` (y la tool MCP `get_diagnostics`) devuelve disponibilidad por motor, errores de import y versiones de paquetes instalados
- **Tests**: 206 tests unitarios e integración (DB, utils, API CRUD, marcado UI, MCP) ejecutables sin GPU
- **CI**: GitHub Actions ejecuta ruff + pytest en cada push y PR
- **Servidor MCP integrado**: endpoint [Model Context Protocol](https://modelcontextprotocol.io) montado en `/mcp/`, **activable desde la propia UI** y protegido por Bearer token. Permite que un LLM (Claude Desktop, Claude Code, Cursor, Gemini CLI, ChatGPT…) liste voces, hable texto y dispare frases guardadas. Se mantiene también `mcp_server.py` (stdio) para clientes que lo necesiten

---

## Motores TTS de un vistazo

| Motor | Clonación de voz | Idiomas | GPU | Notas |
|---|---|---|---|---|
| **XTTSv2** | WAV 10–30 s | 17 | Necesaria para velocidad | Mejor calidad multilingüe |
| **Piper** | No (voces de catálogo) | Por modelo | No necesaria | El más rápido, menos VRAM |
| **F5-TTS** | WAV 3–12 s | EN/ZH mejor | ≥12 GB VRAM | Inglés/chino; otros idiomas pueden sonar con acento inglés |
| **Chatterbox** | WAV 5+ s | 23 | 4–6 GB VRAM | Añade marca de agua imperceptible (Perth/Resemble AI) |

---

## Requisitos previos

### Microsoft C++ Build Tools
Necesario para compilar dependencias nativas de TTS.

1. Descarga [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
2. Selecciona **"Desarrollo de escritorio con C++"**
3. Instala y reinicia si es necesario

---

## Instalación (modo desarrollo)

```bash
# 1. Clona el repositorio
git clone https://github.com/dataeschema/MyVoices.git
cd MyVoices

# 2. Crea un entorno virtual
python -m venv venv
venv\Scripts\activate

# 3. Instala PyTorch con soporte CUDA (elige según tu GPU)
#    RTX 50xx (Blackwell) — CUDA 12.8:
pip install --upgrade --force-reinstall torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cu128

#    RTX 40xx / 30xx / 20xx — CUDA 12.4:
pip install --upgrade --force-reinstall torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cu124

# 4. Instala el resto de dependencias (XTTSv2 + Piper incluidos)
pip install -r requirements.txt
```

### Opcional: F5-TTS y Chatterbox

F5-TTS y Chatterbox no están en `requirements.txt` porque tienen dependencias
opcionales pesadas. Instálalos solo si los vas a usar:

```bash
# F5-TTS — requiere >=1.1.20 para evitar conflicto con pydantic
pip install "f5-tts>=1.1.20"

# Chatterbox — instalar sin deps para evitar conflicto de versión de torch
pip install chatterbox-tts --no-deps
pip install resemble-enhance  # mejora de audio usada por Chatterbox
```

> **Sin GPU**: Piper TTS funciona sin GPU. XTTSv2 es muy lento en CPU. F5-TTS y Chatterbox requieren GPU CUDA.

---

## Ejecución en modo desarrollo

```bash
venv\Scripts\activate
python main.py
```

Al arrancar aparece una **splash screen** con barra de progreso animada mientras se carga el modelo XTTSv2. Una vez listo, se abre la ventana principal.

La primera vez descarga el modelo XTTSv2 (~2 GB) — tarda varios minutos.
F5-TTS (~3 GB) y Chatterbox (~1-2 GB) se descargan en el primer uso.

Panel web disponible también en: `http://localhost:8000`

---

## Tests

```bash
venv\Scripts\activate
pip install -r requirements-dev.txt   # solo la primera vez
pytest --cov
```

206 tests en cinco suites (DB, utils, API CRUD, marcado UI, MCP). No requieren GPU ni modelos descargados (el servidor arranca en modo test sin cargar TTS).

---

## Generar ejecutable (.exe)

`build.bat` es completamente autónomo:

```bat
build.bat
```

El script:
1. Verifica Python 3.10+
2. Crea el venv si no existe
3. **Pregunta qué GPU tienes** (menú 1/2/3) y selecciona la versión CUDA adecuada
4. Instala PyTorch, `requirements.txt` y PyInstaller automáticamente
5. Compila con PyInstaller

El ejecutable final queda en `dist\MyVoices\MyVoices.exe`.

> Ver [GUIA_EJECUTABLE.md](GUIA_EJECUTABLE.md) para detalles y solución de problemas.

---

## API REST

### Reproducir texto con un preset de voz

```
POST http://localhost:8000/api/speak
Content-Type: application/json

{
  "voice": "nombre_del_preset",
  "text": "Hola chat, bienvenidos al stream!"
}
```

El WAV sintetizado se cachea en el servidor para que puedas obtener el audio exacto que sonó:

```
GET http://localhost:8000/api/speak/last     → devuelve el último WAV
```

### Descargar audio sintetizado (WAV / MP3 / OGG)

```
POST http://localhost:8000/api/speak/download?format=mp3
Content-Type: application/json

{
  "voice": "nombre_del_preset",
  "text": "Texto a sintetizar"
}
```

`format` admite `wav` (default), `mp3` o `ogg`. WAV es passthrough; MP3/OGG
requieren `ffmpeg` en el PATH (mp3 a 192 kbps, ogg vía libvorbis).

Para descargar el último audio reproducido sin re-sintetizar:

```
GET http://localhost:8000/api/speak/last?format=mp3
```

### Reproducir una frase guardada

```
POST http://localhost:8000/api/phrases/{nombre}/play
```

### Webhooks

Registra un endpoint HTTP para recibir eventos cuando termina una síntesis:

```
GET    http://localhost:8000/api/webhooks           → listar webhooks
POST   http://localhost:8000/api/webhooks           → añadir webhook
DELETE http://localhost:8000/api/webhooks/{id}      → eliminar webhook
POST   http://localhost:8000/api/webhooks/test/{id}  → disparar evento de prueba
```

**Añadir un webhook:**
```json
POST /api/webhooks
{ "url": "https://tu-servidor/hook", "events": "speak_end" }
```

**Payload enviado en `speak_end`:**
```json
{
  "event": "speak_end",
  "job_id": "a1b2c3d4",
  "voice": "nombre_preset",
  "text": "primeros 120 caracteres del texto",
  "caller": "MCP",
  "duration_ms": 1240
}
```

`caller` es `MCP`, `API` o `UI`.  
`events` puede ser `speak_end` o `*` (todos los eventos).

---

## Servidor MCP (integración con LLMs)

MyVoices expone un endpoint [Model Context Protocol](https://modelcontextprotocol.io) para que un LLM (Claude, Cursor, Gemini, ChatGPT…) pueda listar voces, leer texto y disparar frases guardadas vía tool calls.

Hay dos transportes — usa el que mejor le venga a tu cliente:

### HTTP — integrado en la app (recomendado)

1. Abre MyVoices, ve a la pestaña **Principal → tarjeta 🤖 Servidor MCP** y activa el toggle.
2. La tarjeta muestra la URL (`http://localhost:8000/mcp/`) y un Bearer token (autogenerado en la primera activación).
3. Abre la pestaña **Ayuda**, elige tu cliente en el selector y copia el snippet de configuración auto-rellenado — URL, token y rutas absolutas vienen ya sustituidos.

El endpoint queda gateado por el toggle (devuelve `503` si está OFF) y por `Authorization: Bearer <token>` (devuelve `401` si no coincide).

### stdio — legacy, para clientes sin soporte HTTP

Lanza `python mcp_server.py` como subprocess desde la config de tu cliente. El script solo redirige llamadas a la API REST local, así que la app de MyVoices debe estar abierta.

### Tools expuestas

| Tool | Qué hace |
|---|---|
| `get_status` | Estado del servidor: motor TTS, dispositivo, conteos de voces/presets |
| `list_voices` | Voces registradas (todos los motores) |
| `list_presets` | Presets de voz (voz + velocidad/tono/idioma/radio) |
| `list_phrases` | Frases guardadas con su preset asociado |
| `speak(voice, text)` | Sintetiza y reproduce `text` con el preset indicado |
| `play_phrase(name)` | Reproduce una frase guardada por nombre |
| `download_last_audio` | Metadatos del último WAV cacheado |
| `get_logs` | Últimos N logs filtrables por nivel, origen y subcadena |
| `get_diagnostics` | Estado completo: motores, errores de import, versiones de paquetes |
| `load_model` | Carga bajo demanda un motor TTS (`xtts`/`f5tts`/`chatterbox`) |
| `set_verbose` | Activa/desactiva modo verbose (DEBUG + tracebacks completos) |

### Clientes soportados

| Cliente | Transport | Dónde va el snippet |
|---|---|---|
| Claude Desktop | HTTP o stdio | `%APPDATA%\Claude\claude_desktop_config.json` |
| Claude Code (CLI) | HTTP | `claude mcp add myvoices --transport http …` |
| Cursor | HTTP | `.cursor/mcp.json` (proyecto) o `~/.cursor/mcp.json` (global) |
| Gemini CLI | HTTP | `~/.gemini/mcp.json` |
| ChatGPT (Connectors) | HTTP | Settings → Connectors → Add MCP Server (depende del plan) |
| Cline | stdio | UI de settings de Cline |
| Genérico HTTP | HTTP | URL + header `Authorization: Bearer <token>` |

La pestaña Ayuda dentro de MyVoices muestra el snippet listo para copiar para cada cliente, con URL, token y rutas ya sustituidos.

### Smoke test desde terminal

```bash
# Activa MCP desde la UI primero, luego copia el token de la tarjeta.
TOKEN="<pega aquí>"
curl -X POST http://localhost:8000/mcp/ \
     -H "Accept: application/json, text/event-stream" \
     -H "Authorization: Bearer $TOKEN" \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}'
```

---

## Flujo de uso

1. **Tab XTTS2** → sube un WAV de referencia (10–30 s) → voz registrada con un ID
2. **Tab Piper** → descarga una voz del catálogo → se registra automáticamente
3. **Tab F5-TTS** → sube un WAV de referencia (3–12 s) → voz registrada (recomendado inglés/chino)
4. **Tab Chatterbox** → sube un WAV de referencia (5+ s) → voz registrada (23 idiomas)
5. **Tab Principal** → selecciona una voz, ajusta velocidad/tono/idioma/radio → guarda como preset
6. Llama a la API con `{"voice": "nombre_preset", "text": "..."}` desde SAMMI u otro sistema
7. (Opcional) Registra webhooks en el panel **Webhooks** para recibir eventos `speak_end` en sistemas externos (OBS, Home Assistant, n8n…)

La pestaña **Ayuda** dentro de la app contiene el mismo flujo en forma de diagrama visual.

---

## Modo verbose y diagnóstico

Cuando un motor TTS no carga o un fragmento falla con un error opaco:

```bash
# Activar modo verbose (DEBUG + tracebacks completos)
curl -X POST http://localhost:8000/api/verbose/true

# O desde un cliente MCP:
# tool: set_verbose(enabled=true)

# Ver el estado completo de los motores y errores de import
curl http://localhost:8000/api/diagnostics
# Equivalente MCP: tool: get_diagnostics

# Leer los últimos 50 errores
curl 'http://localhost:8000/api/logs?level=ERROR&limit=50'
```

`get_diagnostics` devuelve para cada motor: si está disponible, su status,
y el `import_error` (con traceback) si la importación falló. También las
versiones instaladas de torch, transformers, TTS, f5-tts, chatterbox.

También puedes activar verbose desde el lanzamiento con la variable de
entorno `MYVOICES_VERBOSE=1`.

---

## Datos de usuario

Todos los datos persisten entre actualizaciones en `%APPDATA%\MyVoices\`:

```
%APPDATA%\MyVoices\
├── myvoices.db        ← DB con voces, presets, frases y logs
├── voices\            ← archivos WAV de voces clonadas (XTTS, F5-TTS, Chatterbox)
└── piper_voices\      ← modelos Piper (.onnx + .onnx.json)
```

El modelo XTTSv2 se guarda en:
```
%USERPROFILE%\AppData\Local\tts\tts_models--multilingual--multi-dataset--xtts_v2\
```

Los modelos de F5-TTS y Chatterbox se cachean en el directorio por defecto de
Hugging Face (`%USERPROFILE%\.cache\huggingface\hub\`).
