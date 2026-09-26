/**
 * "Gerar documentos" da viagem (m064): o contador de equipe ao vivo.
 *
 * Soma, sem repetir ninguém, quem já está nos ofícios da viagem
 * (`data-ja-em-oficios`), quem foi escolhido nas equipes desta tela e os
 * motoristas (que entram na equipe do seu ofício), e compara com a meta da
 * DG (`data-meta`). Sem JS a tela funciona igual: o texto só não se atualiza.
 */
(function () {
  "use strict";

  var form = document.querySelector("[data-gerar-documentos]");
  if (!form) return;
  var saida = form.querySelector("[data-gerar-contador]");
  var meta = parseInt(form.getAttribute("data-meta") || "0", 10) || 0;
  var existentes = (form.getAttribute("data-ja-em-oficios") || "").split(",").filter(Boolean);

  function plural(n, um, varios) { return n === 1 ? um : varios; }

  function atualizar() {
    var todos = {};
    existentes.forEach(function (pk) { todos[pk] = true; });
    var novos = {};
    form.querySelectorAll('input[type="checkbox"][name$="-servidores"]:checked').forEach(function (c) { novos[c.value] = true; });
    form.querySelectorAll('select[name$="-motorista"]').forEach(function (s) { if (s.value) novos[s.value] = true; });
    Object.keys(novos).forEach(function (pk) { todos[pk] = true; });
    var total = Object.keys(todos).length;
    var aqui = Object.keys(novos).filter(function (pk) { return existentes.indexOf(pk) === -1; }).length;
    var texto = total + " " + plural(total, "servidor", "servidores") + " na viagem (" + aqui + " nesta tela)";
    if (meta) {
      var faltam = Math.max(meta - total, 0);
      texto += faltam
        ? " — faltam " + faltam + " para os " + meta + " designados pela DG."
        : " — a meta de " + meta + " designados pela DG está batida.";
      saida.classList.toggle("vg-gerar__contador--falta", faltam > 0);
    } else {
      texto += ". A DG não fixou quantidade.";
    }
    saida.textContent = texto;
  }

  form.addEventListener("change", atualizar);
  atualizar();
})();
