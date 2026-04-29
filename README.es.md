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
- **Visor de logs**: registro de actividad con auto-refresco, filtro por nivel y rotación automática
- **Tests**: 121 tests unitarios e integración (DB, utils, API CRUD, marcado UI) ejecutables sin GPU
- **CI**: GitHub Actions ejecuta ruff + pytest en cada push y PR

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

121 tests en cuatro suites. No requieren GPU ni modelos descargados (el servidor arranca en modo test sin cargar TTS).

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

---

## Flujo de uso

1. **Tab XTTS2** → sube un WAV de referencia → la voz queda registrada con un ID
2. **Tab Piper** → descarga una voz del catálogo → se registra automáticamente
3. **Tab Principal** → selecciona una voz, ajusta velocidad/tono/idioma/radio → guarda como preset
4. Llama a la API con `{"voice": "nombre_preset", "text": "..."}` desde SAMMI u otro sistema

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
