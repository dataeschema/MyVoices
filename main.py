"""
MyVoices Desktop — Punto de entrada con splash screen.

Flujo:
  1. Se muestra la splash inmediatamente (pywebview frameless).
  2. En un hilo daemon se importa server.py (torch + TTS model + uvicorn).
  3. La barra de progreso se anima vía evaluate_js mientras carga.
  4. Cuando el servidor responde, se abre la ventana principal y se cierra la splash.
"""
import os
import sys
import threading
import time
import traceback


# ── Splash HTML ───────────────────────────────────────────────────────────────

_SPLASH_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  html, body { width:100%; height:100%; overflow:hidden; }
  body {
    background: #080d17;
    color: #e2e8f0;
    font-family: 'Segoe UI', system-ui, sans-serif;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100vh;
    -webkit-app-region: drag;
    user-select: none;
  }
  .logo {
    font-size: 2.4rem;
    font-weight: 700;
    color: #4f7ef7;
    letter-spacing: -0.5px;
    margin-bottom: 0.35rem;
  }
  .tagline {
    font-size: 0.85rem;
    color: #5a7090;
    margin-bottom: 2.8rem;
  }
  .bar-wrap {
    width: 300px;
    height: 5px;
    background: #0f1729;
    border-radius: 99px;
    overflow: hidden;
    margin-bottom: 1rem;
    border: 1px solid #1e3050;
  }
  .bar {
    height: 100%;
    width: 0%;
    background: linear-gradient(90deg, #4f7ef7, #7c3aed);
    border-radius: 99px;
    transition: width 0.5s cubic-bezier(0.4, 0, 0.2, 1);
  }
  .status { font-size: 0.78rem; color: #5a7090; }
</style>
</head>
<body>
  <div class="logo">MyVoices</div>
  <div class="tagline">Síntesis de voz avanzada</div>
  <div class="bar-wrap"><div class="bar" id="bar"></div></div>
  <div class="status" id="status">Iniciando…</div>
  <script>
    function setProgress(pct, msg) {
      document.getElementById('bar').style.width = pct + '%';
      if (msg !== undefined) document.getElementById('status').textContent = msg;
    }
  </script>
</body>
</html>"""


# ── Log de arranque ───────────────────────────────────────────────────────────

def _get_log_dir() -> str:
    try:
        if sys.platform == "win32":
            base = os.environ.get("APPDATA", os.path.expanduser("~"))
        else:
            base = os.environ.get("XDG_DATA_HOME",
                                   os.path.join(os.path.expanduser("~"), ".local", "share"))
        d = os.path.join(base, "MyVoices")
        os.makedirs(d, exist_ok=True)
        return d
    except Exception:
        return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
               else os.path.dirname(os.path.abspath(__file__))


_log_path: str | None = None
_log_file = None


def _log(msg: str) -> None:
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
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, "MyVoices — Error de inicio", 0x10)
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
    _log("MyVoices arrancando")

    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        os.chdir(exe_dir)
        _log(f"Modo exe  | CWD: {exe_dir}")
        _log(f"_MEIPASS: {getattr(sys, '_MEIPASS', 'N/A')}")
    else:
        _log(f"Modo dev  | CWD: {os.getcwd()}")

    _log(f"Python {sys.version}")

    import webview

    splash = webview.create_window(
        title="MyVoices",
        html=_SPLASH_HTML,
        width=460,
        height=260,
        frameless=True,
        easy_drag=True,
    )

    _result: dict = {}

    def _set_progress(pct: int, msg: str | None = None) -> None:
        try:
            js = f"setProgress({pct})" if msg is None else f"setProgress({pct}, {repr(msg)})"
            splash.evaluate_js(js)
        except Exception:
            pass

    def _load_app() -> None:
        try:
            time.sleep(0.3)  # deja que la splash renderice
            _set_progress(5, "Cargando módulos…")

            # Animación continua 5→70% mientras carga server.py (torch + TTS model)
            # El modelo tarda entre 20-60 segundos; ajustamos el denominador (~50s).
            _stop_anim = threading.Event()
            def _anim():
                t0 = time.monotonic()
                while not _stop_anim.is_set():
                    elapsed = time.monotonic() - t0
                    pct = 5 + min(65, int(elapsed / 50 * 65))
                    _set_progress(pct)
                    time.sleep(0.5)
            threading.Thread(target=_anim, daemon=True).start()

            _log("Importando server.py …")
            import uvicorn
            from server import app
            _log("server.py importado OK.")

            _stop_anim.set()
            _set_progress(75, "Iniciando servidor…")

            def _run_server():
                try:
                    uvicorn.run(app, host="0.0.0.0", port=8000,
                                log_level="warning", access_log=False,
                                log_config=None)
                except Exception as exc:
                    _log(f"uvicorn terminó con error: {exc}")

            server_thread = threading.Thread(target=_run_server, daemon=True, name="uvicorn")
            server_thread.start()
            _log("Hilo uvicorn iniciado.")

            status_url = "http://127.0.0.1:8000/api/status"
            _log(f"Esperando servidor en {status_url} (máx. 3 min) …")

            # Animar 75→95% mientras esperamos al servidor
            _stop_anim2 = threading.Event()
            def _anim2():
                t0 = time.monotonic()
                while not _stop_anim2.is_set():
                    elapsed = time.monotonic() - t0
                    pct = 75 + min(20, int(elapsed / 10 * 20))
                    _set_progress(pct)
                    time.sleep(0.4)
            threading.Thread(target=_anim2, daemon=True).start()

            ok = _wait_for_server(status_url, timeout=180.0)
            _stop_anim2.set()

            if not ok:
                _result["error"] = "timeout"
                _log("ERROR: timeout esperando servidor.")
                splash.destroy()
                return

            _log("Servidor listo. Abriendo ventana principal…")
            _set_progress(100, "¡Listo!")
            time.sleep(0.4)

            webview.create_window(
                title="MyVoices",
                url="http://127.0.0.1:8000",
                width=1100,
                height=760,
                min_size=(800, 600),
                text_select=True,
            )
            splash.destroy()
            _log("Splash cerrada, ventana principal abierta.")

        except Exception:
            tb = traceback.format_exc()
            _log(f"Error en _load_app:\n{tb}")
            _result["error"] = tb
            try:
                splash.destroy()
            except Exception:
                pass

    try:
        _log("webview.start (edgechromium) …")
        webview.start(gui="edgechromium", func=_load_app, debug=False)
    except Exception as e:
        _log(f"edgechromium falló ({e}), usando fallback …")
        webview.start(func=_load_app, debug=False)

    # Errores que ocurrieron dentro de _load_app
    if _result.get("error") == "timeout":
        _show_error(
            "El servidor no respondió en 3 minutos.\n\n"
            "Puede deberse a:\n"
            "  • Primera descarga del modelo XTTSv2 (~2 GB)\n"
            "  • Error de importación (revisa el log)\n\n"
            f"Log completo:\n{_log_path}"
        )
        sys.exit(1)
    elif "error" in _result:
        _show_error(
            f"MyVoices encontró un error al arrancar:\n\n"
            f"{str(_result['error'])[:900]}\n\n"
            f"Log completo:\n{_log_path}"
        )
        sys.exit(1)

    _log("Ventana cerrada. MyVoices terminando.")


# ── Entry point con captura total de crashes ──────────────────────────────────

if __name__ == "__main__":
    try:
        main()
    except Exception:
        tb = traceback.format_exc()
        _log(f"CRASH FATAL:\n{tb}")
        _show_error(
            f"MyVoices encontró un error fatal al arrancar:\n\n"
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
