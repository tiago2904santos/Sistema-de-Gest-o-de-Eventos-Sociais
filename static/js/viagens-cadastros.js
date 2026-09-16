/* Campos dos cadastros de viagens: máscaras (CPF, RG, telefone, placa) e
   caixa alta ao sair do campo. O seletor múltiplo com busca saiu daqui para o
   `multi-pick.js`, que o cadastro de termo também usa.

   `ligar(raiz)` é chamado no carregamento e de novo a cada modal aberto — o
   formulário chega pronto do servidor via fetch, e o DS avisa pelo evento
   `ds:aprimorar`. Cada elemento é ligado uma única vez. */
(function () {
  "use strict";

  function somenteDigitos(valor, limite) {
    return String(valor || "").replace(/\D/g, "").slice(0, limite);
  }

  function mascaraCpf(valor) {
    var d = somenteDigitos(valor, 11);
    return d
      .replace(/^(\d{3})(\d)/, "$1.$2")
      .replace(/^(\d{3})\.(\d{3})(\d)/, "$1.$2.$3")
      .replace(/\.(\d{3})(\d)/, ".$1-$2");
  }

  function mascaraTelefone(valor) {
    var d = somenteDigitos(valor, 11);
    if (d.length <= 10) {
      return d.replace(/^(\d{2})(\d)/, "($1) $2").replace(/(\d{4})(\d)/, "$1-$2");
    }
    return d.replace(/^(\d{2})(\d)/, "($1) $2").replace(/(\d{5})(\d)/, "$1-$2");
  }

  function mascaraRg(valor) {
    if (/[A-Za-zÀ-ÿ]/.test(valor)) return String(valor).toLocaleUpperCase("pt-BR");
    var d = somenteDigitos(valor, 9);
    return d
      .replace(/^(\d{2})(\d)/, "$1.$2")
      .replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
      .replace(/\.(\d{3})(\d)/, ".$1-$2");
  }

  function mascaraPlaca(valor) {
    var placa = String(valor || "").replace(/[^A-Za-z0-9]/g, "").slice(0, 7).toUpperCase();
    return /^[A-Z]{3}\d{1,4}$/.test(placa) && placa.length > 3
      ? placa.slice(0, 3) + "-" + placa.slice(3)
      : placa;
  }

  var mascaras = { cpf: mascaraCpf, telefone: mascaraTelefone, rg: mascaraRg, placa: mascaraPlaca };

  // Religar o mesmo campo duplicaria máscara e contagem; marca quem já foi.
  function pendentes(raiz, seletor) {
    return Array.prototype.filter.call(raiz.querySelectorAll(seletor), function (elemento) {
      if (elemento.dataset.viagensLigado) return false;
      elemento.dataset.viagensLigado = "1";
      return true;
    });
  }

  function ligarMascaras(raiz) {
    pendentes(raiz, "[data-mask]").forEach(function (campo) {
      var aplicar = mascaras[campo.getAttribute("data-mask")];
      if (!aplicar) return;
      function atualizar() { campo.value = aplicar(campo.value); }
      campo.addEventListener("input", atualizar);
      atualizar();
    });

    pendentes(raiz, "[data-uppercase='true']").forEach(function (campo) {
      campo.addEventListener("blur", function () {
        campo.value = campo.value.trim().replace(/\s+/g, " ").toLocaleUpperCase("pt-BR");
      });
    });
  }

  function ligarPreviaDiaria(raiz) {
    pendentes(raiz, "[data-diaria-base]").forEach(function (base) {
      var quinze = raiz.querySelector("[data-diaria-15]");
      var trinta = raiz.querySelector("[data-diaria-30]");
      var dinheiro = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

      function numero(valor) {
        // O campo é numérico (ponto decimal), mas aceita vírgula digitada.
        var resultado = parseFloat(String(valor || "").trim().replace(",", "."));
        return Number.isFinite(resultado) ? resultado : 0;
      }

      function atualizar() {
        var valor = numero(base.value);
        // Os percentuais gravados saem do servidor; aqui é só a prévia.
        if (quinze) quinze.textContent = dinheiro.format(valor * 0.15);
        if (trinta) trinta.textContent = dinheiro.format(valor * 0.30);
      }

      base.addEventListener("input", atualizar);
      atualizar();
    });
  }

  function ligar(raiz) {
    ligarMascaras(raiz);
    // O seletor múltiplo mora no `multi-pick.js`, compartilhado com o termo, e
    // se liga sozinho pelo mesmo `ds:aprimorar`.
    ligarPreviaDiaria(raiz);
  }

  ligar(document);
  document.addEventListener("ds:aprimorar", function (evento) {
    ligar((evento.detail && evento.detail.raiz) || document);
  });
})();
