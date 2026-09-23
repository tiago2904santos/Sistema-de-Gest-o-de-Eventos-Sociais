/* Coffee Break — visualizador de documento no bloco, como o de Viagens
   (viagens-planos.js): o PDF só é pedido quando o cartão abre, e clicar no
   menu de ações não abre nem fecha o cartão. */
(function () {
  "use strict";
  document.querySelectorAll("[data-ofc-doc]").forEach(function (cartao) {
    function carregar() {
      if (!cartao.open) return;
      var quadro = cartao.querySelector(":scope > .ofc-doc__corpo > iframe[data-src]");
      if (quadro && !quadro.getAttribute("src")) quadro.setAttribute("src", quadro.getAttribute("data-src"));
    }
    cartao.addEventListener("toggle", carregar);
    carregar();
    var acoes = cartao.querySelector(":scope > summary .ofc-doc__acoes");
    if (acoes) acoes.addEventListener("click", function (evento) {
      if (evento.target.closest("[data-menu-gatilho]")) evento.preventDefault();
    });
  });
})();
