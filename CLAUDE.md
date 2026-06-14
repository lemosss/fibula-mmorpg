# Fibula — Guia para o Claude (CLAUDE.md)

> MMORPG 2D estilo **Tibia clássico** feito do zero nesta pasta.
> Servidor Python 3.11 **100% stdlib** + cliente browser (Canvas/JS puro).
> Este arquivo é o "save game" do desenvolvimento: leia antes de mexer.

---

## 1. Como rodar / testar / iterar

```
start.bat                       → sobe tudo e abre http://localhost:7777
node tools/smoke_test.mjs       → regressão e2e (~36 checks, servidor no ar)
python tools/gensprites.py      → regenera client/assets/sprites.png (+json)
python tools/genmap.py          → regenera data/map.json (determinístico)
python tools/clean_test_accounts.py  → apaga contas smoke%/demo%/warnobs%
```

- **Porta única 7777**: HTTP estático (client/) + WebSocket (`/ws`) no mesmo
  processo (`server/main.py`). Sem dependências externas em lugar nenhum.
- Preview do Claude Code: `OT/.claude/launch.json` tem a config `fibula`
  (`python -u server/main.py`, `autoPort: false`). Para recarregar código do
  SERVIDOR: `preview_stop` + `preview_start`. Cliente: só F5 no browser.
- **Cache desligado** (`httpstatic.py` manda `Cache-Control: no-store ...`): o
  browser NUNCA guarda JS/CSS, então F5 sempre traz a versão nova. Evita o clássico
  "corrigi mas o usuário continua vendo o bug" (era a causa de reclamações
  repetidas do mesmo problema entre turnos).
- **O usuário costuma estar JOGANDO na página do preview** (Admin Lemos).
  Não dê `location.reload()` na página dele; peça para ele dar F5.
  O smoke test AVISA quando há outros jogadores online (eles podem "roubar"
  o monstro do teste — falhas intermitentes de loot/exp são isso).
- `preview_screenshot` falha (timeout) se o painel do preview estiver
  oculto (rAF pausa). Use `preview_eval` para inspecionar estado do jogo
  (`G`, `Net.send(...)`, DOM) — funciona sempre.
- PowerShell quebra SQL inline com aspas → para mexer no SQLite, escreva um
  `.py` temporário em tools/ e rode (padrão usado: `tools/_promote.py`).
- Padrão de verificação: scripts descartáveis `tools/_verify_*.mjs` (Node 22
  tem WebSocket nativo) — registrar conta `warnobs`, promover a admin via
  sqlite, usar /goto, /spawn, /item etc., checar mensagens. Apagar no final
  + `clean_test_accounts.py`.

## 2. Contas / banco

- SQLite em `data/fibula.db`. Tabelas: `accounts` (sha256 salt+senha,
  `is_admin`) e `characters` (level, exp, hp/mp, x/y/z, vocation, skills
  JSON, hotkeys JSON, inventory JSON, equipment JSON, deaths).
- Migrações: lista `MIGRATIONS` em `server/database.py` (ALTER TABLE em
  try/except). Adicione novas colunas lá.
- **Conta do usuário: `lemos` (is_admin=1), personagem "Admin Lemos"** —
  senha é dele, nunca registrada por nós. A 1ª conta de um banco novo vira
  admin automaticamente.
- Autosave 60s + save em logout/morte//save/shutdown.

## 3. Arquitetura (resumo)

- **Server-authoritative**: cliente só pede; servidor decide tudo.
- `server/game/game.py` = orquestrador (handlers de mensagens + tick 100ms:
  combate, IA, respawn, decay, regen, autosave). `world.py` = mapa estático
  3D + itens no chão. `entities.py` = Player/Monster/Npc + inventário/peso.
  `npcs.py` diálogo/loja, `spells.py` magias, `formulas.py` fórmulas.
- **Visão por eventos**: cada player tem `known` (ids que o cliente dele
  conhece); `espawn`/`edespawn`/`emove`/`ehp` emitidos por mudança de
  visibilidade (19x15 tiles, mesmo andar). Movimento é processado na hora
  (não espera tick); cooldown de passo = `1000*90/speed` ms (diagonal 2x).
- Protocolo completo em `docs/PROTOCOLO.md` (mantenha atualizado!).
- Itens no chão são broadcast GLOBAL (estado pequeno); chave `(x,y,z)`.
- Cliente: `js/game.js` estado `G` + handlers; `render.js` canvas 480x352
  com câmera em **pixel inteiro** (Math.round — NUNCA desenhe com offset
  fracionário: causa linhas pretas entre tiles); `ui.js` DOM; `input.js`
  teclado/mouse/drag&drop; `net.js` WS.

## 4. Mundo / mapa (gerado por tools/genmap.py, seed fixa)

- 100x100, **2 andares** (`floors[z]`): z=0 superfície, z=1 subsolo.
- Cidade murada (PZ = zona de proteção, monstros não entram): x18-48,y34-66.
  Templo (spawn/renasce) em **(25,42)**. NPCs: Padre Elio (25,39) cura ao
  dizer "curar"; Tobias (42,41) loja (diga "comerciar"); Guarda Marcus (46,48).
- Caça (dificuldade crescente): ratos (56,50)/(60,57) → cobras (62,70) →
  lobos (72,42) → trolls (64,28) → orcs (86,48) → esqueletos cemitério (85,14).
- Subsolo: morcegos (60,20), aranhas (75,35), carniçais/cripta (84,16),
  dragão (50,60), **lorde dragão (30,72)**.
- Conexões entre andares (meta do map.json):
  - `portals` (escadas): (66,26) colinas trolls e (84,12) cemitério.
    **DESCER é AUTOMÁTICO ao pisar** (igual buraco; `check_hole` trata escada com
    dest z>p.z), **SUBIR só ao CLICAR** (`use_stairs`/`use_portal`) — pisar na
    escada-up NÃO sobe (evita bounce). Itens largados na escada-down também CAEM.
  - `holes`: buraco em (75,48,0) → o JOGADOR cai ao pisar (check_hole) E **itens
    jogados ali CAEM pro andar de baixo** (`_ground_drop` checa holes E down-portals).
  - `ropes`: rope spot (75,48,1) → corda. O destino `to` (75,49,0) é a SAÍDA do
    buraco: quem sobe (jogador, ou item/criatura puxados) aparece SEMPRE nesse tile.
  - **Corda na ESCADA**: NÃO sobe você (escada se usa clicando). Roping a escada que
    desce, do andar de cima, PUXA o que está no SQM DIRETAMENTE abaixo (mesmo x,y) e
    POUSA no SQM embaixo da escada (onde quem SOBE a escada-up aparece — andável,
    nunca em cima do tile de queda). `_rope_target`: `exit = ropes[below] OR
    portals[below]` (a saída de subida do tile de baixo). Vale p/ item/jogador/bicho.
- **Pontos de entrada/saída são FIXOS** (`teleport_exact`): cair no buraco, descer/
  subir escada e ser puxado pela corda levam SEMPRE ao SQM exato do destino. Se já
  houver criatura/jogador lá, **EMPILHA** (ocupam o mesmo SQM) — ninguém é deslocado.
  `by_pos` é `(x,y,z) -> [Creature]` (LISTA). `occupied()` (caminhar normal) bloqueia
  qualquer tile com criatura, então só quedas/corda/escada empilham; ao se separarem,
  o caminhar normal impede re-empilhar. `creature_at()` = primeira da lista.
- Lago a oeste (x≤13) — pesca na praia (x=14).
- `world.no_monster = holes | down-portals` (tiles de QUEDA): monstros NÃO pisam em
  buraco do solo NEM em escada-que-desce (fica esquisito um bicho parado em cima sem
  cair). MAS pisam na escada-de-SUBIR e rope spots — que ficam no SQM DIRETAMENTE
  abaixo da escada/buraco de cima. A corda puxa exatamente desse SQM de baixo (não
  está em no_monster), então dá pra puxar o bicho que está lá.
- Subsolo é escuro no cliente (círculo de luz ao redor do player).
- **BURACO/ROPE = PROPRIEDADE DO TILE, não objeto** (refeito): saíram do array
  `objects`; o comportamento vive em `world.holes`/`world.ropes` (por posição) e o
  SPRITE vai em `meta.decos` (`[{x,y,z,sprite}]`), desenhado na **camada 1** (sob
  os itens) via `Render.decoSprite`. Assim o buraco nunca esconde item nenhum, e o
  "ser buraco" não depende do sprite. Escadas continuam objetos andáveis (camada 1).
  Objetos `walk:false` (árvore/parede/altar) vão na camada 3 com as criaturas.
- **Item no buraco de DESCIDA cai** pro andar de baixo (igual jogador descendo):
  todo drop passa por `Game._ground_drop(x,y,z,item)`, que relocaliza pro destino
  do hole. (h_drop, h_drop_equip, _do_move_ground, h_loot_ground).
- Respawn: tempo-base por zona (45s ratos … 15min lorde dragão) × `RESPAWN_MULT`
  (config, **=3** hoje, pq estava nascendo rápido demais) → ratos 135s etc.;
  **bolinha azul pulsante 5s antes** do nascimento (`spawn_warn`, dentro do total).
- **Itens no chão NÃO somem sozinhos** (persistem até reiniciar = "Server Save").
  Só **CORPOS de bicho** têm `decay` (somem em `CORPSE_DECAY_S`); item largado,
  baú e loot tirado do corpo ficam SEM `decay`. `decay_tick` só remove quem tem
  `decay` expirado (`i.get("decay")`). Drops (h_drop/h_drop_equip/loot_ground) não
  setam mais decay. (Não há comando de Server Save ainda — restart do `start.bat`
  é o que zera os itens do chão.)

## 5. Sistemas de gameplay (estado ATUAL — decisões do usuário)

### Inventário / mochila (modelo Tibia raiz)
- **SEM mochila equipada = ZERO slots** (`BASE_INV_SLOTS = 0`). Os slots vêm
  todos do item: mochila comum (id 70) = 24, mochila grande (71) = 32.
- Janela da mochila = mesma cara das janelas de loot (header + ✕); abre/
  fecha clicando no ícone da mochila equipada. Sem scroll horizontal.
- **Dropar a mochila leva TUDO dentro** (itens viram `contents` do item
  dropado); no chão ela é um container clicável; arrastar de volta ao slot
  (equip_ground) despeja o conteúdo nos slots de novo.
- Desequipar mochila para "dentro de si" é impossível → mensagem manda
  dropar no chão ou trocar por outra (equipar a nova por cima faz swap).
- Mochilas com conteúdo não contam em inv_count/inv_remove (não vendem por
  engano). Peso conta o conteúdo aninhado (`Player.item_weight`).

### Equipamento (10 slots) — arma/escudo em QUALQUER mão
`helmet necklace backpack armor weapon shield legs boots ring ammo`
(nomes internos antigos mantidos por compat de save; cliente mostra
Head/Right Hand/Left Hand etc., em cruz). `TYPE_TO_SLOT` em entities.py.
- **Mãos (slots weapon+shield) intercambiáveis:** `weapon_def`/`defense` varrem AS
  DUAS mãos (arma = type "weapon" em qualquer mão; escudo = type "shield"). Arrastar
  pro slot RESPEITA a mão: o cliente manda `eslot` no `equip`, e `_equip_hand(dest)`
  põe naquela mão (o que estava lá volta pro inv). Sem eslot (duplo-clique) escolhe
  mão livre. Arrastar de uma mão DIRETO p/ a outra = `equip_move` (swap entre mãos,
  sem passar pela mochila). NÃO há mais arma de 2 mãos — **qualquer arma (incl. o
  arco id 17) vai em qualquer mão**. O caminho `twohand` em `_equip_hand` continua
  no código, mas nenhum item ativa hoje.
  **`equip_move` SÓ vale mão↔mão** (weapon/shield); arrastar item equipado pro
  ÍCONE DA BACKPACK (ou qualquer outro destino que não seja a outra mão) =
  `unequip` (cai dentro da bag via `inv_add`). Sem o gate `HANDS(a,b)` no
  `Drag.resolve`, desequipar pela bag virava um `equip_move` morto.
- Anel da vida (34): efeito "fed" (regen rápido). Amuleto proteção (33): +2 arm.
- Itens equipados não vendem no NPC (badge "equipado" na loja + msg).
- **Compra/venda em QUANTIDADE no NPC**: o botão Comprar/Vender abre o seletor de
  quantidade (`UI.askQuantity`, mesmo do split de pilha). Comprar: max = quanto o
  ouro paga (`floor(gold/price)`, teto 100), começa em 1. Vender: max = quanto tem,
  começa no total. Manda `count` no `npc_buy`/`npc_sell`; o servidor (`npcs.buy`/
  `sell`) já clampa 1..100 e valida ouro/`give` tudo-ou-nada.

### Usar item: SEM seleção; duplo-clique e clique-DIREITO
NÃO há mais "selecionar item" nem botões Usar/Equipar/Dropar (`#inv-actions`,
`selectSlot` REMOVIDOS). Dropar = arrastar pro chão. **EQUIPAR = SÓ arrastando** pro
slot (duplo-clique NÃO equipa mais). Duplo-clique (`smartAction`) só USA consumível/
ferramenta (food/potion/tool → `use`); arma/armadura não fazem nada no duplo-clique.
**Clique-DIREITO** (`Input.handleItemRightClick`,
na mochila / corpo / chão): comida → `use_item` (come na hora, em qualquer lugar);
poção ou corda → entra no modo "USAR-COM" (`UseWith` no input.js: `body.use-with`
→ cursor `cell`; o PRÓXIMO clique esquerdo escolhe o alvo — poção num jogador
visível = cura; corda num buraco/rope spot adjacente = sobe; ESC cancela); demais
itens → nada. Server: `_source_item` resolve a fonte (inv|container|ground) e
devolve `consume`; `h_use_item` (imediato) e `h_use_with` (com alvo `tid` ou
`tx,ty`).
- **LOOK no mapa — WALK é instantâneo, sem delay nenhum.** Dois jeitos de olhar:
  1. **SHIFT + clique** (recomendado, padrão Tibia): confiável, sem timing. Em
     `onCanvasClick`, `ev.shiftKey` → manda `look` e NÃO anda; o mousedown ignora
     o arrasto com Shift. NÃO grava `lastLookMs` (dá pra olhar vários tiles seguidos).
  2. **Esquerdo + Direito pressionados JUNTOS** (bônus): detectado no `mousedown`
     (`ev.buttons&1 && ev.buttons&2`) → `doLook` na hora. Só funciona se os dois
     estiverem pressionados ao mesmo tempo (segura um, aperta o outro); se soltar o
     1º antes, o walk instantâneo já saiu — por isso o Shift é o jeito robusto.
  `doLook` grava `lastLookMs`; `onCanvasClick`/contextmenu engolem o click/uso nos
  `LOOK_SUPPRESS=350ms` seguintes (não vira walk). Não há mais agendamento de walk.
- **Modo "usar-com" cancela em QUALQUER clique fora do mapa.** Um listener global
  de `mousedown` (capture) faz: se `UseWith.active` e o alvo não está em
  `#canvas-wrap` (ou seja, clicou na interface) → `UseWith.cancel()` (cursor volta).
  Clicar num tile válido do mapa resolve; ESC também cancela.
- **Corda (`_rope_use`/`_rope_pull_up`) usa o ATRIBUTO do tile:** rope spot → o
  jogador sobe; buraco de descida → PUXA UM ente do SQM logo abaixo, na ordem
  ITENS (um por uso) → JOGADOR → CRIATURA (monstro precisa de `ropeable`, default
  True; futuro = marcar por-monstro no JSON). **TUDO pousa na SAÍDA do buraco**
  (`world.ropes[below]`, via `teleport_exact` — o MESMO tile onde um jogador surge
  ao subir), NUNCA aos pés do puxador. Se o puxador está nesse tile, o puxado
  EMPILHA nele (não desloca o puxador); a criatura viva dá o próximo passo pro lado
  (IA) e aí o caminhar normal impede re-empilhar. Verificado live: item cai; corda
  puxa item/jogador/corpo/monstro pro tile de saída; puxador NÃO é deslocado;
  self-climb; prioridade itens-primeiro; monstro ocupa o SQM de baixo e é puxado.
- **Minimapa:** scroll do mouse dá zoom (`wheel` → `Minimap.zoom`); botões +/−
  ficam inset (3px) com bordinha igual à rosa dos ventos.
- **Abrir loot (corpo/baú/container no chão) = clique DIREITO** (`open_container`
  no contextmenu do canvas, junto com come/usar-com). O clique ESQUERDO NÃO abre
  mais container (só pega itens não-container; container cai p/ walk). Futuro: config
  pro player escolher esquerdo ou direito.
- **Pegar item do chão clicando:** clique LIMPO (sem mexer) → `onCanvasClick` manda
  `pickup`. Clique COM tremida (>5px vira arrasto) que solta no MESMO tile também
  manda `pickup` (`Drag.resolve` ground→mesmo-tile = pegar) — antes não fazia nada,
  por isso "só dava pegar arrastando pra bag". As duas vias = pickup, robusto.
- **Item Baú (id 80):** CONTAINER de 8 slots (`container:true, capacity:8`) E
  `blocking:true`. Abre com clique direito no chão (8 slots, guarda/loot via drag,
  conteúdo persiste). NÃO é equipável (type "misc" → fora de `TYPE_TO_SLOT`, então
  não vai no slot backpack) — só dá pra CARREGAR dentro da mochila (item comum no
  inv, com `contents`). Bloqueia o tile (ver `blocking_ids` abaixo).
- **Item Baú — bloqueio:** ninguém anda em cima — nem player nem
  monstro. `world.walkable` checa `world.blocking_ids` (ids com `blocking`) contra
  os itens do chão do tile; pathfinding e movimento contornam. É pegável (drag/click)
  pra reposicionar. Itens no chão são runtime → somem no restart do `start.bat`.

### Capacity (CAP)
Peso em oz em TODO item (`weight` no items.json). `CAP = 350 + level*10`.
`Game.give()` é o caminho padrão para entregar itens (checa peso+espaço
com mensagens distintas).

### Loot (estilo Tibia)
Loot nasce DENTRO do corpo (`contents`). Clicar no corpo (adjacente) abre
janela de container; **várias podem ficar abertas**, empilhadas na SIDEBAR
abaixo da mochila. Clicar de novo no corpo TOGGLA (fecha) a janela.
Arrastar/duplo-clique p/ saquear na mochila (`loot`); arrastar p/ um tile do
mapa joga no chão (`h_loot_ground`). Corpos podem ser arrastados pelo chão.
Corpo some em 120s com o loot.

### Battle list (estilo Tibia)
Janela `#battle-window` na sidebar (botões "Battle" e ☰ perto do equipamento
togglam; tem ✕ fechar e — minimizar). renderBattle() lista monstros + outros
players SÓ dentro do viewport da tela (±Render.VIEW_W/2 x, ±VIEW_H/2 y =
±7/±5), ordenados por distância, mini-sprite + barra; clique = `attack`; alvo
ganha `.targeted`. Atualiza a cada 250ms + na msg `target`.

### Janelas em COLUNAS DE DOCK (principal na sidebar + colunas extras)
A coluna PRINCIPAL de encaixe é `#dock-right-body` (`.dock-body` DENTRO da
`#sidebar`, abaixo do minimapa/HP/MP) — é onde as janelas
`.container-panel.movable` (equip, combat-bar, inv, battle, skills) vivem por
padrão e é um ALVO DE DROP PERMANENTE (a `#sidebar` inteira conta como hit-area).
Isso conserta o "não consigo soltar janela na dock do minimapa". Colunas EXTRAS
`.dock-col[data-side="left|right"]`: **máx 1 extra por lado** — esquerda
`#dock-left` (sempre visível) + `#dock-left2`; direita só `#dock-right2` (a
principal já é a sidebar). As extras começam `.hidden`; as da direita abrem ENTRE
`#game-main` e a sidebar. Cada uma tem `.dock-body`. (Limite: esquerda = 2 colunas
no total; direita = principal + 1.)

Arrastar o `.cont-header` MOVE a janela entre alvos e reordena por Y
(`UI.makeWindowMovable` + `UI.dockAt`). **`UI.dockTargets()`** = colunas extras
visíveis + a coluna principal da sidebar (`{el:#sidebar, body:#dock-right-body}`);
`dockAt(x)` devolve o `.dock-body` cujo `el` contém X (senão o mais próximo). NUNCA
flutua.

**Setinhas na DIVISA (2 controles):** `#dock-ctrl-left`/`#dock-ctrl-right` nas bordas
de `#game-main` (`position:relative`). Esquerda `›` add / `‹` remove; direita
espelhada `‹` add / `›` remove (botões `.dock-more`/`.dock-less` com `data-side`).
Mexem só nas colunas EXTRAS (`sideCols(side)` = `.dock-col[data-side]`); a coluna
do minimapa é permanente. `removeDock` manda as janelas da coluna fechada p/ outra
do mesmo lado ou, senão, p/ a principal (`#dock-right-body`) — janela nunca se
perde. Esquerda pode fechar TODAS as suas colunas. Persistência em
`localStorage["fibula.dock"]` = `{docks:{bodyId:[winIds]}, open:[dockColIds]}`
(`.dock-body` inclui a principal). Drop de loot/ground aceita `.dock-col, #sidebar`.

### Zoom do minimapa (＋/−)
`#mm-zoom` (canto sup-esq do minimapa) tem `#mm-zin`/`#mm-zout` → `Minimap.zoom(±1)`.
`Minimap.VIEW` = nº de tiles visíveis (menor = mais perto); passos em
`Minimap.ZOOMS = [16,24,34,50,70,100]`. `draw()` lê `this.VIEW` a cada frame, então
o zoom é imediato; persiste em `localStorage["fibula.mmzoom"]` (restaurado em
`Minimap.build`). Não afeta o mapa grande (#bigmap).

`.win-resizer` (borda inferior inteira) redimensiona o corpo (UI.makeResizer; lê
`offsetHeight` no mousedown, ajusta pelo delta do cursor, clamp 28–460). TODA
janela que deva redimensionar precisa de um `<div class="win-resizer"
data-resize="ID-DO-CORPO">` no HTML — inv-grid, battle-list, skills-body têm.
combat-bar é movível e tem MINIMIZAR (—) mas NÃO fecha.

Item drag-and-drop = sistema `Drag` nos `.inv-slot` (separado do drag de janela,
que é só no header). Durante o arraste, `Drag.highlight` marca SÓ o slot exato
sob o cursor com `.drop-hover` (tracejado dourado) — apenas `.inv-slot/.equip-slot`
(NÃO a janela inteira nem o mapa; o usuário reclamou de "tracejados pela tela
inteira" — `.container-panel` e `#canvas-wrap` foram removidos do alvo). Dropar no
chão mostra só o "fantasma" do item. `.container-panel.dragging` = só opacidade
(sem tracejado).

### Pathfinding — PRIORIDADE ORTOGONAL (player & monstros)
`world.find_path_smart(z,sx,sy,tx,ty,**kw)` é o pathfinder padrão: (1) tenta
`find_path(allow_diag=False)` — só cardeal; (2) se existir rota ortogonal, usa-a
MESMO que mais longa que uma diagonal; (3) só quando NÃO há rota cardeal nenhuma,
chama `find_path(allow_diag=True, diag_penalty=True)` como último recurso. NUNCA
prioriza diagonal. `find_path` agora tem dois modos: BFS uniforme (rápido, default)
e, com `diag_penalty=True`, Dijkstra com custo cardeal=1 / diagonal=3 → MINIMIZA o
nº de diagonais (diagonal só pra "sair" do bloqueio, depois volta ao ortogonal).
Diagonal nunca corta quina de PAREDE (exige os 2 ortogonais livres).

**CONTORNAR criaturas — `Game._player_path(p, tx, ty)`** é o helper de TODA
caminhada do player (h_walkto, player_autowalk recalc, _walk_then, player_follow):
monta `avoid` = tiles de criaturas (monstros/NPCs/players) num raio 16 e tenta
`find_path_smart(avoid=...)` → ROTA AO REDOR. Se não houver desvio, faz fallback
`find_path_smart` sem avoid (encara e o autowalk recontorna conforme elas andam).
Só devolve None quando NÃO existe caminho nenhum. Isso conserta o bug "clico atrás
de 3 monstros e o personagem fica parado". player_autowalk recalcula com avoid a
cada tile ocupado e só desiste após ~3s sem rota. Monstros: step_toward usa
find_path_smart com avoid de criaturas.

### Movimento dos monstros em combate (server) — 20% + box de 2a camada
monster_ai: dist<=1 → ataca; considera reposicionar a cada `2*step_dur` com
**20%** de chance (`_reposition` anda p/ um SQM cardeal válido colado no alvo,
preferindo o lado menos lotado — SEM trava de "só se melhora o aperto", senão
monstro SOLO nunca andava). dist>1: se o alvo já está totalmente cercado
(`_target_boxed` = nenhum tile livre adjacente ao alvo), o monstro NÃO recalcula
rota/dança — vira-se pro alvo e espera (next_move += 3*step_dur), formando a 2a
camada; quando abre vaga, avança. Senão, step_toward normal.

### Empurrar criaturas (push, estilo Tibia)
Arrastar uma CRIATURA no mapa empurra-a 1 SQM. Cliente: canvas mousedown sobre um
tile com monstro → `Drag.begin({kind:"creature",id,x,y})` (clique sem mover ainda
ataca; só vira push se arrastar >5px). Drop → `{type:"push", id, tx, ty}`. Server
`h_push`: valida player encostado na criatura (Chebyshev<=1), destino encostado na
criatura (==1 SQM), tile andável/livre/sem PZ/sem no_monster, diagonal sem cortar
quina; move com `move_creature` na MESMA velocidade do monstro (dur = step_dur,
ou 2x em diagonal). **Cooldowns (anti-spam, sensação de peso):** `p.next_push`
= now + `PUSH_CD_MS` (700ms) — o jogador não empurra de novo antes disso;
`m.push_until` = now + dur — a criatura precisa CONCLUIR o passo antes de poder
ser re-empurrada; `m.next_move` += dur (a IA dela espera concluir). Monstros têm
`pushable` (default True; futuro `"pushable": false` em monsters.json p/ bosses).

### Alvo selecionado: retângulo VERMELHO SÓLIDO + tecla Espaço
No game-canvas (render.js frame): `ctx.strokeStyle="#e33"; lineWidth=2;
strokeRect(dx+1,dy+1,T-2,T-2)`. O usuário testou tracejado e REJEITOU — vermelho
sólido "igual sempre foi". NÃO trocar por dashed/overlay. **Espaço** (input.js
`cycleTarget`): cicla o próximo MONSTRO visível (G.entities kind=="monster" do
andar, ordenado por distância, wrap no fim; ignora NPC), funciona com a Battle
fechada.

### HP não regenera em PZ (server)
player_regen: HP só sobe se `not world.in_pz(p.x,p.y,p.z)`. Poção/magia ainda
curam em PZ; MP regenera normal. (PZ-lock de logout/combate é outra coisa.)

### NPCs: HP + barra + vagueio por raio (server)
`Npc(Creature)` herda HP/maxhp da base (todas as criaturas compartilham
Creature). Config opcional em `data/npcs.json` por NPC: `hp`, `walks` (default
True), `walkRadius` (2), `walkMin`/`walkMax` (4000/9000 ms), `invulnerable`
(True), `attackable` (False). `Game.npc_ai(npc, now)` (chamado no tick p/ cada
npc): ocasionalmente (timer walkMin–walkMax, ~40% de chance de virar passo) dá UM
passo CARDEAL dentro do `walkRadius` do `home`, respeitando walkable/ocupado/
no_monster (NPCs PODEM andar em PZ; só não pisam em buracos/escadas). NPCs ficam
em `by_pos` → o `_player_path` já os contorna (obstáculo temporário). Cliente
(render.js) desenha a barra de vida p/ qualquer criatura com `maxhp` (NPCs
inclusos). Combate contra NPC ainda NÃO está ligado (invulnerable por default); os
campos `invulnerable`/`attackable` ficam prontos p/ mecânicas futuras (escolta,
pet, summon). NÃO mira NPC: h_attack só aceita monstro/player; Espaço (cycleTarget)
ignora NPC.

### Backpack / itens empilháveis (estilo Tibia)
- **Slot da backpack equipada NUNCA é substituído por arraste.** Cliente
  (input.js resolve): `intoBag = eqSlot=="backpack" && bagWorn`. Com bag worn,
  soltar qualquer coisa no slot = guardar DENTRO (inv source = no-op pois já está
  na bag; ground = pickup; corpo = loot; equip = unequip). Sem bag worn, soltar
  uma bag = equipa (a única forma de trocar é dropar a atual e equipar outra).
- **Compactação automática**: `Player.compact_inv()` empacota itens nos primeiros
  slots (sem buracos). `inv_payload()` chama compact_inv IN-PLACE → os índices
  vistos pelo cliente sempre batem com o servidor. Remover/mover item nunca deixa
  buraco (pedido do usuário). h_move_item virou reorder/merge/split + compacta.
- **Split de pilha (count)**: toda mensagem de movimento aceita `count`. Cliente:
  `Drag.commit(send,count,stackable,ctrl)` — CTRL ou item não-stackável = pilha
  inteira; senão abre `UI.askQuantity` (popup `#qty-modal`: input + slider +
  botões 1/10/50/100/Tudo + Confirmar/Cancelar). Server divide via `_split_count`/
  `_take_from_slot`/`_take_from_container`/`_container_add` (empilha iguais).
  Vale para inv↔inv, inv↔chão, inv↔container, container↔container (`loot_to`),
  container→chão, chão→bag. Containers empilham iguais ao receber.
- Cuidado: como o inv compacta, dropar um item "no slot 7" NÃO o fixa lá — ele
  volta pro primeiro slot livre. O smoke_test foi atualizado p/ esse comportamento.

### Barra de combate = TODOS os botões juntos, só ÍCONES, grade 4-col
`#combat-bar` (.container-panel.movable) tem `#combat-controls` (CSS GRID
`repeat(4,1fr)` → 4 quadradinhos por linha preenchendo a largura, quebra depois)
com 9 botões SÓ DE ÍCONE: ⚔ `#st-attack` / ⚖ `#st-balanced` / 🛡 `#st-defense` /
☠ `#btn-pvp` / 🧍 `#btn-follow` / ☰ `#btn-battle` / 💪 `#btn-skills` / ⌨
`#btn-hotkeys` / 🚪 `#btn-logout`. (Sem texto; `#btn-help`/"?" REMOVIDO; o
`#window-buttons` da sidebar e o `#btn-battle2` também já tinham saído.) Posturas/
alvo escurecem (.55) quando inativos; `.active` realça. Wiring por getElementById.

### Faixas ao redor do mapa = material da interface (não preto)
`#canvas-wrap` (onde o canvas 480x352 letterboxa) tem `background: linear-gradient`
nos tons do painel + `box-shadow: inset` (profundidade) — integra o mapa ao
cliente em vez de barras pretas. O canvas do jogo ainda pinta #000 só DENTRO do
mapa (vazio do mundo), separado dessas faixas.

### Aggro por visão (server)
monster_ai: o monstro mira quem estiver no retângulo config.AGGRO_X/Y (9x7 ≈
tela do jogador +2) OU no raio `aggro` próprio. Assim bicho que aparece na
tela vem atrás. Retenção (leash) = aggro*2+4.

### Container = TODOS os slots
_container_payload manda `slots` = capacity da mochila (corpo = nº de itens).
Cliente renderiza `slots` células (vazias incluídas, droppáveis). Arrastar item
da mochila p/ a `.container-panel[data-ckey]` = `store` (cabe em mochila no
chão também).

### Containers/mochilas (regras críticas — NÃO regredir)
- Mochila no chão É um container abrível (items.json backpack tem
  `"container": true`). `_is_container`/`_top_container` aceitam corpo OU
  qualquer item com flag container; inicializam `contents=[]` lazy.
- NUNCA perder `contents`: use `_give_item` (não `give`) ao pegar/saquear, e
  copie o ITEM INTEIRO ao dropar (h_drop preserva todas as chaves). `give`/
  inv_add só guardam {id,count} — use só para itens sem contents.
- `h_store` (msg "store"): guarda item da mochila DENTRO de um container
  aberto (mochila dentro de mochila, sem perda). Cliente: arrastar item da
  mochila e soltar sobre uma `.container-panel[data-ckey]`.
- Interações de chão andam-até-lá: `_walk_then(p,tx,ty,fn)` + `p.pending`
  processado por `player_pending` no tick. Usado por h_pickup/h_open_container/
  h_move_ground. Cliente manda a ação SEMPRE (não walkto antes); servidor anda.
  pending é cancelado por movimento manual e morte.
- **PARA NO SQM ANTERIOR (não pisa no alvo):** quando a interação dispara,
  `player_pending` ZERA `p.path` (chave! senão o último passo ainda pisava no
  tile do item no tick seguinte, pois pending já estava None). Reforço extra em
  `player_autowalk`: se o próximo passo == tile pendente, não pisa. Assim arrastar
  item do chão deixa o personagem 1 SQM ANTES (range p/ pegar/empurrar), nunca em
  cima. Verificado: item (26,42) → personagem para em (25,42).
- **Arraste no mapa: ITENS antes de CRIATURA.** input.js canvas mousedown checa
  a pilha do chão PRIMEIRO (arrasta item); só sem itens é que pega a criatura
  (empurrar). Clique sem mover ainda ataca o bicho.
- **Mover item do chão: ANDA até o item, move com CONTATO, joga LONGE.**
  `h_move_ground` usa `_walk_then(p,fx,fy,fn)`: o personagem CAMINHA até encostar
  no item (para no SQM anterior, adjacente — graças ao `player_pending` que zera
  o path em dist<=1) e só então `_do_move_ground`. Trava defensiva: só move se
  dist(p,(fx,fy))<=1 (nunca com gap). O DESTINO pode ser longe (`THROW_RANGE=7`,
  dentro da tela); fora disso/parede cai aos pés. (h_drop inv→chão = DROP_RANGE 3,
  à parte.) Verificado: item a 3 SQM → personagem anda até dist 1 e então move ✓.

### Clique no mundo (importante)
`Render.screenToTile` respeita o letterbox (object-fit:contain) e retorna
**null** nas bordas pretas — todos os callers checam null (nada acontece ali).
`Input.entityAt` casa o tile de ORIGEM e DESTINO durante a animação, senão
não dá pra clicar num bicho que está andando (posição visual ≠ lógica).

### Combate
- Posturas: ⚔ attack (1.25 dmg / 0.6 def), ⚖ balanced, 🛡 defense (0.7/1.4).
- Melee: dano = skill da arma (wclass fist/club/sword/axe) + atk + level/5.
- **Distância**: arco (17, alcance 6) consome flecha (19) do slot ammo;
  lança (18, alcance 3) é consumida ao atirar (**NÃO cai no chão** — decisão
  do usuário). Projétil animado (`proj`). Skill `distance`.
- PvP: botão na sidebar; **ambos** precisam estar com PvP ligado, **fora da
  PZ** (mensagens claras quando bloqueado — testado com 2 contas).
- **Locks de combate (estilo Tibia)**: lutar com monstro = lock PvE 10s (só
  bloqueia o botão Sair). AGREDIR um jogador = lock PvP 60s + CAVEIRA ☠
  visível 120s (renovam por golpe): sem logout, sem entrar na PZ
  (_pz_entry_blocked em try_move/autowalk) e fechar o cliente NÃO salva —
  o personagem fica no mundo (lingering) até o lock expirar (tick remove).
  Morte limpa caveira e locks. eskull broadcast; espawn traz "skull".
- **Follow**: botão "Foll" segue o alvo (rota BFS persistente no tick,
  player_follow); cancela se alvo morrer/sumir/longe (>16), por movimento
  manual, ESC ou clique no botão. clear_target centraliza target+follow.
- **Logout**: botão "Sair" valida locks (mensagem com segundos restantes);
  handle_disconnect decide linger vs sair na queda de conexão.
- Morte: -10% exp (não rebaixa level), volta ao templo cheio.

### IA dos monstros (muito iterada — cuidado ao mexer)
- Aggro raio 6-8; alvo mais próximo, ignora ghost/PZ/outro andar.
- Persegue com passos CARDEAIS (zigue-zague); **diagonal SÓ como último
  recurso** (usuário insistiu — não priorizar diagonal). Vagueio cardeal.
- **Follow**: caminho direto bloqueado → rota BFS persistente
  (`m.follow_path`, até 80 passos, contorna paredes mesmo saindo da tela);
  coleira folgada (aggro+14) enquanto segue; se outra criatura bloquear a
  rota, dá um passo aleatório para desfazer bolo e recalcula.
- BFS de monstro evita PZ + no_monster (find_path avoid_pz=True).

### Skills (treino por uso)
`fist club sword axe distance shield fishing magic` — golpe treina arma,
apanhar de escudo treina shield, mana gasta treina magic, pescar treina
fishing. Velocidade por vocação (factors em formulas.VOCATIONS).
Janela de Skills (botão na sidebar) mostra level/exp/cap + skills.

### Vocações (registro)
knight (+15hp/lvl, melee rápido), paladin (+10/+15, distance rápido),
sorcerer/druid (+5/+30, magic rápido). Level 1 = 150hp/50mp p/ todas.

### Magias (faladas no chat)
exura (todos, lvl1), utani hur (todos, lvl3, haste), exori (knight, lvl8),
exori con (paladin, lvl8, alcance 5), exevo flam (sorcerer, lvl8, cone),
exura gran (druid, lvl9). Escalam com magic level.

### Pesca
Vara (73) + água adjacente (8 vizinhos) → peixe (53). Chance 0.25+skill*1.5%.

### Hotkeys
F1-F12 e 0-9; janela de config (botão na sidebar); tipo "say" (fala/magia)
ou "use" (item por id). Persistidas no DB (coluna hotkeys), vêm no welcome.

### Chat
Abas: Default / Server Log / Loot / NPC / PM (bolinha de não-lido).
`/pm <nome> <msg>` (aceita nome com até 3 palavras, prefix-match).

### Interface (sidebar, estado atual)
- Janela "Equipamento" (Lv no título): cruz de slots + **Cap embaixo do Ring**
  e **Atk/Def embaixo do Ammo**; controles ⚔⚖🛡/PvP/Foll em coluna ao lado.
  #char-info foi REMOVIDO (sem nome/voc/andar/ouro/fed na sidebar).
- Scrollbars SEMPRE visíveis (overflow-y: scroll) em grids/listas — slots de
  36px não mexem quando a barra aparece. Sem overflow-x em lugar nenhum.
- Chat redimensionável pelo divisor (#chat-resizer) acima das abas; altura
  persiste em localStorage (fibula_chatH) — o mapa flexa junto.
- Minimapa: rosa dos ventos overlay (8 direções + ● seguir) + ⛶ expandir;
  **auto-centra ao andar** (emove próprio → Minimap.center()).
- Nomes/barras/caveira/números: desenhados numa CAMADA SEPARADA `#fx-canvas`
  (overlay em resolução nativa, antialiased) — NÃO no canvas pixelado, senão
  o texto borra no upscale nearest-neighbor. render.js coleta `_labels`/`_wtext`
  no frame e `drawOverlay()` mapeia internal→display (mesma transform
  object-fit:contain: `_ovS/_ovX/_ovY`) com `octext()`/`obar()`. Fonte ~10px.
- Follow é um MODO (chase, estilo Tibia): fica armado mesmo sem alvo; ao mirar
  algo persegue sozinho. Cancela só ao mover manualmente DURANTE a perseguição
  (break_follow_on_manual_move: exige follow_on E target_id). Ícone 🏃/🧍.

## 6. Movimento (cliente)

WASD/setas; **diagonais: Q E Z C** ou duas teclas juntas (passo diagonal 2x
mais lento). Clique no chão/minimapa/mapa-múndi = autowalk (BFS no server,
ESC cancela via msg `stop`). G pega do chão. Clique direito = olhar (mapa e
slots). Duplo clique = usar/equipar. Drag&drop completo (mochila ↔ equip ↔
chão ↔ corpo; chão→slot de equip = equip_ground).

## 7. Comandos

Todos: `/help /online /save /pm`. Admin: `/goto x y [z]`, `/spawn <bicho>
[n]`, `/item <id> [n]`, `/heal`, `/ghost` (monstros não enxergam),
`/itens` (lista ids), `/bichos` (lista monstros), `/level <n>`,
`/skill <punho|clava|espada|machado|distancia|escudo|pesca|magia> <n>`.

## 8. Dados (data/*.json) — ids úteis

- Itens: 1 ouro · 10-16 armas melee (16=espada de fogo atk22) · 17 arco ·
  18 lança · 19 flecha · 20-25 armaduras · 30-32 escudos (32=dragão) ·
  33 amuleto · 34 anel da vida · 40/41 poções · 50-53 comidas (53=peixe) ·
  70/71 mochilas · 72 corda · 73 vara · 90 corpo (container, pickable false).
- Monstros: rat snake wolf troll orc skeleton bat spider ghoul dragon
  dragon_lord (dropa espada de fogo/mochila grande/escudo dragão/anel).
- **Sprites: NUNCA reordene a lista SPRITES em gensprites.py** — os índices
  precisam ser estáveis; só acrescente no final e rode o gerador.
- Estilo visual = Realm of the Mad God: `main()` aplica pós-processo por
  categoria — `add_shadow()` (figuras em pé, set SHADOWED) e `add_outline()`
  (tudo que NÃO está em TILING; contorno escuro 1px). Chão usa `noise()` +
  `blobs()` com paleta saturada. NÃO dê outline em tiles (cria grade/seams).
  Trocar sprites exige F5 no cliente (sprites carregam no boot, loadAssets).
- Sprites DIRECIONAIS: `humanoid(...facing=)` desenha frente(s)/costas(n)/
  perfil(e). main() gera variantes `_n` e `_e` p/ os nomes em DIRECTIONAL
  (player, npc_*, troll, orc, ghoul). Cliente (render.blitCreature) escolhe
  por e.dir; OESTE = `_e` espelhado (blitFlipped); sul/sem frame = base.
  Adornos (símbolo/avental/presas/clava) só no frame de frente.
- ANIMAÇÃO de caminhada (2 frames/direção): humanoid(...step=) muda as pernas
  (0 parado, 1 passada). main() gera por direção: PARADO + 1 frame `_a`
  (player_a, player_n/_n_a, player_e/_e_a). Cliente (blitCreature) alterna
  PARADO↔andando (stem ↔ stem+"_a") a cada 180ms ENQUANTO se move
  (moving = now < animStart+animDur). Bichos sem _a (rato, lobo...) = bob 1px.
- PATHFINDING dos monstros: step_toward tenta passo cardeal direto; se
  bloqueado usa find_path com `avoid` = tiles de OUTRAS criaturas perto
  (_creatures_near, raio 12) → contorna paredes E grupos de bichos. NÃO anda
  aleatório ao falhar (espera/recalcula via path_stuck>=3). Coleira de
  retenção = aggro*2+4 (não larga o alvo no meio do contorno). find_path tem
  `avoid`/`max_nodes` (teto de custo). Sem follow_path bonus na coleira.
- Mudou genmap.py? Rode-o e REINICIE o servidor (mapa carrega no boot).

## 9. Armadilhas conhecidas

- Linhas pretas entre tiles = alguém desenhou com coordenada fracionária.
  Câmera e blit usam Math.round — mantenha assim.
- `inv` payload tem `active` (slots utilizáveis) — o cliente PRECISA guardar
  (`G.inv.active`) e renderizar só esses.
- Mensagens `espawn` antigas na fila enganam scripts de teste (pegue por
  NOME do monstro e limpe a fila antes de /spawn). `lastInv()`/última-msg
  para estado de inventário.
- h_use de ferramenta (corda/vara) retorna ANTES do bloco que consome o
  item — ferramentas não são consumidas; não mova esse return.
- O fluxo de equipar mochila despeja `contents` (`_try_unpack_backpack`);
  swap de mochila exige slots além da nova capacidade vazios.
- Smoke test mata um rato indo A PÉ do templo (valida mapa andável). Se o
  usuário estiver caçando ratos junto, pode flakear — o teste avisa e tenta
  outro monstro.

## 10. Histórico de decisões (o "porquê")

- Stack stdlib-only: roda com `python` puro em qualquer máquina (pedido:
  "totalmente executável localmente").
- PvP opt-in dos DOIS lados (modo duelo) — usuário aprovou; PvP aberto com
  skull ficou como ideia futura.
- Lança não cai no chão (usuário pediu explicitamente, anti-Tibia).
- Escada: descer automático / subir por clique (iterado 2x até esse formato).
- Sem bolsos: slots só com mochila (iterado: 20 fixos → 8+16 → 0+capacity).
- Aviso de respawn 5s (bolinha azul) DENTRO do tempo total de respawn.
- Sprites são placeholders gerados por código — trocar por arte real =
  substituir sprites.png mantendo índices.

## 11. Roadmap / ideias não feitas

- Runas, mais magias, PvP aberto com skulls, party, depot, quests,
  mais andares/cidades, balanceamento fino, arte real, sons.
- "Pegar tudo" no corpo (botão) — oferecido, usuário não pediu ainda.
