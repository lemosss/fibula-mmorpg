/**
 * ui.js — Painéis DOM: chat com abas, stats, inventário, equipamento,
 * janelas flutuantes (skills, hotkeys), containers de loot e comércio.
 */
const UI = {
  tradeTab: "buy",
  activeChatTab: "default",
  chatBuffer: [],            // {channel, from, text} (máx. 400)
  lastSkills: null,          // último payload de skills (p/ janela)

  // canais que aparecem em cada aba do chat
  TAB_CHANNELS: {
    default: ["say", "look", "error", "info"],
    server:  ["server", "info"],
    loot:    ["loot"],
    npc:     ["npc"],
    pm:      ["pm"],
  },

  $(id) { return document.getElementById(id); },

  // ------------------------------------------------------------ telas

  enterGame() {
    this.$("login-screen").classList.add("hidden");
    this.$("game-screen").classList.remove("hidden");
    this.closeAllContainers(false);
    this.renderHotkeysWindow();
  },

  showLogin(message) {
    this.$("game-screen").classList.add("hidden");
    this.$("login-screen").classList.remove("hidden");
    if (message) this.loginError(message);
  },

  loginError(text) { this.$("login-error").textContent = text; },

  showDead(message) {
    this.$("dead-text").textContent = message;
    this.$("dead-overlay").classList.remove("hidden");
    clearTimeout(this._deadTimer);
    this._deadTimer = setTimeout(
      () => this.$("dead-overlay").classList.add("hidden"), 4000);
  },

  // ------------------------------------------------------- chat (abas)

  chatLine(channel, from, text) {
    channel = channel || "info";
    this.chatBuffer.push({ channel, from, text });
    if (this.chatBuffer.length > 400) this.chatBuffer.shift();

    if (this.TAB_CHANNELS[this.activeChatTab].includes(channel)) {
      this.appendChatDiv(channel, from, text);
    }
    // marca bolinha de não-lido nas outras abas que recebem este canal
    for (const [tab, channels] of Object.entries(this.TAB_CHANNELS)) {
      if (tab !== this.activeChatTab && channels.includes(channel)) {
        const el = document.querySelector(`.chat-tab[data-tab="${tab}"]`);
        if (el) el.classList.add("unread");
      }
    }
  },

  appendChatDiv(channel, from, text) {
    const log = this.$("chat-log");
    const div = document.createElement("div");
    div.className = "c-" + channel;
    div.textContent = from ? `${from}: ${text}` : text;
    log.appendChild(div);
    while (log.childElementCount > 250) log.firstChild.remove();
    log.scrollTop = log.scrollHeight;
  },

  setChatTab(tab) {
    this.activeChatTab = tab;
    document.querySelectorAll(".chat-tab").forEach(el => {
      el.classList.toggle("active", el.dataset.tab === tab);
      if (el.dataset.tab === tab) el.classList.remove("unread");
    });
    const log = this.$("chat-log");
    log.innerHTML = "";
    const channels = this.TAB_CHANNELS[tab];
    for (const m of this.chatBuffer) {
      if (channels.includes(m.channel)) {
        this.appendChatDiv(m.channel, m.from, m.text);
      }
    }
  },

  initChatTabs() {
    document.querySelectorAll(".chat-tab").forEach(el => {
      el.onclick = () => this.setChatTab(el.dataset.tab);
    });
  },

  // ------------------------------------------------------------ stats

  renderStats() {
    const s = G.stats;
    if (!s) return;
    const pct = (a, b) => Math.max(0, Math.min(100, (a / b) * 100)) + "%";
    this.$("bar-hp").style.width = pct(s.hp, s.maxhp);
    this.$("bar-hp-text").textContent = `${s.hp}/${s.maxhp}`;
    this.$("bar-mp").style.width = pct(s.mp, s.maxmp);
    this.$("bar-mp-text").textContent = `${s.mp}/${s.maxmp}`;
    // (o Level agora aparece só na janela de Habilidades, não no header)
    // Cap embaixo do Ring; Atk/Def embaixo do Ammo (estilo Tibia)
    this.$("eq-cap").innerHTML =
      `Cap<br><b>${Math.max(0, Math.round(s.maxcap - s.cap))}</b>`;
    this.$("eq-cap").title = `carregando ${s.cap} de ${s.maxcap} oz`;
    this.$("eq-atkdef").innerHTML =
      `Atk: <b>${s.atk}</b><br>Def: <b>${s.def}</b>`;
    for (const mode of ["attack", "balanced", "defense"]) {
      this.$("st-" + mode).classList.toggle("active", s.stance === mode);
    }
    this.$("btn-pvp").classList.toggle("pvp-on", !!s.pvp);
    this.$("btn-follow").classList.toggle("follow-on", !!s.follow);
    this.$("btn-follow").textContent = s.follow ? "🏃" : "🧍";
    if (G.trade) this.renderTrade();
    this.renderSkillsWindow();
  },

  setFloor() { /* indicador de andar foi removido da UI */ },

  // ------------------------------------------------- battle list (Tibia)

  // cor da barra de vida conforme a % (verde→amarelo→vermelho)
  hpColor(pct) {
    return pct > 0.5 ? "#46c846" : pct > 0.25 ? "#c8b446" : "#c84646";
  },

  renderBattle() {
    const list = this.$("battle-list");
    if (this.$("battle-window").classList.contains("hidden")) return;
    const me = myPlayer();
    if (!me) { list.innerHTML = ""; return; }
    const z = me.z || 0;

    // só o que está REALMENTE na tela do jogador (viewport 15x11 => ±7/±5)
    const hx = Math.floor(Render.VIEW_W / 2);
    const hy = Math.floor(Render.VIEW_H / 2);
    const foes = [];
    for (const e of G.entities.values()) {
      if ((e.z || 0) !== z) continue;
      if (Math.abs(e.x - me.x) > hx || Math.abs(e.y - me.y) > hy) continue;
      if (e.kind === "monster" ||
          (e.kind === "player" && e.id !== G.myId)) {
        e._d = Math.max(Math.abs(e.x - me.x), Math.abs(e.y - me.y));
        foes.push(e);
      }
    }
    foes.sort((a, b) => a._d - b._d);

    if (!foes.length) {
      list.innerHTML = '<div class="battle-empty">Nenhuma criatura à vista</div>';
      return;
    }

    list.innerHTML = "";
    for (const e of foes) {
      const def = ItemDefs;  // (não usado; mantém padrão)
      const row = document.createElement("div");
      row.className = "battle-row" + (e.kind === "player" ? " is-player" : "")
        + (e.id === G.targetId ? " targeted" : "");
      row.title = "Clique para atacar";
      row.appendChild(this.spriteMini(e.sprite));

      const info = document.createElement("div");
      info.className = "bt-info";
      const pct = Math.max(0, e.hp / e.maxhp);
      info.innerHTML =
        `<div class="bt-name">${e.name}</div>` +
        `<div class="bt-bar"><div class="bt-fill" style="width:` +
        `${Math.round(pct * 100)}%;background:${this.hpColor(pct)}"></div></div>`;
      row.appendChild(info);

      row.onclick = () => Net.send({ type: "attack", id: e.id });
      list.appendChild(row);
    }
  },

  /** Canvas 20x20 do sprite (frente) de uma criatura, para a battle list. */
  spriteMini(spriteName) {
    const c = document.createElement("canvas");
    c.width = c.height = 20;
    const i = Render.sprites.index[spriteName];
    if (i !== undefined) {
      const T = Render.sprites.tile;
      const ctx = c.getContext("2d");
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(Render.sheet, (i % Render.sprites.cols) * T,
        Math.floor(i / Render.sprites.cols) * T, T, T, 0, 0, 20, 20);
    }
    return c;
  },

  initBattle() {
    this.$("btn-battle").onclick = () => this.toggleWindow("battle-window");
    // atualiza a lista periodicamente (posições/HP mudam o tempo todo)
    setInterval(() => { if (G.loggedIn) this.renderBattle(); }, 250);
  },

  initCombatControls() {
    for (const mode of ["attack", "balanced", "defense"]) {
      this.$("st-" + mode).onclick = () => Net.send({ type: "stance", mode });
    }
    this.$("btn-pvp").onclick = () =>
      Net.send({ type: "pvp", on: !(G.stats && G.stats.pvp) });
    this.$("btn-follow").onclick = () =>
      Net.send({ type: "follow", on: !(G.stats && G.stats.follow) });
  },

  // chat redimensionável (divisor arrastável) com tamanho persistido
  initChatResize() {
    const panel = this.$("chat-panel");
    const saved = parseInt(localStorage.getItem("fibula_chatH"), 10);
    if (saved) panel.style.height = saved + "px";
    const resizer = this.$("chat-resizer");
    let dragging = false;
    resizer.addEventListener("mousedown", (ev) => {
      dragging = true;
      ev.preventDefault();
    });
    document.addEventListener("mousemove", (ev) => {
      if (!dragging) return;
      const h = Math.max(72, Math.min(window.innerHeight * 0.6,
                                      window.innerHeight - ev.clientY));
      panel.style.height = h + "px";
    });
    document.addEventListener("mouseup", () => {
      if (!dragging) return;
      dragging = false;
      localStorage.setItem("fibula_chatH", parseInt(panel.style.height, 10));
    });
  },

  // ------------------------------------------------- janela de SKILLS

  SKILL_LABELS: {
    magic: "Magic Level", fist: "Fist Fighting", club: "Club Fighting",
    sword: "Sword Fighting", axe: "Axe Fighting",
    distance: "Distance Fight.", shield: "Shielding", fishing: "Fishing",
  },

  renderSkills(skills) {           // chega do servidor a cada treino
    this.lastSkills = skills;
    this.renderSkillsWindow();
  },

  renderSkillsWindow() {
    const win = this.$("skills-window");
    if (win.classList.contains("hidden") || !this.lastSkills) return;
    const s = G.stats || {};
    const body = this.$("skills-body");
    body.innerHTML = "";

    const addStatic = (lbl, val) => {
      const row = document.createElement("div");
      row.className = "skill-static";
      row.innerHTML = `<span class="lbl">${lbl}</span><span class="val">${val}</span>`;
      body.appendChild(row);
    };
    addStatic("Level", s.level ?? "—");
    addStatic("Experience", (s.exp ?? 0).toLocaleString("pt-BR"));
    addStatic("Cap", `${Math.max(0, Math.round((s.maxcap ?? 0) - (s.cap ?? 0)))}`
              + ` / ${s.maxcap ?? 0} oz`);

    const sep = document.createElement("div");
    sep.className = "skill-sep";
    body.appendChild(sep);

    for (const [name, label] of Object.entries(this.SKILL_LABELS)) {
      const sk = this.lastSkills[name];
      if (!sk) continue;
      const row = document.createElement("div");
      row.className = "skill-row";
      row.title = `${sk.pct}% para o próximo nível`;
      row.innerHTML =
        `<div class="sk-head"><span class="sk-name">${label}</span>` +
        `<span class="sk-level">${sk.level}</span></div>` +
        `<div class="sk-bar"><span class="sk-fill" style="width:${sk.pct}%"></span>` +
        `<span class="sk-pct">${sk.pct}%</span></div>`;
      body.appendChild(row);
    }
  },

  // ------------------------------------------------ janela de HOTKEYS

  HOTKEY_KEYS: ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9",
                "F10", "F11", "F12",
                "1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],

  renderHotkeysWindow() {
    const body = this.$("hotkeys-body");
    body.innerHTML = "";
    for (const key of this.HOTKEY_KEYS) {
      const hk = G.hotkeys[key] || {};
      const row = document.createElement("div");
      row.className = "hk-row";
      row.innerHTML =
        `<span class="hk-key">${key}</span>` +
        `<input type="text" class="hk-text" data-key="${key}"
                placeholder="falar/magia" maxlength="60"
                value="${hk.type === "say" ? hk.text : ""}">` +
        `<input type="text" class="hk-item" data-key="${key}"
                placeholder="item" maxlength="4"
                value="${hk.type === "use" ? hk.item : ""}">`;
      body.appendChild(row);
    }
    body.querySelectorAll("input").forEach(el => {
      el.addEventListener("keydown", ev => ev.stopPropagation());
    });
  },

  saveHotkeys() {
    const map = {};
    document.querySelectorAll("#hotkeys-body .hk-text").forEach(el => {
      const text = el.value.trim();
      if (text) map[el.dataset.key] = { type: "say", text };
    });
    document.querySelectorAll("#hotkeys-body .hk-item").forEach(el => {
      const id = parseInt(el.value, 10);
      if (id && !map[el.dataset.key]) {
        map[el.dataset.key] = { type: "use", item: id };
      }
    });
    G.hotkeys = map;
    Net.send({ type: "hotkeys", map });
  },

  toggleWindow(id) {
    const win = this.$(id);
    win.classList.toggle("hidden");
    if (id === "skills-window") this.renderSkillsWindow();
    if (id === "hotkeys-window") this.renderHotkeysWindow();
    if (id === "battle-window") this.renderBattle();
  },

  initWindows() {
    this.$("btn-skills").onclick = () => this.toggleWindow("skills-window");
    this.$("btn-hotkeys").onclick = () => this.toggleWindow("hotkeys-window");
    document.querySelectorAll(".fw-close").forEach(btn => {
      btn.onclick = () => this.$(btn.dataset.close).classList.add("hidden");
    });
    // botões de MINIMIZAR (—): escondem só o corpo da janela, header fica
    document.querySelectorAll(".cont-min").forEach(btn => {
      btn.onclick = () => {
        const body = this.$(btn.dataset.min);
        body.classList.toggle("hidden");
        btn.textContent = body.classList.contains("hidden") ? "+" : "—";
      };
    });
    this.$("btn-logout").onclick = () => Net.send({ type: "logout" });
    this.$("hk-save").onclick = () => this.saveHotkeys();

    // redimensionar (borda inferior inteira) e mover (arrastar título)
    document.querySelectorAll(".win-resizer").forEach(bar => {
      this.makeResizer(bar, this.$(bar.dataset.resize));
    });
    document.querySelectorAll(".container-panel.movable").forEach(win => {
      this.makeWindowMovable(win);
    });
    this.restoreDockLayout();           // recoloca janelas onde o jogador deixou
    this.initDockButtons();             // ＋ adiciona coluna / × remove
    this.initQtyModal();                // seletor de quantidade (split)
  },

  /** Redimensiona um corpo de janela arrastando a borda de baixo inteira. */
  makeResizer(bar, body) {
    let drag = false, sy = 0, sh = 0;
    bar.addEventListener("mousedown", (ev) => {
      drag = true; sy = ev.clientY; sh = body.offsetHeight; ev.preventDefault();
    });
    document.addEventListener("mousemove", (ev) => {
      if (!drag) return;
      body.style.height =
        Math.max(28, Math.min(460, sh + (ev.clientY - sy))) + "px";
    });
    document.addEventListener("mouseup", () => { drag = false; });
  },

  /** Colunas EXTRAS de um lado (as adicionáveis/fecháveis pela setinha). */
  sideCols(side) {
    return [...document.querySelectorAll(`.dock-col[data-side="${side}"]`)];
  },

  /**
   * Alvos de encaixe (corpo + elemento p/ hit-test): colunas extras VISÍVEIS +
   * a coluna PRINCIPAL que fica na sidebar (#dock-right-body) — esta é o alvo
   * permanente, então arrastar janela "pra perto do minimapa" SEMPRE encaixa.
   */
  dockTargets() {
    const t = [...document.querySelectorAll(".dock-col:not(.hidden)")]
      .map(d => ({ el: d, body: d.querySelector(".dock-body") }));
    const sb = this.$("sidebar"), sbBody = this.$("dock-right-body");
    if (sb && sbBody) t.push({ el: sb, body: sbBody });   // coluna do minimapa
    return t.filter(x => x.body);
  },

  /** Corpo (.dock-body) sob o cursor (o que contém X, senão o mais próximo). */
  dockAt(x) {
    const t = this.dockTargets();
    for (const { el, body } of t) {
      const r = el.getBoundingClientRect();
      if (x >= r.left && x <= r.right) return body;
    }
    let best = null, bd = Infinity;                // sobre o mapa: o mais perto
    for (const { el, body } of t) {
      const r = el.getBoundingClientRect();
      const cx = (r.left + r.right) / 2;
      if (Math.abs(x - cx) < bd) { bd = Math.abs(x - cx); best = body; }
    }
    return best;
  },

  /** Adiciona (revela) a próxima coluna extra escondida do lado. */
  addDock(side) {
    const next = this.sideCols(side).find(d => d.classList.contains("hidden"));
    if (next) next.classList.remove("hidden");
    this.updateDockCtrl();
    this.saveDockLayout();
  },

  /** Fecha uma coluna extra; as janelas dela voltam p/ outra coluna do mesmo
      lado ou, se não houver, p/ a coluna PRINCIPAL (a do minimapa). */
  removeDock(id) {
    const dock = this.$(id);
    if (!dock || dock.classList.contains("hidden")) return;
    const wins = [...dock.querySelectorAll(".dock-body > .movable")];
    const side = dock.dataset.side;
    const sameSide = this.sideCols(side)
      .filter(d => d !== dock && !d.classList.contains("hidden"));
    const dest = (sameSide.length
      ? sameSide[sameSide.length - 1].querySelector(".dock-body")
      : this.$("dock-right-body"));
    if (dest) wins.forEach(w => dest.appendChild(w));
    dock.classList.add("hidden");
    this.updateDockCtrl();
    this.saveDockLayout();
  },

  /** Remove a ÚLTIMA coluna aberta do lado (pode chegar a ZERO colunas). */
  removeLastDock(side) {
    const vis = this.sideCols(side).filter(d => !d.classList.contains("hidden"));
    if (vis.length) this.removeDock(vis[vis.length - 1].id);
  },

  /** Liga/desliga as setinhas de cada lado conforme dá p/ add/remover. */
  updateDockCtrl() {
    for (const side of ["left", "right"]) {
      const cols = this.sideCols(side);
      const more = document.querySelector(`.dock-more[data-side="${side}"]`);
      const less = document.querySelector(`.dock-less[data-side="${side}"]`);
      if (more) more.disabled = !cols.some(d => d.classList.contains("hidden"));
      if (less) less.disabled = !cols.some(d => !d.classList.contains("hidden"));
    }
  },

  initDockButtons() {
    document.querySelectorAll(".dock-more").forEach(b =>
      b.onclick = () => this.addDock(b.dataset.side));
    document.querySelectorAll(".dock-less").forEach(b =>
      b.onclick = () => this.removeLastDock(b.dataset.side));
    this.updateDockCtrl();
  },

  /**
   * Arrastar o título move a janela ENTRE as colunas (2 esq + 1 dir) e a
   * reordena por Y dentro da coluna escolhida. Nunca flutua: sempre encaixa.
   */
  makeWindowMovable(win) {
    const header = win.querySelector(".cont-header");
    if (!header) return;
    let drag = false;
    header.addEventListener("mousedown", (ev) => {
      if (ev.target.closest("button")) return;    // não nos botões do header
      drag = true; win.classList.add("dragging"); ev.preventDefault();
    });
    document.addEventListener("mousemove", (ev) => {
      if (!drag) return;
      const body = this.dockAt(ev.clientX);
      if (!body) return;
      document.querySelectorAll(".dock-body").forEach(b =>
        b.classList.toggle("dock-target", b === body));
      const sibs = [...body.children].filter(
        s => s !== win && s.classList.contains("movable"));
      let placed = false;
      for (const s of sibs) {
        const r = s.getBoundingClientRect();
        if (ev.clientY < r.top + r.height / 2) {
          body.insertBefore(win, s); placed = true; break;
        }
      }
      if (!placed) body.appendChild(win);          // abaixo de todas
    });
    document.addEventListener("mouseup", () => {
      if (!drag) return;
      drag = false;
      win.classList.remove("dragging");
      document.querySelectorAll(".dock-body").forEach(b =>
        b.classList.remove("dock-target"));
      this.saveDockLayout();
    });
  },

  /** Salva quais colunas estão abertas + ordem das janelas em cada .dock-body
      (inclui a coluna principal #dock-right-body da sidebar). */
  saveDockLayout() {
    const docks = {};
    document.querySelectorAll(".dock-body").forEach(body => {
      docks[body.id] = [...body.children]
        .filter(c => c.classList.contains("movable")).map(c => c.id);
    });
    const open = [...document.querySelectorAll(".dock-col:not(.hidden)")].map(d => d.id);
    try { localStorage.setItem("fibula.dock", JSON.stringify({ docks, open })); }
    catch (e) { /* localStorage indisponível: tudo bem */ }
  },

  /** Restaura quais colunas estão abertas e a disposição salva das janelas. */
  restoreDockLayout() {
    let layout = null;
    try { layout = JSON.parse(localStorage.getItem("fibula.dock") || "null"); }
    catch (e) { return; }
    if (!layout) return;
    const docks = layout.docks || layout;          // aceita formato antigo plano
    if (Array.isArray(layout.open)) {              // visibilidade exata das colunas
      document.querySelectorAll(".dock-col").forEach(d =>
        d.classList.toggle("hidden", !layout.open.includes(d.id)));
    }
    for (const [bodyId, ids] of Object.entries(docks)) {
      const body = this.$(bodyId);
      if (!body || !Array.isArray(ids)) continue;
      for (const winId of ids) {
        const win = this.$(winId);
        if (win) body.appendChild(win);            // move e respeita a ordem
      }
    }
  },

  // --------------------------------------- seletor de quantidade (split)

  /** Abre o popup de quantidade. `cb(n)` recebe a quantidade escolhida.
   *  `start` define o valor inicial (padrão = max, como no split de pilha). */
  askQuantity(max, spriteName, cb, start) {
    const input = this.$("qty-input"), slider = this.$("qty-slider");
    const preview = this.$("qty-preview");
    this._qtyCb = cb;
    const init = Math.max(1, Math.min(max, start == null ? max : start));
    input.max = max; slider.max = max;
    input.value = init; slider.value = init;
    preview.innerHTML = "";
    if (spriteName) preview.appendChild(this.spriteCanvas(spriteName));
    const lbl = document.createElement("span");
    lbl.textContent = "de " + max + " no total";
    preview.appendChild(lbl);
    this.$("qty-modal").classList.remove("hidden");
    input.focus(); input.select();
  },

  qtyOpen() { return !this.$("qty-modal").classList.contains("hidden"); },

  closeQuantity() {
    this.$("qty-modal").classList.add("hidden");
    this._qtyCb = null;
  },

  /** Liga os controles do popup de quantidade (uma vez). */
  initQtyModal() {
    const modal = this.$("qty-modal");
    const input = this.$("qty-input"), slider = this.$("qty-slider");
    const clamp = v => Math.max(1, Math.min(parseInt(input.max, 10) || 1,
                                           parseInt(v, 10) || 1));
    const sync = v => { const n = clamp(v); input.value = n; slider.value = n; };
    input.oninput = () => { slider.value = clamp(input.value); };
    slider.oninput = () => { input.value = slider.value; };
    modal.querySelectorAll(".qty-quick button").forEach(b => {
      b.onclick = () => sync(b.dataset.q === "max" ? input.max : b.dataset.q);
    });
    const confirm = () => {
      const n = clamp(input.value), cb = this._qtyCb;
      this.closeQuantity();
      if (cb) cb(n);
    };
    this.$("qty-ok").onclick = confirm;
    this.$("qty-cancel").onclick = () => this.closeQuantity();
    this.$("qty-x").onclick = () => this.closeQuantity();
    input.onkeydown = (ev) => {
      if (ev.key === "Enter") { confirm(); ev.preventDefault(); }
      else if (ev.key === "Escape") { this.closeQuantity(); }
      ev.stopPropagation();
    };
  },

  // --------------------------------------- janelas de loot (corpos)

  containerKey(x, y) { return x + "," + y; },

  renderContainer(m) {
    // cria/atualiza a janela deste corpo (várias podem ficar abertas)
    G.containers.set(this.containerKey(m.x, m.y), m);
    const stack = this.$("containers-stack");
    let panel = stack.querySelector(
      `[data-ckey="${this.containerKey(m.x, m.y)}"]`);
    if (!panel) {
      panel = document.createElement("div");
      panel.className = "container-panel";
      panel.dataset.ckey = this.containerKey(m.x, m.y);
      stack.appendChild(panel);
    }
    // preserva a altura escolhida pelo jogador (resize) entre atualizações
    const oldGrid = panel.querySelector(".cont-grid");
    const keptHeight = oldGrid ? oldGrid.style.height : "";
    panel.innerHTML = "";

    const header = document.createElement("div");
    header.className = "cont-header";
    header.innerHTML = `<span>${m.name}</span>`;
    const btn = document.createElement("button");
    btn.className = "cont-close";
    btn.textContent = "✕";
    btn.onclick = () => this.closeContainer(m.x, m.y, true);
    header.appendChild(btn);
    panel.appendChild(header);

    const grid = document.createElement("div");
    grid.className = "cont-grid";
    if (keptHeight) grid.style.height = keptHeight;
    // mostra TODOS os slots (mochila): preenchidos + vazios (droppáveis)
    const total = Math.max(m.slots || 0, m.items.length, 1);
    for (let idx = 0; idx < total; idx++) {
      const it = m.items[idx];
      const div = document.createElement("div");
      div.className = "inv-slot";
      if (it) {
        const def = ItemDefs[it.id] || {};
        div.title = def.name || "?";
        div.appendChild(this.spriteCanvas(def.sprite));
        if (it.count > 1) {
          const n = document.createElement("span");
          n.className = "slot-count";
          n.textContent = it.count;
          div.appendChild(n);
        }
        div.onmousedown = (ev) => {
          if (ev.button === 0)
            Drag.begin({ kind: "container", cx: m.x, cy: m.y, idx }, ev, def.sprite);
        };
        div.ondblclick = () => Net.send({ type: "loot", x: m.x, y: m.y, idx });
        div.oncontextmenu = (ev) =>            // direito usa; esq+dir = olhar
          Input.handleItemRightClick(ev, def,
            { src: "container", cx: m.x, cy: m.y, idx },
            { type: "look_item", cidx: idx, cx: m.x, cy: m.y });
      }
      grid.appendChild(div);
    }
    panel.appendChild(grid);
  },

  closeContainer(x, y, notifyServer = true) {
    G.containers.delete(this.containerKey(x, y));
    const panel = this.$("containers-stack").querySelector(
      `[data-ckey="${this.containerKey(x, y)}"]`);
    if (panel) panel.remove();
    if (notifyServer) Net.send({ type: "close_container", x, y });
  },

  closeAllContainers(notifyServer = true) {
    G.containers.clear();
    this.$("containers-stack").innerHTML = "";
    if (notifyServer) Net.send({ type: "close_container" });
  },

  // ------------------------------------------ inventário / equipamento

  /** Canvas 32x32 com o sprite de um item (para slots e loja). */
  spriteCanvas(spriteName) {
    const c = document.createElement("canvas");
    c.width = c.height = 32;
    const i = Render.sprites.index[spriteName];
    if (i !== undefined) {
      const T = Render.sprites.tile;
      c.getContext("2d").drawImage(
        Render.sheet, (i % Render.sprites.cols) * T,
        Math.floor(i / Render.sprites.cols) * T, T, T, 0, 0, 32, 32);
    }
    return c;
  },

  renderInventory() {
    const grid = this.$("inv-grid");
    grid.innerHTML = "";
    const active = G.inv.active ?? G.inv.slots.length;
    // a janela da mochila só existe se há mochila equipada e está aberta
    const bp = G.inv.equip && G.inv.equip.backpack;
    this.$("inv-window").classList.toggle("hidden",
                                          this.bagClosed || !bp || active === 0);
    if (bp) {
      this.$("inv-title").textContent = (ItemDefs[bp.id] || {}).name || "mochila";
    }
    for (let i = 0; i < active; i++) {
      const slot = G.inv.slots[i];
      const div = document.createElement("div");
      div.className = "inv-slot";
      div.dataset.i = i;
      if (slot) {
        const def = ItemDefs[slot.id] || {};
        div.title = def.name || "?";
        div.appendChild(this.spriteCanvas(def.sprite));
        if (slot.count > 1) {
          const n = document.createElement("span");
          n.className = "slot-count";
          n.textContent = slot.count;
          div.appendChild(n);
        }
        div.ondblclick = () => this.smartAction(i);   // duplo: usa consumível (não equipa)
        div.onmousedown = (ev) => {
          if (ev.button === 0) Drag.begin({ kind: "inv", i }, ev, def.sprite);
        };
        div.oncontextmenu = (ev) =>            // direito usa; esq+dir = olhar
          Input.handleItemRightClick(ev, def, { src: "inv", i },
                                     { type: "look_item", slot: i });
      }
      grid.appendChild(div);
    }

    document.querySelectorAll(".equip-slot").forEach(el => {
      const eslot = el.dataset.eslot;
      const item = G.inv.equip[eslot];
      el.innerHTML = "";
      el.classList.toggle("empty", !item);
      if (item) {
        const def = ItemDefs[item.id] || {};
        el.title = def.name || "?";
        el.appendChild(this.spriteCanvas(def.sprite));
        if (item.count > 1) {
          const n = document.createElement("span");
          n.className = "slot-count";
          n.textContent = item.count;
          el.appendChild(n);
        }
        if (eslot === "backpack") {
          // clique na mochila equipada: abre/fecha a janela da mochila
          el.onclick = () => this.toggleBag();
          el.classList.toggle("bag-open", !this.bagClosed);
          el.title = (def.name || "mochila") + " (clique p/ abrir/fechar)";
        } else {
          el.onclick = () => Net.send({ type: "unequip", eslot });
        }
        el.onmousedown = (ev) => {
          if (ev.button === 0) Drag.begin({ kind: "equip", eslot }, ev, def.sprite);
        };
        el.oncontextmenu = (ev) =>             // esq+dir = olhar (direito só nada)
          Input.handleItemRightClick(ev, def, null, { type: "look_item", eslot });
      } else {
        el.onclick = null;
        el.onmousedown = null;
        el.oncontextmenu = (ev) => ev.preventDefault();
      }
    });
  },

  /** Duplo clique: usa o que é usável, equipa o que é equipável. */
  smartAction(i) {
    const slot = G.inv.slots[i];
    if (!slot) return;
    const def = ItemDefs[slot.id] || {};
    // duplo-clique NÃO equipa mais (equipar = só arrastando pro slot da mão/corpo).
    // só usa consumível/ferramenta; arma/armadura/etc. não fazem nada aqui.
    if (def.type === "potion" || def.type === "food" || def.type === "tool") {
      Net.send({ type: "use", slot: i });
    }
  },

  bagClosed: false,

  toggleBag() {
    this.bagClosed = !this.bagClosed;
    this.renderInventory();
  },

  initInventoryButtons() {
    this.$("inv-close").onclick = () => { this.bagClosed = true; this.renderInventory(); };
  },

  // ------------------------------------------------- minimapa / mapa-múndi

  openMap() { this.$("map-modal").classList.remove("hidden"); },
  closeMap() { this.$("map-modal").classList.add("hidden"); },
  mapOpen() { return !this.$("map-modal").classList.contains("hidden"); },

  initMapControls() {
    document.querySelectorAll("#compass [data-mm]").forEach(btn => {
      const [dx, dy] = btn.dataset.mm.split(",").map(Number);
      btn.onclick = () => Minimap.pan(dx, dy);
    });
    this.$("mm-center").onclick = () => Minimap.center();
    this.$("mm-expand").onclick = () => this.openMap();
    this.$("mm-zin").onclick = () => Minimap.zoom(1);    // aproxima
    this.$("mm-zout").onclick = () => Minimap.zoom(-1);  // afasta
    this.$("map-close").onclick = () => this.closeMap();
    this.$("map-modal").onclick = (ev) => {
      if (ev.target === this.$("map-modal")) this.closeMap();
    };

    this.$("minimap").addEventListener("click", (ev) => {
      const t = Minimap.tileAt(this.$("minimap"), ev.clientX, ev.clientY);
      if (t) Net.send({ type: "walkto", x: t.x, y: t.y });
    });
    // scroll no minimapa = zoom (pra cima aproxima, pra baixo afasta)
    this.$("minimap").addEventListener("wheel", (ev) => {
      ev.preventDefault();
      Minimap.zoom(ev.deltaY < 0 ? 1 : -1);
    }, { passive: false });

    this.$("bigmap").addEventListener("click", (ev) => {
      const big = this.$("bigmap");
      const rect = big.getBoundingClientRect();
      const s = rect.width / G.map.width;
      Net.send({
        type: "walkto",
        x: Math.floor((ev.clientX - rect.left) / s),
        y: Math.floor((ev.clientY - rect.top) / s),
      });
    });
  },

  // ---------------------------------------------------------- comércio

  openTrade() {
    this.tradeTab = "buy";
    this.$("trade-npc-name").textContent = G.trade.npc;
    this.$("trade-modal").classList.remove("hidden");
    this.renderTrade();
  },

  closeTrade() {
    G.trade = null;
    this.$("trade-modal").classList.add("hidden");
  },

  invCount(itemId) {
    return G.inv.slots.reduce(
      (acc, s) => acc + (s && s.id === itemId ? s.count : 0), 0);
  },

  isEquipped(itemId) {
    return Object.values(G.inv.equip || {})
      .some(it => it && it.id === itemId);
  },

  renderTrade() {
    if (!G.trade) return;
    this.$("tab-buy").classList.toggle("active", this.tradeTab === "buy");
    this.$("tab-sell").classList.toggle("active", this.tradeTab === "sell");
    this.$("trade-gold").textContent = G.stats ? G.stats.gold : 0;

    const list = this.$("trade-list");
    list.innerHTML = "";
    const rows = this.tradeTab === "buy" ? G.trade.sells : G.trade.buys;
    for (const row of rows) {
      const def = ItemDefs[row.id] || {};
      const have = this.invCount(row.id);
      const equipped = this.isEquipped(row.id);

      const div = document.createElement("div");
      div.className = "trade-row";
      div.appendChild(this.spriteCanvas(def.sprite));

      const name = document.createElement("span");
      name.className = "t-name";
      name.textContent = row.name;
      div.appendChild(name);

      if (this.tradeTab === "sell" && equipped) {
        const badge = document.createElement("span");
        badge.className = "t-equipped";
        badge.textContent = "equipado";
        badge.title = "Desequipe antes de vender";
        div.appendChild(badge);
      }

      const haveEl = document.createElement("span");
      haveEl.className = "t-have";
      haveEl.textContent = "tem " + have;
      div.appendChild(haveEl);

      const price = document.createElement("span");
      price.className = "t-price";
      price.textContent = row.price + " 🪙";
      price.title = `compra: ${def.priceBuy ?? "—"} · venda: ${def.priceSell ?? "—"}`;
      div.appendChild(price);

      const btn = document.createElement("button");
      if (this.tradeTab === "buy") {
        btn.textContent = "Comprar";
        btn.disabled = G.stats && G.stats.gold < row.price;
        btn.onclick = () => {
          // quantos dá pra pagar (servidor limita a 100 por compra)
          const gold = (G.stats && G.stats.gold) || 0;
          const maxAfford = Math.max(1, Math.min(100,
            row.price > 0 ? Math.floor(gold / row.price) : 100));
          const buy = n => Net.send(
            { type: "npc_buy", npc: G.trade.npc, item: row.id, count: n });
          if (maxAfford <= 1) { buy(1); return; }
          // seletor de quantidade (igual ao de dropar moedas), começa em 1
          this.askQuantity(maxAfford, def.sprite, n => { if (n > 0) buy(n); }, 1);
        };
      } else {
        btn.textContent = "Vender";
        btn.disabled = have < 1;
        if (have < 1) div.classList.add("t-disabled");
        btn.onclick = () => {
          if (equipped && have < 1) {
            this.chatLine("info", "", "Desequipe o item antes de vender.");
            return;
          }
          const sell = n => Net.send(
            { type: "npc_sell", npc: G.trade.npc, item: row.id, count: n });
          if (have <= 1) { sell(1); return; }
          this.askQuantity(have, def.sprite, n => { if (n > 0) sell(n); }, have);
        };
      }
      div.appendChild(btn);
      list.appendChild(div);
    }
  },

  initTrade() {
    this.$("trade-close").onclick = () => this.closeTrade();
    this.$("tab-buy").onclick = () => { this.tradeTab = "buy"; this.renderTrade(); };
    this.$("tab-sell").onclick = () => { this.tradeTab = "sell"; this.renderTrade(); };
    this.$("trade-modal").onclick = (ev) => {
      if (ev.target === this.$("trade-modal")) this.closeTrade();
    };
  },
};
