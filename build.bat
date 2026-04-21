@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo   MyVoices - Script de Build automatico
echo ============================================================
echo.

REM ── 1. Verificar Python ──────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado en el PATH.
    echo         Instala Python 3.10+ desde https://www.python.org/downloads/
    pause
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
        pause
        exit /b 1
    )
    echo Entorno virtual creado.
) else (
    echo Entorno virtual encontrado.
)

REM ── 3. Activar venv ──────────────────────────────────────────────────────────
echo Activando entorno virtual...
call venv\Scripts\activate.bat
echo.

REM ── 4. Seleccionar version de PyTorch ───────────────────────────────────────
echo Selecciona tu GPU:
echo   [1] RTX 50xx (Blackwell)        - CUDA 12.8
echo   [2] RTX 20xx / 30xx / 40xx      - CUDA 12.4  (recomendado para la mayoria)
echo   [3] Sin GPU / Solo CPU
echo.
set /p GPU_CHOICE="Elige (1/2/3): "

if "%GPU_CHOICE%"=="1" (
    set CUDA_INDEX=cu128
    echo Usando CUDA 12.8 para Blackwell.
    goto :install_torch
)
if "%GPU_CHOICE%"=="3" (
    set CUDA_INDEX=cpu
    echo Instalando PyTorch solo CPU.
    goto :install_torch
)
set CUDA_INDEX=cu124
echo Usando CUDA 12.4.
echo.

:install_torch
REM ── 6. Instalar PyTorch con la version CUDA correcta ────────────────────────
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
    pause
    exit /b 1
)
echo.

REM ── 7. Re-fijar numpy y networkx (gruut incompatible con versiones nuevas) ──
echo Fijando versiones de numpy y networkx para compatibilidad con gruut...
python -m pip install "numpy<2.0.0" "networkx<3.0.0"
if errorlevel 1 (
    echo [WARN] No se pudieron fijar numpy/networkx. Puede haber conflictos con gruut.
)
echo.

REM ── 8. Instalar dependencias del proyecto ────────────────────────────────────
echo Instalando dependencias (requirements.txt)...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] No se pudo instalar requirements.txt.
    pause
    exit /b 1
)
echo.

REM ── 9. Instalar PyInstaller ──────────────────────────────────────────────────
echo Instalando PyInstaller...
python -m pip install "pyinstaller>=6.0"
if errorlevel 1 (
    echo [ERROR] No se pudo instalar PyInstaller.
    pause
    exit /b 1
)
echo.

REM ── 10. Verificar que el spec existe ─────────────────────────────────────────
if not exist "MyVoices.spec" (
    echo [ERROR] No se encontro MyVoices.spec.
    echo         Ejecuta este script desde la carpeta raiz del proyecto.
    pause
    exit /b 1
)

REM ── 11. Cerrar instancia anterior si sigue corriendo ─────────────────────────
echo Cerrando MyVoices.exe si esta en ejecucion...
taskkill /f /im MyVoices.exe /t >nul 2>&1
timeout /t 2 /nobreak >nul

REM ── 12. Limpiar builds anteriores ────────────────────────────────────────────
if exist "dist\MyVoices" (
    echo Limpiando build anterior en dist\MyVoices...
    rmdir /s /q "dist\MyVoices"
)
if exist "build" (
    rmdir /s /q "build"
)
echo.

REM ── 13. Compilar con PyInstaller ─────────────────────────────────────────────
echo Generando ejecutable con PyInstaller...
echo (Este proceso puede tardar varios minutos)
echo.
python -m PyInstaller MyVoices.spec --noconfirm

if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller fallo. Revisa los mensajes arriba.
    echo         Consulta GUIA_EJECUTABLE.md - seccion Solucion de problemas.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   BUILD COMPLETADO
echo ============================================================
echo.
echo   Ejecutable: dist\MyVoices\MyVoices.exe
echo.
echo   Para distribuir la app, copia TODA la carpeta dist\MyVoices\
echo   El .exe solo NO funciona fuera de esa carpeta.
echo.
echo   NOTA: El modelo XTTSv2 se descarga automaticamente
echo         en la primera ejecucion (~2 GB, solo una vez).
echo.
pause
