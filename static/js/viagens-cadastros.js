(function () {
  "use strict";

  function semAcentos(valor) {
    return String(valor || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase("pt-BR");
  }

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
  document.querySelectorAll("[data-mask]").forEach(function (campo) {
    var aplicar = mascaras[campo.getAttribute("data-mask")];
    if (!aplicar) return;
    function atualizar() { campo.value = aplicar(campo.value); }
    campo.addEventListener("input", atualizar);
    atualizar();
  });

  document.querySelectorAll("[data-uppercase='true']").forEach(function (campo) {
    campo.addEventListener("blur", function () {
      campo.value = campo.value.trim().replace(/\s+/g, " ").toLocaleUpperCase("pt-BR");
    });
  });

  document.querySelectorAll("[data-multiselect]").forEach(function (raiz) {
    var busca = raiz.querySelector("[data-multiselect-search]");
    var opcoes = Array.prototype.slice.call(raiz.querySelectorAll("[data-multiselect-option]"));
    var contador = raiz.querySelector("[data-multiselect-count]");
    var rotulo = raiz.querySelector("[data-multiselect-label]");
    var vazio = raiz.querySelector("[data-multiselect-empty]");

    function contar() {
      var total = opcoes.filter(function (opcao) { return opcao.querySelector("input").checked; }).length;
      if (contador) contador.textContent = total;
      if (rotulo) rotulo.textContent = total === 1 ? "selecionado" : "selecionados";
    }

    function filtrar() {
      var termo = semAcentos(busca ? busca.value : "").trim();
      var visiveis = 0;
      opcoes.forEach(function (opcao) {
        var mostrar = semAcentos(opcao.getAttribute("data-search")).indexOf(termo) !== -1;
        opcao.hidden = !mostrar;
        if (mostrar) visiveis += 1;
      });
      if (vazio) vazio.hidden = visiveis !== 0 || opcoes.length === 0;
    }

    opcoes.forEach(function (opcao) {
      opcao.querySelector("input").addEventListener("change", contar);
    });
    if (busca) busca.addEventListener("input", filtrar);
    contar();
  });

  var diaria = document.querySelector("[data-diaria-base]");
  if (diaria) {
    var quinze = document.querySelector("[data-diaria-15]");
    var trinta = document.querySelector("[data-diaria-30]");
    var dinheiro = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
    function numero(valor) {
      var texto = String(valor || "").trim();
      if (texto.indexOf(",") >= 0) texto = texto.replace(/\./g, "").replace(",", ".");
      var resultado = Number(texto);
      return Number.isFinite(resultado) ? resultado : 0;
    }
    function atualizarDiaria() {
      var base = numero(diaria.value);
      if (quinze) quinze.textContent = dinheiro.format(base * 0.15);
      if (trinta) trinta.textContent = dinheiro.format(base * 0.30);
    }
    diaria.addEventListener("input", atualizarDiaria);
    atualizarDiaria();
  }

  var resumo = document.querySelector("[data-resumo-erros]");
  if (resumo) resumo.focus();
})();
