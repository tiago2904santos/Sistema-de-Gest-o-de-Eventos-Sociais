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

  /* Nova solicitação: a folha da OS acompanha o formulário. A cada mudança
     (com uma pequena espera), o quadro recarrega com os valores digitados —
     nada é gravado; o palco do editor repagina quando o quadro carrega. */
  var nova = document.querySelector("[data-cb-os-nova]");
  if (form && nova) {
    var espera = null;
    var ultima = "";
    var atualizarFolha = function () {
      var quadro = nova.querySelector("iframe.dc-folha");
      if (!quadro) return;
      var dados = new URLSearchParams();
      new FormData(form).forEach(function (valor, nome) {
        if (nome === "csrfmiddlewaretoken" || typeof valor !== "string") return;
        dados.append(nome, valor);
      });
      var base = quadro.getAttribute("data-cb-base") || quadro.getAttribute("src").split("?")[0];
      quadro.setAttribute("data-cb-base", base);
      var endereco = base + "?" + dados.toString();
      if (endereco === ultima) return;
      ultima = endereco;
      quadro.setAttribute("src", endereco);
    };
    var agendar = function () {
      clearTimeout(espera);
      espera = setTimeout(atualizarFolha, 400);
    };
    form.addEventListener("input", agendar);
    form.addEventListener("change", agendar);
    // Campos fora do <form> ligados pelo atributo form (a data no cabeçalho).
    document.querySelectorAll('[form="form-coffee-break"]').forEach(function (campo) {
      campo.addEventListener("input", agendar);
      campo.addEventListener("change", agendar);
    });
    // O editor chega por fetch: quando o quadro aparece, já mostra o que está preenchido.
    new MutationObserver(function () {
      var quadro = nova.querySelector("iframe.dc-folha");
      if (quadro && !quadro.hasAttribute("data-cb-base")) { ultima = ""; atualizarFolha(); }
    }).observe(nova, { childList: true, subtree: true });
  }
})();
