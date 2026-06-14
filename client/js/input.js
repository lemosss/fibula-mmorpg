/**
 * input.js — Teclado, mouse e drag & drop.
 *
 * Movimento: WASD/setas (segurar anda; duas teclas = diagonal). Clique
 * esquerdo: atacar / falar / pegar / andar / usar escada. Clique direito:
 * olhar. G: pegar do próprio tile. Enter: chat. ESC: parar.
 *
 * Arrasto (mousedown + mover >4px):
 *   mochila -> mochila      mover/juntar pilha
 *   mochila -> equipamento  equipar
 *   mochila -> mapa         jogar no chão (até 3 tiles)
 *   equipamento -> mochila  desequipar
 *   equipamento -> mapa     jogar no chão
 *   chão -> mochila         pegar (loot!)
 *   chão -> chão            arrastar o item no chão
 */

/* ============================ DRAG & DROP ============================ */

const Drag = {
  src: null,            // {kind:"inv",i} | {kind:"equip",eslot} | {kind:"ground",x,y}
  started: false,
  justEnded: false,
  sx: 0, sy: 0,
  ghost: null,

  begin(src, ev, sprite) {
    this.src = src;
    this.started = false;
    this.sx = ev.clientX;
    this.sy = ev.clientY;
    this.sprite = sprite;
  },

  init() {
    this.ghost = document.getElementById("drag-ghost");
    document.addEventListener("mousemove", (ev) => this.onMove(ev));
    document.addEventListener("mouseup", (ev) => this.onUp(ev));
    // um arrasto concluído engole o "click" que o navegador dispara depois
    document.addEventListener("click", (ev) => {
      if (this.justEnded) {
        this.justEnded = false;
        ev.stopPropagation();
        ev.preventDefault();
      }
    }, true);
  },

  onMove(ev) {
    if (!this.src) return;
    if (!this.started) {
      if (Math.hypot(ev.clientX - this.sx, ev.clientY - this.sy) < 5) return;
      this.started = true;
      this.ghost.innerHTML = "";
      this.ghost.appendChild(UI.spriteCanvas(this.sprite));
      this.ghost.classList.remove("hidden");
    }
    this.ghost.style.left = (ev.clientX + 6) + "px";
    this.ghost.style.top = (ev.clientY + 6) + "px";
    this.highlight(ev);                   // linha pontilhada no alvo de soltura
  },

  /** Marca com tracejado APENAS o slot exato embaixo do cursor (destino). */
  highlight(ev) {
    const el = document.elementFromPoint(ev.clientX, ev.clientY);
    // só o slot preciso (mochila/equip/container) — nunca a janela inteira
    // nem o mapa, pra não poluir a tela com tracejados durante o arraste
    const tgt = el && el.closest
      ? el.closest(".inv-slot, .equip-slot")
      : null;
    if (tgt === this.hoverEl) return;
    if (this.hoverEl) this.hoverEl.classList.remove("drop-hover");
    this.hoverEl = tgt;
    if (tgt) tgt.classList.add("drop-hover");
  },

  clearHighlight() {
    if (this.hoverEl) { this.hoverEl.classList.remove("drop-hover"); }
    this.hoverEl = null;
  },

  onUp(ev) {
    if (!this.src) return;
    const src = this.src;
    const started = this.started;
    this.src = null;
    this.started = false;
    this.ghost.classList.add("hidden");
    this.clearHighlight();
    if (!started) return;                 // foi só um clique normal
    this.justEnded = true;
    this.resolve(src, ev);
  },

  /** Quantidade da pilha de origem (para split). */
  srcStack(src) {
    let it = null;
    if (src.kind === "inv") it = G.inv.slots[src.i];
    else if (src.kind === "container") {
      const c = G.containers.get(src.cx + "," + src.cy);
      it = c && c.items[src.idx];
    } else if (src.kind === "ground") {
      const me = myPlayer();
      const pile = me && G.ground.get(groundKey(src.x, src.y, me.z || 0));
      it = pile && pile[pile.length - 1];
    }
    const count = it ? (it.count || 1) : 1;
    const stackable = it ? !!(ItemDefs[it.id] || {}).stackable : false;
    return { count, stackable };
  },

  /**
   * Move stackable: CTRL = pilha inteira; senão abre o seletor de quantidade.
   * Itens não-empilháveis (ou pilha de 1) movem direto. `send(n)` envia a ação.
   */
  commit(send, count, stackable, ctrl) {
    if (!stackable || count <= 1 || ctrl) { send(count); return; }
    UI.askQuantity(count, this.sprite, (n) => { if (n > 0) send(n); });
  },

  /** Decide a ação conforme onde o item foi solto. */
  resolve(src, ev) {
    const el = document.elementFromPoint(ev.clientX, ev.clientY);
    const close = sel => (el && el.closest ? el.closest(sel) : null);
    // container do CHÃO aberto (corpo/mochila) tem data-ckey "x,y"
    const contEl = close(".container-panel[data-ckey]");
    const cont = contEl ? contEl.dataset.ckey.split(",").map(Number) : null;
    const slotEl = close(".inv-slot");
    // slot REAL da mochila = .inv-slot que NÃO está dentro de um container
    const invSlot = (slotEl && !contEl) ? slotEl : null;
    const eqSlot = close(".equip-slot");
    const onCanvas = !!close("#canvas-wrap");
    const tile = onCanvas ? Render.screenToTile(ev.clientX, ev.clientY) : null;
    const inCols = !!close(".dock-col, #sidebar");
    const ctrl = ev.ctrlKey;
    const { count, stackable } = this.srcStack(src);
    // slot da mochila equipada COM uma bag = guardar dentro (nunca substituir)
    const bagWorn = !!(G.inv.equip && G.inv.equip.backpack);
    const intoBag = eqSlot && eqSlot.dataset.eslot === "backpack" && bagWorn;

    if (src.kind === "inv") {
      if (invSlot) {
        const j = parseInt(invSlot.dataset.i, 10);
        if (j !== src.i) this.commit(
          n => Net.send({ type: "move_item", from: src.i, to: j, count: n }),
          count, stackable, ctrl);
      } else if (cont) {
        this.commit(
          n => Net.send({ type: "store", slot: src.i, x: cont[0], y: cont[1],
                          count: n }), count, stackable, ctrl);
      } else if (intoBag) {
        // o item já está na mochila — nunca troca a bag equipada
      } else if (eqSlot) {
        Net.send({ type: "equip", slot: src.i });   // equipa (bag só se nenhuma)
      } else if (tile) {
        this.commit(
          n => Net.send({ type: "drop", slot: src.i, x: tile.x, y: tile.y,
                          count: n }), count, stackable, ctrl);
      }
    } else if (src.kind === "equip") {
      if (tile) {
        Net.send({ type: "drop_equip", eslot: src.eslot, x: tile.x, y: tile.y });
      } else {
        Net.send({ type: "unequip", eslot: src.eslot });
      }
    } else if (src.kind === "ground") {
      if (intoBag) {                                 // chão -> bag equipada: pega
        this.commit(n => Net.send({ type: "pickup", x: src.x, y: src.y,
                                    count: n }), count, stackable, ctrl);
      } else if (eqSlot) {                            // equipa (inclui 1a mochila)
        Net.send({ type: "equip_ground", x: src.x, y: src.y,
                   eslot: eqSlot.dataset.eslot });
      } else if (cont) {                              // chão -> container: guarda
        this.commit(n => Net.send({ type: "pickup", x: src.x, y: src.y,
                                    count: n }), count, stackable, ctrl);
      } else if (tile) {
        if (tile.x !== src.x || tile.y !== src.y) this.commit(
          n => Net.send({ type: "move_ground", fx: src.x, fy: src.y,
                          tx: tile.x, ty: tile.y, count: n }),
          count, stackable, ctrl);
      } else if (invSlot || inCols) {
        this.commit(n => Net.send({ type: "pickup", x: src.x, y: src.y,
                                    count: n }), count, stackable, ctrl);
      }
    } else if (src.kind === "creature") {
      // empurra a criatura 1 SQM (o servidor valida adjacência/bloqueios)
      if (tile && (tile.x !== src.x || tile.y !== src.y)) {
        Net.send({ type: "push", id: src.id, tx: tile.x, ty: tile.y });
      }
    } else if (src.kind === "container") {
      if (cont && cont[0] === src.cx && cont[1] === src.cy) {
        // soltou no MESMO container: nada
      } else if (cont) {                             // container -> outro container
        this.commit(
          n => Net.send({ type: "loot_to", x: src.cx, y: src.cy, idx: src.idx,
                          tx: cont[0], ty: cont[1], count: n }),
          count, stackable, ctrl);
      } else if (tile) {                             // corpo -> chão
        this.commit(
          n => Net.send({ type: "loot_ground", x: src.cx, y: src.cy,
                          idx: src.idx, tx: tile.x, ty: tile.y, count: n }),
          count, stackable, ctrl);
      } else if (invSlot || eqSlot || inCols) {      // corpo -> mochila
        this.commit(n => Net.send({ type: "loot", x: src.cx, y: src.cy,
                                    idx: src.idx, count: n }),
          count, stackable, ctrl);
      }
    }
  },
};
const Input = {
  held: new Set(),

  DIR_KEYS: {
    ArrowUp: "n", KeyW: "n",
    ArrowDown: "s", KeyS: "s",
    ArrowLeft: "w", KeyA: "w",
    ArrowRight: "e", KeyD: "e",
    // diagonais diretas (estilo numpad do Tibia)
    KeyQ: "nw", KeyE: "ne", KeyZ: "sw", KeyC: "se",
  },

  chatFocused() {
    return document.activeElement === UI.$("chat-input");
  },

  /** Direção atual a partir das teclas seguradas (combina em diagonal). */
  currentDir() {
    let v = null, h = null;
    for (const code of this.held) {
      const d = this.DIR_KEYS[code];
      if (!d) continue;
      if (d.length === 2) return d;       // Q/E/Z/C: diagonal direta
      if ((d === "n" || d === "s") && !v) v = d;
      if ((d === "e" || d === "w") && !h) h = d;
    }
    return v && h ? v + h : (v || h);     // "ne", "nw", "se", "sw" ou cardinal
  },

  init() {
    Drag.init();
    document.addEventListener("keydown", (ev) => this.onKeyDown(ev));
    document.addEventListener("keyup", (ev) => this.held.delete(ev.code));
    window.addEventListener("blur", () => this.held.clear());

    // anda continuamente enquanto a(s) tecla(s) estiverem seguradas
    setInterval(() => {
      if (!G.loggedIn || this.chatFocused()) return;
      const dir = this.currentDir();
      if (dir) Net.send({ type: "move", dir });
    }, 90);

    const canvas = UI.$("game-canvas");
    canvas.addEventListener("click", (ev) => this.onCanvasClick(ev));
    // arrasto começando num tile: criatura (empurrar) ou item no chão
    canvas.addEventListener("mousedown", (ev) => {
      if (ev.button !== 0 || !G.loggedIn) return;
      const me = myPlayer();
      if (!me) return;
      const t = Render.screenToTile(ev.clientX, ev.clientY);
      if (!t) return;                          // clicou na faixa preta
      // PRIORIDADE: itens no chão primeiro. Só quando NÃO há item é que o
      // arrasto pega a criatura (empurrar). Assim arrastar um SQM com bicho
      // EM CIMA de itens move os itens; depois de tirá-los, arrasta o bicho.
      const pile = G.ground.get(groundKey(t.x, t.y, me.z || 0));
      if (pile && pile.length) {
        const def = ItemDefs[pile[pile.length - 1].id] || {};
        Drag.begin({ kind: "ground", x: t.x, y: t.y }, ev, def.sprite);
        return;
      }
      // sem itens: criatura no tile -> arrasto de EMPURRAR (1 SQM). Clique sem
      // mover continua atacando (onCanvasClick); só vira push se arrastar >5px.
      const cr = this.entityAt(t.x, t.y);
      if (cr && cr.kind === "monster") {
        Drag.begin({ kind: "creature", id: cr.id, x: t.x, y: t.y },
                   ev, cr.sprite);
      }
    });
    canvas.addEventListener("contextmenu", (ev) => {
      ev.preventDefault();
      const t = Render.screenToTile(ev.clientX, ev.clientY);
      if (t) Net.send({ type: "look", x: t.x, y: t.y });
    });

    const chatInput = UI.$("chat-input");
    chatInput.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        const text = chatInput.value.trim();
        if (text) Net.send({ type: "say", text });
        chatInput.value = "";
        chatInput.blur();
        ev.preventDefault();
      } else if (ev.key === "Escape") {
        chatInput.blur();
      }
      ev.stopPropagation();
    });
  },

  onKeyDown(ev) {
    if (!G.loggedIn) return;
    if (this.chatFocused()) return;

    if (ev.key === "Enter") {
      UI.$("chat-input").focus();
      ev.preventDefault();
      return;
    }
    if (ev.key === "Escape") {
      if (UI.mapOpen()) UI.closeMap();
      else if (!UI.$("hotkeys-window").classList.contains("hidden"))
        UI.$("hotkeys-window").classList.add("hidden");
      else if (!UI.$("skills-window").classList.contains("hidden"))
        UI.$("skills-window").classList.add("hidden");
      else if (G.trade) UI.closeTrade();
      else if (G.containers.size) UI.closeAllContainers();
      else {
        Net.send({ type: "stop" });            // para o autowalk
        if (G.targetId) Net.send({ type: "attack", id: 0 });
      }
      UI.selectSlot(null);
      return;
    }

    // ESPAÇO: cicla para o próximo monstro visível (ignora NPCs)
    if (ev.code === "Space") {
      this.cycleTarget();
      ev.preventDefault();
      return;
    }

    // hotkeys configuráveis: F1-F12 e dígitos 0-9
    const hkKey = ev.key.length === 1 && ev.key >= "0" && ev.key <= "9"
      ? ev.key : (/^F\d{1,2}$/.test(ev.key) ? ev.key : null);
    if (hkKey && G.hotkeys[hkKey]) {
      const hk = G.hotkeys[hkKey];
      if (hk.type === "say" && hk.text) {
        Net.send({ type: "say", text: hk.text });
      } else if (hk.type === "use" && hk.item) {
        const idx = G.inv.slots.findIndex(s => s && s.id === hk.item);
        if (idx >= 0) Net.send({ type: "use", slot: idx });
        else UI.chatLine("info", "", "Voce nao tem esse item na mochila.");
      }
      ev.preventDefault();
      return;
    }
    if (ev.code === "KeyG") {
      const me = myPlayer();
      if (me) Net.send({ type: "pickup", x: me.x, y: me.y });
      return;
    }
    if (this.DIR_KEYS[ev.code]) {
      this.held.add(ev.code);
      const dir = this.currentDir();
      if (dir) Net.send({ type: "move", dir });
      ev.preventDefault();
    }
  },

  /** Criatura num tile do andar atual (preferindo monstros).
      Durante a caminhada casa TANTO o tile de destino quanto o de origem,
      senão não dá pra clicar num bicho que está se movendo. */
  entityAt(x, y) {
    const me = myPlayer();
    const z = (me && me.z) || 0;
    const now = performance.now();
    let found = null;
    for (const e of G.entities.values()) {
      if ((e.z || 0) !== z) continue;
      const animating = e.animDur > 0 && now < e.animStart + e.animDur;
      const hit = (e.x === x && e.y === y) ||
                  (animating && e.fromX === x && e.fromY === y);
      if (hit) {
        if (e.kind === "monster") return e;
        found = found || e;
      }
    }
    return found;
  },

  /** Espaço: seleciona o próximo monstro visível (ordenado por distância). */
  cycleTarget() {
    const me = myPlayer();
    if (!me) return;
    const z = me.z || 0;
    const mons = [...G.entities.values()]
      .filter(e => e.kind === "monster" && (e.z || 0) === z)
      .sort((a, b) => {
        const da = Math.max(Math.abs(a.x - me.x), Math.abs(a.y - me.y));
        const db = Math.max(Math.abs(b.x - me.x), Math.abs(b.y - me.y));
        return da - db || a.id - b.id;
      });
    if (!mons.length) return;
    const idx = mons.findIndex(e => e.id === G.targetId);
    const next = mons[(idx + 1) % mons.length];   // wrap: último -> primeiro
    Net.send({ type: "attack", id: next.id });
  },

  onCanvasClick(ev) {
    if (!G.loggedIn) return;
    const t = Render.screenToTile(ev.clientX, ev.clientY);
    if (!t) return;                            // clicou na faixa preta
    const e = this.entityAt(t.x, t.y);
    const me = myPlayer();
    const dist = me ? Math.max(Math.abs(t.x - me.x), Math.abs(t.y - me.y)) : 99;

    if (e && e.kind === "monster") {
      Net.send({ type: "attack", id: e.id });          // ataca / cancela
      return;
    }
    if (e && e.kind === "player" && e.id !== G.myId) {
      // PvP: o servidor valida (precisa do modo ligado dos dois lados)
      Net.send({ type: "attack", id: e.id });
      return;
    }
    if (e && e.kind === "npc") {
      if (dist <= 3) Net.send({ type: "say", text: "oi" });  // cumprimenta
      else Net.send({ type: "walkto", x: t.x, y: t.y });     // vai até ele
      return;
    }
    // escada: só desce/sobe quando CLICADA (de longe: anda até ela e usa)
    if (me && G.map) {
      const o = (G.map.floors[me.z || 0].objects[t.y] || [])[t.x];
      const meta = o ? G.map.objectMeta[o] : null;
      if (meta && (meta.sprite === "stairs_down" || meta.sprite === "stairs_up")) {
        Net.send({ type: "use_stairs", x: t.x, y: t.y });
        return;
      }
    }
    const pile = me && G.ground.get(groundKey(t.x, t.y, me.z || 0));
    if (pile && pile.length) {
      const topDef = ItemDefs[pile[pile.length - 1].id] || {};
      if (topDef.container) {
        // corpo/mochila: abre (servidor anda até lá se longe). Já aberto = fecha
        if (G.containers.has(t.x + "," + t.y)) {
          UI.closeContainer(t.x, t.y);         // fecha local + avisa servidor
        } else {
          Net.send({ type: "open_container", x: t.x, y: t.y });
        }
      } else {
        Net.send({ type: "pickup", x: t.x, y: t.y });        // anda até lá se longe
      }
      return;
    }
    if (e) return;                                      // você mesmo: nada
    Net.send({ type: "walkto", x: t.x, y: t.y });       // anda até o tile
  },
};
