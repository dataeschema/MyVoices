# MyVoices

**Español** · [English](README.md)

Aplicación de escritorio TTS para streaming. Lee texto con voces clonadas usando **XTTSv2** (GPU/CPU) y **Piper TTS** (ligero, sin GPU). Se integra con SAMMI y otros sistemas vía API REST.

## Características

- **Dos motores TTS**: XTTSv2 (clonación de voz, alta calidad) y Piper TTS (rápido, sin GPU)
- **Presets de voz**: combina una voz con velocidad, tono, idioma y efecto de radio; guárdala con un nombre
- **Idioma por preset**: el idioma XTTS se configura por preset, no globalmente
- **API REST simple**: solo `voice` + `text` — sin parámetros técnicos
- **Frases guardadas**: biblioteca de textos asociados a un preset; reproducibles por nombre vía API; guardar con un nombre ya existente actualiza la frase (upsert)
- **Descarga de audio**: el botón *Descargar audio* guarda **exactamente el último WAV reproducido** desde una caché en el servidor — sin re-sintetizar
- **Pestaña de Ayuda**: diagrama del flujo de trabajo integrado en la app (clonar voz → preset → probar/guardar/API)
- **Efecto de radio**: bandpass 400–3400 Hz + soft clipping + ruido
- **Panel de prueba**: selecciona un preset, escucha y descarga el resultado
- **Splash screen**: barra de progreso animada durante el arranque mientras carga el modelo
- **Visor de logs**: registro de actividad con auto-refresco, filtros por nivel y origen, y columnas nuevas — caller (MCP/API/UI), preset, vista previa del texto y duración de síntesis
- **Cola de prioridad**: las peticiones TTS pasan por un `asyncio.PriorityQueue`; las llamadas de MCP/API tienen prioridad sobre las de UI y frases, eliminando deadlocks en el event loop
- **Notificaciones por webhook**: registra endpoints HTTP para recibir eventos `speak_end` con voz, texto, caller y duración; gestionables desde la UI
- **Tests**: 168 tests unitarios e integración (DB, utils, API CRUD, marcado UI, MCP) ejecutables sin GPU
- **CI**: GitHub Actions ejecuta ruff + pytest en cada push y PR
- **Servidor MCP integrado**: endpoint [Model Context Protocol](https://modelcontextprotocol.io) montado en `/mcp/`, **activable desde la propia UI** y protegido por Bearer token. Permite que un LLM (Claude Desktop, Claude Code, Cursor, Gemini CLI, ChatGPT…) liste voces, hable texto y dispare frases guardadas. Se mantiene también `mcp_server.py` (stdio) para clientes que lo necesiten

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

# 4. Instala el resto de dependencias
pip install -r requirements.txt

# 5. Re-fija numpy y networkx (requirements puede subirlas, gruut las necesita antiguas)
pip install "numpy<2.0.0" "networkx<3.0.0"
```

> **Sin GPU**: Piper TTS funciona sin GPU. XTTSv2 es muy lento en CPU.

---

## Ejecución en modo desarrollo

```bash
venv\Scripts\activate
python main.py
```

Al arrancar aparece una **splash screen** con barra de progreso animada mientras se carga el modelo XTTSv2. Una vez listo, se abre la ventana principal.

La primera vez descarga el modelo XTTSv2 (~2 GB) — tarda varios minutos.

Panel web disponible también en: `http://localhost:8000`

---

## Tests

```bash
venv\Scripts\activate
pip install -r requirements-dev.txt   # solo la primera vez
pytest --cov
```

168 tests en cinco suites (DB, utils, API CRUD, marcado UI, MCP). No requieren GPU ni modelos descargados (el servidor arranca en modo test sin cargar TTS).

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
5. Re-fija `numpy<2.0` y `networkx<3.0` tras las dependencias
6. Compila con PyInstaller

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

### Descargar audio sintetizado como WAV (re-síntesis)

```
POST http://localhost:8000/api/speak/download
Content-Type: application/json

{
  "voice": "nombre_del_preset",
  "text": "Texto a sintetizar"
}
```

Devuelve el fichero WAV directamente (Content-Disposition: attachment).

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
| `list_voices` | Voces registradas (clonadas XTTS + Piper) |
| `list_presets` | Presets de voz (voz + velocidad/tono/idioma/radio) |
| `list_phrases` | Frases guardadas con su preset asociado |
| `speak(voice, text)` | Sintetiza y reproduce `text` con el preset indicado |
| `play_phrase(name)` | Reproduce una frase guardada por nombre |
| `download_last_audio` | Metadatos del último WAV cacheado |

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

1. **Tab XTTS2** → sube un WAV de referencia → la voz queda registrada con un ID
2. **Tab Piper** → descarga una voz del catálogo → se registra automáticamente
3. **Tab Principal** → selecciona una voz, ajusta velocidad/tono/idioma/radio → guarda como preset
4. Llama a la API con `{"voice": "nombre_preset", "text": "..."}` desde SAMMI u otro sistema
5. (Opcional) Registra webhooks en el panel **Webhooks** para recibir eventos `speak_end` en sistemas externos (OBS, Home Assistant, n8n…)

La pestaña **Ayuda** dentro de la app contiene el mismo flujo en forma de diagrama visual.

---

## Datos de usuario

Todos los datos persisten entre actualizaciones en `%APPDATA%\MyVoices\`:

```
%APPDATA%\MyVoices\
├── myvoices.db        ← DB con voces, presets, frases y logs
├── voices\            ← archivos WAV de voces clonadas XTTS
└── piper_voices\      ← modelos Piper (.onnx + .onnx.json)
```

El modelo XTTSv2 se guarda en:
```
%USERPROFILE%\AppData\Local\tts\tts_models--multilingual--multi-dataset--xtts_v2\
```
