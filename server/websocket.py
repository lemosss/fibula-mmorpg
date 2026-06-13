"""
websocket.py — Implementação mínima de servidor WebSocket (RFC 6455).

Apenas stdlib: faz o handshake HTTP de upgrade, decodifica/encodifica frames
e expõe uma classe WSConnection com send_json() (síncrono, com buffer) e
recv_json() (assíncrono). Suporta frames de texto, fragmentação, ping/pong
e close. Não suporta extensões (permessage-deflate é recusado por omissão).
"""
import asyncio
import base64
import hashlib
import json
import struct

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONT, OP_TEXT, OP_BIN, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


def make_accept(key: str) -> str:
    """Calcula o Sec-WebSocket-Accept do handshake."""
    digest = hashlib.sha1((key + WS_GUID).encode()).digest()
    return base64.b64encode(digest).decode()


def encode_frame(payload: bytes, opcode: int = OP_TEXT) -> bytes:
    """Monta um frame servidor->cliente (sem máscara), com FIN=1."""
    header = bytearray([0x80 | opcode])
    n = len(payload)
    if n < 126:
        header.append(n)
    elif n < 65536:
        header.append(126)
        header += struct.pack(">H", n)
    else:
        header.append(127)
        header += struct.pack(">Q", n)
    return bytes(header) + payload


class WSConnection:
    """Uma conexão WebSocket já em estado aberto (pós-handshake)."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        self.closed = False

    # ------------------------------------------------------------- envio

    def send_json(self, obj) -> None:
        """Envia um objeto como frame de texto JSON. Não bloqueia (buffer do SO)."""
        if self.closed:
            return
        try:
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.writer.write(encode_frame(data))
        except (ConnectionError, RuntimeError):
            self.closed = True

    def send_pong(self, payload: bytes) -> None:
        if not self.closed:
            self.writer.write(encode_frame(payload, OP_PONG))

    def close_now(self) -> None:
        """Fecha imediatamente sem handshake de close (kick de sessão antiga)."""
        self.closed = True
        try:
            self.writer.close()
        except RuntimeError:
            pass

    async def close(self, code: int = 1000) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.writer.write(encode_frame(struct.pack(">H", code), OP_CLOSE))
            await self.writer.drain()
        except (ConnectionError, RuntimeError):
            pass
        try:
            self.writer.close()
        except RuntimeError:
            pass

    # ----------------------------------------------------------- recepção

    async def _read_frame(self):
        """Lê um frame cru. Retorna (opcode, payload) ou None se a conexão caiu."""
        try:
            head = await self.reader.readexactly(2)
        except (asyncio.IncompleteReadError, ConnectionError):
            return None
        fin = head[0] & 0x80
        opcode = head[0] & 0x0F
        masked = head[1] & 0x80
        length = head[1] & 0x7F
        try:
            if length == 126:
                length = struct.unpack(">H", await self.reader.readexactly(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", await self.reader.readexactly(8))[0]
            if length > 1 << 20:        # 1 MB: muito acima de qualquer mensagem nossa
                return None
            mask = await self.reader.readexactly(4) if masked else b"\x00" * 4
            payload = bytearray(await self.reader.readexactly(length))
        except (asyncio.IncompleteReadError, ConnectionError):
            return None
        if masked:                      # cliente SEMPRE mascara (RFC 6455 §5.3)
            for i in range(length):
                payload[i] ^= mask[i & 3]
        return fin, opcode, bytes(payload)

    async def recv_text(self):
        """
        Lê a próxima mensagem de texto completa (remontando fragmentação).
        Retorna a string, ou None quando a conexão fechar.
        """
        buffer = b""
        while True:
            frame = await self._read_frame()
            if frame is None:
                self.closed = True
                return None
            fin, opcode, payload = frame
            if opcode == OP_CLOSE:
                await self.close()
                return None
            if opcode == OP_PING:
                self.send_pong(payload)
                continue
            if opcode == OP_PONG:
                continue
            if opcode in (OP_TEXT, OP_CONT):
                buffer += payload
                if fin:
                    try:
                        return buffer.decode("utf-8")
                    except UnicodeDecodeError:
                        return None
            # frames binários são ignorados (protocolo do jogo é só texto)

    async def recv_json(self):
        """Lê a próxima mensagem e decodifica como JSON (None se inválida/fechada)."""
        text = await self.recv_text()
        if text is None:
            return None
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return obj if isinstance(obj, dict) else {}
