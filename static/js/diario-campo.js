/* m096 — Diário de bordo no celular do motorista, mesmo sem internet.
 *
 * Cada alteração de um trecho vira um lançamento com id gerado aqui e vai para
 * uma fila guardada no celular (IndexedDB; localStorage se não houver). A fila é
 * enviada em ordem quando há conexão, com nova tentativa espaçada se falhar. O
 * servidor aceita o mesmo lançamento mais de uma vez sem gravar de novo (pelo
 * id), então reenviar depois de uma queda é seguro.
 *
 * Estados de um trecho: "Salvo no celular" (na fila), "Enviado" e "Recusado"
 * (o servidor não aceitou — ex.: km de chegada menor que o de saída).
 */
(function () {
  "use strict";

  var corpo = document.body;
  var TOKEN = corpo.dataset.token;
  var URL_ENVIAR = corpo.dataset.urlEnviar;
  var URL_SW = corpo.dataset.urlSw;
  var dadosIniciais = JSON.parse(document.getElementById("dc-dados").textContent);

  var elTrechos = document.querySelector("[data-dc-trechos]");
  var elEstado = document.querySelector("[data-dc-estado]");
  var elBloqueio = document.querySelector("[data-dc-bloqueio]");
  var elAvisos = document.querySelector("[data-dc-avisos]");
  var elAvisosLista = document.querySelector("[data-dc-avisos-lista]");
  var elTotal = document.querySelector("[data-dc-total]");
  var elEnviar = document.querySelector("[data-dc-enviar]");
  var modelo = document.getElementById("dc-modelo-trecho");

  // Estado guardado no celular, por link: valores digitados, fila e o que o
  // servidor devolveu por último.
  var estado = { valores: {}, fila: [], servidor: dadosIniciais, recusas: {} };
  var bloqueado = false;
  var enviando = false;
  var espera = 0;
  var temporizador = null;

  // --- Armazenamento local ------------------------------------------------
  var CHAVE = "diario-campo:" + TOKEN;
  var bancoPromessa = null;

  function banco() {
    if (bancoPromessa) return bancoPromessa;
    bancoPromessa = new Promise(function (resolve) {
      if (!window.indexedDB) return resolve(null);
      try {
        var pedido = indexedDB.open("diario-campo", 1);
        pedido.onupgradeneeded = function () { pedido.result.createObjectStore("diarios"); };
        pedido.onsuccess = function () { resolve(pedido.result); };
        pedido.onerror = function () { resolve(null); };
      } catch (e) { resolve(null); }
    });
    return bancoPromessa;
  }

  function carregar() {
    return banco().then(function (db) {
      if (!db) {
        try { return JSON.parse(localStorage.getItem(CHAVE) || "null"); } catch (e) { return null; }
      }
      return new Promise(function (resolve) {
        var req = db.transaction("diarios").objectStore("diarios").get(TOKEN);
        req.onsuccess = function () { resolve(req.result || null); };
        req.onerror = function () { resolve(null); };
      });
    });
  }

  function guardar() {
    var copia = { valores: estado.valores, fila: estado.fila, servidor: estado.servidor, recusas: estado.recusas };
    return banco().then(function (db) {
      if (!db) {
        try { localStorage.setItem(CHAVE, JSON.stringify(copia)); } catch (e) { /* sem espaço: segue só na memória */ }
        return;
      }
      return new Promise(function (resolve) {
        var tx = db.transaction("diarios", "readwrite");
        tx.objectStore("diarios").put(copia, TOKEN);
        tx.oncomplete = resolve;
        tx.onerror = resolve;
      });
    });
  }

  // --- Utilidades ---------------------------------------------------------
  function novoId() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    var bytes = new Uint8Array(16);
    (window.crypto || window.msCrypto).getRandomValues(bytes);
    return Array.prototype.map.call(bytes, function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
  }

  function km(valor) {
    var digitos = String(valor == null ? "" : valor).replace(/\D/g, "");
    return digitos ? parseInt(digitos, 10) : null;
  }

  function fmt(n) { return n == null ? "" : String(n).replace(/\B(?=(\d{3})+(?!\d))/g, "."); }

  function trechos() { return (estado.servidor && estado.servidor.trechos) || []; }

  function valorDe(linha, campo) {
    var local = estado.valores[linha.id];
    if (local && campo in local) return local[campo];
    return linha[campo];
  }

  function pendentes(linhaId) {
    return estado.fila.filter(function (l) { return l.linha === linhaId; }).length;
  }

  // --- Tela ---------------------------------------------------------------
  function montar() {
    elTrechos.innerHTML = "";
    var lista = trechos();
    if (!lista.length) {
      elTrechos.innerHTML = '<p class="dc-cartao">A viagem ainda não tem trechos no roteiro. Avise quem enviou o link.</p>';
      return;
    }
    lista.forEach(function (linha) {
      var no = modelo.content.firstElementChild.cloneNode(true);
      no.dataset.id = linha.id;
      no.querySelector("[data-dc-ordem]").textContent = linha.ordem;
      no.querySelector("[data-dc-rota]").textContent = (linha.origem || "—") + " → " + (linha.destino || "—");
      var datas = [];
      if (linha.saida) datas.push("Saída " + linha.saida);
      if (linha.chegada) datas.push("chegada " + linha.chegada);
      if (linha.prevista) datas.push("≈ " + fmt(linha.prevista) + " km");
      no.querySelector("[data-dc-datas]").textContent = datas.join(" · ");
      no.querySelectorAll('input[type="radio"]').forEach(function (r) { r.name = "abastecimento-" + linha.id; });
      elTrechos.appendChild(no);
    });
    preencher();
  }

  function preencher() {
    var anterior = null;
    trechos().forEach(function (linha) {
      var no = elTrechos.querySelector('[data-dc-linha][data-id="' + linha.id + '"]');
      if (!no) return;
      var ini = valorDe(linha, "km_inicial");
      var fim = valorDe(linha, "km_final");
      var abast = valorDe(linha, "abastecimento");
      var campoIni = no.querySelector('[data-dc-campo="km_inicial"]');
      var campoFim = no.querySelector('[data-dc-campo="km_final"]');
      if (document.activeElement !== campoIni) campoIni.value = ini == null ? "" : ini;
      if (document.activeElement !== campoFim) campoFim.value = fim == null ? "" : fim;
      no.querySelectorAll('[data-dc-campo="abastecimento"]').forEach(function (r) {
        r.checked = (abast === true && r.value === "sim") || (abast === false && r.value === "nao");
      });
      // Sugestões do hodômetro encadeado: a saída pela chegada do trecho
      // anterior, a chegada pela saída + distância prevista.
      var sugIni = ini == null && anterior && valorDe(anterior, "km_final") != null ? valorDe(anterior, "km_final") : null;
      var baseFim = ini != null ? ini : sugIni;
      var sugFim = fim == null && baseFim != null && linha.prevista ? baseFim + linha.prevista : null;
      sugerir(no, "km_inicial", sugIni);
      sugerir(no, "km_final", sugFim);
      campoIni.placeholder = sugIni != null ? fmt(sugIni) : "0";
      campoFim.placeholder = sugFim != null ? "≈ " + fmt(sugFim) : "0";
      estadoDaLinha(no, linha.id);
      anterior = linha;
    });
    var s = estado.servidor || {};
    var avisos = s.avisos || [];
    elAvisos.hidden = !avisos.length;
    elAvisosLista.innerHTML = "";
    avisos.forEach(function (a) { var li = document.createElement("li"); li.textContent = a; elAvisosLista.appendChild(li); });
    elTotal.textContent = s.total_previsto ? "Rodado: " + fmt(s.total_rodado || 0) + " km · previsto: " + fmt(s.total_previsto) + " km" : "";
    estadoGeral();
  }

  function sugerir(no, campo, valor) {
    var botao = no.querySelector('[data-dc-sugerir="' + campo + '"]');
    botao.hidden = valor == null || bloqueado;
    botao.dataset.valor = valor == null ? "" : valor;
    botao.textContent = valor == null ? "" : "Usar " + fmt(valor);
  }

  function estadoDaLinha(no, id) {
    var el = no.querySelector("[data-dc-linha-estado]");
    if (estado.recusas[id]) { el.dataset.tom = "erro"; el.textContent = "Não aceito: " + estado.recusas[id]; return; }
    if (pendentes(id)) { el.dataset.tom = "pendente"; el.textContent = "Salvo no celular — será enviado"; return; }
    if (estado.valores[id] && estado.valores[id].enviado) { el.dataset.tom = "ok"; el.textContent = "Enviado ✓"; return; }
    el.dataset.tom = ""; el.textContent = "";
  }

  function estadoGeral() {
    var n = estado.fila.length;
    if (bloqueado) { elEstado.hidden = true; elEnviar.disabled = true; return; }
    elEstado.hidden = false;
    if (n) {
      elEstado.dataset.tom = "";
      elEstado.textContent = n + (n === 1 ? " lançamento salvo no celular" : " lançamentos salvos no celular") +
        (navigator.onLine === false ? " — aguardando internet" : enviando ? " — enviando…" : " — será enviado");
    } else {
      elEstado.dataset.tom = "ok";
      elEstado.textContent = "Tudo enviado ✓";
    }
    elEnviar.hidden = !n;
    elEnviar.disabled = enviando;
  }

  function bloquear(mensagem) {
    bloqueado = true;
    elBloqueio.textContent = mensagem;
    elBloqueio.hidden = false;
    elTrechos.querySelectorAll("input").forEach(function (i) { i.disabled = true; });
    estadoGeral();
  }

  // --- Lançamentos --------------------------------------------------------
  function lancar(no) {
    if (bloqueado) return;
    var id = parseInt(no.dataset.id, 10);
    var ini = km(no.querySelector('[data-dc-campo="km_inicial"]').value);
    var fim = km(no.querySelector('[data-dc-campo="km_final"]').value);
    var marcado = no.querySelector('[data-dc-campo="abastecimento"]:checked');
    var valores = { km_inicial: ini, km_final: fim };
    if (marcado) valores.abastecimento = marcado.value === "sim";
    var atual = estado.valores[id] || {};
    var linha = trechos().filter(function (t) { return t.id === id; })[0] || {};
    var mudou = ["km_inicial", "km_final", "abastecimento"].some(function (c) {
      return c in valores && valores[c] !== (c in atual ? atual[c] : linha[c]);
    });
    if (!mudou) return;
    estado.valores[id] = Object.assign({}, atual, valores, { enviado: false });
    delete estado.recusas[id];
    // Um lançamento ainda não enviado do mesmo trecho é trocado pelo novo: ele
    // leva o trecho inteiro. O que já está a caminho fica (o servidor responde).
    estado.fila = estado.fila.filter(function (l) { return l.linha !== id || l.aCaminho; });
    estado.fila.push(Object.assign({ id: novoId(), linha: id, criado_em: new Date().toISOString() }, valores));
    guardar().then(function () { preencher(); agendar(0); });
  }

  function agendar(ms) {
    clearTimeout(temporizador);
    temporizador = setTimeout(enviar, ms);
  }

  function enviar() {
    if (enviando || bloqueado || !estado.fila.length) { estadoGeral(); return; }
    enviando = true;
    var lote = estado.fila.slice(0, 50);
    lote.forEach(function (l) { l.aCaminho = true; });
    estadoGeral();
    var corpoEnvio = JSON.stringify({
      lancamentos: lote.map(function (l) {
        var item = { id: l.id, linha: l.linha, km_inicial: l.km_inicial, km_final: l.km_final };
        if ("abastecimento" in l) item.abastecimento = l.abastecimento;
        return item;
      }),
    });
    fetch(URL_ENVIAR, {
      method: "POST",
      credentials: "omit",
      headers: { "Content-Type": "application/json", "X-Diario-Campo": "1" },
      body: corpoEnvio,
    }).then(function (resp) {
      return resp.json().catch(function () { return {}; }).then(function (dados) { return { status: resp.status, dados: dados }; });
    }).then(function (r) {
      enviando = false;
      if (r.status === 200 && r.dados.ok) {
        var feitos = {};
        (r.dados.resultados || []).forEach(function (res) {
          feitos[res.id] = true;
          var l = lote.filter(function (x) { return x.id === res.id; })[0];
          if (!l) return;
          if (res.situacao === "recusado") estado.recusas[l.linha] = res.mensagem || "valor não aceito";
        });
        estado.fila = estado.fila.filter(function (l) { return !feitos[l.id]; });
        lote.forEach(function (l) {
          if (feitos[l.id] && !estado.recusas[l.linha] && !pendentes(l.linha) && estado.valores[l.linha]) estado.valores[l.linha].enviado = true;
        });
        if (r.dados.estado) atualizarDoServidor(r.dados.estado);
        espera = 0;
        return guardar().then(function () { preencher(); if (estado.fila.length) agendar(0); });
      }
      lote.forEach(function (l) { l.aCaminho = false; });
      if (r.status === 404 || r.status === 410 || r.status === 409) {
        // Link vencido, revogado ou prestação finalizada: guarda o que há e para.
        guardar();
        bloquear((r.dados && r.dados.mensagem) || "Este link não aceita mais lançamentos.");
        return;
      }
      tentarDeNovo();
    }).catch(function () {
      enviando = false;
      lote.forEach(function (l) { l.aCaminho = false; });
      tentarDeNovo();
    });
  }

  function tentarDeNovo() {
    // 5 s, 10 s, 20 s… até 2 min; a volta da conexão ou tocar em "Enviar agora" antecipa.
    espera = Math.min(espera ? espera * 2 : 5000, 120000);
    estadoGeral();
    agendar(espera);
  }

  function atualizarDoServidor(novo) {
    // O que o servidor tem passa a valer para os trechos sem nada na fila — assim
    // a correção feita no escritório também aparece aqui.
    (novo.trechos || []).forEach(function (t) {
      if (pendentes(t.id)) return;
      var local = estado.valores[t.id];
      var enviado = local ? local.enviado : false;
      if (local && !estado.recusas[t.id]) estado.valores[t.id] = { enviado: enviado };
    });
    var mesmaForma = trechos().map(function (t) { return t.id; }).join() === (novo.trechos || []).map(function (t) { return t.id; }).join();
    estado.servidor = novo;
    if (novo.travado) bloquear("A prestação de contas desta viagem já foi finalizada; o diário não aceita mais alterações.");
    if (!mesmaForma) montar();
  }

  // --- Eventos ------------------------------------------------------------
  elTrechos.addEventListener("change", function (e) {
    var no = e.target.closest("[data-dc-linha]");
    if (no && e.target.matches("[data-dc-campo]")) lancar(no);
  });
  elTrechos.addEventListener("input", function (e) {
    if (e.target.matches('input[inputmode="numeric"]')) e.target.value = e.target.value.replace(/\D/g, "").slice(0, 7);
  });
  elTrechos.addEventListener("click", function (e) {
    var botao = e.target.closest("[data-dc-sugerir]");
    if (!botao) return;
    e.preventDefault();
    var no = botao.closest("[data-dc-linha]");
    no.querySelector('[data-dc-campo="' + botao.dataset.dcSugerir + '"]').value = botao.dataset.valor;
    lancar(no);
  });
  elEnviar.addEventListener("click", function () { espera = 0; agendar(0); });
  window.addEventListener("online", function () { espera = 0; agendar(0); });
  window.addEventListener("offline", estadoGeral);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) agendar(0); });

  // --- Início -------------------------------------------------------------
  carregar().then(function (salvo) {
    if (salvo) {
      estado.valores = salvo.valores || {};
      estado.fila = (salvo.fila || []).map(function (l) { l.aCaminho = false; return l; });
      estado.recusas = salvo.recusas || {};
    }
    // Com a página vinda da rede, os dados dela são os mais novos; aberta sem
    // sinal (cópia do service worker), vale o último que o servidor devolveu.
    if (salvo && salvo.servidor && navigator.onLine === false) estado.servidor = salvo.servidor;
    else atualizarDoServidor(estado.servidor);
    if (estado.servidor.travado) bloqueado = true;
    montar();
    if (bloqueado) bloquear("A prestação de contas desta viagem já foi finalizada; o diário não aceita mais alterações.");
    guardar();
    agendar(0);
  });

  if ("serviceWorker" in navigator && URL_SW) {
    navigator.serviceWorker.register(URL_SW).then(function () {
      return navigator.serviceWorker.ready;
    }).then(function (reg) {
      var urls = [location.pathname];
      document.querySelectorAll("[data-dc-guardar]").forEach(function (el) { urls.push(el.getAttribute("href") || el.getAttribute("src")); });
      var manifesto = document.querySelector('link[rel="manifest"]');
      if (manifesto) urls.push(manifesto.getAttribute("href"));
      if (reg.active) reg.active.postMessage({ tipo: "guardar", urls: urls });
    }).catch(function () { /* sem service worker: a página funciona, só não abre sem sinal */ });
  }
})();
