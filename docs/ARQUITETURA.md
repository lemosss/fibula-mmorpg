# Arquitetura do Fibula

## Visão geral

```
┌─────────────────────┐         WebSocket (JSON)        ┌──────────────────────┐
│  Cliente (browser)  │ ◄─────────────────────────────► │  Servidor (Python)   │
│  Canvas + JS puro   │         HTTP (estáticos)        │  asyncio, 1 processo │
└─────────────────────┘                                 └──────────┬───────────┘
                                                                   │ sqlite3
                                                             ┌─────▼─────┐
                                                             │ fibula.db │
                                                             └───────────┘
```

- **Uma única porta** (7777): requisições HTTP normais recebem os arquivos
  do cliente; requisições com `Upgrade: websocket` viram sessões do jogo.
  Isso elimina CORS e simplifica rodar em LAN.
- **Zero dependências**: o handshake e os frames WebSocket (RFC 6455) são
  implementados em `server/websocket.py` com hashlib/base64/struct.

## Servidor autoritativo

O cliente **nunca decide gameplay** — ele só pede (`{"type":"move","dir":"n"}`)
e renderiza o que o servidor manda. Toda regra (colisão, cooldown, dano,
loot, preço) vive no servidor. Isso torna trapaça via cliente modificado
inócua por construção.

### O tick (100 ms)

`server/main.py` roda `Game.tick()` a cada 100 ms:

1. **Auto-ataque dos jogadores** — se há alvo adjacente e o cooldown (2 s)
   venceu, o golpe sai.
2. **IA dos monstros** — aquisição de alvo (raio de aggro, ignora quem está
   na zona de proteção), perseguição em passos cardeais gulosos, ataque
   adjacente, vagueio com "coleira" ao redor do spawn.
3. **Respawns** — heap de `(quando, zona)`; monstros mortos voltam após o
   `respawn` da zona.
4. **Decay** — corpos (60 s) e loot (300 s) somem do chão.
5. **Regeneração** — HP/MP por timers; comer acelera (estado "fed").
6. **Autosave** — todos os personagens online a cada 60 s.

Movimentação **não** espera o tick: é processada na hora em que a mensagem
chega (latência de input ~0 em rede local), com o cooldown de passo
(`1000·fricção/velocidade` ms) impedindo speed-hack.

### Sincronização de visão (o coração do multiplayer)

Cada jogador tem um conjunto `known` — os ids de entidades que o cliente
dele conhece. Quando algo muda de posição, o servidor compara visibilidade
antes/depois para cada jogador e emite o mínimo necessário:

| Situação | Evento enviado |
|---|---|
| entrou no campo de visão | `espawn` (entidade completa) |
| saiu do campo de visão | `edespawn` (só o id) |
| moveu-se dentro da visão | `emove` (id, x, y, dir, duração) |
| HP mudou | `ehp` |

O campo de visão é 19x15 tiles (o viewport de 15x11 + margem), igual à
lógica do Tibia. O cliente interpola o movimento entre tiles usando a
duração informada no `emove`, por isso o andar é suave apesar do grid.

### Persistência

SQLite com duas tabelas (`accounts`, `characters`). Inventário e
equipamento são colunas JSON — pragmático para a escala atual e fácil de
normalizar depois. Senhas: `sha256(salt + senha)` com salt aleatório por
conta. Saves: logout, autosave, morte, `/save` e shutdown (Ctrl+C).

### Conteúdo data-driven

Itens, monstros e NPCs são JSONs em `data/`. O servidor lê tudo na
inicialização (`game/data.py`); novos monstros/itens/diálogos não exigem
mexer em código. O mapa também é um JSON, gerado por `tools/genmap.py`
com seed fixa (determinístico).

## Cliente

Seis módulos JS sem framework:

| Módulo | Papel |
|---|---|
| `net.js` | WebSocket + registro de handlers por tipo de mensagem |
| `game.js` | estado (`G`): entidades, chão, stats, inventário; handlers |
| `render.js` | loop de canvas: chão → itens → objetos/criaturas (painter por linha) → efeitos → textos flutuantes; minimapa |
| `ui.js` | DOM: barras, mochila, equipamento, chat, janela de comércio |
| `input.js` | teclado/mouse → mensagens para o servidor |
| `main.js` | bootstrap, login, reconexão |

O canvas interno é 480x352 (15x11 tiles de 32 px) escalado 2x com
`image-rendering: pixelated` — pixel art nítida sem custo de render.

O minimapa pinta o mapa estático uma vez num canvas offscreen (1 px por
tile) e a cada frame recorta a região ao redor do jogador, sobrepondo
pontos coloridos para criaturas.

## Sprites placeholder

`tools/gensprites.py` desenha cada sprite proceduralmente (retângulos,
discos, ruído determinístico) e monta a spritesheet com
`tools/minipng.py` — um escritor de PNG em ~40 linhas de stdlib (zlib +
struct). Trocar por arte real = substituir o PNG mantendo os índices.

## Decisões e trade-offs registrados

- **Lua de fora**: diferente do TFS, os scripts de conteúdo são JSON +
  Python. Para a escala do projeto, menos camadas = menos bugs.
- **Itens no chão são broadcast global** (não por visão): o estado é
  pequeno e isso simplifica o minimapa/cliente. Reavaliar se o mundo
  crescer muito.
- **Sem prediction no cliente**: como o alvo é rede local/LAN, a latência
  não justifica a complexidade de reconciliação.
- **Uma conta = um personagem** (MVP). A tabela `characters` já está
  separada para suportar vários no futuro.
- **Sem perda de nível na morte**: perde-se 10% da exp, com piso no início
  do nível atual. Simples e amigável; fácil de endurecer depois.
