# MyVoices

Aplicación de escritorio TTS para streaming. Lee texto con voces clonadas usando **XTTSv2** (GPU/CPU) y **Piper TTS** (ligero, sin GPU). Se integra con SAMMI y otros sistemas vía API REST.

## Características

- **Dos motores TTS**: XTTSv2 (clonación de voz, alta calidad) y Piper TTS (rápido, sin GPU)
- **Presets de voz**: combina una voz con velocidad, tono y efecto de radio y guárdala con un nombre
- **API REST simple**: solo `voice` + `text` — sin parámetros técnicos
- **Frases guardadas**: biblioteca de textos asociados a un preset; reproducibles por nombre vía API
- **Efecto de radio**: bandpass 400–3400 Hz + soft clipping + ruido
- **Panel de prueba**: selecciona un preset y escucha el resultado antes de usarlo en producción
- **Visor de logs**: registro de actividad con auto-refresco, filtro por nivel y rotación automática

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
#    RTX 5090 / 5080 / 5070 / 5060 — Blackwell (SM_120/SM_121) — CUDA 12.8:
pip install --upgrade --force-reinstall torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cu128
pip install "numpy<2.0.0" "networkx<3.0.0"   # re-fijar dependencias de gruut

#    RTX 4090 y anteriores — CUDA 12.4:
pip install torch==2.6.0+cu124 torchaudio==2.6.0+cu124 torchvision==0.21.0+cu124 --index-url https://download.pytorch.org/whl/cu124

# 4. Instala el resto de dependencias
pip install -r requirements.txt
```

> **Sin GPU**: Piper TTS funciona sin GPU. XTTSv2 es muy lento en CPU.

---

## Ejecución en modo desarrollo

```bash
venv\Scripts\activate
python main.py
```

Arranca el servidor en background y abre una ventana nativa (Edge WebView2).
La primera vez descarga el modelo XTTSv2 (~2 GB) — tarda varios minutos.

Panel web disponible también en: `http://localhost:8000`

---

## Generar ejecutable (.exe)

`build.bat` es completamente autónomo:

1. Crea el venv si no existe
2. Detecta la GPU NVIDIA vía `nvidia-smi` y selecciona la versión CUDA adecuada
3. Instala PyTorch, dependencias y PyInstaller automáticamente
4. Compila el ejecutable con PyInstaller

```bat
build.bat
```

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

### Reproducir una frase guardada

```
POST http://localhost:8000/api/phrases/{nombre}/play
```

---

## Flujo de uso

1. **Tab XTTS2** → sube un WAV de referencia → la voz queda registrada con un ID
2. **Tab Piper** → descarga una voz del catálogo → regístrala con un nombre
3. **Tab Principal** → selecciona una voz, ajusta velocidad/tono/radio → guarda como preset
4. Llama a la API con `{"voice": "nombre_preset", "text": "..."}` desde SAMMI u otro sistema

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
