/**
 * game.js — Estado do cliente + handlers das mensagens do servidor.
 *
 * `G` é a única fonte de verdade do cliente; render.js desenha a partir
 * dele e ui.js espelha inventário/stats/chat no DOM. O servidor manda o
 * estado — o cliente nunca "decide" nada de gameplay.
 */
const G = {
  myId: 0,
  myName: "",
  admin: false,
  map: null,                 // mapa estático (welcome)
  entities: new Map(),       // id -> entidade (com interpolação de movimento)
  ground: new Map(),         // "x,y" -> [{id, count}]
  stats: null,
  inv: { slots: [], equip: {} },
  targetId: 0,
  floats: [],                // textos flutuantes {x, y, text, color, t0, ttl}
  fxs: [],                   // efeitos {x, y, kind, t0}
  warns: [],                 // avisos de respawn {x, y, z, t0, ttl}
  trade: null,               // janela de comércio aberta {npc, sells, buys}
  containers: new Map(),     // corpos abertos: "x,y" -> {x, y, name, items}
  projs: [],                 // projéteis voando {fx,fy,tx,ty,sprite,t0,dur}
  hotkeys: {},               // hotkeys do personagem (vem no welcome)
  loggedIn: false,
};

/** Definições de itens (id -> {name, sprite, ...}), enviadas no welcome. */
let ItemDefs = {};

function groundKey(x, y, z) { return x + "," + y + "," + z; }

/** Posição interpolada (em pixels de mundo) de uma entidade. */
function entityPixelPos(e) {
  const now = performance.now();
  if (!e.animDur || now >= e.animStart + e.animDur) {
    return { px: e.x * 32, py: e.y * 32 };
  }
  const t = (now - e.animStart) / e.animDur;
  return {
    px: (e.fromX + (e.x - e.fromX) * t) * 32,
    py: (e.fromY + (e.y - e.fromY) * t) * 32,
  };
}

function myPlayer() { return G.entities.get(G.myId); }

// ------------------------------------------------ handlers de mensagens

Net.on("welcome", (m) => {
  G.myId = m.id;
  G.myName = m.name;
  G.admin = m.admin;
  G.map = m.map;
  ItemDefs = m.items || {};
  G.entities.clear();
  G.ground.clear();
  G.warns = [];
  G.projs = [];
  G.containers.clear();
  G.hotkeys = m.hotkeys || {};
  G.targetId = 0;
  G.loggedIn = true;
  UI.enterGame();
  UI.chatLine("server", "", m.motd);
  Minimap.build();
});

Net.on("stats", (m) => { G.stats = m; UI.renderStats(); });

Net.on("inv", (m) => {
  G.inv.slots = m.slots;
  G.inv.equip = m.equip;
  G.inv.active = m.active;
  UI.renderInventory();
  if (G.trade) UI.renderTrade();   // atualiza "quantos você tem" na loja
});

Net.on("espawn", (m) => {
  const e = m.e;
  e.animDur = 0;
  G.entities.set(e.id, e);
});

Net.on("edespawn", (m) => { G.entities.delete(m.id); });

Net.on("emove", (m) => {
  const e = G.entities.get(m.id);
  if (!e) return;
  const floorChanged = m.z !== undefined && m.z !== e.z;
  e.fromX = e.x; e.fromY = e.y;
  e.x = m.x; e.y = m.y; e.dir = m.dir;
  if (m.z !== undefined) e.z = m.z;
  e.animStart = performance.now();
  e.animDur = floorChanged ? 0 : (m.ms || 0);   // troca de andar é instantânea
  if (m.id === G.myId) Minimap.center();        // andou: minimapa volta a seguir
});

// caveira (agressor PvP) acende/apaga
Net.on("eskull", (m) => {
  const e = G.entities.get(m.id);
  if (e) e.skull = m.on;
});

// logout aceito pelo servidor
Net.on("logged_out", () => {
  G.loggedIn = false;
  UI.showLogin("Ate logo!");
});

Net.on("skills", (m) => { UI.renderSkills(m.skills); });

Net.on("ehp", (m) => {
  const e = G.entities.get(m.id);
  if (e) { e.hp = m.hp; e.maxhp = m.maxhp; }
});

Net.on("ground_full", (m) => {
  G.ground.clear();
  for (const t of m.tiles) G.ground.set(groundKey(t.x, t.y, t.z), t.items);
});

Net.on("ground", (m) => {
  if (m.items.length) G.ground.set(groundKey(m.x, m.y, m.z), m.items);
  else G.ground.delete(groundKey(m.x, m.y, m.z));
});

Net.on("chat", (m) => {
  UI.chatLine(m.channel, m.from, m.text);
  // balão de fala flutuante para conversas locais
  if ((m.channel === "say" || m.channel === "npc") && m.x !== undefined) {
    G.floats.push({
      x: m.x, y: m.y, text: m.text.slice(0, 30),
      color: m.channel === "npc" ? "#7fd4ee" : "#f3eecf",
      t0: performance.now(), ttl: 2500, rise: 10,
    });
  }
});

Net.on("fx", (m) => {
  const now = performance.now();
  if (m.kind) G.fxs.push({ x: m.x, y: m.y, kind: m.kind, t0: now });
  if (m.text !== undefined) {
    G.floats.push({ x: m.x, y: m.y, text: m.text, color: m.color || "#fff",
                    t0: now, ttl: 1000, rise: 24 });
  }
});

Net.on("target", (m) => { G.targetId = m.id; UI.renderBattle(); });

// aviso de respawn: bolinha azul pulsante no tile onde o monstro vai nascer
Net.on("spawn_warn", (m) => {
  G.warns.push({ x: m.x, y: m.y, z: m.z || 0,
                 t0: performance.now(), ttl: m.ms || 5000 });
});

Net.on("dead", (m) => { UI.showDead(m.message); });

Net.on("npc_trade", (m) => { G.trade = m; UI.openTrade(); });

// corpos abertos (janelas de loot, várias ao mesmo tempo)
Net.on("container", (m) => { UI.renderContainer(m); });
Net.on("container_close", (m) => {
  if (m.x !== undefined) UI.closeContainer(m.x, m.y, false);
  else UI.closeAllContainers(false);
});

// projétil (flecha/lança) voando
Net.on("proj", (m) => {
  G.projs.push({ fx: m.fx, fy: m.fy, tx: m.tx, ty: m.ty,
                 sprite: m.sprite, t0: performance.now(), dur: 220 });
});

Net.on("error", (m) => {
  if (G.loggedIn) UI.chatLine("error", "", m.message);
  else UI.loginError(m.message);
});

Net.on("pong", () => {});
