"""
main.py — Ponto de entrada do servidor Fibula.

Uso:  python server/main.py

Sobe um único servidor asyncio na porta config.PORT que atende:
  - GET normal            -> arquivos estáticos da pasta client/
  - GET com Upgrade: ws   -> sessão WebSocket do jogo

Tarefas de fundo: tick da simulação (100 ms) e salvamento no Ctrl+C.
"""
import asyncio
import sys
import traceback

import config
import httpstatic
from database import Database
from websocket import WSConnection, make_accept
from game.game import Game

game: Game = None  # inicializado no main()


class Session:
    """Estado de uma conexão de cliente (player é None até logar)."""

    def __init__(self, conn: WSConnection):
        self.conn = conn
        self.player = None


async def read_http_request(reader):
    """Lê a request line + headers de uma requisição HTTP."""
    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=10)
    except (asyncio.TimeoutError, ConnectionError):
        return None, {}
    parts = request_line.decode("latin-1").split()
    if len(parts) < 2:
        return None, {}
    path = parts[1]
    headers = {}
    while True:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=10)
        except (asyncio.TimeoutError, ConnectionError):
            return None, {}
        line = line.decode("latin-1").strip()
        if not line:
            break
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return path, headers


async def ws_session(reader, writer, headers):
    """Handshake de upgrade + loop de mensagens de um cliente do jogo."""
    key = headers.get("sec-websocket-key", "")
    accept = make_accept(key)
    writer.write(
        (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
        ).encode()
    )
    await writer.drain()

    conn = WSConnection(reader, writer)
    session = Session(conn)
    try:
        while True:
            msg = await conn.recv_json()
            if msg is None:
                break
            try:
                game.handle(session, msg)
            except Exception:
                # um handler com bug não pode derrubar o servidor inteiro
                print(f"[erro] processando {msg.get('type')}:", file=sys.stderr)
                traceback.print_exc()
    finally:
        if session.player is not None:
            # em combate PvP o personagem fica no mundo até o lock expirar
            game.handle_disconnect(session.player)
        await conn.close()


async def handle_connection(reader, writer):
    """Roteia cada conexão TCP: WebSocket (jogo) ou HTTP estático (cliente)."""
    try:
        path, headers = await read_http_request(reader)
        if path is None:
            writer.close()
            return
        if headers.get("upgrade", "").lower() == "websocket":
            await ws_session(reader, writer, headers)
        else:
            writer.write(httpstatic.serve(path))
            await writer.drain()
            writer.close()
    except (ConnectionError, asyncio.CancelledError):
        pass
    except Exception:
        traceback.print_exc()
        try:
            writer.close()
        except Exception:
            pass


async def tick_loop():
    while True:
        await asyncio.sleep(config.TICK_MS / 1000)
        try:
            game.tick()
        except Exception:
            print("[erro] no tick:", file=sys.stderr)
            traceback.print_exc()


async def main():
    global game
    db = Database()
    game = Game(db)

    server = await asyncio.start_server(handle_connection, config.HOST, config.PORT)
    print("=" * 56)
    print("  FIBULA — servidor no ar!")
    print(f"  Jogue em:  http://localhost:{config.PORT}")
    print("  (Ctrl+C para desligar; personagens são salvos)")
    print("=" * 56)

    ticker = asyncio.create_task(tick_loop())
    try:
        async with server:
            await server.serve_forever()
    finally:
        ticker.cancel()
        game.save_all()
        db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[shutdown] servidor desligado, personagens salvos.")
