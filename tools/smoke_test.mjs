/**
 * smoke_test.mjs — Teste de fumaça ponta a ponta do servidor Fibula.
 *
 * Uso:  node tools/smoke_test.mjs   (com o servidor rodando na porta 7777)
 *
 * Exercita o fluxo completo de jogo via WebSocket (igual ao cliente real):
 *   1. registro de conta + personagem
 *   2. welcome com mapa e definições
 *   3. movimentação em grid
 *   4. chat local e resposta de NPC
 *   5. spawn de monstro (admin), combate até a morte, exp e loot
 *   6. coleta do loot no chão
 *   7. comércio com NPC (compra)
 *   8. persistência: reloga e confere posição/inventário
 *
 * Sai com código 0 se tudo passou; 1 caso contrário.
 */
const URL = "ws://localhost:7777/ws";
// sufixo só com letras (nomes de personagem aceitam apenas letras e espaços)
const sufix = Array.from({ length: 6 },
  () => "abcdefghijklmnopqrstuvwxyz"[Math.floor(Math.random() * 26)]).join("");
const ACC = `smoke${sufix}`;
const PASS = "teste123";
const CHAR = `Smoke ${sufix[0].toUpperCase()}${sufix.slice(1)}`;

let failures = 0;
function check(cond, label) {
  console.log(`${cond ? "PASS" : "FAIL"}  ${label}`);
  if (!cond) failures++;
}

/** Sessão WebSocket com fila de mensagens e espera por tipo/predicado. */
class Session {
  constructor(ws) {
    this.ws = ws;
    this.queue = [];
    this.waiters = [];
    ws.addEventListener("message", (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "error") console.log(`INFO  servidor: "${msg.message}"`);
      const i = this.waiters.findIndex(w => w.pred(msg));
      if (i >= 0) this.waiters.splice(i, 1)[0].resolve(msg);
      else this.queue.push(msg);
    });
  }
  static async connect() {
    const ws = new WebSocket(URL);
    await new Promise((ok, err) => { ws.onopen = ok; ws.onerror = err; });
    return new Session(ws);
  }
  send(obj) { this.ws.send(JSON.stringify(obj)); }
  /** Espera a próxima mensagem que satisfaça o predicado (com timeout). */
  wait(pred, timeout = 8000, label = "") {
    const i = this.queue.findIndex(pred);
    if (i >= 0) return Promise.resolve(this.queue.splice(i, 1)[0]);
    return new Promise((resolve, reject) => {
      const w = { pred, resolve: (m) => { clearTimeout(t); resolve(m); } };
      const t = setTimeout(() => {
        this.waiters.splice(this.waiters.indexOf(w), 1);
        reject(new Error("timeout esperando " + label));
      }, timeout);
      this.waiters.push(w);
    });
  }
  waitType(type, timeout, label) {
    return this.wait(m => m.type === type, timeout, label || type);
  }
  close() { this.ws.close(); }
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function main() {
  // ---------- 1. registro ----------
  const s = await Session.connect();
  s.send({ type: "register", account: ACC, password: PASS, name: CHAR });
  const welcome = await s.waitType("welcome");
  check(welcome.name === CHAR, "registro: welcome com o nome do personagem");
  check(welcome.map && welcome.map.width === 100, "welcome: mapa 100x100");
  check(welcome.map.floors && welcome.map.floors.length === 2,
        "welcome: 2 andares (superfície + subsolo)");
  check(Object.keys(welcome.items).length > 10, "welcome: definições de itens");

  const stats = await s.waitType("stats");
  check(stats.level === 1 && stats.hp === 150, "stats iniciais (level 1, 150 hp)");
  check(stats.maxcap === 360, `capacity inicial (${stats.maxcap} oz)`);
  const skills = await s.waitType("skills", 8000, "payload de skills");
  check(skills.skills.sword.level === 10 && skills.skills.magic.level === 0,
        "skills iniciais (espada 10, magia 0)");
  check(!!skills.skills.distance && !!skills.skills.fishing,
        "skills novas presentes (distance, fishing)");
  const inv = await s.waitType("inv");
  check(inv.equip.weapon && inv.equip.weapon.id === 11, "kit inicial: clava equipada");
  check(inv.equip.backpack && inv.equip.backpack.id === 70,
        "kit inicial: mochila equipada");
  check(inv.active === 24, `slots ativos com mochila (${inv.active})`);
  const gold0 = inv.slots.reduce((a, sl) => a + (sl && sl.id === 1 ? sl.count : 0), 0);
  check(gold0 === 50, "kit inicial: 50 moedas de ouro");

  // espera o espawn de si mesmo para saber a posição
  const self0 = await s.wait(m => m.type === "espawn" && m.e.id === welcome.id,
                             8000, "espawn próprio");
  const startX = self0.e.x, startY = self0.e.y;
  tracked.set(welcome.id, { x: startX, y: startY });
  check(typeof startX === "number", `posição inicial (${startX},${startY}) [templo]`);

  // ---------- 2. movimento (norte: aproxima do Padre Élio) ----------
  s.send({ type: "move", dir: "n" });
  const mv = await s.wait(m => m.type === "emove" && m.id === welcome.id &&
                          m.y === startY - 1, 8000, "emove para o norte");
  tracked.set(welcome.id, { x: mv.x, y: mv.y });
  check(mv.y === startY - 1, "movimentação em grid (norte)");

  // ---------- 3. chat + NPC ----------
  s.send({ type: "say", text: "oi" });
  const echo = await s.wait(m => m.type === "chat" && m.from === CHAR, 8000,
                            "eco do próprio say");
  check(echo.text === "oi", "chat local ecoado");
  // Padre Élio fica no templo, a 3 tiles — deve cumprimentar
  const npcReply = await s.wait(m => m.type === "chat" && m.channel === "npc",
                                8000, "resposta do NPC");
  check(npcReply.text.includes(CHAR.split(" ")[0]) || npcReply.text.length > 0,
        `NPC respondeu: "${npcReply.text}"`);

  // ---------- 3.5 magia: exura consome mana ----------
  s.send({ type: "say", text: "exura" });
  const stMagic = await s.wait(m => m.type === "stats" && m.mp < 50, 5000,
                               "stats pós-exura");
  check(stMagic.mp === 25, `magia exura consumiu 25 de mana (mp ${stMagic.mp})`);

  // ---------- 3.6 walk-to (clique para andar) ----------
  s.send({ type: "walkto", x: startX, y: startY + 2 });
  const wt = await s.wait(m => m.type === "emove" && m.id === welcome.id &&
                          m.x === startX && m.y === startY + 2, 8000,
                          "walkto (autowalk)");
  check(wt.y === startY + 2, "walk-to: caminho percorrido automaticamente");
  tracked.set(welcome.id, { x: wt.x, y: wt.y });

  // ---------- 3.7 diagonal (sai do templo pela porta, em "se") ----------
  // reenvia como o cliente real (tecla segurada): o 1º pode cair no cooldown
  const iv = setInterval(() => s.send({ type: "move", dir: "se" }), 250);
  let dg;
  try {
    dg = await s.wait(m => m.type === "emove" && m.id === welcome.id &&
                      m.x === startX + 1 && m.y === startY + 3, 8000,
                      "movimento diagonal");
  } finally { clearInterval(iv); }
  check(true, "movimento diagonal (se)");
  tracked.set(welcome.id, { x: dg.x, y: dg.y });

  // ---------- 3.8 postura + PvP + mover item de slot ----------
  s.send({ type: "stance", mode: "attack" });
  await s.wait(m => m.type === "stats" && m.stance === "attack", 5000, "stance");
  check(true, "postura full ataque aplicada");
  s.send({ type: "stance", mode: "balanced" });

  s.send({ type: "pvp", on: true });
  await s.wait(m => m.type === "stats" && m.pvp === true, 5000, "pvp on");
  check(true, "modo PvP ligado");
  s.send({ type: "pvp", on: false });

  // snapshot do inv (move_item 0->0 é no-op mas devolve o inv compactado)
  s.send({ type: "move_item", from: 0, to: 0 });
  const inv0 = await s.wait(m => m.type === "inv", 5000, "inv snapshot");
  const goldSlot = inv0.slots.findIndex(x => x && x.id === 1);
  check(goldSlot >= 0 && inv0.slots[goldSlot].count === 50,
        "kit: 50 ouro empilhado num slot");

  // split: separa 10 de ouro num slot vazio (sem deixar buraco entre itens)
  const emptySlot = inv0.slots.findIndex(x => x === null);
  s.send({ type: "move_item", from: goldSlot, to: emptySlot, count: 10 });
  const invSplit = await s.wait(m => {
    if (m.type !== "inv") return false;
    const g = m.slots.filter(x => x && x.id === 1);
    return g.length === 2 && g.some(s => s.count === 40) && g.some(s => s.count === 10);
  }, 5000, "split de ouro");
  check(true, "split de pilha: 50 ouro -> 40 + 10");

  // compactação: itens nos primeiros slots, sem buracos no meio
  const lastItem = invSplit.slots.reduce((a, x, i) => x ? i : a, -1);
  const firstNull = invSplit.slots.findIndex(x => x === null);
  check(firstNull === -1 || firstNull > lastItem,
        "slots compactados (sem buracos entre itens)");

  // merge: junta as duas pilhas de volta num slot só
  const golds = invSplit.slots.map((x, i) => ({ x, i })).filter(o => o.x && o.x.id === 1);
  s.send({ type: "move_item", from: golds[1].i, to: golds[0].i, count: 10 });
  await s.wait(m => m.type === "inv"
               && m.slots.filter(x => x && x.id === 1).length === 1
               && m.slots.some(x => x && x.id === 1 && x.count === 50),
               5000, "merge de ouro");
  check(true, "merge de pilha: 40 + 10 -> 50");

  // ---------- 4. combate (conta 1 já existe? somos admin só se conta id 1) ----------
  // /spawn exige admin (primeira conta do banco). Se não formos admin,
  // caminhamos até a zona de ratos — mais lento. Tentamos /spawn primeiro.
  s.send({ type: "say", text: "/spawn rat" });
  let rat = null;
  try {
    const sp = await s.wait(m => m.type === "espawn" && m.e.kind === "monster",
                            3000, "spawn de rato");
    rat = sp.e;
    tracked.set(rat.id, { x: rat.x, y: rat.y });
  } catch {
    console.log("INFO  sem admin (/spawn negado) — indo a pé até os ratos");
    // anda para o leste até encontrar um rato (sai da cidade pela rua y=50)
    for (let i = 0; i < 200 && !rat; i++) {
      const me = await currentPos(s, welcome.id);
      const dir = me.y > 50 ? "n" : me.y < 50 ? "s" : "e";
      s.send({ type: "move", dir });
      await sleep(420);
      for (const m of s.queue) {
        if (m.type === "espawn" && m.e.kind === "monster") { rat = m.e; break; }
      }
    }
  }
  check(!!rat, `monstro visível: ${rat ? rat.name : "nenhum"}`);

  // avisa se há outros jogadores online (podem "roubar" o monstro do teste)
  s.send({ type: "say", text: "/online" });
  try {
    const on = await s.wait(m => m.type === "chat" && m.text.startsWith("Online"),
                            3000, "/online");
    if (!on.text.includes("(1)")) {
      console.log(`AVISO ${on.text} — outro jogador pode interferir no teste!`);
    }
  } catch { /* segue */ }

  // aproxima e ataca até matar. A morte É CONFIRMADA pela mensagem de LOOT
  // (o edespawn sozinho não basta: dispara se o monstro sai da visão ou se
  // outro jogador o matar). Se o alvo sumir sem loot, tenta outro monstro.
  async function hunt(mob) {
    let loot = null, despawnAt = -1;
    s.send({ type: "attack", id: mob.id });
    await s.waitType("target");
    for (let i = 0; i < 150 && !loot; i++) {
      const r = posOf(s, mob.id);
      if (r) { mob.x = r.x; mob.y = r.y; }
      // persegue usando o autowalk do servidor (BFS desvia de obstáculos;
      // como o tile do monstro está ocupado, o caminho mira um tile adjacente)
      if (despawnAt < 0 && i % 4 === 0) {
        s.send({ type: "walkto", x: mob.x, y: mob.y });
      }
      await sleep(250);
      drainTrack(s, welcome.id, mob.id);
      for (let qi = 0; qi < s.queue.length; qi++) {
        const m = s.queue[qi];
        if (m.type === "edespawn" && m.id === mob.id && despawnAt < 0) despawnAt = i;
        if (m.type === "chat" && m.channel === "loot") loot = m.text;
      }
      if (despawnAt >= 0 && i - despawnAt > 12) {
        if (!loot) return null;                // sumiu sem loot: desiste deste
        break;
      }
    }
    return loot;
  }

  let lootMsg = null;
  if (rat) lootMsg = await hunt(rat);
  if (!lootMsg) {
    // segunda chance: outro monstro que esteja na visão
    const other = [...monstersSeen.values()].find(e => rat && e.id !== rat.id);
    if (other) {
      console.log(`INFO  alvo perdido — tentando outro: ${other.name}`);
      lootMsg = await hunt(other);
    }
  }
  check(!!lootMsg, `combate + loot: "${lootMsg}"`);
  // a exp chega num stats logo após a morte
  let statsAfter = lastStats(s);
  if (!statsAfter || !statsAfter.exp) {
    try {
      statsAfter = await s.wait(m => m.type === "stats" && m.exp > 0, 3000,
                                "stats com exp");
    } catch { statsAfter = lastStats(s) || stats; }
  }
  check(statsAfter.exp > 0, `exp ganha (${statsAfter.exp})`);

  // ---------- 5. saquear o corpo (o loot fica DENTRO do corpo) ----------
  const me2 = posOf(s, welcome.id);
  let corpseTile = null;
  for (const [key, items] of collectGround(s)) {
    if (!items.some(it => it.id === 90)) continue;       // 90 = corpo
    const [gx, gy] = key.split(",").map(Number);
    if (Math.max(Math.abs(gx - me2.x), Math.abs(gy - me2.y)) <= 1) {
      corpseTile = { x: gx, y: gy };
      break;
    }
  }
  check(!!corpseTile, "corpo da criatura no chão (adjacente)");
  if (corpseTile) {
    s.send({ type: "open_container", x: corpseTile.x, y: corpseTile.y });
    const cont = await s.waitType("container", 5000, "janela do corpo");
    check(cont.name.startsWith("corpo de"),
          `container aberto: "${cont.name}" (${cont.items.length} item/ns)`);
    if (cont.items.length) {
      s.send({ type: "loot", x: cont.x, y: cont.y, idx: 0 });
      const got = await s.wait(m => m.type === "chat" &&
                               m.text.startsWith("Voce pegou"), 5000,
                               "saque do corpo");
      check(true, `saqueado do corpo: "${got.text}"`);
    } else {
      console.log("INFO  corpo vazio (loot 'nada') — ok");
    }
  }

  // ---------- 5.1 look em item da mochila (acha o slot do pão dinamicamente) ----------
  s.send({ type: "move_item", from: 0, to: 0 });    // no-op: devolve o inv atual
  const invLk = await s.wait(m => m.type === "inv", 5000, "inv p/ look");
  const breadSlot = invLk.slots.findIndex(x => x && x.id === 52);
  s.send({ type: "look_item", slot: breadSlot });
  const lk = await s.wait(m => m.type === "chat" && m.channel === "look",
                          5000, "look na mochila");
  check(lk.text.includes("pao"), `look na mochila: "${lk.text}"`);

  // ---------- 6. comércio (compra do Tobias via mensagem direta) ----------
  // teleporta de volta se admin; senão pula (já validamos buy no servidor)
  s.send({ type: "say", text: "/goto 41 41" });
  await sleep(400);
  const meAtShop = posOf(s, welcome.id);
  if (meAtShop && Math.abs(meAtShop.x - 41) <= 3 && Math.abs(meAtShop.y - 41) <= 3) {
    const countBread = (inv) => inv.slots.reduce(
      (a, sl) => a + (sl && sl.id === 52 ? sl.count : 0), 0);
    s.send({ type: "npc_buy", npc: "Tobias", item: 52, count: 1 });
    try {
      // espera o inv em que os pães aumentaram (ignora invs antigos na fila)
      const invAfter = await s.wait(
        m => m.type === "inv" && countBread(m) >= 4, 3000, "inv pós-compra");
      check(true, `compra no NPC: agora tem ${countBread(invAfter)} pães`);
    } catch { check(false, "compra no NPC (sem resposta)"); }
  } else {
    console.log("INFO  sem admin para /goto — teste de compra pulado");
  }

  // ---------- 7. persistência ----------
  // os monstros agora vêm da área de visão e podem matar o bot nível 1 →
  // renasce no templo. Se isso aconteceu, a posição esperada é o templo.
  let died = s.queue.some(m => m.type === "dead");
  const posBefore = died ? { x: 25, y: 42 } : posOf(s, welcome.id);
  const expBefore = (lastStats(s) || statsAfter).exp;   // exp mais recente
  s.send({ type: "say", text: "/save" });
  await sleep(300);
  s.close();
  await sleep(500);

  const s2 = await Session.connect();
  s2.send({ type: "login", account: ACC, password: PASS });
  const w2 = await s2.waitType("welcome", 8000, "relogin");
  check(w2.name === CHAR, "relogin com a mesma conta");
  const self2 = await s2.wait(m => m.type === "espawn" && m.e.id === w2.id,
                              8000, "espawn pós-relogin");
  check(Math.abs(self2.e.x - posBefore.x) <= 5 &&
        Math.abs(self2.e.y - posBefore.y) <= 5,
        `posição persistida (${self2.e.x},${self2.e.y})${died ? " [morreu]" : ""}`);
  const st2 = await s2.waitType("stats");
  check(st2.exp === expBefore, `exp persistida (${st2.exp})`);

  // senha errada deve falhar
  const s3 = await Session.connect();
  s3.send({ type: "login", account: ACC, password: "errada" });
  const err = await s3.waitType("error", 8000, "erro de senha");
  check(err.message.includes("invalida"), "login com senha errada é rejeitado");
  s3.close();
  s2.close();

  console.log("\n" + (failures === 0 ? "✅ SMOKE TEST: tudo passou"
                                     : `❌ SMOKE TEST: ${failures} falha(s)`));
  process.exit(failures === 0 ? 0 : 1);
}

// ---------------------------------------------------------------- helpers

/** Última posição conhecida de uma entidade varrendo a fila. */
const tracked = new Map();
const monstersSeen = new Map();   // todos os monstros que já entraram na visão
function drainTrack(s, ...ids) {
  for (const m of s.queue) {
    if (m.type === "espawn") {
      if (m.e.kind === "monster") monstersSeen.set(m.e.id, m.e);
      if (ids.includes(m.e.id)) tracked.set(m.e.id, m.e);
    }
    if (m.type === "emove") {
      if (monstersSeen.has(m.id)) {
        const e = monstersSeen.get(m.id);
        e.x = m.x; e.y = m.y;
      }
      if (ids.includes(m.id)) tracked.set(m.id, { x: m.x, y: m.y });
    }
    if (m.type === "stats") tracked.set("stats", m);
    if (m.type === "ground")
      tracked.set("g:" + m.x + "," + m.y, m.items);
  }
}
function posOf(s, id) { drainTrack(s, id); return tracked.get(id); }
async function currentPos(s, id) { return posOf(s, id) || { x: 0, y: 0 }; }
function lastStats(s) { drainTrack(s); return tracked.get("stats"); }
function collectGround(s) {
  drainTrack(s);
  const out = new Map();
  for (const [k, v] of tracked) {
    if (String(k).startsWith("g:") && v.length) out.set(k.slice(2), v);
  }
  return out;
}

main().catch(err => {
  console.error("FAIL  exceção:", err.message);
  process.exit(1);
});
