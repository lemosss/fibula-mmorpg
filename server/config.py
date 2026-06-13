"""Configurações globais do servidor Fibula."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
CLIENT_DIR = os.path.join(ROOT, "client")
DB_PATH = os.path.join(DATA_DIR, "fibula.db")

HOST = "0.0.0.0"        # 0.0.0.0 permite jogar em LAN; use 127.0.0.1 p/ só local
PORT = 7777             # HTTP (cliente) e WebSocket (jogo) na mesma porta

TICK_MS = 100           # passo da simulação (IA, decay, regen)
AUTOSAVE_S = 60         # salva todos os personagens online a cada N segundos

# Janela de visão (meia-extensão): cliente desenha 15x11, enviamos uma margem
VIEW_X = 9
VIEW_Y = 7

# Aggro: o monstro persegue qualquer jogador dentro desta área retangular
# (≈ a tela do jogador + 2 SQM), além do raio "aggro" próprio dele
AGGRO_X = 9
AGGRO_Y = 7

# Movimento
GROUND_FRICTION = 90    # step_ms = 1000 * FRICTION / speed

# Combate
ATTACK_COOLDOWN_MS = 2000   # estilo Tibia 7.x: um golpe a cada 2s
DEATH_EXP_LOSS = 0.10       # perde 10% da exp ao morrer (sem perder level no MVP)

# Locks de combate (estilo Tibia)
PVE_LOCK_S = 10             # lutou com monstro: sem logout por N s (PZ liberada)
PVP_LOCK_S = 60             # agrediu jogador: sem logout E sem entrar na PZ
SKULL_S = 120               # caveira visível ao agredir jogador (renova a cada golpe)

# Respawn: aviso visual (bolinha azul pulsante) N ms antes do monstro nascer
SPAWN_WARN_MS = 5000

# Itens no chão
CORPSE_ITEM_ID = 90
CORPSE_DECAY_S = 120        # o loot fica DENTRO do corpo; some junto com ele
LOOT_DECAY_S = 300
STACK_MAX = 100             # máximo por pilha (moedas etc.)

# Inventário: como no Tibia, SEM mochila não há slot nenhum —
# os slots vêm todos da mochila equipada (capacity do item)
INV_SLOTS = 32              # tamanho máximo de armazenamento (storage)
BASE_INV_SLOTS = 0          # sem mochila = sem slots
DEFAULT_BACKPACK_ID = 70    # mochila comum (dada a personagens antigos)

# Capacity (peso): CAP = base + level * ganho  (em oz)
CAP_BASE = 350
CAP_PER_LEVEL = 10

# Regeneração (ms por ponto). Comido (fed) regenera muito mais rápido.
REGEN_HP_MS_FED = 1500
REGEN_MP_MS_FED = 1000
REGEN_HP_MS_BASE = 6000
REGEN_MP_MS_BASE = 4000
FOOD_MS_PER_HP = 12000      # cada ponto de food_hp = 12s de "barriga cheia"
FOOD_MAX_MS = 600000        # barriga cheia no máximo 10 min

MOTD = "Bem-vindo a Fibula! Diga 'oi' aos NPCs da cidade. Bom jogo!"
