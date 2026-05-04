"""
Crea MyVoices.dxt — extensión de Claude Desktop para instalar el servidor MCP.

Uso:
    python make_dxt.py

Salida:
    MyVoices.dxt  (en la raíz del proyecto)

El .dxt es un ZIP con un único archivo: manifest.json.
El servidor MCP real (mcp_server.exe) se genera con build.bat y queda en
dist\\MyVoices\\. El manifest lo referencia vía ${user_config.myvoices_dir}.

Instalación en Claude Desktop:
    1. Arrastra MyVoices.dxt a la ventana de Claude Desktop (o doble clic).
    2. Cuando se pida, selecciona la carpeta dist\\MyVoices\\.
    3. Arranca MyVoices antes de usar las tools.
"""
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "MyVoices.dxt"

manifest = ROOT / "dxt" / "manifest.json"
if not manifest.exists():
    raise FileNotFoundError(f"No encontrado: {manifest}")

if OUT.exists():
    OUT.unlink()

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.write(manifest, "manifest.json")
    print(f"  + manifest.json  ({manifest.stat().st_size:,} bytes)")

size_kb = OUT.stat().st_size / 1024
print(f"\nCreado: {OUT.name}  ({size_kb:.1f} KB)")
print("Instalar: arrastra MyVoices.dxt a Claude Desktop o ábrelo con doble clic.")
print("Configura la carpeta dist\\MyVoices\\ cuando se solicite.")
