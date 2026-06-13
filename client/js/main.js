/**
 * main.js — Bootstrap do cliente: assets, login e fiação dos módulos.
 */
(async function boot() {
  // index.html aberto direto do disco (file://)? O jogo precisa ser servido
  // pelo servidor — instruí o jogador e redireciona sozinho se ele estiver no ar.
  if (location.protocol === "file:") {
    UI.$("login-error").innerHTML =
      "Nao abra o index.html direto.<br>Inicie o <b>start.bat</b> e acesse " +
      '<a href="http://localhost:7777" style="color:#c9a45a">' +
      "http://localhost:7777</a>";
    const tryRedirect = () =>
      fetch("http://localhost:7777/assets/sprites.json")
        .then(() => { location.href = "http://localhost:7777"; })
        .catch(() => setTimeout(tryRedirect, 2000));
    tryRedirect();
    return;
  }

  try {
    await Render.loadAssets();
  } catch (err) {
    UI.loginError("Erro carregando sprites: " + err.message);
    return;
  }
  Render.init();
  Input.init();
  UI.initInventoryButtons();
  UI.initTrade();
  UI.initMapControls();
  UI.initCombatControls();
  UI.initWindows();
  UI.initChatTabs();
  UI.initChatResize();
  UI.initBattle();

  const account = UI.$("in-account");
  const password = UI.$("in-password");
  const charname = UI.$("in-charname");

  function doLogin() {
    UI.loginError("");
    Net.connect()
      .then(() => Net.send({
        type: "login",
        account: account.value.trim(),
        password: password.value,
      }))
      .catch(err => UI.loginError(err.message));
  }

  function doRegister() {
    const extra = UI.$("register-extra");
    if (extra.classList.contains("hidden")) {
      // primeiro clique: revela o campo de nome do personagem
      extra.classList.remove("hidden");
      charname.focus();
      UI.loginError("Escolha o nome do seu personagem e clique de novo.");
      return;
    }
    UI.loginError("");
    Net.connect()
      .then(() => Net.send({
        type: "register",
        account: account.value.trim(),
        password: password.value,
        name: charname.value.trim(),
        vocation: UI.$("in-vocation").value,
      }))
      .catch(err => UI.loginError(err.message));
  }

  UI.$("btn-login").onclick = doLogin;
  UI.$("btn-register").onclick = doRegister;
  [account, password, charname].forEach(el => {
    el.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") doLogin();
      ev.stopPropagation();
    });
  });

  Net.onDisconnect = () => {
    if (G.loggedIn) {
      G.loggedIn = false;
      UI.showLogin("Conexao perdida com o servidor.");
    }
  };

  // keepalive para a conexão não cair por inatividade
  setInterval(() => { if (G.loggedIn) Net.send({ type: "ping" }); }, 30000);

  account.focus();
})();
