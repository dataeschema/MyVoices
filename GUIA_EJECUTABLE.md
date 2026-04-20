# ChatVoice — Guía para generar el ejecutable de escritorio

Cómo convertir ChatVoice en un `.exe` para Windows usando **PyInstaller** y **pywebview**.

---

## Índice

1. [Arquitectura](#1-arquitectura)
2. [Prerequisitos](#2-prerequisitos)
3. [Generar el ejecutable](#3-generar-el-ejecutable)
4. [Estructura del bundle](#4-estructura-del-bundle)
5. [Distribución](#5-distribucion)
6. [Primera ejecución](#6-primera-ejecucion)
7. [Solución de problemas](#7-solucion-de-problemas)

---

## 1. Arquitectura

```
main.py
  │  Arranca uvicorn en un hilo daemon
  │  Espera a que el servidor responda (hasta 3 min)
  └─► pywebview (Edge WebView2) ──► http://127.0.0.1:8000
                                           │
                                     server.py (FastAPI)
                                           │
                                     database.py (SQLite)
                                     %APPDATA%\ChatVoice\
                                       ├── chatvoice.db
                                       ├── voices\
                                       └── piper_voices\
```

**Flujo de datos de usuario** (sobreviven a actualizaciones):
- `%APPDATA%\ChatVoice\chatvoice.db` — config, presets, frases guardadas, logs de actividad
- `%APPDATA%\ChatVoice\voices\` — archivos WAV de voces clonadas
- `%APPDATA%\ChatVoice\piper_voices\` — modelos Piper TTS

---

## 2. Prerequisitos

### Python 3.10 o superior
```bash
python --version  # debe mostrar 3.10.x o superior
```

### Microsoft C++ Build Tools
Necesario para dependencias nativas. Descarga: [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/).  
Selecciona **"Desarrollo de escritorio con C++"**.

### PyTorch con CUDA (recomendado para GPU)
```bash
# RTX 5090 / 5080 / 5070 / 5060 — arquitectura Blackwell (SM_120/SM_121) — CUDA 12.8
pip install --upgrade --force-reinstall torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cu128

# RTX 4090 y anteriores — CUDA 12.4
pip install torch==2.6.0+cu124 torchaudio==2.6.0+cu124 torchvision==0.21.0+cu124 --index-url https://download.pytorch.org/whl/cu124
```

> **¿Cómo sé qué versión necesito?** Si tu GPU es RTX 5xxx (Blackwell), usa cu128. Para RTX 40xx, 30xx o anteriores, usa cu124.

### Dependencias del proyecto
```bash
pip install -r requirements.txt
```

### Edge WebView2 Runtime (equipo destino)
Incluido en Windows 10 (v1803+) y Windows 11 por defecto.  
Si falta: [Microsoft Edge WebView2](https://developer.microsoft.com/en-us/microsoft-edge/webview2/)

---

## 3. Generar el ejecutable

### Opción A — Script automático (recomendado)

Haz doble clic en `build.bat` desde la carpeta del proyecto.

El script:
1. Activa el entorno virtual `venv` si existe
2. Instala `pywebview` y `pyinstaller` si no están
3. Limpia builds anteriores
4. Ejecuta `pyinstaller ChatVoice.spec --noconfirm`
5. Muestra la ruta del exe al terminar

### Opción B — Manual

```bash
# 1. Activa el entorno virtual
venv\Scripts\activate

# 2. Instala dependencias de build
pip install "pywebview>=5.0" "pyinstaller>=6.0"

# 3. Limpia (opcional)
rmdir /s /q dist\ChatVoice build

# 4. Compila
pyinstaller ChatVoice.spec --noconfirm
```

---

## 4. Estructura del bundle

```
dist\ChatVoice\
├── ChatVoice.exe          ← doble clic para abrir
└── _internal\
    ├── static\
    │   └── index.html     ← interfaz web empaquetada
    ├── torch\             ← PyTorch (~3-5 GB con CUDA)
    ├── TTS\               ← Coqui TTS + XTTSv2
    ├── piper\             ← Piper TTS (ONNX)
    ├── pygame\            ← reproducción de audio
    └── ...
```

> **Importante:** Para mover o distribuir la app, copia **toda la carpeta `dist\ChatVoice\`**, nunca solo el `.exe`.

---

## 5. Distribución

1. Copia la carpeta completa `dist\ChatVoice\` al equipo destino
2. En la primera ejecución el equipo necesita Internet para descargar el modelo XTTSv2 (~2 GB)
3. Las voces Piper y las voces WAV clonadas se guardan en `%APPDATA%\ChatVoice\` y persisten entre versiones

### Instalador con Inno Setup (opcional)

```iss
[Setup]
AppName=ChatVoice
AppVersion=2.0
DefaultDirName={autopf}\ChatVoice

[Files]
Source: "dist\ChatVoice\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{autodesktop}\ChatVoice"; Filename: "{app}\ChatVoice.exe"
```

---

## 6. Primera ejecución

1. **Windows Defender SmartScreen** puede pedir confirmación. Haz clic en **"Más información" → "Ejecutar de todas formas"**.

2. La app **no muestra consola** (los logs se consultan desde el visor en la UI → sección "Registro de actividad").

3. Si es la primera vez, se descarga el modelo XTTSv2 (~2 GB) antes de que se abra la ventana. Tarda varios minutos según la conexión.

4. Los datos de usuario se guardan en:
   ```
   %APPDATA%\ChatVoice\
   ├── chatvoice.db       ← toda la configuración (incluye presets y frases)
   ├── voices\            ← archivos WAV subidos
   └── piper_voices\      ← modelos Piper descargados
   ```

---

## 7. Solución de problemas

### El exe cierra inmediatamente / pantalla en blanco

Ejecuta desde terminal para ver el error:
```bash
dist\ChatVoice\ChatVoice.exe
```
Los errores de inicio también aparecen en el **visor de logs** si el servidor arrancó parcialmente.

### "No module named 'xxx'"

Añade el módulo a `hiddenimports` en `ChatVoice.spec`:
```python
hiddenimports=[
    ...
    "nombre_del_modulo",
],
```
Luego vuelve a compilar con `build.bat`.

### GPU no detectada / XTTS carga en CPU en vez de GPU

Abre el **visor de logs** en la UI (sección "Registro de actividad") y busca un mensaje `CUDA no disponible`. Las causas más comunes:

**RTX 5xxx (Blackwell) con PyTorch cu124 o anterior**  
PyTorch cu124 no incluye kernels para la arquitectura Blackwell (SM_120/SM_121). Instala la versión cu128 y luego re-fija las dependencias de gruut:
```bash
pip install --upgrade --force-reinstall torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cu128
pip install "numpy<2.0.0" "networkx<3.0.0"
```
Luego vuelve a compilar con `build.bat`.

> **¿Por qué el segundo comando?** `--force-reinstall` puede arrastrar numpy 2.x y networkx 3.x, que rompen gruut (dependencia de TTS). El segundo comando los vuelve a fijar a las versiones compatibles.

**Cualquier GPU — driver o CUDA desactualizado**  
Actualiza los drivers NVIDIA desde [nvidia.com/drivers](https://www.nvidia.com/drivers) y asegúrate de tener CUDA 12.x instalado.

**Fallback garantizado:** el modelo siempre carga en CPU si la GPU no es compatible (más lento pero funcional).

### La ventana no se abre (timeout del servidor)

El servidor tardó más de 3 minutos (puede ocurrir en equipos lentos o la primera vez).
Edita `main.py` y aumenta el timeout:
```python
if not _wait_for_server(status_url, timeout=300.0):  # 5 minutos
```
Luego recompila con `build.bat`.

### Edge WebView2 no encontrado

Instala el runtime desde:  
https://developer.microsoft.com/en-us/microsoft-edge/webview2/

### PyTorch falla en el build

PyTorch debe estar instalado **en el mismo entorno** que PyInstaller.  
Si usas `venv`, actívalo antes de compilar.

### El modelo XTTSv2 no se descarga

Verifica conexión a Internet. El modelo se descarga en:
```
%USERPROFILE%\AppData\Local\tts\tts_models--multilingual--multi-dataset--xtts_v2\
```

---

## Notas

- **Tamaño del bundle:** ~5-8 GB (principalmente PyTorch + TTS)
- **Sin consola visible:** `console=False` en `ChatVoice.spec`. Los logs se consultan desde la UI.
- **Actualizar sin recompilar:** Para cambios en `static/index.html`, reemplaza el archivo en `dist\ChatVoice\_internal\static\`. Para cambios en Python, hay que recompilar.
- **Versión de Python:** El build debe usar la misma versión de Python que el entorno virtual.
