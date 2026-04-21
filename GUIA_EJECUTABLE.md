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
  │  Muestra splash screen con barra de progreso
  │  Importa server.py en hilo daemon (torch + modelo TTS)
  │  Arranca uvicorn en hilo daemon
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

**Flujo de arranque:**
1. `main.py` abre una ventana frameless (splash) de inmediato
2. En background: importa `server.py` (torch + TTS model) → anima la barra de progreso
3. Arranca uvicorn → espera respuesta → crea la ventana principal → cierra la splash

**Datos de usuario** (sobreviven a actualizaciones):
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
3. **Pregunta qué GPU tienes** (menú interactivo):
   ```
   Selecciona tu GPU:
     [1] RTX 50xx (Blackwell)        - CUDA 12.8
     [2] RTX 20xx / 30xx / 40xx      - CUDA 12.4  (recomendado para la mayoria)
     [3] Sin GPU / Solo CPU
   ```
4. Instala PyTorch con la versión CUDA correcta
5. Instala `requirements.txt`
6. Re-fija `numpy<2.0` y `networkx<3.0` (incompatibles con gruut si se actualizan)
7. Instala PyInstaller ≥ 6.0
8. Mata `MyVoices.exe` si está en ejecución
9. Limpia builds anteriores (`dist\MyVoices\`, `build\`)
10. Compila con `MyVoices.spec`
11. Muestra la ruta del exe al terminar

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

#    RTX 40xx y anteriores:
pip install --upgrade --force-reinstall torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cu124

# 3. Instala dependencias y PyInstaller
pip install -r requirements.txt
pip install "numpy<2.0.0" "networkx<3.0.0"
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

2. La app muestra una **splash screen** con barra de progreso animada mientras carga. No hay pantalla en blanco.

3. Si es la primera vez, se descarga el modelo XTTSv2 (~2 GB) antes de que aparezca la ventana principal. Tarda varios minutos según la conexión.

4. La app **no muestra consola** — los logs se consultan desde el visor en la UI (sección "Registro de actividad") o en `%APPDATA%\MyVoices\startup.log`.

5. Los datos de usuario se guardan en:
   ```
   %APPDATA%\MyVoices\
   ├── myvoices.db        ← toda la configuración (voces, presets, frases)
   ├── voices\            ← archivos WAV subidos (XTTS2)
   └── piper_voices\      ← modelos Piper descargados
   ```

6. El modelo XTTSv2 se guarda en:
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

### XTTS carga en CPU en vez de GPU

Abre el **visor de logs** en la UI y busca mensajes de CUDA. Las causas más comunes:

**GPU incorrecta seleccionada en build.bat**  
Vuelve a ejecutar `build.bat` y elige la opción correcta:
- RTX 50xx → opción `1` (CUDA 12.8)
- RTX 40xx / 30xx / 20xx → opción `2` (CUDA 12.4)

**Driver o CUDA desactualizado**  
Actualiza los drivers NVIDIA desde [nvidia.com/drivers](https://www.nvidia.com/drivers).

**Fallback garantizado:** el modelo siempre carga en CPU si la GPU no es compatible (más lento pero funcional). Piper TTS no requiere GPU y funciona correctamente en cualquier caso.

### numpy / networkx incompatibles con gruut

Síntoma: errores de importación en TTS relacionados con gruut, numpy o networkx.

```bash
venv\Scripts\activate
pip install "numpy<2.0.0" "networkx<3.0.0"
```

`build.bat` ejecuta este paso automáticamente al final, después de instalar `requirements.txt`.

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

Si tenías instalada la versión anterior, MyVoices detecta automáticamente la base de datos antigua y la renombra a `myvoices_backup.db`. La nueva instalación arranca con una base de datos limpia.  
Las voces WAV del directorio `%APPDATA%\ChatVoice\voices\` se copian automáticamente a `%APPDATA%\MyVoices\voices\` en el primer arranque.

---

## Notas

- **Tamaño del bundle:** ~5-8 GB (principalmente PyTorch + TTS)
- **Sin consola visible:** `console=False` en `MyVoices.spec`. Los logs se consultan desde la UI o en `%APPDATA%\MyVoices\startup.log`.
- **Actualizar sin recompilar:** Para cambios en `static/index.html`, reemplaza el archivo en `dist\MyVoices\_internal\static\`. Para cambios en Python, hay que recompilar con `build.bat`.
- **Versión de Python:** El build debe usar la misma versión de Python que el entorno virtual.
- **build.bat es idempotente:** puedes ejecutarlo varias veces sin problema; reutiliza el venv existente y solo reinstala lo necesario.
