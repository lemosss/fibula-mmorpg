"""
gensprites.py — Gera a spritesheet placeholder do jogo (pixel art procedural).

Uso:  python tools/gensprites.py

Saída:
  client/assets/sprites.png   — spritesheet 32x32 por célula, 8 colunas
  client/assets/sprites.json  — mapeamento nome -> índice na sheet

Sem dependências externas (usa tools/minipng.py). Toda a arte é desenhada por
código — são placeholders pensados para serem substituídos por sprites reais
no futuro, mantendo os mesmos nomes.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from minipng import write_png

TILE = 32  # tamanho da célula em pixels
COLS = 8   # colunas da spritesheet

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "client", "assets")


# ---------------------------------------------------------------- utilidades

def _lcg(seed: int):
    """Gerador pseudo-aleatório determinístico (mesma arte em toda execução)."""
    s = (seed & 0x7FFFFFFF) or 1
    while True:
        s = (s * 1103515245 + 12345) & 0x7FFFFFFF
        yield s


class Sprite:
    """Buffer RGBA 32x32 com primitivas de desenho simples."""

    def __init__(self):
        self.buf = bytearray(TILE * TILE * 4)  # transparente por padrão

    def px(self, x, y, c):
        if 0 <= x < TILE and 0 <= y < TILE:
            i = (y * TILE + x) * 4
            self.buf[i : i + 4] = bytes(c)

    def rect(self, x, y, w, h, c):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.px(xx, yy, c)

    def outline(self, x, y, w, h, c):
        for xx in range(x, x + w):
            self.px(xx, y, c)
            self.px(xx, y + h - 1, c)
        for yy in range(y, y + h):
            self.px(x, yy, c)
            self.px(x + w - 1, yy, c)

    def disc(self, cx, cy, r, c):
        for yy in range(cy - r, cy + r + 1):
            for xx in range(cx - r, cx + r + 1):
                if (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r:
                    self.px(xx, yy, c)

    def noise(self, base, var, seed, x=0, y=0, w=TILE, h=TILE):
        """Preenche a região com a cor base + variação de brilho por pixel."""
        rng = _lcg(seed)
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                d = (next(rng) % (2 * var + 1)) - var
                c = tuple(max(0, min(255, ch + d)) for ch in base[:3]) + (255,)
                self.px(xx, yy, c)

    def blobs(self, base, lighten, count, radius, seed):
        """Manchas suaves de cor (variação grande, estilo RotMG)."""
        rng = _lcg(seed)
        for _ in range(count):
            cx, cy = next(rng) % TILE, next(rng) % TILE
            r = 1 + next(rng) % radius
            for yy in range(cy - r, cy + r + 1):
                for xx in range(cx - r, cx + r + 1):
                    if (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r:
                        i = (yy * TILE + xx) * 4 if 0 <= xx < TILE and 0 <= yy < TILE else -1
                        if i >= 0 and self.buf[i + 3]:
                            cur = self.buf[i:i + 3]
                            self.px(xx, yy, tuple(
                                max(0, min(255, cur[k] + lighten)) for k in range(3)
                            ) + (255,))

    # ---- pós-processamento estilo Realm of the Mad God -------------------

    def add_shadow(self, cx=16, cy=30, rx=9, ry=3, alpha=95):
        """Sombra elíptica translúcida sob a figura (só em pixels vazios)."""
        for yy in range(cy - ry, cy + ry + 1):
            for xx in range(cx - rx, cx + rx + 1):
                if 0 <= xx < TILE and 0 <= yy < TILE:
                    dx, dy = (xx - cx) / rx, (yy - cy) / ry
                    if dx * dx + dy * dy <= 1.0:
                        i = (yy * TILE + xx) * 4
                        if self.buf[i + 3] == 0:
                            self.buf[i:i + 4] = bytes((0, 0, 0, alpha))

    def add_outline(self, color=(26, 22, 32, 255)):
        """Contorno escuro de 1px ao redor dos pixels opacos (signature RotMG)."""
        src = bytes(self.buf)
        nb = ((-1, 0), (1, 0), (0, -1), (0, 1),
              (-1, -1), (1, -1), (-1, 1), (1, 1))
        for yy in range(TILE):
            for xx in range(TILE):
                i = (yy * TILE + xx) * 4
                if src[i + 3] != 0:
                    continue
                for dx, dy in nb:
                    nx, ny = xx + dx, yy + dy
                    if 0 <= nx < TILE and 0 <= ny < TILE:
                        if src[(ny * TILE + nx) * 4 + 3] >= 200:
                            self.buf[i:i + 4] = bytes(color)
                            break


def _clamp(v):
    return max(0, min(255, v))


def shade(c, d):
    """Clareia (d>0) ou escurece (d<0) uma cor RGB."""
    return (_clamp(c[0] + d), _clamp(c[1] + d), _clamp(c[2] + d), 255)


# Cores nomeadas (RGBA)
BLACK = (10, 10, 10, 255)
SKIN = (232, 184, 138, 255)
GREEN_SKIN = (110, 160, 70, 255)


def _legs_fb(spr, legs, step):
    """Pernas de frente/costas; step 1/2 = passada (uma sobe, outra pisa)."""
    ya, yb = 24, 24
    if step == 1:
        ya, yb = 23, 25
    elif step == 2:
        ya, yb = 25, 23
    spr.rect(11, ya, 4, 6, legs)
    spr.rect(17, yb, 4, 6, legs)
    spr.rect(10, ya + 5, 5, 2, shade(legs, -40))   # botas
    spr.rect(17, yb + 5, 5, 2, shade(legs, -40))


def _legs_side(spr, legs, step):
    """Pernas de perfil; step 1 = passada larga, step 2 = juntas."""
    if step == 1:
        bx, fx = 11, 18
    elif step == 2:
        bx, fx = 14, 15
    else:
        bx, fx = 12, 15
    spr.rect(bx, 24, 4, 6, shade(legs, -28))   # perna de trás
    spr.rect(fx, 24, 4, 6, legs)               # perna da frente
    spr.rect(min(bx, fx) + 1, 29, 6, 2, shade(legs, -45))


def _humanoid_front(spr, tunic, legs, hair, skin, helmet, step=0):
    """Humanoide visto de FRENTE (andando para baixo / parado)."""
    _legs_fb(spr, legs, step)                  # pernas (com passada)
    spr.rect(9, 14, 14, 10, tunic)             # torso
    spr.rect(9, 14, 14, 2, shade(tunic, 25))   # ombros iluminados
    spr.rect(6, 15, 3, 8, shade(tunic, -20))   # braços
    spr.rect(23, 15, 3, 8, shade(tunic, -20))
    spr.rect(6, 22, 3, 3, skin)                # mãos
    spr.rect(23, 22, 3, 3, skin)
    spr.rect(11, 5, 10, 9, skin)               # cabeça
    if helmet:
        spr.rect(10, 3, 12, 5, helmet)
        spr.rect(10, 3, 12, 2, shade(helmet, 30))
    else:
        spr.rect(10, 3, 12, 4, hair)
    spr.px(13, 9, BLACK)                        # olhos
    spr.px(18, 9, BLACK)
    spr.outline(9, 14, 14, 10, shade(tunic, -60))


def _humanoid_back(spr, tunic, legs, hair, skin, helmet, step=0):
    """Humanoide visto de COSTAS (andando para cima) — sem rosto."""
    _legs_fb(spr, legs, step)
    spr.rect(9, 14, 14, 10, tunic)
    spr.rect(9, 14, 14, 2, shade(tunic, 25))
    spr.rect(6, 15, 3, 8, shade(tunic, -20))
    spr.rect(23, 15, 3, 8, shade(tunic, -20))
    spr.rect(6, 22, 3, 3, skin)
    spr.rect(23, 22, 3, 3, skin)
    spr.rect(11, 5, 10, 9, skin)               # nuca
    if helmet:
        spr.rect(10, 3, 12, 6, helmet)
        spr.rect(10, 3, 12, 2, shade(helmet, 30))
    else:
        spr.rect(10, 4, 12, 8, hair)           # cabelo cobre a nuca (sem olhos)
    spr.outline(9, 14, 14, 10, shade(tunic, -60))


def _humanoid_side(spr, tunic, legs, hair, skin, helmet, step=0):
    """Humanoide de PERFIL voltado para a direita (leste; oeste = espelho)."""
    _legs_side(spr, legs, step)
    spr.rect(11, 14, 9, 10, tunic)             # torso estreito
    spr.rect(11, 14, 9, 2, shade(tunic, 25))
    spr.rect(10, 15, 2, 8, shade(tunic, -32))  # braço de trás
    spr.rect(19, 16, 3, 7, shade(tunic, -8))   # braço da frente
    spr.rect(20, 22, 3, 3, skin)               # mão da frente
    spr.rect(12, 5, 9, 9, skin)                # cabeça
    if helmet:
        spr.rect(11, 3, 11, 5, helmet)
        spr.rect(11, 3, 11, 2, shade(helmet, 30))
    else:
        spr.rect(11, 3, 10, 4, hair)
    spr.px(19, 9, BLACK)                        # um olho (lado da frente)
    spr.rect(21, 8, 1, 3, skin)                # nariz saliente
    spr.outline(11, 14, 9, 10, shade(tunic, -60))


def humanoid(spr, tunic, legs, hair, skin=SKIN, helmet=None, facing="s", step=0):
    """Humanoide direcional + passada. facing: s/n/e/w; step: 0 parado, 1/2 anda."""
    if facing in ("e", "w"):
        _humanoid_side(spr, tunic, legs, hair, skin, helmet, step)
    elif facing == "n":
        _humanoid_back(spr, tunic, legs, hair, skin, helmet, step)
    else:
        _humanoid_front(spr, tunic, legs, hair, skin, helmet, step)


# ------------------------------------------------------------------- chãos

def d_grass(s):
    # verde vivo com variação suave de tom (estilo RotMG)
    s.noise((86, 168, 74), 7, 101)
    s.blobs((86, 168, 74), 22, 5, 6, 71)        # clareiras iluminadas
    s.blobs((86, 168, 74), -26, 4, 5, 72)       # sombras de relva
    rng = _lcg(7)
    for _ in range(22):                         # folhinhas de capim
        x, y = next(rng) % TILE, next(rng) % TILE
        s.px(x, y, (54, 132, 50, 255))


def d_dirt(s):
    s.noise((150, 108, 62), 8, 102)
    s.blobs((150, 108, 62), 20, 4, 5, 73)
    s.blobs((150, 108, 62), -24, 4, 5, 74)
    rng = _lcg(8)
    for _ in range(10):
        x, y = next(rng) % TILE, next(rng) % TILE
        s.px(x, y, (110, 78, 44, 255))


def d_stone(s):
    s.noise((150, 152, 162), 5, 103)
    s.blobs((150, 152, 162), 16, 3, 5, 75)
    # juntas de pedra (paralelepípedo)
    for y in (0, 11, 22):
        for x in range(TILE):
            s.px(x, y, (108, 110, 120, 255))
    for y0, off in ((0, 0), (11, 16), (22, 8)):
        for yy in range(y0, min(TILE, y0 + 11)):
            s.px(off, yy, (108, 110, 120, 255))


def d_water(s):
    s.noise((46, 120, 214), 7, 104)
    s.blobs((46, 120, 214), 24, 5, 6, 76)       # reflexos claros
    rng = _lcg(9)
    for _ in range(7):                          # cristas de onda
        x, y = next(rng) % 24, next(rng) % TILE
        for i in range(6):
            s.px(x + i, y, (120, 180, 240, 255))


def d_sand(s):
    s.noise((232, 208, 142), 6, 105)
    s.blobs((232, 208, 142), 16, 4, 5, 77)
    s.blobs((232, 208, 142), -18, 3, 4, 78)


def d_marble(s):
    s.noise((226, 226, 234), 4, 106)
    for x in range(TILE):  # juntas do piso polido
        s.px(x, 15, (196, 196, 206, 255))
    for y in range(TILE):
        s.px(15, y, (196, 196, 206, 255))


def d_wood(s):
    s.noise((158, 112, 60, 255), 6, 107)
    for y in (7, 15, 23, 31):  # tábuas horizontais
        for x in range(TILE):
            s.px(x, y, (116, 80, 42, 255))
    for x, y0 in ((10, 0), (22, 8), (6, 16), (26, 24)):
        for yy in range(y0, y0 + 8):
            s.px(x, yy, (116, 80, 42, 255))


def d_cave(s):
    s.noise((72, 66, 82), 7, 108)              # rocha levemente arroxeada
    s.blobs((72, 66, 82), -16, 4, 5, 79)


# ------------------------------------------------------------------ objetos

def d_tree(s):
    s.rect(13, 20, 6, 11, (104, 72, 38, 255))           # tronco
    s.rect(13, 20, 2, 11, (84, 56, 28, 255))            # sombra do tronco
    s.disc(16, 12, 11, (38, 102, 38, 255))              # copa
    s.disc(13, 9, 6, (52, 128, 48, 255))                # luz na copa
    rng = _lcg(11)
    for _ in range(20):
        x = 6 + next(rng) % 20
        y = 3 + next(rng) % 17
        if (x - 16) ** 2 + (y - 12) ** 2 <= 110:
            s.px(x, y, (30, 84, 30, 255))


def d_wall(s):
    s.noise((118, 112, 108), 7, 112)
    for y in (0, 8, 16, 24, 31):                        # fiadas de tijolo
        for x in range(TILE):
            s.px(x, y, (74, 70, 66, 255))
    for row, off in ((0, 0), (8, 16), (16, 0), (24, 16)):
        for yy in range(row, min(TILE, row + 8)):
            s.px(off, yy, (74, 70, 66, 255))
    for x in range(TILE):                               # topo iluminado
        s.px(x, 1, (150, 144, 140, 255))


def d_rock(s):
    s.disc(16, 19, 11, (110, 106, 102, 255))
    s.disc(12, 15, 6, (138, 134, 130, 255))
    s.disc(21, 22, 5, (88, 84, 80, 255))


def d_bush(s):
    s.disc(16, 21, 9, (40, 110, 44, 255))
    s.disc(11, 18, 5, (56, 134, 56, 255))
    s.disc(21, 19, 5, (48, 122, 50, 255))


def d_fence(s):
    wood = (124, 88, 48, 255)
    dark = (94, 64, 32, 255)
    for x in (4, 15, 26):                               # mourões
        s.rect(x, 8, 3, 22, wood)
        s.rect(x, 8, 1, 22, dark)
    s.rect(0, 12, TILE, 3, wood)                        # travessas
    s.rect(0, 21, TILE, 3, wood)


def d_altar(s):
    s.rect(6, 12, 20, 14, (150, 148, 156, 255))         # pedra
    s.rect(6, 12, 20, 3, (190, 188, 198, 255))
    s.rect(8, 10, 16, 4, (60, 90, 160, 255))            # toalha azul
    s.rect(14, 2, 4, 10, (212, 176, 60, 255))           # símbolo dourado
    s.rect(11, 5, 10, 3, (212, 176, 60, 255))


def d_gravestone(s):
    s.rect(10, 10, 12, 18, (130, 128, 134, 255))
    s.disc(16, 11, 6, (130, 128, 134, 255))
    s.rect(15, 13, 2, 9, (90, 88, 94, 255))             # cruz
    s.rect(12, 16, 8, 2, (90, 88, 94, 255))


# ---------------------------------------------------------------- criaturas

def d_player(s, facing="s", step=0):
    humanoid(s, (64, 120, 232, 255), (74, 78, 92, 255), (118, 74, 34, 255),
             facing=facing, step=step)


def d_npc_priest(s, facing="s", step=0):
    humanoid(s, (236, 234, 228, 255), (220, 218, 212, 255), (180, 180, 180, 255),
             facing=facing, step=step)
    if facing == "s":
        s.rect(14, 16, 4, 6, (212, 176, 60, 255))       # símbolo no peito


def d_npc_merchant(s, facing="s", step=0):
    humanoid(s, (122, 86, 44, 255), (74, 56, 34, 255), (50, 38, 24, 255),
             facing=facing, step=step)
    if facing != "n":
        s.rect(9, 21, 14, 3, (60, 110, 60, 255))        # avental verde


def d_npc_guard(s, facing="s", step=0):
    humanoid(
        s,
        (148, 152, 162, 255),
        (108, 112, 122, 255),
        (96, 62, 30, 255),
        helmet=(168, 172, 182, 255),
        facing=facing,
        step=step,
    )
    if facing == "s":
        s.rect(15, 14, 2, 10, (96, 100, 110, 255))      # vinco da armadura


def d_rat(s):
    grey = (128, 122, 116, 255)
    s.disc(14, 20, 7, grey)                             # corpo
    s.disc(22, 17, 4, shade(grey, 12))                  # cabeça
    s.px(24, 16, BLACK)                                 # olho
    s.rect(25, 18, 4, 1, (220, 170, 170, 255))          # focinho
    s.px(20, 12, shade(grey, -20))                      # orelha
    s.px(23, 12, shade(grey, -20))
    for i in range(8):                                  # cauda
        s.px(7 - i // 2, 22 + i // 3, (200, 150, 150, 255))


def d_snake(s):
    g = (70, 140, 60, 255)
    pts = [(6, 24), (9, 22), (12, 20), (15, 19), (18, 19), (21, 20), (23, 17),
           (24, 14), (23, 11), (20, 10)]
    for (x, y) in pts:
        s.disc(x, y, 3, g)
    s.disc(20, 9, 3, shade(g, 18))                      # cabeça
    s.px(21, 8, BLACK)
    s.px(24, 9, (200, 60, 60, 255))                     # língua


def d_wolf(s):
    grey = (110, 110, 116, 255)
    s.rect(7, 16, 16, 8, grey)                          # corpo
    s.rect(20, 11, 8, 7, shade(grey, 10))               # cabeça
    s.rect(21, 9, 2, 3, shade(grey, -15))               # orelhas
    s.rect(25, 9, 2, 3, shade(grey, -15))
    s.px(26, 13, BLACK)                                 # olho
    s.rect(26, 16, 4, 2, shade(grey, -25))              # focinho
    for x in (8, 12, 18, 21):                           # patas
        s.rect(x, 24, 2, 5, shade(grey, -20))
    s.rect(4, 14, 4, 2, grey)                           # cauda


def d_troll(s, facing="s", step=0):
    humanoid(s, (96, 134, 70, 255), (104, 84, 52, 255), (70, 96, 50, 255),
             skin=GREEN_SKIN, facing=facing, step=step)
    if facing == "s":
        s.rect(11, 12, 2, 3, (220, 220, 200, 255))      # dentes para fora
        s.rect(19, 12, 2, 3, (220, 220, 200, 255))
    s.rect(24, 10, 3, 13, (124, 88, 48, 255))           # clava


def d_orc(s, facing="s", step=0):
    humanoid(s, (74, 78, 86, 255), (54, 58, 64, 255), (40, 60, 32, 255),
             skin=(96, 140, 64, 255), facing=facing, step=step)
    if facing == "s":
        s.px(12, 12, (230, 230, 210, 255))              # presas
        s.px(19, 12, (230, 230, 210, 255))
    s.rect(5, 12, 3, 12, (140, 144, 152, 255))          # lâmina na mão


def d_skeleton(s):
    bone = (224, 222, 210, 255)
    s.rect(12, 4, 8, 8, bone)                           # crânio
    s.px(14, 7, BLACK)
    s.px(17, 7, BLACK)
    s.rect(14, 10, 4, 2, (160, 158, 150, 255))          # mandíbula
    s.rect(15, 12, 2, 12, bone)                         # coluna
    for y in (14, 17, 20):                              # costelas
        s.rect(10, y, 12, 1, bone)
    s.rect(9, 13, 2, 9, bone)                           # braços
    s.rect(21, 13, 2, 9, bone)
    s.rect(12, 24, 2, 7, bone)                          # pernas
    s.rect(18, 24, 2, 7, bone)


def d_corpse(s):
    s.disc(16, 18, 9, (122, 40, 36, 255))               # poça
    s.disc(13, 16, 5, (152, 56, 48, 255))
    s.rect(12, 14, 8, 1, (224, 222, 210, 255))          # ossos à mostra
    s.rect(15, 11, 1, 7, (224, 222, 210, 255))


# ------------------------------------------------------------------- itens

def d_gold(s):
    g = (228, 190, 52, 255)
    for (x, y) in ((12, 22), (18, 23), (15, 18), (21, 19), (10, 18)):
        s.disc(x, y, 4, g)
        s.disc(x, y, 2, shade(g, 30))
        s.px(x, y, shade(g, -40))


def d_sword(s):
    blade = (190, 196, 206, 255)
    for i in range(14):                                 # lâmina diagonal
        s.rect(8 + i, 22 - i, 2, 2, blade)
    s.rect(20, 8, 3, 3, shade(blade, 40))               # ponta
    s.rect(8, 20, 6, 2, (124, 88, 48, 255))             # guarda
    s.rect(5, 24, 4, 4, (94, 64, 32, 255))              # punho
    s.disc(5, 27, 2, (212, 176, 60, 255))               # pomo


def d_club(s):
    wood = (134, 96, 52, 255)
    for i in range(16):
        w = 2 + i // 5
        s.rect(8 + i, 24 - i, w, w, wood if i < 11 else shade(wood, -18))
    s.disc(24, 9, 4, shade(wood, -18))


def d_axe(s):
    s.rect(14, 6, 3, 20, (124, 88, 48, 255))            # cabo
    s.rect(10, 5, 12, 6, (168, 172, 182, 255))          # cabeça
    s.rect(8, 6, 3, 4, (198, 202, 212, 255))            # fio
    s.rect(21, 6, 3, 4, (198, 202, 212, 255))


def d_dagger(s):
    blade = (200, 206, 216, 255)
    for i in range(8):
        s.rect(12 + i, 20 - i, 2, 2, blade)
    s.rect(11, 19, 5, 2, (124, 88, 48, 255))
    s.rect(9, 22, 3, 3, (94, 64, 32, 255))


def _torso(s, c):
    s.rect(8, 10, 16, 14, c)
    s.rect(11, 7, 10, 4, shade(c, -15))                 # gola
    s.rect(6, 11, 3, 8, shade(c, -10))                  # mangas
    s.rect(23, 11, 3, 8, shade(c, -10))
    s.outline(8, 10, 16, 14, shade(c, -50))


def d_leather_helmet(s):
    c = (146, 104, 58, 255)
    s.disc(16, 16, 9, c)
    s.rect(7, 16, 18, 6, c)
    s.rect(9, 12, 14, 2, shade(c, 25))


def d_leather_armor(s):
    _torso(s, (146, 104, 58, 255))


def d_leather_legs(s):
    c = (132, 94, 52, 255)
    s.rect(10, 8, 12, 6, c)
    s.rect(10, 14, 5, 12, c)
    s.rect(17, 14, 5, 12, c)
    s.outline(10, 8, 12, 6, shade(c, -50))


def d_leather_boots(s):
    c = (112, 78, 42, 255)
    s.rect(9, 12, 5, 10, c)
    s.rect(9, 21, 8, 4, c)
    s.rect(18, 12, 5, 10, c)
    s.rect(18, 21, 8, 4, c)


def d_chain_armor(s):
    _torso(s, (138, 142, 152, 255))
    rng = _lcg(13)
    for _ in range(40):                                 # textura de elos
        x = 9 + next(rng) % 14
        y = 11 + next(rng) % 12
        s.px(x, y, (108, 112, 122, 255))


def d_plate_armor(s):
    _torso(s, (176, 182, 194, 255))
    s.rect(15, 10, 2, 14, (136, 142, 154, 255))         # vinco central
    s.rect(9, 12, 14, 1, (210, 216, 226, 255))          # brilho


def d_wooden_shield(s):
    s.disc(16, 16, 11, (134, 96, 52, 255))
    s.disc(16, 16, 11, (134, 96, 52, 255))
    for y in range(6, 27, 5):
        for x in range(6, 27):
            if (x - 16) ** 2 + (y - 16) ** 2 <= 117:
                s.px(x, y, (104, 72, 38, 255))
    s.disc(16, 16, 3, (168, 172, 182, 255))             # umbo central


def d_brass_shield(s):
    s.disc(16, 16, 11, (196, 166, 74, 255))
    s.disc(16, 16, 8, (216, 188, 96, 255))
    s.disc(16, 16, 3, (160, 130, 50, 255))
    s.outline(5, 5, 22, 22, (0, 0, 0, 0))               # mantém transparência


def _potion(s, liquid):
    s.rect(13, 6, 6, 4, (150, 150, 158, 255))           # gargalo
    s.rect(12, 4, 8, 2, (110, 76, 40, 255))             # rolha
    s.disc(16, 19, 8, (190, 200, 210, 255))             # vidro
    s.disc(16, 20, 6, liquid)                           # líquido


def d_potion_red(s):
    _potion(s, (200, 40, 50, 255))


def d_potion_blue(s):
    _potion(s, (50, 80, 210, 255))


def d_cheese(s):
    c = (230, 196, 80, 255)
    # fatia triangular
    for y in range(10, 26):
        w = (y - 10) * 1.4
        s.rect(int(16 - w / 2), y, max(1, int(w)), 1, c)
    for (x, y) in ((14, 18), (18, 22), (15, 23)):       # furos
        s.disc(x, y, 1, shade(c, -60))


def d_meat(s):
    s.disc(15, 17, 8, (188, 80, 70, 255))
    s.disc(13, 15, 4, (214, 110, 96, 255))
    s.rect(21, 20, 7, 3, (224, 222, 210, 255))          # osso


def d_bread(s):
    c = (196, 150, 84, 255)
    s.disc(13, 18, 6, c)
    s.disc(19, 18, 6, c)
    s.rect(13, 12, 7, 12, c)
    s.rect(12, 14, 9, 1, shade(c, 30))


# ------------------------------------------------------ caverna / escadas

def d_cave_wall(s):
    s.noise((52, 46, 42), 8, 120)
    rng = _lcg(21)
    for _ in range(10):                                 # pedras salientes
        x, y = next(rng) % 28, next(rng) % 28
        s.rect(x, y, 4, 3, (70, 62, 56, 255))
        s.rect(x, y, 4, 1, (84, 76, 68, 255))


def d_stairs_down(s):
    s.noise((70, 64, 60), 9, 121)                       # chão de caverna
    # buraco com degraus descendo
    for i, shade_v in enumerate((120, 90, 60, 30, 8)):
        m = 4 + i * 3
        s.rect(m, m, TILE - 2 * m, TILE - 2 * m, (shade_v, shade_v - 6, shade_v - 10, 255))


def d_stairs_up(s):
    s.noise((70, 64, 60), 9, 122)
    wood = (134, 96, 52, 255)
    s.rect(10, 2, 3, 28, wood)                          # escada de mão
    s.rect(19, 2, 3, 28, wood)
    for y in range(4, 30, 5):
        s.rect(10, y, 12, 2, shade(wood, 20))


# ------------------------------------------------- criaturas do subsolo

def d_bat(s):
    body = (74, 70, 80, 255)
    s.disc(16, 16, 4, body)                             # corpo
    for sx in (-1, 1):                                  # asas
        for i in range(7):
            x = 16 + sx * (5 + i)
            h = 6 - abs(i - 3)
            s.rect(x, 13 - h // 2, 1, h + 3, shade(body, -10))
    s.px(14, 14, (220, 60, 60, 255))                    # olhos vermelhos
    s.px(18, 14, (220, 60, 60, 255))
    s.px(13, 11, body)                                  # orelhas
    s.px(19, 11, body)


def d_spider(s):
    body = (38, 34, 32, 255)
    s.disc(16, 19, 6, body)                             # abdômen
    s.disc(16, 11, 4, shade(body, 15))                  # cabeça
    for sx in (-1, 1):                                  # 8 pernas
        for i, ly in enumerate((12, 15, 18, 21)):
            x0 = 16 + sx * 5
            for j in range(6):
                s.px(x0 + sx * j, ly - (j // 2) + i % 2, body)
    s.px(14, 10, (200, 60, 60, 255))
    s.px(18, 10, (200, 60, 60, 255))


def d_ghoul(s, facing="s", step=0):
    humanoid(s, (104, 116, 92, 255), (84, 92, 74, 255), (60, 68, 52, 255),
             skin=(168, 180, 144, 255), facing=facing, step=step)
    if facing != "n":
        s.rect(9, 18, 14, 1, (60, 50, 40, 255))         # trapos rasgados
        s.rect(11, 21, 3, 3, (60, 50, 40, 255))
    if facing == "s":
        s.px(13, 9, (150, 30, 30, 255))                 # olhos fundos
        s.px(18, 9, (150, 30, 30, 255))


def d_dragon(s):
    green = (60, 130, 50, 255)
    s.disc(15, 19, 9, green)                            # corpo
    s.disc(23, 11, 5, shade(green, 12))                 # cabeça
    s.rect(26, 9, 5, 3, shade(green, 12))               # focinho
    s.px(24, 9, (240, 200, 60, 255))                    # olho
    s.rect(27, 12, 3, 1, (230, 120, 40, 255))           # fogo saindo
    for i in range(7):                                  # asa
        s.rect(6 + i, 8 + i, 2, 8 - i, shade(green, -25))
    for i in range(6):                                  # cauda
        s.px(6 - i // 2, 24 + i // 2, green)
    s.rect(10, 26, 3, 4, shade(green, -20))             # patas
    s.rect(18, 26, 3, 4, shade(green, -20))
    s.rect(12, 14, 6, 4, (210, 190, 120, 255))          # barriga clara


def _dragon_body(s, body, belly, fire):
    """Corpo de dragão parametrizado por cor (dragão verde / lorde vermelho)."""
    s.disc(15, 19, 9, body)                             # corpo
    s.disc(23, 11, 5, shade(body, 12))                  # cabeça
    s.rect(26, 9, 5, 3, shade(body, 12))                # focinho
    s.px(24, 9, (240, 200, 60, 255))                    # olho
    s.rect(27, 12, 4, 1, fire)                          # fogo saindo
    s.px(30, 11, fire)
    for i in range(7):                                  # asa
        s.rect(6 + i, 8 + i, 2, 8 - i, shade(body, -25))
    for i in range(6):                                  # cauda
        s.px(6 - i // 2, 24 + i // 2, body)
    s.rect(10, 26, 3, 4, shade(body, -20))              # patas
    s.rect(18, 26, 3, 4, shade(body, -20))
    s.rect(12, 14, 6, 4, belly)                         # barriga clara


def d_dragon_lord(s):
    _dragon_body(s, (180, 56, 36, 255), (230, 180, 110, 255),
                 (255, 160, 30, 255))
    s.rect(13, 6, 2, 3, (240, 200, 60, 255))            # chifres dourados
    s.rect(20, 4, 2, 4, (240, 200, 60, 255))


# ------------------------------------------------------ itens avançados

def d_fire_sword(s):
    blade = (235, 120, 40, 255)
    for i in range(14):                                 # lâmina flamejante
        s.rect(8 + i, 22 - i, 2, 2, blade)
        if i % 3 == 0:
            s.px(9 + i, 19 - i, (255, 200, 60, 255))    # chamas
    s.rect(20, 8, 3, 3, (255, 220, 80, 255))
    s.rect(8, 20, 6, 2, (124, 88, 48, 255))
    s.rect(5, 24, 4, 4, (94, 64, 32, 255))
    s.disc(5, 27, 2, (212, 60, 40, 255))

def d_broad_sword(s):
    blade = (190, 196, 206, 255)
    for i in range(15):
        s.rect(7 + i, 23 - i, 3, 3, blade)              # lâmina larga
    s.rect(22, 7, 3, 3, shade(blade, 40))
    s.rect(7, 21, 7, 2, (124, 88, 48, 255))
    s.rect(4, 25, 4, 4, (94, 64, 32, 255))


def d_battle_axe(s):
    s.rect(14, 4, 3, 24, (110, 78, 42, 255))            # cabo longo
    for sx in (8, 18):                                  # lâmina dupla
        s.rect(sx, 5, 6, 8, (168, 172, 182, 255))
        s.rect(sx, 6, 2, 6, (198, 202, 212, 255))


def d_dragon_shield(s):
    s.disc(16, 16, 11, (160, 50, 40, 255))              # fundo vermelho
    s.disc(16, 16, 8, (190, 70, 50, 255))
    s.disc(16, 15, 4, (60, 130, 50, 255))               # emblema verde
    s.disc(16, 16, 2, (240, 200, 60, 255))


# ------------------------------------------- distância / ferramentas / etc

def d_bow(s):
    wood = (124, 88, 48, 255)
    for i in range(20):                                 # arco curvo
        x = 10 + int(6 * math.sin(math.pi * i / 19))
        s.rect(x, 6 + i, 2, 2, wood)
    for i in range(20):                                 # corda
        s.px(20, 6 + i, (220, 214, 200, 255))


def d_arrow(s):
    for i in range(14):                                 # haste diagonal
        s.px(9 + i, 22 - i, (134, 96, 52, 255))
        s.px(10 + i, 22 - i, (114, 80, 42, 255))
    s.rect(22, 7, 3, 3, (190, 196, 206, 255))           # ponta
    for j in range(4):                                  # penas
        s.px(8 + j, 24 - j, (200, 60, 60, 255))
        s.px(7 + j, 23 - j, (200, 60, 60, 255))


def d_spear(s):
    for i in range(20):                                 # haste longa
        s.px(6 + i, 25 - i, (134, 96, 52, 255))
        s.px(7 + i, 25 - i, (114, 80, 42, 255))
    s.rect(24, 4, 4, 4, (190, 196, 206, 255))           # ponta de metal
    s.px(23, 8, (210, 216, 226, 255))


def d_fishing_rod(s):
    for i in range(18):                                 # vara
        s.px(7 + i, 24 - i, (150, 110, 60, 255))
    for j in range(10):                                 # linha
        s.px(25, 7 + j, (220, 214, 200, 255))
    s.px(24, 17, (190, 196, 206, 255))                  # anzol
    s.px(23, 16, (190, 196, 206, 255))


def d_fish(s):
    body = (120, 150, 190, 255)
    s.disc(15, 16, 6, body)                             # corpo
    s.disc(13, 14, 2, shade(body, 25))                  # brilho
    s.rect(21, 13, 4, 7, shade(body, -20))              # cauda
    s.px(24, 12, shade(body, -20))
    s.px(24, 20, shade(body, -20))
    s.px(11, 15, BLACK)                                 # olho


def d_ring(s):
    gold = (228, 190, 52, 255)
    s.disc(16, 18, 6, gold)
    s.disc(16, 18, 3, (0, 0, 0, 0))                     # furo
    for yy in range(15, 22):                            # furo transparente
        for xx in range(13, 20):
            if (xx - 16) ** 2 + (yy - 18) ** 2 <= 9:
                s.px(xx, yy, (0, 0, 0, 0))
    s.rect(14, 10, 4, 4, (90, 160, 220, 255))           # pedra azul
    s.px(15, 11, (160, 210, 250, 255))


def d_amulet(s):
    chain = (200, 200, 210, 255)
    for i in range(8):                                  # corrente
        s.px(10 + i, 8 + (i % 2), chain)
        s.px(22 - i, 8 + (i % 2), chain)
    s.disc(16, 18, 5, (60, 90, 160, 255))               # pingente
    s.disc(15, 17, 2, (120, 160, 220, 255))
    s.outline(12, 14, 9, 9, (212, 176, 60, 255))


def _backpack_shape(s, c):
    s.rect(8, 10, 16, 16, c)                            # corpo
    s.rect(8, 10, 16, 4, shade(c, 22))                  # aba
    s.rect(14, 16, 4, 5, shade(c, -25))                 # fivela
    s.rect(6, 12, 2, 10, shade(c, -15))                 # alças
    s.rect(24, 12, 2, 10, shade(c, -15))
    s.outline(8, 10, 16, 16, shade(c, -50))


def d_backpack(s):
    _backpack_shape(s, (146, 104, 58, 255))


def d_backpack_big(s):
    _backpack_shape(s, (140, 60, 50, 255))
    s.rect(10, 24, 12, 3, (110, 45, 38, 255))           # bolso extra


def d_rope(s):
    c = (196, 160, 96, 255)
    s.disc(16, 16, 8, c)
    s.disc(16, 16, 5, shade(c, -30))
    s.disc(16, 16, 3, c)
    s.rect(20, 20, 7, 2, c)                             # ponta solta
    s.rect(25, 18, 2, 4, shade(c, -20))


def d_hole(s):
    # buraco aberto no chão (cai ao pisar)
    s.disc(16, 17, 11, (18, 14, 12, 255))
    s.disc(16, 16, 9, (8, 6, 5, 255))
    for x in range(6, 27, 3):                           # borda irregular
        s.px(x, 9 + (x % 3), (60, 50, 42, 255))


def d_rope_spot(s):
    # abertura no teto vista de baixo (use a corda aqui para subir)
    s.disc(16, 16, 10, (30, 26, 22, 255))
    s.disc(16, 14, 7, (74, 66, 56, 255))                # luz vinda de cima
    s.disc(16, 13, 4, (120, 110, 92, 255))
    for j in range(8):                                  # corda pendurada
        s.px(16, 10 + j, (196, 160, 96, 255))


# --------------------------------------------------------------- montagem

# A ordem define o índice de cada sprite na sheet (não remova, só acrescente!)
SPRITES = [
    ("grass", d_grass), ("dirt", d_dirt), ("stone", d_stone), ("water", d_water),
    ("sand", d_sand), ("marble", d_marble), ("wood", d_wood), ("cave", d_cave),
    ("tree", d_tree), ("wall", d_wall), ("rock", d_rock), ("bush", d_bush),
    ("fence", d_fence), ("altar", d_altar), ("gravestone", d_gravestone),
    ("player", d_player), ("npc_priest", d_npc_priest),
    ("npc_merchant", d_npc_merchant), ("npc_guard", d_npc_guard),
    ("rat", d_rat), ("snake", d_snake), ("wolf", d_wolf), ("troll", d_troll),
    ("orc", d_orc), ("skeleton", d_skeleton), ("corpse", d_corpse),
    ("gold", d_gold), ("sword", d_sword), ("club", d_club), ("axe", d_axe),
    ("dagger", d_dagger), ("leather_helmet", d_leather_helmet),
    ("leather_armor", d_leather_armor), ("leather_legs", d_leather_legs),
    ("leather_boots", d_leather_boots), ("chain_armor", d_chain_armor),
    ("plate_armor", d_plate_armor), ("wooden_shield", d_wooden_shield),
    ("brass_shield", d_brass_shield), ("potion_red", d_potion_red),
    ("potion_blue", d_potion_blue), ("cheese", d_cheese), ("meat", d_meat),
    ("bread", d_bread),
    # subsolo (não reordene os anteriores — os índices precisam ser estáveis)
    ("cave_wall", d_cave_wall), ("stairs_down", d_stairs_down),
    ("stairs_up", d_stairs_up), ("bat", d_bat), ("spider", d_spider),
    ("ghoul", d_ghoul), ("dragon", d_dragon),
    ("broad_sword", d_broad_sword), ("battle_axe", d_battle_axe),
    ("dragon_shield", d_dragon_shield),
    ("dragon_lord", d_dragon_lord), ("fire_sword", d_fire_sword),
    ("bow", d_bow), ("arrow", d_arrow), ("spear", d_spear),
    ("fishing_rod", d_fishing_rod), ("fish", d_fish), ("ring", d_ring),
    ("amulet", d_amulet), ("backpack", d_backpack),
    ("backpack_big", d_backpack_big), ("rope", d_rope),
    ("hole", d_hole), ("rope_spot", d_rope_spot),
]


# tiles que se repetem lado a lado: NÃO podem ter contorno (criaria grade)
TILING = {
    "grass", "dirt", "stone", "water", "sand", "marble", "wood", "cave",
    "cave_wall", "wall", "fence",
    "stairs_down", "stairs_up", "hole", "rope_spot",
}
# figuras que ficam "em pé" no mundo e ganham sombra no chão
SHADOWED = {
    "player", "npc_priest", "npc_merchant", "npc_guard",
    "rat", "snake", "wolf", "troll", "orc", "skeleton",
    "bat", "spider", "ghoul", "dragon", "dragon_lord",
    "tree", "rock", "bush", "gravestone", "altar",
}

# humanoides direcionais: ganham frames _n (costas) e _e (perfil); o cliente
# usa o frame base como FRENTE (sul) e espelha _e para o oeste.
DIRECTIONAL = {
    "player": d_player, "npc_priest": d_npc_priest,
    "npc_merchant": d_npc_merchant, "npc_guard": d_npc_guard,
    "troll": d_troll, "orc": d_orc, "ghoul": d_ghoul,
}


def _finish(name, spr):
    """Pós-processo estilo RotMG: sombra no chão + contorno escuro."""
    if name in SHADOWED:
        spr.add_shadow()
    if name not in TILING:
        spr.add_outline()


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # 1) frames base (mantêm os índices estáveis), depois variantes direcionais
    frames = []                                # [(name, Sprite)]
    for name, draw in SPRITES:
        spr = Sprite()
        draw(spr)
        _finish(name, spr)
        frames.append((name, spr))
    # por direção: frame PARADO + 1 frame ANDANDO (_a). O cliente alterna
    # parado<->andando enquanto a criatura se move (2 frames por direção).
    # frente parado = frame base; frente andando = base_a.
    variants = [
        ("_a", "s", 1),
        ("_n", "n", 0), ("_n_a", "n", 1),
        ("_e", "e", 0), ("_e_a", "e", 1),
    ]
    for base, draw in DIRECTIONAL.items():
        for suffix, facing, step in variants:
            spr = Sprite()
            draw(spr, facing, step)
            _finish(base, spr)
            frames.append((base + suffix, spr))

    # 2) empacota tudo na spritesheet
    n = len(frames)
    rows = math.ceil(n / COLS)
    sheet_w, sheet_h = COLS * TILE, rows * TILE
    sheet = bytearray(sheet_w * sheet_h * 4)
    index = {}
    for i, (name, spr) in enumerate(frames):
        index[name] = i
        cx, cy = (i % COLS) * TILE, (i // COLS) * TILE
        for y in range(TILE):
            src = y * TILE * 4
            dst = ((cy + y) * sheet_w + cx) * 4
            sheet[dst : dst + TILE * 4] = spr.buf[src : src + TILE * 4]

    write_png(os.path.join(OUT_DIR, "sprites.png"), sheet_w, sheet_h, sheet)
    with open(os.path.join(OUT_DIR, "sprites.json"), "w", encoding="utf-8") as f:
        json.dump({"tile": TILE, "cols": COLS, "index": index}, f, indent=1)
    print(f"OK: {n} sprites -> {OUT_DIR}\\sprites.png ({sheet_w}x{sheet_h})")


if __name__ == "__main__":
    main()
