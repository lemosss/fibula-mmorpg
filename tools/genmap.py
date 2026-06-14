"""
genmap.py — Gera o mapa inicial do jogo (data/map.json).

Uso:  python tools/genmap.py

Mundo com DOIS ANDARES (z-levels):

z=0 (superfície, 100x100):
  - Cidade murada a oeste (zona de proteção): templo de mármore com altar,
    loja do mercador, casas, ruas de pedra e dois portões.
  - Lago a oeste da cidade.
  - Área de caça a leste: ratos/cobras perto do portão, lobos na floresta,
    trolls nas colinas, orcs distantes e um cemitério com esqueletos.
  - Duas entradas de caverna (escadas p/ baixo): colinas dos trolls e cemitério.

z=1 (subsolo):
  - Túneis escavados ligando: câmara dos morcegos, antro das aranhas,
    a cripta dos carniçais (sob o cemitério) e, no fundo, o covil do DRAGÃO.

Os andares são conectados por portais (escadas) declarados em meta.portals.
Determinístico: rodar de novo produz sempre o mesmo mapa (seed fixa).
"""
import json
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "map.json")

W, H = 100, 100

# --- IDs de chão -------------------------------------------------------------
G_VOID, G_GRASS, G_DIRT, G_STONE, G_WATER, G_SAND, G_MARBLE, G_WOOD, G_CAVE = range(9)

# --- IDs de objeto -----------------------------------------------------------
(O_NONE, O_TREE, O_WALL, O_ROCK, O_BUSH, O_FENCE, O_ALTAR, O_GRAVE,
 O_CAVEWALL, O_STAIRS_DOWN, O_STAIRS_UP, O_HOLE, O_ROPESPOT) = range(13)

# Metadados enviados ao cliente e usados pelo servidor (sprite + andável)
GROUND_META = {
    G_VOID:   {"sprite": None,     "walk": False},
    G_GRASS:  {"sprite": "grass",  "walk": True},
    G_DIRT:   {"sprite": "dirt",   "walk": True},
    G_STONE:  {"sprite": "stone",  "walk": True},
    G_WATER:  {"sprite": "water",  "walk": False},
    G_SAND:   {"sprite": "sand",   "walk": True},
    G_MARBLE: {"sprite": "marble", "walk": True},
    G_WOOD:   {"sprite": "wood",   "walk": True},
    G_CAVE:   {"sprite": "cave",   "walk": True},
}
OBJECT_META = {
    O_TREE:        {"sprite": "tree",        "walk": False},
    O_WALL:        {"sprite": "wall",        "walk": False},
    O_ROCK:        {"sprite": "rock",        "walk": False},
    O_BUSH:        {"sprite": "bush",        "walk": False},
    O_FENCE:       {"sprite": "fence",       "walk": False},
    O_ALTAR:       {"sprite": "altar",       "walk": False},
    O_GRAVE:       {"sprite": "gravestone",  "walk": False},
    O_CAVEWALL:    {"sprite": "cave_wall",   "walk": False},
    O_STAIRS_DOWN: {"sprite": "stairs_down", "walk": True},   # clica para descer
    O_STAIRS_UP:   {"sprite": "stairs_up",   "walk": True},
    O_HOLE:        {"sprite": "hole",        "walk": True},   # pisa e CAI
    O_ROPESPOT:    {"sprite": "rope_spot",   "walk": True},   # use corda p/ subir
}

# superfície (z=0)
ground = [[G_GRASS] * W for _ in range(H)]
objects = [[O_NONE] * W for _ in range(H)]

# subsolo (z=1): tudo rocha maciça; os túneis são escavados depois
ground1 = [[G_VOID] * W for _ in range(H)]
objects1 = [[O_NONE] * W for _ in range(H)]

# entradas das cavernas (escada na superfície; chega-se 1 tile ao sul no subsolo)
CAVE_A = (66, 26)   # colinas dos trolls
CAVE_B = (84, 12)   # cemitério (desce para a cripta)


def fill_ground(x0, y0, x1, y1, g):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            ground[y][x] = g


def fill_obj(x0, y0, x1, y1, o):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            objects[y][x] = o


def carve_disc(cx, cy, r):
    """Escava uma câmara circular no subsolo."""
    for y in range(cy - r, cy + r + 1):
        for x in range(cx - r, cx + r + 1):
            if 1 <= x < W - 1 and 1 <= y < H - 1 and \
                    (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                ground1[y][x] = G_CAVE


def carve_corridor(x1, y1, x2, y2):
    """Escava um corredor em L (2 tiles de largura) entre dois pontos."""
    for x in range(min(x1, x2), max(x1, x2) + 1):
        for w in (0, 1):
            if 1 <= y1 + w < H - 1:
                ground1[y1 + w][x] = G_CAVE
    for y in range(min(y1, y2), max(y1, y2) + 1):
        for w in (0, 1):
            if 1 <= x2 + w < W - 1:
                ground1[y][x2 + w] = G_CAVE


def building(x0, y0, x1, y1, floor, doors):
    """Constrói um prédio: piso interno, paredes no perímetro e portas (gaps)."""
    fill_ground(x0, y0, x1, y1, floor)
    for x in range(x0, x1 + 1):
        objects[y0][x] = O_WALL
        objects[y1][x] = O_WALL
    for y in range(y0, y1 + 1):
        objects[y][x0] = O_WALL
        objects[y][x1] = O_WALL
    for (dx, dy) in doors:
        objects[dy][dx] = O_NONE


def main():
    rng = random.Random(772)  # seed fixa -> mapa determinístico

    # ---- moldura de água (borda do mundo) -----------------------------------
    fill_ground(0, 0, W - 1, 1, G_WATER)
    fill_ground(0, H - 2, W - 1, H - 1, G_WATER)
    fill_ground(0, 0, 1, H - 1, G_WATER)
    fill_ground(W - 2, 0, W - 1, H - 1, G_WATER)

    # ---- lago a oeste + praia ------------------------------------------------
    fill_ground(0, 25, 13, 75, G_WATER)
    fill_ground(14, 25, 15, 75, G_SAND)

    # ---- floresta esparsa no mapa todo (limpa-se depois onde necessário) ----
    for y in range(2, H - 2):
        for x in range(2, W - 2):
            if ground[y][x] != G_GRASS:
                continue
            r = rng.random()
            if r < 0.07:
                objects[y][x] = O_TREE
            elif r < 0.085:
                objects[y][x] = O_BUSH
            elif r < 0.09:
                objects[y][x] = O_ROCK

    # ---- cidade (x 18..48, y 34..66) ----------------------------------------
    CITY = (18, 34, 48, 66)
    fill_ground(*CITY, G_GRASS)
    fill_obj(*CITY, O_NONE)  # limpa a vegetação dentro da cidade

    # muralha com dois portões (leste, na rua principal; sul)
    for x in range(CITY[0], CITY[2] + 1):
        objects[CITY[1]][x] = O_WALL
        objects[CITY[3]][x] = O_WALL
    for y in range(CITY[1], CITY[3] + 1):
        objects[y][CITY[0]] = O_WALL
        objects[y][CITY[2]] = O_WALL
    for y in (49, 50, 51):
        objects[y][CITY[2]] = O_NONE          # portão leste
    for x in (32, 33, 34):
        objects[CITY[3]][x] = O_NONE          # portão sul

    # ruas de pedra: principal (leste-oeste) e transversal (norte-sul)
    fill_ground(19, 49, 48, 51, G_STONE)
    fill_ground(32, 35, 34, 65, G_STONE)

    # estrada de terra saindo do portão leste até a área de caça
    fill_ground(49, 49, 92, 51, G_DIRT)
    fill_obj(49, 48, 92, 52, O_NONE)          # margem da estrada sempre limpa

    # caminho do portão sul
    fill_ground(32, 66, 34, 70, G_DIRT)
    fill_obj(31, 66, 35, 71, O_NONE)

    # ---- templo (noroeste da cidade) ----------------------------------------
    building(20, 36, 31, 45, G_MARBLE, doors=[(25, 45), (26, 45)])
    objects[37][25] = O_ALTAR
    objects[37][26] = O_ALTAR
    fill_ground(25, 46, 26, 48, G_STONE)      # calçada do templo até a rua

    # ---- loja do mercador (nordeste da rua transversal) ----------------------
    building(38, 38, 46, 44, G_WOOD, doors=[(38, 41)])
    fill_ground(35, 41, 37, 41, G_STONE)      # calçada da loja

    # ---- casas decorativas ----------------------------------------------------
    building(20, 54, 28, 62, G_WOOD, doors=[(28, 58)])
    building(38, 56, 46, 62, G_WOOD, doors=[(41, 56), (42, 56)])

    # pracinha com cerca perto do portão sul
    fill_obj(38, 47, 38, 47, O_NONE)

    # ---- cemitério a nordeste (esqueletos) -----------------------------------
    fill_ground(78, 8, 92, 20, G_DIRT)
    fill_obj(78, 8, 92, 20, O_NONE)
    for _ in range(14):
        gx = rng.randint(79, 91)
        gy = rng.randint(9, 19)
        # não cobre o centro do spawn nem a entrada da cripta
        if (gx, gy) != (85, 14) and abs(gx - CAVE_B[0]) + abs(gy - CAVE_B[1]) > 2:
            objects[gy][gx] = O_GRAVE

    # ================== SUBSOLO (z=1): cavernas e cripta =====================
    # câmaras
    carve_disc(60, 20, 5)     # câmara dos morcegos
    carve_disc(75, 35, 6)     # antro das aranhas
    carve_disc(84, 16, 6)     # cripta dos carniçais (sob o cemitério)
    carve_disc(50, 60, 7)     # covil do dragão
    carve_disc(30, 72, 6)     # trono do LORDE DRAGÃO (o mais fundo)
    # chegadas das escadas
    carve_disc(CAVE_A[0], CAVE_A[1] + 1, 2)
    carve_disc(CAVE_B[0], CAVE_B[1] + 1, 2)
    # túneis
    carve_corridor(CAVE_A[0], CAVE_A[1], 60, 20)        # entrada A -> morcegos
    carve_corridor(60, 20, 75, 35)                      # morcegos -> aranhas
    carve_corridor(75, 35, 84, 16)                      # aranhas -> cripta
    carve_corridor(75, 35, 50, 60)                      # aranhas -> dragão
    carve_corridor(50, 60, 30, 72)                      # dragão -> lorde dragão
    # buraco na floresta dos lobos: cai numa galeria com rope spot
    HOLE = (75, 48)
    carve_disc(HOLE[0], HOLE[1], 3)
    carve_corridor(75, 35, HOLE[0], HOLE[1])            # galeria -> aranhas

    # paredes de caverna: anel visual de rocha ao redor do que foi escavado
    for y in range(H):
        for x in range(W):
            if ground1[y][x] != G_VOID:
                continue
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= nx < W and 0 <= ny < H and ground1[ny][nx] == G_CAVE:
                        objects1[y][x] = O_CAVEWALL
                        break
                if objects1[y][x]:
                    break

    # escadas (objetos andáveis) nos dois andares
    objects[CAVE_A[1]][CAVE_A[0]] = O_STAIRS_DOWN
    objects[CAVE_B[1]][CAVE_B[0]] = O_STAIRS_DOWN
    ground[CAVE_A[1]][CAVE_A[0]] = G_DIRT
    ground[CAVE_B[1]][CAVE_B[0]] = G_DIRT
    ground1[CAVE_A[1]][CAVE_A[0]] = G_CAVE
    ground1[CAVE_B[1]][CAVE_B[0]] = G_CAVE
    objects1[CAVE_A[1]][CAVE_A[0]] = O_STAIRS_UP
    objects1[CAVE_B[1]][CAVE_B[0]] = O_STAIRS_UP

    # portais: pisar na escada leva ao outro andar (1 tile ao sul da escada-par)
    portals = []
    for (sx, sy) in (CAVE_A, CAVE_B):
        portals.append({"from": [sx, sy, 0], "to": [sx, sy + 1, 1]})
        portals.append({"from": [sx, sy, 1], "to": [sx, sy + 1, 0]})

    # BURACO e ROPE SPOT são PROPRIEDADES DO TILE (não objetos que sobrepõem):
    # o sprite vai na lista `decos` (desenhada SOB os itens) e o comportamento
    # (descer / usar corda) vive em holes/ropes — independente do sprite.
    fill_obj(HOLE[0] - 1, HOLE[1] - 1, HOLE[0] + 1, HOLE[1] + 1, O_NONE)
    # saída da corda: tile ao sul do buraco, na superfície (sempre limpo)
    objects[HOLE[1] + 1][HOLE[0]] = O_NONE
    holes = [{"from": [HOLE[0], HOLE[1], 0], "to": [HOLE[0], HOLE[1], 1]}]
    ropes = [{"from": [HOLE[0], HOLE[1], 1], "to": [HOLE[0], HOLE[1] + 1, 0]}]
    # decoração visual dos tiles especiais (sprite apenas; sem colisão/overlap)
    decos = [
        {"x": HOLE[0], "y": HOLE[1], "z": 0, "sprite": "hole"},
        {"x": HOLE[0], "y": HOLE[1], "z": 1, "sprite": "rope_spot"},
    ]

    # ---- clareiras dos spawns (remove vegetação ao redor) --------------------
    # "respawn" em segundos — inclui o aviso de 5s (bolinha azul) antes de nascer
    spawns = [
        # área de ratos: logo após o portão leste (iniciantes)
        {"monster": "rat",      "x": 56, "y": 50, "radius": 4, "count": 4, "respawn": 45},
        {"monster": "rat",      "x": 60, "y": 57, "radius": 4, "count": 3, "respawn": 45},
        # cobras no campo ao sudeste
        {"monster": "snake",    "x": 62, "y": 70, "radius": 5, "count": 3, "respawn": 60},
        {"monster": "snake",    "x": 70, "y": 78, "radius": 5, "count": 3, "respawn": 60},
        # lobos na floresta a leste
        {"monster": "wolf",     "x": 72, "y": 42, "radius": 5, "count": 3, "respawn": 90},
        {"monster": "wolf",     "x": 78, "y": 55, "radius": 5, "count": 3, "respawn": 90},
        # trolls nas colinas ao norte
        {"monster": "troll",    "x": 64, "y": 28, "radius": 5, "count": 3, "respawn": 120},
        {"monster": "troll",    "x": 72, "y": 20, "radius": 6, "count": 3, "respawn": 120},
        # orcs no extremo leste
        {"monster": "orc",      "x": 86, "y": 48, "radius": 5, "count": 4, "respawn": 150},
        {"monster": "orc",      "x": 88, "y": 60, "radius": 5, "count": 3, "respawn": 150},
        # esqueletos no cemitério
        {"monster": "skeleton", "x": 85, "y": 14, "radius": 5, "count": 4, "respawn": 180},
        # ---- subsolo (z=1) ----
        {"monster": "bat",         "x": 60, "y": 20, "radius": 4, "count": 5, "respawn": 60,  "z": 1},
        {"monster": "spider",      "x": 75, "y": 35, "radius": 5, "count": 4, "respawn": 120, "z": 1},
        {"monster": "ghoul",       "x": 84, "y": 16, "radius": 4, "count": 4, "respawn": 180, "z": 1},
        {"monster": "dragon",      "x": 50, "y": 60, "radius": 3, "count": 1, "respawn": 600, "z": 1},
        {"monster": "dragon_lord", "x": 30, "y": 72, "radius": 3, "count": 1, "respawn": 900, "z": 1},
    ]
    for s in spawns:
        s.setdefault("z", 0)
        if s["z"] != 0:
            continue                       # subsolo já nasce escavado/limpo
        r = s["radius"] + 1
        for y in range(max(2, s["y"] - r), min(H - 2, s["y"] + r + 1)):
            for x in range(max(2, s["x"] - r), min(W - 2, s["x"] + r + 1)):
                if objects[y][x] in (O_TREE, O_BUSH, O_ROCK):
                    objects[y][x] = O_NONE
    # garante a escada da superfície livre (a limpeza acima pode não cobrir)
    objects[CAVE_A[1]][CAVE_A[0]] = O_STAIRS_DOWN
    objects[CAVE_B[1]][CAVE_B[0]] = O_STAIRS_DOWN

    # ---- sanidade ------------------------------------------------------------
    assert GROUND_META[ground[42][25]]["walk"], "templo não é andável!"
    for p in portals:
        fx_, fy_, fz_ = p["from"]
        tx_, ty_, tz_ = p["to"]
        g = ground if fz_ == 0 else ground1
        t = ground if tz_ == 0 else ground1
        assert GROUND_META[g[fy_][fx_]]["walk"], f"portal origem bloqueado {p}"
        assert GROUND_META[t[ty_][tx_]]["walk"], f"portal destino bloqueado {p}"

    data = {
        "width": W,
        "height": H,
        # andares: índice da lista = coordenada z
        "floors": [
            {"ground": ground, "objects": objects},
            {"ground": ground1, "objects": objects1},
        ],
        "groundMeta": {str(k): v for k, v in GROUND_META.items()},
        "objectMeta": {str(k): v for k, v in OBJECT_META.items()},
        "meta": {
            # ponto de renascimento (dentro do templo, z=0)
            "temple": [25, 42],
            # zona de proteção (só z=0): monstros não entram nem atacam (x0,y0,x1,y1)
            "pz": list(CITY),
            # escadas entre andares
            "portals": portals,
            # buracos (queda automática) e rope spots (corda para subir)
            "holes": holes,
            "ropes": ropes,
            # sprites de tiles especiais (buraco/rope) — desenhados SOB os itens
            "decos": decos,
        },
        "spawns": spawns,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"OK: mapa {W}x{H} x2 andares, {len(spawns)} zonas de spawn, "
          f"{len(portals)} portais -> {OUT}")


if __name__ == "__main__":
    main()
