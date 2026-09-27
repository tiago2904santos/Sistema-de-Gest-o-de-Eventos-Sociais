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
   navegador, nunca estado do sistema. A URL espelha o mesmo estado (m137):
   ela é lida antes do localStorage e reescrita a cada mudança, para que um
   link copiado abra a agenda exatamente como está na tela. */
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
  var selPessoa = $("ag-pessoa"); // filtro por pessoa escalada (m134)
  var linkPauta = $("ag-pauta");  // "Baixar pauta" (m136)
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

  // A URL guarda o que está na tela (m137): visão, período, fontes, situação,
  // município, tipo, pessoa, "minha agenda" e busca. Ela vale mais que o
  // localStorage — um link recebido abre exatamente como foi mandado — e é
  // reescrita (replaceState) a cada mudança, sem entrar no histórico.
  var VISOES = ["dayGridMonth", "timeGridWeek", "timeGridDay", "listMonth", "list30", "multiMonthYear"];
  var url = new URLSearchParams(location.search);
  var dataInicial = /^\d{4}-\d{2}-\d{2}$/.test(url.get("data") || "") ? url.get("data") : null;
  var buscaInicial = url.get("q") || "";
  if (VISOES.indexOf(url.get("view")) !== -1) pref.view = url.get("view");
  if (url.has("fontes")) {
    var ligadas = url.get("fontes").split(",");
    pref.fontesDesligadas = caixas.map(function (c) { return c.value; }).filter(function (v) { return ligadas.indexOf(v) === -1; });
  }
  if (url.has("sit")) pref.sitDesligadas = url.get("sit").split(",").filter(Boolean);
  if (url.has("enc")) pref.encLigadas = url.get("enc").split(",").filter(Boolean);
  ["municipio", "tipo", "pessoa"].forEach(function (k) { if (url.has(k)) pref[k] = url.get(k); });
  if (url.has("meus")) pref.meus = url.get("meus") === "1";
  caixas.forEach(function (c) { if (pref.fontesDesligadas.indexOf(c.value) !== -1) c.checked = false; });
  if (chkMeus) chkMeus.checked = !!pref.meus;
  if (busca && buscaInicial) busca.value = buscaInicial;

  function sincronizarUrl() {
    if (!window.history || !history.replaceState) return;
    var p = new URLSearchParams();
    var v = cal && cal.view;
    if (v && v.currentStart) { p.set("view", v.type); p.set("data", isoLocal(v.currentStart)); }
    var fontes = fontesAtivas();
    if (fontes.length < caixas.length) p.set("fontes", fontes.join(","));
    if (pref.sitDesligadas.length) p.set("sit", pref.sitDesligadas.join(","));
    if (pref.encLigadas.length) p.set("enc", pref.encLigadas.join(","));
    ["municipio", "tipo", "pessoa"].forEach(function (k) { if (pref[k]) p.set(k, pref[k]); });
    if (chkMeus && chkMeus.checked) p.set("meus", "1");
    var q = (busca && busca.value || "").trim();
    if (q) p.set("q", q);
    var s = p.toString();
    history.replaceState(null, "", location.pathname + (s ? "?" + s : "") + location.hash);
  }

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
    // Faixa de fundo (feriado, m138): só a fonte decide; não tem situação nem município próprio.
    if (p.fundo) return true;
    if (!situacaoLigada(p.fonte + ":" + p.situacao_slug, p.encerrado)) return false;
    // Todos os municípios por onde o compromisso passa (m132), não só o primeiro.
    if (pref.municipio && (p.municipios || [p.municipio]).indexOf(pref.municipio) === -1) return false;
    if (pref.tipo && p.tipo !== pref.tipo) return false;
    if (pref.pessoa && (p.pessoas || []).indexOf(pref.pessoa) === -1) return false;
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
    var porFonte = {}, situacoes = {}, municipios = {}, tipos = {}, pessoas = {};
    lista.forEach(function (ev) {
      var p = ev.extendedProps;
      porFonte[p.fonte] = (porFonte[p.fonte] || 0) + 1;
      if (p.fundo) return; // feriado: conta na fonte, não vira situação nem município
      var chave = p.fonte + ":" + p.situacao_slug;
      var s = situacoes[chave] || (situacoes[chave] = { chave: chave, fonte: p.fonte, rotulo: p.situacao, encerrado: !!p.encerrado, n: 0 });
      s.n += 1;
      (p.municipios || [p.municipio]).forEach(function (m) { if (m) municipios[m] = (municipios[m] || 0) + 1; });
      if (p.tipo) tipos[p.tipo] = (tipos[p.tipo] || 0) + 1;
      (p.pessoas || []).forEach(function (nome) { pessoas[nome] = (pessoas[nome] || 0) + 1; });
    });
    renderSelect(selPessoa, pessoas, pref.pessoa);
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
    // Feriado (m138): no desenho do Google é uma faixa de dia inteiro, como a
    // agenda "Feriados", e não um fundo pintado na célula.
    var visiveis = lista.filter(passa).map(function (ev) {
      return ev.display === "background" ? Object.assign({}, ev, { display: "block", allDay: true }) : ev;
    });
    vazio.hidden = visiveis.length > 0;
    ok(visiveis);
    atualizarPauta();
    sincronizarUrl();
  }

  // ---- o calendário (sem a barra dele: a nossa está no template) ----------
  function estreito() { return window.matchMedia("(max-width: 900px)").matches; }
  var gca = $("gca");
  var principal = $("gca-principal");
  var MESES_CURTOS = ["jan.", "fev.", "mar.", "abr.", "mai.", "jun.", "jul.", "ago.", "set.", "out.", "nov.", "dez."];
  var DIAS_CURTOS = ["dom.", "seg.", "ter.", "qua.", "qui.", "sex.", "sáb."];
  // A grade ocupa a altura da tela, como no Google Agenda: o que não cabe
  // no dia vira "Mais N", e semana, dia e lista rolam por dentro.
  function ajustarAltura() {
    if (!principal) return;
    var topo = principal.getBoundingClientRect().top + window.scrollY;
    var alt = Math.max(estreito() ? 480 : 560, window.innerHeight - topo - 16);
    principal.style.height = alt + "px";
    if (gca) gca.style.setProperty("--gc-alt", alt + "px");
  }
  ajustarAltura();
  var cal = new FullCalendar.Calendar(el, {
    locale: "pt-br",
    headerToolbar: false,
    initialView: (VISOES.indexOf(pref.view) !== -1 && pref.view) || (estreito() ? "listMonth" : "dayGridMonth"),
    initialDate: dataInicial || undefined,
    // Visão anual (m137): os 12 meses em colunas; o servidor aceita o período inteiro.
    views: { list30: { type: "list", duration: { days: 30 } }, multiMonthYear: { multiMonthMaxColumns: 3, dayMaxEvents: 2 } },
    height: "100%",
    firstDay: 0,
    navLinks: true,
    dayMaxEvents: true,
    // Como no Google: dia inteiro e vários dias em faixa colorida; o que tem
    // hora vira "● 09:00 Título".
    eventDisplay: "auto",
    moreLinkContent: function (arg) { return "Mais " + arg.num; },
    dayPopoverFormat: { weekday: "long", day: "numeric", month: "long" },
    allDayText: "",
    scrollTime: "07:00:00",
    slotLabelFormat: { hour: "2-digit", minute: "2-digit", hour12: false },
    noEventsContent: "Nada no período com os filtros atuais.",
    // Mês: "DOM." no topo da coluna e "1 de set." no primeiro dia do mês.
    // Semana e dia: o dia da semana pequeno e o número grande, hoje em azul.
    dayHeaderContent: function (arg) {
      if (arg.view.type.indexOf("timeGrid") === 0) {
        return { html: '<span class="gca-dia"><span class="gca-dia__s">' + DIAS_CURTOS[arg.date.getDay()] + '</span><span class="gca-dia__n">' + arg.date.getDate() + "</span></span>" };
      }
      // Programação: o número grande e "SET., TER." ao lado, como no Google.
      if (arg.view.type.indexOf("list") === 0) {
        return { html: '<span class="gca-ldia__n">' + arg.date.getDate() + '</span><span class="gca-ldia__s">' + MESES_CURTOS[arg.date.getMonth()] + ", " + DIAS_CURTOS[arg.date.getDay()] + "</span>" };
      }
      return DIAS_CURTOS[arg.date.getDay()];
    },
    dayCellContent: function (arg) {
      if (arg.view.type === "dayGridMonth" && arg.date.getDate() === 1) return "1 de " + MESES_CURTOS[arg.date.getMonth()];
      return arg.dayNumberText.replace(/\D/g, "") || arg.dayNumberText;
    },
    // O que tem hora (saída do roteiro, palestra, pauta) mostra a hora; o que
    // é dia inteiro leva o horário no título, montado no servidor (m132).
    displayEventTime: true,
    eventTimeFormat: { hour: "2-digit", minute: "2-digit", hour12: false },
    nowIndicator: true,
    events: carregar,
    eventClick: function (arg) {
      arg.jsEvent.preventDefault();
      if ((arg.event.extendedProps || {}).fundo) return; // feriado: não tem dossiê
      abrir(arg.event);
    },
    // "Criar aqui" (m135): clicar num dia ou arrastar sobre vários abre o
    // menu com as telas novas (agenda-extras.js); `end` vem exclusivo.
    selectable: !!document.getElementById("ag-criar"),
    selectMirror: true,
    unselectAuto: true,
    select: function (info) {
      if (window.AgendaCriar) window.AgendaCriar.abrir(info.startStr.slice(0, 10), info.endStr.slice(0, 10));
      cal.unselect();
    },
    eventDidMount: function (arg) {
      var p = arg.event.extendedProps || {};
      if (p.fundo) { arg.el.title = arg.event.title; return; } // feriado (m138)
      arg.el.title = arg.event.title + (p.situacao ? " — " + p.situacao : "") + " · " + (rotulos[p.fonte] || "") +
        (p.conflitos && p.conflitos.length ? "\nConflito de agenda: " + p.conflitos.join("; ") : "");
    },
    datesSet: function (info) {
      titulo.textContent = info.view.title;
      document.querySelectorAll("[data-view]").forEach(function (b) {
        var sim = b.dataset.view === info.view.type;
        b.setAttribute(b.getAttribute("role") === "menuitemradio" ? "aria-checked" : "aria-pressed", sim ? "true" : "false");
        if (sim && rotuloVisao) rotuloVisao.textContent = (b.querySelector("span") || b).textContent.trim();
      });
      mini.sincronizar(info.view);
      pref.view = info.view.type; gravar();
      atualizarPauta(info);
      sincronizarUrl();
    }
  });
  // "Baixar pauta" (m136): o PDF do período visível, com as fontes e o "minha
  // agenda" atuais. O fim do FullCalendar é exclusivo; a pauta quer o último dia.
  function isoLocal(d) {
    var m = d.getMonth() + 1, dia = d.getDate();
    return d.getFullYear() + "-" + (m < 10 ? "0" : "") + m + "-" + (dia < 10 ? "0" : "") + dia;
  }
  function atualizarPauta(info) {
    var view = (info && info.view) || cal.view;
    if (!linkPauta || !view || !view.currentStart) return;
    var fim = new Date(view.currentEnd.getTime() - 86400000);
    var params = new URLSearchParams({ inicio: isoLocal(view.currentStart), fim: isoLocal(fim) });
    var fontes = fontesAtivas();
    if (fontes.length && fontes.length < caixas.length) params.set("fontes", fontes.join(","));
    if (chkMeus && chkMeus.checked) params.set("meus", "1");
    linkPauta.href = linkPauta.dataset.base + "?" + params.toString();
  }
  var rotuloVisao = $("gca-visao-rotulo");

  // ---- minicalendário (à esquerda, como no Google) -----------------------
  var mini = (function () {
    var caixa = $("gca-mini");
    var mes = null, faixa = null;
    var seta = function (d) { return '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="' + (d < 0 ? "M15.41 7.41 14 6l-6 6 6 6 1.41-1.41L10.83 12z" : "M8.59 16.59 10 18l6-6-6-6-1.41 1.41L13.17 12z") + '"/></svg>'; };
    function desenhar() {
      if (!caixa || !mes) return;
      var hoje = isoLocal(new Date());
      var inicio = new Date(mes.getFullYear(), mes.getMonth(), 1);
      inicio.setDate(1 - inicio.getDay());
      var nomeMes = mes.toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
      var h = '<div class="gca-mini__topo"><span class="gca-mini__t">' + nomeMes.charAt(0).toUpperCase() + nomeMes.slice(1) + "</span>" +
        '<button type="button" class="gca-ico" data-mini="-1" aria-label="Mês anterior">' + seta(-1) + "</button>" +
        '<button type="button" class="gca-ico" data-mini="1" aria-label="Próximo mês">' + seta(1) + "</button></div>" +
        "<table><thead><tr>" + ["D", "S", "T", "Q", "Q", "S", "S"].map(function (l) { return "<th>" + l + "</th>"; }).join("") + "</tr></thead><tbody>";
      var d = new Date(inicio);
      for (var s = 0; s < 6; s++) {
        h += "<tr>";
        for (var i = 0; i < 7; i++) {
          var iso = isoLocal(d);
          var cls = "gca-mini__d" + (d.getMonth() !== mes.getMonth() ? " is-fora" : "") + (iso === hoje ? " is-hoje" : "") +
            (faixa && iso >= faixa[0] && iso < faixa[1] ? " is-sel" : "");
          h += '<td><button type="button" class="' + cls + '" data-dia="' + iso + '" aria-label="' + d.toLocaleDateString("pt-BR", { day: "numeric", month: "long", year: "numeric" }) + '">' + d.getDate() + "</button></td>";
          d.setDate(d.getDate() + 1);
        }
        h += "</tr>";
      }
      caixa.innerHTML = h + "</tbody></table>";
    }
    if (caixa) caixa.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      if (b.dataset.mini) { mes = new Date(mes.getFullYear(), mes.getMonth() + Number(b.dataset.mini), 1); desenhar(); }
      else if (b.dataset.dia) cal.gotoDate(b.dataset.dia);
    });
    return {
      sincronizar: function (view) {
        var ref = view.type === "dayGridMonth" || view.type === "listMonth" || view.type === "multiMonthYear" ? view.currentStart : view.activeStart;
        mes = new Date(ref.getFullYear(), ref.getMonth(), 1);
        // Semana e dia marcam os dias na tela; mês, ano e lista não marcam nada.
        faixa = view.type.indexOf("timeGrid") === 0 ? [isoLocal(view.currentStart), isoLocal(view.currentEnd)] : null;
        desenhar();
      }
    };
  })();

  cal.render();
  window.addEventListener("resize", function () { ajustarAltura(); cal.updateSize(); });

  // ---- menu das visões (Dia, Semana, Mês…) ----------------------------------
  var btnVisao = $("gca-visao"), menuVisao = $("gca-visao-menu");
  function menu(abrirMenu) {
    if (!menuVisao) return;
    menuVisao.hidden = !abrirMenu;
    btnVisao.setAttribute("aria-expanded", abrirMenu ? "true" : "false");
    if (abrirMenu) { var marcado = menuVisao.querySelector('[aria-checked="true"]') || menuVisao.querySelector("button"); if (marcado) marcado.focus(); }
  }
  if (btnVisao) btnVisao.addEventListener("click", function (e) { e.stopPropagation(); menu(menuVisao.hidden); });
  document.addEventListener("click", function (e) { if (menuVisao && !menuVisao.hidden && !menuVisao.contains(e.target)) menu(false); });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && menuVisao && !menuVisao.hidden) { menu(false); btnVisao.focus(); }
  });

  // ---- atalhos de teclado do Google Agenda -------------------------------------
  var ATALHOS = { d: "timeGridDay", "1": "timeGridDay", w: "timeGridWeek", "2": "timeGridWeek", m: "dayGridMonth", "3": "dayGridMonth", y: "multiMonthYear", a: "listMonth", x: "list30" };
  document.addEventListener("keydown", function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    var alvo = e.target;
    if (alvo && (alvo.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(alvo.tagName))) return;
    if (document.querySelector("dialog[open]")) return;
    var k = e.key.toLowerCase();
    if (ATALHOS[k]) cal.changeView(ATALHOS[k]);
    else if (k === "t") cal.today();
    else if (k === "j" || k === "n") cal.next();
    else if (k === "k" || k === "p") cal.prev();
    else if (k === "/" && busca) busca.focus();
    else if (k === "c") { var criarBtn = document.querySelector("[data-ag-criar-hoje]"); if (criarBtn) criarBtn.click(); else return; }
    else return;
    e.preventDefault();
  });

  // ---- cabeçalho próprio ------------------------------------------------
  document.querySelectorAll("[data-ag]").forEach(function (b) {
    b.addEventListener("click", function () {
      var acao = b.dataset.ag;
      if (acao === "prev") cal.prev();
      else if (acao === "next") cal.next();
      else if (acao === "hoje") cal.today();
      else if (acao === "filtros") {
        // Menu principal: no computador recolhe a coluna da esquerda (como o
        // Google); no celular ela abre por cima da grade.
        var painel = $("ag-filtros"), aberto;
        if (estreito()) aberto = painel.classList.toggle("is-aberto");
        else aberto = !gca.classList.toggle("gca--recolhido");
        b.setAttribute("aria-expanded", aberto ? "true" : "false");
        setTimeout(function () { cal.updateSize(); }, 0);
      }
    });
  });
  document.querySelectorAll("[data-view]").forEach(function (b) {
    b.addEventListener("click", function () { cal.changeView(b.dataset.view); menu(false); if (btnVisao) btnVisao.focus(); });
  });
  // No celular, tocar fora da gaveta de filtros a fecha.
  document.addEventListener("click", function (e) {
    var painel = $("ag-filtros");
    if (!estreito() || !painel || !painel.classList.contains("is-aberto")) return;
    if (painel.contains(e.target) || e.target.closest('[data-ag="filtros"]')) return;
    painel.classList.remove("is-aberto");
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
  if (selPessoa) selPessoa.addEventListener("change", function () { pref.pessoa = selPessoa.value; gravar(); cal.refetchEvents(); });
  if (chkMeus) chkMeus.addEventListener("change", function () { pref.meus = chkMeus.checked; gravar(); cal.refetchEvents(); });
  var temporizador = null;
  if (busca) busca.addEventListener("input", function () {
    clearTimeout(temporizador);
    temporizador = setTimeout(function () { cal.refetchEvents(); }, 150);
  });
  var limpar = $("ag-limpar");
  if (limpar) limpar.addEventListener("click", function () {
    pref.fontesDesligadas = []; pref.sitDesligadas = []; pref.encLigadas = [];
    pref.municipio = ""; pref.tipo = ""; pref.pessoa = ""; pref.meus = false;
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
