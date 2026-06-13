"""
minipng.py — Escritor de PNG minimalista usando apenas a stdlib (struct + zlib).

Evita dependência do Pillow: gera PNGs RGBA 8-bit sem compressão sofisticada,
suficiente para os sprites placeholder do jogo.
"""
import struct
import zlib


def _chunk(tag: bytes, data: bytes) -> bytes:
    """Monta um chunk PNG: comprimento + tag + dados + CRC32."""
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def write_png(path: str, width: int, height: int, pixels: bytearray) -> None:
    """
    Salva uma imagem RGBA em `path`.

    `pixels` deve ser um bytearray de tamanho width*height*4 (R,G,B,A por pixel,
    linha por linha, de cima para baixo).
    """
    assert len(pixels) == width * height * 4, "buffer de pixels com tamanho errado"

    # Cada scanline é prefixada com o byte de filtro 0 (None)
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)
        raw.extend(pixels[y * stride : (y + 1) * stride])

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _chunk(b"IEND", b"")
    )
    with open(path, "wb") as f:
        f.write(png)
