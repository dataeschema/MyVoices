"""
MyVoices Desktop — Punto de entrada con splash screen.

Flujo:
  1. Splash tkinter aparece casi instantáneamente (stdlib, <100 ms).
  2. Hilo daemon: importa webview, server.py (torch+TTS), arranca uvicorn.
  3. La barra de progreso se actualiza vía cola thread-safe.
  4. Cuando el servidor responde, se cierra la splash y se abre webview.
"""
import os
import queue
import sys
import threading
import time
import tkinter as tk
import traceback

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


# ── Splash tkinter ────────────────────────────────────────────────────────────

def _build_splash():
    """
    Crea y devuelve la ventana tkinter frameless con barra de progreso.
    Devuelve (root, set_progress, close_splash).
    set_progress(pct, msg=None) es thread-safe.
    close_splash() destruye la ventana desde cualquier hilo.
    """
    root = tk.Tk()
    root.overrideredirect(True)          # sin borde ni barra de título
    root.configure(bg="#080d17")
    root.attributes("-topmost", True)    # encima de todo hasta que se cierre

    W, H = 460, 260
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")

    # ── Contenido ──
    tk.Label(root, text="MyVoices",
             font=("Segoe UI", 28, "bold"), fg="#4f7ef7", bg="#080d17"
             ).pack(pady=(48, 4))
    tk.Label(root, text="Síntesis de voz avanzada",
             font=("Segoe UI", 10), fg="#5a7090", bg="#080d17"
             ).pack(pady=(0, 28))

    # Barra de progreso (canvas dibujado, sin depender de ttk themes)
    c = tk.Canvas(root, width=300, height=6, bg="#0f1729",
                  highlightthickness=1, highlightbackground="#1e3050")
    c.pack()
    bar = c.create_rectangle(0, 0, 0, 6, fill="#4f7ef7", outline="")

    status_lbl = tk.Label(root, text="Iniciando…",
                          font=("Segoe UI", 9), fg="#5a7090", bg="#080d17")
    status_lbl.pack(pady=(12, 0))

    # ── Arrastrable desde cualquier punto ──
    def _drag_start(e):
        root._dx, root._dy = e.x, e.y
    def _drag_move(e):
        root.geometry(f"+{root.winfo_x()+e.x-root._dx}+{root.winfo_y()+e.y-root._dy}")
    root.bind("<Button-1>",  _drag_start)
    root.bind("<B1-Motion>", _drag_move)

    # ── Cola thread-safe para actualizar widgets desde el hilo daemon ──
    _q: queue.Queue = queue.Queue()

    def _poll():
        try:
            while True:
                _q.get_nowait()()
        except queue.Empty:
            pass
        root.after(40, _poll)

    root.after(40, _poll)

    def set_progress(pct: int, msg: str | None = None) -> None:
        def _do():
            c.coords(bar, 0, 0, 300 * pct / 100, 6)
            if msg is not None:
                status_lbl.config(text=msg)
        _q.put(_do)

    def close_splash() -> None:
        _q.put(root.destroy)

    return root, set_progress, close_splash


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

    # Splash aparece antes de cualquier import pesado
    root, set_progress, close_splash = _build_splash()
    _log("Splash tkinter creada.")

    _result: dict = {}

    def _load_everything() -> None:
        try:
            set_progress(5, "Cargando módulos…")

            # Importar webview aquí (tarda ~1-3 s) para que cuando lo
            # necesitemos después de mainloop() ya esté en sys.modules.
            import webview  # noqa: F401

            set_progress(10, "Cargando módulos…")

            # Animar 10→72 % mientras carga server.py (torch + TTS model)
            _stop = threading.Event()
            def _anim():
                t0 = time.monotonic()
                while not _stop.is_set():
                    elapsed = time.monotonic() - t0
                    pct = 10 + min(62, int(elapsed / 50 * 62))
                    set_progress(pct)
                    time.sleep(0.5)
            threading.Thread(target=_anim, daemon=True).start()

            _log("Importando server.py …")
            import uvicorn

            from server import app
            _log("server.py importado OK.")

            _stop.set()
            set_progress(75, "Iniciando servidor…")

            def _run_server():
                try:
                    uvicorn.run(app, host="0.0.0.0", port=8000,
                                log_level="warning", access_log=False,
                                log_config=None)
                except Exception as exc:
                    _log(f"uvicorn terminó con error: {exc}")

            threading.Thread(target=_run_server, daemon=True, name="uvicorn").start()
            _log("Hilo uvicorn iniciado.")

            status_url = "http://127.0.0.1:8000/api/status"
            _log(f"Esperando servidor en {status_url} …")

            _stop2 = threading.Event()
            def _anim2():
                t0 = time.monotonic()
                while not _stop2.is_set():
                    elapsed = time.monotonic() - t0
                    pct = 75 + min(20, int(elapsed / 10 * 20))
                    set_progress(pct)
                    time.sleep(0.4)
            threading.Thread(target=_anim2, daemon=True).start()

            ok = _wait_for_server(status_url, timeout=180.0)
            _stop2.set()

            if not ok:
                _result["error"] = "timeout"
                _log("ERROR: timeout esperando servidor.")
                close_splash()
                return

            _log("Servidor listo.")
            set_progress(100, "¡Listo!")
            time.sleep(0.35)
            close_splash()

        except Exception:
            tb = traceback.format_exc()
            _log(f"Error en _load_everything:\n{tb}")
            _result["error"] = tb
            close_splash()

    threading.Thread(target=_load_everything, daemon=True).start()
    root.mainloop()   # bloquea hasta que close_splash() llame a root.destroy()

    # ── Errores capturados durante la carga ───────────────────────────────────
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

    # ── Abrir ventana principal pywebview ─────────────────────────────────────
    _log("Abriendo ventana pywebview …")
    import webview  # ya en sys.modules, import instantáneo

    webview.create_window(
        title="MyVoices",
        url="http://127.0.0.1:8000",
        width=1100,
        height=760,
        min_size=(800, 600),
        text_select=True,
    )
    try:
        webview.start(gui="edgechromium", debug=False)
    except Exception as e:
        _log(f"edgechromium falló ({e}), usando fallback …")
        webview.start(debug=False)

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
