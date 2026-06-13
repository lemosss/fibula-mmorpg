/**
 * render.js — Desenho do mundo no canvas (e o minimapa).
 *
 * Viewport de 15x11 tiles de 32px (480x352), escalado 2x via CSS.
 * A câmera segue a posição interpolada do próprio jogador, então o
 * movimento fica suave mesmo com o servidor mandando posições em grid.
 */
const Render = {
  canvas: null, ctx: null,
  sheet: null,               // Image da spritesheet
  sprites: null,             // {tile, cols, index: {nome -> i}}
  TILE: 32,
  VIEW_W: 15, VIEW_H: 11,

  async loadAssets() {
    const res = await fetch("assets/sprites.json");
    this.sprites = await res.json();
    this.sheet = new Image();
    this.sheet.src = "assets/sprites.png";
    await new Promise((ok, err) => {
      this.sheet.onload = ok;
      this.sheet.onerror = () => err(new Error("sprites.png não carregou"));
    });
  },

  init() {
    this.canvas = document.getElementById("game-canvas");
    this.ctx = this.canvas.getContext("2d");
    this.ctx.imageSmoothingEnabled = false;
    // camada de texto nítido (nomes/barras/números) em resolução nativa
    this.overlay = document.getElementById("fx-canvas");
    this.octx = this.overlay.getContext("2d");
    this._labels = [];
    this._wtext = [];
    requestAnimationFrame(() => this.frame());
  },

  /** Desenha um sprite (por nome) em coordenadas de tela (pixel inteiro). */
  blit(name, dx, dy) {
    const i = this.sprites.index[name];
    if (i === undefined) return;
    const T = this.sprites.tile;
    const sx = (i % this.sprites.cols) * T;
    const sy = Math.floor(i / this.sprites.cols) * T;
    this.ctx.drawImage(this.sheet, sx, sy, T, T,
                       Math.round(dx), Math.round(dy), T, T);
  },

  /** Desenha uma criatura: direção (n/s/e/w) + animação de caminhada. */
  blitCreature(e, dx, dy) {
    const idx = this.sprites.index;
    const now = performance.now();
    const moving = e.animDur > 0 && now < e.animStart + e.animDur;
    const dir = e.dir || "s";

    // frame base da direção (oeste = leste espelhado)
    let stem = e.sprite, flip = false;
    if (dir === "n" && (e.sprite + "_n") in idx) stem = e.sprite + "_n";
    else if (dir === "e" && (e.sprite + "_e") in idx) stem = e.sprite + "_e";
    else if (dir === "w" && (e.sprite + "_e") in idx) {
      stem = e.sprite + "_e"; flip = true;
    }

    // 2 frames por direção: alterna PARADO <-> ANDANDO enquanto se move
    let name = stem, bob = 0;
    if ((stem + "_a") in idx) {
      if (moving && Math.floor(now / 180) % 2) name = stem + "_a";
    } else if (moving) {
      bob = Math.floor(now / 130) % 2 ? -1 : 0;   // bicho sem pernas: balança
    }

    if (flip) this.blitFlipped(name, dx, dy + bob);
    else this.blit(name, dx, dy + bob);
  },

  /** Desenha um sprite espelhado horizontalmente (perfil para o oeste). */
  blitFlipped(name, dx, dy) {
    const i = this.sprites.index[name];
    if (i === undefined) return;
    const T = this.sprites.tile;
    const sx = (i % this.sprites.cols) * T;
    const sy = Math.floor(i / this.sprites.cols) * T;
    const ctx = this.ctx;
    ctx.save();
    ctx.translate(Math.round(dx) + T, Math.round(dy));
    ctx.scale(-1, 1);
    ctx.drawImage(this.sheet, sx, sy, T, T, 0, 0, T, T);
    ctx.restore();
  },

  /**
   * Converte um clique para coordenadas de tile, respeitando o letterbox
   * (object-fit: contain). Retorna null se o clique caiu nas BORDAS PRETAS
   * (fora do mapa) — ali não existe tile.
   */
  screenToTile(clientX, clientY) {
    const rect = this.canvas.getBoundingClientRect();
    const s = Math.min(rect.width / this.canvas.width,
                       rect.height / this.canvas.height);
    const offX = (rect.width - this.canvas.width * s) / 2;
    const offY = (rect.height - this.canvas.height * s) / 2;
    const ix = (clientX - rect.left - offX) / s;   // px internos (0..480)
    const iy = (clientY - rect.top - offY) / s;    // px internos (0..352)
    if (ix < 0 || iy < 0 || ix >= this.canvas.width || iy >= this.canvas.height) {
      return null;                                 // clicou na faixa preta
    }
    return {
      x: Math.floor((ix + this.camX) / this.TILE),
      y: Math.floor((iy + this.camY) / this.TILE),
    };
  },

  camX: 0, camY: 0,

  frame() {
    requestAnimationFrame(() => this.frame());
    const ctx = this.ctx;
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    if (!G.map || !G.loggedIn) {
      if (this.octx) {                         // limpa o texto ao sair do jogo
        this.octx.setTransform(1, 0, 0, 1, 0, 0);
        this.octx.clearRect(0, 0, this.overlay.width, this.overlay.height);
      }
      return;
    }

    const me = myPlayer();
    if (!me) return;
    this._labels = [];                         // coletados p/ a camada nítida
    this._wtext = [];
    const T = this.TILE;
    const Z = me.z || 0;                       // andar que o cliente desenha
    const floor = G.map.floors[Z];
    const mePos = entityPixelPos(me);

    // câmera centrada no jogador (interpolado), SEMPRE em pixel inteiro:
    // offsets fracionários criam costuras/linhas pretas entre os tiles
    this.camX = Math.round(mePos.px - (this.VIEW_W * T) / 2 + T / 2);
    this.camY = Math.round(mePos.py - (this.VIEW_H * T) / 2 + T / 2);

    const x0 = Math.floor(this.camX / T) - 1;
    const y0 = Math.floor(this.camY / T) - 1;
    const x1 = x0 + this.VIEW_W + 2;
    const y1 = y0 + this.VIEW_H + 2;

    // ---------------- camada 1: chão ----------------
    for (let y = y0; y <= y1; y++) {
      for (let x = x0; x <= x1; x++) {
        if (x < 0 || y < 0 || x >= G.map.width || y >= G.map.height) continue;
        const g = floor.ground[y][x];
        const meta = G.map.groundMeta[g];
        if (meta && meta.sprite) {
          this.blit(meta.sprite, x * T - this.camX, y * T - this.camY);
        }
      }
    }

    // ---------------- camada 2: itens no chão ----------------
    for (let y = y0; y <= y1; y++) {
      for (let x = x0; x <= x1; x++) {
        const pile = G.ground.get(groundKey(x, y, Z));
        if (!pile) continue;
        for (const it of pile) {
          const def = ItemDefs[it.id];
          if (def) this.blit(def.sprite, x * T - this.camX, y * T - this.camY);
        }
        if (pile.length) {
          const top = pile[pile.length - 1];
          if (top.count > 1) {
            this._wtext.push({ ix: x * T - this.camX + 31,
                               iy: y * T - this.camY + 30,
                               str: String(top.count) });
          }
        }
      }
    }

    this.drawWarns(Z);   // avisos de respawn (embaixo das criaturas)

    // ---------------- camada 3: objetos + criaturas (painter por linha) ----
    const byRow = new Map();
    for (const e of G.entities.values()) {
      if ((e.z || 0) !== Z) continue;          // só criaturas do andar atual
      const p = entityPixelPos(e);
      const row = Math.floor((p.py + T / 2) / T);
      if (!byRow.has(row)) byRow.set(row, []);
      byRow.get(row).push({ e, p });
    }

    for (let y = y0; y <= y1; y++) {
      // objetos desta linha
      for (let x = x0; x <= x1; x++) {
        if (x < 0 || y < 0 || x >= G.map.width || y >= G.map.height) continue;
        const o = floor.objects[y][x];
        if (o) {
          const meta = G.map.objectMeta[o];
          if (meta) this.blit(meta.sprite, x * T - this.camX, y * T - this.camY);
        }
      }
      // criaturas desta linha
      const list = byRow.get(y);
      if (!list) continue;
      for (const { e, p } of list) {
        const dx = Math.round(p.px) - this.camX;
        const dy = Math.round(p.py) - this.camY;
        // marcação de alvo: retângulo VERMELHO sólido (como sempre foi)
        if (e.id === G.targetId) {
          ctx.strokeStyle = "#e33";
          ctx.lineWidth = 2;
          ctx.strokeRect(dx + 1, dy + 1, T - 2, T - 2);
        }
        this.blitCreature(e, dx, dy);          // sprite direcional (n/s/e/w)
        this._labels.push({ e, dx, dy });      // nome/barra vão p/ o overlay
      }
    }

    this.drawProjectiles(Z);
    this.drawFx();
    this.drawDarkness(me, mePos);
    this.drawOverlay();                         // texto nítido por cima de tudo
    Minimap.draw();
  },

  /** Flechas/lanças voando entre dois tiles. */
  drawProjectiles() {
    const now = performance.now();
    G.projs = G.projs.filter(p => now - p.t0 < p.dur);
    for (const p of G.projs) {
      const t = (now - p.t0) / p.dur;
      const px = (p.fx + (p.tx - p.fx) * t) * 32 - this.camX;
      const py = (p.fy + (p.ty - p.fy) * t) * 32 - this.camY - 6;
      this.blit(p.sprite, px, py);
    }
  },

  /** Bolinha azul pulsante: avisa que um monstro vai nascer naquele tile. */
  drawWarns(Z) {
    const now = performance.now();
    G.warns = G.warns.filter(w => now - w.t0 < w.ttl);
    const ctx = this.ctx;
    for (const w of G.warns) {
      if (w.z !== Z) continue;
      const cx = w.x * 32 - this.camX + 16;
      const cy = w.y * 32 - this.camY + 16;
      const t = (now - w.t0) / 1000;
      const pulse = 0.5 + 0.5 * Math.sin(t * 9);        // pulsação rápida
      // halo externo
      ctx.globalAlpha = 0.18 + 0.25 * pulse;
      ctx.fillStyle = "#4af";
      ctx.beginPath();
      ctx.arc(cx, cy, 9 + 5 * pulse, 0, Math.PI * 2);
      ctx.fill();
      // núcleo
      ctx.globalAlpha = 0.55 + 0.45 * pulse;
      ctx.fillStyle = "#8cf";
      ctx.beginPath();
      ctx.arc(cx, cy, 3.5 + 2 * pulse, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;
    }
  },

  /** Escuridão de caverna: subsolo é escuro com um círculo de luz no jogador. */
  drawDarkness(me, mePos) {
    if ((me.z || 0) === 0) return;
    const ctx = this.ctx;
    const cx = mePos.px - this.camX + 16;
    const cy = mePos.py - this.camY + 16;
    const grad = ctx.createRadialGradient(cx, cy, 60, cx, cy, 180);
    grad.addColorStop(0, "rgba(0,0,0,0)");
    grad.addColorStop(0.6, "rgba(0,0,0,0.55)");
    grad.addColorStop(1, "rgba(0,0,0,0.85)");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
  },

  /**
   * Camada de TEXTO nítido (resolução nativa, antialiased): nomes, barras
   * de vida, caveira, contagem de pilhas e números flutuantes. O mapa fica
   * pixelado; o texto não — por isso some o "borrão" do upscale.
   */
  drawOverlay() {
    const oc = this.overlay, octx = this.octx;
    const wrap = this.canvas.parentElement;
    const W = wrap.clientWidth, H = wrap.clientHeight;
    const dpr = window.devicePixelRatio || 1;
    const bw = Math.round(W * dpr), bh = Math.round(H * dpr);
    if (oc.width !== bw || oc.height !== bh) { oc.width = bw; oc.height = bh; }
    octx.setTransform(dpr, 0, 0, dpr, 0, 0);
    octx.clearRect(0, 0, W, H);

    // mesma transformação "object-fit: contain" do canvas do jogo
    const s = Math.min(W / this.canvas.width, H / this.canvas.height);
    this._ovS = s;
    this._ovX = (W - this.canvas.width * s) / 2;
    this._ovY = (H - this.canvas.height * s) / 2;
    octx.lineJoin = "round";
    octx.textBaseline = "alphabetic";
    // recorta na área do MAPA — nada de nome/barra vazando nas bordas pretas
    octx.save();
    octx.beginPath();
    octx.rect(this._ovX, this._ovY,
              this.canvas.width * s, this.canvas.height * s);
    octx.clip();

    const small = Math.max(8, Math.min(12, Math.round(5.6 * s)));
    const namePx = Math.max(9, Math.min(13, Math.round(6 * s)));

    // contagem de pilhas no chão
    for (const t of this._wtext) {
      this.octext(t.ix, t.iy, t.str, "#fff", "right", small);
    }

    // criaturas: barra de vida + nome + caveira
    for (const { e, dx, dy } of this._labels) {
      if (e.kind !== "npc") {
        const pct = Math.max(0, e.hp / e.maxhp);
        const col = pct > 0.5 ? "#46c846" : pct > 0.25 ? "#c8b446" : "#c84646";
        this.obar(dx + 5, dy - 5, 22, 3, pct, col);
      }
      const color = e.id === G.myId ? "#74e074"
        : e.kind === "player" ? "#ffffff"
        : e.kind === "npc" ? "#6fd0ff" : "#ff9070";
      this.octext(dx + 16, dy - 7, e.name, color, "center", namePx);
      if (e.skull) {
        this.octext(dx + 30, dy - 6, "☠", "#fff", "left", namePx + 2);
      }
    }

    // números/balões flutuantes (dano, exp, fala) — animados
    const now = performance.now();
    G.floats = G.floats.filter(f => now - f.t0 < f.ttl);
    for (const f of G.floats) {
      const t = (now - f.t0) / f.ttl;
      const ix = f.x * 32 - this.camX + 16;
      const iy = f.y * 32 - this.camY - t * (f.rise || 20);
      octx.globalAlpha = 1 - t * t;
      this.octext(ix, iy, f.text, f.color, "center",
                  Math.max(10, Math.min(15, Math.round(7 * s))));
      octx.globalAlpha = 1;
    }

    octx.restore();                            // encerra o recorte do mapa
  },

  /** Texto nítido com contorno escuro, em coordenadas internas do mapa. */
  octext(ix, iy, str, color, align = "left", sizePx = 11) {
    const octx = this.octx;
    const x = this._ovX + ix * this._ovS;
    const y = this._ovY + iy * this._ovS;
    octx.font = `600 ${sizePx}px 'Segoe UI', Tahoma, Verdana, sans-serif`;
    octx.textAlign = align;
    octx.lineWidth = Math.max(2.5, sizePx / 4);
    octx.strokeStyle = "rgba(0,0,0,0.9)";
    octx.strokeText(str, x, y);
    octx.fillStyle = color;
    octx.fillText(str, x, y);
  },

  /** Barra de vida nítida, em coordenadas internas do mapa. */
  obar(ix, iy, w, h, pct, color) {
    const octx = this.octx;
    const x = Math.round(this._ovX + ix * this._ovS);
    const y = Math.round(this._ovY + iy * this._ovS);
    const W = Math.round(w * this._ovS);
    const H = Math.max(2, Math.round(h * this._ovS));
    octx.fillStyle = "#000";
    octx.fillRect(x - 1, y - 1, W + 2, H + 2);
    octx.fillStyle = color;
    octx.fillRect(x, y, Math.round(W * pct), H);
  },

  drawFx() {
    const now = performance.now();
    // a fumaça de bloqueio (poff) dura mais p/ dar pra acompanhar o turno
    const durOf = (f) => (f.kind === "poff" ? 750 : 400);
    G.fxs = G.fxs.filter(f => now - f.t0 < durOf(f));
    const ctx = this.ctx;
    for (const f of G.fxs) {
      const t = (now - f.t0) / durOf(f);
      const cx = f.x * 32 - this.camX + 16;
      const cy = f.y * 32 - this.camY + 16;
      ctx.globalAlpha = 1 - t;
      if (f.kind === "blood") {
        ctx.fillStyle = "#c22";
        for (let i = 0; i < 5; i++) {
          const a = (i / 5) * Math.PI * 2;
          ctx.fillRect(cx + Math.cos(a) * 8 * t - 2, cy + Math.sin(a) * 8 * t - 2, 4, 4);
        }
      } else if (f.kind === "heal") {
        ctx.strokeStyle = "#5e5";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(cx, cy, 6 + 10 * t, 0, Math.PI * 2);
        ctx.stroke();
      } else if (f.kind === "levelup") {
        ctx.strokeStyle = "#fc3";
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.arc(cx, cy, 8 + 14 * t, 0, Math.PI * 2);
        ctx.stroke();
      } else if (f.kind === "magic") {
        ctx.strokeStyle = "#b7e";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(cx, cy, 5 + 12 * t, 0, Math.PI * 2);
        ctx.stroke();
      } else {                       // poff: fumacinha de bloqueio (Tibia)
        // nuvem de bolinhas cinza no MEIO do personagem, sobe de leve
        const baseY = cy - 2 - 5 * t;
        const puffs = [[0, 0], [-5, 1], [5, 0], [-2, 4], [3, 3]];
        for (let i = 0; i < puffs.length; i++) {
          const [ox, oy] = puffs[i];
          ctx.globalAlpha = (1 - t) * 0.8;
          ctx.fillStyle = i % 2 ? "#e6e6e6" : "#bcbcbc";
          ctx.beginPath();
          ctx.arc(cx + ox, baseY + oy, 2.5 + 4 * t, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      ctx.globalAlpha = 1;
    }
  },
};

/* ============================== MINIMAPA ============================== */

const Minimap = {
  bases: [],                 // canvas offscreen por andar (mapa estático)
  el: null, ctx: null,

  COLORS: {
    grass: "#3c702c", dirt: "#6e5532", stone: "#7c7c80", water: "#28508c",
    sand: "#c2ae76", marble: "#b8b6be", wood: "#8a6236", cave: "#46403c",
    tree: "#1e4a1e", wall: "#3a3632", rock: "#5a5652", bush: "#2a5e2a",
    fence: "#5e4220", altar: "#c8b050", gravestone: "#8a888e",
    cave_wall: "#2c2622", stairs_down: "#e8d060", stairs_up: "#e8d060",
  },

  get base() {               // base do andar em que o jogador está
    const me = myPlayer();
    return this.bases[(me && me.z) || 0];
  },

  build() {
    this.el = document.getElementById("minimap");
    this.ctx = this.el.getContext("2d");
    this.ctx.imageSmoothingEnabled = false;
    const m = G.map;
    this.bases = m.floors.map(floor => {
      const c = document.createElement("canvas");
      c.width = m.width;
      c.height = m.height;
      const bctx = c.getContext("2d");
      for (let y = 0; y < m.height; y++) {
        for (let x = 0; x < m.width; x++) {
          const o = floor.objects[y][x];
          const g = floor.ground[y][x];
          const key = o ? m.objectMeta[o].sprite : (m.groundMeta[g] || {}).sprite;
          bctx.fillStyle = this.COLORS[key] || "#000";
          bctx.fillRect(x, y, 1, 1);
        }
      }
      return c;
    });
  },

  VIEW: 50,                  // tiles visíveis no minimapa
  follow: true,              // true = câmera segue o jogador
  cx: 50, cy: 50,            // centro quando follow = false (pan manual)
  lastView: null,            // {x0, y0, scale} do último frame (p/ cliques)

  pan(dx, dy) {
    const me = myPlayer();
    if (this.follow && me) { this.cx = me.x; this.cy = me.y; }
    this.follow = false;
    const half = this.VIEW / 2;
    this.cx = Math.max(half, Math.min(G.map.width - half, this.cx + dx));
    this.cy = Math.max(half, Math.min(G.map.height - half, this.cy + dy));
  },

  center() { this.follow = true; },

  /** Converte um clique no canvas do minimapa em tile do mapa. */
  tileAt(canvas, clientX, clientY) {
    if (!this.lastView) return null;
    const rect = canvas.getBoundingClientRect();
    const px = (clientX - rect.left) * (canvas.width / rect.width);
    const py = (clientY - rect.top) * (canvas.height / rect.height);
    return {
      x: Math.floor(this.lastView.x0 + px / this.lastView.scale),
      y: Math.floor(this.lastView.y0 + py / this.lastView.scale),
    };
  },

  draw() {
    if (!this.base) return;
    const me = myPlayer();
    if (!me) return;
    const ctx = this.ctx;
    const VIEW = this.VIEW;
    const scale = this.el.width / VIEW;
    const half = VIEW / 2;
    let cx, cy;
    if (this.follow) {
      cx = Math.max(half, Math.min(G.map.width - half, me.x));
      cy = Math.max(half, Math.min(G.map.height - half, me.y));
    } else {
      cx = this.cx; cy = this.cy;
    }
    const x0 = cx - half, y0 = cy - half;
    this.lastView = { x0, y0, scale };

    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, this.el.width, this.el.height);
    ctx.drawImage(this.base, x0, y0, VIEW, VIEW,
                  0, 0, this.el.width, this.el.height);
    // pontos das criaturas (só do andar atual)
    for (const e of G.entities.values()) {
      if ((e.z || 0) !== ((me.z) || 0)) continue;
      const dx = (e.x - x0) * scale;
      const dy = (e.y - y0) * scale;
      if (dx < 0 || dy < 0 || dx > this.el.width || dy > this.el.height) continue;
      ctx.fillStyle = e.id === G.myId ? "#fff"
        : e.kind === "player" ? "#9be36e"
        : e.kind === "npc" ? "#7fd4ee" : "#e33";
      ctx.fillRect(dx - 1.5, dy - 1.5, 3, 3);
    }
    this.drawBig();
  },

  /** Mapa-múndi expandido (modal): mapa inteiro, clicável para andar. */
  drawBig() {
    const modal = document.getElementById("map-modal");
    if (modal.classList.contains("hidden")) return;
    const big = document.getElementById("bigmap");
    const ctx = big.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    const s = big.width / G.map.width;        // px por tile
    if (!this.base) return;
    const me = myPlayer();
    ctx.drawImage(this.base, 0, 0, G.map.width, G.map.height,
                  0, 0, big.width, big.height);
    for (const e of G.entities.values()) {
      if ((e.z || 0) !== ((me && me.z) || 0)) continue;
      ctx.fillStyle = e.id === G.myId ? "#fff"
        : e.kind === "player" ? "#9be36e"
        : e.kind === "npc" ? "#7fd4ee" : "#e33";
      const r = e.id === G.myId ? 3 : 2;
      ctx.fillRect(e.x * s - r / 2, e.y * s - r / 2, r + 1, r + 1);
    }
  },
};
