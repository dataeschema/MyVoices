@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo   ChatVoice - Script de Build
echo ============================================================
echo.

REM Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado en el PATH.
    echo         Instala Python 3.10+ desde https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version') do echo Usando %%v
echo.

REM Activar entorno virtual si existe y no esta ya activo
if exist "venv\Scripts\activate.bat" (
    if not defined VIRTUAL_ENV (
        echo Activando entorno virtual...
        call venv\Scripts\activate.bat
    ) else (
        echo Entorno virtual ya activo: %VIRTUAL_ENV%
    )
) else (
    echo ADVERTENCIA: No se encontro un entorno virtual "venv".
)
echo.

REM Instalar pywebview
echo Instalando pywebview...
python -m pip install "pywebview>=5.0"
if errorlevel 1 (
    echo [ERROR] No se pudo instalar pywebview.
    pause
    exit /b 1
)
echo.

REM Instalar PyInstaller
echo Instalando PyInstaller...
python -m pip install "pyinstaller>=6.0"
if errorlevel 1 (
    echo [ERROR] No se pudo instalar PyInstaller.
    pause
    exit /b 1
)
echo.

REM Verificar que el spec existe
if not exist "ChatVoice.spec" (
    echo [ERROR] No se encontro ChatVoice.spec.
    echo         Ejecuta este script desde la carpeta raiz del proyecto.
    pause
    exit /b 1
)

REM Cerrar instancia anterior si sigue corriendo (evita "Acceso denegado" al limpiar)
echo Cerrando ChatVoice.exe si esta en ejecucion...
taskkill /f /im ChatVoice.exe /t >nul 2>&1
timeout /t 2 /nobreak >nul

REM Limpiar builds anteriores
if exist "dist\ChatVoice" (
    echo Limpiando build anterior en dist\ChatVoice...
    rmdir /s /q "dist\ChatVoice"
)
if exist "build" (
    rmdir /s /q "build"
)
echo.

REM Ejecutar PyInstaller
echo Generando ejecutable con PyInstaller...
echo (Este proceso puede tardar varios minutos)
echo.
python -m PyInstaller ChatVoice.spec --noconfirm

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
echo   Ejecutable: dist\ChatVoice\ChatVoice.exe
echo.
echo   Para distribuir la app, copia TODA la carpeta dist\ChatVoice\
echo   El .exe solo NO funciona fuera de esa carpeta.
echo.
echo   NOTA: El modelo XTTSv2 se descarga automaticamente
echo         en la primera ejecucion (~2 GB, solo una vez).
echo.
pause
