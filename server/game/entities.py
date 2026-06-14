"""
entities.py — Criaturas do mundo: jogadores, monstros e NPCs.

Toda criatura ocupa exatamente um tile e bloqueia a passagem.
Timestamps (next_move, next_attack...) são em ms de time.monotonic().
"""
import json
import time

import config
from game import data, formulas

_next_id = 0


def new_id() -> int:
    global _next_id
    _next_id += 1
    return _next_id


def now_ms() -> float:
    return time.monotonic() * 1000.0


DIRS = {
    "n": (0, -1), "s": (0, 1), "e": (1, 0), "w": (-1, 0),
    # diagonais (passo mais lento, como no Tibia)
    "ne": (1, -1), "nw": (-1, -1), "se": (1, 1), "sw": (-1, 1),
}
CARDINALS = ("n", "s", "e", "w")

# Slots de equipamento (estilo Tibia clássico). Os nomes internos antigos
# (weapon/shield/helmet) são mantidos por compatibilidade com saves;
# o cliente exibe Right Hand / Left Hand / Head etc.
EQUIP_SLOTS = ("helmet", "necklace", "backpack", "armor", "weapon",
               "shield", "legs", "boots", "ring", "ammo")

# tipo de item -> slot em que ele equipa
TYPE_TO_SLOT = {
    "weapon": "weapon", "shield": "shield", "helmet": "helmet",
    "armor": "armor", "legs": "legs", "boots": "boots",
    "necklace": "necklace", "ring": "ring", "ammo": "ammo",
    "backpack": "backpack",
}


class Creature:
    kind = "creature"

    def __init__(self, name: str, x: int, y: int, sprite: str, maxhp: int,
                 z: int = 0):
        self.id = new_id()
        self.name = name
        self.x = x
        self.y = y
        self.z = z                  # andar (0 = superfície, 1 = subsolo)
        self.dir = "s"
        self.sprite = sprite
        self.hp = maxhp
        self.maxhp = maxhp
        self.next_move = 0.0
        self.next_attack = 0.0

    @property
    def pos(self):
        return (self.x, self.y, self.z)

    def to_client(self) -> dict:
        """Representação enviada ao cliente no espawn."""
        return {
            "id": self.id, "kind": self.kind, "name": self.name,
            "x": self.x, "y": self.y, "z": self.z, "dir": self.dir,
            "sprite": self.sprite, "hp": self.hp, "maxhp": self.maxhp,
        }


class Player(Creature):
    kind = "player"

    def __init__(self, conn, account_id: int, row, admin: bool = False):
        keys = row.keys()
        z = row["z"] if "z" in keys else 0
        super().__init__(row["name"], row["x"], row["y"], "player",
                         row["maxhp"], z)
        self.conn = conn
        self.account_id = account_id
        self.char_id = row["id"]
        self.admin = admin                    # flag is_admin da conta
        self.level = row["level"]
        self.exp = row["exp"]
        self.hp = row["hp"]
        self.mp = row["mp"]
        self.maxmp = row["maxmp"]
        self.deaths = row["deaths"]
        self.vocation = (row["vocation"] if "vocation" in keys
                         and row["vocation"] else formulas.DEFAULT_VOCATION)
        # skills: completa com defaults o que faltar (saves antigos)
        self.skills = formulas.default_skills()
        if "skills" in keys and row["skills"]:
            for k, v in json.loads(row["skills"]).items():
                if k in self.skills:
                    self.skills[k] = v

        # inventário: lista fixa de slots (None ou {"id": int, "count": int})
        inv = json.loads(row["inventory"])
        inv = (inv + [None] * config.INV_SLOTS)[: config.INV_SLOTS]
        self.inventory = inv
        self.equipment = {s: None for s in EQUIP_SLOTS}
        self.equipment.update(json.loads(row["equipment"]))
        # migração: personagens antigos ganham uma mochila comum equipada
        if self.equipment.get("backpack") is None:
            self.equipment["backpack"] = {"id": config.DEFAULT_BACKPACK_ID,
                                          "count": 1}
        self.hotkeys = {}
        if "hotkeys" in row.keys() and row["hotkeys"]:
            try:
                self.hotkeys = json.loads(row["hotkeys"])
            except json.JSONDecodeError:
                pass

        self.target_id = 0                    # monstro sendo atacado (0 = nenhum)
        self.known = set()                    # ids de entidades que o cliente conhece
        self.dead = False
        self.fed_until = 0.0                  # "barriga cheia" acelera a regeneração
        self.next_hp_regen = 0.0
        self.next_mp_regen = 0.0
        self.next_spell = 0.0                 # cooldown global de magias
        self.haste_bonus = 0                  # bônus de velocidade (utani hur)
        self.haste_until = 0.0
        self.path = []                        # autowalk (clique para andar)
        self.path_target = None
        self.path_stuck = 0                   # ticks esperando criatura sair
        self.pending_stairs = None            # escada clicada (usa ao chegar)
        self.stance = "balanced"              # attack | balanced | defense
        self.pvp = False                      # PvP opt-in (ícone no cliente)
        self.open_containers = set()          # tiles (x,y,z) de corpos abertos
        self.ghost = False                    # /ghost: monstros não enxergam
        self.next_fish = 0.0                  # cooldown da pesca
        self.follow_on = False                # seguir o alvo automaticamente
        self.pve_lock_until = 0.0             # lutou com monstro: sem logout
        self.pvp_lock_until = 0.0             # agrediu player: sem logout/PZ
        self.skull_until = 0.0                # caveira visível (agressor PvP)
        self.lingering = False                # fechou o cliente em combate PvP
        self.pending = None                   # ação a executar ao chegar perto
        self.next_push = 0.0                  # cooldown do jogador entre empurrões

    # ----------------------------------------------------------- atributos

    def speed(self) -> int:
        bonus = self.haste_bonus if now_ms() < self.haste_until else 0
        return formulas.speed(self.level) + bonus

    def step_ms(self) -> int:
        return max(120, int(1000 * config.GROUND_FRICTION / self.speed()))

    def weapon_def(self) -> dict:
        """Definição da arma equipada ({} se desarmado). A arma pode estar em
        QUALQUER mão (slot weapon OU shield) — escudo e arma trocam de mão."""
        for slot in ("weapon", "shield"):
            it = self.equipment.get(slot)
            if it and data.item(it["id"]).get("type") == "weapon":
                return data.item(it["id"])
        return {}

    def weapon_atk(self) -> int:
        return self.weapon_def().get("atk", 5)                # 5 = soco

    def weapon_class(self) -> str:
        """Skill que a arma equipada treina/usa (fist se desarmado)."""
        return self.weapon_def().get("wclass", "fist")

    def defense(self) -> int:
        """Defesa total: armaduras + escudo escalado pela skill de escudo.
        O escudo pode estar em QUALQUER mão (slot weapon OU shield)."""
        total = 0
        for slot in ("helmet", "armor", "legs", "boots", "necklace", "ring"):
            it = self.equipment.get(slot)
            if it:
                total += data.item(it["id"]).get("arm", 0)
        for slot in ("weapon", "shield"):
            it = self.equipment.get(slot)
            if it and data.item(it["id"]).get("type") == "shield":
                sk = self.skills["shield"]["level"]
                total += data.item(it["id"]).get("def", 0) * sk // 20
        return total

    def has_ring_effect(self, effect: str) -> bool:
        """O anel/amuleto equipado tem certo efeito passivo?"""
        for slot in ("ring", "necklace"):
            it = self.equipment.get(slot)
            if it and data.item(it["id"]).get("effect") == effect:
                return True
        return False

    def is_fed(self, now: float) -> bool:
        return now < self.fed_until or self.has_ring_effect("fed")

    # ----------------------------------------------------- capacity (peso)

    def capacity(self) -> int:
        """CAP máxima em oz: base + level * ganho."""
        return config.CAP_BASE + self.level * config.CAP_PER_LEVEL

    @staticmethod
    def item_weight(it: dict) -> float:
        """Peso de um item, incluindo o que estiver DENTRO dele (mochilas)."""
        total = data.item(it["id"]).get("weight", 1.0) * it.get("count", 1)
        for inner in it.get("contents", []):
            total += Player.item_weight(inner)
        return total

    def carried_weight(self) -> float:
        """Peso total carregado (inventário + equipamento)."""
        total = 0.0
        for s in self.inventory:
            if s:
                total += self.item_weight(s)
        for it in self.equipment.values():
            if it:
                total += self.item_weight(it)
        return total

    def can_carry(self, item_id: int, count: int = 1) -> bool:
        w = data.item(item_id).get("weight", 1.0) * count
        return self.carried_weight() + w <= self.capacity()

    def can_carry_weight(self, w: float) -> bool:
        return self.carried_weight() + w <= self.capacity()

    def active_slots(self) -> int:
        """Slots utilizáveis: bolsos + capacidade da mochila equipada."""
        bp = self.equipment.get("backpack")
        extra = data.item(bp["id"]).get("capacity", 0) if bp else 0
        return min(config.INV_SLOTS, config.BASE_INV_SLOTS + extra)

    def skills_payload(self) -> dict:
        out = {}
        for name, sk in self.skills.items():
            needed = formulas.skill_tries_needed(name, sk["level"], self.vocation)
            out[name] = {"level": sk["level"],
                         "pct": min(99, int(100 * sk["tries"] / max(1, needed)))}
        return {"type": "skills", "skills": out}

    # ---------------------------------------------------------- inventário

    def inv_count(self, item_id: int) -> int:
        # mochilas com conteúdo não contam (não podem ser vendidas/gastas)
        return sum(s["count"] for s in self.inventory
                   if s and s["id"] == item_id and not s.get("contents"))

    def inv_add(self, item_id: int, count: int = 1) -> bool:
        """
        Adiciona itens (empilhando se possível) nos slots ATIVOS.
        Retorna False se não coube; nunca adiciona parcialmente.
        (O peso é checado pelos chamadores via can_carry / Game.give.)
        """
        active = self.active_slots()
        stackable = data.item(item_id).get("stackable", False)
        # 1) verifica espaço
        room = 0
        for i in range(active):
            s = self.inventory[i]
            if s is None:
                room += config.STACK_MAX if stackable else 1
            elif stackable and s["id"] == item_id:
                room += config.STACK_MAX - s["count"]
        if room < count:
            return False
        # 2) aplica
        remaining = count
        if stackable:
            for i in range(active):
                if remaining <= 0:
                    break
                s = self.inventory[i]
                if s and s["id"] == item_id and s["count"] < config.STACK_MAX:
                    add = min(remaining, config.STACK_MAX - s["count"])
                    s["count"] += add
                    remaining -= add
        for i in range(active):
            if remaining <= 0:
                break
            if self.inventory[i] is None:
                add = min(remaining, config.STACK_MAX) if stackable else 1
                self.inventory[i] = {"id": item_id, "count": add}
                remaining -= add
        return True

    def compact_inv(self) -> None:
        """Empacota os itens nos PRIMEIROS slots, sem buracos (estilo Tibia).
        Mantém a ordem; preenche o resto com None. Mexe na lista in-place para
        que os índices vistos pelo cliente (via inv_payload) batam com o servidor.
        """
        items = [s for s in self.inventory if s is not None]
        self.inventory[:] = items + [None] * (config.INV_SLOTS - len(items))

    def inv_remove(self, item_id: int, count: int = 1) -> bool:
        """Remove `count` unidades. Retorna False (sem alterar) se não houver."""
        if self.inv_count(item_id) < count:
            return False
        remaining = count
        for i, s in enumerate(self.inventory):
            if remaining <= 0:
                break
            if s and s["id"] == item_id and not s.get("contents"):
                take = min(remaining, s["count"])
                s["count"] -= take
                remaining -= take
                if s["count"] <= 0:
                    self.inventory[i] = None
        return True

    # ------------------------------------------------------------ mensagens

    def send(self, obj) -> None:
        self.conn.send_json(obj)

    def stats_payload(self) -> dict:
        return {
            "type": "stats",
            "hp": self.hp, "maxhp": self.maxhp,
            "mp": self.mp, "maxmp": self.maxmp,
            "level": self.level, "exp": self.exp,
            "expBase": formulas.exp_for_level(self.level),
            "expNext": formulas.exp_for_level(self.level + 1),
            "speed": self.speed(),
            "gold": self.inv_count(1),
            "fed": self.is_fed(now_ms()),
            "atk": self.weapon_atk(),
            "def": self.defense(),
            "vocation": formulas.VOCATIONS[self.vocation]["name"],
            "stance": self.stance,
            "pvp": self.pvp,
            "follow": self.follow_on,
            "cap": round(self.carried_weight(), 1),
            "maxcap": self.capacity(),
        }

    def to_client(self) -> dict:
        d = super().to_client()
        d["skull"] = now_ms() < self.skull_until
        return d

    def inv_payload(self) -> dict:
        self.compact_inv()                         # sempre sem buracos
        return {"type": "inv", "slots": self.inventory,
                "equip": self.equipment, "active": self.active_slots()}


class Monster(Creature):
    kind = "monster"

    def __init__(self, def_name: str, x: int, y: int, zone=None, z: int = 0):
        d = data.MONSTERS[def_name]
        super().__init__(d["name"], x, y, d["sprite"], d["hp"], z)
        self.def_name = def_name
        self.exp = d["exp"]
        self.dmg_min, self.dmg_max = d["dmg"]
        self.armor = d.get("armor", 0)
        self.step_dur = d.get("stepMs", 500)
        self.atk_ms = d.get("atkMs", 2000)
        self.aggro = d.get("aggro", 6)
        self.loot = d.get("loot", [])
        self.zone = zone                      # zona de spawn de origem (ou None)
        self.home = (x, y)
        self.target_id = 0
        self.follow_path = []                 # rota BFS p/ contornar paredes
        self.path_stuck = 0                   # ticks esperando tile da rota
        # empurrável (estilo Tibia): por enquanto TODOS são; no futuro dá pra
        # marcar bosses/criaturas fixas com "pushable": false no monsters.json
        self.pushable = d.get("pushable", True)
        self.push_until = 0.0                 # enquanto conclui o empurrão atual
        # puxável por corda (estilo Tibia): hoje TODOS são; no futuro marca-se
        # criaturas específicas com "ropeable": false no monsters.json
        self.ropeable = d.get("ropeable", True)


class Npc(Creature):
    kind = "npc"

    def __init__(self, name: str, ndef: dict):
        x, y = ndef["pos"]
        super().__init__(name, x, y, ndef["sprite"], ndef.get("hp", 100))
        self.ndef = ndef
        # config individual (tudo opcional em npcs.json, com defaults sensatos)
        self.home = (x, y)
        self.walks = ndef.get("walks", True)        # anda ocasionalmente?
        self.walk_radius = ndef.get("walkRadius", 2)  # raio máx. ao redor do home
        self.walk_min = ndef.get("walkMin", 4000)   # intervalo mín. entre passos
        self.walk_max = ndef.get("walkMax", 9000)   # intervalo máx.
        self.invulnerable = ndef.get("invulnerable", True)
        self.attackable = ndef.get("attackable", False)
