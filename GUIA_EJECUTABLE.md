# MyVoices — Guía para generar el ejecutable de escritorio

Cómo convertir MyVoices en un `.exe` para Windows usando **PyInstaller** y **pywebview**.

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
                                     %APPDATA%\MyVoices\
                                       ├── myvoices.db
                                       ├── voices\
                                       └── piper_voices\
```

**Flujo de datos de usuario** (sobreviven a actualizaciones):
- `%APPDATA%\MyVoices\myvoices.db` — voces, presets, frases guardadas, logs de actividad
- `%APPDATA%\MyVoices\voices\` — archivos WAV de voces clonadas (XTTS2)
- `%APPDATA%\MyVoices\piper_voices\` — modelos Piper TTS (.onnx + .onnx.json)

---

## 2. Prerequisitos

### Python 3.10 o superior
```bash
python --version  # debe mostrar 3.10.x o superior
```

### Microsoft C++ Build Tools
Necesario para dependencias nativas. Descarga: [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/).  
Selecciona **"Desarrollo de escritorio con C++"**.

### Edge WebView2 Runtime (equipo destino)
Incluido en Windows 10 (v1803+) y Windows 11 por defecto.  
Si falta: [Microsoft Edge WebView2](https://developer.microsoft.com/en-us/microsoft-edge/webview2/)

> **PyTorch, CUDA y las demás dependencias las instala automáticamente `build.bat`** — no necesitas instalarlas a mano.

---

## 3. Generar el ejecutable

### Opción A — Script automático (recomendado)

Haz doble clic en `build.bat` desde la carpeta del proyecto (o ejecútalo desde terminal).

El script hace todo de forma autónoma:

1. Verifica que Python 3.10+ está en el PATH
2. Crea el entorno virtual `venv` si no existe
3. Detecta la GPU NVIDIA via `nvidia-smi`:
   - **RTX 50xx (Blackwell)** → instala PyTorch cu128
   - **RTX 40xx / 30xx / anteriores** → instala PyTorch cu124
   - **Sin GPU** → muestra error (XTTSv2 requiere GPU; Piper TTS funcionará igualmente)
4. Re-fija `numpy<2.0` y `networkx<3.0` (incompatibles con gruut si se actualizan)
5. Instala `requirements.txt`
6. Instala PyInstaller ≥ 6.0
7. Mata `MyVoices.exe` si está en ejecución
8. Limpia builds anteriores (`dist\MyVoices\`, `build\`)
9. Compila con `MyVoices.spec`
10. Muestra la ruta del exe al terminar

```bat
build.bat
```

El ejecutable final queda en: `dist\MyVoices\MyVoices.exe`

### Opción B — Manual

```bash
# 1. Crea y activa el entorno virtual
python -m venv venv
venv\Scripts\activate

# 2. Instala PyTorch (elige según tu GPU)
#    RTX 50xx (Blackwell):
pip install --upgrade --force-reinstall torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cu128
pip install "numpy<2.0.0" "networkx<3.0.0"

#    RTX 40xx y anteriores:
pip install torch==2.6.0+cu124 torchaudio==2.6.0+cu124 torchvision==0.21.0+cu124 --index-url https://download.pytorch.org/whl/cu124

# 3. Instala dependencias y PyInstaller
pip install -r requirements.txt
pip install "pyinstaller>=6.0"

# 4. Limpia builds anteriores (opcional)
rmdir /s /q dist\MyVoices build

# 5. Compila
pyinstaller MyVoices.spec --noconfirm
```

---

## 4. Estructura del bundle

```
dist\MyVoices\
├── MyVoices.exe          ← doble clic para abrir
└── _internal\
    ├── static\
    │   └── index.html     ← interfaz web empaquetada
    ├── torch\             ← PyTorch (~3-5 GB con CUDA)
    ├── TTS\               ← Coqui TTS + XTTSv2
    ├── piper\             ← Piper TTS (ONNX)
    ├── pygame\            ← reproducción de audio
    └── ...
```

> **Importante:** Para mover o distribuir la app, copia **toda la carpeta `dist\MyVoices\`**, nunca solo el `.exe`.

---

## 5. Distribución

1. Copia la carpeta completa `dist\MyVoices\` al equipo destino
2. En la primera ejecución el equipo necesita Internet para descargar el modelo XTTSv2 (~2 GB)
3. Las voces Piper y las voces WAV clonadas se guardan en `%APPDATA%\MyVoices\` y persisten entre versiones

### Instalador con Inno Setup (opcional)

```iss
[Setup]
AppName=MyVoices
AppVersion=2.0
DefaultDirName={autopf}\MyVoices

[Files]
Source: "dist\MyVoices\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{autodesktop}\MyVoices"; Filename: "{app}\MyVoices.exe"
```

---

## 6. Primera ejecución

1. **Windows Defender SmartScreen** puede pedir confirmación. Haz clic en **"Más información" → "Ejecutar de todas formas"**.

2. La app **no muestra consola** (los logs se consultan desde el visor en la UI → sección "Registro de actividad").

3. Si es la primera vez, se descarga el modelo XTTSv2 (~2 GB) antes de que se abra la ventana. Tarda varios minutos según la conexión.

4. Los datos de usuario se guardan en:
   ```
   %APPDATA%\MyVoices\
   ├── myvoices.db        ← toda la configuración (voces, presets, frases)
   ├── voices\            ← archivos WAV subidos (XTTS2)
   └── piper_voices\      ← modelos Piper descargados
   ```

5. El modelo XTTSv2 se guarda en:
   ```
   %USERPROFILE%\AppData\Local\tts\tts_models--multilingual--multi-dataset--xtts_v2\
   ```

---

## 7. Solución de problemas

### El exe cierra inmediatamente / pantalla en blanco

El log de inicio se guarda automáticamente en:
```
%APPDATA%\MyVoices\startup.log
```
Ábrelo con cualquier editor de texto para ver el error exacto. También puedes ejecutar desde terminal para ver mensajes:
```bash
dist\MyVoices\MyVoices.exe
```

### "No module named 'xxx'"

Añade el módulo a `hiddenimports` en `MyVoices.spec`:
```python
hiddenimports=[
    ...
    "nombre_del_modulo",
],
```
Luego vuelve a compilar con `build.bat`.

### GPU no detectada / XTTS carga en CPU en vez de GPU

Abre el **visor de logs** en la UI (sección "Registro de actividad") y busca mensajes de CUDA. Las causas más comunes:

**RTX 5xxx (Blackwell) con PyTorch cu124 o anterior**  
PyTorch cu124 no incluye kernels para la arquitectura Blackwell (SM_120/SM_121). `build.bat` lo detecta automáticamente y usa cu128. Si compilaste de forma manual, instala la versión correcta:
```bash
pip install --upgrade --force-reinstall torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cu128
pip install "numpy<2.0.0" "networkx<3.0.0"
```
Luego vuelve a compilar con `build.bat`.

> **¿Por qué el segundo comando?** `--force-reinstall` puede arrastrar numpy 2.x y networkx 3.x, que rompen gruut (dependencia de TTS). El segundo comando los vuelve a fijar a las versiones compatibles.

**Cualquier GPU — driver o CUDA desactualizado**  
Actualiza los drivers NVIDIA desde [nvidia.com/drivers](https://www.nvidia.com/drivers) y asegúrate de tener CUDA 12.x instalado.

**Fallback garantizado:** el modelo siempre carga en CPU si la GPU no es compatible (más lento pero funcional). Piper TTS no requiere GPU y funciona correctamente en cualquier caso.

### La ventana no se abre (timeout del servidor)

El servidor tardó más de 3 minutos. Puede ocurrir en la primera ejecución (descarga del modelo) o en equipos lentos.  
Edita `main.py` y aumenta el timeout:
```python
if not _wait_for_server(status_url, timeout=300.0):  # 5 minutos
```
Luego recompila con `build.bat`.

### Edge WebView2 no encontrado

Instala el runtime desde:  
https://developer.microsoft.com/en-us/microsoft-edge/webview2/

### PyTorch falla en el build manual

PyTorch debe estar instalado **en el mismo entorno** que PyInstaller.  
Usa `build.bat` para que todo se haga en el mismo venv automáticamente.

### El modelo XTTSv2 no se descarga

Verifica conexión a Internet. El modelo se descarga en:
```
%USERPROFILE%\AppData\Local\tts\tts_models--multilingual--multi-dataset--xtts_v2\
```

### Migración desde una versión anterior (ChatVoice)

Si tenías instalada la versión anterior, MyVoices detecta automáticamente la base de datos antigua (`chatvoice.db`) y la renombra a `myvoices_backup.db`. La nueva instalación arranca con una base de datos limpia.  
Las voces WAV y los modelos Piper **no se migran automáticamente** — cópialos manualmente desde `%APPDATA%\ChatVoice\` si los necesitas.

---

## Notas

- **Tamaño del bundle:** ~5-8 GB (principalmente PyTorch + TTS)
- **Sin consola visible:** `console=False` en `MyVoices.spec`. Los logs se consultan desde la UI o en `%APPDATA%\MyVoices\startup.log`.
- **Actualizar sin recompilar:** Para cambios en `static/index.html`, reemplaza el archivo en `dist\MyVoices\_internal\static\`. Para cambios en Python, hay que recompilar con `build.bat`.
- **Versión de Python:** El build debe usar la misma versión de Python que el entorno virtual.
- **build.bat es idempotente:** puedes ejecutarlo varias veces sin problema; reutiliza el venv existente y solo reinstala lo necesario.
