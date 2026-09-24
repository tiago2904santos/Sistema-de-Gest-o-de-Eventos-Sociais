/* Coffee Break — etapa 2: "Vincular outra OS" no cabeçalho do cartão abre a
   lista de escolha das OS do mesmo lote (como a dos palestrantes). Abre
   sozinho quando já há pagamento conjunto ou quando a lista muda. */
(function () {
  "use strict";
  var botao = document.querySelector("[data-cb-vincular-abrir]");
  var painel = document.querySelector("[data-cb-vincular]");
  if (!botao || !painel) return;
  function abrir(sim) {
    painel.hidden = !sim;
    botao.setAttribute("aria-expanded", sim ? "true" : "false");
    if (sim) {
      var busca = painel.querySelector("[data-lista-busca]");
      if (busca) busca.focus();
    }
  }
  botao.addEventListener("click", function () { abrir(painel.hidden); });
})();
