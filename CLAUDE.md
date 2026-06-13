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
    **DESCER é automático ao pisar; SUBIR só clicando** (use_stairs).
  - `holes`: buraco em (75,48,0) → cai ao pisar (check_hole).
  - `ropes`: rope spot (75,48,1) → use item corda para subir.
- Lago a oeste (x≤13) — pesca na praia (x=14).
- Monstros NUNCA pisam em portals/holes/ropes (`world.no_monster`).
- Subsolo é escuro no cliente (círculo de luz ao redor do player).
- Respawn: lento (45s ratos … 15min lorde dragão); **bolinha azul pulsante
  5s antes** do nascimento (`spawn_warn`). Aviso faz parte do tempo total.

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

### Equipamento (10 slots)
`helmet necklace backpack armor weapon shield legs boots ring ammo`
(nomes internos antigos mantidos por compat de save; cliente mostra
Head/Right Hand/Left Hand etc., em cruz). `TYPE_TO_SLOT` em entities.py.
- Anel da vida (34): efeito "fed" (regen rápido). Amuleto proteção (33): +2 arm.
- Itens equipados não vendem no NPC (badge "equipado" na loja + msg).

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

### Janelas em COLUNAS DE DOCK (2 esquerda + 1 direita, recolhíveis)
TRÊS colunas de encaixe: `#dock-left` e `#dock-left2` (à esquerda da tela) e
`#dock-right` (dentro da `#sidebar`, abaixo do minimapa/HP/MP). Cada dock tem um
`.dock-body` (id `dock-left-body`/`dock-left2-body`/`dock-right-body`) onde as
janelas `.container-panel.movable` (equip, combat-bar, battle, inv, skills) ficam.
Arrastar o `.cont-header` MOVE a janela ENTRE qualquer coluna e reordena por Y
(`UI.makeWindowMovable` + `UI.dockAt` → devolve o `.dock-body` da coluna sob o X,
ignorando colunas recolhidas). NUNCA flutua. Layout persiste em
`localStorage["fibula.dock"]` (`saveDockLayout`/`restoreDockLayout`, por body id).
`.dock-body:empty::before` = dica "arraste janelas". `.dock-body.dock-target` =
realce suave do destino. Drop de loot/ground aceita `#sidebar, #dock-left,
#dock-left2, #dock-right` (input.js `inCols`).

RECOLHER: cada dock tem botão `.dock-collapse[data-dock]`. Esquerdas começam
RECOLHIDAS (class `collapsed` no HTML) — viram tira fina de 18px só com a seta
(`#dock-left.collapsed` → flex-basis:18px, `.dock-body` some). A direita recolhe
pelo `#dock-right-toggle` posicionado no canto do minimapa (pedido do usuário:
"acima e ao lado do minimapa"). `UI.toggleDock`/`updateDockArrows`/`initDockToggles`
persistem o estado em `localStorage["fibula.dockcollapse"]`. Setas: esquerdas
`‹`=recolher/`›`=expandir; direita invertida.

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
Diagonal nunca corta quina de PAREDE (exige os 2 ortogonais livres). `avoid` =
tiles de criaturas (contorna grupos). Call-sites do player (h_walkto,
player_autowalk recalc, _walk_then×2, player_follow) e dos monstros (step_toward)
usam `find_path_smart`. `_monster_step`/player_autowalk ainda tratam custo 2x do
passo diagonal quando ele acontece.

### Reposicionamento DINÂMICO em combate (server)
monster_ai: quando dist<=1 e o ataque em cooldown, a cada `step_dur` com 35% de
chance chama `_reposition` (antes era 10% e ficava preso — usuário pediu mais
dinâmico, cercar). `_reposition` dá UM passo CARDEAL para um SQM livre ainda
colado no alvo, preferindo o lado MENOS lotado de monstros (`crowd()` conta
monstros vizinhos) → espalha/cerca o jogador. NUNCA diagonal no ataque; sem
cardeal válido fica parado. Chase (dist>1) usa step_toward→find_path_smart.

### Empurrar criaturas (push, estilo Tibia)
Arrastar uma CRIATURA no mapa empurra-a 1 SQM. Cliente: canvas mousedown sobre um
tile com monstro → `Drag.begin({kind:"creature",id,x,y})` (clique sem mover ainda
ataca; só vira push se arrastar >5px). Drop → `{type:"push", id, tx, ty}`. Server
`h_push`: valida player encostado na criatura (Chebyshev<=1), destino encostado na
criatura (==1 SQM), tile andável/livre/sem PZ/sem no_monster, diagonal sem cortar
quina; move com `move_creature` na MESMA velocidade do monstro (dur = step_dur,
ou 2x em diagonal — o usuário reclamou que "corriam muito" com dur fixo). `m.next_move`
recebe o mesmo dur (anti-spam). Monstros têm `pushable` (default True; futuro:
`"pushable": false` em monsters.json p/ bosses).

### Alvo selecionado: retângulo VERMELHO SÓLIDO
No game-canvas (render.js frame): `ctx.strokeStyle="#e33"; lineWidth=2;
strokeRect(dx+1,dy+1,T-2,T-2)`. O usuário testou tracejado e REJEITOU — quer
vermelho sólido "igual sempre foi". NÃO trocar por dashed/overlay.

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

### Barra de combate independente
`#combat-bar` (.container-panel.movable, FORA do #equip-window): Attack/Balance/
Defense/PvP/Follow/☰. Sempre visível (minimizar/fechar equip ou mochila NÃO a
afeta — é sibling), movível pelo header, SEM botão fechar/minimizar.

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
