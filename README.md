# Fibula — MMORPG 2D inspirado em Tibia

Um MMORPG 2D completo, com arquitetura cliente-servidor, feito **do zero e sem
nenhuma dependência externa**: o servidor é Python puro (stdlib) e o cliente
roda em qualquer navegador moderno.

> *Fibula (fíbula) é o osso vizinho da tíbia — e também uma ilha do Tibia original.* 🦴

![stack](https://img.shields.io/badge/server-Python%203.11%20(stdlib)-blue)
![stack](https://img.shields.io/badge/client-HTML5%20Canvas%20%2B%20JS-orange)
![stack](https://img.shields.io/badge/db-SQLite-green)

---

## Como jogar

**Requisitos:** Python 3.10+ no PATH. Só isso.

```bat
start.bat
```

Depois abra **http://localhost:7777** no navegador. Crie uma conta (a
**primeira conta criada no servidor vira administrador**) e jogue.

Para jogar em LAN, outros computadores acessam `http://SEU_IP:7777`.

### Controles

| Ação | Como |
|---|---|
| Andar | WASD/setas, ou **clique no chão / no minimapa / no mapa expandido** |
| Diagonal | **Q/E/Z/C** ou segure duas teclas (ex.: W+D) — passo diagonal é mais lento |
| Parar | **ESC** cancela o autowalk e o ataque |
| Minimapa | setas ◀▲▼▶ movem a visão, ◎ volta a seguir você, ⛶ expande o mapa inteiro |
| Atacar monstro | clique nele (clique de novo para parar) |
| Postura | botões ⚔ (full ataque) ⚖ (balanceado) 🛡 (full defesa) no painel |
| PvP | botão **PvP** — só ataca/é atacado por jogadores com PvP ligado, **fora da cidade** (dentro da zona de proteção o jogo avisa e bloqueia) |
| Falar / NPC | Enter abre o chat; diga `oi` perto de um NPC |
| Olhar | clique direito em qualquer tile |
| **Saquear (loot)** | clique no **corpo** do monstro → abre a janela → **arraste para a mochila** (ou duplo clique). Vários corpos podem ficar abertos ao mesmo tempo |
| Pegar item solto | clique no item (adjacente), tecla **G**, ou arraste para a mochila |
| Mover itens | **arraste**: mochila ↔ mochila, mochila ↔ equipamento, mochila/chão → chão (corpos também podem ser arrastados) |
| Olhar item | **clique direito** no item (mochila, equipamento ou corpo aberto) |
| Usar/equipar item | duplo clique no item da mochila |
| Comércio | diga `comerciar` perto do mercador Tobias (a aba Vender mostra tudo que ele compra, com quantidade e itens equipados bloqueados) |
| Cavernas | **descer**: pise na escada/buraco (automático) · **subir**: clique na escada · **corda** no rope spot: sobe |
| Hotkeys | botão **Hotkeys** na sidebar: F1–F12 e 0–9 para magias/falas ou usar itens (salvas no personagem) |
| Janelas | botões **Skills** / **Hotkeys** / **?** abrem janelas flutuantes; chat tem abas (Default, Server Log, Loot, NPC, PM) |
| PM | `/pm <nome> <mensagem>` — chega na aba PM |

### Equipamento (10 slots, estilo Tibia)

Head · Necklace · Backpack · Armor · Right Hand (arma) · Left Hand (escudo) ·
Legs · Boots · Ring · Ammo.
- **Sem mochila não há slot nenhum** (como no Tibia): todos os slots vêm da
  mochila equipada — comum = 24, **mochila grande** (drop do Lorde Dragão) = 32.
- **Clique no ícone da mochila** equipada para abrir/fechar a janela dela.
- **Dropar a mochila leva tudo que está dentro** — no chão ela vira um
  container (clique para abrir, como um corpo); arraste de volta para o slot
  e o conteúdo retorna. Para trocar de mochila, equipe a nova por cima.
- As **janelas de loot** (corpos/mochilas abertos) empilham na sidebar,
  abaixo da mochila, como no Tibia clássico.
- **Anel da vida**: regenera como se estivesse sempre alimentado.
- **Amuleto de proteção**: +2 de armadura.

### Capacity (CAP)

Todo item tem peso (oz). `CAP = 350 + level × 10`. Sem capacidade não se
carrega mais nada — a sidebar mostra a Cap restante.

### Combate à distância

- **Arco** (alcance 6) usa **flechas** equipadas no slot Ammo — uma por tiro.
- **Lança** (alcance 3) é arremessada e **cai no tile do alvo** (dá para recolher).
- Ambos treinam a skill *Distance Fighting* (paladino treina mais rápido).

### Pesca

Compre uma **vara de pesca** no Tobias e use-a perto da água (lago a oeste).
Treina a skill *Fishing* — quanto maior, mais peixes.

### Vocações (escolhidas ao criar o personagem)

| Vocação | HP/MP por nível | Estilo | Magia exclusiva |
|---|---|---|---|
| Cavaleiro | +15 / +5 | corpo a corpo, treina armas rápido | `exori` (golpe em área) |
| Paladino | +10 / +15 | equilibrado | `exori con` (tiro à distância) |
| Feiticeiro | +5 / +30 | mago ofensivo | `exevo flam` (onda de fogo) |
| Druida | +5 / +30 | mago curandeiro | `exura gran` (cura forte) |

Magias de todos: `exura` (cura leve, nível 1) e `utani hur` (haste, nível 3).
As exclusivas pedem nível 8+ (9 para `exura gran`). Conjurar gasta mana e
treina o **magic level**, que aumenta o efeito das magias.

### Habilidades (skills)

Treinam **pelo uso**, como no Tibia: golpear com espada sobe *Espada*,
apanhar com escudo equipado sobe *Escudo*, gastar mana sobe *Magia*.
O dano corpo a corpo depende da skill da arma; a velocidade de treino
depende da vocação (cavaleiro treina armas rápido, magos treinam magia rápido).

### O subsolo

Duas entradas de caverna: nas **colinas dos trolls** e no **cemitério**
(a cripta). Lá embaixo é escuro — você enxerga só um círculo ao redor —
e moram morcegos, aranhas das cavernas, carniçais e, no fundo do túnel,
um **dragão**. Mais fundo ainda, no fim de um corredor longo, o
**Lorde Dragão** (1900 HP, respawn de 15 min) guarda os melhores itens do
jogo: a **espada de fogo** (atk 22), o escudo do dragão e a espada larga.

### Comandos de chat

| Comando | Quem | Efeito |
|---|---|---|
| `/help` | todos | lista os comandos |
| `/online` | todos | jogadores conectados |
| `/save` | todos | salva o personagem agora |
| `/goto x y [z]` | admin | teleporta (z: 0=superfície, 1=subsolo) |
| `/spawn <monstro> [n]` | admin | invoca monstros (`rat`, `wolf`, `orc`...) |
| `/item <id> [n]` | admin | cria itens (ids: use `/itens`) |
| `/heal` | admin | vida e mana cheias |
| `/ghost` | admin | modo fantasma: monstros não te enxergam |
| `/itens` | admin | lista todos os itens com seus ids |
| `/bichos` | admin | lista todos os monstros (para usar com `/spawn`) |
| `/level <n>` | admin | define o level do personagem (recalcula hp/mp/exp/cap) |
| `/skill <nome> <n>` | admin | define uma skill (punho/clava/espada/machado/distancia/escudo/pesca/magia) |
| `/pm <nome> <msg>` | todos | mensagem privada (aba PM) |

---

## O mundo

Mapa de 100x100 tiles gerado por `tools/genmap.py`:

- **Cidade murada** (zona de proteção — monstros não entram): templo de
  mármore com o curandeiro **Padre Elio** (diga `curar`), loja do mercador
  **Tobias** (compra e vende equipamentos, poções e comida) e o
  **Guarda Marcus** no portão leste (pergunte sobre os `monstros`).
- **Área de caça** a leste, em dificuldade crescente: ratos e cobras perto
  do portão → lobos na floresta → trolls ao norte → orcs no extremo leste →
  esqueletos no cemitério nordeste.

Monstros têm aggro, perseguem, voltam para o spawn e **renascem** após um
tempo (45s para ratos até 15min para o Lorde Dragão). **Cinco segundos antes
de nascer, uma bolinha azul pulsante aparece no tile** — é o aviso de respawn.
Loot cai no chão (com corpo) e expira se ninguém pegar.

### Progressão

- Curva de experiência idêntica ao Tibia clássico (`50/3·(l³−6l²+17l−12)`).
- Morreu? Perde 10% da exp (sem rebaixar de nível) e volta ao templo.
- Comer (queijo, carne, pão) acelera muito a regeneração de HP/MP.
- Equipamento importa: arma define o dano, armadura+escudo reduzem o que
  você sofre.

---

## Estrutura do projeto

```
fibula/
├── start.bat               inicia tudo (gera assets na 1ª vez)
├── server/                 servidor autoritativo (Python stdlib)
│   ├── main.py             entrada: HTTP + WebSocket na mesma porta
│   ├── config.py           todas as constantes de gameplay/rede
│   ├── websocket.py        RFC 6455 implementado à mão
│   ├── httpstatic.py       serve a pasta client/
│   ├── database.py         SQLite (contas, personagens)
│   └── game/
│       ├── game.py         orquestrador: tick, visão, combate, handlers
│       ├── world.py        mapa, andabilidade, itens no chão
│       ├── entities.py     Player / Monster / Npc, inventário
│       ├── spells.py       magias faladas (exura, exori, utani hur)
│       ├── npcs.py         diálogo por palavras-chave + comércio
│       ├── formulas.py     exp, dano, defesa, velocidade
│       └── data.py         carrega os JSONs de definição
├── client/                 cliente browser (zero dependências)
│   ├── index.html          telas de login e jogo
│   ├── css/style.css       tema escuro estilo Tibia
│   ├── js/                 net, game (estado), render, ui, input, main
│   └── assets/             spritesheet gerada (sprites.png + .json)
├── data/
│   ├── items.json          definições de itens
│   ├── monsters.json       monstros (hp, dano, loot...)
│   ├── npcs.json           NPCs (diálogos, loja, posição)
│   ├── map.json            mapa gerado (camadas + spawns)
│   └── fibula.db           banco SQLite (criado na 1ª execução)
├── tools/
│   ├── gensprites.py       gera a spritesheet placeholder (pixel art em código)
│   ├── genmap.py           gera o mapa (cidade + templo + caça)
│   ├── minipng.py          escritor de PNG sem Pillow
│   └── smoke_test.mjs      teste e2e (Node 22+): node tools/smoke_test.mjs
└── docs/
    ├── ARQUITETURA.md      como tudo funciona por dentro
    └── PROTOCOLO.md        todas as mensagens cliente↔servidor
```

## Personalizando

- **Novos itens/monstros/NPCs**: edite os JSONs em `data/` (não precisa
  mexer em código para loot, dano, preços, diálogos).
- **Mapa**: edite `tools/genmap.py` e rode `python tools/genmap.py`.
- **Sprites**: são placeholders gerados por `tools/gensprites.py` — para
  arte real, basta substituir `client/assets/sprites.png` mantendo os
  nomes/índices de `sprites.json`.
- **Gameplay**: constantes em `server/config.py` (velocidade de ataque,
  perda de exp, decay de loot, regeneração...).

## Testes

Com o servidor rodando:

```
node tools/smoke_test.mjs
```

Valida registro, login, movimento, chat, NPC, combate, loot, coleta,
comércio e persistência (21 verificações).

## Roadmap (ideias futuras)

- Skills de arma por uso (sword/club/axe fighting) e magic level
- Mais magias (projéteis, runas), vocações
- PvP com skull system · party/grupo
- Containers (mochilas dentro de mochilas) e depot
- Caves/andares (z-levels) · mais cidades
- Substituir sprites placeholder por arte real
