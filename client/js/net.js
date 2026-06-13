/**
 * net.js — Conexão WebSocket com o servidor.
 *
 * Protocolo: mensagens JSON { type: "...", ... } nos dois sentidos.
 * Os handlers de cada tipo são registrados pelos outros módulos via Net.on().
 */
const Net = {
  ws: null,
  handlers: {},
  onDisconnect: null,

  /** Registra o handler de um tipo de mensagem do servidor. */
  on(type, fn) { this.handlers[type] = fn; },

  /** Abre (ou reaproveita) a conexão. Retorna uma Promise. */
  connect() {
    return new Promise((resolve, reject) => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) return resolve();
      const proto = location.protocol === "https:" ? "wss" : "ws";
      this.ws = new WebSocket(`${proto}://${location.host}/ws`);
      this.ws.onopen = () => resolve();
      this.ws.onerror = () => reject(new Error("Falha ao conectar ao servidor."));
      this.ws.onclose = () => { if (this.onDisconnect) this.onDisconnect(); };
      this.ws.onmessage = (ev) => {
        let msg;
        try { msg = JSON.parse(ev.data); } catch { return; }
        const fn = this.handlers[msg.type];
        if (fn) fn(msg);
        else console.warn("mensagem sem handler:", msg.type, msg);
      };
    });
  },

  send(obj) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(obj));
    }
  },
};
