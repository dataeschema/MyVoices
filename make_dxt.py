"""
Crea MyVoices.dxt — extensión de Claude Desktop para instalar el servidor MCP.

Uso:
    python make_dxt.py

Salida:
    MyVoices.dxt  (en la raíz del proyecto)

El .dxt contiene:
    manifest.json   — spec de la extensión (type: python, entry_point + mcp_config)
    mcp_server.py   — requerido por el entry_point del DXT para pasar validación

El comando real que Claude Desktop ejecuta es mcp_server.exe, que referencia
${user_config.myvoices_dir}\\mcp_server.exe. El mcp_server.py está en el bundle
solo para satisfacer la validación del entry_point — no se ejecuta como script.

Instalación en Claude Desktop:
    1. Arrastra MyVoices.dxt a la ventana de Claude Desktop (o doble clic).
    2. Cuando se pida, selecciona la carpeta dist\\MyVoices\\ (la que contiene
       MyVoices.exe y mcp_server.exe).
    3. Arranca MyVoices antes de usar las tools.
"""
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "MyVoices.dxt"

BUNDLE = [
    (ROOT / "dxt" / "manifest.json", "manifest.json"),
    (ROOT / "mcp_server.py",         "mcp_server.py"),
]

for src, _ in BUNDLE:
    if not src.exists():
        raise FileNotFoundError(f"No encontrado: {src}")

if OUT.exists():
    OUT.unlink()

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
    for src, dst in BUNDLE:
        zf.write(src, dst)
        print(f"  + {dst}  ({src.stat().st_size:,} bytes)")

size_kb = OUT.stat().st_size / 1024
print(f"\nCreado: {OUT.name}  ({size_kb:.1f} KB)")
print("Instalar: arrastra MyVoices.dxt a Claude Desktop o ábrelo con doble clic.")
print("Configura la carpeta dist\\MyVoices\\ cuando se solicite.")
