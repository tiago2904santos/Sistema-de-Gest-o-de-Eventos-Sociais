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

  /* O que se edita na folha da OS (editor de documentos) grava na
     solicitação: o formulário da etapa acompanha os valores e a versão, para
     "Salvar" depois não desfazer a edição nem acusar alteração de outra pessoa. */
  var form = document.getElementById("form-coffee-break");
  if (form) document.addEventListener("documento:gravado", function (evento) {
    var detalhe = evento.detail || {};
    Object.keys(detalhe.valores || {}).forEach(function (nome) {
      var campo = form.elements.namedItem(nome);
      if (!campo || campo.closest(".de-app") || campo.disabled) return;
      campo.value = detalhe.valores[nome] == null ? "" : detalhe.valores[nome];
    });
    var versao = form.querySelector(":scope > input[name=versao]");
    if (versao && detalhe.versao) versao.value = detalhe.versao;
  });
})();
