@echo off
setlocal enabledelayedexpansion
REM ============================================================
REM   MyVoices — Script de build automatico (idempotente)
REM
REM   Uso:
REM     build.bat                    Build interactivo (pregunta GPU
REM                                  la primera vez, luego la cachea
REM                                  en .build_config).
REM     build.bat --reset-gpu        Olvida la GPU cacheada y vuelve
REM                                  a preguntar.
REM     build.bat --skip-deps        Salta pip install (PyTorch +
REM                                  requirements). Util si solo
REM                                  cambiaste static/index.html o
REM                                  el .spec.
REM     build.bat --ci               Modo no interactivo (no pause,
REM                                  exit codes utiles para CI).
REM ============================================================

REM ── Parse de banderas ────────────────────────────────────────────────────────
set "RESET_GPU=0"
set "SKIP_DEPS=0"
set "CI_MODE=0"
:parse_args
if "%~1"==""              goto :done_args
if "%~1"=="--reset-gpu"   ( set "RESET_GPU=1" & shift & goto :parse_args )
if "%~1"=="--skip-deps"   ( set "SKIP_DEPS=1" & shift & goto :parse_args )
if "%~1"=="--ci"          ( set "CI_MODE=1"   & shift & goto :parse_args )
echo [WARN] Bandera desconocida: %~1
shift
goto :parse_args
:done_args

REM ── Marcar inicio para reportar duracion al final ────────────────────────────
for /f %%t in ('powershell -nop -c "[int][double]::Parse((Get-Date -UFormat %%s))"') do set "T0=%%t"

echo ============================================================
echo   MyVoices - Script de Build automatico
echo ============================================================
echo.

REM ── 1. Verificar Python ──────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado en el PATH.
    echo         Instala Python 3.10+ desde https://www.python.org/downloads/
    if "%CI_MODE%"=="0" pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version') do echo Usando %%v
echo.

REM ── 2. Crear venv si no existe ───────────────────────────────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo Creando entorno virtual...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual.
        if "%CI_MODE%"=="0" pause
        exit /b 1
    )
    echo Entorno virtual creado.
) else (
    echo Entorno virtual encontrado.
)

REM ── 3. Activar venv ──────────────────────────────────────────────────────────
call venv\Scripts\activate.bat
echo.

REM ── 4. Selector de GPU (con cache en .build_config) ──────────────────────────
REM Estructura aplanada: evita la trampa clasica de cmd donde %GPU_CHOICE% se
REM expande en parse-time dentro de un bloque IF (...). Aqui cada accion vive
REM en su propia linea para que la siguiente vea el valor ya asignado.
set "GPU_CHOICE_FILE=.build_config"
if "%RESET_GPU%"=="1" if exist "%GPU_CHOICE_FILE%" del "%GPU_CHOICE_FILE%"

set "GPU_CHOICE="
if exist "%GPU_CHOICE_FILE%" for /f "usebackq tokens=*" %%v in ("%GPU_CHOICE_FILE%") do set "GPU_CHOICE=%%v"

REM Validar cache: si tiene un valor distinto de 1/2/3 lo descartamos.
if "%GPU_CHOICE%"=="" goto :no_cache
if "%GPU_CHOICE%"=="1" goto :cache_ok
if "%GPU_CHOICE%"=="2" goto :cache_ok
if "%GPU_CHOICE%"=="3" goto :cache_ok
echo [WARN] %GPU_CHOICE_FILE% contiene un valor invalido — ignorando.
del "%GPU_CHOICE_FILE%" >nul 2>&1
set "GPU_CHOICE="
goto :no_cache

:cache_ok
echo GPU cacheada: %GPU_CHOICE%   (usa --reset-gpu para cambiar)

:no_cache
if "%GPU_CHOICE%"=="" if "%CI_MODE%"=="1" (
    echo [ERROR] --ci requiere %GPU_CHOICE_FILE% pre-existente.
    echo         Ejecuta build.bat sin --ci una vez para cachear la GPU.
    exit /b 1
)
if "%GPU_CHOICE%"=="" goto :ask_gpu
goto :gpu_resolved

:ask_gpu
echo Selecciona tu GPU:
echo   [1] RTX 50xx (Blackwell)        - CUDA 12.8
echo   [2] RTX 20xx / 30xx / 40xx      - CUDA 12.4  (recomendado para la mayoria)
echo   [3] Sin GPU / Solo CPU
echo.
set /p GPU_CHOICE="Elige (1/2/3): "
if not "%GPU_CHOICE%"=="1" if not "%GPU_CHOICE%"=="2" if not "%GPU_CHOICE%"=="3" (
    echo [ERROR] Opcion invalida. Introduce 1, 2 o 3.
    echo.
    set "GPU_CHOICE="
    goto :ask_gpu
)
> "%GPU_CHOICE_FILE%" echo %GPU_CHOICE%
echo Eleccion guardada en %GPU_CHOICE_FILE%.

:gpu_resolved
if "%GPU_CHOICE%"=="1" set "CUDA_INDEX=cu128"
if "%GPU_CHOICE%"=="2" set "CUDA_INDEX=cu124"
if "%GPU_CHOICE%"=="3" set "CUDA_INDEX=cpu"
echo.

REM ── 5. PyTorch (skip si ya esta la version correcta) ────────────────────────
if "%SKIP_DEPS%"=="1" (
    echo Saltando instalacion de dependencias ^(--skip-deps^).
    goto :verify_spec
)

set "NEED_TORCH=1"
python -c "import torch,sys,os; e=os.environ['CUDA_INDEX']; ec={'cu128':'12.8','cu124':'12.4','cpu':'cpu'}[e]; a=torch.version.cuda or 'cpu'; sys.exit(0 if (ec=='cpu' and a=='cpu') or (a and a.startswith(ec)) else 1)" 2>nul
if not errorlevel 1 (
    echo PyTorch ya instalado con %CUDA_INDEX% — saltando.
    set "NEED_TORCH=0"
)

if "%NEED_TORCH%"=="1" (
    if "%CUDA_INDEX%"=="cpu" (
        echo Instalando PyTorch ^(solo CPU^)...
        python -m pip install --upgrade torch torchaudio torchvision
    ) else (
        echo Instalando PyTorch con %CUDA_INDEX%...
        python -m pip install --upgrade --force-reinstall torch torchaudio torchvision ^
            --index-url https://download.pytorch.org/whl/%CUDA_INDEX%
    )
    if errorlevel 1 (
        echo [ERROR] No se pudo instalar PyTorch.
        if "%CI_MODE%"=="0" pause
        exit /b 1
    )
    echo.
)

REM ── 6. requirements.txt ──────────────────────────────────────────────────────
echo Instalando dependencias del proyecto ^(requirements.txt^)...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] No se pudo instalar requirements.txt.
    if "%CI_MODE%"=="0" pause
    exit /b 1
)
echo.

REM ── 7. requirements-dev.txt (incluye PyInstaller) ───────────────────────────
echo Instalando dependencias de desarrollo ^(requirements-dev.txt^)...
python -m pip install -r requirements-dev.txt
if errorlevel 1 (
    echo [ERROR] No se pudo instalar requirements-dev.txt.
    if "%CI_MODE%"=="0" pause
    exit /b 1
)
echo.

REM Nota: numpy^<2.0.0 y networkx^<3.0.0 ya estan pineados en requirements.txt
REM       (gruut los necesita asi). No se requiere paso extra.

:verify_spec
REM ── 8. Verificar que el .spec existe ─────────────────────────────────────────
if not exist "MyVoices.spec" (
    echo [ERROR] No se encontro MyVoices.spec.
    echo         Ejecuta este script desde la carpeta raiz del proyecto.
    if "%CI_MODE%"=="0" pause
    exit /b 1
)

REM ── 9. Cerrar instancia anterior solo si esta corriendo ─────────────────────
tasklist /fi "imagename eq MyVoices.exe" 2>nul | find /i "MyVoices.exe" >nul
if not errorlevel 1 (
    echo Cerrando MyVoices.exe en ejecucion...
    taskkill /f /im MyVoices.exe /t >nul 2>&1
    REM 5 s da margen al SO para liberar handles antes de borrar el bundle
    timeout /t 5 /nobreak >nul
)

REM ── 10. Limpiar builds anteriores ────────────────────────────────────────────
REM Si el rmdir falla (Defender bloqueando un fichero, lock residual...),
REM renombramos el dir al lateral con timestamp y dejamos que el siguiente
REM build / un cleanup manual lo borre. PyInstaller solo necesita que la ruta
REM destino este libre para crear la suya.
if exist "dist\MyVoices" (
    echo Limpiando dist\MyVoices...
    rmdir /s /q "dist\MyVoices" 2>nul
    if exist "dist\MyVoices" (
        for /f "tokens=*" %%t in ('powershell -nop -c "Get-Date -Format yyyyMMddHHmmss"') do set "_TS=%%t"
        echo [WARN] No se pudo borrar dist\MyVoices ^(fichero bloqueado por antivirus o handle residual^)
        echo        Renombrando a dist\.trash_!_TS! y continuando...
        ren "dist\MyVoices" ".trash_!_TS!" >nul 2>&1
        if exist "dist\MyVoices" (
            echo [ERROR] Tampoco se puede renombrar. Comprueba:
            echo         1^) Que MyVoices.exe no este corriendo
            echo         2^) Que Windows Defender no este escaneando dist\
            echo            ^(añade exclusion para %CD%\dist^)
            echo         3^) Que ninguna ventana de Explorer tenga dist\MyVoices abierto
            if "%CI_MODE%"=="0" pause
            exit /b 1
        )
    )
)
if exist "build" rmdir /s /q "build" 2>nul
echo.

REM ── 11. Compilar con PyInstaller (--clean para evitar caches stale) ─────────
REM El (call ) "rearma" errorlevel a 0 para que la captura post-comando
REM refleje SOLO el resultado de PyInstaller (otros comandos previos como
REM 'find' pueden dejar errorlevel=1 sin que sea un fallo real del build).
(call )
echo Generando ejecutable con PyInstaller...
echo ^(este proceso puede tardar varios minutos^)
echo.
python -m PyInstaller MyVoices.spec --noconfirm --clean
set "PYINST_EXIT=%errorlevel%"
if not "%PYINST_EXIT%"=="0" (
    echo.
    echo [ERROR] PyInstaller fallo con codigo %PYINST_EXIT%.
    echo         Consulta GUIA_EJECUTABLE.md - seccion Solucion de problemas.
    if "%CI_MODE%"=="0" pause
    exit /b 1
)

REM ── 12. Mover mcp_server.exe al bundle principal ────────────────────────────
REM PyInstaller genera dist\mcp_server.exe (onefile). Lo movemos a
REM dist\MyVoices\ para que viaje junto al ejecutable principal.
if exist "dist\mcp_server.exe" (
    echo Moviendo mcp_server.exe a dist\MyVoices\...
    move /y "dist\mcp_server.exe" "dist\MyVoices\mcp_server.exe" >nul
    echo mcp_server.exe listo en dist\MyVoices\.
) else (
    echo [WARN] dist\mcp_server.exe no encontrado ^(la compilacion puede haber fallado^).
)
echo.

REM ── 13. Reporte final: duracion y tamano del bundle ─────────────────────────
for /f %%t in ('powershell -nop -c "[int][double]::Parse((Get-Date -UFormat %%s))"') do set "T1=%%t"
set /a DURATION_SEC=%T1%-%T0%
set /a DURATION_MIN=DURATION_SEC/60
set /a DURATION_RES=DURATION_SEC%%60

set "BUILD_SIZE=N/A"
for /f "usebackq tokens=*" %%s in (`powershell -nop -c "if (Test-Path 'dist\MyVoices') { '{0:N1} GB' -f ((Get-ChildItem 'dist\MyVoices' -Recurse -File | Measure-Object Length -Sum).Sum / 1GB) } else { 'N/A' }"`) do set "BUILD_SIZE=%%s"

echo.
echo ============================================================
echo   BUILD COMPLETADO
echo ============================================================
echo.
echo   Ejecutable:  dist\MyVoices\MyVoices.exe
echo   MCP server:  dist\MyVoices\mcp_server.exe
echo   Tamano:      %BUILD_SIZE%
echo   Duracion:    %DURATION_MIN%m %DURATION_RES%s
echo.
echo   Para distribuir la app, copia TODA la carpeta dist\MyVoices\
echo   El .exe solo NO funciona fuera de esa carpeta.
echo.
echo   Para Claude Desktop: usa el boton "Descargar .dxt" en la app y
echo   configura la carpeta dist\MyVoices\ al instalarlo.
echo.
echo   NOTA: El modelo XTTSv2 se descarga automaticamente
echo         en la primera ejecucion ^(~2 GB, solo una vez^).
echo.
if "%CI_MODE%"=="0" pause
exit /b 0
