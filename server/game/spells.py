"""
spells.py — Sistema de magias por encantamento falado (estilo Tibia).

O jogador "fala" as palavras mágicas no chat; se forem uma magia válida e
os requisitos baterem (vocação, nível, mana, cooldown), o efeito acontece.
A fala é sempre ecoada no chat local — como no Tibia clássico.

Toda conjuração treina o MAGIC LEVEL (mana gasta = "tries"), e os efeitos
escalam com ele.

| Palavras    | Vocações       | Nível | Mana | Efeito                          |
|-------------|----------------|-------|------|---------------------------------|
| exura       | todas          | 1     | 25   | cura leve                       |
| utani hur   | todas          | 3     | 40   | haste por 20s                   |
| exori       | cavaleiro      | 8     | 30   | golpe nos monstros adjacentes   |
| exori con   | paladino       | 8     | 25   | tiro à distância no alvo atual  |
| exevo flam  | feiticeiro     | 8     | 60   | onda de fogo à frente           |
| exura gran  | druida         | 9     | 70   | cura forte                      |
"""
import random

from game import formulas
from game.entities import DIRS, now_ms

SPELL_COOLDOWN_MS = 1000   # cooldown global entre magias


def _ml(p) -> int:
    return p.skills["magic"]["level"]


def _exura(game, p):
    heal = p.level + _ml(p) * 4 + random.randint(5, 15)
    p.hp = min(p.maxhp, p.hp + heal)
    game.fx(p.x, p.y, p.z, kind="heal", text=f"+{heal}", color="#5e5")
    game.broadcast_hp(p)


def _exura_gran(game, p):
    heal = p.level * 2 + _ml(p) * 8 + random.randint(20, 40)
    p.hp = min(p.maxhp, p.hp + heal)
    game.fx(p.x, p.y, p.z, kind="heal", text=f"+{heal}", color="#5e5")
    game.broadcast_hp(p)


def _hit_monster(game, p, m, dmg, kind="blood"):
    m.hp = max(0, m.hp - dmg)
    game.fx(m.x, m.y, m.z, kind=kind, text=f"-{dmg}", color="#e44")
    game.broadcast_hp(m)
    if m.hp <= 0:
        game.kill_monster(m, p)


def _exori(game, p):
    """Golpe físico em todos os monstros nos 8 tiles ao redor (cavaleiro)."""
    hit_any = False
    for m in list(game.monsters.values()):
        if m.z == p.z and game.dist(p, m) == 1:
            hit_any = True
            sk = p.skills[p.weapon_class()]["level"]
            dmg = random.randint(p.level, p.level * 2 + sk * 2)
            _hit_monster(game, p, m, dmg)
    if not hit_any:
        game.fx(p.x, p.y, p.z, kind="poff")


def _exori_con(game, p):
    """Tiro etéreo à distância no alvo atual (paladino), alcance 5."""
    m = game.monsters.get(p.target_id)
    if m is None or m.z != p.z or game.dist(p, m) > 5:
        game.chat_to(p, "Selecione um alvo a ate 5 tiles.")
        game.fx(p.x, p.y, p.z, kind="poff")
        return False                       # não gasta mana
    dmg = random.randint(p.level, p.level * 2 + _ml(p) * 3 + 8)
    _hit_monster(game, p, m, dmg)
    return True


def _exevo_flam(game, p):
    """Onda de fogo (feiticeiro): cone 3x3 na direção em que olha."""
    dx, dy = DIRS[p.dir]
    tiles = set()
    for dist in (1, 2, 3):
        cx, cy = p.x + dx * dist, p.y + dy * dist
        spread = dist - 1
        for s in range(-spread, spread + 1):
            tiles.add((cx + (dy != 0) * s, cy + (dx != 0) * s))
    hit_any = False
    for (tx, ty) in tiles:
        game.fx(tx, ty, p.z, kind="fire")
    for m in list(game.monsters.values()):
        if m.z == p.z and (m.x, m.y) in tiles:
            hit_any = True
            dmg = random.randint(_ml(p) * 2, p.level + _ml(p) * 6 + 10)
            _hit_monster(game, p, m, dmg, kind="fire")
    if not hit_any:
        game.fx(p.x, p.y, p.z, kind="poff")


def _utani_hur(game, p):
    p.haste_bonus = 60
    p.haste_until = now_ms() + 20000
    game.fx(p.x, p.y, p.z, kind="magic")
    p.send(p.stats_payload())


SPELLS = {
    "exura":      {"level": 1, "mana": 25, "fn": _exura,
                   "voc": ("knight", "paladin", "sorcerer", "druid")},
    "utani hur":  {"level": 3, "mana": 40, "fn": _utani_hur,
                   "voc": ("knight", "paladin", "sorcerer", "druid")},
    "exori":      {"level": 8, "mana": 30, "fn": _exori, "voc": ("knight",)},
    "exori con":  {"level": 8, "mana": 25, "fn": _exori_con, "voc": ("paladin",)},
    "exevo flam": {"level": 8, "mana": 60, "fn": _exevo_flam, "voc": ("sorcerer",)},
    "exura gran": {"level": 9, "mana": 70, "fn": _exura_gran, "voc": ("druid",)},
}


def try_cast(game, p, text: str) -> bool:
    """
    Tenta interpretar a fala como magia. Retorna True se ERA uma magia
    (mesmo que a conjuração tenha falhado por requisito).
    """
    words = " ".join(text.lower().split())
    spell = SPELLS.get(words)
    if spell is None:
        return False

    now = now_ms()
    if now < p.next_spell:
        return True                            # em cooldown: só ecoa a fala
    if p.vocation not in spell["voc"]:
        game.chat_to(p, "Sua vocacao nao conhece essa magia.")
        return True
    if p.level < spell["level"]:
        game.chat_to(p, f"Voce precisa do nivel {spell['level']} para conjurar.")
        return True
    if p.mp < spell["mana"]:
        game.chat_to(p, "Voce nao tem mana suficiente.")
        game.fx(p.x, p.y, p.z, kind="poff")
        return True

    result = spell["fn"](game, p)
    if result is False:                        # ex.: exori con sem alvo
        return True
    p.mp -= spell["mana"]
    p.next_spell = now + SPELL_COOLDOWN_MS
    game.train_skill(p, "magic", spell["mana"])
    p.send(p.stats_payload())
    return True
