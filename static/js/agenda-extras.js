/* Agenda — complementos da onda AG-B, fora do calendário em si (agenda.js):
   - o modal "Assinar": abre/fecha, recompõe o link do feed conforme as
     caixas (fontes, "só a minha agenda") e copia para a área de transferência.

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
