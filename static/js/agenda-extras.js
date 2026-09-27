/* Agenda — complementos da onda AG-B, fora do calendário em si (agenda.js):
   - o modal "Assinar": abre/fecha, recompõe o link do feed conforme as
     caixas (fontes, "só a minha agenda") e copia para a área de transferência;
   - o modal "Criar aqui" (window.AgendaCriar), chamado pela seleção de dias;
   - o formulário de filtros da escala.

   Qualquer botão com data-ag-abrir="<id>" abre o <dialog> daquele id; um
   botão com data-ag-assinar-fechar (ou clique no fundo, ou Esc) fecha. */
(function () {
  "use strict";

  function abrirDialogo(d) {
    if (!d) return;
    if (typeof d.showModal === "function") { if (!d.open) d.showModal(); }
    else d.setAttribute("open", "");
  }
  function fecharDialogo(d) {
    if (!d) return;
    if (d.open && typeof d.close === "function") d.close();
    else d.removeAttribute("open");
  }

  document.querySelectorAll("[data-ag-abrir]").forEach(function (b) {
    b.addEventListener("click", function () { abrirDialogo(document.getElementById(b.dataset.agAbrir)); });
  });
  document.querySelectorAll("dialog.an-dialogo").forEach(function (d) {
    // Clique no fundo escurecido fecha: o `dialog` recebe o clique, o miolo não.
    d.addEventListener("click", function (e) { if (e.target === d) fecharDialogo(d); });
    d.querySelectorAll("[data-ag-assinar-fechar], [data-ag-fechar-dialogo]").forEach(function (b) {
      b.addEventListener("click", function () { fecharDialogo(d); });
    });
  });

  // ---- assinatura (m133) --------------------------------------------------
  var assinar = document.getElementById("ag-assinar");
  if (assinar) {
    var campo = assinar.querySelector("[data-ics-url]");
    var baixar = assinar.querySelector("[data-ics-baixar]");
    var fontes = Array.prototype.slice.call(assinar.querySelectorAll("[data-ics-fonte]"));
    var meus = assinar.querySelector("[data-ics-meus]");
    function recompor() {
      if (!campo) return;
      var base = campo.dataset.icsBase;
      var ligadas = fontes.filter(function (c) { return c.checked; }).map(function (c) { return c.value; });
      var params = new URLSearchParams();
      // Todas ligadas = sem parâmetro: o feed já traz tudo o que a pessoa vê.
      if (ligadas.length && ligadas.length < fontes.length) params.set("fontes", ligadas.join(","));
      if (meus && meus.checked) params.set("meus", "1");
      var q = params.toString();
      campo.value = base + (q ? "?" + q : "");
      if (baixar) baixar.href = campo.value;
    }
    fontes.concat(meus ? [meus] : []).forEach(function (c) { c.addEventListener("change", recompor); });
    var copiar = assinar.querySelector("[data-ics-copiar]");
    var copiado = assinar.querySelector("[data-ics-copiado]");
    if (copiar) copiar.addEventListener("click", function () {
      if (!campo) return;
      var ok = function () { if (copiado) { copiado.hidden = false; setTimeout(function () { copiado.hidden = true; }, 2500); } };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(campo.value).then(ok, function () { campo.select(); });
      else { campo.select(); try { document.execCommand("copy"); ok(); } catch (e) { /* a seleção já basta */ } }
    });
    // Volta do POST (gerar/revogar): a URL vem com #assinar e o modal reabre.
    if (location.hash === "#assinar") { abrirDialogo(assinar); history.replaceState(null, "", location.pathname + location.search); }
  }

  // ---- "Criar aqui" (m135) ------------------------------------------------
  // agenda.js chama window.AgendaCriar.abrir(inicio, fimExclusivo) na seleção
  // de dias; aqui as datas entram no título, nos links (?inicio=&fim=) e no
  // formulário POST da viagem. O fim vem exclusivo do FullCalendar e vira o
  // último dia de verdade, que é o que as telas esperam.
  var criar = document.getElementById("ag-criar");
  if (criar) {
    var periodo = criar.querySelector("[data-criar-periodo]");
    function diaAntes(iso) {
      var d = new Date(iso + "T12:00:00");
      d.setDate(d.getDate() - 1);
      return d.toISOString().slice(0, 10);
    }
    function porExtenso(iso) {
      var d = new Date(iso + "T12:00:00");
      return d.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit", year: "numeric" });
    }
    window.AgendaCriar = {
      abrir: function (inicio, fimExclusivo) {
        var fim = fimExclusivo ? diaAntes(fimExclusivo) : inicio;
        if (fim < inicio) fim = inicio;
        if (periodo) periodo.textContent = inicio === fim ? "Em " + porExtenso(inicio) + "." : "De " + porExtenso(inicio) + " a " + porExtenso(fim) + ".";
        var q = "?" + new URLSearchParams({ inicio: inicio, fim: fim }).toString();
        criar.querySelectorAll("[data-criar-link]").forEach(function (a) { a.href = a.dataset.base + q; });
        criar.querySelectorAll("[data-criar-inicio]").forEach(function (i) { i.value = inicio; });
        criar.querySelectorAll("[data-criar-fim]").forEach(function (i) { i.value = fim; });
        abrirDialogo(criar);
        var primeiro = criar.querySelector(".ag-criar__item");
        if (primeiro) primeiro.focus();
      }
    };
    // O botão "Criar" do cabeçalho: hoje, sem precisar clicar no dia.
    var hoje = (document.getElementById("agenda") || {}).dataset ? document.getElementById("agenda").dataset.hoje : "";
    document.querySelectorAll("[data-ag-criar-hoje]").forEach(function (b) {
      b.addEventListener("click", function () { window.AgendaCriar.abrir(hoje || new Date().toISOString().slice(0, 10), ""); });
    });
  }

  // ---- escala (m134): as caixas de fonte viram o parâmetro `fontes` ------
  var formEscala = document.querySelector(".ag-escala__filtros");
  if (formEscala) {
    formEscala.addEventListener("submit", function () {
      var caixas = Array.prototype.slice.call(formEscala.querySelectorAll("[data-escala-fonte]"));
      var ligadas = caixas.filter(function (c) { return c.checked; }).map(function (c) { return c.value; });
      var oculto = formEscala.querySelector("[data-escala-fontes]");
      // Todas ligadas = sem parâmetro. As caixas não vão na URL: só o resumo.
      if (oculto) oculto.value = (ligadas.length && ligadas.length < caixas.length) ? ligadas.join(",") : "";
      caixas.forEach(function (c) { c.disabled = true; });
    });
  }
})();
