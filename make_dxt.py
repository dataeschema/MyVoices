"""
Crea MyVoices.dxt — extensión de Claude Desktop para instalar el servidor MCP.

Uso:
    python make_dxt.py

Salida:
    MyVoices.dxt  (en la raíz del proyecto)

El .dxt es un ZIP renombrado con:
    manifest.json   — spec de la extensión
    mcp_server.py   — servidor MCP stdio (entry point)
    mcp_tools.py    — tools MCP compartidas

El usuario solo necesita:
    1. Abrir MyVoices.dxt (doble clic en Claude Desktop o arrastrar)
    2. Configurar la carpeta raíz de MyVoices cuando Claude Desktop lo pida
    3. Arrancar la app MyVoices antes de usar las tools
"""
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "MyVoices.dxt"

BUNDLE = [
    (ROOT / "dxt" / "manifest.json", "manifest.json"),
    (ROOT / "mcp_server.py",         "mcp_server.py"),
    (ROOT / "mcp_tools.py",          "mcp_tools.py"),
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
