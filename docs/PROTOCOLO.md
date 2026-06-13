# Protocolo Fibula (WebSocket + JSON)

Todas as mensagens são objetos JSON com um campo `type`. Uma conexão:
`ws://host:7777/ws`.

## Cliente → Servidor

| type | Campos | Descrição |
|---|---|---|
| `register` | `account, password, name, vocation` | cria conta + personagem e já entra no jogo (`vocation`: knight/paladin/sorcerer/druid) |
| `login` | `account, password` | entra com personagem existente (derruba sessão duplicada) |
| `move` | `dir` (`n/s/e/w/ne/nw/se/sw`) | pede um passo (diagonal = 2x mais lento); servidor valida colisão e cooldown (cancela autowalk) |
| `walkto` | `x, y` | autowalk: servidor calcula o caminho (BFS, no andar atual) e anda sozinho |
| `stop` | — | cancela o autowalk (tecla ESC) |
| `use_stairs` | `x, y` | usa a escada clicada (anda até ela primeiro, se preciso) |
| `move_item` | `from, to` | arrasta item entre slots da mochila (junta pilhas iguais) |
| `move_ground` | `fx, fy, tx, ty` | arrasta o item do topo de um tile do chão para outro |
| `drop_equip` | `eslot, x, y` | joga um item equipado no chão |
| `stance` | `mode` | postura: `attack` / `balanced` / `defense` |
| `pvp` | `on` | liga/desliga o modo PvP (atacar players exige os dois lados ligados) |
| `follow` | `on` | segue o alvo selecionado automaticamente (cancela se o alvo morrer/sumir) |
| `logout` | — | sair do jogo; negado com lock de combate (PvE 10s / PvP 60s) |
| `open_container` | `x, y` | abre o corpo clicado (adjacente); várias janelas podem ficar abertas |
| `loot` | `x, y, idx` | move o item `idx` de dentro do corpo para a mochila |
| `close_container` | `x?, y?` | fecha uma janela de loot (sem x/y: todas) |
| `look_item` | `slot` \| `eslot` \| `cidx+cx+cy` | olha um item da mochila / equipamento / corpo aberto |
| `hotkeys` | `map` | salva as hotkeys do personagem (`{"F1": {type:"say", text}, "2": {type:"use", item}}`) |
| `say` | `text` | fala local; interpreta magias, comandos `/` e NPCs |
| `attack` | `id` | define/alterna o alvo (0 ou o mesmo id cancela) |
| `pickup` | `x, y` | pega o item do topo da pilha (precisa estar adjacente) |
| `equip` | `slot` | equipa o item do slot da mochila (swap automático) |
| `unequip` | `eslot` | tira `weapon/shield/helmet/armor/legs/boots` |
| `use` | `slot` | usa poção/comida do slot |
| `drop` | `slot, x?, y?` | joga o item no chão (até 3 tiles; padrão: aos pés) |
| `look` | `x, y` | descreve o que está no tile (criatura > item > terreno) |
| `npc_buy` | `npc, item, count` | compra na loja aberta |
| `npc_sell` | `npc, item, count` | vende na loja |
| `ping` | — | keepalive (responde `pong`) |

## Servidor → Cliente

### Sessão

| type | Campos | Descrição |
|---|---|---|
| `welcome` | `id, name, admin, motd, map, items` | login OK; mapa estático completo + definições de itens |
| `error` | `message` | falha (login inválido, sem espaço, etc.) |
| `dead` | `message` | você morreu (já renasceu no templo) |
| `pong` | — | resposta ao ping |

O `map` do welcome contém `width, height, floors[{ground[][], objects[][]}],
groundMeta, objectMeta, meta{temple, pz}` — um item de `floors` por andar
(índice = z). O cliente desenha o andar em que o jogador está e o minimapa
a partir disso; nada de mapa é re-enviado depois. Escadas entre andares são
resolvidas no servidor (pisar → teleporta).

### Estado do jogador (enviados quando mudam)

| type | Campos |
|---|---|
| `stats` | `hp, maxhp, mp, maxmp, level, exp, expBase, expNext, speed, gold, fed, atk, def, vocation, stance, pvp, cap, maxcap` |
| `skills` | `skills{fist/club/sword/axe/distance/shield/fishing/magic: {level, pct}}` |
| `inv` | `slots[32]` (null ou `{id, count}`), `equip{10 slots}`, `active` (slots utilizáveis = 8 bolsos + mochila) |
| `target` | `id` (confirmação do alvo atual) |

### Entidades visíveis (modelo de visão)

| type | Campos | Quando |
|---|---|---|
| `espawn` | `e{id, kind, name, x, y, z, dir, sprite, hp, maxhp}` | entidade entrou na sua visão |
| `edespawn` | `id` | saiu da visão (ou morreu/deslogou/trocou de andar) |
| `emove` | `id, x, y, z, dir, ms` | andou; `ms` = duração do passo p/ interpolação |
| `ehp` | `id, hp, maxhp` | vida mudou |

`kind` ∈ `player | monster | npc`.

### Mundo

| type | Campos | Descrição |
|---|---|---|
| `ground_full` | `tiles[{x, y, z, items[]}]` | estado completo do chão (no login) |
| `ground` | `x, y, z, items[{id, count}]` | pilha de um tile mudou (loot, pickup, decay) |
| `chat` | `from, text, channel, x?, y?` | `channel` ∈ `say/npc/server/info/loot/look` |
| `fx` | `x, y, kind?, text?, color?` | efeito visual (só enviado a quem está no mesmo andar); `kind` ∈ `blood/heal/poff/levelup/magic/fire`; `text` vira número flutuante |
| `npc_trade` | `npc, sells[], buys[]` | abre a janela de comércio (`{id, name, price}`) |
| `spawn_warn` | `x, y, z, ms` | um monstro vai nascer nesse tile em `ms` ms — o cliente desenha a bolinha azul pulsante |
| `container` | `x, y, name, items[]` | conteúdo de um corpo aberto (reenviado a cada mudança) |
| `container_close` | `x?, y?` | aquele corpo sumiu/ficou longe: fecha a janela (sem x/y: todas) |
| `proj` | `fx, fy, tx, ty, sprite` | projétil voando (flecha/lança) — o cliente anima |
| `eskull` | `id, on` | caveira do agressor PvP acendeu/apagou (espawn também traz `skull`) |
| `logged_out` | — | logout aceito: cliente volta para a tela de login |

## Fluxo típico de login

```
C→S  {"type":"login","account":"lemos","password":"..."}
S→C  welcome (mapa + itens)
S→C  stats
S→C  inv
S→C  ground_full
S→C  espawn (você)
S→C  espawn (cada criatura na sua visão)
S→C  chat (motd / "Fulano entrou no jogo")
```

## Notas de implementação

- Frames de texto WebSocket; payloads pequenos (o maior é o `welcome`,
  ~80 KB com o mapa 100x100).
- O servidor ignora mensagens malformadas e taxa nenhuma — flood de `move`
  é inofensivo porque o cooldown de passo é validado server-side.
- IDs de entidade são efêmeros (por sessão de servidor); IDs de item são
  estáveis (vêm de `data/items.json`).
