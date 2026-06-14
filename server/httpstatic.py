"""
httpstatic.py — Servidor de arquivos estáticos minimalista (asyncio).

Serve a pasta client/ na mesma porta do WebSocket. Conexões HTTP normais
recebem o arquivo e são fechadas (Connection: close); pedidos com
`Upgrade: websocket` são tratados pelo main.py antes de chegar aqui.
"""
import os

import config

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8",
}


def _response(status: str, body: bytes, ctype: str = "text/plain") -> bytes:
    return (
        f"HTTP/1.1 {status}\r\n"
        f"Content-Type: {ctype}\r\n"
        f"Content-Length: {len(body)}\r\n"
        # no-store: o browser NUNCA guarda — F5 sempre traz o JS/CSS novo
        # (evita o clássico "corrigi mas o usuário continua vendo o bug")
        "Cache-Control: no-store, no-cache, must-revalidate, max-age=0\r\n"
        "Pragma: no-cache\r\n"
        "Expires: 0\r\n"
        "Access-Control-Allow-Origin: *\r\n"   # permite detecção via file://
        "Connection: close\r\n\r\n"
    ).encode() + body


def serve(path: str) -> bytes:
    """Monta a resposta HTTP completa para um GET em `path`."""
    if path == "/":
        path = "/index.html"
    path = path.split("?", 1)[0]

    # normaliza e garante que o arquivo está dentro de client/ (sem ../ escapes)
    full = os.path.normpath(os.path.join(config.CLIENT_DIR, path.lstrip("/")))
    if not full.startswith(os.path.normpath(config.CLIENT_DIR)):
        return _response("403 Forbidden", b"403")
    if not os.path.isfile(full):
        return _response("404 Not Found", b"404 - arquivo nao encontrado")

    ext = os.path.splitext(full)[1].lower()
    ctype = CONTENT_TYPES.get(ext, "application/octet-stream")
    with open(full, "rb") as f:
        return _response("200 OK", f.read(), ctype)
