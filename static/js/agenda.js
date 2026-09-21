/* Agenda — calendário, cabeçalho próprio, filtros e o modal do dossiê.

   Dois tipos de filtro, e a diferença importa:
   - Fonte (viagens, solicitações…) muda o que o servidor devolve, então
     refaz a busca. Uma fonte desligada nem chega ao navegador.
   - Situação, município, tipo, "só o que eu criei" e busca por texto são
     locais: filtram o que já veio. O período visível fica em cache, então
     mexer neles não toca o servidor — e as opções de situação/município/tipo
     são montadas a partir do que está carregado, com contagem.

   O modal não monta HTML: pede o dossiê pronto ao servidor (agenda:detalhe),
   que é onde a permissão mora. Aqui só se liga aba e fechamento.

   Preferências (visão, filtros) ficam no localStorage — conveniência deste
   navegador, nunca estado do sistema. */
(function () {
  "use strict";

  var el = document.getElementById("agenda");
  if (!el || !window.FullCalendar) return;

  var CHAVE = "agenda.v2";
  var urlEventos = el.dataset.urlEventos;
  var urlDetalhe = el.dataset.urlDetalhe; // termina em /f/0/ — trocado por fonte/pk

  var $ = function (id) { return document.getElementById(id); };
  var caixas = Array.prototype.slice.call(document.querySelectorAll('input[name="fonte"]'));
  var elSituacoes = $("ag-situacoes");
  var selMunicipio = $("ag-municipio");
  var selTipo = $("ag-tipo");
  var chkMeus = $("ag-meus");
  var busca = $("ag-busca");
  var vazio = $("ag-vazio");
  var erro = $("ag-erro");
  var titulo = $("ag-titulo");
  var rotulos = {};
  document.querySelectorAll("[data-rotulo]").forEach(function (n) { rotulos[n.dataset.rotulo] = n.textContent; });

  // ---- preferências ---------------------------------------------------
  function ler() {
    try { return JSON.parse(localStorage.getItem(CHAVE) || "{}") || {}; } catch (e) { return {}; }
  }
  function gravar() {
    try { localStorage.setItem(CHAVE, JSON.stringify(pref)); } catch (e) { /* modo privado, sem espaço */ }
  }
  var pref = ler();
  pref.fontesDesligadas = pref.fontesDesligadas || [];
  pref.sitDesligadas = pref.sitDesligadas || [];   // situações ativas que a pessoa desligou
  pref.encLigadas = pref.encLigadas || [];         // encerradas que a pessoa quis ver
  caixas.forEach(function (c) { if (pref.fontesDesligadas.indexOf(c.value) !== -1) c.checked = false; });
  if (chkMeus) chkMeus.checked = !!pref.meus;

  // ---- filtros locais -------------------------------------------------
  function fontesAtivas() {
    return caixas.filter(function (c) { return c.checked; }).map(function (c) { return c.value; });
  }
  function situacaoLigada(slug, encerrado) {
    return encerrado ? pref.encLigadas.indexOf(slug) !== -1 : pref.sitDesligadas.indexOf(slug) === -1;
  }
  function passa(ev) {
    var p = ev.extendedProps || {};
    if (fontesAtivas().indexOf(p.fonte) === -1) return false;
    if (!situacaoLigada(p.fonte + ":" + p.situacao_slug, p.encerrado)) return false;
    if (pref.municipio && p.municipio !== pref.municipio) return false;
    if (pref.tipo && p.tipo !== pref.tipo) return false;
    if (chkMeus && chkMeus.checked && !p.meu) return false;
    var q = (busca && busca.value || "").trim().toLowerCase();
    if (q) {
      var alvo = (ev.title + " " + (p.detalhes || []).map(function (d) { return d[1]; }).join(" ")).toLowerCase();
      if (alvo.indexOf(q) === -1) return false;
    }
    return true;
  }

  // As opções dos filtros nascem do que está carregado: mostrar "Umuarama"
  // num mês em que não há nada em Umuarama só confunde.
  function montarOpcoes(lista) {
    var porFonte = {}, situacoes = {}, municipios = {}, tipos = {};
    lista.forEach(function (ev) {
      var p = ev.extendedProps;
      porFonte[p.fonte] = (porFonte[p.fonte] || 0) + 1;
      var chave = p.fonte + ":" + p.situacao_slug;
      var s = situacoes[chave] || (situacoes[chave] = { chave: chave, fonte: p.fonte, rotulo: p.situacao, encerrado: !!p.encerrado, n: 0 });
      s.n += 1;
      if (p.municipio) municipios[p.municipio] = (municipios[p.municipio] || 0) + 1;
      if (p.tipo) tipos[p.tipo] = (tipos[p.tipo] || 0) + 1;
    });
    document.querySelectorAll("[data-conta]").forEach(function (n) {
      var t = porFonte[n.dataset.conta] || 0; n.textContent = t ? String(t) : "";
    });
    renderSituacoes(Object.keys(situacoes).map(function (k) { return situacoes[k]; }));
    renderSelect(selMunicipio, municipios, pref.municipio);
    renderSelect(selTipo, tipos, pref.tipo);
  }
  function renderSituacoes(itens) {
    if (!elSituacoes) return;
    itens.sort(function (a, b) { return (a.encerrado - b.encerrado) || a.fonte.localeCompare(b.fonte) || a.rotulo.localeCompare(b.rotulo); });
    elSituacoes.innerHTML = "";
    if (!itens.length) { elSituacoes.innerHTML = '<p class="ag-f__dica">Nada no período.</p>'; return; }
    itens.forEach(function (s) {
      var lab = document.createElement("label");
      lab.className = "ag-chip ag-chip--" + s.fonte + (s.encerrado ? " ag-chip--enc" : "");
      lab.title = rotulos[s.fonte] || s.fonte;
      var inp = document.createElement("input");
      inp.type = "checkbox"; inp.checked = situacaoLigada(s.chave, s.encerrado);
      inp.addEventListener("change", function () {
        if (s.encerrado) {
          pref.encLigadas = pref.encLigadas.filter(function (x) { return x !== s.chave; });
          if (inp.checked) pref.encLigadas.push(s.chave);
        } else {
          pref.sitDesligadas = pref.sitDesligadas.filter(function (x) { return x !== s.chave; });
          if (!inp.checked) pref.sitDesligadas.push(s.chave);
        }
        gravar(); cal.refetchEvents();
      });
      var pt = document.createElement("span"); pt.className = "ag-chip__pt";
      var t = document.createElement("span"); t.className = "ag-chip__t"; t.textContent = s.rotulo;
      var n = document.createElement("span"); n.className = "ag-chip__n"; n.textContent = String(s.n);
      lab.appendChild(inp); lab.appendChild(pt); lab.appendChild(t); lab.appendChild(n);
      elSituacoes.appendChild(lab);
    });
  }
  function renderSelect(sel, mapa, atual) {
    if (!sel) return;
    var nomes = Object.keys(mapa).sort(function (a, b) { return a.localeCompare(b, "pt-BR"); });
    sel.innerHTML = '<option value="">Todos</option>';
    nomes.forEach(function (nome) {
      var o = document.createElement("option");
      o.value = nome; o.textContent = nome + " (" + mapa[nome] + ")";
      sel.appendChild(o);
    });
    // Mantém a escolha se ela ainda existe no período; senão, volta a "Todos"
    // e diz isso pelo próprio select, em vez de esconder tudo em silêncio.
    sel.value = (atual && mapa[atual]) ? atual : "";
  }

  // ---- cache por período ----------------------------------------------
  var cache = { chave: null, lista: [] };
  function carregar(info, ok, falhou) {
    var fontes = fontesAtivas();
    if (!fontes.length) { cache = { chave: null, lista: [] }; montarOpcoes([]); ok([]); vazio.hidden = false; return; }
    var chave = info.startStr + "|" + info.endStr + "|" + fontes.join(",");
    if (cache.chave === chave) { entregar(cache.lista, ok); return; }
    var params = new URLSearchParams({ start: info.startStr, end: info.endStr, fontes: fontes.join(",") });
    fetch(urlEventos + "?" + params.toString(), { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (lista) { cache = { chave: chave, lista: lista }; erro.hidden = true; entregar(lista, ok); })
      .catch(function (e) {
        falhou(e);
        erro.textContent = "Não deu para carregar a agenda (" + e.message + "). Recarregue a página.";
        erro.hidden = false;
      });
  }
  function entregar(lista, ok) {
    montarOpcoes(lista);
    var visiveis = lista.filter(passa);
    vazio.hidden = visiveis.length > 0;
    ok(visiveis);
  }

  // ---- o calendário (sem a barra dele: a nossa está no template) ----------
  function estreito() { return window.matchMedia("(max-width: 900px)").matches; }
  var cal = new FullCalendar.Calendar(el, {
    locale: "pt-br",
    headerToolbar: false,
    initialView: pref.view || (estreito() ? "listMonth" : "dayGridMonth"),
    views: { list30: { type: "list", duration: { days: 30 } } },
    height: "auto",
    firstDay: 0,
    navLinks: true,
    dayMaxEvents: 4,
    eventDisplay: "block",
    displayEventTime: false,
    nowIndicator: true,
    events: carregar,
    eventClick: function (arg) { arg.jsEvent.preventDefault(); abrir(arg.event); },
    eventDidMount: function (arg) {
      var p = arg.event.extendedProps || {};
      arg.el.title = arg.event.title + (p.situacao ? " — " + p.situacao : "") + " · " + (rotulos[p.fonte] || "");
    },
    datesSet: function (info) {
      titulo.textContent = info.view.title;
      document.querySelectorAll("[data-view]").forEach(function (b) {
        b.setAttribute("aria-pressed", b.dataset.view === info.view.type ? "true" : "false");
      });
      pref.view = info.view.type; gravar();
    }
  });
  cal.render();

  // ---- cabeçalho próprio ------------------------------------------------
  document.querySelectorAll("[data-ag]").forEach(function (b) {
    b.addEventListener("click", function () {
      var acao = b.dataset.ag;
      if (acao === "prev") cal.prev();
      else if (acao === "next") cal.next();
      else if (acao === "hoje") cal.today();
      else if (acao === "filtros") {
        var painel = $("ag-filtros"); var aberto = painel.classList.toggle("is-aberto");
        b.setAttribute("aria-expanded", aberto ? "true" : "false");
      }
    });
  });
  document.querySelectorAll("[data-view]").forEach(function (b) {
    b.addEventListener("click", function () { cal.changeView(b.dataset.view); });
  });
  document.querySelectorAll("[data-ir]").forEach(function (b) {
    b.addEventListener("click", function () {
      var alvo = b.dataset.ir;
      if (alvo === "semana") cal.changeView("timeGridWeek");
      else if (alvo === "mes") cal.changeView("dayGridMonth");
      else if (alvo === "30") cal.changeView("list30");
      cal.today();
    });
  });

  // ---- filtros ---------------------------------------------------------
  caixas.forEach(function (c) {
    c.addEventListener("change", function () {
      pref.fontesDesligadas = caixas.filter(function (x) { return !x.checked; }).map(function (x) { return x.value; });
      gravar(); cal.refetchEvents();
    });
  });
  if (selMunicipio) selMunicipio.addEventListener("change", function () { pref.municipio = selMunicipio.value; gravar(); cal.refetchEvents(); });
  if (selTipo) selTipo.addEventListener("change", function () { pref.tipo = selTipo.value; gravar(); cal.refetchEvents(); });
  if (chkMeus) chkMeus.addEventListener("change", function () { pref.meus = chkMeus.checked; gravar(); cal.refetchEvents(); });
  var temporizador = null;
  if (busca) busca.addEventListener("input", function () {
    clearTimeout(temporizador);
    temporizador = setTimeout(function () { cal.refetchEvents(); }, 150);
  });
  var limpar = $("ag-limpar");
  if (limpar) limpar.addEventListener("click", function () {
    pref.fontesDesligadas = []; pref.sitDesligadas = []; pref.encLigadas = [];
    pref.municipio = ""; pref.tipo = ""; pref.meus = false;
    caixas.forEach(function (c) { c.checked = true; });
    if (chkMeus) chkMeus.checked = false;
    if (busca) busca.value = "";
    gravar(); cal.refetchEvents();
  });

  // ---- modal do dossiê ---------------------------------------------------
  var modal = $("ag-modal");
  var corpo = $("ag-modal-c");
  var ultimoFoco = null;

  function abrir(ev) {
    var p = ev.extendedProps || {};
    ultimoFoco = document.activeElement;
    corpo.innerHTML = '<p class="ag-m__carregando">Carregando…</p>';
    if (typeof modal.showModal === "function") { if (!modal.open) modal.showModal(); }
    else modal.setAttribute("open", "");
    var url = urlDetalhe.replace("/f/0/", "/" + encodeURIComponent(p.fonte) + "/" + encodeURIComponent(p.numero) + "/");
    fetch(url, { credentials: "same-origin" })
      .then(function (r) {
        if (r.status === 403) throw new Error("Este compromisso está fora do seu acesso.");
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.text();
      })
      .then(function (html) { corpo.innerHTML = html; ligarModal(); })
      .catch(function (e) {
        corpo.innerHTML = '<div class="ag-m"><header class="ag-m__topo"><div class="ag-m__linha"><h2 class="ag-m__t">Não deu para abrir</h2></div>' +
          '<div class="ag-m__acoes"><button type="button" class="ag-m__x" data-ag-fechar aria-label="Fechar">&times;</button></div></header>' +
          '<section class="ag-painel"><p class="ag-erro" style="text-align:left">' + escapar(e.message) + "</p></section></div>";
        ligarModal();
      });
  }
  function ligarModal() {
    corpo.querySelectorAll("[data-ag-fechar]").forEach(function (b) { b.addEventListener("click", fechar); });
    var abas = corpo.querySelectorAll("[data-aba]");
    abas.forEach(function (b) {
      b.addEventListener("click", function () {
        abas.forEach(function (x) { x.setAttribute("aria-selected", x === b ? "true" : "false"); });
        corpo.querySelectorAll("[data-painel]").forEach(function (s) { s.hidden = s.dataset.painel !== b.dataset.aba; });
        corpo.scrollTop = 0;
      });
    });
    var x = corpo.querySelector("[data-ag-fechar]");
    if (x) x.focus();
  }
  function fechar() {
    if (modal.open && typeof modal.close === "function") modal.close();
    else modal.removeAttribute("open");
    if (ultimoFoco && ultimoFoco.focus) ultimoFoco.focus();
  }
  // Clique no fundo escurecido fecha: o `dialog` recebe o clique, o miolo não.
  modal.addEventListener("click", function (e) { if (e.target === modal) fechar(); });
  modal.addEventListener("close", function () { if (ultimoFoco && ultimoFoco.focus) ultimoFoco.focus(); });
  function escapar(t) { var d = document.createElement("div"); d.textContent = t; return d.innerHTML; }
})();
