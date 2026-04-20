# ChatVoice

Aplicación de escritorio TTS para streaming. Lee el chat de Twitch con voz clonada usando **XTTSv2** (GPU/CPU) y **Piper TTS** (ligero, sin GPU). Se integra con SAMMI vía POST.

## Características

- **Dos motores TTS**: XTTSv2 (alta calidad, clonación de voz) y Piper TTS (rápido, sin GPU)
- **Presets**: guarda configuraciones completas (motor, voz, velocidad, tono) y aplícalas con un clic
- **Frases guardadas**: biblioteca de textos con preset vinculado; se reproducen sin cambiar la config global
- **Efecto de radio**: bandpass 400-3400 Hz + soft clipping + ruido
- **Selector de dispositivo de audio**: elige por qué salida de Windows suena el TTS
- **Visor de logs**: registro de actividad con auto-refresco, filtro por nivel y rotación automática
- **Integración SAMMI**: endpoint POST `/speak` compatible con versiones anteriores

---

## Requisitos previos

### Microsoft C++ Build Tools
Necesario para compilar dependencias nativas de TTS.

1. Descarga [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
2. Selecciona **"Desarrollo de escritorio con C++"**
3. Instala y reinicia si es necesario

---

## Instalación

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

#    RTX 4090 y anteriores — CUDA 12.4:
pip install torch==2.6.0+cu124 torchaudio==2.6.0+cu124 torchvision==0.21.0+cu124 --index-url https://download.pytorch.org/whl/cu124

# 4. Instala el resto de dependencias
pip install -r requirements.txt
```

> **Sin GPU**: Piper TTS funciona sin GPU. XTTSv2 es muy lento en CPU.

---

## Ejecución

### Como aplicación de escritorio (recomendado)
```bash
venv\Scripts\activate
python main.py
```
Arranca el servidor en background y abre una ventana nativa (Edge WebView2).  
La primera vez descarga el modelo XTTSv2 (~2 GB) — tarda varios minutos.

### Solo el servidor (para uso headless / SAMMI sin UI)
```bash
venv\Scripts\activate
python server.py
```
Panel de control disponible en: `http://localhost:8000`

---

## Configuración de voz (XTTSv2)

1. Graba **6-10 segundos** de voz clara, sin ruido de fondo
2. Guarda como `.wav` y súbelo desde la pestaña **"Subir voz"** en el panel
3. Selecciona la voz como activa

### Piper TTS (alternativa sin GPU)
1. Ve a la pestaña **Piper TTS** → **Descargar voces desde HuggingFace**
2. Filtra por idioma, descarga e instala con un clic
3. Selecciona como voz activa

---

## Integración SAMMI

POST a `http://localhost:8000/speak`:

```json
{
  "text": "Hola chat!",
  "engine": "xtts",
  "language": "es",
  "radio_effect": false,
  "speed": 1.0,
  "pitch": 0,
  "voice_index": 0,
  "speaker_id": 0
}
```

Todos los campos son opcionales excepto `text`. Los omitidos usan la Configuración Global activa.

| Campo | Tipo | Descripción |
|---|---|---|
| `text` | string | **Obligatorio** |
| `engine` | `"xtts"` \| `"piper"` | Motor TTS |
| `language` | string | Código de idioma (solo XTTS) |
| `radio_effect` | bool | Efecto bandpass + distorsión |
| `speed` | float 0.5–2.0 | Velocidad de habla |
| `pitch` | int -12 a +12 | Semítonos de tono |
| `voice_index` | int | Índice de voz dentro del motor activo |
| `speaker_id` | int | ID de hablante en modelos Piper multi-speaker |

---

## Datos de usuario

Todos los datos persisten entre actualizaciones en `%APPDATA%\ChatVoice\`:

```
%APPDATA%\ChatVoice\
├── chatvoice.db       ← configuración, presets, frases, logs
├── voices\            ← archivos WAV de voces clonadas
└── piper_voices\      ← modelos Piper (.onnx + .onnx.json)
```

El modelo XTTSv2 se guarda en:
```
%USERPROFILE%\AppData\Local\tts\tts_models--multilingual--multi-dataset--xtts_v2\
```

---

## Generar ejecutable (.exe)

Ver [GUIA_EJECUTABLE.md](GUIA_EJECUTABLE.md) para instrucciones completas.

```bash
build.bat
# o manualmente:
pyinstaller ChatVoice.spec --noconfirm
```

El ejecutable final queda en `dist\ChatVoice\ChatVoice.exe`.
