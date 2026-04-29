"""
MyVoices MCP server — modo **stdio**.

Para clientes que lanzan el servidor como subprocess (Claude Desktop con
config legacy, Cline, etc.). Las tools están en `mcp_tools.py` y se
comparten con el modo HTTP/SSE embebido en la app.

Uso típico (Claude Desktop, claude_desktop_config.json):

    {
      "mcpServers": {
        "myvoices": {
          "command": "C:/ruta/MyVoices/venv/Scripts/python.exe",
          "args":    ["C:/ruta/MyVoices/mcp_server.py"],
          "env":     { "MYVOICES_URL": "http://localhost:8000" }
        }
      }
    }

La app de MyVoices debe estar corriendo (la ventana de escritorio o
`python main.py`) en `MYVOICES_URL` antes de que el modelo invoque las
herramientas; este servidor solo redirige peticiones HTTP.

Si prefieres conectar el modelo por **HTTP** (un solo proceso, toggle
desde la UI), activa MCP en la app de MyVoices y configura tu cliente
con la URL `http://localhost:8000/mcp/` y el Bearer token mostrado en
la UI. No necesitas este script en ese caso.
"""
from mcp_tools import build_mcp_server

mcp = build_mcp_server()


if __name__ == "__main__":
    mcp.run()
