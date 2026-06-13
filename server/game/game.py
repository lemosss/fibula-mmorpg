"""
game.py — O orquestrador do jogo.

Mantém o estado do mundo (jogadores, monstros, NPCs, itens no chão),
processa as mensagens dos clientes e roda o tick da simulação (IA dos
monstros, respawn, decay, regeneração, autosave).

Modelo de rede: server-authoritative. O cliente só pede ("quero andar para
o norte") e o servidor decide e propaga eventos para quem pode ver:
  espawn / edespawn / emove / ehp  — entidades entrando/saindo/andando/HP
  stats / inv / ground / chat / fx — estado do próprio jogador e do chão
"""
import heapq
import random
import re

import config
from game import data, entities, formulas, npcs, spells
from game.entities import DIRS, Monster, Npc, Player, now_ms
from game.world import World

# nomes em português para o /olhar
LOOK_NAMES = {
    "grass": "grama", "dirt": "terra batida", "stone": "um piso de pedra",
    "water": "agua", "sand": "areia", "marble": "um piso de marmore",
    "wood": "um assoalho de madeira", "cave": "chao de caverna",
    "tree": "uma arvore", "wall": "uma muralha", "rock": "uma rocha",
    "bush": "um arbusto", "fence": "uma cerca", "altar": "um altar sagrado",
    "gravestone": "uma lapide", "cave_wall": "rocha maciça",
    "stairs_down": "uma escada para baixo", "stairs_up": "uma escada para cima",
}

SKILL_LABELS = {
    "fist": "luta livre", "club": "combate com clava",
    "sword": "combate com espada", "axe": "combate com machado",
    "distance": "combate a distancia", "shield": "defesa com escudo",
    "fishing": "pesca", "magic": "magic level",
}

# nomes aceitos pelo /skill (português e inglês)
SKILL_ALIASES = {
    "punho": "fist", "fist": "fist",
    "clava": "club", "club": "club",
    "espada": "sword", "sword": "sword",
    "machado": "axe", "axe": "axe",
    "distancia": "distance", "distance": "distance",
    "escudo": "shield", "shield": "shield",
    "pesca": "fishing", "fishing": "fishing",
    "magia": "magic", "magic": "magic", "ml": "magic",
}

STARTER_INVENTORY = [
    {"id": 52, "count": 3},   # pães
    {"id": 40, "count": 1},   # poção de vida
    {"id": 1, "count": 50},   # moedas de ouro
]
STARTER_EQUIPMENT = {
    "weapon": {"id": 11, "count": 1},      # clava
    "backpack": {"id": 70, "count": 1},    # mochila (24 slots no total)
}

RE_ACCOUNT = re.compile(r"^[A-Za-z0-9_]{3,20}$")
RE_CHARNAME = re.compile(r"^[A-Za-z][A-Za-z ]{2,19}$")

# posturas de combate: (multiplicador de dano, multiplicador de defesa)
STANCES = {
    "attack":   (1.25, 0.6),
    "balanced": (1.0, 1.0),
    "defense":  (0.7, 1.4),
}
DIAGONAL_STEP_FACTOR = 2     # passo diagonal demora 2x (estilo Tibia)
DROP_RANGE = 3               # distância máxima para jogar itens


class Game:
    def __init__(self, db):
        self.db = db
        self.world = World()
        self.players = {}     # id -> Player
        self.monsters = {}    # id -> Monster
        self.npcs = {}        # id -> Npc
        self.by_pos = {}      # (x, y, z) -> Creature (ocupação; criaturas bloqueiam)
        self.respawn_q = []   # heap de (due_ms, seq, zona) -> dispara o AVISO
        self.birth_q = []     # heap de (due_ms, seq, zona, spot) -> nasce de fato
        self._seq = 0
        self.last_decay = 0.0
        self.last_autosave = now_ms()

        for name, ndef in data.NPCS.items():
            npc = Npc(name, ndef)
            self.npcs[npc.id] = npc
            self.by_pos[npc.pos] = npc

        for zone in self.world.spawns:
            for _ in range(zone["count"]):
                self.spawn_from_zone(zone)

        print(f"[mundo] {len(self.monsters)} monstros, {len(self.npcs)} NPCs, "
              f"templo em {self.world.temple}")

    # ================================================================ util

    def occupied(self, x: int, y: int, z: int) -> bool:
        return (x, y, z) in self.by_pos

    def entities(self):
        yield from self.players.values()
        yield from self.monsters.values()
        yield from self.npcs.values()

    @staticmethod
    def visible(p: Player, x: int, y: int, z: int) -> bool:
        return (z == p.z and abs(x - p.x) <= config.VIEW_X
                and abs(y - p.y) <= config.VIEW_Y)

    @staticmethod
    def dist(a, b) -> int:
        return max(abs(a.x - b.x), abs(a.y - b.y))   # distância de Chebyshev

    @staticmethod
    def face(e, tx: int, ty: int):
        dx, dy = tx - e.x, ty - e.y
        if abs(dx) >= abs(dy):
            e.dir = "e" if dx > 0 else "w"
        else:
            e.dir = "s" if dy > 0 else "n"

    # ===================================================== visão/broadcast

    def refresh_view(self, p: Player):
        """Sincroniza o conjunto de entidades que o cliente de `p` conhece."""
        for e in self.entities():
            vis = self.visible(p, e.x, e.y, e.z)
            known = e.id in p.known
            if vis and not known:
                p.known.add(e.id)
                p.send({"type": "espawn", "e": e.to_client()})
            elif not vis and known:
                p.known.discard(e.id)
                p.send({"type": "edespawn", "id": e.id})

    def broadcast_spawn(self, e):
        for p in self.players.values():
            if self.visible(p, e.x, e.y, e.z) and e.id not in p.known:
                p.known.add(e.id)
                p.send({"type": "espawn", "e": e.to_client()})

    def broadcast_despawn(self, e):
        for p in self.players.values():
            if e.id in p.known:
                p.known.discard(e.id)
                p.send({"type": "edespawn", "id": e.id})

    def broadcast_hp(self, e):
        for p in self.players.values():
            if e.id in p.known:
                p.send({"type": "ehp", "id": e.id, "hp": e.hp, "maxhp": e.maxhp})

    def fx(self, x: int, y: int, z: int, kind=None, text=None, color=None):
        """Efeito visual num tile (sangue, cura, número de dano...)."""
        msg = {"type": "fx", "x": x, "y": y}
        if kind:
            msg["kind"] = kind
        if text is not None:
            msg["text"] = text
            msg["color"] = color or "#fff"
        for p in self.players.values():
            if self.visible(p, x, y, z):
                p.send(msg)

    def broadcast_ground(self, x: int, y: int, z: int):
        msg = self.world.ground_payload(x, y, z)
        for p in self.players.values():
            p.send(msg)

    def proj(self, fx: int, fy: int, tx: int, ty: int, z: int, sprite: str):
        """Projétil voando de (fx,fy) até (tx,ty) — flecha, lança..."""
        msg = {"type": "proj", "fx": fx, "fy": fy, "tx": tx, "ty": ty,
               "sprite": sprite}
        for p in self.players.values():
            if self.visible(p, fx, fy, z) or self.visible(p, tx, ty, z):
                p.send(msg)

    # ============================================================ movimento

    def move_creature(self, e, nx: int, ny: int, ndir: str, dur: int, nz=None):
        """Move/teleporta uma criatura e propaga os eventos de visão."""
        if self.by_pos.get(e.pos) is e:
            del self.by_pos[e.pos]
        e.x, e.y, e.dir = nx, ny, ndir
        if nz is not None:
            e.z = nz
        self.by_pos[e.pos] = e

        for p in self.players.values():
            if p is e:
                continue
            vis = self.visible(p, e.x, e.y, e.z)
            known = e.id in p.known
            if vis and known:
                p.send({"type": "emove", "id": e.id, "x": e.x, "y": e.y,
                        "z": e.z, "dir": e.dir, "ms": dur})
            elif vis and not known:
                p.known.add(e.id)
                p.send({"type": "espawn", "e": e.to_client()})
            elif not vis and known:
                p.known.discard(e.id)
                p.send({"type": "edespawn", "id": e.id})

        if isinstance(e, Player):
            e.send({"type": "emove", "id": e.id, "x": e.x, "y": e.y,
                    "z": e.z, "dir": e.dir, "ms": dur})
            self.refresh_view(e)
            # afastou-se de algum corpo aberto? fecha aquela janela
            for (cx, cy, cz) in list(e.open_containers):
                if e.z != cz or max(abs(e.x - cx), abs(e.y - cy)) > 1:
                    e.open_containers.discard((cx, cy, cz))
                    e.send({"type": "container_close", "x": cx, "y": cy})

    def teleport(self, e, x: int, y: int, z: int = None):
        if z is None:
            z = e.z
        if not self.world.walkable(x, y, z) or self.occupied(x, y, z):
            spot = self.world.find_free_near(x, y, z, self.occupied)
            if spot is None:
                return
            x, y = spot
        self.move_creature(e, x, y, e.dir, 0, z)

    def check_hole(self, p: Player):
        """
        Pisou num buraco aberto OU no vão de uma escada para BAIXO?
        Desce automaticamente (subir continua sendo só no clique).
        """
        dest = self.world.holes.get(p.pos)
        if dest is not None:
            p.path = []
            p.pending_stairs = None
            self.teleport(p, *dest)
            self.chat_to(p, "Voce caiu no buraco!")
            self.fx(p.x, p.y, p.z, kind="poff")
            return
        dest = self.world.portals.get(p.pos)
        if dest is not None and dest[2] > p.z:   # escada que DESCE
            p.path = []
            p.pending_stairs = None
            self.teleport(p, *dest)
            self.chat_to(p, "Voce desce as escadas.")

    def use_portal(self, p: Player, x: int, y: int):
        """Usa a escada em (x, y) — só acontece quando o jogador CLICA nela."""
        dest = self.world.portals.get((x, y, p.z))
        if dest is None:
            return
        p.path = []
        p.pending_stairs = None
        going_down = dest[2] > p.z
        self.teleport(p, *dest)
        self.chat_to(p, "Voce desce as escadas." if going_down
                     else "Voce sobe as escadas.")

    def h_use_stairs(self, p: Player, msg):
        """Clique numa escada: usa se estiver perto, senão anda até ela antes."""
        x, y = int(msg.get("x", p.x)), int(msg.get("y", p.y))
        if (x, y, p.z) not in self.world.portals:
            return
        if max(abs(x - p.x), abs(y - p.y)) <= 1:
            return self.use_portal(p, x, y)    # em cima ou adjacente: usa já
        path = self.world.find_path(p.z, p.x, p.y, x, y)
        if path is None:
            return self.chat_to(p, "Nao ha caminho ate a escada.")
        p.path = path
        p.path_target = (x, y)
        p.path_stuck = 0
        p.pending_stairs = (x, y)              # usa ao pisar nela

    def _pz_entry_blocked(self, p: Player, nx: int, ny: int) -> bool:
        """Com lock PvP ativo não se entra na zona de proteção."""
        return (now_ms() < p.pvp_lock_until
                and self.world.in_pz(nx, ny, p.z)
                and not self.world.in_pz(p.x, p.y, p.z))

    def try_move(self, p: Player, d: str):
        p.path = []                            # input manual cancela o autowalk
        p.pending_stairs = None
        p.pending = None                       # cancela ação pendente (andar-até)
        self.break_follow_on_manual_move(p)    # só cancela se estava perseguindo
        if d not in DIRS:
            return
        now = now_ms()
        if now < p.next_move:
            return
        dx, dy = DIRS[d]
        nx, ny = p.x + dx, p.y + dy
        diagonal = dx != 0 and dy != 0
        facing = d if not diagonal else ("e" if dx > 0 else "w")
        if self._pz_entry_blocked(p, nx, ny):
            p.next_move = now + 600            # avisa sem spammar
            return self.chat_to(
                p, "Voce esta em combate PvP e nao pode entrar na "
                   "zona de protecao.")
        if not self.world.walkable(nx, ny, p.z) or self.occupied(nx, ny, p.z):
            if p.dir != facing:                  # só vira para a direção
                p.dir = facing
                self.move_creature(p, p.x, p.y, facing, 0)
            return
        dur = p.step_ms() * (DIAGONAL_STEP_FACTOR if diagonal else 1)
        p.next_move = now + dur
        self.move_creature(p, nx, ny, facing, dur)
        self.check_hole(p)

    def h_walkto(self, p: Player, msg):
        """Clique para andar: calcula um caminho e segue automaticamente."""
        p.pending_stairs = None
        tx = max(0, min(self.world.w - 1, int(msg.get("x", p.x))))
        ty = max(0, min(self.world.h - 1, int(msg.get("y", p.y))))
        path = self.world.find_path_smart(p.z, p.x, p.y, tx, ty)
        if path is None:
            self.chat_to(p, "Nao ha caminho ate la.")
            return
        p.path = path
        p.path_target = (tx, ty)
        p.path_stuck = 0

    def player_autowalk(self, p: Player, now: float):
        """Executa o próximo passo do autowalk (respeitando a velocidade)."""
        if not p.path or now < p.next_move:
            return
        nx, ny = p.path[0]
        if self._pz_entry_blocked(p, nx, ny):
            p.path = []
            return self.chat_to(
                p, "Voce esta em combate PvP e nao pode entrar na "
                   "zona de protecao.")
        if self.occupied(nx, ny, p.z):
            # criatura no caminho: recalcula a rota; se continuar bloqueado,
            # espera um pouco (ela pode sair) e desiste depois de ~2s
            tx, ty = p.path_target
            new = self.world.find_path_smart(p.z, p.x, p.y, tx, ty)
            if new and not self.occupied(new[0][0], new[0][1], p.z):
                p.path = new
                p.path_stuck = 0
                nx, ny = p.path[0]
            else:
                p.path_stuck += 1
                if p.path_stuck > 20:
                    p.path = []
                    self.chat_to(p, "O caminho esta bloqueado.")
                return
        p.path.pop(0)
        dxs, dys = nx - p.x, ny - p.y
        diagonal = dxs != 0 and dys != 0
        d = ("e" if dxs > 0 else "w") if dxs else ("s" if dys > 0 else "n")
        dur = p.step_ms() * (DIAGONAL_STEP_FACTOR if diagonal else 1)
        p.next_move = now + dur
        self.move_creature(p, nx, ny, d, dur)
        # escada clicada: usa ao pisar nela
        if p.pending_stairs == (p.x, p.y):
            self.use_portal(p, p.x, p.y)
        self.check_hole(p)

    # ========================================================== tick (100ms)

    def tick(self):
        now = now_ms()
        for p in list(self.players.values()):
            self.player_follow(p, now)
            self.player_autowalk(p, now)
            self.player_pending(p, now)
            self.player_combat(p, now)
            self.player_regen(p, now)
            # caveira expirou? avisa quem vê
            if p.skull_until and now >= p.skull_until:
                p.skull_until = 0.0
                for q in self.players.values():
                    if p.id in q.known:
                        q.send({"type": "eskull", "id": p.id, "on": False})
            # fechou o cliente em combate PvP: sai só quando o lock acabar
            if p.lingering and now >= p.pvp_lock_until:
                self.leave_world(p)
        for m in list(self.monsters.values()):
            self.monster_ai(m, now)
        while self.respawn_q and self.respawn_q[0][0] <= now:
            _, _, zone = heapq.heappop(self.respawn_q)
            self.schedule_birth(zone, now)
        while self.birth_q and self.birth_q[0][0] <= now:
            _, _, zone, spot = heapq.heappop(self.birth_q)
            self.spawn_at(zone, spot)
        if now - self.last_decay > 1000:
            self.last_decay = now
            for (x, y, z) in self.world.decay_tick(now):
                self.broadcast_ground(x, y, z)
                self.sync_containers(x, y, z)   # corpo sumiu? fecha a janela
        if now - self.last_autosave > config.AUTOSAVE_S * 1000:
            self.last_autosave = now
            self.save_all()

    # ============================================================== combate

    def clear_target(self, p: Player, notify: bool = True):
        """Limpa o alvo. O MODO follow continua armado para o próximo alvo."""
        p.target_id = 0
        if p.follow_on:
            p.path = []                        # para de perseguir este alvo
        if notify:
            p.send({"type": "target", "id": 0})

    def break_follow_on_manual_move(self, p: Player):
        """Mexeu manualmente NO MEIO de uma perseguição: desliga o follow."""
        if p.follow_on and p.target_id:
            p.follow_on = False
            p.send(p.stats_payload())

    def set_skull(self, p: Player, now: float):
        """Agrediu um jogador: caveira visível + lock PvP (renováveis)."""
        had_skull = now < p.skull_until
        p.skull_until = now + config.SKULL_S * 1000
        p.pvp_lock_until = now + config.PVP_LOCK_S * 1000
        if not had_skull:
            for q in self.players.values():
                if p.id in q.known:
                    q.send({"type": "eskull", "id": p.id, "on": True})
            self.chat_to(p, "Voce agrediu um jogador: caveira ativa, sem "
                            "logout e sem entrar na cidade por um tempo.")

    def _walk_then(self, p: Player, tx: int, ty: int, fn):
        """
        Executa `fn` se já estiver adjacente a (tx,ty); senão CANCELA o follow,
        anda até lá (contornando paredes/criaturas, com diagonais) e executa
        ao chegar (estilo Tibia: arrastar/clicar algo longe te leva).
        """
        if max(abs(tx - p.x), abs(ty - p.y)) <= 1:
            fn()
            return
        # desvia das outras criaturas perto (o destino é excluído)
        avoid = {(bx, by) for (bx, by, bz) in self.by_pos
                 if bz == p.z and (bx, by) != (tx, ty) and (bx, by) != (p.x, p.y)
                 and abs(bx - p.x) <= 12 and abs(by - p.y) <= 12}
        path = self.world.find_path_smart(p.z, p.x, p.y, tx, ty, avoid=avoid)
        if path is None:                          # sem rota desviando: tenta direta
            path = self.world.find_path_smart(p.z, p.x, p.y, tx, ty)
        if path is None:
            return self.chat_to(p, "Nao ha caminho ate la.")
        if p.follow_on:                           # arrastar cancela o follow
            p.follow_on = False
            p.send(p.stats_payload())
        p.path = path
        p.path_target = (tx, ty)
        p.path_stuck = 0
        p.pending = (tx, ty, p.z, fn)

    def player_pending(self, p: Player, now: float):
        """Executa a ação pendente quando o jogador chega ao destino."""
        if not p.pending:
            return
        tx, ty, tz, fn = p.pending
        if p.z == tz and max(abs(p.x - tx), abs(p.y - ty)) <= 1:
            p.pending = None
            fn()
        elif not p.path:                          # caminho acabou sem chegar
            p.pending = None

    def give(self, p: Player, item_id: int, count: int = 1) -> str:
        """
        Tenta entregar itens ao jogador respeitando CAPACITY e espaço.
        Retorna "" em caso de sucesso ou a mensagem de erro.
        """
        if not p.can_carry(item_id, count):
            return "Voce nao tem capacidade suficiente (peso)."
        if not p.inv_add(item_id, count):
            return "Sem espaco na mochila."
        return ""

    def train_skill(self, p: Player, name: str, amount: int = 1):
        """Treino por uso: golpes (melee), bloqueios (shield), mana (magic)."""
        sk = p.skills[name]
        sk["tries"] += amount
        needed = formulas.skill_tries_needed(name, sk["level"], p.vocation)
        leveled = False
        while sk["tries"] >= needed:
            sk["tries"] -= needed
            sk["level"] += 1
            leveled = True
            needed = formulas.skill_tries_needed(name, sk["level"], p.vocation)
        if leveled:
            label = SKILL_LABELS.get(name, name)
            self.chat_to(p, f"Voce avancou em {label} ({sk['level']}).", "info")
            self.fx(p.x, p.y, p.z, kind="levelup")
        p.send(p.skills_payload())

    def player_follow(self, p: Player, now: float):
        """
        MODO follow (chase, estilo Tibia): fica armado mesmo sem alvo;
        ao mirar algo, persegue automaticamente até colar.
        """
        if not p.follow_on or not p.target_id:
            return
        t = (self.monsters.get(p.target_id) or self.players.get(p.target_id))
        if t is None or t.z != p.z:
            p.path = []                        # alvo sumiu: modo segue armado
            return
        if self.dist(p, t) <= 1:
            p.path = []                        # colado no alvo: para
            return
        # mantém uma rota até o alvo (recalcula quando ele se move)
        if p.path:
            end = p.path[-1]
            if max(abs(end[0] - t.x), abs(end[1] - t.y)) > 1:
                p.path = []
        if not p.path:
            p.path = self.world.find_path_smart(p.z, p.x, p.y, t.x, t.y,
                                                max_len=60) or []
            p.path_target = (t.x, t.y)

    def player_combat(self, p: Player, now: float):
        if not p.target_id:
            return
        target = (self.monsters.get(p.target_id)
                  or self.players.get(p.target_id))
        if target is None:
            self.clear_target(p)               # alvo morreu/sumiu
            return
        wdef = p.weapon_def()
        weapon_range = wdef.get("range", 1)
        if (target.z != p.z or self.dist(p, target) > weapon_range
                or now < p.next_attack):
            return
        # PvP: ambos fora da zona de proteção e com o modo ligado
        if isinstance(target, Player):
            block = None
            if not p.pvp or not target.pvp:
                block = "Os dois precisam estar com o modo PvP ligado."
            elif (self.world.in_pz(p.x, p.y, p.z)
                    or self.world.in_pz(target.x, target.y, target.z)):
                block = "Nao se pode atacar na zona de protecao (cidade)."
            if block:
                p.next_attack = now + 1500     # avisa sem spammar
                return self.chat_to(p, block)

        atk = p.weapon_atk()
        wclass = p.weapon_class()
        if weapon_range > 1:                   # arma de distância
            if wdef.get("needsAmmo"):          # arco: usa flecha do slot ammo
                ammo = p.equipment.get("ammo")
                adef = data.item(ammo["id"]) if ammo else {}
                if not ammo or adef.get("ammoType") != wdef["needsAmmo"]:
                    p.next_attack = now + 1000
                    return self.chat_to(p, "Voce esta sem flechas.")
                atk = adef.get("atk", 8)
                ammo["count"] -= 1             # flecha consumida
                if ammo["count"] <= 0:
                    p.equipment["ammo"] = None
                p.send(p.inv_payload())
                proj_sprite = "arrow"
            else:                              # lança: arremessa a própria arma
                weapon = p.equipment["weapon"]
                weapon["count"] -= 1           # consumida (não cai no chão)
                if weapon["count"] <= 0:
                    p.equipment["weapon"] = None
                p.send(p.inv_payload())
                proj_sprite = "spear"
            self.proj(p.x, p.y, target.x, target.y, p.z, proj_sprite)

        p.next_attack = now + config.ATTACK_COOLDOWN_MS
        self.face(p, target.x, target.y)
        # locks de combate: PvP marca caveira no agressor; PvE só trava logout
        if isinstance(target, Player):
            self.set_skull(p, now)
            target.pve_lock_until = now + config.PVE_LOCK_S * 1000
        else:
            p.pve_lock_until = now + config.PVE_LOCK_S * 1000
        skill = p.skills[wclass]["level"]
        dmg_mult = STANCES[p.stance][0]
        raw = int(formulas.player_melee_roll(skill, atk, p.level)
                  * dmg_mult)
        if isinstance(target, Player):
            defense = int(target.defense() * STANCES[target.stance][1])
        else:
            defense = target.armor
        dmg = formulas.mitigate(raw, defense)
        self.train_skill(p, wclass)            # todo golpe treina a arma
        if dmg <= 0:
            self.fx(target.x, target.y, target.z, kind="poff")
            return
        target.hp = max(0, target.hp - dmg)
        self.fx(target.x, target.y, target.z, kind="blood",
                text=f"-{dmg}", color="#e44")
        self.broadcast_hp(target)
        if isinstance(target, Player):
            if target.equipment.get("shield"):
                self.train_skill(target, "shield")
            if target.hp <= 0:
                self.kill_player(target, p)
            else:
                target.send(target.stats_payload())
        elif target.hp <= 0:
            self.kill_monster(target, p)

    def monster_swing(self, m: Monster, p: Player, now: float):
        m.next_attack = now + m.atk_ms
        p.pve_lock_until = now + config.PVE_LOCK_S * 1000
        raw = formulas.monster_melee_roll(m.dmg_min, m.dmg_max)
        defense = int(p.defense() * STANCES[p.stance][1])
        dmg = formulas.mitigate(raw, defense)
        if p.equipment.get("shield"):
            self.train_skill(p, "shield")      # apanhar de escudo treina defesa
        if dmg <= 0:
            self.fx(p.x, p.y, p.z, kind="poff")
            return
        p.hp -= dmg
        self.fx(p.x, p.y, p.z, kind="blood", text=f"-{dmg}", color="#e44")
        if p.hp <= 0:
            self.kill_player(p, m)
        else:
            p.send(p.stats_payload())
            self.broadcast_hp(p)

    def kill_monster(self, m: Monster, killer: Player):
        del self.monsters[m.id]
        if self.by_pos.get(m.pos) is m:
            del self.by_pos[m.pos]
        self.broadcast_despawn(m)

        # experiência (número branco no tile do monstro, como no Tibia)
        self.fx(m.x, m.y, m.z, text=str(m.exp), color="#fff")
        self.add_exp(killer, m.exp)

        # corpo no chão, com o loot DENTRO (clica no corpo para saquear)
        now = now_ms()
        contents, looted = [], []
        for entry in m.loot:
            if random.random() >= entry["chance"]:
                continue
            count = random.randint(1, entry.get("max", 1))
            contents.append({"id": entry["item"], "count": count})
            name = data.item_name(entry["item"])
            looted.append(f"{count}x {name}" if count > 1 else name)
        corpse = {"id": config.CORPSE_ITEM_ID, "count": 1,
                  "decay": now + config.CORPSE_DECAY_S * 1000,
                  "name": f"corpo de {m.name}", "contents": contents}
        self.world.ground_items.setdefault((m.x, m.y, m.z), []).append(corpse)
        self.broadcast_ground(m.x, m.y, m.z)
        loot_txt = ", ".join(looted) if looted else "nada"
        self.chat_to(killer, f"Loot de {m.name}: {loot_txt}.", "loot")

        if m.zone:
            # o aviso (5s) faz parte do tempo total de respawn
            delay = max(5000, m.zone["respawn"] * 1000 - config.SPAWN_WARN_MS)
            self._seq += 1
            heapq.heappush(self.respawn_q, (now + delay, self._seq, m.zone))

    def kill_player(self, p: Player, killer):
        p.deaths += 1
        loss = int(p.exp * config.DEATH_EXP_LOSS)
        # não rebaixa de nível no MVP: a exp nunca cai abaixo do piso do nível
        p.exp = max(formulas.exp_for_level(p.level), p.exp - loss)
        self.fx(p.x, p.y, p.z, kind="blood")
        self.chat_all(f"{p.name} morreu para {killer.name}.")
        for m in self.monsters.values():
            if m.target_id == p.id:
                m.target_id = 0
        for q in self.players.values():        # players atacando a vítima
            if q.target_id == p.id:
                self.clear_target(q)
        p.target_id = 0
        p.follow_on = False
        p.path = []
        p.pending_stairs = None
        p.pending = None
        # a morte limpa caveira e locks de combate
        if p.skull_until:
            p.skull_until = 0.0
            for q in self.players.values():
                if p.id in q.known:
                    q.send({"type": "eskull", "id": p.id, "on": False})
        p.pvp_lock_until = 0.0
        p.pve_lock_until = 0.0
        p.hp, p.mp = p.maxhp, p.maxmp
        self.teleport(p, self.world.temple[0], self.world.temple[1], 0)
        self.broadcast_hp(p)
        p.send({"type": "target", "id": 0})
        p.send({"type": "dead",
                "message": f"Voce morreu e perdeu {loss} de experiencia. "
                           "O templo te acolheu de volta."})
        p.send(p.stats_payload())
        self.db.save_character(p.char_id, p)

    def add_exp(self, p: Player, amount: int):
        p.exp += amount
        leveled = False
        while p.exp >= formulas.exp_for_level(p.level + 1):
            p.level += 1
            leveled = True
        if leveled:
            p.maxhp = formulas.max_hp(p.level, p.vocation)
            p.maxmp = formulas.max_mp(p.level, p.vocation)
            p.hp = min(p.maxhp, p.hp + 5 * 3)    # bônus de vida ao upar
            self.fx(p.x, p.y, p.z, kind="levelup", text="LEVEL UP!", color="#fc3")
            self.chat_to(p, f"Voce avancou para o nivel {p.level}!", "info")
            self.broadcast_hp(p)
        p.send(p.stats_payload())

    # ======================================================== IA dos monstros

    def monster_ai(self, m: Monster, now: float):
        target = self.players.get(m.target_id)
        # uma vez engajado, persegue longe (até 2x o aggro) p/ não desistir
        # no meio de um contorno de parede/grupo
        leash = m.aggro * 2 + 4
        if target and (target.z != m.z or target.ghost
                       or self.dist(m, target) > leash
                       or self.world.in_pz(target.x, target.y, target.z)):
            m.target_id, target = 0, None
            m.follow_path = []

        if target is None:
            best = None
            for p in self.players.values():
                if p.z != m.z or p.ghost or self.world.in_pz(p.x, p.y, p.z):
                    continue
                d = self.dist(m, p)
                # entra na lista se estiver na área de visão (+2) OU no raio
                # próprio do monstro — assim bicho que aparece na tela vem
                in_view = (abs(m.x - p.x) <= config.AGGRO_X
                           and abs(m.y - p.y) <= config.AGGRO_Y)
                if (in_view or d <= m.aggro) and (best is None or d < best[0]):
                    best = (d, p)
            if best:
                m.target_id, target = best[1].id, best[1]

        if target:
            if self.dist(m, target) <= 1:
                self.face(m, target.x, target.y)
                if now >= m.next_attack:
                    self.monster_swing(m, target, now)
                # cerca o jogador: reposiciona com frequência moderada para os
                # SQMs livres ao redor do alvo (comportamento dinâmico, sem
                # ficar preso no mesmo tile), sempre em passo CARDEAL
                elif now >= m.next_move:
                    m.next_move = now + m.step_dur
                    if random.random() < 0.35:
                        self._reposition(m, target)
            elif now >= m.next_move:
                m.next_move = now + m.step_dur
                self.step_toward(m, target.x, target.y)
        elif now >= m.next_move:
            m.next_move = now + m.step_dur * 2
            if random.random() < 0.3:
                self.wander(m)

    def _reposition(self, m: Monster, target):
        """
        Cerca o alvo: dá UM passo CARDEAL para um SQM livre que ainda fique
        colado nele, preferindo o lado MENOS lotado (espalha os monstros ao
        redor do jogador). Nunca diagonal enquanto ataca; sem cardeal válido,
        fica parado atacando.
        """
        def valid(nx, ny):
            return (max(abs(nx - target.x), abs(ny - target.y)) == 1
                    and self.world.walkable(nx, ny, m.z)
                    and not self.occupied(nx, ny, m.z)
                    and not self.world.in_pz(nx, ny, m.z)
                    and (nx, ny, m.z) not in self.world.no_monster)

        cands = []
        for d in entities.CARDINALS:
            ox, oy = DIRS[d]
            nx, ny = m.x + ox, m.y + oy
            if valid(nx, ny):
                cands.append((ox, oy, nx, ny))
        if not cands:
            return

        def crowd(nx, ny):                         # quantos monstros já encostam
            return sum(1 for (dx, dy) in DIRS.values()
                       if isinstance(self.by_pos.get((nx + dx, ny + dy, m.z)),
                                     Monster))

        random.shuffle(cands)                       # desempate natural
        cands.sort(key=lambda c: crowd(c[2], c[3]))
        ox, oy = cands[0][0], cands[0][1]
        self._monster_step(m, ox, oy)

    def _monster_step(self, m: Monster, ox: int, oy: int) -> bool:
        """Tenta dar um passo (ox, oy). Diagonal custa 2x, como nos players.
        Monstros nunca pisam em buracos, escadas ou rope spots."""
        nx, ny = m.x + ox, m.y + oy
        if not (self.world.walkable(nx, ny, m.z)
                and not self.occupied(nx, ny, m.z)
                and not self.world.in_pz(nx, ny, m.z)
                and (nx, ny, m.z) not in self.world.no_monster):
            return False
        diagonal = ox != 0 and oy != 0
        facing = ("e" if ox > 0 else "w") if ox else ("s" if oy > 0 else "n")
        dur = m.step_dur * (DIAGONAL_STEP_FACTOR if diagonal else 1)
        if diagonal:                           # ajusta o cooldown do passo
            m.next_move += m.step_dur * (DIAGONAL_STEP_FACTOR - 1)
        self.move_creature(m, nx, ny, facing, dur)
        return True

    def _creatures_near(self, m: Monster, tx: int, ty: int, rng: int = 12):
        """Tiles ocupados por outras criaturas perto do monstro (p/ desviar).
        O alvo é excluído — o caminho precisa poder chegar até ele."""
        avoid = set()
        for (bx, by, bz) in self.by_pos:
            if (bz == m.z and (bx, by) != (tx, ty) and (bx, by) != (m.x, m.y)
                    and abs(bx - m.x) <= rng and abs(by - m.y) <= rng):
                avoid.add((bx, by))
        return avoid

    def step_toward(self, m: Monster, tx: int, ty: int):
        dx = (tx > m.x) - (tx < m.x)
        dy = (ty > m.y) - (ty < m.y)
        # 1) passo direto cardeal (rápido) se aproxima e está livre
        if abs(tx - m.x) >= abs(ty - m.y):
            direct = [(dx, 0), (0, dy)]
        else:
            direct = [(0, dy), (dx, 0)]
        for (ox, oy) in direct:
            if (ox or oy) and self._monster_step(m, ox, oy):
                m.follow_path = []
                m.path_stuck = 0
                return
        # 2) FOLLOW por rota BFS que contorna PAREDES e OUTRAS CRIATURAS
        if m.follow_path:
            end = m.follow_path[-1]
            if max(abs(end[0] - tx), abs(end[1] - ty)) > 2:
                m.follow_path = []             # alvo andou: recalcula
        if not m.follow_path:
            # rota ORTOGONAL-FIRST (diagonal só se não houver rota cardeal)
            m.follow_path = self.world.find_path_smart(
                m.z, m.x, m.y, tx, ty, max_len=140, avoid_pz=True,
                avoid=self._creatures_near(m, tx, ty)) or []
            m.path_stuck = 0
        if m.follow_path:
            nx, ny = m.follow_path[0]
            if self._monster_step(m, nx - m.x, ny - m.y):
                m.follow_path.pop(0)
                m.path_stuck = 0
                return
            # tile da rota momentaneamente ocupado: espera; insistiu? recalcula
            m.path_stuck += 1
            if m.path_stuck >= 3:
                m.follow_path = []
                m.path_stuck = 0
            return
        # 3) último recurso (preso entre paredes): passo diagonal
        if dx and dy:
            self._monster_step(m, dx, dy)

    def wander(self, m: Monster):
        hx, hy = m.home
        # se saiu muito longe de casa, tende a voltar
        if m.zone and max(abs(m.x - hx), abs(m.y - hy)) > m.zone["radius"] + 2:
            self.step_toward(m, hx, hy)
            return
        # vagueio é sempre cardeal (como no Tibia)
        dx, dy = DIRS[random.choice(entities.CARDINALS)]
        self._monster_step(m, dx, dy)

    def spawn_from_zone(self, zone: dict):
        """Spawn imediato (povoamento inicial do servidor, sem aviso)."""
        spot = self.world.random_spot_in_zone(zone, self.occupied)
        if spot is None:                       # zona lotada: tenta de novo depois
            self._seq += 1
            heapq.heappush(self.respawn_q, (now_ms() + 5000, self._seq, zone))
            return
        self.spawn_at(zone, spot)

    def schedule_birth(self, zone: dict, now: float):
        """
        Fase 1 do respawn: escolhe o tile, avisa quem está perto com a
        bolinha azul pulsante e agenda o nascimento para daqui a 5s.
        """
        spot = self.world.random_spot_in_zone(zone, self.occupied)
        if spot is None:                       # zona lotada: tenta de novo depois
            self._seq += 1
            heapq.heappush(self.respawn_q, (now + 5000, self._seq, zone))
            return
        z = zone.get("z", 0)
        warn = {"type": "spawn_warn", "x": spot[0], "y": spot[1], "z": z,
                "ms": config.SPAWN_WARN_MS}
        for p in self.players.values():
            if p.z == z:
                p.send(warn)
        self._seq += 1
        heapq.heappush(self.birth_q,
                       (now + config.SPAWN_WARN_MS, self._seq, zone, spot))

    def spawn_at(self, zone: dict, spot):
        """Fase 2: nasce no tile avisado (ou ao lado, se alguém parou em cima)."""
        z = zone.get("z", 0)
        x, y = spot
        if self.occupied(x, y, z):
            alt = self.world.find_free_near(x, y, z, self.occupied)
            if alt is None:
                self._seq += 1
                heapq.heappush(self.respawn_q, (now_ms() + 10000, self._seq, zone))
                return
            x, y = alt
        m = Monster(zone["monster"], x, y, zone, z)
        self.monsters[m.id] = m
        self.by_pos[m.pos] = m
        self.broadcast_spawn(m)

    # ========================================================== regeneração

    def player_regen(self, p: Player, now: float):
        fed = p.is_fed(now)                    # comida ou anel da vida
        hp_ms = config.REGEN_HP_MS_FED if fed else config.REGEN_HP_MS_BASE
        mp_ms = config.REGEN_MP_MS_FED if fed else config.REGEN_MP_MS_BASE
        if now >= p.next_hp_regen:
            p.next_hp_regen = now + hp_ms
            if p.hp < p.maxhp:
                p.hp += 1
                p.send(p.stats_payload())
                self.broadcast_hp(p)
        if now >= p.next_mp_regen:
            p.next_mp_regen = now + mp_ms
            if p.mp < p.maxmp:
                p.mp += 1
                p.send(p.stats_payload())

    # ================================================================= chat

    def chat_local(self, e, text: str, channel: str = "say"):
        for p in self.players.values():
            if self.visible(p, e.x, e.y, e.z):
                p.send({"type": "chat", "from": e.name, "text": text,
                        "x": e.x, "y": e.y, "channel": channel})

    def npc_say(self, npc, text: str):
        self.chat_local(npc, text, "npc")

    def chat_all(self, text: str):
        for p in self.players.values():
            p.send({"type": "chat", "from": "", "text": text, "channel": "server"})

    def chat_to(self, p: Player, text: str, channel: str = "info"):
        p.send({"type": "chat", "from": "", "text": text, "channel": channel})

    # ====================================================== entrada / saída

    def enter_world(self, conn, account_id: int, row, admin: bool = False) -> Player:
        p = Player(conn, account_id, row, admin)
        if not self.world.walkable(p.x, p.y, p.z) or self.occupied(p.x, p.y, p.z):
            spot = self.world.find_free_near(p.x, p.y, p.z, self.occupied)
            if spot is None:
                spot, p.z = self.world.temple, 0
            p.x, p.y = spot
        self.players[p.id] = p
        self.by_pos[p.pos] = p

        p.send({"type": "welcome", "id": p.id, "name": p.name,
                "admin": p.admin, "motd": config.MOTD,
                "map": self.world.client_map, "items": data.ITEMS,
                "hotkeys": p.hotkeys})
        p.send(p.stats_payload())
        p.send(p.skills_payload())
        p.send(p.inv_payload())
        p.send(self.world.ground_full_payload())
        self.refresh_view(p)
        self.broadcast_spawn(p)
        self.chat_all(f"{p.name} entrou no jogo.")
        print(f"[login] {p.name} (conta {account_id}) em {p.pos}")
        return p

    def leave_world(self, p: Player):
        if p.id not in self.players:
            return                              # já saiu (kick + desconexão)
        self.db.save_character(p.char_id, p)
        del self.players[p.id]
        if self.by_pos.get(p.pos) is p:
            del self.by_pos[p.pos]
        for m in self.monsters.values():
            if m.target_id == p.id:
                m.target_id = 0
        self.broadcast_despawn(p)
        self.chat_all(f"{p.name} saiu do jogo.")
        print(f"[logout] {p.name}")

    def save_all(self):
        for p in self.players.values():
            self.db.save_character(p.char_id, p)
        if self.players:
            print(f"[autosave] {len(self.players)} personagem(ns) salvos")

    # ==================================================== mensagens do cliente

    def handle(self, session, msg: dict):
        mtype = msg.get("type")
        p = session.player

        if mtype == "ping":
            session.conn.send_json({"type": "pong"})
            return

        if mtype == "logout" and p is not None:
            return self.h_logout(session, p)

        if p is None:
            if mtype == "register":
                self.h_register(session, msg)
            elif mtype == "login":
                self.h_login(session, msg)
            else:
                session.conn.send_json({"type": "error",
                                        "message": "Faca login primeiro."})
            return

        handlers = {
            "move": lambda: self.try_move(p, msg.get("dir", "")),
            "walkto": lambda: self.h_walkto(p, msg),
            "stop": lambda: self.h_stop(p),    # ESC: cancela autowalk/follow
            "use_stairs": lambda: self.h_use_stairs(p, msg),
            "move_item": lambda: self.h_move_item(p, msg),
            "move_ground": lambda: self.h_move_ground(p, msg),
            "drop_equip": lambda: self.h_drop_equip(p, msg),
            "equip_ground": lambda: self.h_equip_ground(p, msg),
            "stow": lambda: self.h_stow(p, msg),
            "stance": lambda: self.h_stance(p, msg),
            "pvp": lambda: self.h_pvp(p, msg),
            "follow": lambda: self.h_follow(p, msg),
            "open_container": lambda: self.h_open_container(p, msg),
            "loot": lambda: self.h_loot(p, msg),
            "loot_ground": lambda: self.h_loot_ground(p, msg),
            "loot_to": lambda: self.h_loot_to(p, msg),
            "store": lambda: self.h_store(p, msg),
            "close_container": lambda: self.h_close_container(p, msg),
            "look_item": lambda: self.h_look_item(p, msg),
            "hotkeys": lambda: self.h_hotkeys(p, msg),
            "say": lambda: self.h_say(p, msg),
            "attack": lambda: self.h_attack(p, msg),
            "push": lambda: self.h_push(p, msg),
            "pickup": lambda: self.h_pickup(p, msg),
            "equip": lambda: self.h_equip(p, msg),
            "unequip": lambda: self.h_unequip(p, msg),
            "use": lambda: self.h_use(p, msg),
            "drop": lambda: self.h_drop(p, msg),
            "look": lambda: self.h_look(p, msg),
            "npc_buy": lambda: self.h_trade(p, msg, npcs.buy),
            "npc_sell": lambda: self.h_trade(p, msg, npcs.sell),
        }
        fn = handlers.get(mtype)
        if fn:
            fn()

    # ----------------------------------------------------- conta/personagem

    def h_register(self, session, msg):
        account = str(msg.get("account", "")).strip()
        password = str(msg.get("password", ""))
        name = " ".join(str(msg.get("name", "")).split()).title()

        if not RE_ACCOUNT.match(account):
            return self._err(session, "Conta: 3-20 letras/numeros/underscore.")
        if not 4 <= len(password) <= 50:
            return self._err(session, "Senha: minimo de 4 caracteres.")
        if not RE_CHARNAME.match(name):
            return self._err(session, "Nome do personagem: 3-20 letras.")
        if self.db.character_name_exists(name):
            return self._err(session, "Nome de personagem ja em uso.")
        vocation = str(msg.get("vocation", formulas.DEFAULT_VOCATION))
        if vocation not in formulas.VOCATIONS:
            vocation = formulas.DEFAULT_VOCATION

        account_id = self.db.create_account(account, password)
        if account_id is None:
            return self._err(session, "Essa conta ja existe.")

        tx, ty = self.world.temple
        inv = STARTER_INVENTORY + [None] * (config.INV_SLOTS - len(STARTER_INVENTORY))
        self.db.create_character(account_id, name, tx, ty,
                                 formulas.max_hp(1, vocation),
                                 formulas.max_mp(1, vocation),
                                 inv, STARTER_EQUIPMENT, vocation)
        row = self.db.get_character_by_account(account_id)
        session.player = self.enter_world(session.conn, account_id, row,
                                          self.db.is_admin(account_id))

    def h_login(self, session, msg):
        account = str(msg.get("account", "")).strip()
        password = str(msg.get("password", ""))
        acc = self.db.check_login(account, password)
        if acc is None:
            return self._err(session, "Conta ou senha invalida.")
        account_id = acc["id"]
        row = self.db.get_character_by_account(account_id)
        if row is None:
            return self._err(session, "Conta sem personagem.")

        # personagem já online? derruba a sessão antiga
        for other in list(self.players.values()):
            if other.char_id == row["id"]:
                other.send({"type": "error",
                            "message": "Conectado em outro lugar."})
                self.leave_world(other)
                other.conn.close_now()

        row = self.db.get_character_by_account(account_id)  # estado pós-save
        session.player = self.enter_world(session.conn, account_id, row,
                                          bool(acc["is_admin"]))

    @staticmethod
    def _err(session, message: str):
        session.conn.send_json({"type": "error", "message": message})

    # -------------------------------------------------------------- ações

    def h_say(self, p: Player, msg):
        text = str(msg.get("text", "")).strip()[:200]
        if not text:
            return
        if text.startswith("/"):
            return self.h_command(p, text)
        self.chat_local(p, text)               # a fala sempre aparece no chat
        if spells.try_cast(self, p, text):     # palavras mágicas? conjura
            return
        npcs.handle_say(self, p, text)

    def h_attack(self, p: Player, msg):
        target_id = int(msg.get("id", 0) or 0)
        if target_id == 0 or target_id == p.target_id:
            return self.clear_target(p)
        elif target_id in self.monsters:
            p.target_id = target_id
        elif target_id in self.players and target_id != p.id:
            # PvP: exige o modo ligado dos dois lados
            other = self.players[target_id]
            if not p.pvp:
                self.chat_to(p, "Ative o modo PvP (icone ⚔) para atacar jogadores.")
            elif not other.pvp:
                self.chat_to(p, f"{other.name} nao esta em modo PvP.")
            else:
                p.target_id = target_id
        p.send({"type": "target", "id": p.target_id})

    def h_push(self, p: Player, msg):
        """
        Empurra uma criatura para um SQM ADJACENTE a ela (estilo Tibia).
        Regras: o jogador precisa estar encostado na criatura; o destino é só
        1 SQM ao lado dela; o tile precisa estar andável, livre e sem bloqueio
        (parede/PZ/buraco/escada); diagonal não corta quina de parede.
        """
        m = self.monsters.get(int(msg.get("id", 0) or 0))
        if m is None or m.z != p.z:
            return
        if not getattr(m, "pushable", True):
            return self.chat_to(p, "Voce nao consegue empurrar isso.")
        tx, ty = int(msg.get("tx", m.x)), int(msg.get("ty", m.y))
        # jogador encostado na criatura E destino encostado na criatura
        if max(abs(p.x - m.x), abs(p.y - m.y)) > 1:
            return
        if max(abs(tx - m.x), abs(ty - m.y)) != 1:
            return
        if not (self.world.walkable(tx, ty, m.z)
                and not self.occupied(tx, ty, m.z)
                and not self.world.in_pz(tx, ty, m.z)
                and (tx, ty, m.z) not in self.world.no_monster):
            return
        dx, dy = tx - m.x, ty - m.y
        if dx and dy and not (self.world.walkable(m.x + dx, m.y, m.z)
                              and self.world.walkable(m.x, m.y + dy, m.z)):
            return                                 # diagonal sem cortar parede
        facing = ("e" if dx > 0 else "w") if dx else ("s" if dy > 0 else "n")
        # empurrão anda na MESMA velocidade do monstro (diagonal 2x, como o passo)
        diagonal = dx != 0 and dy != 0
        dur = m.step_dur * (DIAGONAL_STEP_FACTOR if diagonal else 1)
        self.move_creature(m, tx, ty, facing, dur)
        m.next_move = max(m.next_move, now_ms() + dur)         # anti-spam leve
        m.follow_path = []

    def h_pickup(self, p: Player, msg):
        x, y = int(msg.get("x", p.x)), int(msg.get("y", p.y))
        count = msg.get("count")
        self._walk_then(p, x, y, lambda: self._do_pickup(p, x, y, count))

    def _do_pickup(self, p: Player, x: int, y: int, count=None):
        pile = self.world.ground_at(x, y, p.z)
        for it in reversed(pile):              # item do topo primeiro
            if data.item(it["id"]).get("pickable", True) is False:
                continue
            n = self._split_count(it, count)
            give = {"id": it["id"], "count": n} if n < it["count"] else it
            err = self._give_item(p, give)     # preserva contents de mochilas
            if not err:
                if n < it["count"]:
                    it["count"] -= n           # pega só parte da pilha
                else:
                    pile.remove(it)
                    if not pile:
                        self.world.ground_items.pop((x, y, p.z), None)
                self.broadcast_ground(x, y, p.z)
                p.send(p.inv_payload())
                p.send(p.stats_payload())      # ouro/peso podem ter mudado
                name = data.item_name(it["id"])
                qty = f"{n}x " if n > 1 else ""
                self.chat_to(p, f"Voce pegou {qty}{name}.")
            else:
                self.chat_to(p, err)
            return
        self.chat_to(p, "Nao ha nada para pegar ai.")

    def _try_unpack_backpack(self, p: Player, item: dict) -> bool:
        """
        Mochila com itens dentro acabou de ser equipada: despeja o conteúdo
        nos slots extras. Retorna False (sem mexer) se não houver vaga.
        """
        contents = item.get("contents")
        if not contents:
            return True
        free = [i for i in range(config.BASE_INV_SLOTS, p.active_slots())
                if p.inventory[i] is None]
        if len(free) < len(contents):
            return False
        for it, i in zip(contents, free):
            it.pop("decay", None)
            p.inventory[i] = it
        item.pop("contents", None)
        item.pop("name", None)
        return True

    def _backpack_can_shrink(self, p: Player, new_bp_item) -> bool:
        """Trocar/remover a mochila não pode deixar itens fora dos slots."""
        extra = (data.item(new_bp_item["id"]).get("capacity", 0)
                 if new_bp_item else 0)
        new_active = min(config.INV_SLOTS, config.BASE_INV_SLOTS + extra)
        return all(p.inventory[i] is None
                   for i in range(new_active, config.INV_SLOTS))

    def _pickup_container(self, p: Player, it: dict) -> str:
        """Pega uma mochila cheia do chão para um slot (conteúdo preservado)."""
        if not p.can_carry_weight(entities.Player.item_weight(it)):
            return "Voce nao tem capacidade suficiente (peso)."
        for i in range(p.active_slots()):
            if p.inventory[i] is None:
                p.inventory[i] = {k: v for k, v in it.items() if k != "decay"}
                return ""
        return "Sem espaco na mochila."

    def h_stow(self, p: Player, msg):
        """Arrastar um item para cima do ícone da mochila: guarda dentro dela."""
        i = int(msg.get("slot", -1))
        active = p.active_slots()
        if not 0 <= i < active or p.inventory[i] is None:
            return
        if i >= config.BASE_INV_SLOTS:
            return                              # já está dentro da mochila
        item = p.inventory[i]
        # tenta empilhar com pilha igual dentro da mochila
        if data.item(item["id"]).get("stackable"):
            for j in range(config.BASE_INV_SLOTS, active):
                s = p.inventory[j]
                if (s and s["id"] == item["id"]
                        and s["count"] + item["count"] <= config.STACK_MAX):
                    s["count"] += item["count"]
                    p.inventory[i] = None
                    return p.send(p.inv_payload())
        for j in range(config.BASE_INV_SLOTS, active):
            if p.inventory[j] is None:
                p.inventory[j] = item
                p.inventory[i] = None
                return p.send(p.inv_payload())
        self.chat_to(p, "A mochila esta cheia.")

    def h_equip(self, p: Player, msg):
        i = int(msg.get("slot", -1))
        if not 0 <= i < config.INV_SLOTS or p.inventory[i] is None:
            return
        item = p.inventory[i]
        itype = data.item(item["id"]).get("type")
        slot = entities.TYPE_TO_SLOT.get(itype)
        if slot is None:
            return self.chat_to(p, "Isso nao e equipavel.")
        if slot == "backpack" and not self._backpack_can_shrink(p, item):
            return self.chat_to(
                p, "Esvazie os ultimos slots antes de trocar de mochila.")
        old = p.equipment.get(slot)
        p.inventory[i] = old                      # swap com o que estava
        p.equipment[slot] = item
        if slot == "backpack" and not self._try_unpack_backpack(p, item):
            p.equipment[slot] = old               # sem vaga: desfaz
            p.inventory[i] = item
            return self.chat_to(
                p, "Sem espaco para despejar o conteudo dessa mochila.")
        p.send(p.inv_payload())
        p.send(p.stats_payload())

    def h_unequip(self, p: Player, msg):
        eslot = msg.get("eslot")
        item = p.equipment.get(eslot) if eslot in entities.EQUIP_SLOTS else None
        if item is None:
            return
        if eslot == "backpack":
            # sem mochila não há slot nenhum: ela só sai para o chão ou
            # trocando por outra mochila
            return self.chat_to(
                p, "Arraste a mochila para o chao (ela leva os itens dentro) "
                   "ou troque por outra mochila.")
        p.equipment[eslot] = None
        if not p.inv_add(item["id"], item["count"]):
            p.equipment[eslot] = item          # não coube: desfaz
            return self.chat_to(p, "Sem espaco na mochila.")
        p.send(p.inv_payload())
        p.send(p.stats_payload())

    def h_use(self, p: Player, msg):
        i = int(msg.get("slot", -1))
        if not 0 <= i < config.INV_SLOTS or p.inventory[i] is None:
            return
        item = p.inventory[i]
        idef = data.item(item["id"])
        now = now_ms()

        if idef.get("type") == "potion":
            healed = []
            if idef.get("heal_hp"):
                p.hp = min(p.maxhp, p.hp + idef["heal_hp"])
                healed.append("vida")
            if idef.get("heal_mp"):
                p.mp = min(p.maxmp, p.mp + idef["heal_mp"])
                healed.append("mana")
            self.fx(p.x, p.y, p.z, kind="heal")
            self.chat_to(p, f"Voce bebeu {idef['name']} (+{'/'.join(healed)}).")
            self.broadcast_hp(p)
        elif idef.get("type") == "food":
            base = max(now, p.fed_until)
            p.fed_until = min(base + idef.get("food_hp", 0) * config.FOOD_MS_PER_HP,
                              now + config.FOOD_MAX_MS)
            self.chat_to(p, f"Voce comeu {idef['name']}. Gnam gnam.")
        elif idef.get("tool") == "rope":
            return self.use_rope(p)            # corda não é consumida
        elif idef.get("tool") == "rod":
            return self.use_rod(p, now)        # vara não é consumida
        else:
            return self.chat_to(p, "Nada acontece.")

        item["count"] -= 1                      # consome uma unidade
        if item["count"] <= 0:
            p.inventory[i] = None
        p.send(p.inv_payload())
        p.send(p.stats_payload())

    def _drop_spot(self, p: Player, msg):
        """Valida o tile alvo de um drop/arremesso. Retorna (x, y) ou None."""
        x = int(msg.get("x", p.x))
        y = int(msg.get("y", p.y))
        if max(abs(x - p.x), abs(y - p.y)) > DROP_RANGE:
            self.chat_to(p, "Longe demais para jogar ai.")
            return None
        if not self.world.walkable(x, y, p.z):
            self.chat_to(p, "Nao da para jogar ai.")
            return None
        return x, y

    def h_drop(self, p: Player, msg):
        i = int(msg.get("slot", -1))
        if not 0 <= i < config.INV_SLOTS or p.inventory[i] is None:
            return
        spot = self._drop_spot(p, msg)
        if spot is None:
            return
        # tira a quantidade pedida (divide pilha) ou o objeto inteiro
        dropped = self._take_from_slot(p, i, msg.get("count"))
        dropped["decay"] = now_ms() + config.LOOT_DECAY_S * 1000
        self.world.ground_items.setdefault((spot[0], spot[1], p.z),
                                           []).append(dropped)
        self.broadcast_ground(spot[0], spot[1], p.z)
        self.sync_containers(spot[0], spot[1], p.z)
        p.send(p.inv_payload())
        p.send(p.stats_payload())

    def h_drop_equip(self, p: Player, msg):
        """
        Arrasta um item equipado direto para o chão. A MOCHILA vai com tudo
        que está dentro dela (os itens dos slots extras viram "contents").
        """
        eslot = msg.get("eslot")
        item = p.equipment.get(eslot) if eslot in entities.EQUIP_SLOTS else None
        if item is None:
            return
        spot = self._drop_spot(p, msg)
        if spot is None:
            return
        p.equipment[eslot] = None
        dropped = {"id": item["id"], "count": item["count"],
                   "decay": now_ms() + config.LOOT_DECAY_S * 1000}
        if eslot == "backpack":
            # empacota os itens dos slots extras dentro da mochila dropada
            contents = []
            for i in range(config.BASE_INV_SLOTS, config.INV_SLOTS):
                if p.inventory[i] is not None:
                    contents.append(p.inventory[i])
                    p.inventory[i] = None
            if contents:
                dropped["contents"] = contents
                dropped["name"] = data.item_name(item["id"])
        self.world.ground_items.setdefault((spot[0], spot[1], p.z),
                                           []).append(dropped)
        self.broadcast_ground(spot[0], spot[1], p.z)
        self.sync_containers(spot[0], spot[1], p.z)
        p.send(p.inv_payload())
        p.send(p.stats_payload())

    def h_move_item(self, p: Player, msg):
        """Arrasta um item entre slots da mochila: junta pilhas iguais, divide
        pilha (count) num slot vazio, ou reordena. Sempre fica sem buracos."""
        i, j = int(msg.get("from", -1)), int(msg.get("to", -1))
        active = p.active_slots()
        if not 0 <= i < active or p.inventory[i] is None:
            return
        a = p.inventory[i]
        b = p.inventory[j] if 0 <= j < active else None
        count = msg.get("count")
        stack_a = (data.item(a["id"]).get("stackable") and not a.get("contents"))
        if (b is not None and b is not a and b["id"] == a["id"]
                and stack_a and not b.get("contents")):
            # juntar pilhas iguais (respeita count e o teto da pilha)
            n = self._split_count(a, count)
            mv = min(n, config.STACK_MAX - b["count"])
            b["count"] += mv
            a["count"] -= mv
            if a["count"] <= 0:
                p.inventory[i] = None
        elif stack_a and count is not None and int(count) < a["count"]:
            # dividir a pilha: parte fica, o resto vai pro slot j (ou 1o vazio)
            n = max(1, min(int(count), a["count"]))
            a["count"] -= n
            new = {"id": a["id"], "count": n}
            if 0 <= j < active and p.inventory[j] is None:
                p.inventory[j] = new
            else:
                for k in range(active):
                    if p.inventory[k] is None:
                        p.inventory[k] = new
                        break
        elif 0 <= j < active and i != j:
            p.inventory[i], p.inventory[j] = b, a       # reordena (troca)
        p.send(p.inv_payload())                         # inv_payload compacta

    def h_equip_ground(self, p: Player, msg):
        """Arrasta um item do chão direto para um slot de equipamento."""
        x, y = int(msg.get("x", p.x)), int(msg.get("y", p.y))
        eslot = msg.get("eslot")
        if eslot not in entities.EQUIP_SLOTS:
            return
        if max(abs(x - p.x), abs(y - p.y)) > 1:
            return self.chat_to(p, "Esta longe demais.")
        if p.equipment.get(eslot):
            return self.chat_to(p, "O slot ja esta ocupado.")
        pile = self.world.ground_at(x, y, p.z)
        for it in reversed(pile):
            idef = data.item(it["id"])
            if idef.get("pickable", True) is False:
                continue
            if entities.TYPE_TO_SLOT.get(idef.get("type")) != eslot:
                return self.chat_to(p, "Isso nao equipa nesse slot.")
            if not p.can_carry_weight(entities.Player.item_weight(it)):
                return self.chat_to(p, "Voce nao tem capacidade suficiente (peso).")
            pile.remove(it)
            if not pile:
                self.world.ground_items.pop((x, y, p.z), None)
            equipped = {k: v for k, v in it.items() if k != "decay"}
            p.equipment[eslot] = equipped
            if eslot == "backpack":
                self._try_unpack_backpack(p, equipped)  # mochila volta cheia
            self.broadcast_ground(x, y, p.z)
            self.sync_containers(x, y, p.z)
            p.send(p.inv_payload())
            p.send(p.stats_payload())
            return
        self.chat_to(p, "Nao ha nada para pegar ai.")

    def h_move_ground(self, p: Player, msg):
        """Arrasta um item/corpo do chão; anda até a origem se estiver longe."""
        fx, fy = int(msg.get("fx", p.x)), int(msg.get("fy", p.y))
        tx, ty = int(msg.get("tx", p.x)), int(msg.get("ty", p.y))
        count = msg.get("count")
        self._walk_then(p, fx, fy,
                        lambda: self._do_move_ground(p, fx, fy, tx, ty, count))

    def _do_move_ground(self, p: Player, fx, fy, tx, ty, count=None):
        # destino fora de alcance (andou até a origem): traz para os pés
        if max(abs(tx - p.x), abs(ty - p.y)) > DROP_RANGE \
                or not self.world.walkable(tx, ty, p.z):
            tx, ty = p.x, p.y
        pile = self.world.ground_at(fx, fy, p.z)
        if not pile:
            return self.chat_to(p, "Nao ha nada para mover ai.")
        top = pile[-1]                          # o do topo, corpo incluso
        n = self._split_count(top, count)
        if n < top["count"]:                    # divide a pilha no chão
            top["count"] -= n
            it = {"id": top["id"], "count": n}
        else:
            it = pile.pop()
            if not pile:
                self.world.ground_items.pop((fx, fy, p.z), None)
        self.world.ground_items.setdefault((tx, ty, p.z), []).append(it)
        self.broadcast_ground(fx, fy, p.z)
        self.broadcast_ground(tx, ty, p.z)
        self.sync_containers(fx, fy, p.z)
        self.sync_containers(tx, ty, p.z)

    def h_store(self, p: Player, msg):
        """Guarda um item da mochila DENTRO de um container aberto (corpo/
        mochila no chão). Preserva o item inteiro — mochila dentro de mochila."""
        i = int(msg.get("slot", -1))
        cx, cy = int(msg.get("x", p.x)), int(msg.get("y", p.y))
        if not 0 <= i < p.active_slots() or p.inventory[i] is None:
            return
        if (cx, cy, p.z) not in p.open_containers:
            return
        if max(abs(cx - p.x), abs(cy - p.y)) > 1:
            return self.chat_to(p, "Esta longe demais.")
        corpse = self._top_container(self.world.ground_at(cx, cy, p.z))
        if corpse is None:
            return
        # evita o paradoxo de guardar a mochila DENTRO dela mesma
        if p.inventory[i] is corpse:
            return
        taken = self._take_from_slot(p, i, msg.get("count"))
        self._container_add(corpse, taken)             # empilha iguais
        self.broadcast_ground(cx, cy, p.z)
        self.sync_containers(cx, cy, p.z)
        p.send(p.inv_payload())
        p.send(p.stats_payload())

    # ===================================================== corpos (loot)

    @staticmethod
    def _is_container(it) -> bool:
        """Corpo OU mochila (qualquer item com flag container) é abrível."""
        return "contents" in it or data.item(it["id"]).get("container", False)

    def _top_container(self, pile):
        """Container mais ao topo da pilha (corpo/mochila), ou None.
        Inicializa `contents` vazio se ainda não existir (mochila vazia)."""
        for it in reversed(pile):
            if self._is_container(it):
                if "contents" not in it:
                    it["contents"] = []
                return it
        return None

    # ------------------------------------------------ split de pilhas (count)

    @staticmethod
    def _split_count(item: dict, count) -> int:
        """Quantas unidades mover de `item` dado o pedido `count`. Item não
        empilhável (ou mochila com conteúdo) = sempre inteiro."""
        if (count is not None
                and data.item(item["id"]).get("stackable")
                and not item.get("contents")):
            try:
                return max(1, min(int(count), item["count"]))
            except (TypeError, ValueError):
                return item["count"]
        return item["count"]

    def _take_from_slot(self, p: Player, i: int, count) -> dict:
        """Retira até `count` do slot i (divide stackable; senão item inteiro)."""
        item = p.inventory[i]
        n = self._split_count(item, count)
        if n < item["count"]:
            item["count"] -= n
            return {"id": item["id"], "count": n}
        p.inventory[i] = None
        return {k: v for k, v in item.items() if k != "decay"}

    def _take_from_container(self, corpse: dict, idx: int, count) -> dict:
        """Retira até `count` do item idx de um container (divide/inteiro)."""
        item = corpse["contents"][idx]
        n = self._split_count(item, count)
        if n < item["count"]:
            item["count"] -= n
            return {"id": item["id"], "count": n}
        return corpse["contents"].pop(idx)

    @staticmethod
    def _container_add(corpse: dict, item: dict) -> None:
        """Coloca um item num container, empilhando stackable iguais."""
        if data.item(item["id"]).get("stackable") and not item.get("contents"):
            for s in corpse["contents"]:
                if s["id"] == item["id"] and not s.get("contents") \
                        and s["count"] < config.STACK_MAX:
                    mv = min(config.STACK_MAX - s["count"], item["count"])
                    s["count"] += mv
                    item["count"] -= mv
                    if item["count"] <= 0:
                        return
        corpse["contents"].append({k: v for k, v in item.items()
                                   if k != "decay"})

    def _give_item(self, p: Player, item: dict) -> str:
        """
        Entrega um item INTEIRO ao jogador (preserva `contents` de mochilas).
        Retorna "" em sucesso ou a mensagem de erro.
        """
        if item.get("contents"):                  # mochila cheia: objeto inteiro
            if not p.can_carry_weight(entities.Player.item_weight(item)):
                return "Voce nao tem capacidade suficiente (peso)."
            for i in range(p.active_slots()):
                if p.inventory[i] is None:
                    p.inventory[i] = {k: v for k, v in item.items()
                                      if k != "decay"}
                    return ""
            return "Sem espaco na mochila."
        return self.give(p, item["id"], item["count"])

    def _container_payload(self, x, y, corpse) -> dict:
        # corpos têm "name" próprio; mochilas/itens usam o nome do item
        name = corpse.get("name") or data.item_name(corpse["id"])
        items = [{"id": i["id"], "count": i["count"]} for i in corpse["contents"]]
        # mochila mostra TODOS os slots (capacidade); corpo mostra só o que tem
        cap = data.item(corpse["id"]).get("capacity", 0)
        slots = max(cap, len(items)) if cap else len(items)
        return {"type": "container", "x": x, "y": y, "name": name,
                "slots": slots, "items": items}

    def sync_containers(self, x, y, z):
        """Reenvia (ou fecha) as janelas de quem está com este corpo aberto."""
        corpse = self._top_container(self.world.ground_at(x, y, z))
        for q in self.players.values():
            if (x, y, z) not in q.open_containers:
                continue
            if (corpse is None or q.z != z
                    or max(abs(q.x - x), abs(q.y - y)) > 1):
                q.open_containers.discard((x, y, z))
                q.send({"type": "container_close", "x": x, "y": y})
            else:
                q.send(self._container_payload(x, y, corpse))

    def h_open_container(self, p: Player, msg):
        """Clique num corpo/mochila: anda até lá (se longe) e abre a janela."""
        x, y = int(msg.get("x", p.x)), int(msg.get("y", p.y))
        self._walk_then(p, x, y, lambda: self._do_open(p, x, y))

    def _do_open(self, p: Player, x: int, y: int):
        corpse = self._top_container(self.world.ground_at(x, y, p.z))
        if corpse is None:
            return self.chat_to(p, "Nao ha nada para abrir ai.")
        p.open_containers.add((x, y, p.z))
        p.send(self._container_payload(x, y, corpse))

    def h_loot(self, p: Player, msg):
        """Arrasta um item de dentro do corpo para a mochila."""
        x, y = int(msg.get("x", p.x)), int(msg.get("y", p.y))
        idx = int(msg.get("idx", -1))
        if max(abs(x - p.x), abs(y - p.y)) > 1:
            return self.chat_to(p, "Esta longe demais.")
        corpse = self._top_container(self.world.ground_at(x, y, p.z))
        if corpse is None or not 0 <= idx < len(corpse["contents"]):
            return
        item = corpse["contents"][idx]
        n = self._split_count(item, msg.get("count"))
        # monta o que será entregue (split de pilha ou item inteiro com conteúdo)
        give = {"id": item["id"], "count": n} if n < item["count"] else item
        err = self._give_item(p, give)         # preserva contents (mochila)
        if err:
            return self.chat_to(p, err)
        if n < item["count"]:
            item["count"] -= n
        else:
            corpse["contents"].pop(idx)
        qty = f"{n}x " if n > 1 else ""
        self.chat_to(p, f"Voce pegou {qty}{data.item_name(item['id'])}.")
        p.send(p.inv_payload())
        p.send(p.stats_payload())
        self.sync_containers(x, y, p.z)

    def h_loot_ground(self, p: Player, msg):
        """Arrasta um item de dentro do corpo direto para um tile do chão."""
        cx, cy = int(msg.get("x", p.x)), int(msg.get("y", p.y))
        idx = int(msg.get("idx", -1))
        if max(abs(cx - p.x), abs(cy - p.y)) > 1:
            return self.chat_to(p, "Esta longe demais.")
        tx = int(msg.get("tx", p.x))
        ty = int(msg.get("ty", p.y))
        if max(abs(tx - p.x), abs(ty - p.y)) > DROP_RANGE:
            return self.chat_to(p, "Longe demais para jogar ai.")
        if not self.world.walkable(tx, ty, p.z):
            return self.chat_to(p, "Nao da para jogar ai.")
        corpse = self._top_container(self.world.ground_at(cx, cy, p.z))
        if corpse is None or not 0 <= idx < len(corpse["contents"]):
            return
        ground_item = self._take_from_container(corpse, idx, msg.get("count"))
        ground_item["decay"] = now_ms() + config.LOOT_DECAY_S * 1000
        self.world.ground_items.setdefault((tx, ty, p.z), []).append(ground_item)
        self.broadcast_ground(tx, ty, p.z)
        self.sync_containers(cx, cy, p.z)

    def h_loot_to(self, p: Player, msg):
        """Move um item de um container aberto para OUTRO (split com count)."""
        fx, fy = int(msg.get("x", p.x)), int(msg.get("y", p.y))
        tx, ty = int(msg.get("tx", p.x)), int(msg.get("ty", p.y))
        idx = int(msg.get("idx", -1))
        if (max(abs(fx - p.x), abs(fy - p.y)) > 1
                or max(abs(tx - p.x), abs(ty - p.y)) > 1):
            return self.chat_to(p, "Esta longe demais.")
        src = self._top_container(self.world.ground_at(fx, fy, p.z))
        dst = self._top_container(self.world.ground_at(tx, ty, p.z))
        if src is None or dst is None or src is dst \
                or not 0 <= idx < len(src["contents"]):
            return
        if src["contents"][idx] is dst:        # não meter o container nele mesmo
            return
        taken = self._take_from_container(src, idx, msg.get("count"))
        self._container_add(dst, taken)
        self.broadcast_ground(fx, fy, p.z)
        self.broadcast_ground(tx, ty, p.z)
        self.sync_containers(fx, fy, p.z)
        self.sync_containers(tx, ty, p.z)

    def h_close_container(self, p: Player, msg):
        if "x" in msg:
            p.open_containers.discard((int(msg["x"]), int(msg["y"]), p.z))
        else:
            p.open_containers.clear()

    def h_hotkeys(self, p: Player, msg):
        """Salva a configuração de hotkeys do personagem (máx. 30)."""
        raw = msg.get("map")
        if not isinstance(raw, dict):
            return
        clean = {}
        for key, action in list(raw.items())[:30]:
            if not isinstance(action, dict):
                continue
            entry = {}
            if action.get("type") == "say" and isinstance(action.get("text"), str):
                entry = {"type": "say", "text": action["text"][:60]}
            elif action.get("type") == "use" and isinstance(action.get("item"), int):
                entry = {"type": "use", "item": action["item"]}
            if entry:
                clean[str(key)[:16]] = entry
        p.hotkeys = clean
        self.db.save_character(p.char_id, p)
        self.chat_to(p, "Hotkeys salvas.")

    # ======================================================= corda / pesca

    def use_rope(self, p: Player):
        """Usa a corda num rope spot (no tile ou adjacente) para subir."""
        for dx, dy in ((0, 0), (0, -1), (0, 1), (-1, 0), (1, 0)):
            dest = self.world.ropes.get((p.x + dx, p.y + dy, p.z))
            if dest:
                p.path = []
                self.teleport(p, *dest)
                return self.chat_to(p, "Voce sobe pela corda.")
        self.chat_to(p, "Nao ha onde usar a corda aqui.")

    def use_rod(self, p: Player, now: float):
        """Pesca: precisa de água adjacente. Treina a skill de pesca."""
        if now < p.next_fish:
            return
        water = None
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                gx, gy = p.x + dx, p.y + dy
                if (0 <= gx < self.world.w and 0 <= gy < self.world.h
                        and self.world.ground_id(gx, gy, p.z) == 4):  # água
                    water = (gx, gy)
                    break
            if water:
                break
        if water is None:
            return self.chat_to(p, "Voce precisa estar perto da agua.")
        p.next_fish = now + 1500
        self.fx(water[0], water[1], p.z, kind="splash")
        skill = p.skills["fishing"]["level"]
        self.train_skill(p, "fishing")
        if random.random() < min(0.9, 0.25 + skill * 0.015):
            err = self.give(p, 53, 1)          # peixe
            if err:
                return self.chat_to(p, err)
            p.send(p.inv_payload())
            p.send(p.stats_payload())
            self.chat_to(p, "Voce pescou um peixe!")
        else:
            self.chat_to(p, "Nada mordeu a isca...")

    def h_stance(self, p: Player, msg):
        mode = msg.get("mode")
        if mode in STANCES:
            p.stance = mode
            p.send(p.stats_payload())

    def h_stop(self, p: Player):
        p.path = []
        if p.follow_on:
            p.follow_on = False
            p.send(p.stats_payload())

    def h_follow(self, p: Player, msg):
        """
        Botão Follow: liga o MODO follow (fica armado). Com o modo ligado,
        ao mirar um alvo o personagem já anda atrás dele sozinho.
        """
        p.follow_on = bool(msg.get("on"))
        if not p.follow_on:
            p.path = []
        else:
            self.chat_to(p, "Modo follow ligado: selecione um alvo para "
                            "segui-lo automaticamente.")
        p.send(p.stats_payload())

    def h_logout(self, session, p: Player):
        """Botão Sair: valida locks de combate antes de deslogar."""
        now = now_ms()
        if now < p.pvp_lock_until:
            secs = int((p.pvp_lock_until - now) / 1000) + 1
            return self.chat_to(
                p, f"Em combate PvP: aguarde {secs}s para sair.")
        if now < p.pve_lock_until:
            secs = int((p.pve_lock_until - now) / 1000) + 1
            return self.chat_to(
                p, f"Em combate: aguarde {secs}s para sair.")
        p.send({"type": "logged_out"})
        self.leave_world(p)
        session.player = None
        p.conn.close_now()

    def handle_disconnect(self, p: Player):
        """
        Cliente caiu/fechou. Em combate PvP o personagem PERMANECE no mundo
        (vulnerável!) até o lock expirar — não dá para fugir fechando o jogo.
        """
        if now_ms() < p.pvp_lock_until and p.id in self.players:
            p.lingering = True
            self.chat_all(f"{p.name} fechou o jogo em combate PvP "
                          "e permanece no mundo!")
        else:
            self.leave_world(p)

    def h_pvp(self, p: Player, msg):
        p.pvp = bool(msg.get("on"))
        if not p.pvp and p.target_id in self.players:
            self.clear_target(p)               # desligou: para de atacar player
        self.chat_to(p, "Modo PvP LIGADO. Voce pode atacar e ser atacado "
                        "por jogadores com PvP ligado." if p.pvp
                     else "Modo PvP desligado.")
        p.send(p.stats_payload())

    def h_look(self, p: Player, msg):
        x, y = int(msg.get("x", p.x)), int(msg.get("y", p.y))
        if not self.visible(p, x, y, p.z):
            return
        e = self.by_pos.get((x, y, p.z))
        if isinstance(e, Player):
            voc = formulas.VOCATIONS[e.vocation]["name"]
            text = f"Voce ve {e.name} ({voc}, Level {e.level})."
        elif isinstance(e, Monster):
            text = f"Voce ve um {e.name}."
        elif isinstance(e, Npc):
            text = f"Voce ve {e.name}."
        else:
            pile = self.world.ground_at(x, y, p.z)
            if pile:
                text = self._describe_item(pile[-1])
            else:
                oid = self.world.object_id(x, y, p.z)
                gid = self.world.ground_id(x, y, p.z)
                key = (data.MAP["objectMeta"].get(str(oid), {}).get("sprite")
                       if oid else None) or \
                    data.MAP["groundMeta"].get(str(gid), {}).get("sprite")
                text = f"Voce ve {LOOK_NAMES.get(key, 'o chao')}."
        self.chat_to(p, text, "look")

    @staticmethod
    def _describe_item(it: dict) -> str:
        """Descrição de um item ({'id','count',...}) no estilo do /look."""
        idef = data.item(it["id"])
        name = it.get("name") or idef.get("name", "?")
        qty = f"{it['count']}x " if it.get("count", 1) > 1 else ""
        extra = []
        if idef.get("atk"):
            extra.append(f"Atk:{idef['atk']}")
        if idef.get("def"):
            extra.append(f"Def:{idef['def']}")
        if idef.get("arm"):
            extra.append(f"Arm:{idef['arm']}")
        if idef.get("heal_hp"):
            extra.append(f"+{idef['heal_hp']} vida")
        if idef.get("heal_mp"):
            extra.append(f"+{idef['heal_mp']} mana")
        if idef.get("food_hp"):
            extra.append("comida")
        if "contents" in it:
            extra.append(f"{len(it['contents'])} item(ns) dentro")
        suffix = f" ({', '.join(extra)})" if extra else ""
        return f"Voce ve {qty}{name}{suffix}."

    def h_look_item(self, p: Player, msg):
        """Clique direito num item da mochila/equipamento/corpo aberto."""
        item = None
        if "slot" in msg:
            i = int(msg["slot"])
            if 0 <= i < config.INV_SLOTS:
                item = p.inventory[i]
        elif "eslot" in msg and msg["eslot"] in entities.EQUIP_SLOTS:
            item = p.equipment.get(msg["eslot"])
        elif "cidx" in msg and "cx" in msg:
            key = (int(msg["cx"]), int(msg["cy"]), p.z)
            if key in p.open_containers:
                corpse = self._top_container(
                    self.world.ground_at(key[0], key[1], key[2]))
                if corpse:
                    idx = int(msg["cidx"])
                    if 0 <= idx < len(corpse["contents"]):
                        item = corpse["contents"][idx]
        if item:
            self.chat_to(p, self._describe_item(item), "look")

    def h_trade(self, p: Player, msg, fn):
        err = fn(self, p, str(msg.get("npc", "")), int(msg.get("item", 0)),
                 int(msg.get("count", 1)))
        if err:
            self.chat_to(p, err)
        else:
            p.send(p.inv_payload())
            p.send(p.stats_payload())

    # ------------------------------------------------------------ comandos

    def h_command(self, p: Player, text: str):
        parts = text.split()
        cmd = parts[0].lower()

        if cmd == "/help":
            cmds = "/help /online /save" + (
                " /goto /spawn /item /heal /ghost /itens /bichos"
                " /level /skill" if p.admin else "")
            return self.chat_to(p, f"Comandos: {cmds}")
        if cmd == "/online":
            names = ", ".join(q.name for q in self.players.values())
            return self.chat_to(p, f"Online ({len(self.players)}): {names}")
        if cmd == "/save":
            self.db.save_character(p.char_id, p)
            return self.chat_to(p, "Personagem salvo.")
        if cmd == "/pm" and len(parts) >= 3:
            # nomes podem ter mais de uma palavra: tenta o prefixo mais longo
            other, msg_start = None, 2
            for n in range(min(3, len(parts) - 2), 0, -1):
                cand = " ".join(parts[1:1 + n]).lower()
                other = next((q for q in self.players.values()
                              if q is not p
                              and q.name.lower().startswith(cand)), None)
                if other:
                    msg_start = 1 + n
                    break
            if other is None:
                return self.chat_to(p, "Jogador nao encontrado.")
            text_pm = " ".join(parts[msg_start:])[:200]
            other.send({"type": "chat", "from": p.name, "text": text_pm,
                        "channel": "pm"})
            p.send({"type": "chat", "from": f"-> {other.name}",
                    "text": text_pm, "channel": "pm"})
            return

        if not p.admin:
            return self.chat_to(p, "Comando desconhecido. Use /help.")

        if cmd == "/goto" and len(parts) >= 3:
            try:
                p.path = []
                z = int(parts[3]) if len(parts) > 3 else p.z
                self.teleport(p, int(parts[1]), int(parts[2]), z)
            except ValueError:
                pass
            return
        if cmd == "/spawn" and len(parts) >= 2:
            name = parts[1].lower()
            count = int(parts[2]) if len(parts) > 2 else 1
            if name not in data.MONSTERS:
                return self.chat_to(p, f"Monstro desconhecido: {name}")
            for _ in range(min(count, 10)):
                spot = self.world.find_free_near(p.x, p.y, p.z, self.occupied)
                if spot:
                    m = Monster(name, spot[0], spot[1], z=p.z)
                    self.monsters[m.id] = m
                    self.by_pos[m.pos] = m
                    self.broadcast_spawn(m)
            return
        if cmd == "/item" and len(parts) >= 2:
            try:
                item_id = int(parts[1])
                count = int(parts[2]) if len(parts) > 2 else 1
            except ValueError:
                return
            if item_id not in data.ITEMS:
                return self.chat_to(p, "Item desconhecido.")
            if p.inv_add(item_id, count):
                p.send(p.inv_payload())
                p.send(p.stats_payload())
            return
        if cmd == "/heal":
            p.hp, p.mp = p.maxhp, p.maxmp
            self.fx(p.x, p.y, p.z, kind="heal")
            self.broadcast_hp(p)
            return p.send(p.stats_payload())
        if cmd == "/level" and len(parts) >= 2:
            try:
                lvl = max(1, min(500, int(parts[1])))
            except ValueError:
                return self.chat_to(p, "Uso: /level <numero>")
            p.level = lvl
            p.exp = formulas.exp_for_level(lvl)
            p.maxhp = formulas.max_hp(lvl, p.vocation)
            p.maxmp = formulas.max_mp(lvl, p.vocation)
            p.hp, p.mp = p.maxhp, p.maxmp
            self.broadcast_hp(p)
            p.send(p.stats_payload())
            return self.chat_to(p, f"Level ajustado para {lvl}.")
        if cmd == "/skill":
            if len(parts) < 3 or SKILL_ALIASES.get(parts[1].lower()) is None:
                return self.chat_to(
                    p, "Uso: /skill <punho|clava|espada|machado|escudo|magia> <nivel>")
            name = SKILL_ALIASES[parts[1].lower()]
            try:
                lvl = int(parts[2])
            except ValueError:
                return self.chat_to(p, "Nivel invalido.")
            lvl = max(0 if name == "magic" else 10, min(200, lvl))
            p.skills[name] = {"level": lvl, "tries": 0}
            p.send(p.skills_payload())
            p.send(p.stats_payload())      # defesa pode mudar (escudo)
            return self.chat_to(p, f"{SKILL_LABELS[name]} ajustado para {lvl}.")
        if cmd == "/ghost":
            p.ghost = not p.ghost
            if p.ghost:
                for m in self.monsters.values():
                    if m.target_id == p.id:
                        m.target_id = 0
            return self.chat_to(
                p, "Modo fantasma LIGADO: monstros nao te enxergam."
                if p.ghost else "Modo fantasma desligado.")
        if cmd in ("/itens", "/items"):
            ids = sorted(data.ITEMS)
            for i in range(0, len(ids), 6):
                line = " · ".join(f"{n}={data.item_name(n)}"
                                  for n in ids[i:i + 6])
                self.chat_to(p, line)
            return
        if cmd in ("/bichos", "/monsters"):
            for key in sorted(data.MONSTERS):
                d = data.MONSTERS[key]
                self.chat_to(
                    p, f"{key} ({d['name']}) — hp {d['hp']}, exp {d['exp']}, "
                       f"dano {d['dmg'][0]}-{d['dmg'][1]}")
            return self.chat_to(p, "Use /spawn <nome> [qtd] para invocar.")

        self.chat_to(p, "Comando desconhecido. Use /help.")
