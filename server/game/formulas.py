"""
formulas.py — Fórmulas de progressão e combate.

Mantém a curva de experiência do Tibia clássico e aproximações simples
(e documentadas) para dano/defesa, já que não há skills de arma no MVP.
"""
import random

import config


def exp_for_level(level: int) -> int:
    """Experiência total necessária para atingir `level` (curva do Tibia)."""
    return int((50 * (level ** 3 - 6 * level ** 2 + 17 * level - 12)) / 3)


# ------------------------------------------------------------------ vocações
# hp/mp = ganho por nível (todas começam com 150 hp / 50 mp no nível 1).
# melee/magic/shield = multiplicador de "tries" p/ subir a skill (menor = mais rápido).
VOCATIONS = {
    "knight":   {"name": "Cavaleiro",  "hp": 15, "mp": 5,
                 "melee": 1.0, "magic": 3.0, "shield": 1.0, "distance": 1.4},
    "paladin":  {"name": "Paladino",   "hp": 10, "mp": 15,
                 "melee": 1.4, "magic": 1.5, "shield": 1.2, "distance": 1.0},
    "sorcerer": {"name": "Feiticeiro", "hp": 5,  "mp": 30,
                 "melee": 2.0, "magic": 1.0, "shield": 1.5, "distance": 2.0},
    "druid":    {"name": "Druida",     "hp": 5,  "mp": 30,
                 "melee": 2.0, "magic": 1.0, "shield": 1.5, "distance": 2.0},
}
DEFAULT_VOCATION = "knight"


def max_hp(level: int, vocation: str = DEFAULT_VOCATION) -> int:
    gain = VOCATIONS.get(vocation, VOCATIONS[DEFAULT_VOCATION])["hp"]
    return (150 - gain) + gain * level      # nível 1 = 150 para todas


def max_mp(level: int, vocation: str = DEFAULT_VOCATION) -> int:
    gain = VOCATIONS.get(vocation, VOCATIONS[DEFAULT_VOCATION])["mp"]
    return (50 - gain) + gain * level       # nível 1 = 50 para todas


# ------------------------------------------------------------------- skills
SKILL_NAMES = ("fist", "club", "sword", "axe", "distance", "shield",
               "fishing", "magic")


def default_skills() -> dict:
    return {n: {"level": 0 if n == "magic" else 10, "tries": 0}
            for n in SKILL_NAMES}


def skill_tries_needed(name: str, level: int, vocation: str) -> int:
    """Quantos usos (golpes / bloqueios / mana gasta) para o próximo nível."""
    voc = VOCATIONS.get(vocation, VOCATIONS[DEFAULT_VOCATION])
    if name == "magic":
        return int(160 * (1.4 ** level) * voc["magic"])
    if name == "fishing":
        factor = 1.0                      # pesca treina igual para todos
    elif name == "shield":
        factor = voc["shield"]
    elif name == "distance":
        factor = voc["distance"]
    else:
        factor = voc["melee"]
    return int(30 * (1.1 ** (level - 10)) * factor)


def speed(level: int) -> int:
    return 218 + 2 * level          # level 1 = 220 (igual ao Tibia)


def step_ms(level: int) -> int:
    """Duração de um passo do jogador, em ms."""
    return max(120, int(1000 * config.GROUND_FRICTION / speed(level)))


def player_melee_roll(skill_level: int, weapon_atk: int, level: int) -> int:
    """Dano bruto de um golpe: dominado pela skill da arma, nível ajuda pouco."""
    max_dmg = int(weapon_atk * (skill_level + 10) / 20 + level / 5) + 2
    return random.randint(0, max_dmg)


def monster_melee_roll(dmg_min: int, dmg_max: int) -> int:
    return random.randint(dmg_min, dmg_max)


def mitigate(damage: int, defense: int) -> int:
    """Reduz o dano conforme a defesa total (armadura + escudo)."""
    if defense <= 0:
        return max(0, damage)
    reduction = random.randint(defense // 3, (defense * 2) // 3 + 1)
    return max(0, damage - reduction)
