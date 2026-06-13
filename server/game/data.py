"""
data.py — Carrega as definições do jogo (data/*.json) para a memória.

ITEMS    : dict[int, dict]  — definições de itens
MONSTERS : dict[str, dict]  — definições de monstros
NPCS     : dict[str, dict]  — definições de NPCs
MAP      : dict             — mapa completo (camadas + metadados + spawns)
"""
import json
import os

import config


def _load(name: str):
    with open(os.path.join(config.DATA_DIR, name), encoding="utf-8") as f:
        data = json.load(f)
    data.pop("_comment", None)
    return data


ITEMS = {int(k): v for k, v in _load("items.json").items()}
MONSTERS = _load("monsters.json")
NPCS = _load("npcs.json")
MAP = _load("map.json")


def item(item_id: int) -> dict:
    """Definição de um item (dict vazio se id desconhecido)."""
    return ITEMS.get(item_id, {})


def item_name(item_id: int) -> str:
    return item(item_id).get("name", f"item #{item_id}")
