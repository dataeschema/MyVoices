"""
ChatVoice Desktop — Punto de entrada.

Arranca uvicorn en un hilo daemon, espera a que responda y abre
una ventana nativa con pywebview (Edge WebView2 en Windows).

Con console=False todo output estándar se pierde; los errores se
capturan en %APPDATA%\ChatVoice\startup.log y se muestran en un
MessageBox si hay un crash fatal.
"""
import os
import sys
import threading
import time
import traceback


# ── Log de arranque ───────────────────────────────────────────────────────────

def _get_log_dir() -> str:
    """Devuelve %APPDATA%\\ChatVoice, con fallback junto al exe."""
    try:
        if sys.platform == "win32":
            base = os.environ.get("APPDATA", os.path.expanduser("~"))
        else:
            base = os.environ.get("XDG_DATA_HOME",
                                   os.path.join(os.path.expanduser("~"), ".local", "share"))
        d = os.path.join(base, "ChatVoice")
        os.makedirs(d, exist_ok=True)
        return d
    except Exception:
        return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
               else os.path.dirname(os.path.abspath(__file__))


_log_path: str | None = None
_log_file = None


def _log(msg: str) -> None:
    """Escribe una línea con timestamp en startup.log."""
    global _log_file, _log_path
    ts   = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        if _log_file is None:
            _log_path = os.path.join(_get_log_dir(), "startup.log")
            _log_file = open(_log_path, "a", encoding="utf-8", buffering=1)
        _log_file.write(line + "\n")
        _log_file.flush()
    except Exception:
        pass


def _show_error(msg: str) -> None:
    """Muestra un MessageBox de error (Windows, sin consola disponible)."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, "ChatVoice — Error de inicio", 0x10)
    except Exception:
        pass


# ── Esperar servidor ──────────────────────────────────────────────────────────

def _wait_for_server(url: str, timeout: float = 180.0) -> bool:
    import urllib.request

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return True
        except Exception:
            time.sleep(0.4)
    return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    _log("=" * 60)
    _log("ChatVoice arrancando")

    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        os.chdir(exe_dir)
        _log(f"Modo exe  | CWD: {exe_dir}")
        _log(f"_MEIPASS: {getattr(sys, '_MEIPASS', 'N/A')}")
    else:
        _log(f"Modo dev  | CWD: {os.getcwd()}")

    _log(f"Python {sys.version}")

    # ── Importar servidor ─────────────────────────────────────────────────────
    _log("Importando server.py …")
    import uvicorn
    from server import app          # dispara imports pesados (torch, TTS, pygame…)
    _log("server.py importado OK.")

    # ── Arrancar uvicorn en hilo daemon ───────────────────────────────────────
    def _run_server():
        try:
            uvicorn.run(app, host="0.0.0.0", port=8000,
                        log_level="warning", access_log=False,
                        log_config=None)   # no sobreescribir nuestro logging setup
        except Exception as exc:
            _log(f"uvicorn terminó con error: {exc}")

    server_thread = threading.Thread(target=_run_server, daemon=True, name="uvicorn")
    server_thread.start()
    _log("Hilo uvicorn iniciado.")

    # ── Esperar a que el servidor responda ────────────────────────────────────
    status_url = "http://127.0.0.1:8000/api/status"
    _log(f"Esperando servidor en {status_url} (máx. 3 min) …")
    if not _wait_for_server(status_url, timeout=180.0):
        msg = (
            "El servidor no respondió en 3 minutos.\n\n"
            "Puede deberse a:\n"
            "  • Primera descarga del modelo XTTSv2 (~2 GB)\n"
            "  • Error de importación (revisa el log)\n\n"
            f"Log completo:\n{_log_path}"
        )
        _log("ERROR: timeout esperando servidor.")
        _show_error(msg)
        sys.exit(1)

    _log("Servidor listo. Abriendo ventana pywebview …")

    # ── Abrir ventana nativa ──────────────────────────────────────────────────
    import webview

    webview.create_window(
        title="ChatVoice",
        url="http://127.0.0.1:8000",
        width=1100,
        height=760,
        min_size=(800, 600),
        text_select=True,
    )

    try:
        _log("webview.start (edgechromium) …")
        webview.start(gui="edgechromium", debug=False)
    except Exception as e:
        _log(f"edgechromium falló ({e}), usando fallback …")
        webview.start(debug=False)

    _log("Ventana cerrada. ChatVoice terminando.")


# ── Entry point con captura total de crashes ──────────────────────────────────

if __name__ == "__main__":
    try:
        main()
    except Exception:
        tb = traceback.format_exc()
        _log(f"CRASH FATAL:\n{tb}")
        _show_error(
            f"ChatVoice encontró un error fatal al arrancar:\n\n"
            f"{tb[:900]}\n\n"
            f"Log completo en:\n{_log_path}"
        )
        sys.exit(1)
    finally:
        if _log_file:
            try:
                _log_file.close()
            except Exception:
                pass
