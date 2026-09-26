/*
 * Tela da solicitação de evento: ajudas que só preenchem com um clique.
 *
 * - Textos prontos do despacho da DG: o botão acrescenta o texto à
 *   observação (que continua editável).
 */
(function () {
  "use strict";

  function disparar(campo) {
    campo.dispatchEvent(new Event("input", { bubbles: true }));
    campo.dispatchEvent(new Event("change", { bubbles: true }));
  }

  // ------------------------------------------------------------------
  // Textos prontos do despacho
  // ------------------------------------------------------------------
  document.querySelectorAll("[data-texto-pronto]").forEach(function (botao) {
    botao.addEventListener("click", function () {
      var alvo = document.getElementById(botao.getAttribute("data-texto-alvo"));
      if (!alvo) return;
      var texto = botao.getAttribute("data-texto-pronto");
      var atual = alvo.value.trim();
      if (atual.indexOf(texto) !== -1) return;
      alvo.value = atual ? atual + "\n" + texto : texto;
      disparar(alvo);
      alvo.focus();
    });
  });
})();
