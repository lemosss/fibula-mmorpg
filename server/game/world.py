"""
world.py — O mapa estático (multi-andar) e os itens no chão.

O mundo tem N andares (z-levels): z=0 é a superfície, z=1 o subsolo.
Andares são ligados por portais (escadas): pisar no tile de origem
teleporta para o destino — a lógica de disparo fica no Game.

A ocupação por criaturas (quem está em qual tile) fica no Game (by_pos);
aqui mora só o que é terreno: andabilidade, zona de proteção, portais e
pilhas de itens dropados.
"""
import heapq
import random
from collections import deque

import config
from game import data


class World:
    def __init__(self):
        m = data.MAP
        self.w = m["width"]
        self.h = m["height"]
        self.floors = m["floors"]            # [{"ground":[][], "objects":[][]}]
        self.depth = len(self.floors)
        self.temple = tuple(m["meta"]["temple"])  # (x, y) em z=0
        self.pz = m["meta"]["pz"]            # [x0, y0, x1, y1] (só z=0)
        self.spawns = m["spawns"]

        # portais (escadas): (x, y, z) -> (x, y, z)
        self.portals = {tuple(p["from"]): tuple(p["to"])
                        for p in m["meta"].get("portals", [])}
        # buracos: cair ao pisar (jogadores); rope spots: subir usando corda
        self.holes = {tuple(h["from"]): tuple(h["to"])
                      for h in m["meta"].get("holes", [])}
        self.ropes = {tuple(r["from"]): tuple(r["to"])
                      for r in m["meta"].get("ropes", [])}
        # tiles proibidos para monstros (escadas, buracos, rope spots)
        self.no_monster = (set(self.portals) | set(self.holes)
                           | set(self.ropes))

        # pré-computa a grade de andabilidade por andar
        gwalk = {int(k): v["walk"] for k, v in m["groundMeta"].items()}
        owalk = {int(k): v["walk"] for k, v in m["objectMeta"].items()}
        self.walk_grids = []
        for f in self.floors:
            g, o = f["ground"], f["objects"]
            self.walk_grids.append([
                [
                    gwalk.get(g[y][x], False)
                    and (o[y][x] == 0 or owalk.get(o[y][x], False))
                    for x in range(self.w)
                ]
                for y in range(self.h)
            ])

        # itens no chão: (x, y, z) -> [{"id", "count", "decay"(ms monotonic)}]
        self.ground_items = {}

        # payload do mapa enviado a cada cliente no login (sem os spawns)
        self.client_map = {
            "width": self.w, "height": self.h, "floors": self.floors,
            "groundMeta": m["groundMeta"], "objectMeta": m["objectMeta"],
            "meta": {"temple": list(self.temple), "pz": self.pz},
        }

    # ------------------------------------------------------------- terreno

    def walkable(self, x: int, y: int, z: int) -> bool:
        return (0 <= z < self.depth and 0 <= x < self.w and 0 <= y < self.h
                and self.walk_grids[z][y][x])

    def in_pz(self, x: int, y: int, z: int) -> bool:
        """Zona de proteção (a cidade, só na superfície)."""
        if z != 0:
            return False
        x0, y0, x1, y1 = self.pz
        return x0 <= x <= x1 and y0 <= y <= y1

    def ground_id(self, x: int, y: int, z: int) -> int:
        return self.floors[z]["ground"][y][x]

    def object_id(self, x: int, y: int, z: int) -> int:
        return self.floors[z]["objects"][y][x]

    def find_free_near(self, x: int, y: int, z: int, occupied, max_r: int = 4):
        """
        Procura o tile andável e desocupado mais próximo de (x,y) no andar z,
        em espiral. `occupied` é um callable (x,y,z)->bool. Retorna (x,y) ou None.
        """
        for r in range(max_r + 1):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if max(abs(dx), abs(dy)) != r:
                        continue
                    nx, ny = x + dx, y + dy
                    if self.walkable(nx, ny, z) and not occupied(nx, ny, z):
                        return nx, ny
        return None

    # vizinhança 8-direções (cardeais primeiro, diagonais depois)
    _NB8 = ((1, 0), (-1, 0), (0, 1), (0, -1),
            (1, 1), (1, -1), (-1, 1), (-1, -1))
    _NB4 = ((1, 0), (-1, 0), (0, 1), (0, -1))

    def find_path_smart(self, z: int, sx: int, sy: int, tx: int, ty: int,
                        **kw):
        """
        Pathfinding com PRIORIDADE ORTOGONAL (nunca prioriza diagonal):
          1) tenta uma rota usando SÓ cima/baixo/esquerda/direita;
          2) se existir, usa ela (mesmo que mais longa que uma diagonal);
          3) só quando NÃO há rota ortogonal nenhuma, libera diagonal como
             último recurso — e mesmo aí MINIMIZA o nº de diagonais
             (diagonal só pra sair do bloqueio; depois volta ao ortogonal).
        """
        kw.pop("allow_diag", None)
        kw.pop("diag_penalty", None)
        ortho = self.find_path(z, sx, sy, tx, ty, allow_diag=False, **kw)
        if ortho is not None:
            return ortho
        return self.find_path(z, sx, sy, tx, ty, allow_diag=True,
                              diag_penalty=True, **kw)

    def find_path(self, z: int, sx: int, sy: int, tx: int, ty: int,
                  max_len: int = 200, avoid_pz: bool = False,
                  avoid=None, max_nodes: int = 4000, allow_diag: bool = True,
                  diag_penalty: bool = False):
        """
        Busca de caminho num andar. Retorna [(x,y), ...] sem a origem, ou None.
        Se o destino não for andável, mira o tile andável adjacente.
        `avoid_pz`: monstros não atravessam zona de proteção/escadas/buracos.
        `avoid`: conjunto de (x,y) bloqueados (outras criaturas) — o caminho
        os CONTORNA, então dá a volta em grupos de monstros.
        `allow_diag`: permite passos diagonais (8-dir) além dos cardeais (4-dir).
        Diagonal não corta quina de PAREDE (exige os 2 ortogonais livres),
        mas pode passar diagonalmente entre criaturas — escapa de aglomerados.
        `diag_penalty`: usa custo (cardeal=1, diagonal=3) com Dijkstra, então o
        caminho usa o MÍNIMO de diagonais possível (prefere dar a volta a reto).
        """
        if (sx, sy) == (tx, ty):
            return []
        nb = self._NB8 if allow_diag else self._NB4
        if self.walkable(tx, ty, z):
            goals = {(tx, ty)}
        else:
            goals = {(tx + dx, ty + dy) for dx, dy in self._NB4
                     if self.walkable(tx + dx, ty + dy, z)}
        if not goals:
            return None
        if (sx, sy) in goals:
            return []
        avoid = avoid or ()

        def reachable(x, y, dx, dy):
            """Vizinho (x+dx,y+dy) é entrável a partir de (x,y)?"""
            nx, ny = x + dx, y + dy
            if not self.walkable(nx, ny, z):
                return False
            if dx and dy and not (self.walkable(x + dx, y, z)
                                  and self.walkable(x, y + dy, z)):
                return False                        # diagonal sem cortar parede
            if avoid_pz and (self.in_pz(nx, ny, z)
                             or (nx, ny, z) in self.no_monster):
                return False
            if (nx, ny) in avoid and (nx, ny) not in goals:
                return False
            return True

        def rebuild(prev, last):
            path = [last]
            while prev[path[-1]] != (sx, sy):
                path.append(prev[path[-1]])
            path.reverse()
            return path if len(path) <= max_len else None

        if not diag_penalty:                        # BFS uniforme (rápido)
            prev = {(sx, sy): None}
            queue = deque([(sx, sy)])
            while queue:
                if len(prev) > max_nodes:
                    return None
                x, y = queue.popleft()
                for dx, dy in nb:
                    n = (x + dx, y + dy)
                    if n in prev or not reachable(x, y, dx, dy):
                        continue
                    prev[n] = (x, y)
                    if n in goals:
                        return rebuild(prev, n)
                    queue.append(n)
            return None

        # Dijkstra com custo: cardeal=1, diagonal=3 (minimiza diagonais)
        prev = {(sx, sy): None}
        best = {(sx, sy): 0}
        pq = [(0, sx, sy)]
        while pq:
            if len(prev) > max_nodes:
                return None
            cost, x, y = heapq.heappop(pq)
            if cost > best.get((x, y), 1e9):
                continue
            if (x, y) in goals:
                return rebuild(prev, (x, y))
            for dx, dy in nb:
                if not reachable(x, y, dx, dy):
                    continue
                n = (x + dx, y + dy)
                nc = cost + (3 if dx and dy else 1)
                if nc < best.get(n, 1e9):
                    best[n] = nc
                    prev[n] = (x, y)
                    heapq.heappush(pq, (nc, n[0], n[1]))
        return None

    def random_spot_in_zone(self, zone: dict, occupied, tries: int = 24):
        """Tile aleatório válido dentro de uma zona de spawn (ou None)."""
        z = zone.get("z", 0)
        for _ in range(tries):
            x = zone["x"] + random.randint(-zone["radius"], zone["radius"])
            y = zone["y"] + random.randint(-zone["radius"], zone["radius"])
            if (self.walkable(x, y, z) and not self.in_pz(x, y, z)
                    and not occupied(x, y, z)
                    and (x, y, z) not in self.no_monster):
                return x, y
        return None

    # -------------------------------------------------------- itens no chão

    def ground_at(self, x: int, y: int, z: int) -> list:
        return self.ground_items.get((x, y, z), [])

    def ground_add(self, x: int, y: int, z: int, item_id: int, count: int,
                   decay_at: float):
        pile = self.ground_items.setdefault((x, y, z), [])
        idef = data.item(item_id)
        if idef.get("stackable"):
            for it in pile:
                if it["id"] == item_id:
                    it["count"] += count
                    it["decay"] = decay_at
                    return
        pile.append({"id": item_id, "count": count, "decay": decay_at})

    def ground_payload(self, x: int, y: int, z: int) -> dict:
        """Mensagem com o estado completo da pilha de um tile."""
        items = [{"id": i["id"], "count": i["count"]}
                 for i in self.ground_at(x, y, z)]
        return {"type": "ground", "x": x, "y": y, "z": z, "items": items}

    def ground_full_payload(self) -> dict:
        tiles = [
            {"x": x, "y": y, "z": z,
             "items": [{"id": i["id"], "count": i["count"]} for i in pile]}
            for (x, y, z), pile in self.ground_items.items() if pile
        ]
        return {"type": "ground_full", "tiles": tiles}

    def decay_tick(self, now: float):
        """Remove itens expirados. Retorna a lista de tiles alterados."""
        changed = []
        for pos in list(self.ground_items.keys()):
            pile = self.ground_items[pos]
            kept = [i for i in pile if i["decay"] > now]
            if len(kept) != len(pile):
                if kept:
                    self.ground_items[pos] = kept
                else:
                    del self.ground_items[pos]
                changed.append(pos)
        return changed
